from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .catalogs import (
    CatalogFinding,
    compare_locale_catalogs,
    findings_as_json,
    load_json_catalog,
    write_json_atomic,
)
from .paths import default_data_root

ISSUE_LABELS = {
    "missing_translation_key": "Eksik çeviri anahtarı",
    "orphan_translation_key": "Kaynakta olmayan anahtar",
    "placeholder_mismatch": "Değişken yapısı bozulmuş",
    "markup_mismatch": "HTML/XML yapısı bozulmuş",
    "empty_translation": "Boş çeviri",
    "untranslated_entry": "Çevrilmemiş metin",
    "whitespace_difference": "Boşluk yapısı farklı",
    "newline_mismatch": "Satır sonu yapısı farklı",
    "unexpected_bidi_control": "Tehlikeli yön karakteri",
    "unexpected_invisible_character": "Görünmez karakter",
    "invalid_unicode_surrogate": "Geçersiz Unicode",
}

EXPLANATION_LABELS = {
    "missing_translation_key": "Kaynak anahtar hedef dil dosyasında bulunmuyor.",
    "orphan_translation_key": "Hedef dosyada kaynak dilde bulunmayan bir anahtar var.",
    "empty_translation": "Hedef metin boş bırakılmış.",
    "untranslated_entry": "Hedef metin kaynak metinle tamamen aynı.",
    "markup_mismatch": "Kaynak ve hedef metnin HTML/XML etiket yapıları eşleşmiyor.",
    "unbalanced_markup": "Hedef metindeki HTML/XML etiketleri dengeli kapanmıyor.",
    "newline_mismatch": "Kaynak ve hedef metnin satır sonu sayıları eşleşmiyor.",
    "whitespace_difference": "Metnin başındaki veya sonundaki boşluk yapısı değişmiş.",
    "unexpected_bidi_control": "Hedef metin beklenmeyen yönlendirme karakterleri ekliyor.",
    "unexpected_invisible_character": "Hedef metin beklenmeyen görünmez karakterler ekliyor.",
    "invalid_unicode_surrogate": "Hedef metin geçersiz Unicode kod noktaları içeriyor.",
}


class ScannerApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("L10n Sentinel — Çeviri Güvenlik Taraması")
        self.root.geometry("1440x900")
        self.root.minsize(1180, 760)

        self.colors = {
            "page": "#F4F7FB",
            "surface": "#FFFFFF",
            "sidebar": "#0B1220",
            "sidebar_active": "#172554",
            "text": "#152033",
            "muted": "#64748B",
            "border": "#DCE4EF",
            "accent": "#2864DC",
            "accent_dark": "#1D4ED8",
            "hero": "#102A56",
            "success": "#07966D",
            "warning": "#D97706",
            "danger": "#D9343E",
        }
        self.root.configure(background=self.colors["page"])

        self.source_path: Path | None = None
        self.target_paths: list[Path] = []
        self.findings: list[CatalogFinding] = []
        self.source_label_var = tk.StringVar(value="Henüz kaynak dosya seçilmedi")
        self.target_label_var = tk.StringVar(value="Henüz hedef dosya seçilmedi")
        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="Tümü")
        self.result_hint_var = tk.StringVar(
            value="Dosyaları seçip taramayı başlattığınızda bulgular burada listelenir."
        )
        self.status_var = tk.StringVar(value="Hazır")
        self.metric_vars = {
            "files": tk.StringVar(value="0"),
            "keys": tk.StringVar(value="0"),
            "errors": tk.StringVar(value="0"),
            "warnings": tk.StringVar(value="0"),
        }

        self._configure_styles()
        self._build_ui()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.colors["page"])
        style.configure(
            "TButton",
            font=("Segoe UI Semibold", 9),
            padding=(14, 9),
            borderwidth=0,
        )
        style.configure(
            "Primary.TButton",
            background=self.colors["accent"],
            foreground="#FFFFFF",
        )
        style.map(
            "Primary.TButton",
            background=[("active", self.colors["accent_dark"]), ("pressed", "#1E40AF")],
        )
        style.configure(
            "Soft.TButton",
            background="#E8EEF8",
            foreground="#1E3A5F",
        )
        style.map("Soft.TButton", background=[("active", "#DCE7F6")])
        style.configure(
            "Treeview",
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground=self.colors["text"],
            rowheight=34,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#EDF2F8",
            foreground="#42526A",
            font=("Segoe UI Semibold", 9),
            padding=(8, 9),
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", "#DCE9FF")],
            foreground=[("selected", "#173B79")],
        )
        style.configure(
            "TEntry",
            fieldbackground="#FFFFFF",
            bordercolor=self.colors["border"],
            padding=8,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#FFFFFF",
            bordercolor=self.colors["border"],
            padding=7,
        )

    def _build_ui(self) -> None:
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self) -> None:
        sidebar = tk.Frame(self.root, background=self.colors["sidebar"], width=238)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        brand = tk.Frame(sidebar, background=self.colors["sidebar"])
        brand.pack(fill="x", padx=22, pady=(24, 32))
        badge = tk.Label(
            brand,
            text="LS",
            background=self.colors["accent"],
            foreground="#FFFFFF",
            font=("Segoe UI Semibold", 13),
            width=3,
            height=2,
        )
        badge.pack(side="left")
        brand_text = tk.Frame(brand, background=self.colors["sidebar"])
        brand_text.pack(side="left", padx=10)
        tk.Label(
            brand_text,
            text="L10n Sentinel",
            background=self.colors["sidebar"],
            foreground="#FFFFFF",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        tk.Label(
            brand_text,
            text="Locale integrity",
            background=self.colors["sidebar"],
            foreground="#7F93AF",
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        self._nav_item(sidebar, "01", "Yeni tarama", active=True)
        self._nav_item(sidebar, "02", "Nasıl çalışır?", command=self.show_how_it_works)
        self._nav_item(sidebar, "03", "CI kurulumu", command=self.show_ci_setup)

        note = tk.Frame(sidebar, background="#111D32")
        note.pack(side="bottom", fill="x", padx=16, pady=16)
        tk.Label(
            note,
            text="GİZLİLİK",
            background="#111D32",
            foreground="#7DD3FC",
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", padx=14, pady=(12, 4))
        tk.Label(
            note,
            text="Dosyalarınız cihazınızdan çıkmaz.\nHesap, bulut veya API anahtarı gerekmez.",
            background="#111D32",
            foreground="#B8C6D9",
            font=("Segoe UI", 8),
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 10))
        tk.Label(
            note,
            text=f"Açık kaynak • v{__version__}",
            background="#111D32",
            foreground="#6F849F",
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=14, pady=(0, 12))

    def _nav_item(
        self,
        parent: tk.Widget,
        number: str,
        text: str,
        *,
        active: bool = False,
        command: object | None = None,
    ) -> None:
        background = self.colors["sidebar_active"] if active else self.colors["sidebar"]
        foreground = "#FFFFFF" if active else "#91A3BA"
        item = tk.Frame(parent, background=background, height=48)
        item.pack(fill="x", padx=12, pady=3)
        item.pack_propagate(False)
        number_label = tk.Label(
            item,
            text=number,
            background=background,
            foreground="#60A5FA" if active else "#52657D",
            font=("Segoe UI Semibold", 8),
        )
        number_label.pack(side="left", padx=(14, 10))
        text_label = tk.Label(
            item,
            text=text,
            background=background,
            foreground=foreground,
            font=("Segoe UI Semibold", 9),
        )
        text_label.pack(side="left")
        if command is not None:
            for widget in (item, number_label, text_label):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _event, action=command: action())

    def _show_info_window(self, title: str, eyebrow: str, heading: str, body: str) -> tk.Toplevel:
        window = tk.Toplevel(self.root)
        window.title(f"{title} — L10n Sentinel")
        window.geometry("760x600")
        window.minsize(680, 520)
        window.configure(background=self.colors["page"])
        window.transient(self.root)

        header = tk.Frame(window, background=self.colors["hero"], height=150)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=eyebrow,
            background=self.colors["hero"],
            foreground="#8FC1FF",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", padx=34, pady=(28, 8))
        tk.Label(
            header,
            text=heading,
            background=self.colors["hero"],
            foreground="#FFFFFF",
            font=("Segoe UI Semibold", 20),
        ).pack(anchor="w", padx=34)

        content = tk.Frame(window, background=self.colors["surface"])
        content.pack(fill="both", expand=True, padx=28, pady=24)
        tk.Label(
            content,
            text=body,
            background=self.colors["surface"],
            foreground=self.colors["text"],
            font=("Segoe UI", 11),
            justify="left",
            anchor="nw",
            wraplength=650,
        ).pack(fill="x", padx=24, pady=24)
        ttk.Button(content, text="Kapat", command=window.destroy).pack(
            anchor="e", padx=24, pady=(0, 22)
        )
        return window

    def show_how_it_works(self) -> tk.Toplevel:
        return self._show_info_window(
            "Nasıl çalışır?",
            "ÜÇ ADIMDA ÇEVİRİ GÜVENLİĞİ",
            "Kullanıcının göreceği hatayı yayınlanmadan yakalayın",
            "1  Kaynak dil dosyanızı seçin\n"
            "    Örneğin uygulamanızın en.json dosyası.\n\n"
            "2  Bir veya daha fazla çeviri dosyası ekleyin\n"
            "    tr.json, de.json ve diğer hedef dilleri birlikte tarayın.\n\n"
            "3  Kritik sorunları düzeltin\n"
            "    Eksik anahtarları, bozuk {name} değişkenlerini, HTML/XML "
            "uyuşmazlıklarını ve riskli Unicode karakterlerini görün.\n\n"
            "L10n Sentinel dosyalarınızı değiştirmez ve internete göndermez. "
            "Yalnızca karşılaştırır ve güvenli, uygulanabilir bir rapor üretir.",
        )

    def show_ci_setup(self) -> tk.Toplevel:
        window = self._show_info_window(
            "CI kurulumu",
            "HER PULL REQUEST'TE OTOMATİK KONTROL",
            "Aynı güvenlik kontrolünü GitHub Actions'a taşıyın",
            "Aşağıdaki adımı mevcut workflow dosyanıza ekleyin. Hatalı bir "
            "çeviri bulunduğunda kontrol başarısız olur ve sorun kullanıcıya "
            "ulaşmadan pull request üzerinde görünür.",
        )
        content = window.winfo_children()[1]
        close_button = content.winfo_children()[-1]
        code = tk.Text(
            content,
            height=8,
            background="#0B1220",
            foreground="#DCE8F7",
            insertbackground="#FFFFFF",
            relief="flat",
            font=("Cascadia Mono", 9),
            padx=16,
            pady=14,
            wrap="none",
        )
        code.insert(
            "1.0",
            "- uses: ahmetmusab42-stack/l10n-sentinel@v0.3.1\n"
            "  with:\n"
            "    source: locales/en.json\n"
            "    targets: locales/tr.json locales/de.json\n",
        )
        code.configure(state="disabled")
        code.pack(fill="x", padx=24, before=close_button)
        return window

    def _build_main(self) -> None:
        main = tk.Frame(self.root, background=self.colors["page"])
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)
        self._build_topbar(main)
        self._build_hero(main)
        self._build_scan_flow(main)
        self._build_metrics(main)
        self._build_results(main)
        self._build_status(main)

    def _build_topbar(self, parent: tk.Widget) -> None:
        topbar = tk.Frame(parent, background=self.colors["surface"], height=58)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        tk.Label(
            topbar,
            text="YENİ TARAMA",
            background=self.colors["surface"],
            foreground="#52637A",
            font=("Segoe UI Semibold", 9),
        ).pack(side="left", padx=26)
        tk.Label(
            topbar,
            text="ÇEVRİMDIŞI",
            background="#E8F8F2",
            foreground=self.colors["success"],
            font=("Segoe UI Semibold", 8),
            padx=12,
            pady=6,
        ).pack(side="right", padx=26)

    def _build_hero(self, parent: tk.Widget) -> None:
        hero = tk.Frame(parent, background=self.colors["hero"], height=130)
        hero.grid(row=1, column=0, sticky="ew", padx=24, pady=(20, 14))
        hero.grid_propagate(False)
        text = tk.Frame(hero, background=self.colors["hero"])
        text.pack(side="left", fill="both", expand=True, padx=24, pady=22)
        tk.Label(
            text,
            text="Bozuk çeviriler kullanıcıya ulaşmadan yakalayın.",
            background=self.colors["hero"],
            foreground="#FFFFFF",
            font=("Segoe UI Semibold", 18),
        ).pack(anchor="w")
        tk.Label(
            text,
            text=(
                "Ana dil dosyanızı çevirilerle karşılaştırır; eksik anahtarları, bozulan "
                "değişkenleri ve riskli Unicode karakterlerini saniyeler içinde gösterir."
            ),
            background=self.colors["hero"],
            foreground="#BFD2EE",
            font=("Segoe UI", 10),
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        tk.Label(
            hero,
            text="JSON  •  ARB  •  SARIF  •  GITHUB ACTIONS",
            background="#1A3B72",
            foreground="#CFE0FA",
            font=("Segoe UI Semibold", 8),
            padx=16,
            pady=8,
        ).pack(side="right", padx=22)

    def _build_scan_flow(self, parent: tk.Widget) -> None:
        flow = tk.Frame(parent, background=self.colors["page"])
        flow.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 14))
        flow.columnconfigure(0, weight=1)
        flow.columnconfigure(2, weight=1)
        flow.columnconfigure(4, weight=1)
        self._file_card(
            flow,
            column=0,
            step="1",
            title="Ana dil dosyası",
            description="Örneğin en.json veya app_en.arb",
            variable=self.source_label_var,
            button_text="Kaynak dosyayı seç",
            command=self.choose_source,
        )
        self._flow_arrow(flow, 1)
        self._file_card(
            flow,
            column=2,
            step="2",
            title="Çeviri dosyaları",
            description="Bir veya birden fazla hedef dil seçin",
            variable=self.target_label_var,
            button_text="Hedef dosyaları seç",
            command=self.choose_targets,
        )
        self._flow_arrow(flow, 3)
        self._scan_card(flow, 4)

    def _file_card(
        self,
        parent: tk.Widget,
        *,
        column: int,
        step: str,
        title: str,
        description: str,
        variable: tk.StringVar,
        button_text: str,
        command: object,
    ) -> None:
        card = tk.Frame(
            parent,
            background=self.colors["surface"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        card.grid(row=0, column=column, sticky="nsew")
        header = tk.Frame(card, background=self.colors["surface"])
        header.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(
            header,
            text=step,
            background="#E7EFFF",
            foreground=self.colors["accent"],
            font=("Segoe UI Semibold", 9),
            width=3,
            height=1,
        ).pack(side="left")
        tk.Label(
            header,
            text=title,
            background=self.colors["surface"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(side="left", padx=9)
        tk.Label(
            card,
            text=description,
            background=self.colors["surface"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16)
        tk.Label(
            card,
            textvariable=variable,
            background="#F6F8FC",
            foreground="#415169",
            font=("Segoe UI", 8),
            anchor="w",
            padx=10,
            pady=8,
        ).pack(fill="x", padx=16, pady=(10, 8))
        ttk.Button(card, text=button_text, style="Soft.TButton", command=command).pack(
            anchor="e", padx=16, pady=(0, 14)
        )

    def _flow_arrow(self, parent: tk.Widget, column: int) -> None:
        tk.Label(
            parent,
            text="→",
            background=self.colors["page"],
            foreground="#90A1B8",
            font=("Segoe UI", 18),
        ).grid(row=0, column=column, padx=8)

    def _scan_card(self, parent: tk.Widget, column: int) -> None:
        card = tk.Frame(
            parent,
            background="#F0F5FF",
            highlightthickness=1,
            highlightbackground="#BFD1F5",
        )
        card.grid(row=0, column=column, sticky="nsew")
        tk.Label(
            card,
            text="3",
            background="#DCE8FF",
            foreground=self.colors["accent"],
            font=("Segoe UI Semibold", 9),
            width=3,
        ).pack(anchor="w", padx=16, pady=(14, 6))
        tk.Label(
            card,
            text="Sözleşmeyi doğrula",
            background="#F0F5FF",
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", padx=16)
        tk.Label(
            card,
            text="Dosyalar salt okunur taranır; içerik değiştirilmez.",
            background="#F0F5FF",
            foreground=self.colors["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16, pady=(4, 12))
        ttk.Button(
            card,
            text="Taramayı başlat",
            style="Primary.TButton",
            command=self.run_scan,
        ).pack(fill="x", padx=16, pady=(0, 8))
        ttk.Button(
            card,
            text="Örnek dosyalarla dene",
            style="Soft.TButton",
            command=self.load_demo,
        ).pack(fill="x", padx=16, pady=(0, 14))

    def _build_metrics(self, parent: tk.Widget) -> None:
        metrics = tk.Frame(parent, background=self.colors["page"])
        metrics.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 14))
        for index in range(4):
            metrics.columnconfigure(index, weight=1)
        cards = (
            ("files", "TARANAN DOSYA", self.colors["accent"]),
            ("keys", "KAYNAK ANAHTAR", self.colors["success"]),
            ("errors", "KRİTİK HATA", self.colors["danger"]),
            ("warnings", "UYARI", self.colors["warning"]),
        )
        for index, (name, caption, color) in enumerate(cards):
            card = tk.Frame(
                metrics,
                background=self.colors["surface"],
                highlightthickness=1,
                highlightbackground=self.colors["border"],
            )
            card.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=(0 if index == 0 else 5, 0 if index == 3 else 5),
            )
            tk.Frame(card, background=color, width=4).pack(side="left", fill="y")
            tk.Label(
                card,
                textvariable=self.metric_vars[name],
                background=self.colors["surface"],
                foreground=self.colors["text"],
                font=("Segoe UI Semibold", 18),
            ).pack(side="left", padx=(13, 8), pady=10)
            tk.Label(
                card,
                text=caption,
                background=self.colors["surface"],
                foreground=self.colors["muted"],
                font=("Segoe UI Semibold", 8),
            ).pack(side="left")

    def _build_results(self, parent: tk.Widget) -> None:
        panel = tk.Frame(
            parent,
            background=self.colors["surface"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        panel.grid(row=4, column=0, sticky="nsew", padx=24, pady=(0, 12))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        titlebar = tk.Frame(panel, background=self.colors["surface"])
        titlebar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 8))
        tk.Label(
            titlebar,
            text="Tarama sonuçları",
            background=self.colors["surface"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 12),
        ).pack(side="left")
        ttk.Button(
            titlebar,
            text="JSON raporunu dışa aktar",
            style="Soft.TButton",
            command=self.export_report,
        ).pack(side="right")

        toolbar = tk.Frame(panel, background=self.colors["surface"])
        toolbar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 9))
        toolbar.columnconfigure(0, weight=1)
        search = ttk.Entry(toolbar, textvariable=self.search_var)
        search.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        search.bind("<KeyRelease>", lambda _event: self.render_findings())
        severity = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("Tümü", "Hatalar", "Uyarılar"),
            state="readonly",
            width=14,
        )
        severity.grid(row=0, column=1)
        severity.bind("<<ComboboxSelected>>", lambda _event: self.render_findings())

        self.results_tree = ttk.Treeview(
            panel,
            columns=("severity", "file", "line", "key", "issue", "explanation"),
            show="headings",
            selectmode="browse",
        )
        columns = (
            ("severity", "SEVİYE", 80),
            ("file", "DOSYA", 145),
            ("line", "SATIR", 55),
            ("key", "ANAHTAR", 190),
            ("issue", "BULGU", 190),
            ("explanation", "AÇIKLAMA", 430),
        )
        for name, heading, width in columns:
            self.results_tree.heading(name, text=heading)
            self.results_tree.column(name, width=width, anchor="w")
        self.results_tree.grid(row=2, column=0, sticky="nsew", padx=(16, 0), pady=(0, 8))
        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=self.results_tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns", padx=(0, 14), pady=(0, 8))
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        self.results_tree.tag_configure("error", foreground=self.colors["danger"])
        self.results_tree.tag_configure("warning", foreground=self.colors["warning"])
        tk.Label(
            panel,
            textvariable=self.result_hint_var,
            background=self.colors["surface"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

    def _build_status(self, parent: tk.Widget) -> None:
        status = tk.Frame(parent, background="#E9EEF5", height=30)
        status.grid(row=5, column=0, sticky="ew")
        status.grid_propagate(False)
        tk.Label(
            status,
            textvariable=self.status_var,
            background="#E9EEF5",
            foreground="#53647A",
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="both", expand=True, padx=24)

    def choose_source(self) -> None:
        selected = filedialog.askopenfilename(
            title="Ana dil dosyasını seçin",
            filetypes=[("JSON ve ARB", "*.json *.arb"), ("Tüm dosyalar", "*.*")],
        )
        if not selected:
            return
        self.source_path = Path(selected)
        self.source_label_var.set(self.source_path.name)
        self.status_var.set(f"Kaynak seçildi: {self.source_path.name}")

    def choose_targets(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Çeviri dosyalarını seçin",
            filetypes=[("JSON ve ARB", "*.json *.arb"), ("Tüm dosyalar", "*.*")],
        )
        if not selected:
            return
        self.target_paths = [Path(item) for item in selected]
        names = ", ".join(path.name for path in self.target_paths[:3])
        if len(self.target_paths) > 3:
            names += f" +{len(self.target_paths) - 3} dosya"
        self.target_label_var.set(names)
        self.status_var.set(f"{len(self.target_paths)} hedef dosya seçildi")

    def load_demo(self) -> None:
        demo_dir = default_data_root() / "demo"
        source_path = demo_dir / "en.json"
        target_path = demo_dir / "tr.json"
        demo_dir.mkdir(parents=True, exist_ok=True)
        source_path.write_text(
            json.dumps(
                {
                    "nav": {"home": "Home", "account": "Account"},
                    "welcome": "Welcome, {name}!",
                    "actions": {"save": "Save", "cancel": "Cancel"},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        target_path.write_text(
            json.dumps(
                {
                    "nav": {"home": "Ana Sayfa"},
                    "welcome": "Hoş geldin!",
                    "actions": {"save": "Kaydet", "cancel": "Cancel"},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.source_path = source_path
        self.target_paths = [target_path]
        self.source_label_var.set("en.json — örnek kaynak")
        self.target_label_var.set("tr.json — örnek çeviri")
        self.run_scan()

    def run_scan(self) -> None:
        if self.source_path is None or not self.target_paths:
            messagebox.showinfo(
                "Dosyalar eksik",
                "Taramadan önce bir ana dil dosyası ve en az bir çeviri dosyası seçin.",
            )
            return
        self.status_var.set("Dosyalar taranıyor…")
        self.root.update_idletasks()
        try:
            source_messages = load_json_catalog(self.source_path)
            findings: list[CatalogFinding] = []
            for target_path in self.target_paths:
                target_messages = load_json_catalog(target_path)
                findings.extend(
                    compare_locale_catalogs(
                        source_messages,
                        target_messages,
                        source_path=self.source_path,
                        target_path=target_path,
                    )
                )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Tarama tamamlanamadı", str(exc))
            self.status_var.set("Tarama başarısız — dosya biçimini kontrol edin")
            return

        severity_order = {"error": 0, "warning": 1}
        self.findings = sorted(
            findings,
            key=lambda item: (
                severity_order.get(item.severity, 2),
                Path(item.path).name,
                item.line,
                item.key,
            ),
        )
        errors = sum(1 for item in findings if item.severity == "error")
        warnings = sum(1 for item in findings if item.severity == "warning")
        self.metric_vars["files"].set(str(1 + len(self.target_paths)))
        self.metric_vars["keys"].set(str(len(source_messages)))
        self.metric_vars["errors"].set(str(errors))
        self.metric_vars["warnings"].set(str(warnings))
        self.render_findings()
        if findings:
            self.result_hint_var.set(
                f"Tarama tamamlandı: {errors} kritik hata, {warnings} uyarı. "
                "Dosyalarda hiçbir değişiklik yapılmadı."
            )
            self.status_var.set("Tarama tamamlandı — bulguları inceleyin")
        else:
            self.result_hint_var.set(
                "Tebrikler — kaynak ve hedef dosyalar arasında sözleşme ihlali bulunamadı."
            )
            self.status_var.set("Tarama başarılı — sorun bulunamadı")

    def render_findings(self) -> None:
        self.results_tree.delete(*self.results_tree.get_children())
        query = self.search_var.get().strip().casefold()
        severity_filter = self.severity_var.get()
        for index, finding in enumerate(self.findings):
            if severity_filter == "Hatalar" and finding.severity != "error":
                continue
            if severity_filter == "Uyarılar" and finding.severity != "warning":
                continue
            issue_label = ISSUE_LABELS.get(finding.issue_type, finding.issue_type)
            explanation = self._localized_explanation(finding)
            haystack = " ".join((finding.key, finding.path, issue_label, explanation)).casefold()
            if query and query not in haystack:
                continue
            self.results_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    "HATA" if finding.severity == "error" else "UYARI",
                    Path(finding.path).name,
                    finding.line,
                    finding.key,
                    issue_label,
                    explanation,
                ),
                tags=(finding.severity,),
            )

    def _localized_explanation(self, finding: CatalogFinding) -> str:
        if finding.issue_type == "placeholder_mismatch":
            detail = finding.explanation
            detail = detail.replace("Placeholder mismatch detected", "Değişkenler eşleşmiyor")
            detail = detail.replace("missing:", "eksik:").replace("extra:", "fazladan:")
            return detail
        return EXPLANATION_LABELS.get(finding.issue_type, finding.explanation)

    def export_report(self) -> None:
        if not self.findings:
            messagebox.showinfo("Rapor", "Dışa aktarılacak bir tarama sonucu bulunmuyor.")
            return
        selected = filedialog.asksaveasfilename(
            title="Tarama raporunu kaydedin",
            defaultextension=".json",
            filetypes=[("JSON raporu", "*.json")],
        )
        if not selected:
            return
        payload = {
            "schema_version": 1,
            "source": str(self.source_path),
            "targets": [str(path) for path in self.target_paths],
            "findings": findings_as_json(self.findings),
        }
        write_json_atomic(Path(selected), payload)
        self.status_var.set(f"Rapor kaydedildi: {Path(selected).name}")

    def run(self) -> None:
        self.root.mainloop()


def launch_scanner_gui() -> None:
    ScannerApp().run()
