"""
setup.py — Setup automatico e launcher
Esegui questo script UNA SOLA VOLTA per installare tutto:
  python setup.py

Poi per avviare l'applicazione:
  python main.py --gui          (interfaccia grafica)
  python main.py --run-now      (scraping immediato)
  python main.py --schedule     (scheduler giornaliero)
"""
import sys
import subprocess
import importlib
import json
from pathlib import Path

# ─── Colori console ──────────────────────────────────────────────────────────
G = "\033[92m"   # Verde
Y = "\033[93m"   # Giallo
R = "\033[91m"   # Rosso
B = "\033[94m"   # Blu
W = "\033[97m"   # Bianco
D = "\033[0m"    # Reset
BOLD = "\033[1m"


def banner():
    print(f"""
{B}{BOLD}╔══════════════════════════════════════════════════════╗
║         🏠  Real Estate Monitor — Setup             ║
║              Aggregatore Annunci Immobiliari         ║
╚══════════════════════════════════════════════════════╝{D}
""")


def check_python():
    """Verifica versione Python."""
    print(f"{W}[1/5] Verifica versione Python...{D}")
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        print(f"{R}❌ Python {major}.{minor} rilevato. Richiesto Python 3.10+{D}")
        print(f"   Scarica da: https://www.python.org/downloads/")
        sys.exit(1)
    print(f"{G}   ✓ Python {major}.{minor} OK{D}")


def create_directories():
    """Crea struttura cartelle del progetto."""
    print(f"\n{W}[2/5] Creazione directory...{D}")
    dirs = [
        "config", "database", "scrapers", "utils",
        "gui", "output", "logs",
    ]
    for d in dirs:
        Path(d).mkdir(exist_ok=True)
        print(f"{G}   ✓ {d}/{D}")


def install_dependencies():
    """Installa le dipendenze Python via pip."""
    print(f"\n{W}[3/5] Installazione dipendenze...{D}")
    req_file = Path("requirements.txt")
    if not req_file.exists():
        print(f"{R}   ❌ requirements.txt non trovato!{D}")
        return False

    # Aggiorna pip silenziosamente
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "-q"],
        capture_output=True
    )

    # Installa requirements
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        print(f"{G}   ✓ Tutte le dipendenze installate{D}")
        return True
    else:
        print(f"{Y}   ⚠ Alcuni pacchetti potrebbero avere warning:{D}")
        # Mostra solo errori reali, non i warning
        for line in result.stderr.splitlines():
            if "ERROR" in line:
                print(f"     {R}{line}{D}")
            elif "WARNING" in line:
                print(f"     {Y}{line}{D}")
        return True  # Prosegui comunque


def verify_imports():
    """Verifica che i moduli critici siano importabili."""
    print(f"\n{W}[4/5] Verifica importazioni...{D}")
    critical = [
        ("requests",        "requests"),
        ("bs4",             "beautifulsoup4"),
        ("lxml",            "lxml"),
        ("schedule",        "schedule"),
        ("tkinter",         "tkinter (built-in)"),
    ]
    all_ok = True
    for module, pkg_name in critical:
        try:
            importlib.import_module(module)
            print(f"{G}   ✓ {pkg_name}{D}")
        except ImportError:
            print(f"{R}   ❌ {pkg_name} — installa con: pip install {pkg_name}{D}")
            all_ok = False

    # Verifica Selenium (opzionale ma consigliato)
    try:
        importlib.import_module("undetected_chromedriver")
        importlib.import_module("selenium")
        print(f"{G}   ✓ selenium + undetected-chromedriver{D}")
    except ImportError:
        print(f"{Y}   ⚠ selenium/undetected-chromedriver non installato{D}")
        print(f"     Installa con: {Y}pip install selenium undetected-chromedriver{D}")
        print(f"     Necessario per bypassare Cloudflare (403) su immobiliare.it, subito.it, idealista.it")

    # Verifica Chrome installato
    _check_chrome()
    return all_ok


def _check_chrome():
    """Controlla se Google Chrome è installato."""
    import os, platform
    system = platform.system()
    found = False

    if system == "Windows":
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        found = any(os.path.exists(p) for p in paths)
    elif system == "Darwin":
        found = os.path.exists("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:
        found = os.system("which google-chrome > /dev/null 2>&1") == 0 or \
                os.system("which chromium-browser > /dev/null 2>&1") == 0

    if found:
        print(f"{G}   ✓ Google Chrome installato{D}")
    else:
        print(f"{Y}   ⚠ Google Chrome non trovato{D}")
        print(f"     Scarica da: {Y}https://www.google.com/chrome/{D}")
        print(f"     Necessario per lo scraping con Selenium (bypass Cloudflare)")


def verify_config():
    """Verifica che i file di configurazione esistano e siano validi.
    settings.json viene creato dai default se manca (non è un errore)."""
    print(f"\n{W}[5/5] Verifica configurazione...{D}")
    try:
        from config.defaults import ensure_settings
        ensure_settings()
    except Exception:
        pass
    configs = {
        "config/settings.json": "Impostazioni principali",
        "config/sites.json":    "Elenco siti",
    }
    all_ok = True
    for path, description in configs.items():
        p = Path(path)
        if not p.exists():
            print(f"{R}   ❌ {path} non trovato — {description}{D}")
            all_ok = False
            continue
        try:
            with open(p, encoding="utf-8") as f:
                json.load(f)
            print(f"{G}   ✓ {path}{D}")
        except json.JSONDecodeError as e:
            print(f"{R}   ❌ {path} — JSON non valido: {e}{D}")
            all_ok = False
    return all_ok


def print_summary(all_ok: bool):
    """Stampa il riepilogo finale e le istruzioni d'uso."""
    print()
    if all_ok:
        print(f"{G}{BOLD}╔══════════════════════════════════════════════════════╗")
        print(f"║      ✅  Setup completato con successo!              ║")
        print(f"╚══════════════════════════════════════════════════════╝{D}\n")
    else:
        print(f"{Y}{BOLD}╔══════════════════════════════════════════════════════╗")
        print(f"║   ⚠  Setup completato con alcuni avvisi             ║")
        print(f"╚══════════════════════════════════════════════════════╝{D}\n")

    print(f"{W}{BOLD}Come avviare l'applicazione:{D}\n")
    print(f"  {G}python main.py --gui{D}        → Interfaccia grafica completa")
    print(f"  {G}python main.py --run-now{D}    → Scraping immediato (console)")
    print(f"  {G}python main.py --schedule{D}   → Scheduler giornaliero (headless)")
    print()
    print(f"{W}{BOLD}Configurazione rapida:{D}")
    print(f"  1. Modifica {B}config/settings.json{D} per zona geografica e filtri")
    print(f"  2. Modifica {B}config/sites.json{D} per abilitare/disabilitare siti")
    print(f"  3. Avvia con {G}python main.py --gui{D} e clicca 'Avvia Scraping'")
    print()
    print(f"{W}{BOLD}Automazione giornaliera (Linux/Mac):{D}")
    print(f"  Aggiungi al crontab: {Y}crontab -e{D}")
    print(f"  {Y}0 8 * * * cd /path/to/app && python main.py --run-now{D}")
    print()
    print(f"{W}{BOLD}Automazione giornaliera (Windows Task Scheduler):{D}")
    print(f"  Programma: {Y}python{D}")
    print(f"  Argomenti: {Y}main.py --run-now{D}")
    print()


def ensure_default_settings():
    """Crea config/settings.json dai default se manca. NON chiede nulla:
    tutta la configurazione (zona, orario, filtri) si fa dalla GUI."""
    try:
        from config.defaults import ensure_settings
        ensure_settings()
        print(f"{G}  ✓ config/settings.json pronto.{D}")
    except Exception as e:
        print(f"{Y}  ! Impossibile creare settings.json: {e}{D}")


def main():
    banner()
    check_python()
    create_directories()
    deps_ok  = install_dependencies()
    imps_ok  = verify_imports()
    conf_ok  = verify_config()

    all_ok = deps_ok and imps_ok and conf_ok

    # Crea settings.json dai default se manca (nessuna domanda: la
    # configurazione si fa dalla GUI, scheda Configurazione).
    print()
    ensure_default_settings()
    print(f"{W}  → Configura zona, orario e filtri dalla GUI "
          f"(scheda Configurazione).{D}")

    print_summary(all_ok)

    # Offri avvio immediato
    try:
        print()
        launch = input(f"{W}Avviare l'applicazione adesso? [s/N]: {D}").strip().lower()
        if launch in ("s", "si", "sì", "y", "yes"):
            import subprocess
            subprocess.run([sys.executable, "main.py", "--gui"])
    except (EOFError, KeyboardInterrupt):
        print()


if __name__ == "__main__":
    main()
