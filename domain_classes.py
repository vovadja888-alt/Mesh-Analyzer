import abc
import json
import os
import logging
import xml.etree.ElementTree as ET

import obj_parser
import math_logic

logging.basicConfig(
    filename="mesh_analyzer.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)


class Reportable(abc.ABC):
    @abc.abstractmethod
    def to_xml(self, save_path: str) -> None:
        pass


class Vertex:
    def __init__(self, index: int, x: float, y: float, z: float):
        self.index = index
        self.x = x
        self.y = y
        self.z = z

    def as_tuple(self) -> tuple:
        return (self.x, self.y, self.z)


class Face:
    def __init__(self, index: int, vertex_indices: list):
        self.index = index
        self.vertex_indices = vertex_indices


class Issue:
    SEVERITY_MAP = {
        "ZERO_NORMAL": "Critical",
        "FLIPPED_NORMAL": "Critical",
        "DUPLICATE_VERTEX": "Warning",
        "NOT_QUAD": "Info"
    }

    def __init__(self, element_index: int, error_type: str, rule_name: str = ""):
        self.index = element_index
        self.error_type = error_type
        self.rule_name = rule_name or error_type
        self.severity = self.SEVERITY_MAP.get(error_type, "Warning")

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "error_type": self.error_type,
            "rule_name": self.rule_name,
            "severity": self.severity
        }


class ValidationRule(abc.ABC):
    def __init__(self, name: str, tolerance: float = 1e-6):
        if tolerance is None or tolerance <= 0:
            raise ValueError("Допуск (tolerance) має бути додатним числом (> 0)!")
        self.name = name
        self.tolerance = float(tolerance)

    @abc.abstractmethod
    def check(self, model: "Model3D") -> list[Issue]:
        pass


class DuplicateVertexRule(ValidationRule):
    def __init__(self, tolerance: float = 1e-6):
        super().__init__("DuplicateVertexRule", tolerance)

    def check(self, model: "Model3D") -> list[Issue]:
        dup_indices = math_logic.find_duplicate_vertices(model.raw_data['vertices'], self.tolerance)
        return [Issue(idx, "DUPLICATE_VERTEX", self.name) for idx in dup_indices]


class DegenerateFaceRule(ValidationRule):
    def __init__(self, tolerance: float = 1e-6):
        super().__init__("DegenerateFaceRule", tolerance)

    def check(self, model: "Model3D") -> list[Issue]:
        issues = []
        center = model.center
        for face_idx, face_item in enumerate(model.raw_data['faces']):
            coords = obj_parser.get_face_vertices(model.raw_data, face_item)
            if len(coords) < 3:
                continue
            errors = math_logic.check_face(coords, center, self.tolerance)
            for err in errors:
                if err == "NOT_QUAD":
                    issues.append(Issue(face_idx, err, self.name))
        return issues


class NormalRule(ValidationRule):
    def __init__(self, tolerance: float = 1e-6):
        super().__init__("NormalRule", tolerance)

    def check(self, model: "Model3D") -> list[Issue]:
        issues = []
        center = model.center
        faces_normals = []
        face_neighbors = {i: set() for i in range(len(model.raw_data['faces']))}
        edge_to_faces = {}

        for face_idx, face_item in enumerate(model.raw_data['faces']):
            coords = obj_parser.get_face_vertices(model.raw_data, face_item)
            normal = math_logic.calculate_face_normal(coords)
            faces_normals.append(normal)

            if len(coords) >= 3:
                errors = math_logic.check_face(coords, center, self.tolerance)
                for err in errors:
                    if err == "ZERO_NORMAL":
                        issues.append(Issue(face_idx, err, self.name))

            v_indices = [
                int(item[0]) if isinstance(item, (tuple, list)) else int(item)
                for item in face_item
            ]
            for i in range(len(v_indices)):
                p1, p2 = v_indices[i], v_indices[(i + 1) % len(v_indices)]
                edge_key = tuple(sorted((p1, p2)))
                edge_to_faces.setdefault(edge_key, []).append(face_idx)

        for f_list in edge_to_faces.values():
            if len(f_list) == 2:
                face_neighbors[f_list[0]].add(f_list[1])
                face_neighbors[f_list[1]].add(f_list[0])

        flipped = math_logic.check_flipped_normals_by_neighbors(faces_normals, face_neighbors)
        for f_idx in flipped:
            issues.append(Issue(f_idx, "FLIPPED_NORMAL", self.name))

        return issues


RULE_REGISTRY = {
    "DuplicateVertexRule": DuplicateVertexRule,
    "DegenerateFaceRule": DegenerateFaceRule,
    "NormalRule": NormalRule
}


def run_rule_worker(rule: ValidationRule, model: "Model3D") -> list[Issue]:
    return rule.check(model)


class Model3D(Reportable):
    def __init__(self, name: str, file_path: str, raw_data: dict | None = None):
        if not name or not name.strip():
            raise ValueError("Назва моделі не може бути порожньою!")
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл моделі не знайдено: {file_path}")
        if not file_path.lower().endswith(".obj"):
            raise ValueError("Підтримуються лише файли у форматі .obj!")

        self.name = name.strip()
        self.file_path = file_path
        self.raw_data = raw_data if raw_data is not None else obj_parser.parse_obj(file_path)
        self.center = obj_parser.calculate_object_center(self.raw_data['vertices'])
        self.vertices = [Vertex(i, *v) for i, v in enumerate(self.raw_data['vertices'])]
        self.faces = [Face(i, f) for i, f in enumerate(self.raw_data['faces'])]
        self.issues: list[Issue] = []

    def validate(self, rules: list[ValidationRule]) -> list[Issue]:
        self.issues.clear()
        seen = set()
        for rule in rules:
            found = rule.check(self)
            for iss in found:
                key = (iss.index, iss.error_type)
                if key not in seen:
                    seen.add(key)
                    self.issues.append(iss)
        logging.info(f"Перевірка '{self.name}' завершена: знайдено {len(self.issues)} помилок")
        return self.issues

    def set_issues_deduplicated(self, raw_issues: list[Issue]) -> list[Issue]:
        self.issues.clear()
        seen = set()
        for iss in raw_issues:
            key = (iss.index, iss.error_type)
            if key not in seen:
                seen.add(key)
                self.issues.append(iss)
        logging.info(f"Перевірка '{self.name}' завершена: знайдено {len(self.issues)} помилок")
        return self.issues

    def to_xml(self, save_path: str) -> None:
        root_elem = ET.Element("ValidationReport")
        root_elem.set("model_name", self.name)
        root_elem.set("source_file", self.file_path)
        root_elem.set("total_vertices", str(len(self.vertices)))
        root_elem.set("total_faces", str(len(self.faces)))
        root_elem.set("total_errors", str(len(self.issues)))

        for issue in self.issues:
            err_elem = ET.SubElement(root_elem, "Issue")
            ET.SubElement(err_elem, "Model").text = self.name
            ET.SubElement(err_elem, "Rule").text = issue.rule_name
            ET.SubElement(err_elem, "ElementIndex").text = str(issue.index)
            ET.SubElement(err_elem, "ErrorType").text = issue.error_type
            ET.SubElement(err_elem, "Severity").text = issue.severity

        tree = ET.ElementTree(root_elem)
        ET.indent(tree, space="  ")
        tree.write(save_path, encoding="utf-8", xml_declaration=True)
        logging.info(f"XML-звіт збережено: {save_path}")


class Project:
    def __init__(self, name: str):
        if not name or not name.strip():
            raise ValueError("Назва проєкту не може бути порожньою!")
        self.name = name.strip()
        self.models: list[Model3D] = []
        self.rules: list[ValidationRule] = [
            DuplicateVertexRule(1e-6),
            DegenerateFaceRule(1e-6),
            NormalRule(1e-6)
        ]

    def rename(self, new_name: str):
        if not new_name or not new_name.strip():
            raise ValueError("Нова назва проєкту не може бути порожньою!")
        self.name = new_name.strip()

    def add_model(self, model: Model3D):
        self.remove_model(model.name)
        self.models.append(model)

    def get_model(self, model_name: str) -> Model3D | None:
        for m in self.models:
            if m.name == model_name:
                return m
        return None

    def remove_model(self, model_name: str):
        self.models = [m for m in self.models if m.name != model_name]

    def find_models(self, query: str) -> list[Model3D]:
        q = query.lower().strip()
        if not q:
            return list(self.models)
        return [m for m in self.models if q in m.name.lower()]

    def sort_models(self, by: str = "errors", reverse: bool = True) -> list[Model3D]:
        if by == "vertices":
            return sorted(self.models, key=lambda m: len(m.vertices), reverse=reverse)
        if by == "name":
            return sorted(self.models, key=lambda m: m.name.lower(), reverse=reverse)
        return sorted(self.models, key=lambda m: len(m.issues), reverse=reverse)

    def add_or_update_rule(self, rule_type: str, tolerance: float):
        if tolerance <= 0:
            raise ValueError("Допуск має бути додатним числом (> 0)!")
        if rule_type not in RULE_REGISTRY:
            raise ValueError(f"Невідомий тип правила: {rule_type}")
        self.remove_rule(rule_type)
        self.rules.append(RULE_REGISTRY[rule_type](tolerance))

    def remove_rule(self, rule_type: str):
        self.rules = [r for r in self.rules if r.name != rule_type]

    def save_to_json(self, json_path: str = "projects.json"):
        payload = {
            "project_name": self.name,
            "rules": [{"type": r.name, "tolerance": r.tolerance} for r in self.rules],
            "models": [
                {
                    "name": m.name,
                    "path": m.file_path,
                    "vertices_count": len(m.vertices),
                    "errors_count": len(m.issues)
                }
                for m in self.models
            ]
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_from_json(json_path: str = "projects.json") -> "Project":
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logging.error(f"Некоректний JSON у файлі {json_path}: {e}")
            raise ValueError(f"Пошкоджений JSON-файл '{json_path}': {e}") from e

        proj = Project(data.get("project_name", "Default Project"))
        if "rules" in data and isinstance(data["rules"], list):
            proj.rules.clear()
            for r_info in data["rules"]:
                r_type = r_info.get("type")
                tol = float(r_info.get("tolerance", 1e-6))
                if r_type in RULE_REGISTRY and tol > 0:
                    proj.rules.append(RULE_REGISTRY[r_type](tol))

        for m_info in data.get("models", []):
            m_path = m_info.get("path", "")
            m_name = m_info.get("name", os.path.basename(m_path))
            if m_path and os.path.exists(m_path):
                try:
                    m_obj = Model3D(m_name, m_path)
                    proj.add_model(m_obj)
                except Exception as ex:
                    logging.warning(f"Пропущено модель '{m_name}' при завантаженні JSON: {ex}")
        return proj