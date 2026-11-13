"""Local HTTP interface and project session."""

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
from zipfile import BadZipFile

from .bundle import open_bundle, save_bundle, write_workspace
from .layout import Layout, apply
from .model import Project, project_from_dict, presets

WEB = Path(__file__).parent / "web"
WORKSPACES = Path.home() / "Library/Application Support/Plate/workspaces"


class Session:
    def __init__(self, bundle=None, workspaces=WORKSPACES):
        self.workspaces = workspaces
        self.lock = RLock()
        self.bundle = Path(bundle).resolve() if bundle else None
        if self.bundle:
            self.project, self.workspace = open_bundle(self.bundle, workspaces)
        else:
            self.project = Project()
            self.workspace = workspaces / self.project.id
            write_workspace(self.project, self.workspace)

    def state(self):
        return {
            "project": asdict(self.project),
            "geometry": Layout(self.project).view(),
            "bundle": str(self.bundle or ""),
            "workspace": str(self.workspace),
        }

    def update(self, data):
        project = project_from_dict(data)
        if project.id != self.project.id:
            raise ValueError("This project is no longer open.")
        Layout(project)
        write_workspace(project, self.workspace)
        self.project = project
        return self.state()

    def action(self, endpoint, data):
        if endpoint == "/api/layout":
            return self.update(asdict(apply(self.project, data)))
        if endpoint == "/api/project":
            return self.update(data)
        if endpoint == "/api/new":
            self.__init__(workspaces=self.workspaces)
        elif endpoint == "/api/open":
            self.__init__(data["path"], self.workspaces)
        elif endpoint == "/api/save":
            path = Path(data["path"]).expanduser() if data.get("path") else self.bundle
            if not path:
                raise ValueError("Choose a .plate file to save.")
            if path.suffix.lower() != ".plate":
                path = path.with_suffix(".plate")
            save_bundle(self.project, self.workspace, path, data.get("cache", False))
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
        if path == "/api/project":
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
        except (ValueError, TypeError, KeyError, OSError, BadZipFile) as error:
            self.json({"error": str(error)}, 400)

    def log_message(self, format, *args):
        if args and str(args[-2]).startswith(("4", "5")):
            logging.getLogger("plate").info(format, *args)


def make_server(bundle=None, workspaces=WORKSPACES):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.session = Session(bundle, workspaces)
    return server
