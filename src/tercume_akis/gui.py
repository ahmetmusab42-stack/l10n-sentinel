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
        self.root.title("L10n Sentinel Workbench")
        self.root.geometry("1180x760")
        self.root.minsize(1060, 680)

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
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self.refresh_projects()

    def _build_ui(self) -> None:
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)
        self._build_project_area()
        self._build_file_area()
        self._build_table_area()
        self._build_qa_area()
        ttk.Label(self.root, textvariable=self.status_var, anchor="w").grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8)
        )

    def _build_project_area(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Project Area")
        frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        frame.columnconfigure(7, weight=1)

        ttk.Label(frame, text="Project").grid(row=0, column=0, sticky="w")
        self.project_combo = ttk.Combobox(frame, state="readonly", width=30)
        self.project_combo.grid(row=0, column=1, padx=(6, 10), sticky="w")
        ttk.Button(frame, text="Open", command=self.open_selected_project).grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(frame, text="Refresh", command=self.refresh_projects).grid(
            row=0, column=3, padx=(0, 12)
        )
        ttk.Button(frame, text="Sample", command=self.create_sample_project).grid(
            row=0, column=4, padx=(0, 8)
        )

        fields = (
            ("Slug", self.project_slug_var, 18, 1, 0),
            ("Name", self.project_name_var, 24, 1, 2),
            ("Source", self.project_source_var, 8, 1, 4),
            ("Target", self.project_target_var, 8, 1, 6),
        )
        for label, variable, width, row, column in fields:
            ttk.Label(frame, text=label).grid(row=row, column=column, sticky="w", pady=(6, 0))
            ttk.Entry(frame, textvariable=variable, width=width).grid(
                row=row, column=column + 1, sticky="w", pady=(6, 0)
            )
        ttk.Button(frame, text="Create Project", command=self.create_project).grid(
            row=1, column=8, padx=(8, 0), pady=(6, 0)
        )

    def _build_file_area(self) -> None:
        frame = ttk.LabelFrame(self.root, text="File Area")
        frame.grid(row=1, column=0, sticky="nswe", padx=(10, 6), pady=6)

        ttk.Label(frame, text="Format").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            frame,
            textvariable=self.format_var,
            values=("json", "po", "xliff"),
            width=10,
            state="readonly",
        ).grid(row=0, column=1, sticky="w")
        ttk.Button(frame, text="Import", command=self.import_file).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 4)
        )
        ttk.Button(frame, text="Export", command=self.export_file).grid(
            row=2, column=0, columnspan=2, sticky="ew"
        )

    def _build_table_area(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Translation Table")
        frame.grid(row=2, column=1, sticky="nswe", padx=(6, 10), pady=6)
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)

        filters = ttk.Frame(frame)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(filters, text="Search").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(filters, textvariable=self.search_var, width=32)
        entry.grid(row=0, column=1, padx=(6, 10), sticky="ew")
        entry.bind("<KeyRelease>", lambda _event: self.reload_entries())
        ttk.Checkbutton(
            filters,
            text="Untranslated",
            variable=self.filter_untranslated,
            command=self.reload_entries,
        ).grid(row=0, column=2, padx=(0, 10))
        ttk.Checkbutton(
            filters,
            text="QA problems",
            variable=self.filter_qa,
            command=self.reload_entries,
        ).grid(row=0, column=3)

        self.tree = ttk.Treeview(
            frame,
            columns=("key", "source", "translation", "status", "qa"),
            show="headings",
            selectmode="browse",
        )
        for column, width in (
            ("key", 170),
            ("source", 280),
            ("translation", 280),
            ("status", 110),
            ("qa", 70),
        ):
            self.tree.heading(column, text=column.capitalize())
            self.tree.column(column, width=width, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nswe")
        self.tree.bind("<<TreeviewSelect>>", self.on_entry_selected)
        tree_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)

        editor = ttk.Frame(frame)
        editor.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        editor.columnconfigure(0, weight=1)
        ttk.Label(editor, text="Translation editor").grid(row=0, column=0, sticky="w")
        self.translation_text = tk.Text(editor, height=5, wrap="word")
        self.translation_text.grid(row=1, column=0, sticky="ew")
        ttk.Button(editor, text="Save Translation", command=self.save_translation).grid(
            row=2, column=0, sticky="e", pady=(6, 0)
        )

    def _build_qa_area(self) -> None:
        frame = ttk.LabelFrame(self.root, text="QA Panel")
        frame.grid(row=2, column=0, sticky="nswe", padx=(10, 6), pady=6)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.qa_tree = ttk.Treeview(
            frame,
            columns=("key", "issue", "severity", "explanation"),
            show="headings",
            selectmode="browse",
        )
        for column, width in (
            ("key", 120),
            ("issue", 130),
            ("severity", 80),
            ("explanation", 280),
        ):
            self.qa_tree.heading(column, text=column.capitalize())
            self.qa_tree.column(column, width=width, anchor="w")
        self.qa_tree.grid(row=0, column=0, sticky="nswe")
        self.qa_tree.bind("<<TreeviewSelect>>", self.on_issue_selected)
        qa_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.qa_tree.yview)
        qa_scroll.grid(row=0, column=1, sticky="ns")
        self.qa_tree.configure(yscrollcommand=qa_scroll.set)

        stats = ttk.LabelFrame(self.root, text="Project Stats")
        stats.grid(row=1, column=1, sticky="ew", padx=(6, 10), pady=(6, 0))
        for row, name in enumerate(("total", "translated", "untranslated", "qa")):
            ttk.Label(stats, text=name.capitalize()).grid(row=row, column=0, sticky="w")
            ttk.Label(stats, textvariable=self.stats_vars[name]).grid(row=row, column=1, sticky="e")

    def run(self) -> None:
        self.root.mainloop()

    def refresh_projects(self) -> None:
        projects = self.repository.list_projects()
        labels = [f"{item['slug']} | {item['name']}" for item in projects]
        self.project_combo["values"] = labels
        if labels and self.project_combo.current() < 0:
            self.project_combo.current(0)
        if self.current_project_slug is None and projects:
            self.current_project_slug = str(projects[0]["slug"])
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
        self.reload_entries()

    def create_project(self) -> None:
        slug = self.project_slug_var.get().strip()
        name = self.project_name_var.get().strip()
        if not slug or not name:
            messagebox.showerror("Create project", "Slug and name are required.")
            return
        try:
            created = self.workflow.create_project(
                slug=slug,
                name=name,
                source_language=self.project_source_var.get().strip(),
                target_language=self.project_target_var.get().strip(),
            )
        except Exception as exc:  # pragma: no cover - user-facing dialog
            messagebox.showerror("Create project", str(exc))
            return
        self.current_project_slug = created
        self.status_var.set(f"Project ready: {created}")
        self.refresh_projects()

    def create_sample_project(self) -> None:
        try:
            slug = self.workflow.create_sample_project()
        except Exception as exc:  # pragma: no cover - user-facing dialog
            messagebox.showerror("Sample project", str(exc))
            return
        self.current_project_slug = slug
        self.refresh_projects()
        self.status_var.set(f"Sample project ready: {slug}")

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
            )

        translated_count = sum(1 for item in entries if str(item["target_text"]).strip())
        self.stats_vars["total"].set(str(len(entries)))
        self.stats_vars["translated"].set(str(translated_count))
        self.stats_vars["untranslated"].set(str(len(entries) - translated_count))
        self.stats_vars["qa"].set(str(len(issues)))

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
            messagebox.showerror("Save translation", str(exc))
            return
        self.status_var.set("Translation saved")
        self.reload_entries()

    def import_file(self) -> None:
        if not self.current_project_slug:
            messagebox.showinfo("Import", "Create or open a project first.")
            return
        path = filedialog.askopenfilename(
            filetypes=[
                ("Localization files", "*.json *.po *.xlf *.xliff *.xml"),
                ("All files", "*.*"),
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
            messagebox.showerror("Import", str(exc))
            return
        self.status_var.set(f"Imported {Path(path).name}")
        self.reload_entries()

    def export_file(self) -> None:
        if not self.current_project_slug:
            messagebox.showinfo("Export", "Create or open a project first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=f".{self.format_var.get()}",
            filetypes=[
                ("Localization files", "*.json *.po *.xlf *.xliff *.xml"),
                ("All files", "*.*"),
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
            messagebox.showerror("Export", str(exc))
            return
        self.status_var.set(f"Exported {Path(path).name}")


def launch_gui() -> None:
    WorkbenchApp().run()
