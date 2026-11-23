# ШІ: Базовий модуль геометричних обчислень для MeshAnalyzer. Змінено: додано математичну перевірку виродженості граней (повтор індексів та колінеарність/нульова площа).
import math


def calculate_face_normal(coords):
    if len(coords) < 3:
        return (0.0, 0.0, 0.0)

    p0, p1, p2 = coords[0], coords[1], coords[2]
    v1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    v2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])

    nx = v1[1] * v2[2] - v1[2] * v2[1]
    ny = v1[2] * v2[0] - v1[0] * v2[2]
    nz = v1[0] * v2[1] - v1[1] * v2[0]

    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0.0:
        return (0.0, 0.0, 0.0)

    return (nx / length, ny / length, nz / length)


# ШІ: Функція перевірки виродженості полігональної грані. Змінено: додано виявлення повтору індексів вершин (наприклад, f 1 1 2) та нульової площі грані (вершини на одній прямій) з масштабонезависимою перевіркою колінеарності.
def is_degenerate_face(face_indices: list[int], vertices: list[tuple[float, float, float]], tolerance: float = 1e-6) -> tuple[bool, str]:
    if len(face_indices) < 3:
        return True, "Менше 3 вершин у грані"

    if len(set(face_indices)) < len(face_indices):
        return True, f"Повтор індексу вершини у грані: {[i + 1 for i in face_indices]}"

    v0 = vertices[face_indices[0]]
    total_double_area = 0.0
    max_edge_sq = 0.0

    for i in range(1, len(face_indices) - 1):
        v1 = vertices[face_indices[i]]
        v2 = vertices[face_indices[i + 1]]

        e1x, e1y, e1z = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
        e2x, e2y, e2z = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]

        e1_sq = e1x * e1x + e1y * e1y + e1z * e1z
        e2_sq = e2x * e2x + e2y * e2y + e2z * e2z
        if e1_sq > max_edge_sq:
            max_edge_sq = e1_sq
        if e2_sq > max_edge_sq:
            max_edge_sq = e2_sq

        cx = e1y * e2z - e1z * e2y
        cy = e1z * e2x - e1x * e2z
        cz = e1x * e2y - e1y * e2x

        cross_len = math.sqrt(cx * cx + cy * cy + cz * cz)
        total_double_area += cross_len

    # Масштабонезалежний поріг: sin(alpha) * |e1| * |e2| <= tolerance * max_edge_sq
    area_threshold = tolerance * max(max_edge_sq, 1e-12)
    if total_double_area <= area_threshold:
        return True, "Нульова площа грані (вершини лежать на одній прямій)"

    return False, ""


def check_face(coords, center, tolerance=0.0001):
    errors = []
    if len(coords) < 3:
        errors.append("DEGENERATE_FACE")

    normal = calculate_face_normal(coords)
    if normal == (0.0, 0.0, 0.0):
        errors.append("ZERO_NORMAL")

    return errors


def check_flipped_normals_by_neighbors(faces_normals, face_neighbors):
    flipped_indices = []
    for idx, normal in enumerate(faces_normals):
        if normal == (0.0, 0.0, 0.0):
            continue

        neighbors = face_neighbors.get(idx, [])
        if not neighbors:
            continue

        negative_dots = 0
        for n_idx in neighbors:
            n_normal = faces_normals[n_idx]
            if n_normal == (0.0, 0.0, 0.0):
                continue

            dot = normal[0] * n_normal[0] + normal[1] * n_normal[1] + normal[2] * n_normal[2]
            if dot < -0.5:
                negative_dots += 1

        if negative_dots >= len(neighbors) / 2:
            flipped_indices.append(idx)

    return flipped_indices


def find_duplicate_vertices(vertices, tolerance=0.0001):
    seen = {}
    duplicates = []
    for idx, v in enumerate(vertices):
        key = (round(v[0] / tolerance), round(v[1] / tolerance), round(v[2] / tolerance))
        if key in seen:
            duplicates.append(idx)
        else:
            seen[key] = idx
    return duplicates
