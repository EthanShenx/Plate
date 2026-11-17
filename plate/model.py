"""Serializable project records."""

from dataclasses import dataclass, field
import json
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
PANEL_TYPES = ("script-r", "script-py", "image", "vector", "text", "legend")
SCRIPT_EXTENSIONS = {"script-r": "R", "script-py": "py"}


def new_id():
    return uuid4().hex


def presets():
    return json.loads((ROOT / "presets/journals.json").read_text())


@dataclass
class FigureSize:
    preset_id: str = "nature"
    width_mm: float = 183
    height_mm: float = 122
    minimum_mm: float = 12


@dataclass
class Panel:
    id: str = field(default_factory=new_id)
    type: str = "script-py"
    name: str = "Untitled panel"
    label: str = ""
    overrides: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    locks: dict = field(default_factory=dict)
    interpreter: str = ""
    script: str = ""
    asset: str = ""
    input_files: list[str] = field(default_factory=list)


@dataclass
class Project:
    id: str = field(default_factory=new_id)
    name: str = "Untitled figure"
    size: FigureSize = field(default_factory=lambda: FigureSize(
        preset_id="custom", width_mm=122, height_mm=183))
    style: dict = field(default_factory=lambda: {"margin_mm": 4, "gutter_mm": 3})
    palettes: dict = field(default_factory=dict)
    panels: list[Panel] = field(default_factory=list)
    layout: dict | None = None
    interpreters: dict = field(default_factory=dict)
    data_root: str = ""
    embedded_data: bool = False
    timeout_s: float = 60
    alignment: list[dict] = field(default_factory=list)
    groups: list[dict] = field(default_factory=list)

    def __post_init__(self):
        for panel in self.panels:
            paths = panel.input_files
            if (not isinstance(paths, list) or any(
                    not isinstance(path, str) or not path.strip() or "\0" in path for path in paths)):
                raise ValueError("Panel input files must be a list of nonempty paths.")
            if paths and panel.type not in SCRIPT_EXTENSIONS:
                raise ValueError("Only script panels can declare input files.")


def project_from_dict(data):
    return Project(**{
        **data,
        "size": FigureSize(**data.get("size", {})),
        "panels": [Panel(**panel) for panel in data.get("panels", [])],
    })
