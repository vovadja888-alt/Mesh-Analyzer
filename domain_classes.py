import json
import os
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
import math_logic


class Reportable(ABC):
    @abstractmethod
    def to_xml(self, save_path: str) -> None:
        raise NotImplementedError


@dataclass
class Vertex:
    index: int
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class Face:
    index: int
    vertex_indices: tuple[int, ...]


@dataclass
class Issue:
    index: int
    error_type: str
    rule_name: str
    severity: str
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "error_type": self.error_type,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Issue":
        return cls(
            index=int(data["index"]),
            error_type=str(data["error_type"]),
            rule_name=str(data["rule_name"]),
            severity=str(data["severity"]),
            description=str(data.get("description", "")),
        )


class ValidationRule(ABC):
    def __init__(self, name: str, tolerance: float = 1e-6, enabled: bool = True):
        self.name = name
        self.enabled = bool(enabled)
        self._tolerance = 1e-6
        self.tolerance = tolerance

    @property
    def tolerance(self) -> float:
        return self._tolerance

    @tolerance.setter
    def tolerance(self, value: float) -> None:
        val = float(value)
        if val <= 0:
            raise ValueError(f"Допуск правила «{self.name}» має бути > 0 (отримано {val}).")
        self._tolerance = val

    @abstractmethod
    def check(self, model: "Model3D") -> list[Issue]:
        raise NotImplementedError

    def to_dict(self) -> dict:
        return {
            "type": self.__class__.__name__,
            "name": self.name,
            "tolerance": self.tolerance,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ValidationRule":
        r_type = data.get("type", "")
        tol = float(data.get("tolerance", 1e-6))
        enabled = bool(data.get("enabled", True))
        mapping = {
            "DuplicateVertexRule": DuplicateVertexRule,
            "DegenerateFaceRule": DegenerateFaceRule,
            "NormalRule": NormalRule,
        }
        target_cls = mapping.get(r_type)
        if target_cls is None:
            raise ValueError(f"Невідомий тип правила: {r_type}")
        return target_cls(tolerance=tol, enabled=enabled)


class DuplicateVertexRule(ValidationRule):
    def __init__(self, tolerance: float = 1e-6, enabled: bool = True):
        super().__init__(name="Дублікати вершин", tolerance=tolerance, enabled=enabled)

    def check(self, model: "Model3D") -> list[Issue]:
        if not self.enabled:
            return []
        verts = model.get_raw_vertices()
        dups = math_logic.find_duplicate_vertices(verts, tolerance=self.tolerance)
        return [
            Issue(
                index=idx,
                error_type="DUPLICATE_VERTEX",
                rule_name=self.name,
                severity="Warning",
                description=f"Дублікат вершини #{idx} (допуск {self.tolerance:g})",
            )
            for idx in dups
        ]


class DegenerateFaceRule(ValidationRule):
    def __init__(self, tolerance: float = 1e-12, enabled: bool = True):
        super().__init__(name="Вироджені та n-гони", tolerance=tolerance, enabled=enabled)

    def check(self, model: "Model3D") -> list[Issue]:
        if not self.enabled:
            return []
        verts = model.get_raw_vertices()
        faces = model.get_raw_faces()
        zeros, non_quads = math_logic.find_degenerate_and_non_quad_faces(
            verts, faces, zero_tolerance=self.tolerance
        )
        issues = [
            Issue(
                index=idx,
                error_type="ZERO_NORMAL",
                rule_name=self.name,
                severity="Critical",
                description=f"Вироджена грань #{idx} (допуск {self.tolerance:g})",
            )
            for idx in zeros
        ]
        issues.extend(
            Issue(
                index=idx,
                error_type="NOT_QUAD",
                rule_name=self.name,
                severity="Info",
                description=f"Нечотирикутний полігон #{idx} ({len(faces[idx])} вершин)",
            )
            for idx in non_quads
        )
        return issues


class NormalRule(ValidationRule):
    def __init__(self, tolerance: float = 1e-12, enabled: bool = True):
        super().__init__(name="Орієнтація нормалей", tolerance=tolerance, enabled=enabled)

    def check(self, model: "Model3D") -> list[Issue]:
        if not self.enabled:
            return []
        verts = model.get_raw_vertices()
        faces = model.get_raw_faces()
        flipped = math_logic.find_flipped_normals_bfs(verts, faces, zero_tolerance=self.tolerance)
        return [
            Issue(
                index=idx,
                error_type="FLIPPED_NORMAL",
                rule_name=self.name,
                severity="Critical",
                description=f"Інвертована нормаль грані #{idx} (допуск {self.tolerance:g})",
            )
            for idx in flipped
        ]


class Model3D(Reportable):
    def __init__(
        self,
        name: str,
        file_path: str,
        raw_data: dict | None = None,
        analyzed: bool = False,
        vertex_count: int = 0,
        face_count: int = 0,
        issues: list[Issue] | None = None,
    ):
        if not name or not name.strip():
            raise ValueError("Назва 3D-моделі не може бути порожньою.")
        self.name = name.strip()
        self.file_path = file_path
        self.vertices: list[Vertex] = []
        self.faces: list[Face] = []
        self.issues: list[Issue] = issues if issues is not None else []
        self.analyzed = analyzed
        self._cached_vertex_count = vertex_count
        self._cached_face_count = face_count

        if raw_data is not None:
            self.load_geometry(raw_data)

    def load_geometry(self, raw_data: dict) -> None:
        raw_verts = raw_data.get("vertices", [])
        raw_faces = raw_data.get("faces", [])
        self.vertices = [Vertex(i, v[0], v[1], v[2]) for i, v in enumerate(raw_verts)]
        self.faces = [Face(i, tuple(f)) for i, f in enumerate(raw_faces)]
        self._cached_vertex_count = len(self.vertices)
        self._cached_face_count = len(self.faces)

    @property
    def vertex_count(self) -> int:
        return len(self.vertices) if self.vertices else self._cached_vertex_count

    @property
    def face_count(self) -> int:
        return len(self.faces) if self.faces else self._cached_face_count

    def get_raw_vertices(self) -> list[tuple[float, float, float]]:
        return [v.as_tuple() for v in self.vertices]

    def get_raw_faces(self) -> list[tuple[int, ...]]:
        return [f.vertex_indices for f in self.faces]

    def validate(self, rules: list[ValidationRule]) -> list[Issue]:
        all_issues: list[Issue] = []
        for rule in rules:
            if rule.enabled:
                all_issues.extend(rule.check(self))
        self.set_issues_deduplicated(all_issues)
        self.analyzed = True
        return self.issues

    def set_issues_deduplicated(self, issues: list[Issue]) -> None:
        seen: set[tuple[str, int]] = set()
        unique: list[Issue] = []
        for iss in issues:
            key = (iss.error_type, iss.index)
            if key not in seen:
                seen.add(key)
                unique.append(iss)
        unique.sort(key=lambda x: (x.severity != "Critical", x.severity != "Warning", x.index))
        self.issues = unique
        self.analyzed = True

    def to_xml(self, save_path: str) -> None:
        root = ET.Element(
            "ModelReport",
            attrib={
                "name": self.name,
                "file_path": self.file_path,
                "vertices": str(self.vertex_count),
                "faces": str(self.face_count),
                "issues_count": str(len(self.issues)),
            },
        )
        issues_el = ET.SubElement(root, "Issues")
        for iss in self.issues:
            ET.SubElement(
                issues_el,
                "Issue",
                attrib={
                    "index": str(iss.index),
                    "type": iss.error_type,
                    "rule": iss.rule_name,
                    "severity": iss.severity,
                    "description": iss.description,
                },
            )
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(save_path, encoding="utf-8", xml_declaration=True)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "analyzed": self.analyzed,
            "vertex_count": self.vertex_count,
            "face_count": self.face_count,
            "issues": [i.to_dict() for i in self.issues],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Model3D":
        return cls(
            name=data["name"],
            file_path=data["file_path"],
            analyzed=bool(data.get("analyzed", False)),
            vertex_count=int(data.get("vertex_count", 0)),
            face_count=int(data.get("face_count", 0)),
            issues=[Issue.from_dict(x) for x in data.get("issues", [])],
        )


class Project:
    def __init__(
        self,
        name: str = "Проєкт за замовчуванням",
        models: list[Model3D] | None = None,
        rules: list[ValidationRule] | None = None,
    ):
        if not name or not name.strip():
            raise ValueError("Назва проєкту не може бути порожньою.")
        self.name = name.strip()
        self.models: list[Model3D] = models if models is not None else []
        self.rules: list[ValidationRule] = (
            rules
            if rules is not None
            else [
                DuplicateVertexRule(tolerance=1e-6, enabled=True),
                DegenerateFaceRule(tolerance=1e-12, enabled=True),
                NormalRule(tolerance=1e-12, enabled=True),
            ]
        )

    def add_model(self, model: Model3D) -> None:
        for i, existing in enumerate(self.models):
            if existing.name.lower() == model.name.lower():
                self.models[i] = model
                return
        self.models.append(model)

    def update_model(self, old_name: str, new_name: str, new_path: str) -> Model3D:
        if not new_name or not new_name.strip():
            raise ValueError("Нова назва моделі не може бути порожньою.")
        if not new_path or not os.path.isfile(new_path):
            raise FileNotFoundError(f"Файл моделі не існує: {new_path}")

        target = self.get_model(old_name)
        if target is None:
            raise KeyError(f"Модель «{old_name}» не знайдено у проєкті.")

        clean_new = new_name.strip()
        if clean_new.lower() != old_name.lower() and self.get_model(clean_new) is not None:
            raise ValueError(f"Модель із назвою «{clean_new}» вже існує у проєкті.")

        path_changed = os.path.abspath(target.file_path) != os.path.abspath(new_path)
        target.name = clean_new
        target.file_path = new_path
        if path_changed:
            target.vertices.clear()
            target.faces.clear()
            target.issues.clear()
            target.analyzed = False
            target._cached_vertex_count = 0
            target._cached_face_count = 0
        return target

    def remove_model(self, model_name: str) -> bool:
        for i, m in enumerate(self.models):
            if m.name == model_name:
                self.models.pop(i)
                return True
        return False

    def get_model(self, model_name: str) -> Model3D | None:
        for m in self.models:
            if m.name == model_name:
                return m
        return None

    def find_models(self, query: str) -> list[Model3D]:
        q = query.strip().lower()
        if not q:
            return list(self.models)
        return [m for m in self.models if q in m.name.lower()]

    def sort_models(self, by: str = "name", reverse: bool = False) -> list[Model3D]:
        if by == "vertices":
            return sorted(self.models, key=lambda m: m.vertex_count, reverse=reverse)
        if by == "issues":
            return sorted(self.models, key=lambda m: len(m.issues), reverse=reverse)
        return sorted(self.models, key=lambda m: m.name.lower(), reverse=reverse)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "rules": [r.to_dict() for r in self.rules],
            "models": [m.to_dict() for m in self.models],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        rules = [ValidationRule.from_dict(r) for r in data.get("rules", [])]
        models = [Model3D.from_dict(m) for m in data.get("models", [])]
        return cls(name=data.get("name", "Без назви"), models=models, rules=rules if rules else None)


class ProjectStorage:
    """Менеджер зберігання та завантаження кількох проєктів у JSON-файлі."""

    def __init__(self, storage_path: str = "projects.json"):
        self.storage_path = storage_path
        self.projects: dict[str, Project] = {}
        self.active_project_name: str = ""

    def load_all(self) -> Project:
        if not os.path.isfile(self.storage_path):
            default_proj = Project("Проєкт за замовчуванням")
            self.projects = {default_proj.name: default_proj}
            self.active_project_name = default_proj.name
            self.save_all()
            return default_proj

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}

        if isinstance(raw, dict) and "projects" not in raw and "name" in raw:
            proj = Project.from_dict(raw)
            self.projects = {proj.name: proj}
            self.active_project_name = proj.name
            self.save_all()
            return proj

        self.projects.clear()
        if isinstance(raw, dict):
            for p_data in raw.get("projects", []):
                proj = Project.from_dict(p_data)
                self.projects[proj.name] = proj

        if not self.projects:
            default_proj = Project("Проєкт за замовчуванням")
            self.projects[default_proj.name] = default_proj

        active_name = raw.get("active_project", "") if isinstance(raw, dict) else ""
        if active_name in self.projects:
            self.active_project_name = active_name
        else:
            self.active_project_name = next(iter(self.projects))

        return self.projects[self.active_project_name]

    def save_all(self) -> None:
        payload = {
            "active_project": self.active_project_name,
            "projects": [p.to_dict() for p in self.projects.values()],
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def get_active(self) -> Project:
        return self.projects[self.active_project_name]

    def set_active(self, name: str) -> Project:
        if name not in self.projects:
            raise KeyError(f"Проєкт «{name}» не знайдено.")
        self.active_project_name = name
        self.save_all()
        return self.projects[name]

    def create_or_select_project(self, name: str) -> Project:
        clean = name.strip()
        if not clean:
            raise ValueError("Назва проєкту не може бути порожньою.")
        if clean not in self.projects:
            self.projects[clean] = Project(clean)
        self.active_project_name = clean
        self.save_all()
        return self.projects[clean]

    def rename_active_project(self, new_name: str) -> Project:
        clean = new_name.strip()
        if not clean:
            raise ValueError("Назва проєкту не може бути порожньою.")
        proj = self.get_active()
        if clean != proj.name:
            if clean in self.projects:
                raise ValueError(f"Проєкт із назвою «{clean}» вже існує.")
            del self.projects[proj.name]
            proj.name = clean
            self.projects[clean] = proj
            self.active_project_name = clean
        self.save_all()
        return proj

    def delete_project(self, name: str) -> Project:
        if name in self.projects:
            del self.projects[name]
        if not self.projects:
            fallback = Project("Проєкт за замовчуванням")
            self.projects[fallback.name] = fallback
        if self.active_project_name not in self.projects:
            self.active_project_name = next(iter(self.projects))
        self.save_all()
        return self.projects[self.active_project_name]
