"""
utils/geo_filter.py - Filtraggio geografico degli annunci
Supporta due modalità:
  - "text":  matching testuale su titolo/località con lista di parole chiave
  - "bbox":  bounding box lat/lon (se le coordinate sono disponibili)
  - "both":  entrambi (OR logic)
"""
import re
from typing import Any
from .logger import get_logger

logger = get_logger("geo_filter")


def build_geo_filter(config: dict) -> "GeoFilter":
    """
    Costruisce il GeoFilter combinando due fonti SEMPRE separate su disco:
      - config["search_zones"]         → le zone di ricerca (scritte dalla
        scheda "Zona di ricerca" della GUI);
      - config["geo_filter"]["keywords"] → parole chiave AGGIUNTIVE opzionali
        (scritte dal vecchio box "Filtro Geografico").

    Le due liste vengono unite solo qui, a runtime, senza mai scrivere le
    zone dentro geo_filter.keywords su disco: questo evita che salvare
    l'uno cancelli l'altro (bug corretto nella v1.4 — i due controlli GUI
    scrivevano entrambi in geo_filter.keywords, e l'ultimo salvataggio
    sovrascriveva silenziosamente le zone dell'altro).
    """
    geo_cfg = dict(config.get("geo_filter", {}))
    zones = config.get("search_zones", []) or []
    extra = geo_cfg.get("keywords", []) or []
    merged = list(dict.fromkeys([*zones, *extra]))  # ordine stabile, no duplicati
    geo_cfg["keywords"] = merged
    return GeoFilter(geo_cfg)


class GeoFilter:
    """
    Filtra una lista di annunci normalizzati per zona geografica.
    """

    _VALID_MODES = ("text", "bbox", "both")

    # Parole così comuni negli annunci immobiliari che usarle come filtro
    # di zona equivale a non filtrare nulla (compaiono nella quasi totalità
    # dei titoli, indipendentemente da dove si trova l'immobile).
    _TROPPO_GENERICHE = {
        "casa", "appartamento", "immobile", "vendita", "affitto", "affittasi",
        "vendesi", "fittasi", "acquisto", "locazione", "in vendita", "in affitto",
    }

    def __init__(self, config: dict):
        self.enabled = config.get("enabled", True)
        mode = config.get("mode", "text")
        if mode not in self._VALID_MODES:
            logger.warning(
                f"geo_filter.mode='{mode}' non valido (valori ammessi: "
                f"{', '.join(self._VALID_MODES)}) — uso 'text'. Nessun "
                f"annuncio verrebbe filtrato con un modo sconosciuto."
            )
            mode = "text"
        self.mode = mode

        # Lista parole chiave per matching testuale (lowercase)
        raw_kw = config.get("keywords", [])
        self.keywords = [k.lower().strip() for k in raw_kw if k and k.strip()]

        # Bounding box
        bb = config.get("bounding_box", {})
        self.lat_min = bb.get("lat_min")
        self.lat_max = bb.get("lat_max")
        self.lon_min = bb.get("lon_min")
        self.lon_max = bb.get("lon_max")

        self._has_bbox = all(
            v is not None for v in [self.lat_min, self.lat_max, self.lon_min, self.lon_max]
        )

        if self.mode in ("bbox", "both") and not self._has_bbox:
            logger.warning(
                f"geo_filter.mode='{self.mode}' ma bounding_box non è "
                f"configurato: il filtro userà solo le parole chiave di zona."
            )
        if not self.keywords and not self._has_bbox:
            logger.warning(
                "Filtro geografico SENZA zone configurate (né parole chiave "
                "né bounding box): nessun annuncio verrà scartato per zona."
            )
        generiche = self._TROPPO_GENERICHE & set(self.keywords)
        if generiche:
            logger.warning(
                f"Parole chiave troppo generiche nel filtro: "
                f"{', '.join(sorted(generiche))}. Compaiono nella quasi "
                f"totalità degli annunci immobiliari: usarle come filtro di "
                f"zona equivale a non filtrare nulla per zona. Rimuovile "
                f"dalle parole chiave extra — la zona è già coperta da "
                f"search_zones."
            )

        logger.debug(
            f"GeoFilter init — mode={self.mode}, keywords={len(self.keywords)}, bbox={self._has_bbox}"
        )

    # ------------------------------------------------------------------
    # Interfaccia pubblica
    # ------------------------------------------------------------------

    def filter(self, listings: list[dict]) -> list[dict]:
        """Filtra la lista e restituisce solo gli annunci pertinenti."""
        if not self.enabled:
            return listings

        result = []
        for listing in listings:
            if self._matches(listing):
                result.append(listing)
        return result

    def _matches(self, listing: dict) -> bool:
        """Ritorna True se l'annuncio supera il filtro geografico."""
        if self.mode == "text":
            return self._match_text(listing)
        if self.mode == "bbox":
            return self._match_bbox(listing)
        if self.mode == "both":
            # "both" ha senso come OR solo se ENTRAMBI i criteri sono
            # configurati. Se uno dei due manca, degradare su quello
            # disponibile invece di lasciare che l'assente (pass-through
            # per definizione) renda l'OR sempre vero e disattivi il filtro.
            if self._has_bbox and self.keywords:
                return self._match_text(listing) or self._match_bbox(listing)
            if self._has_bbox:
                return self._match_bbox(listing)
            return self._match_text(listing)
        return True  # mode già validato in __init__: qui non si arriva mai

    def _match_text(self, listing: dict) -> bool:
        """Controlla se titolo o località contengono almeno una keyword."""
        if not self.keywords:
            return True  # Nessuna keyword → tutto passa

        # Campi da controllare (concatenati in lowercase)
        haystack = " ".join(filter(None, [
            listing.get("title",    ""),
            listing.get("location", ""),
            listing.get("address",  ""),
        ])).lower()

        for kw in self.keywords:
            if kw in haystack:
                return True

        return False

    def _match_bbox(self, listing: dict) -> bool:
        """Controlla se le coordinate del listing sono dentro il bounding box."""
        if not self._has_bbox:
            return True  # Bbox non configurato → non filtrare

        lat = listing.get("latitude")
        lon = listing.get("longitude")

        if lat is None or lon is None:
            # Coordinate assenti: fallback su text se possibile
            if self.keywords:
                return self._match_text(listing)
            return True  # Nessun modo per filtrare → lascia passare

        try:
            lat, lon = float(lat), float(lon)
            return (self.lat_min <= lat <= self.lat_max and
                    self.lon_min <= lon <= self.lon_max)
        except (TypeError, ValueError):
            return True


# ------------------------------------------------------------------
# Utility: pulizia stringhe geografiche
# ------------------------------------------------------------------

def normalize_location(raw: str | None) -> str:
    """Normalizza una stringa di località (strip, lowercase, rimuove simboli extra)."""
    if not raw:
        return ""
    cleaned = re.sub(r"\s+", " ", raw.strip())
    return cleaned


def parse_coordinates(raw: str | None) -> tuple[float, float] | None:
    """
    Tenta di estrarre (lat, lon) da una stringa tipo '40.8518, 14.2681'
    o da attributi data-lat / data-lon.
    """
    if not raw:
        return None
    match = re.search(r"(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)", raw)
    if match:
        try:
            return float(match.group(1)), float(match.group(2))
        except ValueError:
            pass
    return None
