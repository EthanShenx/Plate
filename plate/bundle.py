"""Versioned workspace documents and atomic ZIP bundles."""

from dataclasses import asdict
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from .model import SCHEMA_VERSION, SCRIPT_EXTENSIONS, new_id, project_from_dict

SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


def atomic_write(path, write):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        write(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, data):
    atomic_write(path, lambda tmp: tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    ))


def script_path(workspace, panel):
    if not SAFE_ID.fullmatch(panel.id):
        raise ValueError("Invalid panel identifier.")
    return workspace / "panels" / panel.id / f"script.{SCRIPT_EXTENSIONS[panel.type]}"


def write_workspace(project, workspace, write_scripts=True):
    if not SAFE_ID.fullmatch(project.id):
        raise ValueError("Invalid project identifier.")
    data = asdict(project)
    for key in ("layout", "style", "palettes"):
        write_json(workspace / f"{key}.json", data.pop(key))
    for panel, record in zip(project.panels, data.pop("panels"), strict=True):
        if not SAFE_ID.fullmatch(panel.id):
            raise ValueError("Invalid panel identifier.")
        record.pop("script")
        write_json(workspace / "panels" / panel.id / "panel.json", record)
        if write_scripts and panel.type in SCRIPT_EXTENSIONS:
            atomic_write(script_path(workspace, panel),
                         lambda tmp: tmp.write_text(panel.script, encoding="utf-8"))
    write_json(workspace / "manifest.json", {
        **data, "schema_version": SCHEMA_VERSION,
        "panel_ids": [panel.id for panel in project.panels],
    })


def migrate(manifest):
    version = manifest.pop("schema_version", 0)
    if version == 0:
        manifest["name"] = manifest.pop("title", manifest.get("name", "Untitled figure"))
        manifest.setdefault("panel_ids", [])
        version = 1
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema {version}.")
    return manifest


def asset_path(workspace, value):
    asset = PurePosixPath(value)
    if len(asset.parts) != 2 or asset.parts[0] != "assets" or asset.name == ".." or "\\" in value:
        raise ValueError("Invalid asset location.")
    return workspace / asset


def read_workspace(workspace):
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    manifest = migrate(read(workspace / "manifest.json"))
    if not SAFE_ID.fullmatch(manifest["id"]):
        raise ValueError("Invalid project identifier.")
    manifest["panels"] = []
    for panel_id in manifest.pop("panel_ids"):
        if not SAFE_ID.fullmatch(panel_id):
            raise ValueError("Invalid panel identifier.")
        folder = workspace / "panels" / panel_id
        panel = read(folder / "panel.json")
        if panel_id != panel.get("id"):
            raise ValueError("Panel identifier does not match its folder.")
        if panel["type"] in SCRIPT_EXTENSIONS:
            panel["script"] = (folder / f"script.{SCRIPT_EXTENSIONS[panel['type']]}").read_text(
                encoding="utf-8")
        if panel.get("asset"):
            asset_path(workspace, panel["asset"])
        manifest["panels"].append(panel)
    for key in ("layout", "style", "palettes"):
        path = workspace / f"{key}.json"
        if path.exists():
            manifest[key] = read(path)
    return project_from_dict(manifest)


def open_bundle(path, workspaces):
    workspaces.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=workspaces) as scratch:
        unpacked = Path(scratch)
        with ZipFile(path) as archive:
            seen = set()
            for entry in archive.infolist():
                name = PurePosixPath(entry.filename)
                if (name.is_absolute() or ".." in name.parts or not name.parts
                        or name in seen or "\\" in entry.filename):
                    raise ValueError("Unsafe or duplicate bundle entry.")
                seen.add(name)
                if entry.is_dir():
                    continue
                destination = unpacked.joinpath(*name.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
        project = read_workspace(unpacked)
        workspace = workspaces / project.id
        if workspace.exists():
            workspace = workspaces / f"{project.id}-{new_id()}"
        unpacked.rename(workspace)
    return project, workspace


def save_bundle(project, workspace, path, include_cache=False, write_scripts=True):
    write_workspace(project, workspace, write_scripts=write_scripts)
    files = [workspace / f"{key}.json" for key in ("manifest", "layout", "style", "palettes")]
    for panel in project.panels:
        files.append(workspace / "panels" / panel.id / "panel.json")
        if panel.type in SCRIPT_EXTENSIONS:
            files.append(script_path(workspace, panel))
        if panel.asset:
            files.append(asset_path(workspace, panel.asset))
    if include_cache:
        files.extend(path for path in (workspace / "cache").rglob("*") if path.is_file())

    def pack(temporary):
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for file in dict.fromkeys(files):
                archive.write(file, file.relative_to(workspace))

    atomic_write(path, pack)
