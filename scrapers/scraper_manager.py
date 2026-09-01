"""
scrapers/scraper_manager.py
Factory e orchestratore: carica il parser giusto per ogni sito
e gestisce i filtri di prezzo/tipo post-scraping.
"""
import re
from .base_scraper import BaseScraper
from .immobiliare_scraper import ImmobiliareScraper
from .subito_scraper import SubitoScraper
from .idealista_scraper import IdealistaScraper
from .generic_scraper import GenericScraper
from utils.logger import get_logger

logger = get_logger("scraper_manager")

# Mappa id scraper → classe
SCRAPER_MAP: dict[str, type] = {
    "immobiliare": ImmobiliareScraper,
    "subito":      SubitoScraper,
    "idealista":   IdealistaScraper,
    "generic":     GenericScraper,
}


class ScraperManager:
    """
    Gestisce la selezione e l'esecuzione dello scraper corretto per ogni sito.
    Applica anche i filtri post-scraping (prezzo, keyword, tipo).
    """

    def __init__(self, config: dict):
        self.scraping_config = config.get("scraping", {})
        self.filters_config  = config.get("filters", {})

    def scrape_site(self, site_config: dict) -> list[dict]:
        """
        Seleziona lo scraper giusto, esegue lo scraping e applica i filtri.
        Restituisce la lista filtrata di annunci normalizzati.
        """
        scraper_id = site_config.get("scraper", "generic")
        scraper_cls = SCRAPER_MAP.get(scraper_id, GenericScraper)

        logger.info(f"Usando scraper: {scraper_cls.__name__} per {site_config['name']}")

        try:
            scraper: BaseScraper = scraper_cls(site_config, self.scraping_config)
            listings = scraper.scrape()
        except Exception as e:
            logger.error(f"Errore critico nello scraper {scraper_id}: {e}", exc_info=True)
            return []

        # Applica filtri post-scraping
        filtered = self._apply_filters(listings)
        logger.info(f"[{site_config['name']}] {len(listings)} trovati → {len(filtered)} dopo filtri")
        return filtered

    # ------------------------------------------------------------------
    # Filtri
    # ------------------------------------------------------------------

    def _apply_filters(self, listings: list[dict]) -> list[dict]:
        """Applica tutti i filtri configurati agli annunci."""
        result = []
        for listing in listings:
            if self._passes_filters(listing):
                result.append(listing)
        return result

    def _passes_filters(self, listing: dict) -> bool:
        cfg = self.filters_config

        # Filtro tipo annuncio
        allowed_types = cfg.get("listing_types", [])
        if allowed_types and listing.get("listing_type") not in allowed_types:
            return False

        # Filtro prezzo
        min_price = cfg.get("min_price", 0)
        max_price = cfg.get("max_price", 9_999_999)
        price_val = self._parse_price(listing.get("price", ""))
        if price_val is not None:
            if price_val < min_price or price_val > max_price:
                return False

        # Parole da escludere
        exclude_kw = [k.lower() for k in cfg.get("keywords_exclude", [])]
        haystack = f"{listing.get('title','')}{listing.get('location','')}".lower()
        for kw in exclude_kw:
            if kw in haystack:
                return False

        # Parole da includere (almeno una deve esserci)
        include_kw = [k.lower() for k in cfg.get("keywords_include", [])]
        if include_kw:
            if not any(kw in haystack for kw in include_kw):
                return False

        return True

    @staticmethod
    def _parse_price(price_str: str) -> float | None:
        """Estrae il valore numerico da una stringa prezzo."""
        if not price_str:
            return None
        # Rimuove tutto tranne cifre e separatori
        cleaned = re.sub(r"[^\d.,]", "", price_str)
        # Gestisce formato europeo (1.000.000 o 1.000.000,00)
        cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
