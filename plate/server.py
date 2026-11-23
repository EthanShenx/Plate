"""Local HTTP interface and project session."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from dataclasses import asdict, replace
from hashlib import sha256
from hmac import compare_digest
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, RLock
from time import time
from urllib.parse import urlsplit
from zipfile import BadZipFile

from .alignment import dependency_signature, fixed_axes, participating, validate_groups
from .bundle import (
    DATA_FOLDER, PROVENANCE_FILE, SAFE_ID, asset_path, atomic_write, declared_data_files, import_asset,
    open_bundle, read_workspace, save_bundle, script_path, write_json, write_workspace,
)
from .checks import project_checks
from .grid import apply_grid, as_grid, fit_artboard, is_grid, validate_panel_groups
from .layout import Layout
from .library import FigureLibrary
from .model import Project, SCRIPT_EXTENSIONS, new_id, project_from_dict, presets
from .export import FORMATS, compose_pdf, rasterize
from .native import native_signature, render_native
from .fonts import label_metrics
from .interpreters import discovery, interpreter, probe
from .provenance import compare_environment, read_provenance, render_environment
from .render import (
    PREVIEW_DPI, data_directory, input_fingerprints, make_preview, prepare_script, render_script,
    seed_matplotlib_cache, signature,
)
from .style import BUILTINS, ENUMS, PT_PER_MM, TOKENS, content_box, context_for, resolve, validate_style
from .watcher import Watcher, save_script, sync_scripts

WEB = Path(__file__).parent / "web"
WORKSPACES = Path.home() / "Library/Application Support/Plate/workspaces"
RENDER_ERRORS = (ValueError, OSError, RuntimeError, subprocess.SubprocessError)
MAX_RENDER_WORKERS = 3
PREVIEW_LOCK = Lock()
DESKTOP_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
               "img-src 'self' data: blob:; object-src 'none'; base-uri 'none'; "
               "form-action 'self'; frame-ancestors 'none'; frame-src 'none'")


def workspace_record(workspace):
    try:
        record = json.loads((workspace / "library.json").read_text(encoding="utf-8"))
        return record if isinstance(record, dict) else {}
    except (OSError, ValueError):
        return {}


def project_digest(project):
    if isinstance(project, dict) and project.get("embedded_data") is False:
        project = {key: value for key, value in project.items() if key != "embedded_data"}
    return sha256(json.dumps(project, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def project_library(workspaces):
    projects = []
    for workspace in workspaces.iterdir():
        if workspace.is_symlink() or not workspace.is_dir():
            continue
        manifest = workspace / "manifest.json"
        try:
            project = json.loads(manifest.read_text(encoding="utf-8"))
            name = project.get("name", project.get("title", "Untitled figure"))
            if not isinstance(name, str):
                continue
            panel_count = len(project.get("panel_ids", []))
            record = workspace_record(workspace)
            if not record and not panel_count and name == "Untitled figure":
                continue
            bundle = record.get("bundle", "")
            projects.append({
                "id": workspace.name, "name": name, "panels": panel_count,
                "bundle": bundle if isinstance(bundle, str) else "",
                "modified": max(manifest.stat().st_mtime, record.get("opened_at", 0)),
            })
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return sorted(projects, key=lambda project: project["modified"], reverse=True)


def has_render_source(panel):
    if panel.type in SCRIPT_EXTENSIONS:
        return bool(panel.script.strip())
    return panel.type not in {"image", "vector"} or bool(panel.asset)


class IncompleteExport(ValueError):
    def __init__(self, issues):
        super().__init__("Some panels do not have a current render. Review the affected panels.")
        self.issues = issues


class Session:
    def __init__(self, bundle=None, workspaces=WORKSPACES, *, workspace=None):
        self.workspaces = workspaces
        self.matplotlib_cache = workspaces.parent / "matplotlib"
        if not hasattr(self, "lock"):
            self.lock = RLock()
        self.renders = {}
        self.data_root_override = ""
        self.keep_cache = False
        self.registered_workspace = workspace is not None
        self.bundle = Path(bundle).resolve() if bundle else None
        self.saved_digest = None
        if workspace is not None:
            self.workspace = workspace
            self.project = read_workspace(workspace)
            record = workspace_record(workspace)
            if isinstance(record.get("bundle"), str) and record["bundle"]:
                self.bundle = Path(record["bundle"])
            self.saved_digest = record.get("saved_digest")
            self.data_root_override = record.get("data_root_override", "")
        elif self.bundle:
            self.project, self.workspace = open_bundle(self.bundle, workspaces)
        else:
            self.project = Project()
            self.project.size.minimum_mm = 4
            as_grid(self.project)
            self.workspace = workspaces / self.project.id
            write_workspace(self.project, self.workspace)
        as_grid(self.project)
        Layout(self.project)
        validate_style(self.project)
        validate_groups(self.project)
        validate_panel_groups(self.project)
        self.provenance = read_provenance(self.workspace)
        index = self.workspace / "cache/index.json"
        if index.is_file():
            self.renders = json.loads(index.read_text())
            self.keep_cache = True
        if workspace is not None:
            self.keep_cache = record.get("keep_cache", self.keep_cache)
        elif self.bundle:
            self.saved_digest = project_digest(asdict(self.project))
            self.remember_workspace()
        try:
            seed_matplotlib_cache(self.matplotlib_cache, self.workspaces)
            if self.workspaces != WORKSPACES:
                seed_matplotlib_cache(self.matplotlib_cache, WORKSPACES)
        except OSError as error:
            logging.getLogger("plate").info("Could not reuse Matplotlib font cache: %s", error)

    def remember_workspace(self):
        write_json(self.workspace / "library.json", {
            "bundle": str(self.bundle or ""), "saved_digest": self.saved_digest,
            "keep_cache": self.keep_cache, "opened_at": time(),
            "data_root_override": self.data_root_override,
        })
        self.registered_workspace = True

    def render_state(self, panel, rect, rects=None):
        if not has_render_source(panel):
            return {"state": "empty"}
        previous = self.renders.get(panel.id, {})
        current = self.panel_signature(panel, rect, rects)
        if previous.get("signature") != current:
            return {**previous, "state": "stale"}
        if previous.get("state") == "fresh" and panel.type in SCRIPT_EXTENSIONS:
            stamp = previous.get("interpreter_stamp")
            if stamp:
                try:
                    path = interpreter(self.project, panel)
                    if [path, Path(path).stat().st_mtime_ns] != stamp:
                        return {**previous, "state": "stale"}
                except (OSError, ValueError):
                    return {**previous, "state": "stale"}
        return {"state": "stale", **previous}

    def data_folder(self):
        return data_directory(self.project, self.workspace, self.bundle, self.data_root_override).resolve()

    def panel_signature(self, panel, rect, rects=None):
        try:
            if panel.type in SCRIPT_EXTENSIONS:
                directory = self.data_folder()
                layout_signature = (
                    dependency_signature(self.project, panel, rects or Layout(self.project).rects)
                    if self.project.alignment else signature(self.project, panel, rect)
                )
                members = participating(self.project, {panel.id}) if self.project.alignment else {panel.id}
                candidates = self.project.panels if self.project.alignment else (panel,)
                inputs = {other.id: input_fingerprints(other, directory) for other in candidates
                          if other.id in members and other.input_files}
                return project_digest([layout_signature, str(directory), directory.is_dir(), inputs])
            return native_signature(self.project, panel, rect)
        except ValueError:
            return None

    def initialize_native_panels(self):
        geometry = Layout(self.project).rects
        for panel in self.project.panels:
            if panel.type not in SCRIPT_EXTENSIONS and panel.id not in self.renders and has_render_source(panel):
                self.refresh_panel(panel, geometry[panel.id])

    def state(self):
        geometry = Layout(self.project).view()
        renders = {panel.id: self.render_state(panel, geometry["rects"][panel.id], geometry["rects"])
                   for panel in self.project.panels}
        for panel in self.project.panels:
            render = renders[panel.id]
            rect = geometry["rects"][panel.id]
            style = resolve(self.project, panel)["style"]
            try:
                render["box"] = content_box(rect, panel, style)
            except ValueError:
                render["box"] = rect
            if panel.label:
                width, height = rect["w"] * PT_PER_MM, rect["h"] * PT_PER_MM
                font, size, bounds = label_metrics(panel.label, width, height - PT_PER_MM, style)
                render["label_metadata"] = {
                    "text": panel.label, "font": font.name, "size": size,
                    "page_pt": [width, height], "bbox": bounds,
                }
            render["style"] = {key: style[key] for key in ("font_family", "panel_label_pt",
                                "panel_label_weight", "label_offset_x_mm", "label_offset_y_mm")}
        project = asdict(self.project)
        return {
            "project": project,
            "geometry": geometry,
            "bundle": str(self.bundle or ""),
            "bundle_dirty": bool(self.bundle and self.saved_digest != project_digest(project)),
            "workspace": str(self.workspace),
            "workspace_id": self.workspace.name,
            "workspace_registered": self.registered_workspace,
            "data_root_override": self.data_root_override,
            "keep_cache": self.keep_cache,
            "style_tokens": TOKENS,
            "style_options": ENUMS,
            "palettes": BUILTINS,
            "renders": renders,
            "export_issues": self.export_issues(self.export_inputs(geometry["rects"], renders)),
            "checks": project_checks(self.project, renders, presets(), resolve),
        }

    def refresh(self, panel_ids, *, force=False):
        geometry = Layout(self.project).rects
        requested = participating(self.project, panel_ids)
        panels = [panel for panel in self.project.panels if panel.id in requested and has_render_source(panel)]
        if not panels:
            return
        scripts = [panel for panel in panels if panel.type in SCRIPT_EXTENSIONS]
        signatures = {panel.id: self.panel_signature(panel, geometry[panel.id], geometry) for panel in scripts}
        workers = min(MAX_RENDER_WORKERS, os.cpu_count() or 1, len(scripts))
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                self.refresh_batch(panels, geometry, {}, executor, force=force)
                self.align_renders(scripts, geometry, executor, force=force)
        else:
            for panel in panels:
                self.refresh_panel(panel, geometry[panel.id], force=force)
            self.align_renders(scripts, geometry, force=force)
        for panel in scripts:
            self.renders[panel.id]["signature"] = signatures[panel.id]
        write_json(self.workspace / "cache/index.json", self.renders)

    def refresh_pending(self, *, force=False):
        rects = Layout(self.project).rects
        self.refresh([panel.id for panel in self.project.panels
                      if force or self.render_state(panel, rects[panel.id], rects)["state"] in {"stale", "error"}
                      or (has_render_source(panel) and self.render_pdf(self.renders.get(panel.id, {})) is None)],
                     force=force)

    def refresh_batch(self, panels, geometry, contexts, executor, *, force=False):
        # Only subprocess execution runs concurrently. PDF processing and
        # session state stay on the request thread.
        with ExitStack() as stack:
            submitted = {}
            pending = {}
            for panel in panels:
                if panel.type not in SCRIPT_EXTENSIONS:
                    continue
                rect = geometry[panel.id]
                try:
                    job, finish = stack.enter_context(prepare_script(
                        self.project, panel, rect, self.workspace, self.bundle,
                        contexts.get(panel.id), matplotlib_cache=self.matplotlib_cache,
                        data_root=self.data_root_override, force=force))
                    if finish is None:
                        self.store_render(panel, rect, job, geometry)
                        continue
                    if job.key not in submitted:
                        future = executor.submit(job.run)
                        submitted[job.key] = future
                        pending[future] = (finish, [])
                    pending[submitted[job.key]][1].append(panel)
                except RENDER_ERRORS as error:
                    self.render_error(panel, rect, error, geometry)
            for panel in panels:
                if panel.type not in SCRIPT_EXTENSIONS:
                    self.refresh_panel(panel, geometry[panel.id])
            for future in as_completed(pending):
                finish, users = pending[future]
                try:
                    result = finish(future.result())
                except RENDER_ERRORS as error:
                    for panel in users:
                        self.render_error(panel, geometry[panel.id], error, geometry)
                else:
                    for panel in users:
                        self.store_render(panel, geometry[panel.id], result.copy(), geometry)

    def align_renders(self, scripts, geometry, executor=None, *, force=False):
        if not self.project.alignment:
            return
        measured = {panel.id: self.renders[panel.id].get("metadata", {}).get("axes")
                    if self.renders[panel.id].get("state") == "fresh" else None for panel in scripts}
        targets, warnings = fixed_axes(self.project, geometry, measured)
        aligned = [panel for panel in scripts if panel.id in targets]
        contexts = {
            panel.id: {**context_for(self.project, panel, geometry[panel.id]),
                       "fixed_axes": targets[panel.id]} for panel in aligned
        }
        if executor and len(aligned) > 1:
            self.refresh_batch(aligned, geometry, contexts, executor, force=force)
        else:
            for panel in aligned:
                self.refresh_panel(panel, geometry[panel.id], contexts[panel.id], force=force)
        for panel in scripts:
            if panel.id in contexts:
                actual = self.renders[panel.id].get("metadata", {}).get("axes")
                if not actual or any(abs(a-b)*mm > .15 for a, b, mm in
                                     zip(actual, targets[panel.id], contexts[panel.id]["size_mm"]*2, strict=True)):
                    warnings.setdefault(panel.id, []).append("The plot could not reach the requested alignment.")
            result = self.renders[panel.id]
            result["warnings"] = [*result.get("warnings", []), *warnings.get(panel.id, [])]

    def refresh_panel(self, panel, rect, context=None, *, force=False):
        try:
            if panel.type in SCRIPT_EXTENSIONS:
                result = render_script(self.project, panel, rect, self.workspace, self.bundle, context,
                                       matplotlib_cache=self.matplotlib_cache, data_root=self.data_root_override,
                                       force=force)
            else:
                result = render_native(self.project, panel, rect, self.workspace)
            self.store_render(panel, rect, result)
        except RENDER_ERRORS as error:
            self.render_error(panel, rect, error)

    def store_render(self, panel, rect, result, geometry=None):
        self.renders[panel.id] = result
        result["signature"] = self.panel_signature(panel, rect, geometry)

    def render_error(self, panel, rect, error, geometry=None):
        logging.getLogger("plate").info("Render failed for %s: %s", panel.id, error)
        self.renders[panel.id] = {
            **self.renders.get(panel.id, {}), "state": "error",
            "signature": self.panel_signature(panel, rect, geometry),
            "error": str(error), "stdout": getattr(error, "stdout", ""),
            "stderr": getattr(error, "stderr", ""),
        }

    def update(self, data):
        project = project_from_dict(data)
        current = {panel.id: panel for panel in self.project.panels}
        for panel in project.panels:
            if panel.id in current and panel.type in SCRIPT_EXTENSIONS:
                panel.script = current[panel.id].script
        if project.id != self.project.id:
            raise ValueError("This project is no longer open.")
        if is_grid(project.layout) and (
            project.size.width_mm != self.project.size.width_mm or
            project.size.height_mm != self.project.size.height_mm
        ):
            fit_artboard(project)
        self.store_project(project)
        return self.state()

    def store_project(self, project, *, write_scripts=False):
        Layout(project)
        validate_style(project)
        validate_groups(project)
        validate_panel_groups(project)
        for panel in project.panels:
            if panel.asset:
                asset_path(self.workspace, panel.asset)
            if (not write_scripts and panel.type in SCRIPT_EXTENSIONS
                    and not script_path(self.workspace, panel).exists()):
                atomic_write(script_path(self.workspace, panel),
                             lambda tmp: tmp.write_text(panel.script, encoding="utf-8"))
        write_workspace(project, self.workspace, write_scripts=write_scripts)
        self.project = project
        self.renders = {panel.id: self.renders[panel.id] for panel in project.panels if panel.id in self.renders}

    def save(self, path=None, *, cache=False):
        path = Path(path).expanduser() if path else self.bundle
        if not path:
            raise ValueError("Choose a .plate file to save.")
        if path.suffix.lower() != ".plate":
            path = path.with_suffix(".plate")
        path = path.resolve()
        project = self.project
        if self.bundle or project.data_root:
            original = data_directory(project, self.workspace, self.bundle).resolve()
            new_root = data_directory(project, self.workspace, path).resolve()
            if new_root != original:
                root = os.path.relpath(original, path.parent)
                project = replace(project, data_root=root if root != "." or project.embedded_data else "")
        provenance = self.current_provenance()
        write_json(self.workspace / "cache/index.json", self.renders)
        save_bundle(project, self.workspace, path, cache, write_scripts=False, provenance=provenance)
        write_json(self.workspace / PROVENANCE_FILE, provenance)
        self.provenance = provenance
        self.project, self.bundle = project, path
        self.keep_cache = bool(cache)
        self.saved_digest = project_digest(asdict(self.project))
        self.remember_workspace()

    def share(self, path, *, cache=False):
        path = Path(path).expanduser().with_suffix(".plate").resolve()
        inputs = declared_data_files(self.project, self.data_folder(), required=True)
        if path == self.bundle or path in inputs.values():
            raise ValueError("Choose a new path for the shareable copy.")

        project = replace(self.project, id=new_id(), data_root="", embedded_data=True, interpreters={},
                          panels=[replace(panel, interpreter="") for panel in self.project.panels])
        provenance = self.current_provenance()
        for panel_id, environment in provenance.items():
            if "interpreter" in environment:
                provenance[panel_id] = {**environment,
                                        "interpreter": Path(environment["interpreter"]).name}
        with TemporaryDirectory(dir=self.workspace) as scratch:
            workspace = Path(scratch)
            for relative, source in inputs.items():
                target = workspace / DATA_FOLDER / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            for asset in {panel.asset for panel in project.panels if panel.asset}:
                target = asset_path(workspace, asset)
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(asset_path(self.workspace, asset), target)
            if cache:
                self.copy_current_previews(workspace)
            save_bundle(project, workspace, path, cache, provenance=provenance)
        return {"path": str(path)}

    def copy_current_previews(self, workspace):
        rects = Layout(self.project).rects
        renders = {}
        for panel in self.project.panels:
            render = self.render_state(panel, rects[panel.id], rects)
            pdf = self.render_pdf(render)
            if render["state"] != "fresh" or not pdf or not pdf.with_suffix(".png").is_file():
                continue
            for source in (pdf, pdf.with_suffix(".png")):
                target = workspace / "cache" / source.name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(source, target)
            renders[panel.id] = {key: render[key] for key in ("key", "signature", "metadata")}
            renders[panel.id]["state"] = "stale" if panel.type in SCRIPT_EXTENSIONS else "fresh"
        if renders:
            write_json(workspace / "cache/index.json", renders)

    def current_provenance(self, *, prefer_saved=False):
        state = self.state()
        recorded = {}
        for panel in self.project.panels:
            render = state["renders"][panel.id]
            baseline = self.provenance.get(panel.id)
            if render["state"] == "fresh" and not (prefer_saved and baseline):
                baseline = render_environment(panel, render) or baseline
            if baseline:
                recorded[panel.id] = baseline
        return recorded

    def environment_report(self):
        return compare_environment(self.project, self.current_provenance(prefer_saved=True), self.data_folder())

    def remap_data_folder(self, location):
        if not isinstance(location, str):
            raise ValueError("Enter a folder path.")
        folder = Path(location).expanduser()
        if location and (not folder.is_absolute() or not folder.is_dir()):
            raise ValueError("Choose an existing absolute path for the local data folder.")
        self.data_root_override = str(folder.resolve()) if location else ""

    def render_pdf(self, render):
        key = render.get("key")
        if isinstance(key, str) and SAFE_ID.fullmatch(key):
            source = self.workspace / "cache" / f"{key}.pdf"
            if source.is_file():
                return source
        return None

    def export_inputs(self, rects, renders):
        for panel in self.project.panels:
            rect = rects[panel.id]
            style = resolve(self.project, panel)["style"]
            render = renders[panel.id]
            source = self.render_pdf(render)
            try:
                box = content_box(rect, panel, style)
            except ValueError:
                source, box = None, rect
            yield panel, render, (source, box, panel.label, rect, style)

    def export_issues(self, inputs):
        issues = []
        for panel, render, (source, *_) in inputs:
            state = render["state"]
            if state == "fresh" and source:
                continue
            reason = {
                "stale": "Render is out of date.",
                "error": render.get("error") or "Render failed.",
                "empty": "No script or asset is set.",
            }.get(state, "Rendered artwork is missing.")
            issues.append({"panel": panel.id, "name": panel.name, "label": panel.label,
                           "reason": reason, "uses_previous": source is not None})
        return issues

    def export(self, data):
        format = data["format"]
        if format not in FORMATS:
            raise ValueError("Choose PDF, PNG or TIFF.")
        path = Path(data["path"]).expanduser().with_suffix(f".{format}")
        if self.bundle and path.resolve() == self.bundle:
            raise ValueError("Choose a separate destination for the export.")
        rects = Layout(self.project).rects
        renders = {panel.id: self.render_state(panel, rects[panel.id], rects)
                   for panel in self.project.panels}
        inputs = list(self.export_inputs(rects, renders))
        issues = self.export_issues(inputs)
        draft = data.get("draft") is True
        if issues and (not draft or data.get("reviewed_issues", issues) != issues):
            raise IncompleteExport(issues)
        panels = [entry for _, _, entry in inputs]
        size = self.project.size
        result = compose_pdf(size.width_mm, size.height_mm, panels)
        if format != "pdf":
            result = rasterize(result, size.width_mm, size.height_mm, format, data["dpi"])
        atomic_write(path, lambda file: file.write_bytes(result))
        return {"path": str(path.resolve()), "draft": draft, "export_issues": issues}

    def action(self, endpoint, data):
        sync_scripts(self.project, self.workspace)
        if endpoint == "/api/script":
            source = data["script"]
            if not isinstance(source, str):
                raise ValueError("Script must be text.")
            result = save_script(self.project, self.workspace, data["panel"], source, data["base"])
            if result["conflict"]:
                return result
            self.remember_workspace()
            return self.state()
        if endpoint == "/api/reveal-workspace":
            subprocess.run(["/usr/bin/open", str(self.workspace)], check=True, timeout=5)
            return {"path": str(self.workspace)}
        if endpoint == "/api/reveal-script":
            panel = next(panel for panel in self.project.panels if panel.id == data["panel"])
            path = script_path(self.workspace, panel)
            subprocess.run(["/usr/bin/open", "-R", str(path)], check=True, timeout=5)
            return {"path": str(path)}
        if endpoint == "/api/asset":
            path = Path(data["path"]).expanduser()
            panel = next(panel for panel in self.project.panels if panel.id == data["panel"])
            asset = import_asset(self.workspace, panel.type, path)
            project = asdict(self.project)
            record = next(item for item in project["panels"] if item["id"] == panel.id)
            record["asset"] = asset
            record["settings"]["filename"] = path.name
            self.update(project)
            panel = next(item for item in self.project.panels if item.id == panel.id)
            self.refresh_panel(panel, Layout(self.project).rects[panel.id])
            return self.state()
        if endpoint in {"/api/style-json", "/api/save-style"}:
            result = resolve(self.project)
            result["size_mm"] = [self.project.size.width_mm, self.project.size.height_mm]
            if endpoint == "/api/save-style":
                path = Path(data["path"]).expanduser().with_suffix(".json")
                write_json(path, result)
                return {"path": str(path.resolve())}
            return result
        if endpoint == "/api/export":
            return self.export(data)
        if endpoint == "/api/export-preflight":
            self.refresh_pending()
            return self.state()
        if endpoint == "/api/refresh":
            requested = data.get("panels")
            force = data.get("force") is True
            if requested is None:
                self.refresh_pending(force=force)
            else:
                self.refresh(requested, force=force)
            return self.state()
        if endpoint == "/api/environment":
            return self.environment_report()
        if endpoint == "/api/local-data-folder":
            self.remap_data_folder(data["path"])
            self.remember_workspace()
            return self.state()
        if endpoint == "/api/share":
            return self.share(data["path"], cache=data.get("cache") is True)
        if endpoint == "/api/interpreters":
            return discovery(data.get("venvs", []))
        if endpoint == "/api/dependencies":
            panel = next(panel for panel in self.project.panels if panel.id == data["panel"])
            return probe(interpreter(self.project, panel), panel.type, refresh=True)
        if endpoint == "/api/layout":
            return self.update_layout(data)
        if endpoint == "/api/project":
            return self.update(data)
        if endpoint == "/api/new":
            self.__init__(workspaces=self.workspaces)
            if data.get("name"):
                self.project.name = data["name"]
                write_workspace(self.project, self.workspace)
            self.remember_workspace()
        elif endpoint in {"/api/open", "/api/resume"}:
            if endpoint == "/api/open":
                loaded = Session(Path(data["path"]).expanduser(), self.workspaces)
            else:
                name = data["workspace"]
                if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."}:
                    raise ValueError("Invalid workspace.")
                workspace = self.workspaces / name
                if workspace.is_symlink() or not workspace.is_dir():
                    raise ValueError("This workspace is no longer available.")
                loaded = Session(workspaces=self.workspaces, workspace=workspace)
                loaded.remember_workspace()
            loaded.initialize_native_panels()
            self.project, self.workspace, self.bundle = loaded.project, loaded.workspace, loaded.bundle
            self.renders, self.keep_cache = loaded.renders, loaded.keep_cache
            self.provenance, self.data_root_override = loaded.provenance, loaded.data_root_override
            self.saved_digest = loaded.saved_digest
            self.registered_workspace = loaded.registered_workspace
        elif endpoint == "/api/save":
            self.save(data.get("path"), cache=data.get("cache", False))
        else:
            raise ValueError("Unknown project action.")
        return self.state()

    def update_layout(self, data):
        project = apply_grid(self.project, data)
        auto_render = data.get("auto_render", False)
        if auto_render:
            previous_rects = Layout(self.project).rects
            before = {panel.id: self.panel_signature(panel, previous_rects[panel.id], previous_rects)
                      for panel in self.project.panels}
        if data["kind"] == "delete":
            for group in project.alignment:
                group["panels"] = [id for id in group["panels"] if id != data["panel"]]
            project.alignment = [group for group in project.alignment if len(group["panels"]) > 1]
        result = self.update(asdict(project))
        if auto_render:
            rects = result["geometry"]["rects"]
            result["panels_to_refresh"] = [
                panel.id for panel in self.project.panels
                if result["renders"][panel.id]["state"] != "fresh"
                and (panel.type not in SCRIPT_EXTENSIONS or panel.script.strip())
                and self.panel_signature(panel, rects[panel.id], rects) != before.get(panel.id)
            ]
        return result


class Handler(BaseHTTPRequestHandler):
    def address(self):
        return f"127.0.0.1:{self.server.server_port}"

    def send(self, data, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if self.server.desktop_token:
            self.send_header("Content-Security-Policy", DESKTOP_CSP)
        self.end_headers()
        self.wfile.write(data)

    def json(self, data, status=200):
        self.send(json.dumps(data, ensure_ascii=False).encode(), "application/json", status)

    def allowed(self):
        if self.headers.get("Host") != self.address():
            self.send_error(403)
            return False
        if self.server.desktop_token:
            try:
                cookie = SimpleCookie(self.headers.get("Cookie", "")).get("plate_desktop")
                authorized = cookie and compare_digest(cookie.value.encode(), self.server.desktop_token)
            except CookieError:
                authorized = False
            if not authorized:
                self.send_error(403)
                return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        url = urlsplit(self.path)
        path = url.path
        if path.startswith("/preview/"):
            parts = path.removeprefix("/preview/").split("/")
            key = parts[-1]
            if (len(parts) not in (1, 2) or len(key) != 64 or not SAFE_ID.fullmatch(key)
                    or (len(parts) == 2 and not SAFE_ID.fullmatch(parts[0]))):
                self.send_error(404)
                return
            session = self.server.session
            workspace = session.workspaces / parts[0] if len(parts) == 2 else session.workspace
            if workspace.is_symlink():
                self.send_error(404)
                return
            preview = workspace / "cache" / f"{key}.png"
            variants = {f"dpi={dpi}": dpi for dpi in PREVIEW_DPI[1:]}
            if url.query in variants:
                dpi = variants[url.query]
                source = preview.with_suffix(".pdf")
                variant = workspace / "previews" / f"{key}-{dpi}.png"
                with PREVIEW_LOCK:
                    if source.is_file() and not variant.is_file():
                        try:
                            make_preview(source, variant, dpi)
                        except (OSError, RuntimeError, ValueError):
                            pass
                if variant.is_file():
                    preview = variant
            if not preview.is_file():
                self.send_error(404)
                return
            self.send(preview.read_bytes(), "image/png")
        elif path == "/api/scripts":
            with self.server.session.lock:
                session = self.server.session
                sync_scripts(session.project, session.workspace)
                rects = Layout(session.project).rects
                self.json({
                    "id": session.project.id,
                    "workspace_id": session.workspace.name,
                    "scripts": {panel.id: panel.script for panel in session.project.panels
                                if panel.type in SCRIPT_EXTENSIONS},
                    "stale_inputs": [
                        panel.id for panel in session.project.panels if panel.input_files
                        and session.render_state(panel, rects[panel.id], rects)["state"] == "stale"
                    ],
                })
        elif path == "/api/project":
            with self.server.session.lock:
                session = self.server.session
                sync_scripts(session.project, session.workspace)
                self.json(self.server.workbench_state())
        elif path == "/api/projects":
            with self.server.session.lock:
                self.json(self.server.library_state())
        elif path == "/api/presets":
            self.json(presets())
        else:
            file = (WEB / path.lstrip("/")).resolve() if path != "/" else WEB / "index.html"
            if not file.is_relative_to(WEB) or not file.is_file():
                self.send_error(404)
                return
            self.send(file.read_bytes(), mimetypes.guess_type(file)[0] or "application/octet-stream")

    def do_POST(self):
        if not self.allowed():
            return
        if (self.headers.get("Origin") != f"http://{self.address()}"
                or self.headers.get_content_type() != "application/json"):
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 20 * 1024 * 1024:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(size))
            with self.server.session.lock:
                workspace = self.headers.get("X-Plate-Workspace")
                if workspace and workspace != self.server.session.workspace.name:
                    raise ValueError("This figure is no longer active. Reopen its tab before editing.")
                result = self.server.act(urlsplit(self.path).path, data)
            self.json(result)
        except IncompleteExport as error:
            self.json({"error": str(error), "export_issues": error.issues}, 409)
        except (ValueError, TypeError, KeyError, OSError, BadZipFile, StopIteration, subprocess.SubprocessError) as error:
            self.json({"error": str(error)}, 400)

    def log_message(self, format, *args):
        if args and str(args[-2]).startswith(("4", "5")):
            logging.getLogger("plate").info(format, *args)


class PlateServer(ThreadingHTTPServer):
    def library_state(self):
        figures = project_library(self.session.workspaces)
        for figure in figures:
            self.library.include(figure["id"], figure["name"])
        return self.library.view(figures)

    def workbench_state(self):
        return {**self.session.state(), "library": self.library_state()}

    def act(self, endpoint, data):
        session, library = self.session, self.library
        active = session.workspace.name
        if endpoint in {"/api/new", "/api/new-figure", "/api/open", "/api/resume"}:
            project_id = data.get("project")
            if project_id is not None and project_id not in library.projects:
                raise ValueError("Choose an existing project.")
            if endpoint in {"/api/new", "/api/new-figure"}:
                members = library.projects[project_id]["figures"] if project_id else []
                names = {item["name"] for item in project_library(session.workspaces) if item["id"] in members}
                index = 1
                while f"Figure {index}" in names:
                    index += 1
                data = {"name": f"Figure {index}"}
            if endpoint == "/api/open":
                path = str(Path(data["path"]).expanduser().resolve())
                existing = next((item["id"] for item in project_library(session.workspaces)
                                 if item["bundle"] == path), None)
                if existing:
                    endpoint, data = "/api/resume", {"workspace": existing}
            if endpoint != "/api/resume" or data["workspace"] != active:
                session.action("/api/new" if endpoint == "/api/new-figure" else endpoint, data)
            figure = session.workspace.name
            if not library.project_for(figure):
                name = session.project.name if endpoint in {"/api/open", "/api/resume"} else library.untitled_name()
                library.include(figure, name, project_id)
            library.activate(figure)
        elif endpoint == "/api/close-tab":
            figure = data["workspace"]
            if figure == library.active and figure in library.tabs and len(library.tabs) > 1:
                index = library.tabs.index(figure)
                next_tab = library.tabs[index + 1] if index + 1 < len(library.tabs) else library.tabs[index - 1]
                session.action("/api/resume", {"workspace": next_tab})
            library.close(figure)
        elif endpoint == "/api/rename-project":
            name = data["name"].strip()
            if not name:
                raise ValueError("Enter a project name.")
            library.projects[library.project_for(active)]["name"] = name
        elif endpoint == "/api/move-figure":
            library.move(active, data["project"])
        else:
            return session.action(endpoint, data)
        library.save()
        return self.workbench_state()

    def server_close(self):
        if hasattr(self, "watcher"):
            self.watcher.close()
            self.watcher.join(timeout=1)
        super().server_close()


def make_server(bundle=None, workspaces=WORKSPACES, *, desktop_token=""):
    server = PlateServer(("127.0.0.1", 0), Handler)
    server.desktop_token = desktop_token.encode()
    try:
        workspaces.mkdir(parents=True, exist_ok=True)
        library = server.library = FigureLibrary(workspaces)
        figures = project_library(workspaces)
        for figure in figures:
            library.include(figure["id"], figure["name"])
        valid = {figure["id"] for figure in figures}
        library.tabs = [key for key in library.tabs if key in valid]
        if library.active not in library.tabs:
            library.active = next(iter(library.tabs), None)
        if not bundle:
            candidates = [library.active] if library.active else []
            candidates.extend(key for key in library.tabs if key != library.active)
            if not library.initialized and desktop_token:
                candidates.extend(figure["id"] for figure in figures)
            for key in candidates:
                try:
                    server.session = Session(workspaces=workspaces, workspace=workspaces / key)
                    break
                except (ValueError, KeyError, TypeError, OSError):
                    logging.getLogger("plate").info("Could not resume workspace %s", key)
                    library.close(key)
        if not hasattr(server, "session"):
            server.session = Session(bundle, workspaces)
        if server.session.registered_workspace:
            figure = server.session.workspace.name
            library.include(figure, server.session.project.name)
            library.activate(figure)
            library.save()
        server.session.initialize_native_panels()
        if not desktop_token:
            server.watcher = Watcher(server.session)
            server.watcher.start()
    except Exception:
        server.server_close()
        raise
    return server
