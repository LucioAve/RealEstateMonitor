# Real Estate Monitor — v1.4

Analisi dei tuoi dati reali (settimane di log, database, HTML di debug) dopo
la pubblicazione su GitHub. Trovati e corretti tre bug strutturali che
limitavano seriamente l'accuratezza, più miglioramenti di robustezza.

## Bug critici corretti

### 1. Il filtro geografico non filtrava nulla
La tua configurazione aveva `mode: "both"` con `bounding_box` vuoto. Con
quella combinazione, la logica del filtro lasciava passare QUALSIASI
annuncio, di qualunque città. Causa: due controlli diversi nella GUI
scrivevano sullo stesso campo di configurazione senza saperlo (la scheda
"Zona di ricerca" e il vecchio "Filtro Geografico"), e uno sovrascriveva
l'altro; inoltre un valore di default scritto in una versione precedente
(`mode: "keywords"`) non era nemmeno tra i valori validi del filtro.

**Corretto**: le due fonti (zone di ricerca / parole chiave extra) sono ora
fisicamente separate su disco e si combinano solo a runtime — salvare
l'una non cancella più l'altra. Il filtro ora rifiuta un `mode` non
valido con un avviso invece di disattivarsi in silenzio, e segnala se le
parole chiave configurate sono troppo generiche ("vendita", "casa" ecc.)
per servire da filtro di zona.

### 2. Immobiliare.it e Idealista.it davano 0 annunci da settimane
Dai tuoi HTML di debug: Immobiliare rispondeva con una pagina 404
mascherata da status 200, Idealista con un redirect silenzioso alla
homepage. Causa: la funzione "Applica zona" usava il primo quartiere della
lista (es. "Chiaiano") come se fosse una città — ma questi siti richiedono
un comune vero per costruire l'URL di ricerca. Solo Subito.it (ricerca
testuale libera) continuava a funzionare, ed è per questo che negli ultimi
tempi vedevi risultati solo da lì.

**Corretto**: nuovo campo "Città principale" nella scheda Configurazione,
separato dai quartieri. Gli URL si costruiscono sulla città; i quartieri
restano nell'elenco "Zone" e filtrano i risultati dopo lo scraping (ora che
il filtro geografico funziona davvero). La tua configurazione nel repo è
già stata corretta (città = Napoli, quartieri invariati).

### 3. Con più quartieri, Subito cercava solo il primo
Stesso meccanismo: con 10 quartieri configurati, la ricerca testuale su
Subito usava solo il primo, ignorando gli altri 9. Ora, con più di una
zona, la ricerca usa la città intera e lascia il filtro post-scraping
selezionare i quartieri giusti — stesso approccio già usato per gli altri
portali.

## Accuratezza: filtro categorie non residenziali (Subito)

Analizzando il tuo database reale: **il 38% degli annunci di Subito non
erano case** — uffici, box auto, terreni, camere in condivisione, case
vacanza (la ricerca "immobili" di Subito le raggruppa tutte insieme). Ora
vengono scartate di default. Personalizzabile per singolo sito con la
chiave `subito_exclude_categories` in `sites.json` (lista vuota per non
escludere nulla).

## Robustezza

- **Diagnosi più chiara**: quando una fonte dà 0 annunci, il log ora
  distingue "pagina di errore del sito / URL non valido" da "selettori CSS
  da aggiornare" — la stessa ambiguità ha reso questo bug difficile da
  scovare per settimane.
- **Fallback di riserva per Immobiliare**: il sito sembra aver cambiato
  motore di rendering (React Server Components streaming, non più
  `__NEXT_DATA__`); aggiunta un'euristica basata su link+prezzo come rete
  di sicurezza se i selettori noti falliscono. Non verificabile da qui
  contro il sito reale: testa e, se resta a 0, mandami il nuovo
  `logs/debug_html/immobiliare_..._raw.html` (ora sarà una pagina vera di
  Napoli, non un 404) per la stessa correzione mirata fatta per Subito.
- **Attesa dei redirect JavaScript** in Selenium: alcuni siti (Gabetti,
  Grimaldi) servono una pagina-ponte con fingerprint JS prima di
  reindirizzare; ora il browser attende il redirect prima di leggere il
  contenuto. Beneficia automaticamente anche Gabetti (già presente).

## Nuova fonte

- **Grimaldi Immobiliare** — aggiunta disabilitata, da verificare. Schema
  URL dedotto da un redirect osservato in una sessione precedente; i
  selettori CSS sono generici e non validati contro il sito reale.

## File modificati
`config/defaults.py`, `config/settings.json`, `config/sites.json`,
`gui/app_gui.py`, `utils/geo_filter.py`, `scrapers/subito_scraper.py`,
`scrapers/immobiliare_scraper.py`, `scrapers/idealista_scraper.py`,
`scrapers/base_scraper.py`, `scrapers/selenium_helper.py`, `main.py`.

## Cosa NON è verificabile da qui
Nessuna di queste correzioni è stata testata contro i siti reali (nessun
accesso di rete a quei domini da questo ambiente). Sono verificate contro:
i tuoi log e HTML di debug reali, il tuo database reale, e test automatici
con dati sintetici basati su quei dati reali. Testa e fammi sapere,
specialmente su Immobiliare — è il punto più incerto.
