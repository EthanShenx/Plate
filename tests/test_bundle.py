from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import pymupdf

from plate.bundle import open_bundle, save_bundle
from plate.interpreters import probe
from plate.model import Panel, Project, presets
from plate.server import Session


class Bundles(unittest.TestCase):
    def test_round_trip(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            panel = Panel(script="print('hello')\n")
            project = Project(panels=[panel], layout={"panel": panel.id})
            path = root / "sample.plate"
            save_bundle(project, root / "working", path)
            reopened, workspace = open_bundle(path, root / "opened")
            self.assertEqual(project, reopened)
            self.assertEqual((workspace / "panels" / panel.id / "script.py").read_text(), panel.script)

    def test_migration(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            path = root / "legacy.plate"
            with ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", '{"schema_version":0,"id":"legacy","title":"Old figure"}')
            project, _ = open_bundle(path, root / "opened")
            self.assertEqual(project.name, "Old figure")
            self.assertEqual(project.size.width_mm, 183)

    def test_invalid_member_cannot_escape_workspace(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            path = root / "bad.plate"
            with ZipFile(path, "w") as archive:
                archive.writestr("../../escape", "bad")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                open_bundle(path, root / "opened")
            self.assertFalse((root / "escape").exists())

    def test_presets(self):
        journals = {preset["id"]: preset for preset in presets()}
        self.assertEqual(journals["nature"]["widths"], [89, 120, 136, 183])
        self.assertIsNone(journals["science"]["widths"])

    def test_shareable_copy_can_be_rendered_and_resaved_away_from_the_source(self):
        if probe(sys.executable, "script-py")["missing"]:
            self.skipTest("Matplotlib is required")
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            data = root / "sender-data"
            (data / "table").mkdir(parents=True)
            (data / "table/value.txt").write_text("Shared data")
            (data / "helper.py").write_text(
                'from pathlib import Path\nvalue = Path("table/value.txt").read_text()\n')
            (data / "unlisted.txt").write_text("Private notes")
            sender = Session(workspaces=root / "sender")
            state = sender.action("/api/layout", {"kind": "add", "type": "script-py", "name": "Plot"})
            project = state["project"]
            panel = project["panels"][0]
            panel.update(interpreter=sys.executable, input_files=["table/value.txt", "helper.py"])
            panel_id = panel["id"]
            sender.update(project)
            sender.action("/api/local-data-folder", {"path": str(data)})
            source = ('import matplotlib.pyplot as plt\nfrom helper import value\n'
                      'fig = plt.figure()\nfig.text(.2, .5, value)\n')
            sender.action("/api/script", {"panel": panel_id, "base": "", "script": source})
            sender.refresh_pending()
            sender.save(root / "Original.plate")

            shared = root / "transfer/Shared.plate"
            sender.action("/api/share", {"path": str(shared), "cache": True})
            self.assertEqual(sender.bundle, (root / "Original.plate").resolve())
            self.assertEqual(sender.project.panels[0].interpreter, sys.executable)
            with ZipFile(shared) as archive:
                self.assertEqual({name for name in archive.namelist() if name.startswith("data/")},
                                 {"data/table/value.txt", "data/helper.py"})
                self.assertIn("cache/index.json", archive.namelist())

            data.rename(root / "unavailable-to-recipient")
            recipient = Session(shared, root / "recipient")
            self.assertNotEqual(recipient.project.id, sender.project.id)
            self.assertFalse(recipient.project.panels[0].interpreter)
            self.assertEqual(recipient.project.panels[0].script, source)
            self.assertEqual(recipient.data_folder(), recipient.workspace.resolve() / "data")
            (recipient.data_folder() / "table/value.txt").write_text("Recipient edited this")
            recipient.refresh_pending()
            revised = root / "revision/Revised.plate"
            recipient.save(revised)

            reopened = Session(revised, root / "reopened")
            reopened.refresh_pending()
            pdf_path = reopened.export({"path": str(root / "revised.pdf"), "format": "pdf"})["path"]
            with pymupdf.open(pdf_path) as pdf:
                self.assertIn("Recipient edited this", pdf[0].get_text())

    def test_sharing_rejects_files_outside_the_data_folder(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            data = root / "data"
            data.mkdir()
            (root / "external.txt").write_text("External data")
            (data / "symlink.txt").symlink_to(root / "external.txt")
            session = Session(workspaces=root / "workspaces")
            state = session.action("/api/layout", {"kind": "add", "type": "script-py", "name": "Plot"})
            session.action("/api/local-data-folder", {"path": str(data)})
            for invalid in ("../external.txt", "symlink.txt", "missing.txt"):
                with self.subTest(path=invalid):
                    state["project"]["panels"][0]["input_files"] = [invalid]
                    session.update(state["project"])
                    with self.assertRaisesRegex(ValueError, invalid):
                        session.action("/api/share", {"path": str(root / "share.plate")})
                    self.assertFalse((root / "share.plate").exists())
