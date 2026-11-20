import os
import threading
import queue
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

import obj_parser
import domain_classes


class MeshAnalyzerController:
    def __init__(self, json_storage_path: str = "projects.json"):
        self.json_storage_path = json_storage_path
        self.project = self._init_or_load_project()
        self.current_model: domain_classes.Model3D | None = None
        self.cancel_event = threading.Event()
        self.result_queue: queue.Queue = queue.Queue()

    def _init_or_load_project(self) -> domain_classes.Project:
        if os.path.exists(self.json_storage_path):
            try:
                return domain_classes.Project.load_from_json(self.json_storage_path)
            except Exception:
                pass
        return domain_classes.Project("Coursework 3D Validation")

    def create_new_project(self, name: str):
        self.project = domain_classes.Project(name)
        self.current_model = None
        self.project.save_to_json(self.json_storage_path)

    def rename_project(self, new_name: str):
        self.project.rename(new_name)
        self.project.save_to_json(self.json_storage_path)

    def import_project_json(self, json_path: str):
        self.project = domain_classes.Project.load_from_json(json_path)
        self.current_model = self.project.models[0] if self.project.models else None

    def export_project_json(self, json_path: str):
        self.project.save_to_json(json_path)

    def update_rules(self, enabled_rules: dict[str, bool], tolerance_str: str):
        try:
            tol = float(tolerance_str)
        except ValueError as e:
            raise ValueError("Допуск (tolerance) має бути числовим значенням (наприклад, 1e-6)!") from e

        if tol <= 0:
            raise ValueError("Допуск (tolerance) має бути додатним числом (> 0)!")

        if not any(enabled_rules.values()):
            raise ValueError("Потрібно обрати хоча б одне правило перевірки!")

        self.project.rules.clear()
        for r_type, is_enabled in enabled_rules.items():
            if is_enabled:
                self.project.add_or_update_rule(r_type, tol)
        self.project.save_to_json(self.json_storage_path)

    def delete_model(self, model_name: str):
        self.project.remove_model(model_name)
        if self.current_model and self.current_model.name == model_name:
            self.current_model = None
        self.project.save_to_json(self.json_storage_path)

    def get_filtered_sorted_models(self, search_query: str = "", sort_by: str = "errors") -> list[domain_classes.Model3D]:
        found = self.project.find_models(search_query)
        if sort_by == "vertices":
            return sorted(found, key=lambda m: len(m.vertices), reverse=True)
        if sort_by == "name":
            return sorted(found, key=lambda m: m.name.lower())
        return sorted(found, key=lambda m: len(m.issues), reverse=True)

    def start_analysis(self, file_path: str):
        if not file_path or not file_path.strip():
            raise ValueError("Вкажіть шлях до файлу .obj!")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл '{file_path}' не знайдено!")
        if not file_path.lower().endswith(".obj"):
            raise ValueError("Підтримуються лише файли формату .obj!")
        if not self.project.rules:
            raise ValueError("Не обрано жодного правила валідації!")

        self.cancel_event.clear()
        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                break

        worker_thread = threading.Thread(
            target=self._background_pipeline,
            args=(file_path.strip(), list(self.project.rules)),
            daemon=True
        )
        worker_thread.start()

    def cancel_analysis(self):
        self.cancel_event.set()

    def _background_pipeline(self, file_path: str, rules: list[domain_classes.ValidationRule]):
        try:
            self.result_queue.put(("progress", 0.15, "Розбір OBJ-файлу у фоновому потоці..."))
            if self.cancel_event.is_set():
                self.result_queue.put(("cancelled", None, "Операцію скасовано користувачем."))
                return

            raw_data = obj_parser.parse_obj(file_path)
            if self.cancel_event.is_set():
                self.result_queue.put(("cancelled", None, "Операцію скасовано користувачем."))
                return

            model_name = os.path.basename(file_path)
            model_obj = domain_classes.Model3D(model_name, file_path, raw_data=raw_data)
            self.result_queue.put(("progress", 0.40, f"Завантажено {len(model_obj.vertices)} вершин. Запуск перевірки..."))

            collected_issues: list[domain_classes.Issue] = []
            total_rules = len(rules)
            completed = 0

            with ProcessPoolExecutor(max_workers=min(3, total_rules)) as executor:
                future_to_rule = {
                    executor.submit(domain_classes.run_rule_worker, rule, model_obj): rule.name
                    for rule in rules
                }
                for future in as_completed(future_to_rule):
                    if self.cancel_event.is_set():
                        for f in future_to_rule:
                            f.cancel()
                        self.result_queue.put(("cancelled", None, "Перевірку скасовано користувачем."))
                        return

                    rule_issues = future.result()
                    collected_issues.extend(rule_issues)
                    completed += 1
                    prog = 0.40 + 0.50 * (completed / total_rules)
                    self.result_queue.put(("progress", prog, f"Виконано правило: {future_to_rule[future]}"))

            model_obj.set_issues_deduplicated(collected_issues)
            self.current_model = model_obj

            self.project.add_model(model_obj)
            self.project.save_to_json(self.json_storage_path)

            self.result_queue.put(("progress", 1.0, "Перевірку успішно завершено!"))
            self.result_queue.put(("success", model_obj, None))

        except Exception as exc:
            logging.error(f"Помилка під час аналізу '{file_path}': {exc}")
            self.result_queue.put(("error", str(exc), None))

    def export_current_model_xml(self, save_path: str):
        if self.current_model is None:
            raise ValueError("Немає активної перевіреної моделі для експорту!")
        self.current_model.to_xml(save_path)
        