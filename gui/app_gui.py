"""
gui/app_gui.py — GUI principale con tkinter/ttk (PATCHED v1.2.2)
Layout a schede:
  Dashboard — nuovi annunci dell'ultima sessione
  Storico — tutti gli annunci con ricerca
  Config — siti, filtri, notifiche, scheduler
  Statistiche — grafici e contatori
  Log — log in tempo reale

PATCH v1.2.2:
  - Fix bug lambda scope (NameError su variabile e nel popup errore)
  - Errori nel thread worker mostrati in messagebox
  - Check siti abilitati prima di partire
  - Stato pulsante sempre ripristinato anche in caso di crash
"""
import sys
import json
import threading
import queue
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# Costanti di stile
BG_DARK = "#1e1e2e"
BG_MID = "#2a2a3e"
BG_CARD = "#313147"
ACCENT = "#7c5cfc"
ACCENT2 = "#00d4aa"
TEXT_PRI = "#e0e0f0"
TEXT_SEC = "#9090b0"
SUCCESS = "#4caf50"
WARNING = "#ff9800"
DANGER = "#f44336"
FONT_SAN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_H1 = ("Segoe UI", 18, "bold")
FONT_H2 = ("Segoe UI", 13, "bold")
FONT_MONO = ("Courier New", 9)


def launch_gui(config: dict, logger):
    """Lancia la finestra GUI principale."""
    root = tk.Tk()
    app = RealEstateApp(root, config, logger)
    root.mainloop()


class RealEstateApp:

    def __init__(self, root: tk.Tk, config: dict, logger):
        self.root = root
        self.config = config
        self.logger = logger
        self._log_queue: queue.Queue = queue.Queue()
        self._job_thread: threading.Thread | None = None
        self._is_running = False
        self._last_results: list[dict] = []

        from database.db_manager import DatabaseManager
        self.db = DatabaseManager(config.get("database", {}).get("path", "database/listings.db"))

        self.root.title("Real Estate Monitor")
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)
        self.root.configure(bg=BG_DARK)

        self._setup_styles()
        self._build_ui()
        self._setup_log_handler()

        self.root.after(500, self._refresh_stats)
        self.root.after(800, self._load_history)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG_DARK, foreground=TEXT_PRI, font=FONT_SAN,
                        fieldbackground=BG_MID, selectbackground=ACCENT, selectforeground="white")
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_MID, foreground=TEXT_SEC,
                        padding=[18, 8], font=FONT_SAN)
        style.map("TNotebook.Tab",
                  background=[("selected", BG_CARD), ("active", BG_MID)],
                  foreground=[("selected", TEXT_PRI), ("active", TEXT_PRI)])
        style.configure("TFrame", background=BG_DARK)
        style.configure("Card.TFrame", background=BG_CARD, relief="flat")
        style.configure("Mid.TFrame", background=BG_MID, relief="flat")
        style.configure("TLabel", background=BG_DARK, foreground=TEXT_PRI, font=FONT_SAN)
        style.configure("Sec.TLabel", background=BG_DARK, foreground=TEXT_SEC, font=FONT_SAN)
        style.configure("Card.TLabel", background=BG_CARD, foreground=TEXT_PRI, font=FONT_SAN)
        style.configure("H1.TLabel", background=BG_DARK, foreground=TEXT_PRI, font=FONT_H1)
        style.configure("H2.TLabel", background=BG_DARK, foreground=TEXT_PRI, font=FONT_H2)
        style.configure("Accent.TLabel", background=BG_DARK, foreground=ACCENT, font=FONT_BOLD)
        style.configure("Success.TLabel", background=BG_DARK, foreground=SUCCESS, font=FONT_BOLD)
        style.configure("Warn.TLabel", background=BG_DARK, foreground=WARNING, font=FONT_BOLD)
        style.configure("TButton", background=ACCENT, foreground="white", font=FONT_BOLD,
                        borderwidth=0, focusthickness=0, padding=[14, 8])
        style.map("TButton",
                  background=[("active", "#9575d4"), ("disabled", BG_MID)],
                  foreground=[("disabled", TEXT_SEC)])
        style.configure("Danger.TButton", background=DANGER, foreground="white",
                        font=FONT_BOLD, borderwidth=0, padding=[14, 8])
        style.configure("Success.TButton", background=SUCCESS, foreground="white",
                        font=FONT_BOLD, borderwidth=0, padding=[14, 8])
        style.configure("Small.TButton", background=BG_MID, foreground=TEXT_PRI,
                        font=FONT_SAN, borderwidth=0, padding=[8, 4])
        style.map("Small.TButton", background=[("active", ACCENT)])
        style.configure("Treeview", background=BG_MID, foreground=TEXT_PRI,
                        fieldbackground=BG_MID, rowheight=28, borderwidth=0, font=FONT_SAN)
        style.configure("Treeview.Heading", background=BG_CARD, foreground=TEXT_SEC,
                        font=FONT_BOLD, borderwidth=0)
        style.map("Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])
        style.configure("TEntry", fieldbackground=BG_MID, foreground=TEXT_PRI,
                        borderwidth=1, insertcolor=TEXT_PRI)
        style.configure("TCombobox", fieldbackground=BG_MID, foreground=TEXT_PRI, background=BG_MID)
        style.configure("TScrollbar", background=BG_MID, troughcolor=BG_DARK,
                        borderwidth=0, arrowsize=13)
        style.configure("TCheckbutton", background=BG_DARK, foreground=TEXT_PRI)
        style.configure("TLabelframe", background=BG_DARK, foreground=TEXT_SEC, font=FONT_SAN)
        style.configure("TLabelframe.Label", background=BG_DARK, foreground=TEXT_SEC, font=FONT_SAN)
        style.configure("Horizontal.TProgressbar", troughcolor=BG_MID, background=ACCENT, borderwidth=0)

    def _build_ui(self):
        header = ttk.Frame(self.root, style="Mid.TFrame")
        header.pack(fill="x", padx=0, pady=0)
        ttk.Label(header, text="Real Estate Monitor", font=FONT_H1,
                  background=BG_MID, foreground=ACCENT).pack(side="left", padx=20, pady=12)

        self._status_var = tk.StringVar(value="Pronto")
        ttk.Label(header, textvariable=self._status_var, style="Sec.TLabel",
                  background=BG_MID).pack(side="right", padx=10)

        self._run_btn = ttk.Button(header, text="Avvia Scraping",
                                   command=self._start_job)
        self._run_btn.pack(side="right", padx=5, pady=8)

        self._progress = ttk.Progressbar(self.root, mode="indeterminate",
                                         style="Horizontal.TProgressbar")

        self._nb = ttk.Notebook(self.root)
        self._nb.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        self._tab_dashboard = ttk.Frame(self._nb, style="TFrame")
        self._tab_history = ttk.Frame(self._nb, style="TFrame")
        self._tab_config = ttk.Frame(self._nb, style="TFrame")
        self._tab_stats = ttk.Frame(self._nb, style="TFrame")
        self._tab_log = ttk.Frame(self._nb, style="TFrame")

        self._nb.add(self._tab_dashboard, text=" Dashboard ")
        self._nb.add(self._tab_history, text=" Storico ")
        self._nb.add(self._tab_config, text=" Config ")
        self._nb.add(self._tab_stats, text=" Statistiche ")
        self._nb.add(self._tab_log, text=" Log ")

        self._build_dashboard_tab()
        self._build_history_tab()
        self._build_config_tab()
        self._build_stats_tab()
        self._build_log_tab()

    def _build_dashboard_tab(self):
        tab = self._tab_dashboard
        top = ttk.Frame(tab)
        top.pack(fill="x", padx=16, pady=(16, 6))
        ttk.Label(top, text="Nuovi annunci", style="H2.TLabel").pack(side="left")
        self._new_count_lbl = ttk.Label(top, text="—", style="Accent.TLabel",
                                        font=("Segoe UI", 20, "bold"))
        self._new_count_lbl.pack(side="left", padx=12)
        ttk.Button(top, text="Aggiorna", style="Small.TButton",
                   command=self._load_todays_listings).pack(side="right")
        ttk.Button(top, text="Esporta JSON", style="Small.TButton",
                   command=self._export_json).pack(side="right", padx=6)

        cols = ("source", "title", "price", "location", "date", "type")
        self._dash_tree = self._make_tree(tab, cols, {
            "source": ("Sito", 90),
            "title": ("Titolo", 350),
            "price": ("Prezzo", 110),
            "location": ("Zona", 160),
            "date": ("Data", 90),
            "type": ("Tipo", 70),
        })
        self._dash_tree.bind("<Double-1>", self._open_listing_url)
        self._dash_tree.bind("<Return>", self._open_listing_url)
        ttk.Label(tab, text="Doppio click apre nel browser",
                  style="Sec.TLabel").pack(pady=(0, 8))

    def _build_history_tab(self):
        tab = self._tab_history
        search_frame = ttk.Frame(tab)
        search_frame.pack(fill="x", padx=16, pady=14)
        ttk.Label(search_frame, text="Cerca:").pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._search_history())
        ttk.Entry(search_frame, textvariable=self._search_var,
                  width=40).pack(side="left", padx=8)
        ttk.Button(search_frame, text="Mostra tutto", style="Small.TButton",
                   command=self._load_history).pack(side="left")
        self._hist_count_lbl = ttk.Label(search_frame, text="", style="Sec.TLabel")
        self._hist_count_lbl.pack(side="right")

        cols = ("source", "title", "price", "location", "seen_at", "type")
        self._hist_tree = self._make_tree(tab, cols, {
            "source": ("Sito", 90),
            "title": ("Titolo", 320),
            "price": ("Prezzo", 110),
            "location": ("Zona", 150),
            "seen_at": ("Visto il", 120),
            "type": ("Tipo", 70),
        })
        self._hist_tree.bind("<Double-1>", self._open_history_url)

    def _build_config_tab(self):
        tab = self._tab_config
        canvas = tk.Canvas(tab, bg=BG_DARK, highlightthickness=0)
        sb = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(win_id, width=canvas.winfo_width())
        inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))

        pad = {"padx": 20, "pady": 8}

        lfz = ttk.LabelFrame(inner, text=" Zona di ricerca ", padding=12)
        lfz.pack(fill="x", **pad)

        ttk.Label(lfz, text="Città principale (obbligatoria: è quella usata "
                            "per costruire gli URL sui portali):").pack(anchor="w")
        city_row = ttk.Frame(lfz)
        city_row.pack(fill="x", pady=(2, 8))
        self._city_var = tk.StringVar(value=self.config.get("main_city", "Napoli"))
        ttk.Entry(city_row, textvariable=self._city_var, width=30).pack(side="left")

        ttk.Label(lfz, text="Quartieri/zone da restringere (una per riga, opzionale — "
                            "usati per filtrare i risultati DOPO la ricerca sulla città):"
                  ).pack(anchor="w")
        self._zona_text = tk.Text(lfz, height=3, width=50, bg=BG_MID,
                                  fg=TEXT_PRI, insertbackground=TEXT_PRI,
                                  relief="flat", font=FONT_SAN)
        self._zona_text.pack(fill="x", pady=6)
        zone_saved = self.config.get("search_zones", [])
        self._zona_text.insert("1.0", "\n".join(zone_saved))
        zrow = ttk.Frame(lfz)
        zrow.pack(fill="x")
        ttk.Button(zrow, text="Applica zona alle fonti", style="Small.TButton",
                   command=self._apply_zone).pack(side="left")
        self._zona_status = ttk.Label(zrow, text="", style="Sec.TLabel")
        self._zona_status.pack(side="left", padx=10)
        ttk.Label(lfz, text="Esempio: città 'Napoli' + quartieri 'Chiaiano, Vomero' → "
                            "i portali cercano su tutta Napoli, poi solo gli annunci "
                            "di quei quartieri vengono mostrati. Senza città, la "
                            "ricerca su alcuni portali fallisce se i quartieri non "
                            "sono comuni autonomi.",
                  style="Sec.TLabel", wraplength=600).pack(anchor="w", pady=(4, 0))

        lf = ttk.LabelFrame(inner, text=" Scheduler ", padding=12)
        lf.pack(fill="x", **pad)
        row = ttk.Frame(lf)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Orario giornaliero (HH:MM):").pack(side="left")
        self._sched_time_var = tk.StringVar(
            value=self.config.get("schedule", {}).get("time", "08:00"))
        ttk.Entry(row, textvariable=self._sched_time_var, width=8).pack(side="left", padx=8)

        self._sched_run_start = tk.BooleanVar(
            value=self.config.get("schedule", {}).get("run_on_start", True))
        ttk.Checkbutton(lf, text="Avvia automaticamente all'apertura",
                        variable=self._sched_run_start).pack(anchor="w", pady=2)

        sched_row = ttk.Frame(lf)
        sched_row.pack(fill="x", pady=6)
        self._scheduler_btn = ttk.Button(sched_row, text="Avvia Scheduler",
                                         command=self._toggle_scheduler, style="Success.TButton")
        self._scheduler_btn.pack(side="left")
        self._sched_status_lbl = ttk.Label(sched_row, text="Non attivo", style="Sec.TLabel")
        self._sched_status_lbl.pack(side="left", padx=10)

        lf2 = ttk.LabelFrame(inner, text="  🔎 Parole chiave aggiuntive (opzionali)  ", padding=12)
        lf2.pack(fill="x", **pad)
        ttk.Label(lf2, text="Si sommano SEMPRE alle zone impostate sopra — "
                            "non serve ripetere qui i nomi di quartieri/città.",
                  style="Sec.TLabel", wraplength=600).pack(anchor="w", pady=(0, 6))
        geo = self.config.get("geo_filter", {})
        r2 = ttk.Frame(lf2)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="Modalita:").pack(side="left")
        self._geo_mode_var = tk.StringVar(value=geo.get("mode", "text"))
        ttk.Combobox(r2, textvariable=self._geo_mode_var, width=12,
                     values=["text", "bbox", "both"], state="readonly").pack(side="left", padx=8)
        ttk.Label(r2, text="(bbox/both richiedono un bounding_box in "
                           "settings.json: non c'è ancora un editor in GUI; "
                           "senza, il filtro userà solo le parole chiave)",
                  style="Sec.TLabel", wraplength=380).pack(side="left", padx=8)

        r3 = ttk.Frame(lf2)
        r3.pack(fill="x", pady=4)
        ttk.Label(r3, text="Parole chiave EXTRA (una per riga, es. per escludere/includere "
                           "termini oltre alla zona):").pack(anchor="w")
        self._geo_kw_text = tk.Text(r3, height=4, width=50, bg=BG_MID, fg=TEXT_PRI,
                                    insertbackground=TEXT_PRI, font=FONT_MONO,
                                    relief="flat", borderwidth=1)
        self._geo_kw_text.pack(fill="x", pady=4)
        self._geo_kw_text.insert("1.0", "\n".join(geo.get("keywords", [])))

        lf3 = ttk.LabelFrame(inner, text=" Filtri Annunci ", padding=12)
        lf3.pack(fill="x", **pad)
        filters = self.config.get("filters", {})
        prow = ttk.Frame(lf3)
        prow.pack(fill="x", pady=2)
        ttk.Label(prow, text="Prezzo min EUR:").pack(side="left")
        self._pmin_var = tk.StringVar(value=str(filters.get("min_price", 0)))
        ttk.Entry(prow, textvariable=self._pmin_var, width=12).pack(side="left", padx=8)
        ttk.Label(prow, text="Prezzo max EUR:").pack(side="left")
        self._pmax_var = tk.StringVar(value=str(filters.get("max_price", 9999999)))
        ttk.Entry(prow, textvariable=self._pmax_var, width=12).pack(side="left", padx=8)

        exrow = ttk.Frame(lf3)
        exrow.pack(fill="x", pady=4)
        ttk.Label(exrow, text="Parole da escludere (virgola-sep):").pack(anchor="w")
        self._exclude_var = tk.StringVar(
            value=", ".join(filters.get("keywords_exclude", [])))
        ttk.Entry(lf3, textvariable=self._exclude_var, width=60).pack(fill="x", pady=2)

        lf4 = ttk.LabelFrame(inner, text=" Notifiche ", padding=12)
        lf4.pack(fill="x", **pad)
        notif = self.config.get("notifications", {})
        self._notif_enabled = tk.BooleanVar(value=notif.get("enabled", False))
        ttk.Checkbutton(lf4, text="Abilita notifiche",
                        variable=self._notif_enabled).pack(anchor="w")

        ef = ttk.LabelFrame(lf4, text=" Email ", padding=8)
        ef.pack(fill="x", pady=6)
        email_cfg = notif.get("email", {})
        self._email_enabled = tk.BooleanVar(value=email_cfg.get("enabled", False))
        ttk.Checkbutton(ef, text="Abilita Email", variable=self._email_enabled).pack(anchor="w")

        fields_email = [
            ("SMTP Host", "smtp_host"), ("SMTP Port", "smtp_port"),
            ("Username", "username"), ("Password", "password"),
            ("From", "from"), ("To", "to"),
        ]
        self._email_vars = {}
        for label, key in fields_email:
            r = ttk.Frame(ef)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text=f"{label}:", width=12, anchor="e").pack(side="left")
            show = "*" if key == "password" else ""
            var = tk.StringVar(value=str(email_cfg.get(key, "")))
            ttk.Entry(r, textvariable=var, show=show, width=40).pack(side="left", padx=6)
            self._email_vars[key] = var

        tf = ttk.LabelFrame(lf4, text=" Telegram ", padding=8)
        tf.pack(fill="x", pady=4)
        tg_cfg = notif.get("telegram", {})
        self._tg_enabled = tk.BooleanVar(value=tg_cfg.get("enabled", False))
        ttk.Checkbutton(tf, text="Abilita Telegram", variable=self._tg_enabled).pack(anchor="w")
        self._tg_vars = {}
        for label, key in [("Bot Token", "bot_token"), ("Chat ID", "chat_id")]:
            r = ttk.Frame(tf)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text=f"{label}:", width=12, anchor="e").pack(side="left")
            var = tk.StringVar(value=str(tg_cfg.get(key, "")))
            ttk.Entry(r, textvariable=var, width=40).pack(side="left", padx=6)
            self._tg_vars[key] = var

        ttk.Button(inner, text="Salva configurazione",
                   command=self._save_config).pack(pady=14, padx=20, anchor="w")

    def _build_stats_tab(self):
        tab = self._tab_stats
        top = ttk.Frame(tab)
        top.pack(fill="x", padx=20, pady=16)
        ttk.Label(top, text="Statistiche database", style="H2.TLabel").pack(side="left")
        ttk.Button(top, text="Aggiorna", style="Small.TButton",
                   command=self._refresh_stats).pack(side="right")

        self._stat_cards_frame = ttk.Frame(tab)
        self._stat_cards_frame.pack(fill="x", padx=20, pady=(0, 16))

        ttk.Label(tab, text="Ultime sessioni di scraping", style="H2.TLabel").pack(
            anchor="w", padx=20, pady=(8, 4))
        cols = ("started_at", "finished_at", "total_found", "new_found", "errors")
        self._runs_tree = self._make_tree(tab, cols, {
            "started_at": ("Inizio", 160),
            "finished_at": ("Fine", 160),
            "total_found": ("Tot trovati", 100),
            "new_found": ("Nuovi", 100),
            "errors": ("Errori", 80),
        }, height=8)

        ttk.Button(tab, text="Svuota database (ATTENZIONE)",
                   style="Danger.TButton", command=self._clear_db).pack(
                       pady=12, padx=20, anchor="w")

    def _build_log_tab(self):
        tab = self._tab_log
        controls = ttk.Frame(tab)
        controls.pack(fill="x", padx=12, pady=8)
        ttk.Label(controls, text="Log applicazione", style="H2.TLabel").pack(side="left")
        ttk.Button(controls, text="Pulisci", style="Small.TButton",
                   command=self._clear_log).pack(side="right")
        ttk.Button(controls, text="Salva log", style="Small.TButton",
                   command=self._save_log).pack(side="right", padx=6)

        self._log_text = scrolledtext.ScrolledText(
            tab, bg=BG_DARK, fg=TEXT_PRI, font=FONT_MONO,
            state="disabled", wrap="word", relief="flat",
            insertbackground=TEXT_PRI, selectbackground=ACCENT
        )
        self._log_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._log_text.tag_configure("INFO", foreground=SUCCESS)
        self._log_text.tag_configure("WARNING", foreground=WARNING)
        self._log_text.tag_configure("ERROR", foreground=DANGER)
        self._log_text.tag_configure("DEBUG", foreground=TEXT_SEC)
        self._log_text.tag_configure("CRITICAL", foreground="#ff00ff")

    def _make_tree(self, parent, columns: tuple, defs: dict, height: int = 15) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree._defs = defs
        tree._sort_state: dict = {}
        for col in columns:
            text, width = defs.get(col, (col, 100))
            tree.heading(col, text=text, anchor="w",
                         command=lambda c=col, t=tree: self._sort_column(t, c))
            tree.column(col, width=width, minwidth=40, anchor="w")

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        tree.tag_configure("even", background=BG_MID)
        tree.tag_configure("odd", background=BG_CARD)
        tree.tag_configure("new", background="#1a3a2a", foreground=ACCENT2)

        return tree

    def _sort_column(self, tree: ttk.Treeview, col: str):
        import re
        state = tree._sort_state
        reverse = (state.get("col") == col) and not state.get("reverse", False)
        tree._sort_state = {"col": col, "reverse": reverse}

        rows = [(tree.set(iid, col), iid) for iid in tree.get_children("")]

        def sort_key(item):
            val = item[0]
            cleaned = val.replace(".", "").replace(",", ".")
            nums = re.findall(r"\d+(?:\.\d+)?", cleaned)
            if nums:
                try:
                    return (0, float(nums[0]), "")
                except ValueError:
                    pass
            return (1, 0.0, val.lower())

        rows.sort(key=sort_key, reverse=reverse)

        for index, (_, iid) in enumerate(rows):
            tree.move(iid, "", index)
            current_tags = tree.item(iid, "tags")
            if "new" not in current_tags:
                tree.item(iid, tags=("even" if index % 2 == 0 else "odd",))

        defs = getattr(tree, "_defs", {})
        for c in tree["columns"]:
            label, _ = defs.get(c, (c, 100))
            if c == col:
                arrow = " " + ("↑" if not reverse else "↓")
                tree.heading(c, text=label + arrow)
            else:
                tree.heading(c, text=label)

    def _stat_card(self, parent, label: str, value: str, color: str = TEXT_PRI) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.pack(side="left", padx=8, pady=4, ipadx=8)
        ttk.Label(card, text=value, font=("Segoe UI", 24, "bold"),
                  background=BG_CARD, foreground=color).pack()
        ttk.Label(card, text=label, style="Card.TLabel",
                  foreground=TEXT_SEC).pack()
        return card

    # ================================================================
    #  AZIONI SCRAPING — errori ora visibili in messagebox
    # ================================================================

    def _start_job(self):
        if self._is_running:
            messagebox.showinfo("In corso", "Scraping gia in esecuzione.")
            return

        try:
            sites_path = Path("config/sites.json")
            if not sites_path.exists():
                messagebox.showerror("Errore", "File config/sites.json non trovato!")
                return
            with open(sites_path, encoding="utf-8") as f:
                sites = json.load(f)
            enabled = [s for s in sites if s.get("enabled", True)]
            if not enabled:
                messagebox.showwarning("Nessuna fonte",
                    "Nessun sito abilitato in config/sites.json.\n"
                    "Abilita almeno una fonte prima di avviare.")
                return
        except Exception as e:
            messagebox.showerror("Errore config",
                f"Impossibile leggere config/sites.json:\n{e}")
            return

        self._is_running = True
        self._run_btn.configure(state="disabled", text="Scraping...")
        self._status_var.set("Scraping in corso...")
        self._progress.pack(fill="x", padx=10, pady=(0, 4))
        self._progress.start(10)

        self._job_thread = threading.Thread(target=self._run_job, daemon=True)
        self._job_thread.start()

    def _run_job(self):
        new_listings = []
        try:
            import json as _json
            from scrapers.scraper_manager import ScraperManager
            from utils.geo_filter import build_geo_filter
            from utils.notifier import Notifier

            self._log("INFO", "=== Avvio sessione scraping ===")
            run_id = self.db.log_run_start()

            sites_path = Path("config/sites.json")
            with open(sites_path, encoding="utf-8") as f:
                sites = _json.load(f)

            geo_filter = build_geo_filter(self.config)
            scraper_manager = ScraperManager(self.config)
            notifier = Notifier(self.config.get("notifications", {}))

            all_new = []
            total_found = 0
            errors = 0

            for site in sites:
                if not site.get("enabled", True):
                    self._log("DEBUG", f"Sito disabilitato: {site['name']}")
                    continue

                self._log("INFO", f"Scraping: {site['name']}")
                self._status_var.set(f"Scraping {site['name']}...")

                try:
                    listings = scraper_manager.scrape_site(site)
                    total_found += len(listings)
                    self._log("INFO", f" -> {len(listings)} annunci trovati")

                    filtered = geo_filter.filter(listings)
                    self._log("INFO", f" -> {len(filtered)} dopo filtro geo")

                    for listing in filtered:
                        if not self.db.is_seen(listing["url"]):
                            self.db.mark_seen(listing)
                            all_new.append(listing)

                    self._log("INFO", f" -> {len(all_new)} nuovi finora")

                except Exception as e:
                    errors += 1
                    tb = traceback.format_exc()
                    self._log("ERROR", f"Errore su {site['name']}: {e}\n{tb}")

            if all_new:
                out_dir = Path(self.config.get("output", {}).get("directory", "output"))
                out_dir.mkdir(exist_ok=True)
                fname = out_dir / f"new_listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(fname, "w", encoding="utf-8") as f:
                    _json.dump(all_new, f, ensure_ascii=False, indent=2, default=str)
                self._log("INFO", f"Risultati salvati: {fname}")

                if self.config.get("notifications", {}).get("enabled"):
                    notifier.send(all_new)

            self.db.log_run_end(run_id, total_found, len(all_new), errors)
            self._last_results = all_new
            self._log("INFO", f"=== Fine. Nuovi annunci: {len(all_new)} ===")
            new_listings = all_new

        except Exception as e:
            tb = traceback.format_exc()
            self._log("ERROR", f"Errore CRITICO scraping:\n{e}\n{tb}")
            # FIX: cattura i valori in variabili locali per evitare NameError nel lambda
            err_type = type(e).__name__
            err_msg = str(e)
            self.root.after(0, lambda et=err_type, em=err_msg: messagebox.showerror(
                "Errore durante lo scraping",
                f"Si e verificato un errore critico e lo scraping non e partito.\n\n"
                f"{et}: {em}\n\n"
                f"Controlla il tab Log per il traceback completo.\n\n"
                f"Suggerimento: se hai modificato file nello scraper, "
                f"verifica che non ci siano errori di sintassi."
            ))

        finally:
            self.root.after(0, self._on_job_done, new_listings)

    def _on_job_done(self, new_listings: list[dict]):
        self._is_running = False
        self._progress.stop()
        self._progress.pack_forget()
        self._run_btn.configure(state="normal", text="Avvia Scraping")
        self._status_var.set(f"Completato — {len(new_listings)} nuovi annunci")

        self._populate_tree(self._dash_tree, new_listings,
                            lambda r: (r.get("source",""), r.get("title",""),
                                       r.get("price",""), r.get("location",""),
                                       r.get("date",""), r.get("listing_type","")),
                            tag="new")
        self._new_count_lbl.configure(text=str(len(new_listings)),
                                      foreground=ACCENT2 if new_listings else TEXT_SEC)
        self._nb.select(0)
        self._refresh_stats()

        if new_listings:
            messagebox.showinfo("Scraping completato",
                                f"Trovati {len(new_listings)} nuovi annunci!\n"
                                f"Controlla la scheda Dashboard.")

    def _load_todays_listings(self):
        listings = self.db.get_listings_today()
        self._populate_tree(self._dash_tree, listings,
                            lambda r: (r.get("source",""), r.get("title",""),
                                       r.get("price",""), r.get("location",""),
                                       r.get("seen_at","")[:10], r.get("listing_type","")),
                            tag="new")
        self._new_count_lbl.configure(text=str(len(listings)))

    def _load_history(self):
        listings = self.db.get_all_listings(limit=500)
        self._populate_tree(self._hist_tree, listings,
                            lambda r: (r.get("source",""), r.get("title",""),
                                       r.get("price",""), r.get("location",""),
                                       r.get("seen_at","")[:16], r.get("listing_type","")))
        self._hist_count_lbl.configure(text=f"{len(listings)} annunci")

    def _search_history(self):
        q = self._search_var.get().strip()
        if not q:
            self._load_history()
            return
        listings = self.db.search_listings(q)
        self._populate_tree(self._hist_tree, listings,
                            lambda r: (r.get("source",""), r.get("title",""),
                                       r.get("price",""), r.get("location",""),
                                       r.get("seen_at","")[:16], r.get("listing_type","")))
        self._hist_count_lbl.configure(text=f"{len(listings)} risultati")

    def _populate_tree(self, tree: ttk.Treeview, data: list, row_fn, tag: str = ""):
        tree.delete(*tree.get_children())
        for i, item in enumerate(data):
            values = row_fn(item)
            t = tag if tag else ("even" if i % 2 == 0 else "odd")
            tree.insert("", "end", iid=str(i), values=values, tags=(t,))
        tree._data = data

    def _open_listing_url(self, event):
        self._open_url_from_tree(self._dash_tree)

    def _open_history_url(self, event):
        self._open_url_from_tree(self._hist_tree)

    def _open_url_from_tree(self, tree: ttk.Treeview):
        sel = tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        data = getattr(tree, "_data", [])
        if idx < len(data):
            url = data[idx].get("url", "")
            if url:
                webbrowser.open(url)

    def _refresh_stats(self):
        stats = self.db.get_stats()
        for w in self._stat_cards_frame.winfo_children():
            w.destroy()

        self._stat_card(self._stat_cards_frame, "Totale annunci",
                        str(stats["total"]), ACCENT)
        self._stat_card(self._stat_cards_frame, "Oggi",
                        str(stats["today"]), ACCENT2)
        for src, cnt in stats["by_source"].items():
            self._stat_card(self._stat_cards_frame, src, str(cnt), TEXT_PRI)

        runs = self.db.get_run_history()
        self._runs_tree.delete(*self._runs_tree.get_children())
        for i, r in enumerate(runs):
            tag = "even" if i % 2 == 0 else "odd"
            self._runs_tree.insert("", "end", values=(
                r.get("started_at","")[:16],
                r.get("finished_at","")[:16] if r.get("finished_at") else "—",
                r.get("total_found",""),
                r.get("new_found",""),
                r.get("errors",""),
            ), tags=(tag,))

    def _clear_db(self):
        if messagebox.askyesno("Conferma",
                               "Stai per cancellare TUTTI i dati del database.\n"
                               "L'operazione e irreversibile. Continuare?",
                               icon="warning"):
            self.db.clear_all()
            self._refresh_stats()
            self._load_history()
            self._log("WARNING", "Database svuotato dall'utente.")
            messagebox.showinfo("OK", "Database svuotato.")

    def _apply_zone(self):
        import json as _json, re as _re
        from pathlib import Path

        city = self._city_var.get().strip()
        if not city:
            messagebox.showwarning("Zona", "Inserisci la città principale "
                                            "(es. Napoli): serve per costruire "
                                            "gli URL di ricerca sui portali.")
            return
        raw = self._zona_text.get("1.0", "end").strip()
        zones = [z.strip() for z in raw.splitlines() if z.strip()]

        def slug(nome: str) -> str:
            s = nome.lower().strip()
            for a, b in (("à","a"),("è","e"),("é","e"),("ì","i"),
                         ("ò","o"),("ù","u"),("'","-")):
                s = s.replace(a, b)
            s = _re.sub(r"[^a-z0-9]+", "-", s).strip("-")
            return s

        city_slug = slug(city)
        # per la ricerca testuale (es. Subito, che cerca a livello nazionale
        # con ?q=<termine>): con UNA sola zona ha senso cercare quella
        # direttamente (più mirato); con zero o PIÙ zone si cerca sulla
        # città intera e si lascia il filtro post-scraping selezionare i
        # quartieri giusti — altrimenti con più quartieri configurati la
        # ricerca testuale ne userebbe solo il primo, perdendo gli altri.
        text_search_term = zones[0] if len(zones) == 1 else city

        try:
            sites_path = Path("config/sites.json")
            sites = _json.loads(sites_path.read_text(encoding="utf-8"))
            updated = 0
            for site in sites:
                pattern = site.get("url_pattern")
                if not pattern:
                    continue
                new_urls = {}
                for lt, tmpl in pattern.items():
                    if "?q=" in tmpl or "q={zona}" in tmpl:
                        new_urls[lt] = tmpl.replace(
                            "{zona}", text_search_term.replace(" ", "+"))
                    else:
                        new_urls[lt] = tmpl.replace("{zona}", city_slug)
                site["search_urls"] = new_urls
                updated += 1
            sites_path.write_text(
                _json.dumps(sites, ensure_ascii=False, indent=2), encoding="utf-8")

            self.config["main_city"] = city
            self.config["search_zones"] = zones
            from config.defaults import save_settings
            save_settings(self.config)

            self._zona_status.configure(
                text=f"OK — {updated} fonti su «{city}»"
                     + (f", filtro su {len(zones)} zone" if zones else ""))
            self._log("INFO", f"Città applicata: {city} (slug: {city_slug}) → "
                              f"{updated} fonti. Zone di filtro: {zones}")
            note_zone = (f"I risultati verranno poi filtrati sui quartieri: "
                        f"{', '.join(zones)}." if zones else
                        "Nessun quartiere impostato: verranno mostrati tutti "
                        "gli annunci della città.")
            messagebox.showinfo(
                "Zona applicata",
                f"URL di ricerca impostati su «{city}» per {updated} fonti.\n\n"
                f"{note_zone}")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile applicare la zona: {e}")

    def _save_config(self):
        try:
            kw_raw = self._geo_kw_text.get("1.0", "end").strip()
            keywords = [k.strip() for k in kw_raw.splitlines() if k.strip()]

            self.config["geo_filter"]["mode"] = self._geo_mode_var.get()
            self.config["geo_filter"]["keywords"] = keywords

            self.config["filters"]["min_price"] = int(self._pmin_var.get() or 0)
            self.config["filters"]["max_price"] = int(self._pmax_var.get() or 9999999)
            excl = [k.strip() for k in self._exclude_var.get().split(",") if k.strip()]
            self.config["filters"]["keywords_exclude"] = excl

            self.config["schedule"]["time"] = self._sched_time_var.get()
            self.config["schedule"]["run_on_start"] = self._sched_run_start.get()

            self.config["notifications"]["enabled"] = self._notif_enabled.get()
            self.config["notifications"]["email"]["enabled"] = self._email_enabled.get()
            for k, var in self._email_vars.items():
                self.config["notifications"]["email"][k] = var.get()
            self.config["notifications"]["telegram"]["enabled"] = self._tg_enabled.get()
            for k, var in self._tg_vars.items():
                self.config["notifications"]["telegram"][k] = var.get()

            from config.defaults import save_settings
            save_settings(self.config)

            self._log("INFO", "Configurazione salvata.")
            messagebox.showinfo("Salvato", "Configurazione aggiornata e salvata.")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile salvare: {e}")

    def _export_json(self):
        if not self._last_results:
            messagebox.showinfo("Nessun dato", "Nessun risultato da esportare.\nEsegui prima lo scraping.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            initialfile=f"annunci_{datetime.now().strftime('%Y%m%d')}.json"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._last_results, f, ensure_ascii=False, indent=2, default=str)
            messagebox.showinfo("Esportato", f"Salvato in:\n{path}")

    def _toggle_scheduler(self):
        if not hasattr(self, "_sched_running"):
            self._sched_running = False

        if self._sched_running:
            self._sched_running = False
            self._scheduler_btn.configure(text="Avvia Scheduler", style="Success.TButton")
            self._sched_status_lbl.configure(text="Fermato", foreground=DANGER)
            self._log("INFO", "Scheduler fermato.")
        else:
            self._sched_running = True
            self._scheduler_btn.configure(text="Ferma Scheduler", style="Danger.TButton")
            sched_time = self._sched_time_var.get()
            self._sched_status_lbl.configure(
                text=f"Attivo — esecuzione giornaliera alle {sched_time}", foreground=SUCCESS)
            self._log("INFO", f"Scheduler avviato — esecuzione alle {sched_time}")

            def sched_loop():
                import schedule as sched
                sched.clear()
                sched.every().day.at(sched_time).do(self._start_job)
                while self._sched_running:
                    sched.run_pending()
                    import time
                    time.sleep(30)

            threading.Thread(target=sched_loop, daemon=True).start()

    def _setup_log_handler(self):
        import logging

        class GuiHandler(logging.Handler):
            def __init__(self_, queue_):
                super().__init__()
                self_._q = queue_
            def emit(self_, record):
                self_._q.put((record.levelname, self_.format(record)))

        handler = GuiHandler(self._log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)-20s %(message)s",
                                               "%H:%M:%S"))
        logging.getLogger("real_estate_monitor").addHandler(handler)
        self._poll_log()

    def _poll_log(self):
        try:
            while True:
                level, msg = self._log_queue.get_nowait()
                self._append_log(level, msg)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_log)

    def _log(self, level: str, message: str):
        self._log_queue.put((level, message))

    def _append_log(self, level: str, message: str):
        self._log_text.configure(state="normal")
        tag = level if level in ("INFO","WARNING","ERROR","DEBUG","CRITICAL") else "INFO"
        self._log_text.insert("end", message + "\n", tag)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            initialfile=f"log_{datetime.now().strftime('%Y%m%d')}.txt"
        )
        if path:
            content = self._log_text.get("1.0", "end")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
