"""
scrapers/base_scraper.py  —  v1.3
Classe base astratta per tutti gli scraper.

Cascata di fetch (in ordine):
  1. requests  →  veloce, nessuna dipendenza extra
  2. Selenium  →  fallback automatico se requests riceve 403/blocco Cloudflare
     Richiede: Google Chrome + pip install undetected-chromedriver
"""
import time
import random
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.logger import get_logger
from utils.robots_checker import RobotsChecker, BROWSER_USER_AGENT

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

BASE_HEADERS = {
    "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language":           "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding":           "gzip, deflate, br",
    "Connection":                "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":            "document",
    "Sec-Fetch-Mode":            "navigate",
    "Sec-Fetch-Site":            "none",
    "Sec-Fetch-User":            "?1",
    "Cache-Control":             "max-age=0",
    "DNT":                       "1",
}


class BaseScraper(ABC):

    def __init__(self, site_config: dict, scraping_config: dict):
        self.site_config     = site_config
        self.scraping_config = scraping_config
        self.name            = site_config.get("name", "Unknown")
        self.base_url        = site_config.get("base_url", "")
        self.logger          = get_logger(f"scraper.{site_config.get('id', 'unknown')}")

        self.delay     = scraping_config.get("request_delay_seconds", 2.5)
        self.timeout   = scraping_config.get("request_timeout", 30)
        self.max_pages = scraping_config.get("max_pages_per_site", 5)

        # robots.txt — override per-sito ha priorità
        per_site = site_config.get("respect_robots_txt", None)
        global_r  = scraping_config.get("respect_robots_txt", True)
        self.robots = RobotsChecker(respect_robots=(per_site if per_site is not None else global_r))

        # Selenium — abilitato per-sito o globalmente
        self.use_selenium   = site_config.get("use_selenium", False)
        self.selenium_headless = scraping_config.get("selenium_headless", True)

        self.session = self._build_session(
            max_retries=scraping_config.get("max_retries", 3),
            retry_delay=scraping_config.get("retry_delay", 5),
        )

    # ── Session setup ─────────────────────────────────────────────────────────

    def _build_session(self, max_retries=3, retry_delay=5) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://",  adapter)
        session.headers.update({**BASE_HEADERS, "User-Agent": random.choice(USER_AGENTS)})
        return session

    # ── Fetch con fallback Selenium ───────────────────────────────────────────

    def fetch(self, url: str, params: dict = None,
              referer: str = None) -> requests.Response | None:
        """
        Tenta requests. Se ottiene 403, tenta automaticamente Selenium.
        Restituisce None solo se ENTRAMBI falliscono.
        """
        if not self.robots.is_allowed(url):
            return None

        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
        if referer:
            self.session.headers["Referer"] = referer
        elif "Referer" in self.session.headers:
            del self.session.headers["Referer"]

        try:
            self.logger.debug(f"requests GET {url[:80]}")
            resp = self.session.get(url, params=params, timeout=self.timeout)

            if resp.status_code == 200:
                return resp
            elif resp.status_code == 403:
                self.logger.warning(
                    f"HTTP 403 su {url[:60]} — Cloudflare/bot protection rilevato. "
                    f"Attivo Selenium fallback..."
                )
                # ── Fallback automatico a Selenium ──
                return self._selenium_response(url)
            elif resp.status_code == 429:
                self.logger.warning(f"Rate limit (429) — attendo 60s")
                time.sleep(60)
                return self.fetch(url, params, referer)
            else:
                self.logger.warning(f"HTTP {resp.status_code}: {url[:60]}")
                return None

        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout su {url[:60]}")
            return None
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Errore connessione: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Errore inatteso: {e}", exc_info=True)
            return None
        finally:
            time.sleep(self.delay * random.uniform(0.5, 1.5))

    def _selenium_response(self, url: str) -> requests.Response | None:
        """
        Carica la pagina con Selenium e la impacchetta in un oggetto
        Response-like compatibile con il resto del codice.
        """
        from scrapers.selenium_helper import fetch_page, is_available
        if not is_available():
            self.logger.warning(
                "Selenium non disponibile. Installa Chrome + "
                "pip install undetected-chromedriver selenium"
            )
            return None

        self.logger.info(f"Selenium fetching: {url[:80]}")
        html = fetch_page(url, wait_seconds=4.0,
                          headless=self.selenium_headless, scroll=True)
        if not html:
            return None

        # Crea un oggetto Response simulato con .text e .status_code
        fake = _FakeResponse(html, url)
        return fake

    # ── Fetch Selenium diretto (per scraper che lo usano nativamente) ─────────

    def fetch_js(self, url: str, wait: float = 4.0, scroll: bool = True,
                 wait_for_selector: str | None = None) -> str | None:
        """
        Scarica direttamente con Selenium (senza provare requests prima).
        Utile per scraper che sanno già che il sito richiede JS.
        """
        from scrapers.selenium_helper import fetch_page, is_available
        if not is_available():
            self.logger.error("Selenium non disponibile per fetch_js()")
            return None
        return fetch_page(url, wait_seconds=wait,
                          headless=self.selenium_headless, scroll=scroll,
                          wait_for_selector=wait_for_selector)

    # ── Metodi astratti ───────────────────────────────────────────────────────

    @abstractmethod
    def get_listings(self, search_url: str, listing_type: str = "vendita") -> list[dict]:
        ...

    @abstractmethod
    def parse_listing(self, element: Any) -> dict | None:
        ...

    # ── Normalizzazione ───────────────────────────────────────────────────────

    def normalize(self, title=None, url=None, price=None, location=None,
                  date=None, listing_type="", **extra) -> dict:
        if url and url.startswith("/"):
            url = self.base_url.rstrip("/") + url
        return {
            "title":        self._clean(title),
            "url":          self._clean(url),
            "price":        self._clean(price),
            "location":     self._clean(location),
            "date":         self._clean(date) or datetime.now().strftime("%Y-%m-%d"),
            "listing_type": listing_type,
            "source":       self.name,
            **extra,
        }

    @staticmethod
    def _clean(value) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value).strip())

    @staticmethod
    def looks_like_error_page(html: str) -> str:
        """
        Rileva pagine servite con HTTP 200 ma che sono in realtà errori o
        redirect silenziosi (soft-404): con status_code=200 il codice non
        se ne accorgerebbe da solo, e un parser che trova 0 annunci in una
        pagina così farebbe pensare a selettori CSS da aggiornare, quando
        la vera causa è un URL non valido (es. una zona non riconosciuta
        dal sito). Ritorna una stringa che descrive il problema, o "" se
        la pagina sembra legittima.
        """
        if not html or len(html) < 500:
            return "pagina vuota o troppo corta per essere una lista risultati"
        low = html[:20000].lower()
        markers = [
            ('data-cy="error-404"', "pagina 404 del sito (URL/zona non valida)"),
            ('data-cy="error-page"', "pagina di errore del sito"),
            ("pagina non trovata", "pagina 404 (testo esplicito)"),
            ("page not found", "pagina 404 (testo esplicito)"),
            ("non è stato possibile trovare", "pagina di errore del sito"),
        ]
        for marker, desc in markers:
            if marker in low:
                return desc
        return ""

    # ── Diagnostica ──────────────────────────────────────────────────────────

    def diagnose(self, url: str) -> dict:
        """
        Esegue una richiesta HTTP diagnostica sull'URL dato.
        Usato da: python main.py --diagnose
        Restituisce un dict con status_code, size, content_type, ecc.
        """
        result = {
            "url":           url,
            "status_code":   None,
            "size_bytes":    0,
            "content_type":  "",
            "has_next_data": False,
            "title":         "",
            "body_preview":  "",
            "error":         None,
        }
        try:
            resp = self.session.get(url, timeout=self.timeout)
            result["status_code"] = resp.status_code
            result["size_bytes"]  = len(resp.content)
            result["content_type"] = resp.headers.get("Content-Type", "")

            if resp.status_code == 200:
                text = resp.text
                result["has_next_data"] = "__NEXT_DATA__" in text
                result["body_preview"]  = text[:1000]
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(text, "lxml")
                    t = soup.find("title")
                    result["title"] = t.get_text(strip=True) if t else ""
                except Exception:
                    pass

        except Exception as e:
            result["error"] = str(e)

        return result

    # ── Scrape completo ───────────────────────────────────────────────────────

    def scrape(self) -> list[dict]:
        results = []
        for lt in self.site_config.get("listing_types", ["vendita"]):
            url = self.site_config.get("search_urls", {}).get(lt)
            if not url:
                continue
            self.logger.info(f"[{self.name}] Scraping {lt}: {url}")
            try:
                listings = self.get_listings(url, listing_type=lt)
                self.logger.info(f"[{self.name}] {lt}: {len(listings)} annunci trovati")
                results.extend(listings)
            except Exception as e:
                self.logger.error(f"[{self.name}] Errore: {e}", exc_info=True)
        return results


# ── Oggetto Response simulato ─────────────────────────────────────────────────

class _FakeResponse:
    """
    Simula requests.Response con .text, .status_code e .content
    per compatibilità con il codice che usa fetch().
    """
    def __init__(self, html: str, url: str):
        self.text        = html
        self.url         = url
        self.status_code = 200
        self.content     = html.encode("utf-8", errors="replace")

    def json(self):
        import json
        return json.loads(self.text)
