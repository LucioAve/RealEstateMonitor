"""
scrapers/selenium_helper.py
Helper Selenium con undetected-chromedriver per bypassare Cloudflare / JS challenge.
"""
import re
import sys
import time
import atexit
import random
import subprocess
import threading
from utils.logger import get_logger

logger = get_logger("selenium")

_instance_lock = threading.Lock()
_driver = None
_available = None


def _get_chrome_major_version() -> int | None:
    cmds = []
    if sys.platform == "win32":
        cmds = [
            ["reg", "query", r"HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon", "/v", "version"],
            ["reg", "query", r"HKEY_LOCAL_MACHINE\SOFTWARE\Google\Chrome\BLBeacon", "/v", "version"],
            ["reg", "query", r"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon", "/v", "version"],
        ]
    elif sys.platform == "darwin":
        cmds = [["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"]]
    else:
        cmds = [
            ["google-chrome", "--version"],
            ["google-chrome-stable", "--version"],
            ["chromium-browser", "--version"],
            ["chromium", "--version"],
        ]
    for cmd in cmds:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=5).decode(errors="ignore")
            m = re.search(r"(\d+)\.\d+\.\d+", out)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None


def is_available() -> bool:
    global _available
    if _available is not None:
        return _available
    try:
        import undetected_chromedriver as uc
        _available = True
    except ImportError:
        _available = False
    return _available


def get_driver(headless: bool = True):
    global _driver
    if not is_available():
        return None
    with _instance_lock:
        if _driver is not None:
            try:
                _ = _driver.current_url
                return _driver
            except Exception:
                _driver = None
        _driver = _create_driver(headless=headless)
        return _driver


def _create_driver(headless: bool = True):
    try:
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--lang=it-IT,it")
        options.add_argument("--window-size=1366,768")
        options.add_argument("--disable-gpu")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        chrome_version = _get_chrome_major_version()
        kwargs = {"options": options, "use_subprocess": True}
        if chrome_version is not None:
            kwargs["version_main"] = chrome_version
            logger.info(f"ChromeDriver selezionato per Chrome {chrome_version}")
        driver = uc.Chrome(**kwargs)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)
        logger.info("Browser Chrome (undetected) avviato.")
        atexit.register(shutdown)
        return driver
    except Exception as e:
        logger.error(f"Impossibile avviare Chrome: {e}")
        return None


_CHALLENGE_MARKERS = (
    "just a moment", "challenge-platform", "cf-challenge",
    "captcha-delivery", "datadome", "geo.captcha-delivery.com",
    "verifica di non essere un robot", "verify you are human",
    "attention required", "access denied",
)


def _looks_challenge(html: str) -> bool:
    if not html or len(html) < 1000:
        return True
    low = html[:8000].lower()
    return any(m in low for m in _CHALLENGE_MARKERS)


def fetch_page(url: str,
               wait_seconds: float = 3.0,
               headless: bool = True,
               scroll: bool = False,
               wait_for_selector: str | None = None) -> str | None:
    driver = get_driver(headless=headless)
    if driver is None:
        return None
    try:
        html = _load_and_wait(driver, url, wait_seconds, scroll, wait_for_selector)
        for _ in range(3):
            if not _looks_challenge(html):
                return html
            time.sleep(4)
            html = driver.page_source
            if not _looks_challenge(html):
                return html
        if headless:
            logger.warning(
                f"Verifica anti-bot su {url[:70]} — apro Chrome VISIBILE: "
                f"completa l'eventuale controllo a mano (attendo ~90s). "
                f"Il superamento resta valido per le richieste successive."
            )
            vdriver = _get_visible_driver()
            if vdriver is not None:
                html = _load_and_wait(vdriver, url, wait_seconds, scroll, wait_for_selector)
                waited = 0
                while _looks_challenge(html) and waited < 90:
                    time.sleep(3)
                    waited += 3
                    html = vdriver.page_source
                if not _looks_challenge(html):
                    logger.info("Verifica superata: proseguo.")
                    return html
        logger.warning(f"Challenge anti-bot non superato su {url[:80]}.")
        return None
    except Exception as e:
        logger.error(f"Errore Selenium su {url}: {e}")
        return None


def _load_and_wait(driver, url: str, wait_seconds: float, scroll: bool, wait_for_selector: str | None = None) -> str:
    logger.debug(f"Selenium GET: {url}")
    driver.get(url)

    # Alcuni siti (es. Grimaldi, Gabetti) servono una pagina-ponte che
    # calcola un fingerprint JS e poi reindirizza con window.location: la
    # pagina iniziale è pochi byte e non contiene mai risultati. Attendiamo
    # che l'URL cambi e il contenuto cresca, entro un tetto di tempo, prima
    # di procedere con l'attesa normale del selettore/pausa fissa.
    try:
        start_url = driver.current_url
        for _ in range(8):
            time.sleep(1)
            if driver.current_url != start_url and len(driver.page_source or "") > 3000:
                logger.debug(f"Redirect JS rilevato: {start_url[:60]} → {driver.current_url[:60]}")
                time.sleep(1.5)
                break
    except Exception:
        pass

    if wait_for_selector:
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.by import By
            WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
            )
            logger.info(f"Elemento '{wait_for_selector}' trovato nel DOM.")
            time.sleep(1.5 + random.uniform(0.5, 1.0))
        except Exception as e:
            logger.warning(
                f"Attesa elemento '{wait_for_selector}' fallita ({e}): "
                f"procedo con page_source attuale."
            )
            time.sleep(2.0)
    else:
        time.sleep(wait_seconds + random.uniform(0.5, 1.5))
    if scroll:
        _scroll_page(driver)
    return driver.page_source


_visible_driver = None


def _get_visible_driver():
    global _visible_driver
    if not is_available():
        return None
    with _instance_lock:
        if _visible_driver is not None:
            try:
                _ = _visible_driver.current_url
                return _visible_driver
            except Exception:
                _visible_driver = None
        _visible_driver = _create_driver(headless=False)
        return _visible_driver


def _scroll_page(driver, steps: int = 3):
    try:
        total_height = driver.execute_script("return document.body.scrollHeight")
        step = total_height // steps
        for i in range(1, steps + 1):
            driver.execute_script(f"window.scrollTo(0, {step * i});")
            time.sleep(0.8)
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass


def shutdown():
    global _driver, _visible_driver
    for name in ("_driver", "_visible_driver"):
        drv = globals().get(name)
        if drv is not None:
            try:
                drv.quit()
            except Exception:
                pass
            globals()[name] = None
    logger.debug("Browser Selenium chiusi.")
