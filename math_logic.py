import math
from collections import defaultdict, deque


def find_duplicate_vertices(
    vertices: list[tuple[float, float, float]],
    tolerance: float = 1e-6,
    index_offset: int = 0,
) -> list[int]:
    """
    Пошук дублікатів вершин методом просторового хешування (Spatial Hashing)
    з перевіркою 27 сусідніх комірок (3x3x3) та точним евклідовим порівнянням.
    Обходить виключно переданий сегмент вершин (O(N/k) у паралельному режимі),
    повертаючи глобальні індекси з урахуванням index_offset.
    """
    if tolerance <= 0:
        raise ValueError("Допуск (tolerance) має бути додатним числом.")

    tol_sq = tolerance * tolerance
    inv_tol = 1.0 / tolerance
    grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    duplicates: list[int] = []

    for local_idx, (x, y, z) in enumerate(vertices):
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
                    for ref_local_idx in bucket:
                        rx, ry, rz = vertices[ref_local_idx]
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
            duplicates.append(index_offset + local_idx)
        else:
            grid[(cx, cy, cz)].append(local_idx)

    return duplicates


def compute_face_normal(
    lookup_vertices: list[tuple[float, float, float]],
    face: tuple[int, ...],
) -> tuple[float, float, float]:
    """Обчислення ненормованого вектора нормалі полігона через векторний добуток."""
    if len(face) < 3:
        return (0.0, 0.0, 0.0)
    v0 = lookup_vertices[face[0]]
    v1 = lookup_vertices[face[1]]
    v2 = lookup_vertices[face[2]]
    e1x, e1y, e1z = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
    e2x, e2y, e2z = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
    nx = e1y * e2z - e1z * e2y
    ny = e1z * e2x - e1x * e2z
    nz = e1x * e2y - e1y * e2x
    return (nx, ny, nz)


def find_degenerate_and_non_quad_faces(
    lookup_vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    zero_tolerance: float = 1e-12,
    index_offset: int = 0,
) -> tuple[list[int], list[int]]:
    """
    Пошук вироджених граней нульової площі (ZERO_NORMAL) та нечотирикутних полігонів (NOT_QUAD)
    виключно у переданому сегменті граней faces (O(M/k)).
    """
    if zero_tolerance <= 0:
        raise ValueError("Допуск площі грані має бути додатним.")

    zero_normals: list[int] = []
    non_quads: list[int] = []
    tol_sq = zero_tolerance * zero_tolerance

    for local_idx, face in enumerate(faces):
        global_idx = index_offset + local_idx
        if len(face) != 4:
            non_quads.append(global_idx)
        nx, ny, nz = compute_face_normal(lookup_vertices, face)
        if (nx * nx + ny * ny + nz * nz) <= tol_sq:
            zero_normals.append(global_idx)

    return zero_normals, non_quads


def find_normals_issues_bfs(
    lookup_vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    zero_tolerance: float = 1e-12,
    index_offset: int = 0,
) -> tuple[list[int], list[int]]:
    """
    Комплексний аналіз нормалей виключно у переданому сегменті граней faces (O(M/k)):
    - zero_normals: глобальні індекси граней із нульовою нормаллю (||N|| <= zero_tolerance);
    - flipped_normals: глобальні індекси граней з інвертованою орієнтацією за BFS-графом ребер.
    """
    if zero_tolerance <= 0:
        raise ValueError("Допуск нормалі має бути додатним.")

    tol_sq = zero_tolerance * zero_tolerance
    valid_local_faces: set[int] = set()
    zero_normals: list[int] = []

    for local_idx, face in enumerate(faces):
        nx, ny, nz = compute_face_normal(lookup_vertices, face)
        if (nx * nx + ny * ny + nz * nz) <= tol_sq:
            zero_normals.append(index_offset + local_idx)
        else:
            valid_local_faces.add(local_idx)

    edge_map: dict[tuple[int, int], list[tuple[int, bool]]] = defaultdict(list)
    for local_idx in valid_local_faces:
        face = faces[local_idx]
        k = len(face)
        for i in range(k):
            a = face[i]
            b = face[(i + 1) % k]
            if a == b:
                continue
            key = (a, b) if a < b else (b, a)
            forward = a < b
            edge_map[key].append((local_idx, forward))

    adjacency: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    for incident in edge_map.values():
        if len(incident) == 2:
            (f1, dir1), (f2, dir2) = incident
            is_consistent = dir1 != dir2
            adjacency[f1].append((f2, is_consistent))
            adjacency[f2].append((f1, is_consistent))

    orientation: dict[int, int] = {}
    flipped: list[int] = []

    for start_local in sorted(valid_local_faces):
        if start_local in orientation:
            continue

        component: list[int] = []
        queue = deque([start_local])
        orientation[start_local] = 0

        while queue:
            curr = queue.popleft()
            component.append(curr)
            curr_state = orientation[curr]
            for neighbor, is_consistent in adjacency.get(curr, ()):
                expected = curr_state if is_consistent else (1 - curr_state)
                if neighbor not in orientation:
                    orientation[neighbor] = expected
                    queue.append(neighbor)

        count_0 = sum(1 for c in component if orientation[c] == 0)
        count_1 = len(component) - count_0
        inverted_state = 1 if count_0 >= count_1 else 0

        for c in component:
            if orientation[c] == inverted_state:
                flipped.append(index_offset + c)

    return sorted(zero_normals), sorted(flipped)
