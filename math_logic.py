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


def check_face(coords, center, tolerance=0.0001):
    errors = []
    if len(coords) < 3 or len(coords) > 4:
        errors.append("NOT_QUAD")

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