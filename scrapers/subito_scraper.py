"""
scrapers/subito_scraper.py  —  v1.3
Parser per subito.it. Usa Selenium (via base_scraper fallback) per il bypass Cloudflare.
Strategia parsing:
  1. JSON __NEXT_DATA__ (Next.js)
  2. JSON in <script> con "ads" o "listing"
  3. HTML — selettori aggiornati dalla struttura reale del sito
"""
import json
import re
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper
from utils.logger import get_logger

logger = get_logger("scraper.subito")

NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# Subito raggruppa nella sezione "immobili" anche categorie non abitative:
# la ricerca ?q=<città> le restituisce tutte insieme. Chi cerca casa non
# vuole uffici, box auto, terreni o affitti turistici — su un campione
# reale di 459 annunci, ~30% erano di queste categorie escluse.
# "camere-posti-letto" (stanze in condivisione) è escluso di default perché
# l'app cerca "casa", non una stanza singola: rimuovi la voce dalla lista
# sotto se invece ti interessano anche quelle.
DEFAULT_EXCLUDED_CATEGORIES = {
    "uffici-locali-commerciali", "garage-e-box", "terreni-e-rustici",
    "case-vacanza", "camere-posti-letto",
}

_CATEGORY_RE = re.compile(r"subito\.it/([a-z-]+)/")


class SubitoScraper(BaseScraper):

    def _excluded_categories(self) -> set[str]:
        custom = self.site_config.get("subito_exclude_categories")
        return set(custom) if custom is not None else DEFAULT_EXCLUDED_CATEGORIES

    @staticmethod
    def _category_from_url(url: str) -> str:
        m = _CATEGORY_RE.search(url or "")
        return m.group(1) if m else ""

    def get_listings(self, search_url: str, listing_type: str = "vendita") -> list[dict]:
        results = []
        excluded = self._excluded_categories()
        skipped = 0
        for page in range(1, self.max_pages + 1):
            page_url = f"{search_url}?o={page}" if page > 1 else search_url
            resp = self.fetch(page_url)
            if resp is None:
                break

            html = resp.text
            raw_listings = self._parse(html, listing_type)
            if not raw_listings:
                logger.debug(f"[subito] p.{page} vuota, stop")
                break

            listings = []
            for l in raw_listings:
                cat = self._category_from_url(l.get("url", ""))
                if cat in excluded:
                    skipped += 1
                    continue
                listings.append(l)

            results.extend(listings)
            logger.debug(f"[subito] p.{page}: +{len(listings)} (tot {len(results)})")

        if skipped:
            logger.info(f"[Subito.it] {skipped} annunci scartati per categoria "
                       f"non residenziale (uffici/box/terreni/ecc.)")
        return results

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse(self, html: str, listing_type: str) -> list[dict]:
        """Prova JSON, poi HTML."""
        soup = BeautifulSoup(html, "lxml")

        # 1. __NEXT_DATA__
        m = NEXT_DATA_RE.search(html)
        if m:
            try:
                data = json.loads(m.group(1))
                items = self._extract_items(data)
                if items:
                    parsed = [self._from_json(i, listing_type) for i in items]
                    return [p for p in parsed if p]
            except Exception as e:
                logger.debug(f"__NEXT_DATA__ parse error: {e}")

        # 2. Script con JSON inline
        for script in soup.find_all("script", type=lambda t: not t or "json" in t.lower()):
            txt = script.string or ""
            if '"ads"' in txt or '"items"' in txt:
                try:
                    data = json.loads(txt)
                    ads = (data.get("ads") or data.get("items") or
                           data.get("listing", {}).get("ads", []))
                    if ads:
                        parsed = [self._from_json(a, listing_type) for a in ads]
                        parsed = [p for p in parsed if p]
                        if parsed:
                            return parsed
                except Exception:
                    pass

        # 3. HTML selectors
        return self._parse_html(soup, listing_type)

    def _extract_items(self, data: dict) -> list | None:
        """Naviga la struttura Next.js di subito.it.

        Struttura 2026: initialState.items.originalList (+ galleryList).
        Manteniamo i percorsi vecchi come fallback."""
        try:
            pp = data.get("props", {}).get("pageProps", {})
            # Percorso 2026: items.originalList + galleryList
            items_node = pp.get("initialState", {}).get("items", {})
            if isinstance(items_node, dict):
                combined, seen = [], set()
                for key in ("galleryList", "originalList"):
                    for a in items_node.get(key, []) or []:
                        urn = a.get("urn") or id(a)
                        if urn not in seen:
                            seen.add(urn)
                            combined.append(a)
                if combined:
                    return combined
            # Percorso vecchio 1
            ads = pp.get("initialState", {}).get("listing", {}).get("ads")
            if ads:
                return ads
            # Percorso vecchio 2
            for q in pp.get("dehydratedState", {}).get("queries", []):
                items = q.get("state", {}).get("data", {}).get("ads")
                if items:
                    return items
            # Percorso vecchio 3
            return pp.get("ads") or pp.get("items")
        except Exception:
            return None

    @staticmethod
    def _feature(features, key: str) -> str:
        """features['/key'] → primo values[].value (struttura 2026)."""
        f = features.get(key) if isinstance(features, dict) else None
        if not isinstance(f, dict):
            return ""
        vals = f.get("values", [])
        if vals and isinstance(vals[0], dict):
            return str(vals[0].get("value", "") or vals[0].get("key", ""))
        return str(f.get("value", "") or "")

    def _from_json(self, item: dict, listing_type: str) -> dict | None:
        url = item.get("urls", {}).get("default", "") or item.get("url", "")
        if not url:
            return None
        if not url.startswith("http"):
            url = "https://www.subito.it" + url

        title = item.get("subject", "") or item.get("title", "")
        price = self._get_price(item)
        location = self._get_location(item)
        date = (item.get("date", "") or
                (item.get("date_time", "") or "")[:10])

        return self.normalize(title=title, url=url, price=price,
                              location=location, date=date,
                              listing_type=listing_type)

    def _get_price(self, item: dict) -> str:
        feats = item.get("features", {})
        # struttura 2026: features è un dict con chiave "/price"
        if isinstance(feats, dict):
            raw = self._feature(feats, "/price")
            if raw:
                digits = re.sub(r"[^\d]", "", raw)
                return f"{digits} €" if digits else raw
        # struttura vecchia: lista params
        if isinstance(feats, list):
            for param in feats:
                if param.get("name") == "price":
                    vals = param.get("values", [])
                    if vals:
                        return f"{vals[0].get('key', '')} €"
        for param in item.get("params", []):
            if param.get("name") == "price":
                vals = param.get("values", [])
                if vals:
                    return f"{vals[0].get('key', '')} €"
        p = item.get("price", {})
        if isinstance(p, dict):
            return f"{p.get('amount', '')} {p.get('currency', '€')}".strip()
        return str(p) if p else ""

    def _get_location(self, item: dict) -> str:
        geo = item.get("geo", {})
        if not isinstance(geo, dict):
            return str(geo or "")
        def val(node):
            return node.get("value", "") if isinstance(node, dict) else str(node or "")
        # town (comune) → provincia → regione, senza duplicati
        parts, seen = [], set()
        for node in (geo.get("town"), geo.get("city"), geo.get("region")):
            v = val(node)
            if v and v.lower() not in seen:
                seen.add(v.lower())
                parts.append(v)
        return ", ".join(parts)

    # ── HTML fallback (struttura aggiornata 2024-2025) ────────────────────────

    def _parse_html(self, soup: BeautifulSoup, listing_type: str) -> list[dict]:
        results = []

        # Subito.it usa data-testid="listing-card" o article[class*="item"]
        cards = (
            soup.select("[data-testid='listing-card']") or
            soup.select("article[class*='item']") or
            soup.select("div[class*='item-card']") or
            soup.select(".items-list article") or
            soup.select("article")
        )

        logger.debug(f"[subito HTML] {len(cards)} card trovate")

        for card in cards:
            try:
                listing = self.parse_listing(card)
                if listing:
                    listing["listing_type"] = listing_type
                    results.append(listing)
            except Exception as e:
                logger.debug(f"Errore card: {e}")

        return results

    def parse_listing(self, el) -> dict | None:
        # Link
        a = (el.select_one("a[href*='subito.it']") or
             el.select_one("a[href*='/annunci/']") or
             el.select_one("a"))
        if not a:
            return None
        url = a.get("href", "")
        if not url:
            return None
        if not url.startswith("http"):
            url = "https://www.subito.it" + url

        # Titolo
        title_el = (el.select_one("[data-testid='listing-title']") or
                    el.select_one("h2") or el.select_one("h3") or
                    el.select_one("[class*='title']") or a)
        title = title_el.get_text(strip=True) if title_el else ""

        # Prezzo
        price_el = (el.select_one("[data-testid='listing-price']") or
                    el.select_one("[class*='price']"))
        price = price_el.get_text(strip=True) if price_el else ""

        # Città
        loc_el = (el.select_one("[data-testid='listing-location']") or
                  el.select_one("[class*='location']") or
                  el.select_one("[class*='city']"))
        location = loc_el.get_text(strip=True) if loc_el else ""

        if not title:
            return None
        return self.normalize(title=title, url=url, price=price, location=location)
