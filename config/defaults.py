"""
config/defaults.py
Impostazioni di default e utilità per garantire l'esistenza di
config/settings.json. Usato sia dalla GUI sia da main.py/setup.py, così
non serve più configurare nulla da terminale: il file viene creato in
automatico coi valori di default e poi modificato SOLO dalla GUI.
"""
import json
from pathlib import Path

SETTINGS_PATH = Path("config/settings.json")


def default_settings() -> dict:
    """Configurazione iniziale completa dell'applicazione."""
    return {
        "version": "1.4",
        "main_city": "",              # città usata per costruire gli URL sui portali
                                      # (obbligatoria se search_zones contiene quartieri)
        "search_zones": [],           # quartieri/zone per il filtro POST-scraping
        "scraping": {
            "max_pages_per_site": 3,
            "request_delay_seconds": 2.0,
            "timeout_seconds": 25,
            "selenium_headless": True,
        },
        "filters": {
            "listing_types": ["vendita", "affitto"],
            "min_price": 0,
            "max_price": 9999999,
            "keywords_exclude": [],
        },
        "geo_filter": {
            "mode": "text",               # "text" | "bbox" | "both" (unici valori validi, vedi utils/geo_filter.py)
            "keywords": [],               # parole chiave AGGIUNTIVE, opzionali: le zone in search_zones
                                          # si sommano sempre automaticamente, non serve ripeterle qui
            "bounding_box": {},
        },
        "schedule": {
            "time": "08:00",
            "run_on_start": False,
        },
        "notifications": {
            "enabled": False,
            "email": {"enabled": False, "smtp_host": "", "smtp_port": "587",
                      "username": "", "password": "", "to": ""},
            "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        },
        "database": {"path": "database/listings.db"},
        "output": {"export_dir": "output"},
        "logging": {"level": "INFO"},
    }


def _deep_merge(base: dict, override: dict) -> dict:
    """Unisce override su base: i valori dell'utente vincono, le chiavi
    nuove dei default vengono aggiunte (migrazione automatica)."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_settings(path: Path = SETTINGS_PATH) -> dict:
    """
    Garantisce che config/settings.json esista e sia completo.
    - se manca: lo crea coi default;
    - se esiste: lo carica e aggiunge eventuali chiavi mancanti dei default;
    - se è corrotto: lo rigenera dai default (salvando un backup .bak).
    Ritorna il dizionario di configurazione.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    defaults = default_settings()

    if not path.exists():
        save_settings(defaults, path)
        return defaults

    try:
        user = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        try:
            path.rename(path.with_suffix(".json.bak"))
        except OSError:
            pass
        save_settings(defaults, path)
        return defaults

    merged = _deep_merge(defaults, user)
    if merged != user:
        save_settings(merged, path)   # completa le chiavi mancanti
    return merged


def save_settings(config: dict, path: Path = SETTINGS_PATH) -> None:
    """Scrittura atomica di settings.json (evita file corrotti a metà)."""
    import os, tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
