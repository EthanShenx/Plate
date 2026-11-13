from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plate.bundle import script_path
from plate.server import Session


class ScriptFiles(unittest.TestCase):
    def test_external_edits_and_conflict(self):
        with TemporaryDirectory() as scratch:
            session = Session(workspaces=Path(scratch))
            state = session.action("/api/layout", {"kind": "add", "type": "script-py", "name": "Panel"})
            panel = session.project.panels[0]
            path = script_path(session.workspace, panel)
            path.write_text("external = True")
            state["project"]["name"] = "Renamed"
            updated = session.action("/api/project", state["project"])
            self.assertEqual(updated["project"]["panels"][0]["script"], "external = True")
            result = session.action("/api/script", {"panel": panel.id, "base": "", "script": "editor"})
            self.assertTrue(result["conflict"])
            self.assertEqual(result["script"], "external = True")
            result = session.action("/api/script", {
                "panel": panel.id, "base": "external = True", "script": "editor",
            })
            self.assertEqual(result["project"]["panels"][0]["script"], "editor")
            self.assertEqual(path.read_text(), "editor")
