"""
scrapers/immobiliare_scraper.py — v1.2.2 (PATCHED)
Parser per immobiliare.it

PATCH:
  - Regex __NEXT_DATA__ corretta (era vuota)
  - Salvataggio HTML di debug quando 0 risultati
"""
import json
import os
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper
from utils.logger import get_logger

logger = get_logger("scraper.immobiliare")

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL
)

API_URL = "https://www.immobiliare.it/api-next/search-list/real-estates/"


class ImmobiliareScraper(BaseScraper):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._warmed_up = False

    def _warmup(self):
        if self._warmed_up:
            return
        self.logger.debug("Warm-up immobiliare.it...")
        steps = [
            ("https://www.immobiliare.it/", "https://www.google.com/"),
            ("https://www.immobiliare.it/napoli/", "https://www.immobiliare.it/"),
        ]
        for url, referer in steps:
            try:
                self.session.get(url, timeout=self.timeout,
                                 headers={**self.session.headers, "Referer": referer})
                time.sleep(1.0)
            except Exception as e:
                self.logger.debug(f"Warm-up step fallito ({url}): {e}")
        self._warmed_up = True
        self.logger.debug("Warm-up completato.")

    def _save_debug_html(self, html: str, listing_type: str, page: int, label: str = ""):
        try:
            debug_dir = os.path.join("logs", "debug_html")
            os.makedirs(debug_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"immobiliare_{listing_type}_p{page}_{ts}{label}.html"
            path = os.path.join(debug_dir, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self.logger.info(f"[DIAGNOSTICA] HTML salvato: {path}")
        except Exception as e:
            self.logger.warning(f"[DIAGNOSTICA] Impossibile salvare HTML: {e}")

    def get_listings(self, search_url: str, listing_type: str = "vendita") -> list[dict]:
        self._warmup()
        results = []

        for page in range(1, self.max_pages + 1):
            self.logger.info(f"[Immobiliare] Pagina {page} ({listing_type})...")

            api_results = self._fetch_from_api(listing_type, page)
            if api_results is not None:
                if not api_results:
                    self.logger.info("[Immobiliare] API: pagina vuota, stop.")
                    break
                results.extend(api_results)
                self.logger.info(f"[Immobiliare] API: +{len(api_results)} (tot {len(results)})")
                if len(api_results) < 20:
                    break
                continue

            page_url = search_url if page == 1 else f"{search_url}&pag={page}"
            referer = ("https://www.immobiliare.it/" if page == 1
                       else f"{search_url}&pag={page-1}")
            self.logger.info(f"[Immobiliare] Fallback HTML: {page_url[:80]}")
            resp = self.fetch(page_url, referer=referer)
            if resp is None:
                self.logger.warning("[Immobiliare] Sia API che HTML non disponibili.")
                break

            self._save_debug_html(resp.text, listing_type, page, "_raw")

            listings, has_next = self._parse_html_page(resp.text, listing_type)
            if not listings:
                error_desc = self.looks_like_error_page(resp.text)
                if error_desc:
                    self.logger.warning(
                        f"[Immobiliare] 0 annunci: {error_desc}. "
                        f"L'URL richiesto probabilmente non è valido per "
                        f"questo sito (verifica la Città principale nella "
                        f"scheda Configurazione) — non è un problema di "
                        f"selettori CSS."
                    )
                else:
                    self.logger.warning(
                        f"[Immobiliare] 0 annunci parsati. "
                        f"Lunghezza HTML: {len(resp.text)} chars. "
                        f"Contiene __NEXT_DATA__: {'__NEXT_DATA__' in resp.text}. "
                        f"Contiene listing-card: {'listing-card' in resp.text}."
                    )
                self._save_debug_html(resp.text, listing_type, page, "_zero_results")
                break

            results.extend(listings)
            self.logger.info(f"[Immobiliare] HTML: +{len(listings)} (tot {len(results)})")
            if not has_next:
                break

        self.logger.info(f"[Immobiliare] {listing_type}: {len(results)} annunci totali")
        return results

    def _fetch_from_api(self, listing_type: str, page: int) -> list[dict] | None:
        contract_map = {"vendita": "1", "affitto": "2"}
        params = {
            "idCategoria": "1",
            "idContratto": contract_map.get(listing_type, "1"),
            "idNazione": "IT",
            "idProvincia": "NA",
            "pageNum": str(page),
            "criterio": "rilevanza",
            "noAste": "1",
        }
        headers = {
            **self.session.headers,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.immobiliare.it/",
            "Origin": "https://www.immobiliare.it",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            resp = self.session.get(API_URL, params=params,
                                    headers=headers, timeout=self.timeout)
            self.logger.info(f"[Immobiliare] API status: {resp.status_code}")
            if resp.status_code != 200:
                return None

            data = resp.json()
            raw = data if isinstance(data, list) else data.get("results")
            if raw is None:
                self.logger.info("[Immobiliare] API: nessun campo results trovato.")
                return None

            parsed = []
            for item in raw:
                try:
                    l = self.parse_listing_json(item, listing_type)
                    if l and l.get("url"):
                        parsed.append(l)
                except Exception as e:
                    self.logger.debug(f" Errore item API: {e}")
            self.logger.info(f"[Immobiliare] API: {len(parsed)} annunci parsati.")
            return parsed

        except (ValueError, Exception) as e:
            self.logger.info(f"[Immobiliare] API non disponibile: {e}")
            return None

    def _parse_html_page(self, html: str, listing_type: str) -> tuple[list[dict], bool]:
        match = NEXT_DATA_RE.search(html)
        if not match:
            self.logger.info("[Immobiliare] __NEXT_DATA__ NON trovato, uso HTML fallback.")
            return self._parse_html_fallback(html, listing_type), False
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            self.logger.warning(f"[Immobiliare] __NEXT_DATA__ JSON invalido: {e}")
            return self._parse_html_fallback(html, listing_type), False

        raw = self._extract_from_next_data(data)
        if raw is None:
            self.logger.info("[Immobiliare] __NEXT_DATA__ trovato ma nessun dato listings, uso HTML fallback.")
            return self._parse_html_fallback(html, listing_type), False

        self.logger.info(f"[Immobiliare] __NEXT_DATA__: {len(raw)} raw items trovati.")
        parsed = [self.parse_listing_json(i, listing_type) for i in raw]
        parsed = [p for p in parsed if p and p.get("url")]
        self.logger.info(f"[Immobiliare] __NEXT_DATA__: {len(parsed)} annunci validi.")
        return parsed, self._has_next_page_json(data)

    def _extract_from_next_data(self, data: dict) -> list | None:
        try:
            for q in (data.get("props", {})
                          .get("pageProps", {})
                          .get("dehydratedState", {})
                          .get("queries", [])):
                r = q.get("state", {}).get("data", {}).get("results")
                if r is not None:
                    return r
            return data.get("props", {}).get("pageProps", {}).get("listings")
        except Exception:
            return None

    def _has_next_page_json(self, data: dict) -> bool:
        try:
            for q in (data.get("props", {})
                          .get("pageProps", {})
                          .get("dehydratedState", {})
                          .get("queries", [])):
                pag = q.get("state", {}).get("data", {}).get("pagination", {})
                if pag:
                    return pag.get("currentPage", 1) < pag.get("totalPages", 1)
        except Exception:
            pass
        return False

    def parse_listing_json(self, item: dict, listing_type: str) -> dict | None:
        token = (item.get("seo", {}).get("url", "")
                 or item.get("url", "")
                 or item.get("urlDetail", ""))
        if not token:
            re_id = item.get("realEstate", {}).get("id", "") or item.get("id", "")
            token = f"/annunci/{re_id}/" if re_id else ""
        if not token:
            return None
        url = token if token.startswith("http") else f"https://www.immobiliare.it{token}"

        title = (item.get("seo", {}).get("title", "")
                 or item.get("realEstate", {}).get("title", "")
                 or item.get("title", ""))

        price = ""
        pi = item.get("realEstate", {}).get("price", {}) or item.get("price", {})
        if isinstance(pi, dict):
            val = pi.get("minValue") or pi.get("value") or pi.get("price")
            if val:
                price = f"{int(val):,} €".replace(",", ".")
        elif isinstance(pi, (int, float)):
            price = f"{int(pi):,} €".replace(",", ".")

        addr = item.get("realEstate", {}).get("location", {}) or item.get("location", {})
        location = ""
        if isinstance(addr, dict):
            def _name(v):
                return v.get("name", "") if isinstance(v, dict) else str(v or "")
            parts = [_name(addr.get("zone") or addr.get("macrozone", {})),
                     _name(addr.get("city", {}))]
            location = ", ".join(p for p in parts if p)

        lat = item.get("realEstate", {}).get("location", {}).get("latitude") or item.get("latitude")
        lon = item.get("realEstate", {}).get("location", {}).get("longitude") or item.get("longitude")

        return self.normalize(title=title, url=url, price=price,
                              location=location, listing_type=listing_type,
                              latitude=lat, longitude=lon)

    def parse_listing(self, element) -> dict | None:
        return None

    _PRICE_RE = re.compile(
        r"€\s*(\d{1,3}(?:[.\s]\d{3})+|\d{4,7})"
        r"|(\d{1,3}(?:[.\s]\d{3})+|\d{4,7})\s*(?:€|euro)", re.I)

    def _parse_html_fallback(self, html: str, listing_type: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        cards = (soup.select("li[data-type='real_estate_unit']")
                 or soup.select("[class*='listing-card']")
                 or soup.select("article.listing__item"))
        self.logger.info(f"[Immobiliare] HTML fallback: {len(cards)} card trovate con selettori.")
        results = []
        for card in cards:
            try:
                a = card.select_one("a[href*='/annunci/']") or card.select_one("a")
                if not a:
                    continue
                url = a.get("href", "")
                title = (card.select_one("[class*='title']") or a).get_text(strip=True)
                price_el = card.select_one("[class*='price']")
                price = price_el.get_text(strip=True) if price_el else ""
                loc_el = card.select_one("[class*='location'],[class*='zone']")
                loc = loc_el.get_text(strip=True) if loc_el else ""
                if url and title:
                    results.append(self.normalize(title=title, url=url, price=price,
                                                  location=loc, listing_type=listing_type))
            except Exception as e:
                self.logger.debug(f"Errore HTML card: {e}")

        if results:
            return results

        # Rete di sicurezza: se i selettori noti non trovano nulla (es. il
        # sito ha cambiato ancora il markup), tenta un'euristica basata su
        # link a "/annunci/<id>/" con un prezzo individuabile nel testo del
        # contenitore. Meno precisa, ma resiste ai cambi di classi CSS.
        self.logger.info("[Immobiliare] selettori noti a 0: provo euristica di riserva.")
        results = self._parse_html_heuristic(soup, listing_type)
        if results:
            self.logger.info(f"[Immobiliare] euristica di riserva: {len(results)} annunci.")
        return results

    def _parse_html_heuristic(self, soup: BeautifulSoup, listing_type: str) -> list[dict]:
        results, seen = [], set()
        for a in soup.select("a[href*='/annunci/']"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            title = a.get_text(strip=True)
            if len(title) < 8:
                continue
            # risale nei genitori cercando un prezzo, fermandosi se il
            # contenitore raggruppa più annunci (eviterebbe di prendere il
            # prezzo di un annuncio vicino)
            price, node = "", a
            for _ in range(5):
                if node.parent is None:
                    break
                node = node.parent
                siblings = node.select("a[href*='/annunci/']")
                if len(siblings) > 1:
                    break
                m = self._PRICE_RE.search(node.get_text(" ", strip=True))
                if m:
                    price = f"{(m.group(1) or m.group(2)).replace(' ', '')} €"
                    break
            if not price:
                continue  # senza prezzo, troppo rischio di prendere rumore
            seen.add(href)
            results.append(self.normalize(title=title, url=href, price=price,
                                          listing_type=listing_type))
            if len(results) >= 60:
                break
        return results
