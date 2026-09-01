from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .formats import load_localization_document
from .paths import default_data_root
from .qa import analyze_entries
from .storage import ProjectRepository
from .workflows import LocalizationWorkflow


class WorkbenchApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("L10n Sentinel — Yerelleştirme Çalışma Alanı")
        self.root.geometry("1380x860")
        self.root.minsize(1180, 740)

        self.colors = {
            "canvas": "#F3F6FA",
            "panel": "#FFFFFF",
            "sidebar": "#111827",
            "sidebar_muted": "#94A3B8",
            "text": "#172033",
            "muted": "#64748B",
            "border": "#DCE3EC",
            "accent": "#2563EB",
            "accent_hover": "#1D4ED8",
            "success": "#059669",
            "warning": "#D97706",
            "danger": "#DC2626",
        }
        self.root.configure(background=self.colors["canvas"])

        self.repository = ProjectRepository(default_data_root() / "l10n-sentinel.sqlite3")
        self.workflow = LocalizationWorkflow(self.repository)

        self.current_project_slug: str | None = None
        self.all_entries: list[dict[str, object]] = []
        self.visible_entries: list[dict[str, object]] = []
        self.current_issues = []
        self.selected_entry_id: str | None = None

        self.search_var = tk.StringVar()
        self.format_var = tk.StringVar(value="json")
        self.filter_untranslated = tk.BooleanVar(value=False)
        self.filter_qa = tk.BooleanVar(value=False)
        self.project_slug_var = tk.StringVar()
        self.project_name_var = tk.StringVar()
        self.project_source_var = tk.StringVar(value="en")
        self.project_target_var = tk.StringVar(value="tr")

        self.stats_vars = {
            "total": tk.StringVar(value="0"),
            "translated": tk.StringVar(value="0"),
            "untranslated": tk.StringVar(value="0"),
            "qa": tk.StringVar(value="0"),
        }
        self.status_var = tk.StringVar(value="Hazır — veriler yalnızca bu bilgisayarda işlenir")
        self.project_title_var = tk.StringVar(value="Bir proje seçin")
        self.project_subtitle_var = tk.StringVar(
            value="Çeviri akışını ve kalite bulgularını yönetin"
        )

        self._configure_styles()
        self._build_ui()
        self.refresh_projects()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.colors["canvas"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure(
            "TLabel",
            background=self.colors["canvas"],
            foreground=self.colors["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Panel.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Section.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "Muted.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Stat.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 22),
        )
        style.configure(
            "StatCaption.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "TButton",
            font=("Segoe UI Semibold", 9),
            padding=(12, 8),
            borderwidth=0,
        )
        style.configure(
            "Accent.TButton",
            background=self.colors["accent"],
            foreground="#FFFFFF",
        )
        style.map(
            "Accent.TButton",
            background=[("active", self.colors["accent_hover"]), ("pressed", "#1E40AF")],
        )
        style.configure(
            "Secondary.TButton",
            background="#E8EEF7",
            foreground=self.colors["text"],
        )
        style.map("Secondary.TButton", background=[("active", "#DCE6F3")])
        style.configure(
            "TEntry",
            fieldbackground="#FFFFFF",
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            lightcolor=self.colors["border"],
            darkcolor=self.colors["border"],
            padding=7,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#FFFFFF",
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            padding=6,
        )
        style.configure(
            "Treeview",
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground=self.colors["text"],
            rowheight=31,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#EEF2F7",
            foreground="#475569",
            font=("Segoe UI Semibold", 9),
            padding=(8, 8),
            borderwidth=0,
        )
        style.map(
            "Treeview", background=[("selected", "#DBEAFE")], foreground=[("selected", "#1E3A8A")]
        )
        style.configure("TCheckbutton", background=self.colors["panel"], font=("Segoe UI", 9))

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_header()
        content = ttk.Frame(self.root, padding=(18, 16, 18, 12))
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(content, background=self.colors["sidebar"], width=292)
        self.sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 16))
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)
        self._build_sidebar()

        workspace = ttk.Frame(content)
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(2, weight=3)
        workspace.rowconfigure(3, weight=2)
        self._build_workspace_heading(workspace)
        self._build_stats(workspace)
        self._build_table_area(workspace)
        self._build_lower_area(workspace)

        status = tk.Frame(self.root, background="#E9EEF5", height=34)
        status.grid(row=2, column=0, sticky="ew")
        status.grid_propagate(False)
        tk.Label(
            status,
            textvariable=self.status_var,
            anchor="w",
            background="#E9EEF5",
            foreground="#475569",
            font=("Segoe UI", 9),
        ).pack(fill="both", expand=True, padx=18)

    def _build_header(self) -> None:
        header = tk.Frame(self.root, background="#0B1220", height=76)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        brand = tk.Frame(header, background="#0B1220")
        brand.pack(side="left", fill="y", padx=20)
        tk.Label(
            brand,
            text="L10n SENTINEL",
            background="#0B1220",
            foreground="#FFFFFF",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w", pady=(13, 0))
        tk.Label(
            brand,
            text="Yerelleştirme bütünlüğü • çevrimdışı ve açık kaynak",
            background="#0B1220",
            foreground="#94A3B8",
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="LOCAL  •  PRIVATE  •  CI READY",
            background="#172554",
            foreground="#BFDBFE",
            font=("Segoe UI Semibold", 9),
            padx=14,
            pady=7,
        ).pack(side="right", padx=22)

    def _sidebar_label(self, parent: tk.Widget, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            background=self.colors["sidebar"],
            foreground="#E2E8F0",
            font=("Segoe UI Semibold", 10),
            anchor="w",
        )

    def _build_sidebar(self) -> None:
        pad = tk.Frame(self.sidebar, background=self.colors["sidebar"])
        pad.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        pad.columnconfigure(0, weight=1)

        self._sidebar_label(pad, "PROJE").grid(row=0, column=0, sticky="ew")
        self.project_combo = ttk.Combobox(pad, state="readonly")
        self.project_combo.grid(row=1, column=0, sticky="ew", pady=(7, 8))
        self.project_combo.bind("<<ComboboxSelected>>", lambda _event: self.open_selected_project())
        buttons = tk.Frame(pad, background=self.colors["sidebar"])
        buttons.grid(row=2, column=0, sticky="ew")
        buttons.columnconfigure((0, 1), weight=1)
        ttk.Button(
            buttons, text="Projeyi Aç", style="Accent.TButton", command=self.open_selected_project
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(
            buttons, text="Yenile", style="Secondary.TButton", command=self.refresh_projects
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Button(
            pad,
            text="Örnek veriyi yükle",
            style="Secondary.TButton",
            command=self.create_sample_project,
        ).grid(row=3, column=0, sticky="ew", pady=(8, 20))

        self._sidebar_label(pad, "YENİ PROJE").grid(row=4, column=0, sticky="ew")
        fields = (
            ("Kısa ad", self.project_slug_var),
            ("Proje adı", self.project_name_var),
            ("Kaynak dil", self.project_source_var),
            ("Hedef dil", self.project_target_var),
        )
        row = 5
        for label, variable in fields:
            tk.Label(
                pad,
                text=label,
                background=self.colors["sidebar"],
                foreground=self.colors["sidebar_muted"],
                font=("Segoe UI", 8),
                anchor="w",
            ).grid(row=row, column=0, sticky="ew", pady=(7, 2))
            ttk.Entry(pad, textvariable=variable).grid(row=row + 1, column=0, sticky="ew")
            row += 2
        ttk.Button(
            pad, text="Proje oluştur", style="Accent.TButton", command=self.create_project
        ).grid(row=row, column=0, sticky="ew", pady=(10, 20))

        self._sidebar_label(pad, "DOSYA İŞLEMLERİ").grid(row=row + 1, column=0, sticky="ew")
        self.format_combo = ttk.Combobox(
            pad,
            textvariable=self.format_var,
            values=("json", "po", "xliff"),
            state="readonly",
        )
        self.format_combo.grid(row=row + 2, column=0, sticky="ew", pady=(7, 8))
        file_buttons = tk.Frame(pad, background=self.colors["sidebar"])
        file_buttons.grid(row=row + 3, column=0, sticky="ew")
        file_buttons.columnconfigure((0, 1), weight=1)
        ttk.Button(
            file_buttons, text="İçe aktar", style="Secondary.TButton", command=self.import_file
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(
            file_buttons, text="Dışa aktar", style="Secondary.TButton", command=self.export_file
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _build_workspace_heading(self, parent: ttk.Frame) -> None:
        heading = ttk.Frame(parent)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(
            heading, textvariable=self.project_title_var, font=("Segoe UI Semibold", 17)
        ).pack(anchor="w")
        ttk.Label(
            heading, textvariable=self.project_subtitle_var, foreground=self.colors["muted"]
        ).pack(anchor="w")

    def _build_stats(self, parent: ttk.Frame) -> None:
        stats = ttk.Frame(parent)
        stats.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for index in range(4):
            stats.columnconfigure(index, weight=1)
        captions = (
            ("total", "TOPLAM KAYIT", self.colors["accent"]),
            ("translated", "ÇEVRİLEN", self.colors["success"]),
            ("untranslated", "BEKLEYEN", self.colors["warning"]),
            ("qa", "QA BULGUSU", self.colors["danger"]),
        )
        for index, (name, caption, color) in enumerate(captions):
            card = tk.Frame(
                stats,
                background=self.colors["panel"],
                highlightthickness=1,
                highlightbackground=self.colors["border"],
            )
            card.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=(0 if index == 0 else 6, 0 if index == 3 else 6),
            )
            tk.Frame(card, background=color, width=5).pack(side="left", fill="y")
            text = tk.Frame(card, background=self.colors["panel"])
            text.pack(side="left", fill="both", expand=True, padx=14, pady=10)
            tk.Label(
                text,
                textvariable=self.stats_vars[name],
                background=self.colors["panel"],
                foreground=self.colors["text"],
                font=("Segoe UI Semibold", 20),
            ).pack(anchor="w")
            tk.Label(
                text,
                text=caption,
                background=self.colors["panel"],
                foreground=self.colors["muted"],
                font=("Segoe UI Semibold", 8),
            ).pack(anchor="w")

    def _panel(self, parent: ttk.Frame) -> tk.Frame:
        return tk.Frame(
            parent,
            background=self.colors["panel"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )

    def _build_table_area(self, parent: ttk.Frame) -> None:
        frame = self._panel(parent)
        frame.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)

        titlebar = tk.Frame(frame, background=self.colors["panel"])
        titlebar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 8))
        tk.Label(
            titlebar,
            text="Çeviri Kayıtları",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")
        filters = tk.Frame(frame, background=self.colors["panel"])
        filters.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))
        filters.columnconfigure(0, weight=1)
        entry = ttk.Entry(filters, textvariable=self.search_var)
        entry.grid(row=0, column=0, padx=(0, 12), sticky="ew")
        entry.bind("<KeyRelease>", lambda _event: self.reload_entries())
        ttk.Checkbutton(
            filters,
            text="Yalnızca çevrilmemiş",
            variable=self.filter_untranslated,
            command=self.reload_entries,
        ).grid(row=0, column=1, padx=(0, 10))
        ttk.Checkbutton(
            filters,
            text="QA sorunu olanlar",
            variable=self.filter_qa,
            command=self.reload_entries,
        ).grid(row=0, column=2)

        self.tree = ttk.Treeview(
            frame,
            columns=("key", "source", "translation", "status", "qa"),
            show="headings",
            selectmode="browse",
        )
        headings = {
            "key": "ANAHTAR",
            "source": "KAYNAK METİN",
            "translation": "ÇEVİRİ",
            "status": "DURUM",
            "qa": "QA",
        }
        for column, width in (
            ("key", 180),
            ("source", 310),
            ("translation", 310),
            ("status", 130),
            ("qa", 55),
        ):
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=width, anchor="w")
        self.tree.grid(row=2, column=0, sticky="nsew", padx=(14, 0), pady=(0, 14))
        self.tree.bind("<<TreeviewSelect>>", self.on_entry_selected)
        tree_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=2, column=1, sticky="ns", padx=(0, 12), pady=(0, 14))
        self.tree.configure(yscrollcommand=tree_scroll.set)

    def _build_lower_area(self, parent: ttk.Frame) -> None:
        lower = ttk.Frame(parent)
        lower.grid(row=3, column=0, sticky="nsew")
        lower.columnconfigure(0, weight=3)
        lower.columnconfigure(1, weight=2)
        lower.rowconfigure(0, weight=1)
        self._build_qa_area(lower)
        self._build_editor_area(lower)

    def _build_qa_area(self, parent: ttk.Frame) -> None:
        frame = self._panel(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        tk.Label(
            frame,
            text="Kalite Bulguları",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8))

        self.qa_tree = ttk.Treeview(
            frame,
            columns=("key", "issue", "severity", "explanation"),
            show="headings",
            selectmode="browse",
        )
        headings = {
            "key": "ANAHTAR",
            "issue": "BULGU",
            "severity": "SEVİYE",
            "explanation": "AÇIKLAMA",
        }
        for column, width in (
            ("key", 130),
            ("issue", 140),
            ("severity", 75),
            ("explanation", 300),
        ):
            self.qa_tree.heading(column, text=headings[column])
            self.qa_tree.column(column, width=width, anchor="w")
        self.qa_tree.grid(row=1, column=0, sticky="nsew", padx=(14, 0), pady=(0, 14))
        self.qa_tree.bind("<<TreeviewSelect>>", self.on_issue_selected)
        qa_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.qa_tree.yview)
        qa_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 14))
        self.qa_tree.configure(yscrollcommand=qa_scroll.set)
        self.qa_tree.tag_configure("error", foreground=self.colors["danger"])
        self.qa_tree.tag_configure("warning", foreground=self.colors["warning"])

    def _build_editor_area(self, parent: ttk.Frame) -> None:
        frame = self._panel(parent)
        frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        tk.Label(
            frame,
            text="Çeviri Düzenleyici",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        self.translation_text = tk.Text(
            frame,
            height=7,
            wrap="word",
            font=("Segoe UI", 10),
            relief="flat",
            borderwidth=0,
            background="#F8FAFC",
            foreground=self.colors["text"],
            insertbackground=self.colors["accent"],
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["accent"],
        )
        self.translation_text.grid(row=1, column=0, sticky="nsew", padx=14)
        ttk.Button(
            frame, text="Çeviriyi kaydet", style="Accent.TButton", command=self.save_translation
        ).grid(row=2, column=0, sticky="e", padx=14, pady=12)

    def run(self) -> None:
        self.root.mainloop()

    def refresh_projects(self) -> None:
        projects = self.repository.list_projects()
        labels = [f"{item['slug']} | {item['name']}" for item in projects]
        self.project_combo["values"] = labels
        if self.current_project_slug is None and projects:
            self.current_project_slug = str(projects[0]["slug"])
        selected_index = next(
            (
                index
                for index, item in enumerate(projects)
                if str(item["slug"]) == self.current_project_slug
            ),
            0 if projects else -1,
        )
        if selected_index >= 0:
            self.project_combo.current(selected_index)
            self.open_selected_project()
        else:
            self.project_title_var.set("Bir proje seçin")
            self.project_subtitle_var.set(
                "Çeviri akışını ve kalite bulgularını tek ekrandan yönetin"
            )
            self.reload_entries()

    def open_selected_project(self) -> None:
        selection = self.project_combo.get().strip()
        if not selection:
            return
        self.current_project_slug = selection.split("|", 1)[0].strip()
        project = self.repository.get_project(self.current_project_slug)
        self.project_slug_var.set(str(project["slug"]))
        self.project_name_var.set(str(project["name"]))
        self.project_source_var.set(str(project["source_language"]))
        self.project_target_var.set(str(project["target_language"]))
        self.project_title_var.set(str(project["name"]))
        self.project_subtitle_var.set(
            f"{project['source_language']} → {project['target_language']}  •  "
            f"Proje: {project['slug']}"
        )
        self.reload_entries()

    def create_project(self) -> None:
        slug = self.project_slug_var.get().strip()
        name = self.project_name_var.get().strip()
        if not slug or not name:
            messagebox.showerror("Proje oluştur", "Kısa ad ve proje adı zorunludur.")
            return
        try:
            created = self.workflow.create_project(
                slug=slug,
                name=name,
                source_language=self.project_source_var.get().strip(),
                target_language=self.project_target_var.get().strip(),
            )
        except Exception as exc:  # pragma: no cover - user-facing dialog
            messagebox.showerror("Proje oluştur", str(exc))
            return
        self.current_project_slug = created
        self.status_var.set(f"Proje hazır: {created}")
        self.refresh_projects()

    def create_sample_project(self) -> None:
        try:
            slug = self.workflow.create_sample_project()
        except Exception as exc:  # pragma: no cover - user-facing dialog
            messagebox.showerror("Örnek proje", str(exc))
            return
        self.current_project_slug = slug
        self.refresh_projects()
        self.status_var.set(f"Örnek proje hazır: {slug}")

    def reload_entries(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.qa_tree.delete(*self.qa_tree.get_children())
        if not self.current_project_slug:
            for name in self.stats_vars:
                self.stats_vars[name].set("0")
            return

        entries = self.repository.list_entries(
            self.current_project_slug,
            search=self.search_var.get().strip() or None,
        )
        issues = analyze_entries(entries)
        issue_map: dict[str, list[str]] = {}
        for issue in issues:
            issue_map.setdefault(issue.key, []).append(issue.issue_type)
            self.qa_tree.insert(
                "",
                "end",
                values=(issue.key, issue.issue_type, issue.severity, issue.explanation),
                tags=(issue.severity,),
            )

        visible: list[dict[str, object]] = []
        for entry in entries:
            translation = str(entry["target_text"])
            has_translation = bool(translation.strip())
            has_qa = bool(issue_map.get(str(entry["source_key"])))
            if self.filter_untranslated.get() and has_translation:
                continue
            if self.filter_qa.get() and not has_qa:
                continue
            visible.append(entry)

        self.all_entries = entries
        self.visible_entries = visible
        self.current_issues = issues

        for entry in visible:
            key = str(entry["source_key"])
            qa_count = str(len(issue_map.get(key, []))) if issue_map.get(key) else ""
            self.tree.insert(
                "",
                "end",
                iid=str(entry["id"]),
                values=(
                    key,
                    entry["source_text"],
                    entry["target_text"],
                    f"{entry['translation_status']}/{entry['review_status']}",
                    qa_count,
                ),
                tags=("has_qa",) if qa_count else (),
            )

        translated_count = sum(1 for item in entries if str(item["target_text"]).strip())
        self.stats_vars["total"].set(str(len(entries)))
        self.stats_vars["translated"].set(str(translated_count))
        self.stats_vars["untranslated"].set(str(len(entries) - translated_count))
        self.stats_vars["qa"].set(str(len(issues)))
        self.tree.tag_configure("has_qa", foreground=self.colors["danger"])

    def on_entry_selected(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected_entry_id = selection[0]
        item = next((row for row in self.visible_entries if str(row["id"]) == selection[0]), None)
        if item is None:
            return
        self.translation_text.delete("1.0", tk.END)
        self.translation_text.insert("1.0", str(item["target_text"]))

    def on_issue_selected(self, _event: tk.Event) -> None:
        selection = self.qa_tree.selection()
        if not selection:
            return
        key = self.qa_tree.item(selection[0], "values")[0]
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            if values and values[0] == key:
                self.tree.selection_set(item_id)
                self.tree.see(item_id)
                self.selected_entry_id = item_id
                self.on_entry_selected(_event)
                break

    def save_translation(self) -> None:
        if not self.current_project_slug or self.selected_entry_id is None:
            return
        translation = self.translation_text.get("1.0", "end-1c")
        current = next(
            row
            for row in self.repository.list_entries(self.current_project_slug)
            if str(row["id"]) == self.selected_entry_id
        )
        try:
            self.repository.update_entry(
                self.selected_entry_id,
                target_text=translation,
                translation_status="translated" if translation.strip() else "draft",
                review_status=str(current["review_status"]),
            )
        except Exception as exc:  # pragma: no cover - user-facing dialog
            messagebox.showerror("Çeviriyi kaydet", str(exc))
            return
        self.status_var.set("Çeviri kaydedildi")
        self.reload_entries()

    def import_file(self) -> None:
        if not self.current_project_slug:
            messagebox.showinfo("İçe aktar", "Önce bir proje oluşturun veya açın.")
            return
        path = filedialog.askopenfilename(
            filetypes=[
                ("Yerelleştirme dosyaları", "*.json *.po *.xlf *.xliff *.xml"),
                ("Tüm dosyalar", "*.*"),
            ]
        )
        if not path:
            return
        try:
            document = load_localization_document(Path(path), self.format_var.get())
            if document.project:
                self.project_name_var.set(
                    str(document.project.get("name", self.project_name_var.get()))
                )
                self.project_source_var.set(
                    str(document.project.get("source_language", self.project_source_var.get()))
                )
                self.project_target_var.set(
                    str(document.project.get("target_language", self.project_target_var.get()))
                )
            self.workflow.import_project(
                Path(path),
                format_name=self.format_var.get(),
                project_slug=self.current_project_slug,
            )
        except Exception as exc:  # pragma: no cover - user-facing dialog
            messagebox.showerror("İçe aktar", str(exc))
            return
        self.status_var.set(f"İçe aktarıldı: {Path(path).name}")
        self.reload_entries()

    def export_file(self) -> None:
        if not self.current_project_slug:
            messagebox.showinfo("Dışa aktar", "Önce bir proje oluşturun veya açın.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=f".{self.format_var.get()}",
            filetypes=[
                ("Yerelleştirme dosyaları", "*.json *.po *.xlf *.xliff *.xml"),
                ("Tüm dosyalar", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.workflow.export_project(
                self.current_project_slug,
                Path(path),
                format_name=self.format_var.get(),
            )
        except Exception as exc:  # pragma: no cover - user-facing dialog
            messagebox.showerror("Dışa aktar", str(exc))
            return
        self.status_var.set(f"Dışa aktarıldı: {Path(path).name}")


def launch_gui() -> None:
    from .scanner_gui import launch_scanner_gui

    launch_scanner_gui()
