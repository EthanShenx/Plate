import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import BadZipFile

from plate.library import FigureLibrary
from plate.project_bundle import save_project_bundle
from plate.server import PlateServer, Session


class ProjectBundles(unittest.TestCase):
    def build(self, manifest, output, status=0):
        result = subprocess.run([sys.executable, "-m", "plate", "project", "build", str(manifest),
                                 "--output", str(output)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_build_import_and_reopen_preserving_order_and_edits(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "specs"
            source.mkdir()
            (source / "counts.csv").write_text("group,count\nA,3\n")
            figures = {"b.json": "Results", "a.json": "Methods"}
            for filename, name in figures.items():
                (source / filename).write_text(json.dumps({"name": name, "panels": [
                    {"id": "note", "type": "text", "rect": {"x": 4, "y": 4, "w": 50, "h": 25},
                     "settings": {"text": name}},
                    {"id": "plot", "type": "script-py", "rect": {"x": 4, "y": 36, "w": 50, "h": 25},
                     "input_files": ["counts.csv"]},
                ]}))
            manifest = source / "study.json"
            manifest.write_text(json.dumps({"name": "Study", "figures": list(figures)}))
            output = root / "build" / "study.plateproject"
            result = self.build(manifest, output)
            self.assertEqual([figure["name"] for figure in result["figures"]], list(figures.values()))

            previous_archive = output.read_bytes()
            (source / "a.json").unlink()
            self.assertEqual(self.build(manifest, output, 1)["figure"], "a.json")
            self.assertEqual(output.read_bytes(), previous_archive)
            (source / "counts.csv").unlink()

            workspaces = root / "workspaces"
            server = object.__new__(PlateServer)
            server.session = Session(workspaces=workspaces)
            server.library = FigureLibrary(workspaces)
            original = server.act("/api/new", {})["workspace_id"]
            imported = server.act("/api/open", {"path": str(output)})
            group = next(project for project in imported["library"]["projects"] if project["name"] == "Study")
            first, second = [item["id"] for item in group["figures"]]
            self.assertEqual(imported["library"]["tabs"], [original, first, second])
            self.assertEqual(imported["workspace_id"], first)
            self.assertEqual([item["name"] for item in group["figures"]], ["Results", "Methods"])
            for figure in (first, second):
                self.assertEqual((workspaces / figure / "data/counts.csv").read_text(), "group,count\nA,3\n")

            # Aborting a second import after its first figure leaves the library intact.
            valid = root / "valid.plate"
            server.session.share(valid, cache=True)
            invalid = root / "invalid.plate"
            invalid.write_text("not a figure bundle")
            broken = root / "broken.plateproject"
            save_project_bundle(broken, "Unfinished study", [valid, invalid])
            folders = set(workspaces.iterdir())
            with self.assertRaises(BadZipFile):
                server.act("/api/open", {"path": str(broken)})
            self.assertEqual(set(workspaces.iterdir()), folders)
            self.assertEqual(server.workbench_state()["library"], imported["library"])

            edit = imported["project"]
            edit["name"] = "Edited results"
            server.act("/api/project", edit)
            reopened = server.act("/api/open", {"path": str(output)})
            self.assertEqual(reopened["workspace_id"], first)
            self.assertEqual(reopened["project"]["name"], "Edited results")
            self.assertEqual(reopened["library"]["tabs"], [original, first, second])
            self.assertEqual(FigureLibrary(workspaces).projects[group["id"]]["figures"], [first, second])
