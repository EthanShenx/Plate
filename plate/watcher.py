"""Poll real script files and reconcile writes under the session lock."""

from threading import Event, Thread

from .bundle import atomic_write, script_path
from .model import SCRIPT_EXTENSIONS


def read_script(workspace, panel):
    try:
        return script_path(workspace, panel).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeError):
        return panel.script


def sync_scripts(project, workspace):
    changed = []
    for panel in project.panels:
        if panel.type not in SCRIPT_EXTENSIONS:
            continue
        source = read_script(workspace, panel)
        if source != panel.script:
            panel.script = source
            changed.append(panel.id)
    return changed


def save_script(project, workspace, panel_id, source, base):
    panel = next(panel for panel in project.panels if panel.id == panel_id)
    current = read_script(workspace, panel)
    if base != current:
        return {"conflict": True, "script": current}
    path = script_path(workspace, panel)
    atomic_write(path, lambda tmp: tmp.write_text(source, encoding="utf-8"))
    panel.script = source
    return {"conflict": False}


class Watcher(Thread):
    def __init__(self, session, interval=.4):
        super().__init__(daemon=True, name="Plate script watcher")
        self.session = session
        self.interval = interval
        self.finished = Event()

    def run(self):
        while not self.finished.wait(self.interval):
            try:
                with self.session.lock:
                    sync_scripts(self.session.project, self.session.workspace)
            except OSError:
                continue

    def close(self):
        self.finished.set()
