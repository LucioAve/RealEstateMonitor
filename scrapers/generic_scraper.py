"""
scrapers/generic_scraper.py
Scraper generico configurabile via sites.json per siti non supportati nativamente.
I selettori CSS vengono letti dal file di configurazione del sito.
"""
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper
from utils.logger import get_logger

logger = get_logger("scraper.generic")


class GenericScraper(BaseScraper):
    """
    Scraper configurabile via CSS selectors definiti in sites.json.
    Perfetto per aggiungere nuovi siti senza scrivere codice.

    Campi richiesti nel config del sito:
      listing_selector: str  — selettore per ogni card annuncio
      title_selector:   str  — selettore per il titolo
      price_selector:   str  — selettore per il prezzo
      location_selector:str  — selettore per la località
      link_selector:    str  — selettore per il link (con href)
      date_selector:    str  — (opzionale) selettore per la data
    """

    def get_listings(self, search_url: str, listing_type: str = "vendita") -> list[dict]:
        results = []

        for page in range(1, self.max_pages + 1):
            # Paginazione generica: aggiunge ?page=N o &page=N
            sep = "&" if "?" in search_url else "?"
            page_url = search_url if page == 1 else f"{search_url}{sep}page={page}"
            response = self.fetch(page_url)

            if response is None:
                break

            soup = BeautifulSoup(response.text, "lxml")
            listings = self._parse_page(soup, listing_type)

            if not listings:
                break

            results.extend(listings)
            logger.debug(f"[generic:{self.name}] Pagina {page}: +{len(listings)}")

            # Controlla paginazione generica
            if not self._has_next(soup):
                break

        return results

    def _parse_page(self, soup: BeautifulSoup, listing_type: str) -> list[dict]:
        sel = self.site_config.get("listing_selector", "article")
        cards = soup.select(sel)

        if not cards:
            logger.debug(f"[{self.name}] Nessuna card trovata con selettore: {sel}")
            return []

        results = []
        for card in cards:
            listing = self.parse_listing(card)
            if listing:
                listing["listing_type"] = listing_type
                results.append(listing)

        return results

    def parse_listing(self, element) -> dict | None:
        cfg = self.site_config

        def extract(selector: str) -> str:
            if not selector:
                return ""
            el = element.select_one(selector)
            return el.get_text(strip=True) if el else ""

        def extract_href(selector: str) -> str:
            if not selector:
                return ""
            el = element.select_one(selector)
            if el:
                href = el.get("href", "")
                if href and not href.startswith("http"):
                    href = self.base_url.rstrip("/") + "/" + href.lstrip("/")
                return href
            return ""

        title    = extract(cfg.get("title_selector", ""))
        price    = extract(cfg.get("price_selector", ""))
        location = extract(cfg.get("location_selector", ""))
        date     = extract(cfg.get("date_selector", ""))
        url      = extract_href(cfg.get("link_selector", "a"))

        # Se il selettore del link è uguale al selettore del titolo, prendi href dal titolo
        if not url:
            a = element.select_one("a")
            if a:
                url = a.get("href", "")

        if not url or not title:
            return None

        return self.normalize(title=title, url=url, price=price,
                              location=location, date=date)

    def _has_next(self, soup: BeautifulSoup) -> bool:
        """Cerca link paginazione generici."""
        for sel in ["a[rel='next']", ".pagination .next a", "a.next", "[class*='next-page']"]:
            if soup.select_one(sel):
                return True
        return False
