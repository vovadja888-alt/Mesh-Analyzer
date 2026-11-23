import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import math_logic
import obj_parser


def _split_ranges(total: int, parts: int) -> list[tuple[int, int]]:
    parts = max(1, min(parts, total))
    step = math.ceil(total / parts)
    return [(s, min(total, s + step)) for s in range(0, total, step)]


def run_benchmark(file_path: str, workers: int = 4) -> None:
    if not os.path.isfile(file_path):
        print(f"Файл не знайдено: {file_path}")
        return

    print(f"Завантаження моделі: {file_path} ...")
    raw = obj_parser.parse_obj(file_path)
    verts = raw["vertices"]
    faces = raw["faces"]
    print(f"Вершин: {len(verts):,} | Граней: {len(faces):,} | Виконавців (частин моделі): n = {workers}\n")

    rules_cfg = [
        {"type": "DuplicateVertexRule", "name": "Дублікати вершин", "tolerance": 1e-6, "enabled": True},
        {"type": "DegenerateFaceRule", "name": "Вироджені та n-гони", "tolerance": 1e-12, "enabled": True},
        {"type": "NormalRule", "name": "Орієнтація нормалей", "tolerance": 1e-12, "enabled": True},
    ]

    v_ranges = _split_ranges(len(verts), workers)
    f_ranges = _split_ranges(len(faces), workers)
    chunks = max(len(v_ranges), len(f_ranges))

    # 1. Однопотоковий режим (T1)
    t0 = time.perf_counter()
    res_single = math_logic.validate_model_chunk_worker(verts, faces, (0, len(verts)), (0, len(faces)), rules_cfg)
    t1 = time.perf_counter() - t0

    # 2. ThreadPoolExecutor (перевірка частин моделі у потоках)
    t0 = time.perf_counter()
    res_threads = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(
                math_logic.validate_model_chunk_worker,
                verts,
                faces,
                v_ranges[i] if i < len(v_ranges) else (0, 0),
                f_ranges[i] if i < len(f_ranges) else (0, 0),
                rules_cfg,
            )
            for i in range(chunks)
        ]
        for f in as_completed(futs):
            res_threads.extend(f.result())
    t_thread = time.perf_counter() - t0

    # 3. ProcessPoolExecutor (перевірка частин моделі у процесах)
    t0 = time.perf_counter()
    res_procs = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(
                math_logic.validate_model_chunk_worker,
                verts,
                faces,
                v_ranges[i] if i < len(v_ranges) else (0, 0),
                f_ranges[i] if i < len(f_ranges) else (0, 0),
                rules_cfg,
            )
            for i in range(chunks)
        ]
        for f in as_completed(futs):
            res_procs.extend(f.result())
    t_proc = time.perf_counter() - t0

    print(f"1. Однопотоковий режим (T1):   {t1:.4f} с | Помилок: {len(res_single)} | S = 1.00x")
    print(f"2. ThreadPoolExecutor (n={workers}):  {t_thread:.4f} с | Помилок: {len(res_threads)} | S = {t1 / t_thread:.2f}x")
    print(f"3. ProcessPoolExecutor (n={workers}): {t_proc:.4f} с | Помилок: {len(res_procs)} | S = {t1 / t_proc:.2f}x")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "test_models/тело1.obj"
    run_benchmark(target, workers=4)
