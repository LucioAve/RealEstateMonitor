"""
scrapers/idealista_scraper.py — v1.3.2 (PATCHED)
Parser per idealista.it. Usa Selenium per bypass Cloudflare.

PATCH:
  - Attesa elemento DOM prima di leggere page_source (React lazy-load)
  - Salvataggio HTML di debug quando 0 risultati
"""
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper
from utils.logger import get_logger

logger = get_logger("scraper.idealista")

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL
)


class IdealistaScraper(BaseScraper):

    def _save_debug_html(self, html: str, listing_type: str, page: int, label: str = ""):
        try:
            debug_dir = os.path.join("logs", "debug_html")
            os.makedirs(debug_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"idealista_{listing_type}_p{page}_{ts}{label}.html"
            path = os.path.join(debug_dir, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self.logger.info(f"[DIAGNOSTICA] HTML salvato: {path}")
        except Exception as e:
            self.logger.warning(f"[DIAGNOSTICA] Impossibile salvare HTML: {e}")

    def get_listings(self, search_url: str, listing_type: str = "vendita") -> list[dict]:
        results = []
        for page in range(1, self.max_pages + 1):
            page_url = (search_url if page == 1
                        else f"{search_url.rstrip('/')}/pagina-{page}.htm")

            self.logger.info(f"[Idealista] Scraping {listing_type} pagina {page}: {page_url[:80]}")

            html = None
            if self.use_selenium:
                html = self.fetch_js(page_url, wait=10.0, scroll=True,
                                     wait_for_selector="article.item")
            if html is None:
                resp = self.fetch(page_url)
                html = resp.text if resp is not None else None
            if html is None:
                self.logger.warning("[Idealista] Nessun HTML ricevuto.")
                break

            self._save_debug_html(html, listing_type, page, "_raw")

            listings = self._parse(html, listing_type)
            if not listings:
                error_desc = self.looks_like_error_page(html)
                if error_desc:
                    self.logger.warning(
                        f"[Idealista] 0 annunci: {error_desc}. "
                        f"L'URL richiesto probabilmente non è valido per "
                        f"questo sito (verifica la Città principale nella "
                        f"scheda Configurazione) — non è un problema di "
                        f"selettori CSS."
                    )
                else:
                    self.logger.warning(
                        f"[Idealista] 0 annunci parsati. "
                        f"Lunghezza HTML: {len(html)} chars. "
                        f"Contiene __NEXT_DATA__: {'__NEXT_DATA__' in html}. "
                        f"Contiene article.item: {'article.item' in html}."
                    )
                self._save_debug_html(html, listing_type, page, "_zero_results")
                break

            results.extend(listings)
            self.logger.info(f"[Idealista] p.{page}: +{len(listings)} (tot {len(results)})")

            if not self._has_next(BeautifulSoup(html, "lxml")):
                break

        self.logger.info(f"[Idealista] {listing_type}: {len(results)} annunci totali")
        return results

    def _parse(self, html: str, listing_type: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")

        m = NEXT_DATA_RE.search(html)
        if m:
            try:
                data = json.loads(m.group(1))
                items = self._extract_items(data)
                if items:
                    parsed = [self._from_json(i, listing_type) for i in items]
                    parsed = [p for p in parsed if p]
                    if parsed:
                        self.logger.info(f"[Idealista] __NEXT_DATA__: {len(parsed)} annunci validi.")
                        return parsed
                    else:
                        self.logger.info("[Idealista] __NEXT_DATA__: 0 annunci validi dopo parsing.")
                else:
                    self.logger.info("[Idealista] __NEXT_DATA__: nessun item trovato.")
            except Exception as e:
                self.logger.warning(f"[Idealista] __NEXT_DATA__ parse error: {e}")
        else:
            self.logger.info("[Idealista] __NEXT_DATA__ NON trovato nell'HTML.")

        for script in soup.find_all("script", {"type": "application/json"}):
            try:
                data = json.loads(script.string or "")
                items = (data.get("itemListElement") or
                         data.get("items") or
                         data.get("properties"))
                if items and isinstance(items, list):
                    parsed = [self._from_json(i, listing_type) for i in items]
                    parsed = [p for p in parsed if p]
                    if parsed:
                        self.logger.info(f"[Idealista] script JSON: {len(parsed)} annunci validi.")
                        return parsed
            except Exception:
                pass

        return self._parse_html(soup, listing_type)

    def _extract_items(self, data: dict) -> list | None:
        try:
            pp = data.get("props", {}).get("pageProps", {})
            for key in ["properties", "listings", "items", "ads", "elementList"]:
                v = pp.get(key)
                if isinstance(v, list) and v:
                    return v
            for q in pp.get("dehydratedState", {}).get("queries", []):
                for key in ["properties", "listings", "items", "elementList"]:
                    v = q.get("state", {}).get("data", {}).get(key)
                    if isinstance(v, list) and v:
                        return v
            return pp.get("ads") or pp.get("items")
        except Exception:
            return None

    def _from_json(self, item: dict, listing_type: str) -> dict | None:
        url = (item.get("url") or item.get("detailUrl") or
               item.get("canonicalUrl") or
               item.get("@id") or "")
        if not url:
            return None
        if not url.startswith("http"):
            url = "https://www.idealista.it" + url

        title = (item.get("title") or item.get("name") or
                 item.get("typology", {}).get("name", "") if isinstance(item.get("typology"), dict) else "")

        price = ""
        p = item.get("price") or item.get("priceInfo", {})
        if isinstance(p, dict):
            val = p.get("amount") or p.get("value") or p.get("price")
            price = f"{int(val):,} €".replace(",", ".") if val else ""
        elif isinstance(p, (int, float)):
            price = f"{int(p):,} €".replace(",", ".")

        location = ""
        addr = item.get("address") or item.get("location") or {}
        if isinstance(addr, dict):
            parts = [addr.get("neighborhood", ""), addr.get("district", ""),
                     addr.get("municipality", "") or addr.get("city", "")]
            location = ", ".join(x for x in parts if x)
        elif isinstance(addr, str):
            location = addr

        return self.normalize(title=title, url=url, price=price,
                              location=location, listing_type=listing_type)

    def _parse_html(self, soup: BeautifulSoup, listing_type: str) -> list[dict]:
        results = []

        cards = (
            soup.select("article.item") or
            soup.select("[class*='item-info-container']") or
            soup.select("section.items-list article") or
            soup.select("div[data-element-id='home-search-list'] article") or
            soup.select("article[data-ad-position]") or
            soup.select("div[class*='listing-item']") or
            soup.select("article[class*='item']") or
            soup.select("div[class*='item-card']") or
            soup.select("article")
        )

        self.logger.info(f"[Idealista HTML] {len(cards)} card trovate con selettori.")

        for card in cards:
            try:
                listing = self.parse_listing(card)
                if listing:
                    listing["listing_type"] = listing_type
                    results.append(listing)
            except Exception as e:
                self.logger.debug(f"Errore card: {e}")

        self.logger.info(f"[Idealista HTML] {len(results)} annunci validi estratti.")
        return results

    def parse_listing(self, el) -> dict | None:
        a = (el.select_one("a.item-link") or
             el.select_one("a[href*='idealista.it']") or
             el.select_one("a[href*='/immobile/']") or
             el.select_one("h3 a") or el.select_one("a"))
        if not a:
            return None
        url = a.get("href", "")
        if not url:
            return None
        if not url.startswith("http"):
            url = "https://www.idealista.it" + url

        title_el = (el.select_one("a.item-link") or
                    el.select_one("[class*='item-title']") or
                    el.select_one("h2") or el.select_one("h3") or a)
        title = title_el.get_text(strip=True) if title_el else ""

        price_el = (el.select_one(".price-row") or
                    el.select_one("[class*='item-price']") or
                    el.select_one("[class*='price']"))
        price = price_el.get_text(strip=True) if price_el else ""

        loc_el = (el.select_one("p.ellipsis") or
                  el.select_one("[class*='item-detail-char']") or
                  el.select_one("[class*='location']"))
        location = loc_el.get_text(strip=True) if loc_el else ""

        if not title:
            return None
        return self.normalize(title=title, url=url, price=price, location=location)

    def _has_next(self, soup: BeautifulSoup) -> bool:
        return bool(soup.select_one("a[rel='next'], .pagination .next a, li.next a"))
