from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from plate.bundle import open_bundle, save_bundle
from plate.model import Panel, Project, presets


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
