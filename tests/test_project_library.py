from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plate.bundle import open_bundle
from plate.library import FigureLibrary
from plate.server import PlateServer, Session, project_library


class ProjectLibrary(unittest.TestCase):
    def test_projects_keep_multiple_figures_and_restore_open_tabs(self):
        with TemporaryDirectory() as folder:
            workspaces = Path(folder)
            server = object.__new__(PlateServer)
            server.session = Session(workspaces=workspaces)
            server.library = FigureLibrary(workspaces)

            first = server.act("/api/new", {})
            first_id = first["workspace_id"]
            project = first["library"]["projects"][0]["id"]
            server.act("/api/rename-project", {"name": "Paper revisions"})
            server.act("/api/layout", {"kind": "add", "type": "text", "name": "First panel"})
            second = server.act("/api/new-figure", {"project": project})
            second_id = second["workspace_id"]
            self.assertEqual(second["project"]["name"], "Figure 2")
            self.assertEqual(second["library"]["tabs"], [first_id, second_id])
            self.assertEqual(len(second["library"]["projects"]), 1)

            closed = server.act("/api/close-tab", {"workspace": second_id})
            self.assertEqual(closed["workspace_id"], first_id)
            self.assertEqual(len(closed["project"]["panels"]), 1)
            self.assertEqual(len(closed["library"]["projects"][0]["figures"]), 2)
            server.act("/api/resume", {"workspace": second_id})

            other = server.act("/api/new", {})
            other_id = other["workspace_id"]
            server.act("/api/move-figure", {"project": project})
            stored = FigureLibrary(workspaces)
            self.assertEqual(stored.active, other_id)
            self.assertEqual(stored.tabs, [first_id, second_id, other_id])
            self.assertEqual(stored.projects[project]["name"], "Paper revisions")
            self.assertEqual(stored.projects[project]["figures"], [first_id, second_id, other_id])
            resumed = Session(workspaces=workspaces, workspace=workspaces / first_id)
            self.assertEqual(resumed.project.panels[0].name, "First panel")

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
            local_data = workspaces / "data"
            local_data.mkdir()
            session.action("/api/local-data-folder", {"path": str(local_data)})
            self.assertEqual(project_library(workspaces)[0]["panels"], 1)

            reopened = Session(workspaces=workspaces)
            state = reopened.action("/api/resume", {"workspace": workspace})
            self.assertEqual(state["project"]["name"], "Local figure")
            self.assertEqual(state["project"]["panels"][0]["name"], "Plot")
            self.assertEqual(state["data_root_override"], str(local_data.resolve()))
            self.assertEqual(state["project"]["data_root"], "")
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
