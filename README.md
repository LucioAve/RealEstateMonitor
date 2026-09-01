SE NON FUNZIONA INSTALLARE NELLA DIR DEL SOFTWARE:
python -m pip install undetected-chromedriver selenium
pip install setuptools
python -c "import undetected_chromedriver; print('OK')"
python -m pip install -r requirements.txt
./setup.py      

py -3.14 -m pip install undetected-chromedriver selenium
python main.py --gui

# 🏠 Real Estate Monitor

**Aggregatore intelligente di annunci immobiliari** — mostra ogni giorno solo le novità per la tua zona.

---

## ✨ Funzionalità

| Feature | Dettaglio |
|---|---|
| **Multi-sito** | immobiliare.it, subito.it, idealista.it + scraper generico |
| **Deduplicazione** | SQLite — mostra solo annunci MAI visti prima |
| **Filtro geografico** | Parole chiave + bounding box lat/lon |
| **Interfaccia grafica** | GUI tkinter con dashboard, storico, config, statistiche |
| **Scheduler** | Esecuzione giornaliera automatica (integrato + cron) |
| **Notifiche** | Email (SMTP) e Telegram Bot |
| **Logging** | File rotante + output console colorato |
| **robots.txt** | Rispetto automatico delle regole di crawling |

---

## 📦 Requisiti

- Python **3.10+**
- Connessione Internet
- (Opzionale) Account Gmail o Bot Telegram per notifiche

---

## 🚀 Installazione e Avvio

### 1. Installa e configura (una tantum)

```bash
cd real_estate_monitor
python setup.py
```

Lo script:
- Verifica la versione Python
- Installa tutte le dipendenze
- Verifica la configurazione
- Offre una configurazione rapida interattiva

### 2. Avvia l'applicazione

```bash
# Interfaccia grafica (consigliato)
python main.py --gui

# Scraping immediato da terminale
python main.py --run-now

# Scheduler giornaliero headless
python main.py --schedule

# Con log verboso
python main.py --run-now --log-level DEBUG
```

---

## 📁 Struttura del Progetto

```
real_estate_monitor/
├── main.py                    # Entry point + CLI
├── setup.py                   # Installazione automatica
├── requirements.txt
│
├── config/
│   ├── settings.json          # Configurazione principale
│   └── sites.json             # Elenco siti da monitorare
│
├── scrapers/
│   ├── base_scraper.py        # Classe base (retry, logging, robots)
│   ├── scraper_manager.py     # Factory + filtri post-scraping
│   ├── immobiliare_scraper.py # Parser immobiliare.it (JSON)
│   ├── subito_scraper.py      # Parser subito.it
│   ├── idealista_scraper.py   # Parser idealista.it (HTML)
│   └── generic_scraper.py     # Scraper generico (CSS selectors)
│
├── database/
│   └── db_manager.py          # SQLite: deduplicazione + storico
│
├── utils/
│   ├── logger.py              # Logging colorato + file rotante
│   ├── geo_filter.py          # Filtro zona (testo + bbox)
│   ├── notifier.py            # Email + Telegram
│   └── robots_checker.py      # Rispetto robots.txt
│
├── gui/
│   └── app_gui.py             # GUI tkinter completa
│
├── output/                    # JSON degli annunci trovati
└── logs/                      # File di log
```

---

## ⚙️ Configurazione

### `config/settings.json`

```json
{
  "schedule": {
    "time": "08:00",            // Orario esecuzione giornaliera
    "run_on_start": true        // Esegui subito all'avvio
  },
  "scraping": {
    "request_delay_seconds": 2.5,  // Pausa tra richieste (rispetto siti)
    "max_pages_per_site": 5,       // Max pagine per sito
    "respect_robots_txt": true
  },
  "geo_filter": {
    "mode": "text",             // "text" | "bbox" | "both"
    "keywords": [               // Parole chiave per zona
      "napoli", "pozzuoli", "vomero", "chiaia"
    ],
    "bounding_box": {           // Usato se mode = "bbox" o "both"
      "lat_min": 40.78, "lat_max": 40.92,
      "lon_min": 14.10, "lon_max": 14.40
    }
  },
  "filters": {
    "listing_types": ["vendita", "affitto"],
    "min_price": 0,
    "max_price": 500000,
    "keywords_exclude": ["garage", "posto auto"]
  }
}
```

### `config/sites.json`

Ogni sito ha:

```json
{
  "id": "mio_sito",
  "name": "Nome Sito",
  "base_url": "https://www.esempio.it",
  "enabled": true,
  "scraper": "generic",         // "immobiliare"|"subito"|"idealista"|"generic"
  "search_urls": {
    "vendita": "https://www.esempio.it/vendita/napoli/",
    "affitto": "https://www.esempio.it/affitto/napoli/"
  },
  "listing_types": ["vendita"],
  // Solo per scraper "generic":
  "listing_selector": "article.card",
  "title_selector":   "h2.title",
  "price_selector":   "span.price",
  "location_selector":"p.location",
  "link_selector":    "a.card-link"
}
```

---

## 🔔 Notifiche

### Email (Gmail)

1. Abilita "App password" su Gmail (Impostazioni → Sicurezza)
2. Configura in `settings.json`:
   ```json
   "email": {
     "enabled": true,
     "smtp_host": "smtp.gmail.com",
     "smtp_port": 587,
     "username": "tuaemail@gmail.com",
     "password": "xxxx xxxx xxxx xxxx",
     "from": "tuaemail@gmail.com",
     "to": "destinatario@email.com"
   }
   ```

### Telegram

1. Crea un bot: parla con `@BotFather` → `/newbot`
2. Ottieni il `chat_id`: invia un messaggio al bot e visita
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Configura:
   ```json
   "telegram": {
     "enabled": true,
     "bot_token": "123456:ABC-DEF...",
     "chat_id": "-100123456789"
   }
   ```

---

## ⏰ Automazione

### Linux/Mac (cron)

```bash
crontab -e
# Aggiunge esecuzione ogni giorno alle 08:00
0 8 * * * cd /percorso/real_estate_monitor && python main.py --run-now >> logs/cron.log 2>&1
```

### Windows (Task Scheduler)

1. Apri **Utilità di pianificazione** → Crea attività di base
2. Trigger: Giornaliero, ore 08:00
3. Azione: `python.exe`, argomenti: `main.py --run-now`
4. Directory di avvio: cartella del progetto

### Scheduler Python integrato

```bash
python main.py --schedule
# Gira in background, esegue ogni giorno all'orario configurato
# Usare nohup su Linux: nohup python main.py --schedule &
```

---

## 📊 Esempio Output Console

```
══════════════════════════════════════════════════
  🏠  3 NUOVI ANNUNCI TROVATI
══════════════════════════════════════════════════

    1. Appartamento 3 camere Vomero con terrazzo
       💶 280.000 €            📍 Vomero, Napoli
       🔗 https://www.immobiliare.it/annunci/12345678/
       🏷  vendita — Immobiliare.it

    2. Bilocale ristrutturato Chiaia
       💶 1.200 €/mese         📍 Chiaia, Napoli
       🔗 https://www.subito.it/immobili/...
       🏷  affitto — Subito.it
```

---

## 🧩 Aggiungere un nuovo sito

### Metodo 1: Scraper generico (no codice)

Aggiungi in `sites.json` con `"scraper": "generic"` e i selettori CSS corretti.
Usa i DevTools del browser (F12 → Inspector) per trovare i selettori giusti.

### Metodo 2: Scraper personalizzato

1. Crea `scrapers/miosito_scraper.py` ereditando da `BaseScraper`
2. Implementa `get_listings()` e `parse_listing()`
3. Registra in `scrapers/scraper_manager.py` → dizionario `SCRAPER_MAP`

---

## 🐛 Troubleshooting

| Problema | Soluzione |
|---|---|
| `ModuleNotFoundError` | Esegui `python setup.py` o `pip install -r requirements.txt` |
| 0 annunci trovati | Il sito ha cambiato layout — apri i DevTools e aggiorna i selettori |
| HTTP 403 | Il sito blocca i bot — aumenta `request_delay_seconds` |
| GUI non si apre | Verifica che tkinter sia installato: `python -m tkinter` |
| Database corrotto | Cancella `database/listings.db` e ricomincia |

---

## 📄 Licenza

MIT — Uso personale/educativo. Rispetta i Termini di Servizio di ogni sito.
