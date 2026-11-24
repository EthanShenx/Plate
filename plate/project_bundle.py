"""Portable collections of editable Plate figures."""

import json
from zipfile import ZipFile

from .bundle import SAFE_ID, atomic_write
from .model import new_id

PROJECT_SUFFIX = ".plateproject"
MANIFEST = "project.json"
VERSION = 1
MAX_MANIFEST_BYTES = 1024 * 1024


def figure_entries(count):
    return [f"figures/{index}.plate" for index in range(1, count + 1)]


def save_project_bundle(path, name, figures):
    manifest = {"schema_version": VERSION, "id": new_id(), "name": name, "figure_count": len(figures)}
    content = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    if len(content) > MAX_MANIFEST_BYTES:
        raise ValueError("The Plate project manifest is too large.")

    def pack(temporary):
        with ZipFile(temporary, "w") as archive:
            archive.writestr(MANIFEST, content)
            for figure, entry in zip(figures, figure_entries(len(figures)), strict=True):
                archive.write(figure, entry)

    atomic_write(path, pack)


def read_project_bundle(archive):
    entries = archive.namelist()
    if MANIFEST not in entries or archive.getinfo(MANIFEST).file_size > MAX_MANIFEST_BYTES:
        raise ValueError("The Plate project manifest is missing or too large.")
    manifest = json.loads(archive.read(MANIFEST))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != VERSION:
        raise ValueError("Unsupported Plate project file version.")
    project_id, name, count = (manifest.get(key) for key in ("id", "name", "figure_count"))
    if (not isinstance(project_id, str) or not SAFE_ID.fullmatch(project_id)
            or not isinstance(name, str) or not name.strip() or type(count) is not int or count < 1):
        raise ValueError("Invalid Plate project manifest.")
    if len(entries) != count + 1:
        raise ValueError("The Plate project does not contain the expected figures.")
    figures = figure_entries(count)
    if set(entries) != {MANIFEST, *figures}:
        raise ValueError("The Plate project does not contain the expected figures.")
    return f"archive-{project_id}", name, figures
