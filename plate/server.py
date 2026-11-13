"""Local HTTP interface and project session."""

from dataclasses import asdict
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import subprocess
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
from zipfile import BadZipFile

from .bundle import SAFE_ID, atomic_write, open_bundle, save_bundle, script_path, write_json, write_workspace
from .checks import project_checks
from .layout import Layout, apply
from .model import Project, SCRIPT_EXTENSIONS, project_from_dict, presets
from .export import FORMATS, compose_pdf, rasterize
from .native import native_signature, render_native
from .fonts import get_font
from .interpreters import discovery, interpreter, probe
from .render import render_script, signature
from .style import BUILTINS, ENUMS, PT_PER_MM, TOKENS, content_box, resolve, validate_style
from .watcher import Watcher, save_script, sync_scripts

WEB = Path(__file__).parent / "web"
WORKSPACES = Path.home() / "Library/Application Support/Plate/workspaces"


class Session:
    def __init__(self, bundle=None, workspaces=WORKSPACES):
        self.workspaces = workspaces
        if not hasattr(self, "lock"):
            self.lock = RLock()
        self.renders = {}
        self.bundle = Path(bundle).resolve() if bundle else None
        if self.bundle:
            self.project, self.workspace = open_bundle(self.bundle, workspaces)
            index = self.workspace / "cache/index.json"
            if index.is_file():
                self.renders = json.loads(index.read_text())
        else:
            self.project = Project()
            self.workspace = workspaces / self.project.id
            write_workspace(self.project, self.workspace)

    def render_state(self, panel, rect):
        previous = self.renders.get(panel.id, {})
        current = self.panel_signature(panel, rect)
        if previous.get("signature") == current or not previous:
            return {"state": "stale", **previous}
        return {**previous, "state": "stale"}

    def panel_signature(self, panel, rect):
        try:
            if panel.type in SCRIPT_EXTENSIONS:
                return signature(self.project, panel, rect)
            return native_signature(self.project, panel, rect)
        except ValueError:
            return None

    def render_native_panels(self, geometry):
        for panel in self.project.panels:
            if panel.type not in SCRIPT_EXTENSIONS and self.render_state(panel, geometry[panel.id])["state"] == "stale":
                self.refresh_panel(panel, geometry[panel.id])

    def state(self):
        geometry = Layout(self.project).view()
        renders = {panel.id: self.render_state(panel, geometry["rects"][panel.id])
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
                font = get_font(style["font_family"], style["panel_label_weight"] == "bold")
                render["label_metadata"] = {
                    "text": panel.label, "font": font.name, "size": style["panel_label_pt"],
                    "page_pt": [rect["w"] * PT_PER_MM, rect["h"] * PT_PER_MM],
                }
                x, y = (style[f"label_offset_{axis}_mm"] * PT_PER_MM for axis in ("x", "y"))
                render["label_metadata"]["bbox"] = [
                    x, y, x + font.text_length(panel.label, fontsize=style["panel_label_pt"]),
                    y + (font.ascender-font.descender) * style["panel_label_pt"],
                ]
            render["style"] = {key: style[key] for key in ("font_family", "panel_label_pt",
                                "panel_label_weight", "label_offset_x_mm", "label_offset_y_mm")}
        return {
            "project": asdict(self.project),
            "geometry": geometry,
            "bundle": str(self.bundle or ""),
            "workspace": str(self.workspace),
            "style_tokens": TOKENS,
            "style_options": ENUMS,
            "palettes": BUILTINS,
            "renders": renders,
            "checks": project_checks(self.project, renders, presets(), resolve),
        }

    def refresh(self, panel_ids):
        geometry = Layout(self.project).rects
        for panel in self.project.panels:
            if panel.id in panel_ids:
                self.refresh_panel(panel, geometry[panel.id])
        write_json(self.workspace / "cache/index.json", self.renders)

    def refresh_panel(self, panel, rect):
        try:
            if panel.type in SCRIPT_EXTENSIONS:
                result = render_script(self.project, panel, rect, self.workspace, self.bundle)
            else:
                result = render_native(self.project, panel, rect, self.workspace)
            self.renders[panel.id] = result
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
            logging.getLogger("plate").info("Render failed for %s: %s", panel.id, error)
            self.renders[panel.id] = {
                **self.renders.get(panel.id, {}), "state": "error",
                "signature": self.panel_signature(panel, rect),
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
        Layout(project)
        validate_style(project)
        for panel in project.panels:
            if panel.type in SCRIPT_EXTENSIONS and not script_path(self.workspace, panel).exists():
                atomic_write(script_path(self.workspace, panel),
                             lambda tmp: tmp.write_text(panel.script, encoding="utf-8"))
        write_workspace(project, self.workspace, write_scripts=False)
        self.project = project
        self.render_native_panels(Layout(project).rects)
        return self.state()

    def export(self, data):
        format = data["format"]
        if format not in FORMATS:
            raise ValueError("Choose PDF, PNG or TIFF.")
        path = Path(data["path"]).expanduser().with_suffix(f".{format}")
        if self.bundle and path.resolve() == self.bundle:
            raise ValueError("Choose a separate destination for the export.")
        rects = Layout(self.project).rects
        self.render_native_panels(rects)
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
            return result if result["conflict"] else self.state()
        if endpoint == "/api/reveal-script":
            panel = next(panel for panel in self.project.panels if panel.id == data["panel"])
            path = script_path(self.workspace, panel)
            subprocess.run(["/usr/bin/open", "-R", str(path)], check=True, timeout=5)
            return {"path": str(path)}
        if endpoint == "/api/asset":
            path = Path(data["path"]).expanduser()
            panel = next(panel for panel in self.project.panels if panel.id == data["panel"])
            extensions = {"image": {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"},
                          "vector": {".pdf", ".svg"}}
            suffix = path.suffix.lower()
            if suffix not in extensions.get(panel.type, set()):
                raise ValueError("Choose an asset matching this panel type.")
            if path.stat().st_size > 150 * 1024 * 1024:
                raise ValueError("Choose an asset smaller than 150 MB.")
            content = path.read_bytes()
            asset = f"assets/{sha256(content).hexdigest()}{suffix}"
            atomic_write(self.workspace / asset, lambda file: file.write_bytes(content))
            project = asdict(self.project)
            record = next(item for item in project["panels"] if item["id"] == panel.id)
            record["asset"] = asset
            record["settings"]["filename"] = path.name
            return self.update(project)
        if endpoint == "/api/style-json":
            result = resolve(self.project)
            result["size_mm"] = [self.project.size.width_mm, self.project.size.height_mm]
            return result
        if endpoint == "/api/export":
            return self.export(data)
        if endpoint == "/api/refresh":
            requested = data.get("panels")
            if requested is None:
                geometry = Layout(self.project).rects
                requested = [panel.id for panel in self.project.panels
                             if self.render_state(panel, geometry[panel.id]).get("state") in {"stale", "error"}]
            self.refresh(requested)
            return self.state()
        if endpoint == "/api/interpreters":
            return discovery(data.get("venvs", []))
        if endpoint == "/api/dependencies":
            panel = next(panel for panel in self.project.panels if panel.id == data["panel"])
            return probe(interpreter(self.project, panel), panel.type, refresh=True)
        if endpoint == "/api/layout":
            return self.update(asdict(apply(self.project, data)))
        if endpoint == "/api/project":
            return self.update(data)
        if endpoint == "/api/new":
            self.__init__(workspaces=self.workspaces)
        elif endpoint == "/api/open":
            self.__init__(Path(data["path"]).expanduser(), self.workspaces)
            self.render_native_panels(Layout(self.project).rects)
        elif endpoint == "/api/save":
            path = Path(data["path"]).expanduser() if data.get("path") else self.bundle
            if not path:
                raise ValueError("Choose a .plate file to save.")
            if path.suffix.lower() != ".plate":
                path = path.with_suffix(".plate")
            if data.get("cache"):
                write_json(self.workspace / "cache/index.json", self.renders)
            save_bundle(self.project, self.workspace, path, data.get("cache", False), write_scripts=False)
            self.bundle = path.resolve()
        else:
            raise ValueError("Unknown project action.")
        return self.state()


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
        path = urlsplit(self.path).path
        if path.startswith("/preview/"):
            key = path.removeprefix("/preview/")
            if len(key) != 64 or not SAFE_ID.fullmatch(key):
                self.send_error(404)
                return
            with self.server.session.lock:
                preview = self.server.session.workspace / "cache" / f"{key}.png"
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
        elif path == "/api/presets":
            self.json(presets())
        else:
            file = (WEB / path.lstrip("/")).resolve() if path != "/" else WEB / "index.html"
            if not file.is_relative_to(WEB) or not file.is_file():
                self.send_error(404)
                return
            self.send(file.read_bytes(), mimetypes.guess_type(file)[0] or "application/octet-stream")

    def do_POST(self):
        if (not self.allowed()):
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
    server.session.render_native_panels(Layout(server.session.project).rects)
    server.watcher = Watcher(server.session)
    server.watcher.start()
    return server
