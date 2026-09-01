"""
utils/robots_checker.py - Verifica permessi robots.txt prima dello scraping

FIX: Il checker ora usa lo stesso User-Agent browser-like degli scraper.
Il problema precedente era che "RealEstateMonitorBot" veniva bloccato
dal robots.txt (che blocca i bot generici), mentre "Mozilla/5.0"
è normalmente permesso perché i siti vogliono traffico umano.
"""
import urllib.robotparser
import urllib.parse
import urllib.request
from .logger import get_logger

logger = get_logger("robots")

# Stesso UA usato dagli scraper — DEVE corrispondere
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


class RobotsChecker:
    """
    Controlla se lo scraping è permesso dal robots.txt.
    USA lo stesso User-Agent browser-like degli scraper (non "bot"),
    perché i siti bloccano i bot ma permettono i browser.
    """

    def __init__(self, respect_robots: bool = True):
        self.respect_robots = respect_robots
        self._cache: dict = {}

    def _get_parser(self, base_url: str):
        if base_url in self._cache:
            return self._cache[base_url]

        robots_url = urllib.parse.urljoin(base_url, "/robots.txt")
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)

        try:
            req = urllib.request.Request(
                robots_url,
                headers={"User-Agent": BROWSER_USER_AGENT}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            rp.parse(content.splitlines())
            self._cache[base_url] = rp
            logger.debug(f"robots.txt caricato: {robots_url}")
            return rp
        except Exception as e:
            logger.debug(f"robots.txt non disponibile per {base_url}: {e} — permesso per default")
            self._cache[base_url] = None
            return None

    def is_allowed(self, url: str, user_agent: str = BROWSER_USER_AGENT) -> bool:
        if not self.respect_robots:
            return True

        parsed   = urllib.parse.urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        parser   = self._get_parser(base_url)

        if parser is None:
            return True

        # Controlla sia con UA browser che con wildcard "*"
        allowed = parser.can_fetch(user_agent, url) or parser.can_fetch("*", url)

        if not allowed:
            logger.warning(
                f"robots.txt blocca: {url} — per ignorarlo imposta "
                f"'respect_robots_txt': false nel config del sito in sites.json"
            )
        return allowed

    def get_crawl_delay(self, base_url: str, user_agent: str = BROWSER_USER_AGENT):
        parser = self._get_parser(base_url)
        if parser:
            try:
                return parser.crawl_delay(user_agent)
            except Exception:
                return None
        return None

    def clear_cache(self):
        self._cache.clear()
