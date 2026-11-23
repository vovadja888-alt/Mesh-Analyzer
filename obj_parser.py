import os
import logging


class ObjParseError(Exception):
    pass


def parse_obj(file_path: str) -> dict:
    if not os.path.exists(file_path):
        logging.error(f"Файл не знайдено: {file_path}")
        raise FileNotFoundError(f"Файл не знайдено: {file_path}")

    vertices = []
    normals = []
    faces = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split()
                prefix = parts[0]

                if prefix == 'v':
                    if len(parts) < 4:
                        raise ObjParseError(f"Рядок {line_num}: некоректний запис вершини '{line}'")
                    try:
                        vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                    except ValueError as e:
                        raise ObjParseError(f"Рядок {line_num}: помилка координат вершини ({e})") from e

                elif prefix == 'vn':
                    if len(parts) < 4:
                        raise ObjParseError(f"Рядок {line_num}: некоректний запис нормалі '{line}'")
                    try:
                        normals.append((float(parts[1]), float(parts[2]), float(parts[3])))
                    except ValueError as e:
                        raise ObjParseError(f"Рядок {line_num}: помилка координат нормалі ({e})") from e

                elif prefix == 'f':
                    if len(parts) < 4:
                        raise ObjParseError(f"Рядок {line_num}: грань містить менше 3 вершин")
                    face_indices = []
                    for p in parts[1:]:
                        sub_parts = p.split('/')
                        try:
                            raw_v = int(sub_parts[0])
                        except ValueError as e:
                            raise ObjParseError(f"Рядок {line_num}: некоректний індекс вершини '{sub_parts[0]}'") from e

                        v_idx = raw_v - 1 if raw_v > 0 else len(vertices) + raw_v
                        if v_idx < 0 or v_idx >= len(vertices):
                            raise IndexError(
                                f"Рядок {line_num}: індекс вершини {raw_v} поза межами (0..{len(vertices)-1})"
                            )

                        vn_idx = None
                        if len(sub_parts) >= 3 and sub_parts[2]:
                            try:
                                raw_vn = int(sub_parts[2])
                                vn_idx = raw_vn - 1 if raw_vn > 0 else len(normals) + raw_vn
                            except ValueError:
                                vn_idx = None

                        face_indices.append((v_idx, vn_idx))
                    faces.append(face_indices)

    except UnicodeDecodeError as e:
        logging.error(f"Пошкоджений файл або кодування: {file_path}")
        raise ObjParseError(f"Файл '{file_path}' пошкоджений або має непідтримуване кодування") from e

    if not vertices:
        logging.error(f"Файл без вершин: {file_path}")
        raise ObjParseError(f"Файл '{file_path}' не містить жодної вершини (v)")

    logging.info(f"Розібрано OBJ '{os.path.basename(file_path)}': {len(vertices)} вершин, {len(faces)} граней")
    return {
        'vertices': vertices,
        'normals': normals,
        'faces': faces
    }


def get_face_vertices(parsed_data: dict, face_indices: list) -> list:
    all_verts = parsed_data['vertices']
    face_coords = []

    for item in face_indices:
        idx = int(item[0]) if isinstance(item, (tuple, list)) else int(item)
        if idx < 0 or idx >= len(all_verts):
            raise IndexError(f"Індекс вершини {idx} виходить за межі масиву вершин")
        face_coords.append(all_verts[idx])

    return face_coords


def calculate_object_center(vertices: list) -> tuple:
    if not vertices:
        return (0.0, 0.0, 0.0)
    count = len(vertices)
    cx = sum(v[0] for v in vertices) / count
    cy = sum(v[1] for v in vertices) / count
    cz = sum(v[2] for v in vertices) / count
    return (cx, cy, cz)
