import math
import os
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import obj_parser
from domain_classes import (
    DegenerateFaceRule,
    DuplicateVertexRule,
    Issue,
    Model3D,
    NormalRule,
    validate_model_chunk_worker,
)


def _split_ranges(total: int, parts: int) -> list[tuple[int, int]]:
    if total <= 0:
        return [(0, 0)]
    parts = max(1, min(parts, total))
    step = math.ceil(total / parts)
    return [(s, min(total, s + step)) for s in range(0, total, step)]


def _deduplicate_dicts(raw_issues: list[dict]) -> list[Issue]:
    seen: set[tuple[str, int]] = set()
    unique: list[Issue] = []
    for d in raw_issues:
        iss = Issue.from_dict(d)
        key = (iss.error_type, iss.index)
        if key not in seen:
            seen.add(key)
            unique.append(iss)
    return unique


def _resolve_model_path() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]

    base_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(base_dir, "test_models")
    zip_path = os.path.join(base_dir, "test_models.zip")

    if not os.path.isdir(models_dir) and os.path.isfile(zip_path):
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(base_dir)

    candidates = [
        os.path.join(models_dir, "тело1 .obj"),
        os.path.join(models_dir, "тело1.obj"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    if os.path.isdir(models_dir):
        obj_files: list[str] = []
        for root, _, files in os.walk(models_dir):
            for fname in files:
                low = fname.lower()
                if low.endswith(".obj") and "broken" not in low and "corrupt" not in low:
                    obj_files.append(os.path.join(root, fname))
        if obj_files:
            return max(obj_files, key=os.path.getsize)

    return candidates[0]


def run_benchmark(file_path: str, workers: int = 4) -> None:
    if not os.path.isfile(file_path):
        print(f"Файл не знайдено: {file_path}")
        return

    print(f"Завантаження моделі: {file_path} ...")
    raw = obj_parser.parse_obj(file_path)
    verts = raw["vertices"]
    faces = raw["faces"]
    print(f"Вершин: {len(verts):,} | Граней: {len(faces):,} | Виконавців (частин моделі): n = {workers}\n")

    rules = [
        DuplicateVertexRule(tolerance=1e-6, enabled=True),
        DegenerateFaceRule(tolerance=1e-12, enabled=True),
        NormalRule(tolerance=1e-12, enabled=True),
    ]
    rules_cfg = [r.to_dict() for r in rules]

    v_ranges = _split_ranges(len(verts), workers)
    f_ranges = _split_ranges(len(faces), workers)
    chunks = max(len(v_ranges), len(f_ranges))

    # 1. Однопотоковий режим (T1) — класичний ООП-виклик model.validate(rules) -> rule.check()
    model_single = Model3D(name="benchmark_single", file_path=file_path, raw_data=raw)
    t0 = time.perf_counter()
    res_single = model_single.validate(rules)
    t1 = time.perf_counter() - t0

    # 2. ThreadPoolExecutor (перевірка виділених сегментів моделі у потоках через rule.check())
    t0 = time.perf_counter()
    raw_threads: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = []
        for i in range(chunks):
            v_start, v_end = v_ranges[i] if i < len(v_ranges) else (0, 0)
            f_start, f_end = f_ranges[i] if i < len(f_ranges) else (0, 0)
            futs.append(
                ex.submit(
                    validate_model_chunk_worker,
                    verts[v_start:v_end],
                    faces[f_start:f_end],
                    verts if f_start < f_end else [],
                    v_start,
                    f_start,
                    rules_cfg,
                )
            )
        for f in as_completed(futs):
            raw_threads.extend(f.result())
    res_threads = _deduplicate_dicts(raw_threads)
    t_thread = time.perf_counter() - t0

    # 3. ProcessPoolExecutor (перевірка виділених сегментів моделі у процесах через rule.check())
    t0 = time.perf_counter()
    raw_procs: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = []
        for i in range(chunks):
            v_start, v_end = v_ranges[i] if i < len(v_ranges) else (0, 0)
            f_start, f_end = f_ranges[i] if i < len(f_ranges) else (0, 0)
            futs.append(
                ex.submit(
                    validate_model_chunk_worker,
                    verts[v_start:v_end],
                    faces[f_start:f_end],
                    verts if f_start < f_end else [],
                    v_start,
                    f_start,
                    rules_cfg,
                )
            )
        for f in as_completed(futs):
            raw_procs.extend(f.result())
    res_procs = _deduplicate_dicts(raw_procs)
    t_proc = time.perf_counter() - t0

    print(f"1. Однопотоковий режим (T1):   {t1:.4f} с | Помилок: {len(res_single)} | S = 1.00x")
    print(f"2. ThreadPoolExecutor (n={workers}):  {t_thread:.4f} с | Помилок: {len(res_threads)} | S = {t1 / t_thread:.2f}x")
    print(f"3. ProcessPoolExecutor (n={workers}): {t_proc:.4f} с | Помилок: {len(res_procs)} | S = {t1 / t_proc:.2f}x")


if __name__ == "__main__":
    run_benchmark(_resolve_model_path(), workers=4)
