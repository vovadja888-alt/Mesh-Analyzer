import os
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import customtkinter as ctk
from controller import MeshAnalyzerController
from domain_classes import DegenerateFaceRule, DuplicateVertexRule, NormalRule

class ModelEditDialog(ctk.CTkToplevel):
    """Модальне вікно для додавання або редагування 3D-моделі у проєкті без запуску аналізу."""

    def __init__(self, parent, title: str, initial_name: str = "", initial_path: str = ""):
        super().__init__(parent)
        self.title(title)
        self.geometry("520x210")
        self.resizable(False, False)
        self.grab_set()
        self.result: tuple[str, str] | None = None

        ctk.CTkLabel(self, text="Назва моделі у проєкті:").pack(anchor="w", padx=16, pady=(14, 2))
        self.entry_name = ctk.CTkEntry(self, width=480)
        self.entry_name.insert(0, initial_name)
        self.entry_name.pack(padx=16)

        ctk.CTkLabel(self, text="Шлях до файлу (.obj):").pack(anchor="w", padx=16, pady=(10, 2))
        path_row = ctk.CTkFrame(self, fg_color="transparent")
        path_row.pack(fill="x", padx=16)
        self.entry_path = ctk.CTkEntry(path_row, width=385)
        self.entry_path.insert(0, initial_path)
        self.entry_path.pack(side="left")
        ctk.CTkButton(path_row, text="Огляд...", width=85, command=self._browse).pack(side="right")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(18, 10))
        ctk.CTkButton(btn_row, text="Зберегти", width=120, command=self._on_save).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Скасувати", width=110, fg_color="#555555", command=self.destroy).pack(side="right")

    def _browse(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Wavefront OBJ", "*.obj")])
        if path:
            self.entry_path.delete(0, "end")
            self.entry_path.insert(0, path)
            if not self.entry_name.get().strip():
                self.entry_name.insert(0, os.path.basename(path))

    def _on_save(self) -> None:
        name = self.entry_name.get().strip()
        path = self.entry_path.get().strip()
        if not name:
            messagebox.showwarning("Валідація", "Введіть назву моделі.", parent=self)
            return
        if not path or not os.path.isfile(path):
            messagebox.showwarning("Валідація", "Оберіть існуючий файл .obj.", parent=self)
            return
        self.result = (name, path)
        self.destroy()


class MeshAnalyzerView(ctk.CTk):
    def __init__(self, controller: MeshAnalyzerController):
        super().__init__()
        self.ctrl = controller
        self.title("MeshAnalyzer - Аналіз та валідація топології 3D-моделей")
        self.geometry("1340x820")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        if os.path.isfile("Icon.ico"):
            try:
                self.iconbitmap("Icon.ico")
            except Exception:
                pass

        self.zoom_scale = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._drag_start = (0, 0)
        self.highlighted_issue: tuple[str, int] | None = None
        self.sort_col = "name"
        self.sort_reverse = False

        self._build_top_project_bar()
        self._build_main_layout()
        self._sync_project_ui()
        self.after(100, self._poll_queue)

    # ==================== ВЕРХНЯ ПАНЕЛЬ ПРОЄКТІВ (МУЛЬТИПРОЄКТНІСТЬ) ====================
    def _build_top_project_bar(self) -> None:
        bar = ctk.CTkFrame(self)
        bar.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(bar, text="Активний проєкт:").pack(side="left", padx=(10, 6))
        self.combo_projects = ctk.CTkComboBox(
            bar, width=210, values=self.ctrl.get_project_names(), command=self._on_switch_project
        )
        self.combo_projects.pack(side="left", padx=4)

        self.entry_proj_name = ctk.CTkEntry(bar, width=190, placeholder_text="Назва проєкту...")
        self.entry_proj_name.pack(side="left", padx=6)

        ctk.CTkButton(bar, text="Новий", width=75, command=self._on_new_project).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="Перейменувати", width=115, command=self._on_rename_project).pack(side="left", padx=3)
        ctk.CTkButton(
            bar, text="Видалити проєкт", width=120, fg_color="#8B2635", hover_color="#6E1D29",
            command=self._on_delete_project
        ).pack(side="left", padx=3)

        ctk.CTkButton(bar, text="Експорт JSON", width=105, command=self._on_export_json).pack(side="right", padx=(4, 10))
        ctk.CTkButton(bar, text="Імпорт JSON", width=105, command=self._on_import_json).pack(side="right", padx=4)

    # ==================== ОСНОВНИЙ МАКЕТ ====================
    def _build_main_layout(self) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=5)

        left_panel = ctk.CTkFrame(container, width=540)
        left_panel.pack(side="left", fill="both", expand=False, padx=(0, 8))
        left_panel.pack_propagate(False)

        right_panel = ctk.CTkFrame(container)
        right_panel.pack(side="right", fill="both", expand=True)

        self._build_rules_panel(left_panel)
        self._build_analysis_controls(left_panel)
        self._build_models_table(left_panel)
        self._build_issues_table(left_panel)
        self._build_canvas_panel(right_panel)

    def _build_rules_panel(self, parent) -> None:
        box = ctk.CTkFrame(parent)
        box.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(box, text="Правила валідації та індивідуальні допуски (tolerance > 0):", font=("", 13, "bold")).pack(
            anchor="w", padx=8, pady=(6, 4)
        )

        # 1. DuplicateVertexRule
        r1 = ctk.CTkFrame(box, fg_color="transparent")
        r1.pack(fill="x", padx=8, pady=2)
        self.var_dup = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(r1, text="Дублікати вершин", variable=self.var_dup, width=180).pack(side="left")
        ctk.CTkLabel(r1, text="Допуск:").pack(side="left", padx=(8, 4))
        self.entry_tol_dup = ctk.CTkEntry(r1, width=95)
        self.entry_tol_dup.pack(side="left")

        # 2. DegenerateFaceRule
        r2 = ctk.CTkFrame(box, fg_color="transparent")
        r2.pack(fill="x", padx=8, pady=2)
        self.var_deg = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(r2, text="Вироджені та n-гони", variable=self.var_deg, width=180).pack(side="left")
        ctk.CTkLabel(r2, text="Допуск:").pack(side="left", padx=(8, 4))
        self.entry_tol_deg = ctk.CTkEntry(r2, width=95)
        self.entry_tol_deg.pack(side="left")

        # 3. NormalRule
        r3 = ctk.CTkFrame(box, fg_color="transparent")
        r3.pack(fill="x", padx=8, pady=2)
        self.var_norm = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(r3, text="Орієнтація нормалей", variable=self.var_norm, width=180).pack(side="left")
        ctk.CTkLabel(r3, text="Допуск:").pack(side="left", padx=(8, 4))
        self.entry_tol_norm = ctk.CTkEntry(r3, width=95)
        self.entry_tol_norm.pack(side="left")

        ctk.CTkButton(box, text="Застосувати допуски", height=28, command=self._on_apply_rules).pack(
            anchor="e", padx=8, pady=(4, 8)
        )

    def _build_analysis_controls(self, parent) -> None:
        box = ctk.CTkFrame(parent)
        box.pack(fill="x", padx=8, pady=4)

        file_row = ctk.CTkFrame(box, fg_color="transparent")
        file_row.pack(fill="x", padx=8, pady=(8, 4))
        self.entry_file = ctk.CTkEntry(file_row, placeholder_text="Шлях до .obj файлу...")
        self.entry_file.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(file_row, text="Огляд...", width=80, command=self._on_browse_file).pack(side="right")

        act_row = ctk.CTkFrame(box, fg_color="transparent")
        act_row.pack(fill="x", padx=8, pady=4)
        self.btn_run = ctk.CTkButton(act_row, text="Перевірити файл", width=130, command=self._on_run_single)
        self.btn_run.pack(side="left", padx=(0, 4))
        self.btn_batch = ctk.CTkButton(
            act_row, text="Перевірити всі в проєкті", width=165, fg_color="#1F6AA5", command=self._on_run_batch
        )
        self.btn_batch.pack(side="left", padx=4)
        self.btn_cancel = ctk.CTkButton(
            act_row, text="Скасувати", width=95, fg_color="#9E2A2B", hover_color="#781E1F",
            command=self._on_cancel_analysis
        )
        self.btn_cancel.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(box)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=8, pady=(4, 2))

        self.lbl_status = ctk.CTkLabel(box, text="Готово до роботи", text_color="#A0A0A0")
        self.lbl_status.pack(anchor="w", padx=8, pady=(0, 6))

    def _build_models_table(self, parent) -> None:
        box = ctk.CTkFrame(parent)
        box.pack(fill="both", expand=True, padx=8, pady=4)

        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(fill="x", padx=6, pady=(6, 4))
        ctk.CTkLabel(top, text="Моделі проєкту:", font=("", 12, "bold")).pack(side="left")
        self.entry_search = ctk.CTkEntry(top, width=155, placeholder_text="Пошук моделі...")
        self.entry_search.pack(side="right")
        self.entry_search.bind("<KeyRelease>", lambda _e: self._refresh_models_table())

        crud_row = ctk.CTkFrame(box, fg_color="transparent")
        crud_row.pack(fill="x", padx=6, pady=(0, 4))
        ctk.CTkButton(crud_row, text="+ Додати", width=85, height=26, command=self._on_add_model_crud).pack(
            side="left", padx=(0, 4)
        )
        ctk.CTkButton(crud_row, text="Редагувати", width=95, height=26, command=self._on_edit_model_crud).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            crud_row, text="Видалити", width=85, height=26, fg_color="#7A2021", command=self._on_delete_model_crud
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            crud_row, text="Перевірити обрану", width=130, height=26, command=self._on_analyze_selected_model
        ).pack(side="right")

        cols = ("name", "verts", "issues", "status")
        self.tree_models = ttk.Treeview(box, columns=cols, show="headings", height=6)
        self.tree_models.heading("name", text="Назва моделі", command=lambda: self._sort_models_by("name"))
        self.tree_models.heading("verts", text="Вершин", command=lambda: self._sort_models_by("vertices"))
        self.tree_models.heading("issues", text="Помилок", command=lambda: self._sort_models_by("issues"))
        self.tree_models.heading("status", text="Статус")

        self.tree_models.column("name", width=190)
        self.tree_models.column("verts", width=85, anchor="center")
        self.tree_models.column("issues", width=75, anchor="center")
        self.tree_models.column("status", width=120, anchor="center")
        self.tree_models.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.tree_models.bind("<<TreeviewSelect>>", self._on_model_select)

    def _build_issues_table(self, parent) -> None:
        box = ctk.CTkFrame(parent)
        box.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        flt = ctk.CTkFrame(box, fg_color="transparent")
        flt.pack(fill="x", padx=6, pady=(6, 4))
        self.combo_rule_flt = ctk.CTkComboBox(
            flt, width=155, values=["Усі правила", "DUPLICATE_VERTEX", "ZERO_NORMAL", "NOT_QUAD", "FLIPPED_NORMAL"],
            command=lambda _v: self._refresh_issues_table()
        )
        self.combo_rule_flt.set("Усі правила")
        self.combo_rule_flt.pack(side="left", padx=(0, 4))

        self.combo_sev_flt = ctk.CTkComboBox(
            flt, width=125, values=["Усі рівні", "Critical", "Warning", "Info"],
            command=lambda _v: self._refresh_issues_table()
        )
        self.combo_sev_flt.set("Усі рівні")
        self.combo_sev_flt.pack(side="left", padx=4)

        ctk.CTkButton(flt, text="Експорт XML", width=105, fg_color="#2B7A0B", command=self._on_export_xml).pack(
            side="right"
        )

        cols = ("idx", "type", "sev", "desc")
        self.tree_issues = ttk.Treeview(box, columns=cols, show="headings", height=7)
        self.tree_issues.heading("idx", text="Елемент")
        self.tree_issues.heading("type", text="Тип дефекту")
        self.tree_issues.heading("sev", text="Критичність")
        self.tree_issues.heading("desc", text="Опис")

        self.tree_issues.column("idx", width=70, anchor="center")
        self.tree_issues.column("type", width=130)
        self.tree_issues.column("sev", width=85, anchor="center")
        self.tree_issues.column("desc", width=210)
        self.tree_issues.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.tree_issues.bind("<<TreeviewSelect>>", self._on_issue_select)

    def _build_canvas_panel(self, parent) -> None:
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(top, text="Ортогональні проєкції 3D-сітки (XY та XZ)", font=("", 14, "bold")).pack(side="left")
        ctk.CTkButton(top, text="Скинути вигляд", width=115, command=self._reset_view).pack(side="right")

        canv_box = ctk.CTkFrame(parent, fg_color="transparent")
        canv_box.pack(fill="both", expand=True, padx=10, pady=4)

        self.canvas_xy = tk.Canvas(canv_box, bg="#141414", highlightthickness=1, highlightbackground="#333333")
        self.canvas_xy.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.canvas_xz = tk.Canvas(canv_box, bg="#141414", highlightthickness=1, highlightbackground="#333333")
        self.canvas_xz.pack(side="right", fill="both", expand=True, padx=(5, 0))

        for cv in (self.canvas_xy, self.canvas_xz):
            cv.bind("<MouseWheel>", self._on_zoom)
            cv.bind("<ButtonPress-1>", self._on_pan_start)
            cv.bind("<B1-Motion>", self._on_pan_move)
            cv.bind("<Configure>", lambda _e: self._redraw_projections())

        legend = (
            "Легенда: Сірі лінії - нормальні грані | Червоні лінії - пошкоджені грані | "
            "Жовті точки - дублікати вершин (Коліщатко - зум, ЛКМ - переміщення)"
        )
        ctk.CTkLabel(parent, text=legend, text_color="#B0B0B0").pack(anchor="w", padx=10, pady=(2, 8))

    # ==================== СИНХРОНІЗАЦІЯ UI ====================
    def _sync_project_ui(self) -> None:
        names = self.ctrl.get_project_names()
        self.combo_projects.configure(values=names)
        self.combo_projects.set(self.ctrl.project.name)
        self.entry_proj_name.delete(0, "end")
        self.entry_proj_name.insert(0, self.ctrl.project.name)

        for rule in self.ctrl.project.rules:
            if isinstance(rule, DuplicateVertexRule):
                self.var_dup.set(rule.enabled)
                self.entry_tol_dup.delete(0, "end")
                self.entry_tol_dup.insert(0, f"{rule.tolerance:g}")
            elif isinstance(rule, DegenerateFaceRule):
                self.var_deg.set(rule.enabled)
                self.entry_tol_deg.delete(0, "end")
                self.entry_tol_deg.insert(0, f"{rule.tolerance:g}")
            elif isinstance(rule, NormalRule):
                self.var_norm.set(rule.enabled)
                self.entry_tol_norm.delete(0, "end")
                self.entry_tol_norm.insert(0, f"{rule.tolerance:g}")

        self._refresh_models_table()
        self._refresh_issues_table()
        self._redraw_projections()

    def _refresh_models_table(self) -> None:
        for item in self.tree_models.get_children():
            self.tree_models.delete(item)

        query = self.entry_search.get().strip().lower()
        sorted_list = self.ctrl.project.sort_models(by=self.sort_col, reverse=self.sort_reverse)
        for m in sorted_list:
            if query and query not in m.name.lower():
                continue
            status_txt = "Перевірено" if m.analyzed else "Не перевірено"
            self.tree_models.insert("", "end", iid=m.name, values=(m.name, m.vertex_count, len(m.issues), status_txt))

    def _refresh_issues_table(self) -> None:
        for item in self.tree_issues.get_children():
            self.tree_issues.delete(item)

        model = self.ctrl.current_model
        if model is None:
            return

        r_flt = self.combo_rule_flt.get()
        s_flt = self.combo_sev_flt.get()
        for i, iss in enumerate(model.issues):
            if r_flt != "Усі правила" and iss.error_type != r_flt:
                continue
            if s_flt != "Усі рівні" and iss.severity != s_flt:
                continue
            self.tree_issues.insert(
                "", "end", iid=str(i), values=(f"#{iss.index}", iss.error_type, iss.severity, iss.description)
            )

    # ==================== ОБРОБНИКИ ПОДІЙ ====================
    def _on_switch_project(self, selected_name: str) -> None:
        self.ctrl.switch_project(selected_name)
        self._sync_project_ui()

    def _on_new_project(self) -> None:
        name = simpledialog.askstring("Новий проєкт", "Введіть назву нового проєкту:", parent=self)
        if name:
            try:
                self.ctrl.create_project(name)
                self._sync_project_ui()
            except Exception as exc:
                messagebox.showerror("Помилка", str(exc))

    def _on_rename_project(self) -> None:
        try:
            self.ctrl.rename_project(self.entry_proj_name.get())
            self._sync_project_ui()
        except Exception as exc:
            messagebox.showerror("Помилка", str(exc))

    def _on_delete_project(self) -> None:
        if messagebox.askyesno("Підтвердження", f"Видалити проєкт «{self.ctrl.project.name}»?"):
            self.ctrl.delete_active_project()
            self._sync_project_ui()

    def _on_import_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON файли", "*.json")])
        if path:
            try:
                self.ctrl.import_project_json(path)
                self._sync_project_ui()
            except Exception as exc:
                messagebox.showerror("Помилка імпорту", str(exc))

    def _on_export_json(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON файли", "*.json")])
        if path:
            try:
                self.ctrl.export_project_json(path)
                messagebox.showinfo("Успіх", "Проєкт збережено у JSON.")
            except Exception as exc:
                messagebox.showerror("Помилка експорту", str(exc))

    def _on_apply_rules(self) -> None:
        try:
            self.ctrl.update_rules(
                dup_enabled=self.var_dup.get(),
                dup_tol=float(self.entry_tol_dup.get()),
                deg_enabled=self.var_deg.get(),
                deg_tol=float(self.entry_tol_deg.get()),
                norm_enabled=self.var_norm.get(),
                norm_tol=float(self.entry_tol_norm.get()),
            )
            self.lbl_status.configure(text="Індивідуальні допуски правил збережено.", text_color="#4CC9F0")
        except Exception as exc:
            messagebox.showerror("Помилка валідації правил", str(exc))

    def _on_browse_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Wavefront OBJ", "*.obj")])
        if path:
            self.entry_file.delete(0, "end")
            self.entry_file.insert(0, path)

    def _on_add_model_crud(self) -> None:
        dlg = ModelEditDialog(self, title="Додати 3D-модель у проєкт")
        self.wait_window(dlg)
        if dlg.result:
            name, path = dlg.result
            try:
                self.ctrl.add_model_without_analysis(file_path=path, custom_name=name)
                self._refresh_models_table()
                self.lbl_status.configure(text=f"Модель «{name}» додано до проєкту.", text_color="#90BE6D")
            except Exception as exc:
                messagebox.showerror("Помилка", str(exc))

    def _on_edit_model_crud(self) -> None:
        sel = self.tree_models.selection()
        if not sel:
            messagebox.showinfo("Увага", "Оберіть модель у таблиці для редагування.")
            return
        old_name = sel[0]
        model = self.ctrl.project.get_model(old_name)
        if model is None:
            return
        dlg = ModelEditDialog(self, title="Редагувати модель", initial_name=model.name, initial_path=model.file_path)
        self.wait_window(dlg)
        if dlg.result:
            new_name, new_path = dlg.result
            try:
                self.ctrl.edit_model(old_name, new_name, new_path)
                self._refresh_models_table()
                self._refresh_issues_table()
                self._redraw_projections()
                self.lbl_status.configure(text=f"Модель «{new_name}» оновлено.", text_color="#4CC9F0")
            except Exception as exc:
                messagebox.showerror("Помилка редагування", str(exc))

    def _on_delete_model_crud(self) -> None:
        sel = self.tree_models.selection()
        if not sel:
            return
        name = sel[0]
        if messagebox.askyesno("Видалення", f"Видалити модель «{name}» із проєкту?"):
            self.ctrl.delete_model(name)
            self._refresh_models_table()
            self._refresh_issues_table()
            self._redraw_projections()

    def _on_analyze_selected_model(self) -> None:
        sel = self.tree_models.selection()
        if not sel:
            messagebox.showinfo("Увага", "Оберіть модель у таблиці.")
            return
        model = self.ctrl.project.get_model(sel[0])
        if model:
            self.entry_file.delete(0, "end")
            self.entry_file.insert(0, model.file_path)
            self._start_single_analysis(model.file_path, model.name)

    def _on_run_single(self) -> None:
        path = self.entry_file.get().strip()
        self._start_single_analysis(path, None)

    def _start_single_analysis(self, path: str, model_name: str | None) -> None:
        try:
            self._on_apply_rules()
            self.progress_bar.set(0)
            self.ctrl.start_analysis(path, model_name=model_name)
        except Exception as exc:
            messagebox.showerror("Помилка запуску", str(exc))

    def _on_run_batch(self) -> None:
        try:
            self._on_apply_rules()
            self.progress_bar.set(0)
            self.ctrl.start_batch_project_analysis()
        except Exception as exc:
            messagebox.showerror("Помилка пакетної перевірки", str(exc))

    def _on_cancel_analysis(self) -> None:
        self.ctrl.cancel_analysis()
        self.lbl_status.configure(text="Надсилання запиту на скасування...", text_color="#F9C74F")

    def _on_export_xml(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML звіти", "*.xml")])
        if path:
            try:
                self.ctrl.export_current_model_xml(path)
                messagebox.showinfo("Експорт XML", "Звіт успішно сформовано.")
            except Exception as exc:
                messagebox.showerror("Помилка експорту", str(exc))

    def _sort_models_by(self, col: str) -> None:
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col = col
            self.sort_reverse = False
        self._refresh_models_table()

    def _on_model_select(self, _event) -> None:
        sel = self.tree_models.selection()
        if not sel:
            return
        try:
            self.ctrl.select_model_for_preview(sel[0])
            self.highlighted_issue = None
            self._refresh_issues_table()
            self._redraw_projections()
        except Exception as exc:
            self.lbl_status.configure(text=f"Помилка завантаження геометрії: {exc}", text_color="#F94144")

    def _on_issue_select(self, _event) -> None:
        sel = self.tree_issues.selection()
        model = self.ctrl.current_model
        if not sel or model is None:
            return
        idx_in_list = int(sel[0])
        if 0 <= idx_in_list < len(model.issues):
            iss = model.issues[idx_in_list]
            self.highlighted_issue = (iss.error_type, iss.index)
            self._redraw_projections()

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self.ctrl.result_queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, pct, text = msg
                    self.progress_bar.set(pct)
                    self.lbl_status.configure(text=text, text_color="#4CC9F0")
                elif kind == "done":
                    _, model_obj, elapsed = msg
                    self.progress_bar.set(1.0)
                    self.lbl_status.configure(
                        text=f"Готово ({elapsed:.2f} с): {model_obj.name} — помилок: {len(model_obj.issues)}",
                        text_color="#90BE6D",
                    )
                    self._refresh_models_table()
                    self._refresh_issues_table()
                    self._redraw_projections()
                elif kind == "batch_done":
                    _, count, elapsed = msg
                    self.progress_bar.set(1.0)
                    self.lbl_status.configure(
                        text=f"Пакетну перевірку завершено ({count} моделей за {elapsed:.2f} с).",
                        text_color="#90BE6D",
                    )
                    self._refresh_models_table()
                    self._refresh_issues_table()
                    self._redraw_projections()
                elif kind == "cancelled":
                    self.progress_bar.set(0)
                    self.lbl_status.configure(text=msg[1], text_color="#F9C74F")
                elif kind == "error":
                    self.progress_bar.set(0)
                    self.lbl_status.configure(text=f"Помилка: {msg[1]}", text_color="#F94144")
                    messagebox.showerror("Помилка аналізу", msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ==================== 2D-ВІЗУАЛІЗАЦІЯ ПРОЄКЦІЙ ====================
    def _reset_view(self) -> None:
        self.zoom_scale = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._redraw_projections()

    def _on_zoom(self, event) -> None:
        factor = 1.15 if event.delta > 0 else 0.85
        self.zoom_scale = max(0.2, min(15.0, self.zoom_scale * factor))
        self._redraw_projections()

    def _on_pan_start(self, event) -> None:
        self._drag_start = (event.x, event.y)

    def _on_pan_move(self, event) -> None:
        self.pan_x += event.x - self._drag_start[0]
        self.pan_y += event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        self._redraw_projections()

    def _redraw_projections(self) -> None:
        self._draw_single_canvas(self.canvas_xy, mode="XY")
        self._draw_single_canvas(self.canvas_xz, mode="XZ")

    def _draw_single_canvas(self, canvas: tk.Canvas, mode: str) -> None:
        canvas.delete("all")
        w = max(10, canvas.winfo_width())
        h = max(10, canvas.winfo_height())
        canvas.create_text(12, 12, anchor="nw", text=f"Проєкція {mode}", fill="#CCCCCC", font=("Arial", 10, "bold"))

        model = self.ctrl.current_model
        if model is None or not model.vertices:
            return

        pts_2d = [(v.x, v.y) if mode == "XY" else (v.x, v.z) for v in model.vertices]
        xs = [p[0] for p in pts_2d]
        ys = [p[1] for p in pts_2d]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span = max(max_x - min_x, max_y - min_y, 1e-6)
        base_scale = (min(w, h) * 0.78) / span * self.zoom_scale
        cx_mid = (min_x + max_x) * 0.5
        cy_mid = (min_y + max_y) * 0.5

        def to_screen(px: float, py: float) -> tuple[float, float]:
            sx = w * 0.5 + (px - cx_mid) * base_scale + self.pan_x
            sy = h * 0.5 - (py - cy_mid) * base_scale + self.pan_y
            return sx, sy

        bad_faces = {iss.index for iss in model.issues if iss.error_type != "DUPLICATE_VERTEX"}
        dup_verts = {iss.index for iss in model.issues if iss.error_type == "DUPLICATE_VERTEX"}

        step = max(1, len(model.faces) // 15000)
        for f_idx in range(0, len(model.faces), step):
            if f_idx in bad_faces:
                continue
            face = model.faces[f_idx]
            coords = []
            for vi in face.vertex_indices:
                coords.extend(to_screen(*pts_2d[vi]))
            if len(coords) >= 6:
                canvas.create_polygon(coords, outline="#3E444C", fill="", width=1)

        for f_idx in bad_faces:
            if f_idx >= len(model.faces):
                continue
            face = model.faces[f_idx]
            coords = []
            for vi in face.vertex_indices:
                coords.extend(to_screen(*pts_2d[vi]))
            is_selected = self.highlighted_issue is not None and self.highlighted_issue[1] == f_idx
            color = "#00F5D4" if is_selected else "#E63946"
            width = 3 if is_selected else 1.5
            if len(coords) >= 6:
                canvas.create_polygon(coords, outline=color, fill="", width=width)

        for v_idx in dup_verts:
            if v_idx >= len(pts_2d):
                continue
            sx, sy = to_screen(*pts_2d[v_idx])
            is_selected = (
                self.highlighted_issue is not None
                and self.highlighted_issue[0] == "DUPLICATE_VERTEX"
                and self.highlighted_issue[1] == v_idx
            )
            r = 5 if is_selected else 3
            fill = "#00F5D4" if is_selected else "#FFD166"
            canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill=fill, outline="")
