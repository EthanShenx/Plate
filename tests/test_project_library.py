from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plate.bundle import open_bundle
from plate.server import Session, project_library


class ProjectLibrary(unittest.TestCase):
    def test_local_draft_is_available_in_a_new_session(self):
        with TemporaryDirectory() as folder:
            workspaces = Path(folder)
            session = Session(workspaces=workspaces)
            self.assertEqual(project_library(workspaces), [])

            state = session.action("/api/new", {})
            workspace = state["workspace_id"]
            state["project"]["name"] = "Local figure"
            session.action("/api/project", state["project"])
            session.action("/api/layout", {"kind": "add", "type": "script-py", "name": "Plot"})
            self.assertEqual(project_library(workspaces)[0]["panels"], 1)

            reopened = Session(workspaces=workspaces)
            state = reopened.action("/api/resume", {"workspace": workspace})
            self.assertEqual(state["project"]["name"], "Local figure")
            self.assertEqual(state["project"]["panels"][0]["name"], "Plot")
            self.assertFalse(state["bundle"])
            with self.assertRaisesRegex(ValueError, "Invalid workspace"):
                reopened.action("/api/resume", {"workspace": "../other"})
            self.assertEqual(reopened.state()["workspace_id"], workspace)

    def test_resuming_local_edits_keeps_the_saved_file_separate(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            workspaces = root / "workspaces"
            bundle = root / "figure.plate"
            session = Session(workspaces=workspaces)
            original = session.action("/api/save", {"path": str(bundle)})
            self.assertFalse(original["bundle_dirty"])

            original["project"]["name"] = "Edited locally"
            session.action("/api/project", original["project"])
            saved, _ = open_bundle(bundle, root / "readback")
            self.assertEqual(saved.name, "Untitled figure")

            reopened = Session(workspaces=workspaces)
            state = reopened.action("/api/resume", {"workspace": original["workspace_id"]})
            self.assertEqual(state["bundle"], str(bundle.resolve()))
            self.assertEqual(state["project"]["name"], "Edited locally")
            self.assertTrue(state["bundle_dirty"])
            self.assertFalse(reopened.action("/api/save", {})["bundle_dirty"])
