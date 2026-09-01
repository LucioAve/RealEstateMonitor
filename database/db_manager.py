"""
database/db_manager.py - Gestione database SQLite per deduplicazione e storico
Schema:
  listings   → annunci visti (URL hash come PK)
  run_log    → log delle sessioni di scraping
"""
import sqlite3
import hashlib
import json
from datetime import datetime
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("database")

DDL = """
-- Tabella principale: ogni annuncio mai visto
CREATE TABLE IF NOT EXISTS listings (
    id           TEXT PRIMARY KEY,       -- SHA256 dell'URL normalizzato
    url          TEXT NOT NULL UNIQUE,
    title        TEXT,
    price        TEXT,
    location     TEXT,
    listing_date TEXT,
    listing_type TEXT,                   -- "vendita" | "affitto"
    source       TEXT,                   -- sito di origine
    raw_data     TEXT,                   -- JSON completo per riferimento futuro
    seen_at      TEXT NOT NULL,          -- prima volta che l'abbiamo visto
    notified_at  TEXT                    -- quando è stato notificato (null = non ancora)
);

-- Indici utili
CREATE INDEX IF NOT EXISTS idx_listings_seen_at  ON listings(seen_at);
CREATE INDEX IF NOT EXISTS idx_listings_source   ON listings(source);
CREATE INDEX IF NOT EXISTS idx_listings_type     ON listings(listing_type);

-- Log delle sessioni
CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    total_found INTEGER DEFAULT 0,
    new_found   INTEGER DEFAULT 0,
    errors      INTEGER DEFAULT 0,
    notes       TEXT
);
"""


class DatabaseManager:
    """
    Gestisce tutte le operazioni sul database SQLite.
    Thread-safe per uso in GUI multi-thread via check_same_thread=False.
    """

    def __init__(self, db_path: str = "database/listings.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.debug(f"Database aperto: {self.db_path}")

    # ------------------------------------------------------------------
    # Connessione
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        """Crea le tabelle se non esistono."""
        with self._connect() as conn:
            conn.executescript(DDL)
        logger.debug("Schema database inizializzato.")

    # ------------------------------------------------------------------
    # Hash
    # ------------------------------------------------------------------

    @staticmethod
    def compute_id(url: str) -> str:
        """Genera un identificatore univoco stabile dall'URL."""
        normalized = url.strip().lower().rstrip("/")
        return hashlib.sha256(normalized.encode()).hexdigest()

    # ------------------------------------------------------------------
    # API pubblica: deduplicazione
    # ------------------------------------------------------------------

    def is_seen(self, url: str) -> bool:
        """Restituisce True se l'URL è già stato registrato."""
        listing_id = self.compute_id(url)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM listings WHERE id = ? LIMIT 1", (listing_id,)
            ).fetchone()
        return row is not None

    def mark_seen(self, listing: dict) -> bool:
        """
        Salva un nuovo annuncio nel database.
        Ritorna True se inserito, False se già esisteva (race condition).
        """
        listing_id = self.compute_id(listing["url"])
        now = datetime.now().isoformat()

        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO listings
                       (id, url, title, price, location, listing_date,
                        listing_type, source, raw_data, seen_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        listing_id,
                        listing.get("url", ""),
                        listing.get("title", ""),
                        listing.get("price", ""),
                        listing.get("location", ""),
                        listing.get("date", ""),
                        listing.get("listing_type", ""),
                        listing.get("source", ""),
                        json.dumps(listing, ensure_ascii=False, default=str),
                        now,
                    ),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Errore inserimento DB: {e} — url={listing.get('url')}")
            return False

    def mark_notified(self, url: str) -> None:
        """Aggiorna il timestamp di notifica per un annuncio."""
        listing_id = self.compute_id(url)
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE listings SET notified_at=? WHERE id=?", (now, listing_id)
            )

    # ------------------------------------------------------------------
    # Query di sola lettura
    # ------------------------------------------------------------------

    def get_all_listings(self, limit: int = 500, offset: int = 0) -> list[dict]:
        """Restituisce tutti gli annunci salvati (ordinati per data discendente)."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM listings
                   ORDER BY seen_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_listings_today(self) -> list[dict]:
        """Restituisce gli annunci visti oggi."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM listings WHERE seen_at LIKE ? ORDER BY seen_at DESC",
                (f"{today}%",),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_listings(self, query: str) -> list[dict]:
        """Ricerca full-text su titolo e località."""
        like = f"%{query}%"
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM listings
                   WHERE title LIKE ? OR location LIKE ? OR price LIKE ?
                   ORDER BY seen_at DESC LIMIT 200""",
                (like, like, like),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Restituisce statistiche generali sul database."""
        with self._connect() as conn:
            total      = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            today_str  = datetime.now().strftime("%Y-%m-%d")
            today      = conn.execute(
                "SELECT COUNT(*) FROM listings WHERE seen_at LIKE ?", (f"{today_str}%",)
            ).fetchone()[0]
            by_source  = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM listings GROUP BY source ORDER BY cnt DESC"
            ).fetchall()
            by_type    = conn.execute(
                "SELECT listing_type, COUNT(*) as cnt FROM listings GROUP BY listing_type"
            ).fetchall()

        return {
            "total":     total,
            "today":     today,
            "by_source": {r["source"]: r["cnt"] for r in by_source},
            "by_type":   {r["listing_type"]: r["cnt"] for r in by_type},
        }

    # ------------------------------------------------------------------
    # Run log
    # ------------------------------------------------------------------

    def log_run_start(self) -> int:
        """Registra l'inizio di una sessione. Ritorna il run ID."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO run_log (started_at) VALUES (?)",
                (datetime.now().isoformat(),),
            )
            return cur.lastrowid

    def log_run_end(self, run_id: int, total: int, new: int, errors: int, notes: str = "") -> None:
        """Aggiorna il log della sessione al termine."""
        with self._connect() as conn:
            conn.execute(
                """UPDATE run_log
                   SET finished_at=?, total_found=?, new_found=?, errors=?, notes=?
                   WHERE id=?""",
                (datetime.now().isoformat(), total, new, errors, notes, run_id),
            )

    def get_run_history(self, limit: int = 30) -> list[dict]:
        """Restituisce le ultime sessioni di scraping."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM run_log ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_listing(self, url: str) -> None:
        """Rimuove un annuncio dal database (utile per debug/test)."""
        listing_id = self.compute_id(url)
        with self._connect() as conn:
            conn.execute("DELETE FROM listings WHERE id=?", (listing_id,))
        logger.debug(f"Annuncio rimosso: {url}")

    def clear_all(self) -> None:
        """Cancella tutti i dati (ATTENZIONE: irreversibile)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM listings")
            conn.execute("DELETE FROM run_log")
        logger.warning("Database svuotato completamente.")
