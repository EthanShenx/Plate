"""Batch authoring for Plate bundles."""

from argparse import ArgumentParser
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

from .bundle import import_asset
from .export import DPIS, FORMATS
from .model import SCRIPT_EXTENSIONS, project_from_dict
from .render import data_directory
from .server import IncompleteExport, Session

COMMANDS = ("build", "apply", "inspect", "export")
SPEC_FIELDS = {"name", "size", "style", "palettes", "groups", "alignment", "interpreters",
               "timeout_s", "grid_mm", "data_root", "panels", "remove_panels"}


def relative_to(folder, value):
    return (folder / Path(value).expanduser()).resolve()


def update_project(session, spec_path, output):
    folder = spec_path.resolve().parent
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or spec.keys() - SPEC_FIELDS:
        raise ValueError("Expected a Plate JSON specification. See docs/cli.md for supported fields.")

    data = asdict(session.project)
    size = spec.get("size", {})
    data["size"].update(size)
    if "width_mm" in size and "preset_id" not in size:
        data["size"]["preset_id"] = "custom"
    for field in ("style", "palettes", "interpreters"):
        data[field].update(spec.get(field, {}))
    for field in ("name", "groups", "alignment", "timeout_s"):
        if field in spec:
            data[field] = spec[field]
    if "grid_mm" in spec:
        data["layout"]["step_mm"] = spec["grid_mm"]

    if session.bundle is None or "data_root" in spec:
        data_root = relative_to(folder, spec.get("data_root", ""))
    else:
        data_root = data_directory(session.project, session.workspace, session.bundle).resolve()
    relative_root = os.path.relpath(data_root, output.parent)
    data["data_root"] = "" if relative_root == "." else relative_root

    panels = {panel["id"]: panel for panel in data["panels"]}
    removing = spec.get("remove_panels", [])
    if not isinstance(removing, list):
        raise ValueError("remove_panels must be an array of panel IDs.")
    rects = data["layout"]["rects"]
    for panel_id in removing:
        if panel_id not in panels:
            raise ValueError(f"Unknown panel {panel_id!r}.")
        del panels[panel_id]
        del rects[panel_id]
    for field in ("groups", "alignment"):
        if removing and field not in spec:
            for group in data[field]:
                group["panels"] = [id for id in group["panels"] if id not in removing]
            data[field] = [group for group in data[field] if len(group["panels"]) >= 2]

    edited = set()
    for update in spec.get("panels", []):
        record = dict(update)
        panel_id = record["id"]
        if panel_id in edited or panel_id in removing:
            raise ValueError(f"Panel {panel_id!r} has conflicting edits.")
        edited.add(panel_id)
        previous = panels.get(panel_id, {})
        if "type" in previous and "type" in record and record["type"] != previous["type"]:
            raise ValueError(f"Panel {panel_id!r} already has a type. Use a new ID for a different type.")
        if "asset" in record:
            raise ValueError("Use asset_file to import a file.")
        if "rect" in record:
            rects[panel_id] = {**rects.get(panel_id, {}), **record.pop("rect")}
        kind = record.get("type", previous.get("type", "script-py"))
        if "script_file" in record:
            if kind not in SCRIPT_EXTENSIONS or "script" in record:
                raise ValueError(f"Panel {panel_id!r} needs one script source and a script panel type.")
            record["script"] = relative_to(folder, record.pop("script_file")).read_text(encoding="utf-8")
        if "script" in record and (kind not in SCRIPT_EXTENSIONS or not isinstance(record["script"], str)):
            raise ValueError(f"Panel {panel_id!r} needs text for its script source.")
        if "asset_file" in record:
            source = relative_to(folder, record.pop("asset_file"))
            record["asset"] = import_asset(session.workspace, kind, source)
            record["settings"] = {**previous.get("settings", {}), **record.get("settings", {}),
                                  "filename": source.name}
        panels[panel_id] = {**previous, **record}

    data["panels"] = list(panels.values())
    session.store_project(project_from_dict(data), write_scripts=True)
    session.bundle = output


def summary(state):
    project = state["project"]
    size = project["size"]
    return {
        "bundle": state["bundle"],
        "name": project["name"],
        "size_mm": [size["width_mm"], size["height_mm"]],
        "groups": project["groups"],
        "panels": [{
            "id": panel["id"], "name": panel["name"], "type": panel["type"], "label": panel["label"],
            "rect_mm": state["geometry"]["rects"][panel["id"]],
            "state": state["renders"][panel["id"]]["state"],
            **{key: state["renders"][panel["id"]][key] for key in ("error", "stderr")
               if state["renders"][panel["id"]]["state"] == "error" and key in state["renders"][panel["id"]]},
        } for panel in project["panels"]],
        "checks": state["checks"],
        "export_issues": state["export_issues"],
    }


def execute(options, workspaces):
    command = options.command
    if command == "export":
        format = options.output.suffix.lower().lstrip(".")
        if format not in FORMATS:
            raise ValueError("The output path must end in .pdf, .png or .tiff.")
    session = Session(getattr(options, "bundle", None), workspaces)
    if getattr(options, "data_root", None) is not None:
        session.remap_data_folder(str(options.data_root.expanduser().resolve()))
    if command in {"build", "apply"}:
        output = options.output.expanduser().resolve()
        if output.suffix.lower() != ".plate":
            raise ValueError("The project output path must end in .plate.")
        update_project(session, options.spec, output)
    if command == "inspect":
        result = {"ok": True, **summary(session.state()), "provenance": session.current_provenance(prefer_saved=True)}
        if options.compare_environment:
            result["environment"] = session.environment_report()
        return result

    session.refresh_pending(force=options.force)
    result = summary(session.state())
    if command != "export" and any(panel["state"] in {"stale", "error"} for panel in result["panels"]):
        return {"ok": False, "error": "Some panels could not render.", **result}
    if command == "export":
        try:
            exported = session.export({"path": str(options.output), "format": format,
                                       "dpi": options.dpi, "draft": options.draft})
        except IncompleteExport as error:
            return {**result, "ok": False, "error": str(error), "export_issues": error.issues}
        result.update(export=exported["path"], draft=exported["draft"], export_issues=exported["export_issues"])
    else:
        session.save(output, cache=True)
        result["bundle"] = str(output)
    return {"ok": True, **result}


def main(argv):
    parser = ArgumentParser(prog="python -m plate", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Build and render a new .plate bundle from JSON.")
    build.add_argument("spec", type=Path)
    build.add_argument("--output", required=True, type=Path)
    apply = commands.add_parser("apply", help="Apply a JSON patch, render and save a .plate bundle.")
    apply.add_argument("bundle", type=Path)
    apply.add_argument("spec", type=Path)
    apply.add_argument("--output", required=True, type=Path)
    inspect = commands.add_parser("inspect", help="Read geometry, render states, checks and recorded provenance.")
    inspect.add_argument("bundle", type=Path)
    inspect.add_argument("--compare-environment", action="store_true", help="Compare saved and local render environments.")
    export = commands.add_parser("export", help="Refresh the bundle and export PDF, PNG or TIFF.")
    export.add_argument("bundle", type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--dpi", type=int, choices=DPIS, default=300)
    export.add_argument("--draft", action="store_true", help="Allow previous or missing artwork and list affected panels.")
    for command in (build, apply, export):
        command.add_argument("--force", action="store_true", help="Rerun scripts even when their cached renders match.")
    for command in (inspect, export):
        command.add_argument("--data-root", type=Path, help="Use a local data folder for this invocation.")
    options = parser.parse_args(argv)
    if hasattr(options, "bundle"):
        options.bundle = options.bundle.expanduser()
    if hasattr(options, "spec"):
        options.spec = options.spec.expanduser()
    try:
        with TemporaryDirectory(prefix="plate-cli-") as scratch:
            result = execute(options, Path(scratch) / "workspaces")
    except (OSError, ValueError, TypeError, LookupError, RuntimeError, BadZipFile, subprocess.SubprocessError) as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["ok"] else 1
