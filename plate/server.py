"""Local HTTP interface and project session."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from dataclasses import asdict
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
import subprocess
from pathlib import Path
from threading import Lock, RLock
from time import time
from urllib.parse import urlsplit
from zipfile import BadZipFile

from .alignment import dependency_signature, fixed_axes, participating, validate_groups
from .bundle import (
    SAFE_ID, asset_path, atomic_write, import_asset, open_bundle, read_workspace, save_bundle, script_path,
    write_json, write_workspace,
)
from .checks import project_checks
from .grid import apply_grid, as_grid, fit_artboard, is_grid, validate_panel_groups
from .layout import Layout
from .model import Project, SCRIPT_EXTENSIONS, project_from_dict, presets
from .export import FORMATS, compose_pdf, rasterize
from .native import native_signature, render_native
from .fonts import label_metrics
from .interpreters import discovery, interpreter, probe
from .render import PREVIEW_DPI, data_directory, make_preview, prepare_script, render_script, seed_matplotlib_cache, signature
from .style import BUILTINS, ENUMS, PT_PER_MM, TOKENS, content_box, context_for, resolve, validate_style
from .watcher import Watcher, save_script, sync_scripts

WEB = Path(__file__).parent / "web"
WORKSPACES = Path.home() / "Library/Application Support/Plate/workspaces"
RENDER_ERRORS = (ValueError, OSError, RuntimeError, subprocess.SubprocessError)
MAX_RENDER_WORKERS = 3
PREVIEW_LOCK = Lock()


def workspace_record(workspace):
    try:
        record = json.loads((workspace / "library.json").read_text(encoding="utf-8"))
        return record if isinstance(record, dict) else {}
    except (OSError, ValueError):
        return {}


def project_digest(project):
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


class Session:
    def __init__(self, bundle=None, workspaces=WORKSPACES, *, workspace=None):
        self.workspaces = workspaces
        self.matplotlib_cache = workspaces.parent / "matplotlib"
        if not hasattr(self, "lock"):
            self.lock = RLock()
        self.renders = {}
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
        })
        self.registered_workspace = True

    def render_state(self, panel, rect, rects=None):
        if not has_render_source(panel):
            return {"state": "empty"}
        previous = self.renders.get(panel.id, {})
        current = self.panel_signature(panel, rect, rects)
        if previous.get("signature") == current or not previous:
            return {"state": "stale", **previous}
        return {**previous, "state": "stale"}

    def panel_signature(self, panel, rect, rects=None):
        try:
            if panel.type in SCRIPT_EXTENSIONS:
                directory = data_directory(self.project, self.workspace, self.bundle).resolve()
                previous = self.renders.get(panel.id, {})
                version = previous.get("interpreter_stamp")
                if version:
                    path, stamp = version
                    try:
                        if Path(path).stat().st_mtime_ns != stamp:
                            return None
                    except OSError:
                        return None
                layout_signature = (
                    dependency_signature(self.project, panel, rects or Layout(self.project).rects)
                    if self.project.alignment else signature(self.project, panel, rect)
                )
                return f"{layout_signature}:{directory}"
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
            "keep_cache": self.keep_cache,
            "style_tokens": TOKENS,
            "style_options": ENUMS,
            "palettes": BUILTINS,
            "renders": renders,
            "checks": project_checks(self.project, renders, presets(), resolve),
        }

    def refresh(self, panel_ids):
        geometry = Layout(self.project).rects
        requested = participating(self.project, panel_ids)
        panels = [panel for panel in self.project.panels if panel.id in requested and has_render_source(panel)]
        if not panels:
            return
        scripts = [panel for panel in panels if panel.type in SCRIPT_EXTENSIONS]
        workers = min(MAX_RENDER_WORKERS, os.cpu_count() or 1, len(scripts))
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                self.refresh_batch(panels, geometry, {}, executor)
                self.align_renders(scripts, geometry, executor)
        else:
            for panel in panels:
                self.refresh_panel(panel, geometry[panel.id])
            self.align_renders(scripts, geometry)
        write_json(self.workspace / "cache/index.json", self.renders)

    def refresh_pending(self):
        rects = Layout(self.project).rects
        self.refresh([panel.id for panel in self.project.panels
                      if self.render_state(panel, rects[panel.id], rects)["state"] in {"stale", "error"}])

    def refresh_batch(self, panels, geometry, contexts, executor):
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
                        contexts.get(panel.id), matplotlib_cache=self.matplotlib_cache))
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

    def align_renders(self, scripts, geometry, executor=None):
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
            self.refresh_batch(aligned, geometry, contexts, executor)
        else:
            for panel in aligned:
                self.refresh_panel(panel, geometry[panel.id], contexts[panel.id])
        for panel in scripts:
            if panel.id in contexts:
                actual = self.renders[panel.id].get("metadata", {}).get("axes")
                if not actual or any(abs(a-b)*mm > .15 for a, b, mm in
                                     zip(actual, targets[panel.id], contexts[panel.id]["size_mm"]*2, strict=True)):
                    warnings.setdefault(panel.id, []).append("The plot could not reach the requested alignment.")
            result = self.renders[panel.id]
            result["warnings"] = [*result.get("warnings", []), *warnings.get(panel.id, [])]
            result["signature"] = self.panel_signature(panel, geometry[panel.id], geometry)

    def refresh_panel(self, panel, rect, context=None):
        try:
            if panel.type in SCRIPT_EXTENSIONS:
                result = render_script(self.project, panel, rect, self.workspace, self.bundle, context,
                                       matplotlib_cache=self.matplotlib_cache)
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

    def save(self, path=None, *, cache=False):
        path = Path(path).expanduser() if path else self.bundle
        if not path:
            raise ValueError("Choose a .plate file to save.")
        if path.suffix.lower() != ".plate":
            path = path.with_suffix(".plate")
        if cache:
            write_json(self.workspace / "cache/index.json", self.renders)
        save_bundle(self.project, self.workspace, path, cache, write_scripts=False)
        self.bundle = path.resolve()
        self.keep_cache = bool(cache)
        self.saved_digest = project_digest(asdict(self.project))
        self.remember_workspace()

    def export(self, data):
        format = data["format"]
        if format not in FORMATS:
            raise ValueError("Choose PDF, PNG or TIFF.")
        path = Path(data["path"]).expanduser().with_suffix(f".{format}")
        if self.bundle and path.resolve() == self.bundle:
            raise ValueError("Choose a separate destination for the export.")
        rects = Layout(self.project).rects
        panels = []
        for panel in self.project.panels:
            previous = self.render_state(panel, rects[panel.id])
            key = previous.get("key")
            source = self.workspace / "cache" / f"{key}.pdf" if key else None
            if source and not source.is_file():
                source = None
            style = resolve(self.project, panel)["style"]
            rect = rects[panel.id]
            try:
                box = content_box(rect, panel, style)
            except ValueError:
                source, box = None, rect
            panels.append((source, box, panel.label, rect, style))
        size = self.project.size
        result = compose_pdf(size.width_mm, size.height_mm, panels)
        if format != "pdf":
            result = rasterize(result, size.width_mm, size.height_mm, format, data["dpi"])
        atomic_write(path, lambda file: file.write_bytes(result))
        return {"path": str(path.resolve())}

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
        if endpoint == "/api/style-json":
            result = resolve(self.project)
            result["size_mm"] = [self.project.size.width_mm, self.project.size.height_mm]
            return result
        if endpoint == "/api/export":
            return self.export(data)
        if endpoint == "/api/refresh":
            requested = data.get("panels")
            if requested is None:
                self.refresh_pending()
            else:
                self.refresh(requested)
            return self.state()
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
        self.end_headers()
        self.wfile.write(data)

    def json(self, data, status=200):
        self.send(json.dumps(data, ensure_ascii=False).encode(), "application/json", status)

    def allowed(self):
        if self.headers.get("Host") != self.address():
            self.send_error(403)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        url = urlsplit(self.path)
        path = url.path
        if path.startswith("/preview/"):
            key = path.removeprefix("/preview/")
            if len(key) != 64 or not SAFE_ID.fullmatch(key):
                self.send_error(404)
                return
            workspace = self.server.session.workspace
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
                self.json({
                    "id": session.project.id,
                    "scripts": {panel.id: panel.script for panel in session.project.panels
                                if panel.type in SCRIPT_EXTENSIONS},
                })
        elif path == "/api/project":
            with self.server.session.lock:
                self.json(self.server.session.state())
        elif path == "/api/projects":
            self.json(project_library(self.server.session.workspaces))
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
                result = self.server.session.action(urlsplit(self.path).path, data)
            self.json(result)
        except (ValueError, TypeError, KeyError, OSError, BadZipFile, StopIteration, subprocess.SubprocessError) as error:
            self.json({"error": str(error)}, 400)

    def log_message(self, format, *args):
        if args and str(args[-2]).startswith(("4", "5")):
            logging.getLogger("plate").info(format, *args)


class PlateServer(ThreadingHTTPServer):
    def server_close(self):
        if hasattr(self, "watcher"):
            self.watcher.close()
            self.watcher.join(timeout=1)
        super().server_close()


def make_server(bundle=None, workspaces=WORKSPACES):
    server = PlateServer(("127.0.0.1", 0), Handler)
    server.session = Session(bundle, workspaces)
    server.session.initialize_native_panels()
    server.watcher = Watcher(server.session)
    server.watcher.start()
    return server
