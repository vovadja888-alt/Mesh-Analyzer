import math
from collections import defaultdict, deque


def find_duplicate_vertices(
    vertices: list[tuple[float, float, float]],
    tolerance: float = 1e-6,
    start_idx: int = 0,
    end_idx: int | None = None,
) -> list[int]:
    """
    Пошук дублікатів вершин методом просторового хешування (Spatial Hashing)
    з перевіркою 27 сусідніх комірок (3x3x3) та точним евклідовим порівнянням,
    щоб не пропускати близькі точки на межах комірок.
    Підтримує перевірку діапазону [start_idx:end_idx] для паралельної обробки частин моделі.
    """
    if tolerance <= 0:
        raise ValueError("Допуск (tolerance) має бути додатним числом.")

    n = len(vertices)
    if end_idx is None or end_idx > n:
        end_idx = n

    tol_sq = tolerance * tolerance
    inv_tol = 1.0 / tolerance
    grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    duplicates: list[int] = []

    # Якщо перевіряється чанк [start_idx:end_idx], попередньо індексуємо попередні вершини
    # в околиці, або виконуємо повну індексацію для детермінованого пошуку першого входження
    for idx in range(0, end_idx):
        x, y, z = vertices[idx]
        cx = math.floor(x * inv_tol)
        cy = math.floor(y * inv_tol)
        cz = math.floor(z * inv_tol)

        is_dup = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    bucket = grid.get((cx + dx, cy + dy, cz + dz))
                    if not bucket:
                        continue
                    for ref_idx in bucket:
                        rx, ry, rz = vertices[ref_idx]
                        dist_sq = (x - rx) ** 2 + (y - ry) ** 2 + (z - rz) ** 2
                        if dist_sq <= tol_sq:
                            is_dup = True
                            break
                    if is_dup:
                        break
                if is_dup:
                    break
            if is_dup:
                break

        if is_dup:
            if idx >= start_idx:
                duplicates.append(idx)
        else:
            grid[(cx, cy, cz)].append(idx)

    return duplicates


def compute_face_normal(
    vertices: list[tuple[float, float, float]],
    face: tuple[int, ...],
) -> tuple[float, float, float]:
    """Обчислення ненормованого вектора нормалі полігона через векторний добуток."""
    if len(face) < 3:
        return (0.0, 0.0, 0.0)
    v0 = vertices[face[0]]
    v1 = vertices[face[1]]
    v2 = vertices[face[2]]
    e1x, e1y, e1z = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
    e2x, e2y, e2z = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
    nx = e1y * e2z - e1z * e2y
    ny = e1z * e2x - e1x * e2z
    nz = e1x * e2y - e1y * e2x
    return (nx, ny, nz)


def find_degenerate_and_non_quad_faces(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    zero_tolerance: float = 1e-12,
    start_idx: int = 0,
    end_idx: int | None = None,
) -> tuple[list[int], list[int]]:
    """
    Пошук вироджених граней нульової площі (ZERO_NORMAL) та нечотирикутних полігонів (NOT_QUAD)
    у заданому діапазоні граней [start_idx:end_idx].
    """
    if zero_tolerance <= 0:
        raise ValueError("Допуск площі грані має бути додатним.")

    m = len(faces)
    if end_idx is None or end_idx > m:
        end_idx = m

    zero_normals: list[int] = []
    non_quads: list[int] = []
    tol_sq = zero_tolerance * zero_tolerance

    for f_idx in range(start_idx, end_idx):
        face = faces[f_idx]
        if len(face) != 4:
            non_quads.append(f_idx)
        nx, ny, nz = compute_face_normal(vertices, face)
        if (nx * nx + ny * ny + nz * nz) <= tol_sq:
            zero_normals.append(f_idx)

    return zero_normals, non_quads


def find_flipped_normals_bfs(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    zero_tolerance: float = 1e-12,
    start_idx: int = 0,
    end_idx: int | None = None,
) -> list[int]:
    """
    Топологічний аналіз узгодженості нормалей методом BFS по графу суміжності ребер.
    Виключає хибні спрацьовування на гострих кутах та підтримує фільтрацію за діапазоном граней.
    """
    if zero_tolerance <= 0:
        raise ValueError("Допуск нормалі має бути додатним.")

    m = len(faces)
    if end_idx is None or end_idx > m:
        end_idx = m

    tol_sq = zero_tolerance * zero_tolerance
    valid_faces: set[int] = set()
    face_normals: dict[int, tuple[float, float, float]] = {}

    for idx, face in enumerate(faces):
        nx, ny, nz = compute_face_normal(vertices, face)
        if (nx * nx + ny * ny + nz * nz) > tol_sq:
            valid_faces.add(idx)
            face_normals[idx] = (nx, ny, nz)

    edge_map: dict[tuple[int, int], list[tuple[int, bool]]] = defaultdict(list)
    for f_idx in valid_faces:
        face = faces[f_idx]
        k = len(face)
        for i in range(k):
            a = face[i]
            b = face[(i + 1) % k]
            if a == b:
                continue
            key = (a, b) if a < b else (b, a)
            forward = a < b
            edge_map[key].append((f_idx, forward))

    adjacency: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    for incident in edge_map.values():
        if len(incident) == 2:
            (f1, dir1), (f2, dir2) = incident
            # У коректній сітці суміжні грані проходять спільне ребро у протилежних напрямках
            is_consistent = dir1 != dir2
            adjacency[f1].append((f2, is_consistent))
            adjacency[f2].append((f1, is_consistent))

    orientation: dict[int, int] = {}
    flipped: list[int] = []

    for f_idx in sorted(valid_faces):
        if f_idx in orientation:
            continue

        component: list[int] = []
        queue = deque([f_idx])
        orientation[f_idx] = 0

        while queue:
            curr = queue.popleft()
            component.append(curr)
            curr_state = orientation[curr]
            for neighbor, is_consistent in adjacency.get(curr, ()):
                expected = curr_state if is_consistent else (1 - curr_state)
                if neighbor not in orientation:
                    orientation[neighbor] = expected
                    queue.append(neighbor)

        # Визначаємо домінуючу орієнтацію компоненти (більшість граней вважається еталонною)
        count_0 = sum(1 for c in component if orientation[c] == 0)
        count_1 = len(component) - count_0
        inverted_state = 1 if count_0 >= count_1 else 0

        for c in component:
            if orientation[c] == inverted_state and start_idx <= c < end_idx:
                flipped.append(c)

    return sorted(flipped)


def validate_model_chunk_worker(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    v_range: tuple[int, int],
    f_range: tuple[int, int],
    rules_config: list[dict],
) -> list[dict]:
    """
    Функція-воркер для ProcessPoolExecutor: перевіряє виділену ЧАСТИНУ (чанк) 3D-моделі
    за всіма активними правилами з їхніми індивідуальними допусками tolerance.
    """
    issues: list[dict] = []
    v_start, v_end = v_range
    f_start, f_end = f_range

    for cfg in rules_config:
        if not cfg.get("enabled", True):
            continue
        r_type = cfg["type"]
        tol = float(cfg["tolerance"])

        if r_type == "DuplicateVertexRule" and v_start < v_end:
            dups = find_duplicate_vertices(vertices, tolerance=tol, start_idx=v_start, end_idx=v_end)
            for idx in dups:
                issues.append({
                    "index": idx,
                    "error_type": "DUPLICATE_VERTEX",
                    "rule_name": cfg["name"],
                    "severity": "Warning",
                    "description": f"Дублікат вершини #{idx} (допуск {tol:g})",
                })

        elif r_type == "DegenerateFaceRule" and f_start < f_end:
            zeros, non_quads = find_degenerate_and_non_quad_faces(
                vertices, faces, zero_tolerance=tol, start_idx=f_start, end_idx=f_end
            )
            for idx in zeros:
                issues.append({
                    "index": idx,
                    "error_type": "ZERO_NORMAL",
                    "rule_name": cfg["name"],
                    "severity": "Critical",
                    "description": f"Вироджена грань #{idx} з нульовою площею (допуск {tol:g})",
                })
            for idx in non_quads:
                issues.append({
                    "index": idx,
                    "error_type": "NOT_QUAD",
                    "rule_name": cfg["name"],
                    "severity": "Info",
                    "description": f"Нечотирикутна грань #{idx} ({len(faces[idx])} вершин)",
                })

        elif r_type == "NormalRule" and f_start < f_end:
            flipped = find_flipped_normals_bfs(
                vertices, faces, zero_tolerance=tol, start_idx=f_start, end_idx=f_end
            )
            for idx in flipped:
                issues.append({
                    "index": idx,
                    "error_type": "FLIPPED_NORMAL",
                    "rule_name": cfg["name"],
                    "severity": "Critical",
                    "description": f"Інвертована нормаль грані #{idx} (допуск {tol:g})",
                })

    return issues
