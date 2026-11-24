import os
import threading
from typing import Callable


class ObjParseError(Exception):
    """Спеціалізований виняток при пошкодженні або некоректній структурі OBJ-файлу."""


class AnalysisCancelledError(Exception):
    """Виняток кооперативного переривання операції користувачем."""


def parse_obj(
    file_path: str,
    cancel_event: threading.Event | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    if not file_path or not os.path.isfile(file_path):
        raise FileNotFoundError(f"Файл моделі не знайдено: {file_path}")

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise ObjParseError("Файл моделі порожній.")

    vertices: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    bytes_read = 0

    try:
        with open(file_path, "r", encoding="utf-8", errors="strict") as f:
            for line_num, raw_line in enumerate(f, start=1):
                bytes_read += len(raw_line.encode("utf-8"))

                # Перевірка скасування та оновлення прогресу кожні 2000 рядків
                if line_num % 2000 == 0:
                    if cancel_event is not None and cancel_event.is_set():
                        raise AnalysisCancelledError("Розбір OBJ-файлу скасовано користувачем.")
                    if progress_callback is not None and file_size > 0:
                        pct = min(0.45, (bytes_read / file_size) * 0.45)
                        progress_callback(pct, f"Парсинг рядка {line_num:,}...")

                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                prefix = parts[0]

                if prefix == "v":
                    if len(parts) < 4:
                        raise ObjParseError(f"Некоректна вершина у рядку {line_num}: {line}")
                    try:
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    except ValueError as exc:
                        raise ObjParseError(f"Помилка конвертації координат у рядку {line_num}") from exc
                    vertices.append((x, y, z))

                elif prefix == "vn":
                    if len(parts) < 4:
                        raise ObjParseError(f"Некоректна нормаль у рядку {line_num}: {line}")
                    try:
                        nx, ny, nz = float(parts[1]), float(parts[2]), float(parts[3])
                    except ValueError as exc:
                        raise ObjParseError(f"Помилка конвертації нормалі у рядку {line_num}") from exc
                    normals.append((nx, ny, nz))

                elif prefix == "f":
                    if len(parts) < 4:
                        raise ObjParseError(f"Грань має менше 3 вершин у рядку {line_num}: {line}")
                    face_indices: list[int] = []
                    v_count = len(vertices)
                    for token in parts[1:]:
                        v_str = token.split("/")[0]
                        try:
                            raw_idx = int(v_str)
                        except ValueError as exc:
                            raise ObjParseError(f"Некоректний індекс вершини у рядку {line_num}") from exc

                        if raw_idx == 0:
                            raise IndexError(f"Нульовий індекс вершини неприпустимий у рядку {line_num}")
                        idx = raw_idx - 1 if raw_idx > 0 else v_count + raw_idx
                        if idx < 0 or idx >= v_count:
                            raise IndexError(
                                f"Індекс вершини {raw_idx} виходить за межі [1..{v_count}] у рядку {line_num}"
                            )
                        face_indices.append(idx)
                    faces.append(tuple(face_indices))

    except UnicodeDecodeError as exc:
        raise ObjParseError("Файл не є текстовим Wavefront OBJ (виявлено бінарні дані).") from exc

    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelledError("Розбір OBJ-файлу скасовано користувачем.")

    if not vertices:
        raise ObjParseError("У файлі OBJ не знайдено жодної вершини (токен 'v').")

    return {
        "vertices": vertices,
        "normals": normals,
        "faces": faces,
    }
