"""
main.py — Entry point principale di Real Estate Monitor

Modalità:
  python main.py --gui          → GUI completa
  python main.py --run-now      → Scraping immediato (console)
  python main.py --schedule     → Scheduler giornaliero headless
  python main.py --diagnose     → Diagnostica siti (debug connettività)
  python main.py --help         → Aiuto
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

if sys.version_info < (3, 10):
    print("❌ Python 3.10+ richiesto. Rilevato:", sys.version)
    sys.exit(1)


# ─── Controllo e installazione automatica dipendenze ─────────────────────────

def check_and_install_requirements(req_file: str = "requirements.txt") -> None:
    """
    Legge requirements.txt, verifica quali pacchetti mancano
    e li installa automaticamente tramite pip.
    Viene eseguito prima di qualsiasi altro import.
    """
    import importlib.util
    import subprocess
    import re

    req_path = Path(req_file)
    if not req_path.exists():
        return  # nessun requirements.txt, prosegui

    # Mappa nome-pacchetto → nome-modulo (quando differiscono)
    IMPORT_MAP = {
        "beautifulsoup4":        "bs4",
        "Pillow":                "PIL",
        "python-dotenv":         "dotenv",
        "fake-useragent":        "fake_useragent",
        "undetected-chromedriver": "undetected_chromedriver",
        "scikit-learn":          "sklearn",
        "opencv-python":         "cv2",
    }

    missing = []
    with open(req_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Estrae il nome del pacchetto (es. "requests>=2.31.0" → "requests")
            pkg_name = re.split(r"[>=<!;\[]", line)[0].strip()
            if not pkg_name:
                continue
            module_name = IMPORT_MAP.get(pkg_name, pkg_name.replace("-", "_"))
            if importlib.util.find_spec(module_name) is None:
                missing.append(line)  # passa la riga intera per rispettare versioni minime

    if not missing:
        return

    print("=" * 60)
    print("  📦  Dipendenze mancanti — installazione automatica")
    print("=" * 60)
    for pkg in missing:
        print(f"  • {pkg}")
    print()

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        print("\n  ✅  Tutte le dipendenze installate correttamente.\n")
    except subprocess.CalledProcessError as e:
        print(f"\n  ❌  Installazione fallita (codice {e.returncode}).")
        print("  Esegui manualmente:  python -m pip install -r requirements.txt\n")
        sys.exit(1)


check_and_install_requirements()


def load_config(path: str = "config/settings.json") -> dict:
    # settings.json viene creato/completato automaticamente dai default:
    # nessuna configurazione da terminale, tutto poi si gestisce dalla GUI.
    from config.defaults import ensure_settings
    return ensure_settings(Path(path))


def load_sites(path: str = "config/sites.json") -> list:
    p = Path(path)
    if not p.exists():
        print(f"❌ Sites non trovato: {path}")
        sys.exit(1)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ─── Job scraping ─────────────────────────────────────────────────────────────

def run_scraping_job(config: dict, logger, return_results: bool = False) -> list[dict]:
    from scrapers.scraper_manager import ScraperManager
    from database.db_manager import DatabaseManager
    from utils.geo_filter import build_geo_filter
    from utils.notifier import Notifier

    logger.info("=" * 60)
    logger.info(f"  AVVIO — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    logger.info("=" * 60)

    db             = DatabaseManager(config.get("database", {}).get("path", "database/listings.db"))
    geo_filter     = build_geo_filter(config)
    scraper_manager= ScraperManager(config)
    notifier       = Notifier(config.get("notifications", {}))
    sites          = load_sites()
    run_id         = db.log_run_start()

    all_new, total_found, errors = [], 0, 0
    enabled = [s for s in sites if s.get("enabled", True)]
    logger.info(f"Siti abilitati: {len(enabled)}")

    for site in enabled:
        logger.info(f"\n▶  {site['name']}")
        try:
            listings = scraper_manager.scrape_site(site)
            total_found += len(listings)
            logger.info(f"   Trovati:     {len(listings)}")
            filtered = geo_filter.filter(listings)
            logger.info(f"   Dopo filtro: {len(filtered)}")
            new_here = 0
            for listing in filtered:
                if not db.is_seen(listing["url"]):
                    db.mark_seen(listing)
                    all_new.append(listing)
                    new_here += 1
            logger.info(f"   Nuovi:       {new_here}")
        except Exception as e:
            errors += 1
            logger.error(f"   ❌ Errore: {e}", exc_info=True)

    logger.info(f"\n{'─'*60}")
    logger.info(f"  Totale trovati: {total_found} | Nuovi: {len(all_new)} | Errori: {errors}")
    logger.info(f"{'─'*60}\n")

    if all_new:
        _print_new_listings(all_new)
        _save_results(all_new, config)
        if config.get("notifications", {}).get("enabled"):
            notifier.send(all_new)
    else:
        logger.info("Nessun nuovo annuncio trovato.")

    db.log_run_end(run_id, total_found, len(all_new), errors)
    return all_new


def _print_new_listings(listings: list[dict]) -> None:
    print(f"\n{'━'*70}")
    print(f"  🏠  {len(listings)} NUOVI ANNUNCI")
    print(f"{'━'*70}\n")
    for i, l in enumerate(listings, 1):
        print(f"  {i:>3}. {l.get('title','N/D')[:60]}")
        print(f"       💶 {l.get('price','N/D'):<20}  📍 {l.get('location','N/D')}")
        print(f"       🔗 {l.get('url','')[:80]}")
        print(f"       🏷  {l.get('listing_type','')} — {l.get('source','')}\n")
    print(f"{'━'*70}\n")


def _save_results(listings: list[dict], config: dict) -> None:
    out_cfg = config.get("output", {})
    out_dir = Path(out_cfg.get("directory", "output"))
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if out_cfg.get("save_json", True):
        path = out_dir / f"new_listings_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(listings, f, ensure_ascii=False, indent=2, default=str)
        print(f"  💾 Salvato: {path}")

    if out_cfg.get("save_csv", False):
        import csv
        path = out_dir / f"new_listings_{ts}.csv"
        fields = ["title", "url", "price", "location", "date", "listing_type", "source"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(listings)
        print(f"  💾 CSV: {path}")


# ─── Diagnostica ──────────────────────────────────────────────────────────────

def run_diagnose(config: dict, logger) -> None:
    """
    Testa la connettività e il parsing di ogni sito abilitato.
    Produce un report dettagliato per identificare i problemi.
    Uso: python main.py --diagnose
    """
    from scrapers.scraper_manager import SCRAPER_MAP
    from scrapers.generic_scraper import GenericScraper
    from utils.robots_checker import RobotsChecker

    sites = load_sites()
    enabled = [s for s in sites if s.get("enabled", True)]

    W = "\033[97m"; G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; B = "\033[94m"; D = "\033[0m"; BOLD = "\033[1m"

    print(f"\n{B}{BOLD}{'═'*65}")
    print(f"  🔍  DIAGNOSTICA SITI — Real Estate Monitor")
    print(f"{'═'*65}{D}\n")

    report_lines = [f"=== DIAGNOSTICA {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ===\n"]

    for site in enabled:
        name = site["name"]
        print(f"{W}{BOLD}▶ {name}{D}")
        report_lines.append(f"\n--- {name} ---")

        scraper_id  = site.get("scraper", "generic")
        scraper_cls = SCRAPER_MAP.get(scraper_id, GenericScraper)
        scraper     = scraper_cls(site, config.get("scraping", {}))

        search_urls = site.get("search_urls", {})
        lt          = list(search_urls.keys())[0] if search_urls else "vendita"
        test_url    = search_urls.get(lt, site.get("base_url", ""))

        print(f"  URL test: {test_url}")
        report_lines.append(f"URL test: {test_url}")

        # 1. Controllo robots.txt
        robots_global = config.get("scraping", {}).get("respect_robots_txt", True)
        per_site      = site.get("respect_robots_txt", None)
        respect       = per_site if per_site is not None else robots_global
        checker       = RobotsChecker(respect_robots=True)  # sempre True per la diagnosi
        robots_ok     = checker.is_allowed(test_url)

        robots_status = f"{G}✓ Permesso{D}" if robots_ok else f"{Y}⚠ Bloccato da robots.txt{D}"
        respect_str   = f"{'RISPETTATO' if respect else 'IGNORATO (respect_robots_txt=false)'}"
        print(f"  robots.txt: {robots_status} — config: {respect_str}")
        report_lines.append(f"robots.txt permesso: {robots_ok} | config: {respect_str}")

        # 2. Diagnosi HTTP
        diag = scraper.diagnose(test_url)
        sc   = diag.get("status_code")
        err  = diag.get("error")

        if err and sc is None:
            print(f"  {R}✗ Connessione fallita: {err}{D}")
            report_lines.append(f"Errore connessione: {err}")
        elif sc == 200:
            print(f"  {G}✓ HTTP 200 OK{D} — {diag.get('size_bytes',0):,} byte")
            print(f"  Content-Type: {diag.get('content_type','?')}")
            has_nd = diag.get("has_next_data", False)
            print(f"  __NEXT_DATA__: {'✓ presente' if has_nd else '✗ assente'}")
            print(f"  Titolo pagina: {diag.get('title','N/D')}")
            report_lines += [
                f"HTTP: 200 OK | Size: {diag.get('size_bytes')} byte",
                f"Content-Type: {diag.get('content_type')}",
                f"__NEXT_DATA__: {has_nd}",
                f"Titolo: {diag.get('title')}",
            ]

            # 3. Tenta parsing reale (prime 3 pagine)
            print(f"  Tentativo parsing...")
            try:
                listings = scraper.get_listings(test_url, listing_type=lt)
                n = len(listings)
                if n > 0:
                    print(f"  {G}✓ Parsing OK: {n} annunci trovati{D}")
                    report_lines.append(f"Parsing: OK — {n} annunci")
                    # Mostra i primi 3
                    for l in listings[:3]:
                        print(f"    • {l.get('title','?')[:55]} | {l.get('price','?')} | {l.get('location','?')}")
                        report_lines.append(f"  Esempio: {l.get('title','?')} | {l.get('price','?')} | {l.get('url','?')}")
                else:
                    print(f"  {Y}⚠ HTTP OK ma 0 annunci estratti{D}")
                    print(f"     → Possibile: selettori CSS/JSON obsoleti")
                    print(f"     → Anteprima HTML (prime 500 chars):")
                    preview = (diag.get("body_preview","") or "")[:500]
                    print(f"     {preview[:300]}")
                    report_lines.append(f"Parsing: 0 annunci — selettori probabilmente obsoleti")
                    report_lines.append(f"HTML preview: {preview[:500]}")
            except Exception as e:
                print(f"  {R}✗ Errore parsing: {e}{D}")
                report_lines.append(f"Errore parsing: {e}")

        elif sc == 403:
            print(f"  {R}✗ HTTP 403 Forbidden{D}")
            print(f"     → Il sito sta bloccando la richiesta (Cloudflare / anti-bot)")
            print(f"     → Suggerimenti:")
            print(f"        1) Aumenta request_delay_seconds in settings.json")
            print(f"        2) Imposta un Referer nel config del sito")
            print(f"        3) Prova con Selenium (JS challenge)")
            report_lines += [f"HTTP: 403 Forbidden", "Probabile blocco anti-bot"]

        elif sc == 404:
            print(f"  {Y}⚠ HTTP 404 — URL non trovato{D}")
            print(f"     → Aggiorna search_urls in sites.json")
            report_lines.append(f"HTTP: 404 — URL obsoleto")

        elif sc is None:
            print(f"  {R}✗ Nessuna risposta{D}")
            report_lines.append("Nessuna risposta HTTP")
        else:
            print(f"  {Y}⚠ HTTP {sc}{D}")
            report_lines.append(f"HTTP: {sc}")

        print()

    # Salva report
    out_dir = Path("logs"); out_dir.mkdir(exist_ok=True)
    rpt_path = out_dir / f"diagnose_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(rpt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n{G}Report salvato: {rpt_path}{D}")
    print(f"\n{'─'*65}")
    print(f"Suggerimento: esegui con --log-level DEBUG per dettagli HTTP completi")
    print(f"  python main.py --diagnose --log-level DEBUG")


# ─── Scheduler ────────────────────────────────────────────────────────────────

def run_with_schedule(config: dict, logger) -> None:
    import schedule, time
    sched_cfg  = config.get("schedule", {})
    sched_time = sched_cfg.get("time", "08:00")
    logger.info(f"📅 Scheduler attivo — esecuzione alle {sched_time} ogni giorno")
    logger.info("   Premi CTRL+C per terminare.\n")
    schedule.every().day.at(sched_time).do(run_scraping_job, config=config, logger=logger)
    if sched_cfg.get("run_on_start", True):
        run_scraping_job(config, logger)
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("\n⏹  Scheduler fermato.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="real_estate_monitor",
        description="🏠 Real Estate Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python main.py --gui                  # GUI completa
  python main.py --run-now              # Scraping immediato
  python main.py --diagnose             # Diagnosi connettività siti
  python main.py --diagnose --log-level DEBUG  # Diagnosi con dettagli HTTP
  python main.py --schedule             # Scheduler giornaliero
        """
    )
    parser.add_argument("--gui",       action="store_true", help="Avvia GUI")
    parser.add_argument("--run-now",   action="store_true", help="Scraping immediato")
    parser.add_argument("--schedule",  action="store_true", help="Scheduler giornaliero")
    parser.add_argument("--diagnose",  action="store_true", help="Diagnostica siti (debug)")
    parser.add_argument("--config",    default="config/settings.json")
    parser.add_argument("--sites",     default="config/sites.json")
    parser.add_argument("--log-level", default=None,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()
    config = load_config(args.config)

    if args.log_level:
        config.setdefault("logging", {})["level"] = args.log_level

    from utils.logger import setup_logger
    logger = setup_logger("real_estate_monitor", config.get("logging", {}))
    logger.info(f"Real Estate Monitor v{config.get('version','1.0.0')} | Python {sys.version.split()[0]}")

    for d in ["output", "logs", "database"]:
        Path(d).mkdir(exist_ok=True)

    if args.diagnose:
        run_diagnose(config, logger)
    elif args.run_now:
        run_scraping_job(config, logger)
    elif args.schedule:
        run_with_schedule(config, logger)
    else:
        try:
            from gui.app_gui import launch_gui
            launch_gui(config, logger)
        except ImportError as e:
            logger.error(f"GUI non disponibile: {e}")
            logger.info("Usa --run-now per modalità console.")
            sys.exit(1)


if __name__ == "__main__":
    main()
