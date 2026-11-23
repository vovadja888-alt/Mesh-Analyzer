# ШІ: Контролер MVC для координації фонового парсингу OBJ (threading.Thread) та паралельної перевірки правил (ProcessPoolExecutor). Змінено: додано маркування авторства та синхронізовано з оновленим DegenerateFaceRule.
import logging
import math
import os
import queue
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
import math_logic
import obj_parser
from domain_classes import (
    DuplicateVertexRule,
    DegenerateFaceRule,
    Issue,
    Model3D,
    NormalRule,
    Project,
    ProjectStorage,
)


def _split_ranges(total: int, parts: int) -> list[tuple[int, int]]:
    if total <= 0:
        return [(0, 0)]
    parts = max(1, min(parts, total))
    step = math.ceil(total / parts)
    ranges = []
    for start in range(0, total, step):
        ranges.append((start, min(total, start + step)))
    return ranges


def _batch_model_worker(model_name: str, file_path: str, rules_cfg: list[dict]) -> dict:
    """Воркер для паралельної перевірки окремої моделі при пакетному запуску по проєкту."""
    raw = obj_parser.parse_obj(file_path)
    verts = raw["vertices"]
    faces = raw["faces"]
    raw_issues = math_logic.validate_model_chunk_worker(
        verts, faces, (0, len(verts)), (0, len(faces)), rules_cfg
    )
    return {
        "name": model_name,
        "file_path": file_path,
        "vertex_count": len(verts),
        "face_count": len(faces),
        "issues": raw_issues,
    }


class MeshAnalyzerController:
    def __init__(self, storage_path: str = "projects.json"):
        self.storage = ProjectStorage(storage_path)
        self.project: Project = self.storage.load_all()
        self.current_model: Model3D | None = self.project.models[0] if self.project.models else None
        self.cancel_event = threading.Event()
        self.result_queue: queue.Queue = queue.Queue()
        self._worker_thread: threading.Thread | None = None

    # ==================== CRUD ПРОЄКТІВ ====================
    def get_project_names(self) -> list[str]:
        return list(self.storage.projects.keys())

    def switch_project(self, project_name: str) -> Project:
        self.project = self.storage.set_active(project_name)
        self.current_model = self.project.models[0] if self.project.models else None
        logging.info("Перемкнуто активний проєкт на: %s", self.project.name)
        return self.project

    def create_project(self, name: str) -> Project:
        self.project = self.storage.create_or_select_project(name)
        self.current_model = None
        logging.info("Створено новий проєкт: %s", self.project.name)
        return self.project

    def rename_project(self, new_name: str) -> Project:
        self.project = self.storage.rename_active_project(new_name)
        logging.info("Проєкт перейменовано на: %s", self.project.name)
        return self.project

    def delete_active_project(self) -> Project:
        old_name = self.project.name
        self.project = self.storage.delete_project(old_name)
        self.current_model = self.project.models[0] if self.project.models else None
        logging.info("Видалено проєкт: %s", old_name)
        return self.project

    def import_project_json(self, json_path: str) -> Project:
        temp_storage = ProjectStorage(json_path)
        imported = temp_storage.load_all()
        for proj in temp_storage.projects.values():
            self.storage.projects[proj.name] = proj
        self.storage.active_project_name = imported.name
        self.storage.save_all()
        self.project = imported
        self.current_model = self.project.models[0] if self.project.models else None
        logging.info("Імпортовано проєкт(и) з %s", json_path)
        return self.project

    def export_project_json(self, json_path: str) -> None:
        self.storage.save_all()
        with open(json_path, "w", encoding="utf-8") as f:
            import json
            json.dump(self.project.to_dict(), f, ensure_ascii=False, indent=2)
        logging.info("Експортовано проєкт «%s» у %s", self.project.name, json_path)

    # ==================== CRUD ПРАВИЛ (ОКРЕМІ ДОПУСКИ) ====================
    def update_rules(
        self,
        dup_enabled: bool,
        dup_tol: float,
        deg_enabled: bool,
        deg_tol: float,
        norm_enabled: bool,
        norm_tol: float,
    ) -> None:
        new_rules = [
            DuplicateVertexRule(tolerance=dup_tol, enabled=dup_enabled),
            DegenerateFaceRule(tolerance=deg_tol, enabled=deg_enabled),
            NormalRule(tolerance=norm_tol, enabled=norm_enabled),
        ]
        self.project.rules = new_rules
        self.storage.save_all()
        logging.info(
            "Оновлено правила: Dup=(%s, %g), Deg=(%s, %g), Norm=(%s, %g)",
            dup_enabled, dup_tol, deg_enabled, deg_tol, norm_enabled, norm_tol,
        )

    # ==================== CRUD МОДЕЛЕЙ БЕЗ ЗАПУСКУ АНАЛІЗУ ====================
    def add_model_without_analysis(self, file_path: str, custom_name: str | None = None) -> Model3D:
        if not file_path or not os.path.isfile(file_path):
            raise FileNotFoundError("Вкажіть існуючий файл формату .obj.")
        name = custom_name.strip() if custom_name and custom_name.strip() else os.path.basename(file_path)
        model = Model3D(name=name, file_path=file_path, analyzed=False)
        self.project.add_model(model)
        self.current_model = model
        self.storage.save_all()
        logging.info("Додано модель без аналізу: %s (%s)", model.name, file_path)
        return model

    def edit_model(self, old_name: str, new_name: str, new_path: str) -> Model3D:
        updated = self.project.update_model(old_name, new_name, new_path)
        self.current_model = updated
        self.storage.save_all()
        logging.info("Відредаговано модель «%s» -> «%s» (%s)", old_name, new_name, new_path)
        return updated

    def delete_model(self, model_name: str) -> None:
        if self.project.remove_model(model_name):
            if self.current_model and self.current_model.name == model_name:
                self.current_model = self.project.models[0] if self.project.models else None
            self.storage.save_all()
            logging.info("Видалено модель: %s", model_name)

    def select_model_for_preview(self, model_name: str) -> Model3D | None:
        model = self.project.get_model(model_name)
        if model is None:
            return None
        if not model.vertices and os.path.isfile(model.file_path):
            raw = obj_parser.parse_obj(model.file_path)
            model.load_geometry(raw)
        self.current_model = model
        return model

    # ==================== ПАРАЛЕЛЬНИЙ АНАЛІЗ ЧАСТИН ОДНІЄЇ МОДЕЛІ ====================
    def start_analysis(self, file_path: str, model_name: str | None = None) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            raise RuntimeError("Аналіз уже виконується. Дочекайтеся завершення або натисніть «Скасувати».")
        if not file_path or not os.path.isfile(file_path):
            raise FileNotFoundError(f"Файл моделі не знайдено: {file_path}")

        active_rules = [r for r in self.project.rules if r.enabled]
        if not active_rules:
            raise ValueError("Увімкніть хоча б одне правило перевірки.")

        self.cancel_event.clear()
        rules_cfg = [r.to_dict() for r in active_rules]
        target_name = model_name.strip() if model_name and model_name.strip() else os.path.basename(file_path)

        self._worker_thread = threading.Thread(
            target=self._single_model_chunked_pipeline,
            args=(target_name, file_path, rules_cfg),
            daemon=True,
        )
        self._worker_thread.start()

    def _single_model_chunked_pipeline(self, model_name: str, file_path: str, rules_cfg: list[dict]) -> None:
        t0 = time.perf_counter()
        try:
            self.result_queue.put(("progress", 0.05, "Читання та розбір OBJ-файлу..."))
            raw_data = obj_parser.parse_obj(
                file_path,
                cancel_event=self.cancel_event,
                progress_callback=lambda pct, msg: self.result_queue.put(("progress", pct, msg)),
            )

            if self.cancel_event.is_set():
                raise obj_parser.AnalysisCancelledError("Операцію скасовано користувачем.")

            verts = raw_data["vertices"]
            faces = raw_data["faces"]
            model_obj = Model3D(name=model_name, file_path=file_path, raw_data=raw_data)

            # Розбиваємо геометрію моделі на частини (чанки) для паралельної обробки в ProcessPoolExecutor
            workers_count = min(4, max(1, os.cpu_count() or 2))
            if len(verts) < 2000 and len(faces) < 2000:
                workers_count = 1

            v_ranges = _split_ranges(len(verts), workers_count)
            f_ranges = _split_ranges(len(faces), workers_count)
            chunks_total = max(len(v_ranges), len(f_ranges))

            self.result_queue.put(
                ("progress", 0.50, f"Паралельна перевірка {chunks_total} частин моделі ({workers_count} проц.)...")
            )

            collected_dicts: list[dict] = []
            if workers_count == 1:
                collected_dicts = math_logic.validate_model_chunk_worker(
                    verts, faces, (0, len(verts)), (0, len(faces)), rules_cfg
                )
            else:
                with ProcessPoolExecutor(max_workers=workers_count) as executor:
                    futures = []
                    for i in range(chunks_total):
                        vr = v_ranges[i] if i < len(v_ranges) else (0, 0)
                        fr = f_ranges[i] if i < len(f_ranges) else (0, 0)
                        futures.append(
                            executor.submit(
                                math_logic.validate_model_chunk_worker,
                                verts,
                                faces,
                                vr,
                                fr,
                                rules_cfg,
                            )
                        )

                    done_cnt = 0
                    for fut in as_completed(futures):
                        if self.cancel_event.is_set():
                            for pending in futures:
                                pending.cancel()
                            raise obj_parser.AnalysisCancelledError("Паралельну перевірку скасовано.")
                        collected_dicts.extend(fut.result())
                        done_cnt += 1
                        pct = 0.50 + 0.45 * (done_cnt / chunks_total)
                        self.result_queue.put(("progress", pct, f"Оброблено частин моделі: {done_cnt}/{chunks_total}"))

            issues = [Issue.from_dict(d) for d in collected_dicts]
            model_obj.set_issues_deduplicated(issues)
            self.project.add_model(model_obj)
            self.current_model = model_obj
            self.storage.save_all()

            elapsed = time.perf_counter() - t0
            logging.info(
                "Модель «%s» перевірено за %.3f с (%d вершин, %d граней, %d помилок)",
                model_obj.name, elapsed, model_obj.vertex_count, model_obj.face_count, len(model_obj.issues),
            )
            self.result_queue.put(("done", model_obj, elapsed))

        except obj_parser.AnalysisCancelledError as cancel_msg:
            logging.warning(str(cancel_msg))
            self.result_queue.put(("cancelled", str(cancel_msg)))
        except Exception as exc:
            logging.exception("Помилка під час аналізу моделі %s", file_path)
            self.result_queue.put(("error", str(exc)))

    # ==================== ПАРАЛЕЛЬНА ПЕРЕВІРКА ВСІХ МОДЕЛЕЙ ПРОЄКТУ ====================
    def start_batch_project_analysis(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            raise RuntimeError("Виконання уже триває.")
        if not self.project.models:
            raise ValueError("У поточному проєкті немає моделей для перевірки.")
        active_rules = [r for r in self.project.rules if r.enabled]
        if not active_rules:
            raise ValueError("Увімкніть хоча б одне правило перевірки.")

        self.cancel_event.clear()
        rules_cfg = [r.to_dict() for r in active_rules]
        targets = [(m.name, m.file_path) for m in self.project.models]

        self._worker_thread = threading.Thread(
            target=self._batch_models_pipeline,
            args=(targets, rules_cfg),
            daemon=True,
        )
        self._worker_thread.start()

    def _batch_models_pipeline(self, targets: list[tuple[str, str]], rules_cfg: list[dict]) -> None:
        t0 = time.perf_counter()
        try:
            workers = min(len(targets), max(1, os.cpu_count() or 2))
            self.result_queue.put(
                ("progress", 0.1, f"Паралельна перевірка {len(targets)} моделей ({workers} процесів)...")
            )
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_batch_model_worker, name, path, rules_cfg): name
                    for name, path in targets
                }
                completed = 0
                for fut in as_completed(futures):
                    if self.cancel_event.is_set():
                        for p in futures:
                            p.cancel()
                        raise obj_parser.AnalysisCancelledError("Пакетну перевірку моделей скасовано.")
                    res = fut.result()
                    model_obj = self.project.get_model(res["name"])
                    if model_obj is not None:
                        model_obj._cached_vertex_count = res["vertex_count"]
                        model_obj._cached_face_count = res["face_count"]
                        model_obj.set_issues_deduplicated([Issue.from_dict(d) for d in res["issues"]])
                    completed += 1
                    self.result_queue.put(
                        ("progress", completed / len(targets), f"Перевірено моделей: {completed}/{len(targets)}")
                    )

            self.storage.save_all()
            if self.current_model:
                self.select_model_for_preview(self.current_model.name)
            elapsed = time.perf_counter() - t0
            self.result_queue.put(("batch_done", len(targets), elapsed))
        except obj_parser.AnalysisCancelledError as msg:
            self.result_queue.put(("cancelled", str(msg)))
        except Exception as exc:
            logging.exception("Помилка пакетної перевірки моделей")
            self.result_queue.put(("error", str(exc)))

    def cancel_analysis(self) -> None:
        self.cancel_event.set()
        logging.info("Надіслано сигнал скасування (cancel_event.set()).")

    def export_current_model_xml(self, save_path: str) -> None:
        if self.current_model is None:
            raise ValueError("Спочатку оберіть модель для експорту звіту.")
        self.current_model.to_xml(save_path)
        logging.info("Звіт моделі «%s» збережено у %s", self.current_model.name, save_path)
