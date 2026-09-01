"""
utils/logger.py - Configurazione logging centralizzata
"""
import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logger(name: str = "real_estate_monitor", config: dict = None) -> logging.Logger:
    """
    Configura e restituisce il logger principale dell'applicazione.
    Supporta output su console (con colori) e su file rotante.
    """
    if config is None:
        config = {}

    log_level_str = config.get("level", "INFO")
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    log_file = config.get("file", "logs/monitor.log")
    max_bytes = config.get("max_bytes", 5 * 1024 * 1024)   # 5 MB default
    backup_count = config.get("backup_count", 3)

    # Crea directory log se non esiste
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Evita handler duplicati su re-inizializzazione
    if logger.handlers:
        logger.handlers.clear()

    # --- Formatter con timestamp e livello ---
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=date_fmt)

    # --- Handler Console con colori ANSI ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColorFormatter(fmt, datefmt=date_fmt))
    logger.addHandler(console_handler)

    # --- Handler File Rotante ---
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Impossibile aprire il file di log '{log_file}': {e}")

    return logger


class ColorFormatter(logging.Formatter):
    """Formatter con colori ANSI per output console."""

    COLORS = {
        "DEBUG":    "\033[36m",    # Cyan
        "INFO":     "\033[32m",    # Green
        "WARNING":  "\033[33m",    # Yellow
        "ERROR":    "\033[31m",    # Red
        "CRITICAL": "\033[35m",    # Magenta
    }
    RESET = "\033[0m"
    BOLD  = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{self.BOLD}{record.levelname:<8}{self.RESET}"
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """Restituisce un logger figlio (per moduli specifici)."""
    return logging.getLogger(f"real_estate_monitor.{name}")
