# ШІ: Графічний інтерфейс користувача на базі CustomTkinter. Змінено: оновлено підпис чекбокса правила перевірки виродженості граней.
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import queue
import customtkinter as ctk

import controller

ctk.set_appearance_mode("dark")


class MeshAnalyzerView(ctk.CTk):
    def __init__(self, ctrl: controller.MeshAnalyzerController):
        super().__init__()
        self.ctrl = ctrl

        self.title("Meshanalyzer — Аналіз та валідація 3D-моделей")
        self.geometry("1380x800")
        self.minsize(1200, 720)
        self.configure(fg_color="#0d0d0d")

        self.canvas_states = {}
        self.active_rule_filter = "Усі"
        self.active_severity_filter = "Усі"

        self._configure_treeview_style()
        self._build_layout()
        self._refresh_models_table()
        self._sync_rules_ui_from_project()

    def _configure_treeview_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.Treeview",
            background="#141414",
            foreground="#e6e6e6",
            fieldbackground="#141414",
            borderwidth=0,
            font=("Segoe UI", 10),
            rowheight=24
        )
        style.configure(
            "Dark.Treeview.Heading",
            background="#222222",
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat"
        )
        style.map("Dark.Treeview", background=[("selected", "#b8252f")], foreground=[("selected", "#ffffff")])

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=5)
        self.grid_columnconfigure(1, weight=6)
        self.grid_rowconfigure(0, weight=1)

        left_panel = ctk.CTkFrame(self, fg_color="#141414", border_width=1, border_color="#2a2a2a", corner_radius=8)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(4, weight=1)
        left_panel.grid_rowconfigure(6, weight=2)

        proj_frame = ctk.CTkFrame(left_panel, fg_color="#1c1c1c", border_width=1, border_color="#2e2e2e", corner_radius=6)
        proj_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        proj_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(proj_frame, text="Проєкт:", text_color="#ffffff", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, padx=8, pady=6)
        self.entry_project = ctk.CTkEntry(proj_frame, fg_color="#121212", border_color="#383838", text_color="#ffffff", placeholder_text="Назва проєкту")
        self.entry_project.insert(0, self.ctrl.project.name)
        self.entry_project.grid(row=0, column=1, sticky="ew", padx=4, pady=6)

        ctk.CTkButton(proj_frame, text="Зберегти назву", width=105, fg_color="#2e2e2e", hover_color="#3d3d3d", text_color="#ffffff", command=self._on_rename_project).grid(row=0, column=2, padx=4, pady=6)
        ctk.CTkButton(proj_frame, text="Новий", width=65, fg_color="#242424", hover_color="#363636", text_color="#dcdcdc", command=self._on_new_project).grid(row=0, column=3, padx=4, pady=6)
        ctk.CTkButton(proj_frame, text="Імпорт JSON", width=95, fg_color="#1f7a3f", hover_color="#175e30", text_color="#ffffff", command=self._on_import_json).grid(row=0, column=4, padx=(4, 8), pady=6)

        file_frame = ctk.CTkFrame(left_panel, fg_color="#1c1c1c", border_width=1, border_color="#2e2e2e", corner_radius=6)
        file_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        file_frame.grid_columnconfigure(0, weight=1)

        self.entry_path = ctk.CTkEntry(file_frame, fg_color="#121212", border_color="#383838", text_color="#ffffff", placeholder_text="Шлях до 3D-моделі (.obj)...")
        self.entry_path.insert(0, "test_models/01_valid_cube.obj")
        self.entry_path.grid(row=0, column=0, sticky="ew", padx=(8, 6), pady=8)

        ctk.CTkButton(file_frame, text="Огляд...", width=85, fg_color="#2e2e2e", hover_color="#3f3f3f", text_color="#ffffff", command=self._on_browse_obj).grid(row=0, column=1, padx=4, pady=8)
        self.btn_run = ctk.CTkButton(file_frame, text="Перевірити", width=105, fg_color="#1f7a3f", hover_color="#175e30", text_color="#ffffff", font=("Segoe UI", 12, "bold"), command=self._on_run_analysis)
        self.btn_run.grid(row=0, column=2, padx=4, pady=8)
        self.btn_cancel = ctk.CTkButton(file_frame, text="Скасувати", width=90, fg_color="#b8252f", hover_color="#8f1b23", text_color="#ffffff", state="disabled", command=self._on_cancel_analysis)
        self.btn_cancel.grid(row=0, column=3, padx=(4, 8), pady=8)

        prog_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        prog_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 6))
        prog_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(prog_frame, height=10, fg_color="#242424", progress_color="#28a745")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.lbl_status = ctk.CTkLabel(prog_frame, text="Готово до роботи", font=("Segoe UI", 11), text_color="#9e9e9e")
        self.lbl_status.grid(row=0, column=1, sticky="e")

        rules_frame = ctk.CTkFrame(left_panel, fg_color="#1c1c1c", border_width=1, border_color="#2e2e2e", corner_radius=6)
        rules_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=6)

        self.var_dup = ctk.BooleanVar(value=True)
        self.var_deg = ctk.BooleanVar(value=True)
        self.var_norm = ctk.BooleanVar(value=True)

        cb_kwargs = {"fg_color": "#1f7a3f", "hover_color": "#175e30", "border_color": "#555555", "text_color": "#e6e6e6"}
        ctk.CTkCheckBox(rules_frame, text="Дублікати", variable=self.var_dup, width=90, **cb_kwargs).pack(side="left", padx=(8, 4), pady=6)
        ctk.CTkCheckBox(rules_frame, text="Вироджені", variable=self.var_deg, width=85, **cb_kwargs).pack(side="left", padx=4, pady=6)
        ctk.CTkCheckBox(rules_frame, text="Нормалі", variable=self.var_norm, width=80, **cb_kwargs).pack(side="left", padx=4, pady=6)

        ctk.CTkLabel(rules_frame, text="Допуск:", text_color="#cccccc").pack(side="left", padx=(8, 4))
        self.entry_tol = ctk.CTkEntry(rules_frame, width=75, fg_color="#121212", border_color="#383838", text_color="#ffffff")
        self.entry_tol.insert(0, "1e-6")
        self.entry_tol.pack(side="left", padx=4, pady=6)

        ctk.CTkButton(rules_frame, text="Застосувати", width=95, fg_color="#2e2e2e", hover_color="#3f3f3f", text_color="#ffffff", command=self._on_apply_rules).pack(side="right", padx=(4, 8), pady=6)

        models_box = ctk.CTkFrame(left_panel, fg_color="#1c1c1c", border_width=1, border_color="#2e2e2e", corner_radius=6)
        models_box.grid(row=4, column=0, sticky="nsew", padx=10, pady=6)
        models_box.grid_columnconfigure(0, weight=1)
        models_box.grid_rowconfigure(1, weight=1)

        m_toolbar = ctk.CTkFrame(models_box, fg_color="transparent")
        m_toolbar.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        m_toolbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(m_toolbar, text="Моделі проєкту:", text_color="#ffffff", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, padx=(2, 6))
        self.entry_search = ctk.CTkEntry(m_toolbar, fg_color="#121212", border_color="#383838", text_color="#ffffff", placeholder_text="Пошук за назвою...", height=28)
        self.entry_search.grid(row=0, column=1, sticky="ew", padx=4)
        self.entry_search.bind("<KeyRelease>", lambda e: self._refresh_models_table())

        self.combo_sort = ctk.CTkComboBox(
            m_toolbar,
            values=["Сортувати: Помилки", "Сортувати: Вершини", "Сортувати: Назва"],
            width=165,
            height=28,
            fg_color="#121212",
            border_color="#383838",
            button_color="#2e2e2e",
            button_hover_color="#3f3f3f",
            text_color="#ffffff",
            command=lambda _: self._refresh_models_table()
        )
        self.combo_sort.grid(row=0, column=2, padx=4)

        ctk.CTkButton(m_toolbar, text="Видалити", width=75, height=28, fg_color="#b8252f", hover_color="#8f1b23", text_color="#ffffff", command=self._on_delete_selected_model).grid(row=0, column=3, padx=(4, 2))

        self.tree_models = ttk.Treeview(
            models_box,
            columns=("name", "vertices", "errors"),
            show="headings",
            style="Dark.Treeview",
            height=4
        )
        self.tree_models.heading("name", text="Назва моделі")
        self.tree_models.heading("vertices", text="Вершин")
        self.tree_models.heading("errors", text="Помилок")
        self.tree_models.column("name", width=260, anchor="w")
        self.tree_models.column("vertices", width=95, anchor="center")
        self.tree_models.column("errors", width=95, anchor="center")
        self.tree_models.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.tree_models.bind("<<TreeviewSelect>>", self._on_select_model_row)

        filter_bar = ctk.CTkFrame(left_panel, fg_color="#1c1c1c", border_width=1, border_color="#2e2e2e", corner_radius=6)
        filter_bar.grid(row=5, column=0, sticky="ew", padx=10, pady=6)

        ctk.CTkLabel(filter_bar, text="Правило:", text_color="#cccccc").pack(side="left", padx=(8, 4), pady=6)
        self.combo_rule_filter = ctk.CTkComboBox(
            filter_bar,
            values=["Усі", "DuplicateVertexRule", "DegenerateFaceRule", "NormalRule"],
            width=160,
            height=28,
            fg_color="#121212",
            border_color="#383838",
            button_color="#2e2e2e",
            button_hover_color="#3f3f3f",
            text_color="#ffffff",
            command=self._on_filter_issues
        )
        self.combo_rule_filter.pack(side="left", padx=4, pady=6)

        ctk.CTkLabel(filter_bar, text="Критичність:", text_color="#cccccc").pack(side="left", padx=(8, 4), pady=6)
        self.combo_sev_filter = ctk.CTkComboBox(
            filter_bar,
            values=["Усі", "Critical", "Warning", "Info"],
            width=105,
            height=28,
            fg_color="#121212",
            border_color="#383838",
            button_color="#2e2e2e",
            button_hover_color="#3f3f3f",
            text_color="#ffffff",
            command=self._on_filter_issues
        )
        self.combo_sev_filter.pack(side="left", padx=4, pady=6)

        self.btn_export_xml = ctk.CTkButton(
            filter_bar, text="Експорт XML", width=110, height=28,
            fg_color="#1f7a3f", hover_color="#175e30", text_color="#ffffff", state="disabled",
            command=self._on_export_xml
        )
        self.btn_export_xml.pack(side="right", padx=(4, 8), pady=6)

        issues_box = ctk.CTkFrame(left_panel, fg_color="#1c1c1c", border_width=1, border_color="#2e2e2e", corner_radius=6)
        issues_box.grid(row=6, column=0, sticky="nsew", padx=10, pady=(6, 10))
        issues_box.grid_columnconfigure(0, weight=1)
        issues_box.grid_rowconfigure(0, weight=1)

        self.tree_issues = ttk.Treeview(
            issues_box,
            columns=("idx", "type", "rule", "severity"),
            show="headings",
            style="Dark.Treeview",
            height=9
        )
        self.tree_issues.heading("idx", text="Елемент #")
        self.tree_issues.heading("type", text="Тип помилки")
        self.tree_issues.heading("rule", text="Правило")
        self.tree_issues.heading("severity", text="Критичність")
        self.tree_issues.column("idx", width=85, anchor="center")
        self.tree_issues.column("type", width=155, anchor="w")
        self.tree_issues.column("rule", width=155, anchor="w")
        self.tree_issues.column("severity", width=95, anchor="center")
        self.tree_issues.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.tree_issues.bind("<<TreeviewSelect>>", self._on_select_issue_row)

        right_panel = ctk.CTkFrame(self, fg_color="#141414", border_width=1, border_color="#2a2a2a", corner_radius=8)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right_panel.grid_columnconfigure((0, 1), weight=1)
        right_panel.grid_rowconfigure(2, weight=1)

        dash_frame = ctk.CTkFrame(right_panel, fg_color="#1c1c1c", border_width=1, border_color="#2e2e2e", corner_radius=6)
        dash_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 8))

        self.lbl_summary = ctk.CTkLabel(
            dash_frame,
            text="Завантажте .obj модель та натисніть «Перевірити» для візуалізації",
            font=("Segoe UI", 12, "bold"),
            text_color="#ffffff"
        )
        self.lbl_summary.pack(side="left", padx=12, pady=8)

        ctk.CTkButton(dash_frame, text="Скинути вигляд", width=115, height=28, fg_color="#2e2e2e", hover_color="#3f3f3f", text_color="#ffffff", command=self._reset_view).pack(side="right", padx=12, pady=8)

        ctk.CTkLabel(right_panel, text="Горизонтальна проєкція (XY):", text_color="#e0e0e0", font=("Segoe UI", 12, "bold")).grid(row=1, column=0, sticky="w", padx=14, pady=(4, 2))
        ctk.CTkLabel(right_panel, text="Вертикальна проєкція (XZ):", text_color="#e0e0e0", font=("Segoe UI", 12, "bold")).grid(row=1, column=1, sticky="w", padx=14, pady=(4, 2))

        self.canvas_xy = tk.Canvas(right_panel, width=340, height=340, bg="#0a0a0a", highlightthickness=1, highlightbackground="#333333")
        self.canvas_xy.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)

        self.canvas_xz = tk.Canvas(right_panel, width=340, height=340, bg="#0a0a0a", highlightthickness=1, highlightbackground="#333333")
        self.canvas_xz.grid(row=2, column=1, sticky="nsew", padx=(6, 12), pady=6)

        legend = (
            "Легенда візуалізації:
"
            "• Сірі лінії — коректна сітка | Червоні лінії — дефектні грані | Білі точки — дублікати вершин
"
            "• Обраний елемент — яскраво-зелений акцент | Коліщатко миші — Zoom, ЛКМ — Pan"
        )
        ctk.CTkLabel(right_panel, text=legend, justify="left", font=("Segoe UI", 11), text_color="#9e9e9e").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(6, 12)
        )

    def _on_rename_project(self):
        try:
            self.ctrl.rename_project(self.entry_project.get())
            self.lbl_status.configure(text="Назву проєкту оновлено")
        except Exception as e:
            messagebox.showerror("Помилка валідації", str(e))

    def _on_new_project(self):
        try:
            name = self.entry_project.get().strip() or "New 3D Project"
            self.ctrl.create_new_project(name)
            self._refresh_models_table()
            self._clear_issues_table()
            self.canvas_xy.delete("all")
            self.canvas_xz.delete("all")
            self.lbl_status.configure(text=f"Створено проєкт '{name}'")
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def _on_import_json(self):
        path = filedialog.askopenfilename(title="Імпорт проєкту JSON", filetypes=[("JSON файли", "*.json")])
        if not path:
            return
        try:
            self.ctrl.import_project_json(path)
            self.entry_project.delete(0, tk.END)
            self.entry_project.insert(0, self.ctrl.project.name)
            self._sync_rules_ui_from_project()
            self._refresh_models_table()
            messagebox.showinfo("Імпорт JSON", f"Проєкт '{self.ctrl.project.name}' успішно завантажено!")
        except Exception as e:
            messagebox.showerror("Помилка JSON", str(e))

    def _sync_rules_ui_from_project(self):
        active_names = {r.name for r in self.ctrl.project.rules}
        self.var_dup.set("DuplicateVertexRule" in active_names)
        self.var_deg.set("DegenerateFaceRule" in active_names)
        self.var_norm.set("NormalRule" in active_names)
        if self.ctrl.project.rules:
            self.entry_tol.delete(0, tk.END)
            self.entry_tol.insert(0, str(self.ctrl.project.rules[0].tolerance))

    def _on_apply_rules(self):
        try:
            enabled = {
                "DuplicateVertexRule": self.var_dup.get(),
                "DegenerateFaceRule": self.var_deg.get(),
                "NormalRule": self.var_norm.get()
            }
            self.ctrl.update_rules(enabled, self.entry_tol.get())
            self.lbl_status.configure(text="Правила та допуск збережено")
        except Exception as e:
            messagebox.showerror("Помилка правил", str(e))

    def _on_browse_obj(self):
        file_path = filedialog.askopenfilename(
            title="Виберіть 3D-модель (.obj)",
            filetypes=[("OBJ 3D моделі", "*.obj"), ("Усі файли", "*.*")]
        )
        if file_path:
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, file_path)

    def _on_run_analysis(self):
        try:
            self._on_apply_rules()
            file_path = self.entry_path.get()
            self.ctrl.start_analysis(file_path)

            self.progress_bar.set(0.05)
            self.btn_run.configure(state="disabled")
            self.btn_cancel.configure(state="normal")
            self.btn_export_xml.configure(state="disabled")
            self.after(80, self._poll_queue)
        except Exception as e:
            messagebox.showerror("Помилка запуску", str(e))

    def _on_cancel_analysis(self):
        self.ctrl.cancel_analysis()
        self.btn_cancel.configure(state="disabled")

    def _poll_queue(self):
        keep_polling = True
        while not self.ctrl.result_queue.empty():
            try:
                msg_type, payload, text_info = self.ctrl.result_queue.get_nowait()
                if msg_type == "progress":
                    self.progress_bar.set(payload)
                    if text_info:
                        self.lbl_status.configure(text=text_info)
                elif msg_type == "cancelled":
                    self.progress_bar.set(0)
                    self.lbl_status.configure(text=text_info or "Скасовано")
                    self.btn_run.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    keep_polling = False
                elif msg_type == "error":
                    self.progress_bar.set(0)
                    self.lbl_status.configure(text="Помилка перевірки")
                    self.btn_run.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    messagebox.showerror("Помилка аналізу OBJ", payload)
                    keep_polling = False
                elif msg_type == "success":
                    self.progress_bar.set(1.0)
                    self.lbl_status.configure(text=text_info or "Готово")
                    self.btn_run.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    self.btn_export_xml.configure(state="normal")

                    model_obj = payload
                    self._refresh_models_table()
                    self._display_model_results(model_obj)
                    keep_polling = False
            except queue.Empty:
                break

        if keep_polling:
            self.after(80, self._poll_queue)

    def _refresh_models_table(self):
        for item in self.tree_models.get_children():
            self.tree_models.delete(item)

        sort_choice = self.combo_sort.get()
        sort_key = "errors"
        if "Вершини" in sort_choice:
            sort_key = "vertices"
        elif "Назва" in sort_choice:
            sort_key = "name"

        models = self.ctrl.get_filtered_sorted_models(self.entry_search.get(), sort_key)
        for m in models:
            self.tree_models.insert("", "end", iid=m.name, values=(m.name, len(m.vertices), len(m.issues)))

    def _on_select_model_row(self, _event):
        sel = self.tree_models.selection()
        if not sel:
            return
        model_obj = self.ctrl.project.get_model(sel[0])
        if model_obj:
            self.ctrl.current_model = model_obj
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, model_obj.file_path)
            if not model_obj.issues:
                model_obj.validate(self.ctrl.project.rules)
            self._display_model_results(model_obj)
            self.btn_export_xml.configure(state="normal")

    def _on_delete_selected_model(self):
        sel = self.tree_models.selection()
        if not sel:
            return
        self.ctrl.delete_model(sel[0])
        self._refresh_models_table()
        self._clear_issues_table()

    def _clear_issues_table(self):
        for item in self.tree_issues.get_children():
            self.tree_issues.delete(item)

    def _on_filter_issues(self, _val=None):
        self.active_rule_filter = self.combo_rule_filter.get()
        self.active_severity_filter = self.combo_sev_filter.get()
        if self.ctrl.current_model:
            self._populate_issues_table(self.ctrl.current_model)
            self._redraw_both_canvases()

    def _get_filtered_issues(self, model_obj):
        res = model_obj.issues
        if self.active_rule_filter != "Усі":
            res = [i for i in res if i.rule_name == self.active_rule_filter]
        if self.active_severity_filter != "Усі":
            res = [i for i in res if i.severity == self.active_severity_filter]
        return res

    def _populate_issues_table(self, model_obj):
        self._clear_issues_table()
        filtered = self._get_filtered_issues(model_obj)
        for idx, iss in enumerate(filtered[:500]):
            self.tree_issues.insert(
                "", "end", iid=f"{idx}_{iss.index}",
                values=(iss.index, iss.error_type, iss.rule_name, iss.severity)
            )

    def _display_model_results(self, model_obj):
        self.lbl_summary.configure(
            text=f"Модель: {model_obj.name} | Вершин: {len(model_obj.vertices)} | Граней: {len(model_obj.faces)} | Помилок: {len(model_obj.issues)}"
        )
        self._populate_issues_table(model_obj)
        self._setup_canvas(self.canvas_xy, model_obj, lambda v: (v[0], v[1]))
        self._setup_canvas(self.canvas_xz, model_obj, lambda v: (v[0], v[2]))

    def _on_select_issue_row(self, _event):
        sel = self.tree_issues.selection()
        if not sel:
            return
        vals = self.tree_issues.item(sel[0], "values")
        if vals:
            elem_idx = int(vals[0])
            self._redraw_both_canvases(highlight_idx=elem_idx)

    def _on_export_xml(self):
        save_path = filedialog.asksaveasfilename(
            defaultextension=".xml",
            filetypes=[("XML звіти", "*.xml")],
            title="Експорт звіту в XML"
        )
        if not save_path:
            return
        try:
            self.ctrl.export_current_model_xml(save_path)
            messagebox.showinfo("Експорт XML", f"Звіт успішно збережено:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Помилка експорту", str(e))

    def _setup_canvas(self, canvas, model_obj, coords_func):
        vertices = model_obj.raw_data["vertices"]
        if not vertices:
            return

        min_u = min(coords_func(v)[0] for v in vertices)
        max_u = max(coords_func(v)[0] for v in vertices)
        min_v = min(coords_func(v)[1] for v in vertices)
        max_v = max(coords_func(v)[1] for v in vertices)

        range_u = max_u - min_u if max_u != min_u else 1.0
        range_v = max_v - min_v if max_v != min_v else 1.0

        c_w = max(320, canvas.winfo_width())
        c_h = max(320, canvas.winfo_height())
        c_size = min(c_w, c_h)
        margin = 25
        base_scale = min((c_size - 2 * margin) / range_u, (c_size - 2 * margin) / range_v)

        base_offset_u = (c_size - range_u * base_scale) / 2 - min_u * base_scale
        base_offset_v = (c_size - range_v * base_scale) / 2 - min_v * base_scale

        self.canvas_states[canvas] = {
            "zoom": 1.0,
            "pan_x": 0.0,
            "pan_y": 0.0,
            "base_scale": base_scale,
            "base_offset_u": base_offset_u,
            "base_offset_v": base_offset_v,
            "c_size": c_size,
            "model": model_obj,
            "coords_func": coords_func,
            "drag_start": (0, 0),
            "highlight_index": None,
            "zoom_timer": None
        }
        self._redraw_canvas(canvas, fast_mode=False)

        canvas.bind("<ButtonPress-1>", lambda e, c=canvas: self._on_pan_start(c, e))
        canvas.bind("<B1-Motion>", lambda e, c=canvas: self._on_pan_move(c, e))
        canvas.bind("<ButtonRelease-1>", lambda e, c=canvas: self._on_pan_release(c, e))
        canvas.bind("<MouseWheel>", lambda e, c=canvas: self._on_zoom(c, e))

    def _reset_view(self):
        for canvas, state in self.canvas_states.items():
            state["zoom"] = 1.0
            state["pan_x"] = 0.0
            state["pan_y"] = 0.0
            state["highlight_index"] = None
            self._redraw_canvas(canvas, fast_mode=False)

    def _on_pan_start(self, canvas, event):
        self.canvas_states[canvas]["drag_start"] = (event.x, event.y)

    def _on_pan_move(self, canvas, event):
        st = self.canvas_states[canvas]
        dx = event.x - st["drag_start"][0]
        dy = event.y - st["drag_start"][1]
        st["drag_start"] = (event.x, event.y)
        st["pan_x"] += dx
        st["pan_y"] -= dy
        self._redraw_canvas(canvas, fast_mode=True)

    def _on_pan_release(self, canvas, _event):
        self._redraw_canvas(canvas, fast_mode=False)

    def _on_zoom(self, canvas, event):
        st = self.canvas_states[canvas]
        st["zoom"] *= 1.12 if event.delta > 0 else 0.88
        self._redraw_canvas(canvas, fast_mode=True)

        if st["zoom_timer"] is not None:
            self.after_cancel(st["zoom_timer"])
        st["zoom_timer"] = self.after(150, lambda c=canvas: self._finish_zoom(c))

    def _finish_zoom(self, canvas):
        st = self.canvas_states.get(canvas)
        if st:
            st["zoom_timer"] = None
            self._redraw_canvas(canvas, fast_mode=False)

    def _redraw_both_canvases(self, highlight_idx=None):
        for c in (self.canvas_xy, self.canvas_xz):
            if c in self.canvas_states:
                self._redraw_canvas(c, highlight_idx=highlight_idx, fast_mode=False)

    def _redraw_canvas(self, canvas, highlight_idx=None, fast_mode=False):
        canvas.delete("all")
        st = self.canvas_states.get(canvas)
        if not st:
            return
        if highlight_idx is not None:
            st["highlight_index"] = highlight_idx

        model_obj = st["model"]
        vertices = model_obj.raw_data["vertices"]
        faces = model_obj.raw_data["faces"]
        filtered_issues = self._get_filtered_issues(model_obj)
        coords_func = st["coords_func"]
        hl_idx = st["highlight_index"]

        zoom = st["zoom"]
        pan_x = st["pan_x"]
        pan_y = st["pan_y"]
        base_scale = st["base_scale"]
        off_u = st["base_offset_u"]
        off_v = st["base_offset_v"]
        c_size = st["c_size"]

        def project(v):
            u, w = coords_func(v)
            px = u * base_scale * zoom + off_u * zoom + pan_x
            py = c_size - (w * base_scale * zoom + off_v * zoom + pan_y)
            return px, py

        err_faces = {iss.index for iss in filtered_issues if iss.error_type != "DUPLICATE_VERTEX"}

        if not fast_mode:
            drawn_edges = set()
            step = max(1, len(faces) // 8000)

            for idx, face in enumerate(faces):
                is_err = (idx in err_faces) or (idx == hl_idx)
                if not is_err and (idx % step != 0):
                    continue

                v_idxs = [int(it[0]) if isinstance(it, (tuple, list)) else int(it) for it in face]
                pts = [project(vertices[vi]) for vi in v_idxs if 0 <= vi < len(vertices)]
                if len(pts) < 2:
                    continue

                for i in range(len(pts)):
                    e_key = tuple(sorted((v_idxs[i], v_idxs[(i + 1) % len(v_idxs)])))
                    if not is_err and e_key in drawn_edges:
                        continue
                    drawn_edges.add(e_key)

                    if idx == hl_idx:
                        color = "#28a745"
                        width = 3
                    elif idx in err_faces:
                        color = "#ff3b3b"
                        width = 2
                    else:
                        color = "#2c2c2c"
                        width = 1

                    p0, p1 = pts[i], pts[(i + 1) % len(pts)]
                    canvas.create_line(p0[0], p0[1], p1[0], p1[1], fill=color, width=width)

        for iss in filtered_issues[:600]:
            if iss.error_type == "DUPLICATE_VERTEX" and 0 <= iss.index < len(vertices):
                px, py = project(vertices[iss.index])
                c = "#28a745" if iss.index == hl_idx else "#ffffff"
                r = 4 if iss.index == hl_idx else 3
                canvas.create_oval(px - r, py - r, px + r, py + r, fill=c, outline="#0a0a0a")
            elif fast_mode and iss.error_type != "DUPLICATE_VERTEX" and 0 <= iss.index < len(faces):
                face = faces[iss.index]
                xs, ys = [], []
                for it in face:
                    vi = int(it[0]) if isinstance(it, (tuple, list)) else int(it)
                    if 0 <= vi < len(vertices):
                        px, py = project(vertices[vi])
                        xs.append(px)
                        ys.append(py)
                if xs and ys:
                    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                    c = "#28a745" if iss.index == hl_idx else "#ff3b3b"
                    r = 4 if iss.index == hl_idx else 2.5
                    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=c, outline="#0a0a0a")
