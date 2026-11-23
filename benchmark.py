# ШІ: Скрипт порівняльного бенчмаркінгу (T1, ThreadPoolExecutor, ProcessPoolExecutor). Змінено: замінено локальний шлях із кирилицею на відносний шлях через pathlib.Path до високополігональної моделі у test_models/.
import time
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import domain_classes

BASE_DIR = Path(__file__).resolve().parent
TEST_OBJ_PATH = str(BASE_DIR / "test_models" / "highpoly_120k_benchmark.obj")


def run_single_thread(model, rules):
    start = time.perf_counter()
    issues = []
    for rule in rules:
        issues.extend(rule.check(model))
    return time.perf_counter() - start, len(issues)


def run_thread_pool(model, rules, workers=3):
    start = time.perf_counter()
    issues = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(rule.check, model) for rule in rules]
        for fut in futures:
            issues.extend(fut.result())
    return time.perf_counter() - start, len(issues)


def run_process_pool(model, rules, workers=3):
    start = time.perf_counter()
    issues = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(domain_classes.run_rule_worker, rule, model) for rule in rules]
        for fut in futures:
            issues.extend(fut.result())
    return time.perf_counter() - start, len(issues)


if __name__ == "__main__":
    if not os.path.exists(TEST_OBJ_PATH):
        print(f"Файл не знайдено: {TEST_OBJ_PATH}")
        exit(1)

    model_name = os.path.basename(TEST_OBJ_PATH)
    print(f"Завантаження моделі '{model_name}'...")
    model = domain_classes.Model3D(model_name, TEST_OBJ_PATH)

    rules = [
        domain_classes.DuplicateVertexRule(1e-6),
        domain_classes.DegenerateFaceRule(1e-6),
        domain_classes.NormalRule(1e-6)
    ]

    print(f"Вершин: {len(model.vertices)} | Граней: {len(model.faces)}\n")

    t1, err1 = run_single_thread(model, rules)
    t_thread, err_t = run_thread_pool(model, rules, workers=3)
    t_proc, err_p = run_process_pool(model, rules, workers=3)

    s_thread = t1 / t_thread if t_thread > 0 else 1.0
    s_proc = t1 / t_proc if t_proc > 0 else 1.0

    print("РЕЗУЛЬТАТИ ТЕСТУ")
    print(f"1. Однопотоковий режим (T1):  {t1:.4f} сек (помилок: {err1})")
    print(f"2. ThreadPoolExecutor (n=3):  {t_thread:.4f} сек (помилок: {err_t}) | S = {s_thread:.2f}x")
    print(f"3. ProcessPoolExecutor (n=3): {t_proc:.4f} сек (помилок: {err_p}) | S = {s_proc:.2f}x")
