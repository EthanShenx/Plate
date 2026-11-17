import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from plate.interpreters import probe


class HeadlessAuthoring(unittest.TestCase):
    def run_plate(self, status, *args):
        process = subprocess.run([sys.executable, "-m", "plate", *map(str, args)],
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(process.returncode, status, process.stdout + process.stderr)
        return json.loads(process.stdout)

    def test_build_revise_and_export_with_diagnostics(self):
        if probe(sys.executable, "script-py")["missing"]:
            self.skipTest("Matplotlib is required")
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            spec = root / "figure.json"
            bundle = root / "build" / "figure.plate"
            revised = root / "revision" / "figure.plate"
            (root / "value.txt").write_text("First rendering")
            (root / "plot.py").write_text(
                'import matplotlib.pyplot as plt\nfrom pathlib import Path\n'
                'fig = plt.figure()\nfig.text(.22, .5, Path("value.txt").read_text())\n'
            )
            spec.write_text(json.dumps({
                "size": {"width_mm": 100, "height_mm": 60},
                "panels": [
                    {"id": "plot", "label": "a", "script_file": "plot.py", "input_files": ["value.txt"],
                     "rect": {"x": 2, "y": 2, "w": 45, "h": 56}},
                    {"id": "note", "label": "b", "type": "text", "settings": {"text": "Synthetic data"},
                     "rect": {"x": 51, "y": 2, "w": 45, "h": 56}},
                ],
                "groups": [{"id": "pair", "name": "Pair", "panels": ["plot", "note"]}],
            }))
            built = self.run_plate(0, "build", spec, "--output", bundle)
            self.assertTrue(all(panel["state"] == "fresh" for panel in built["panels"]))
            self.assertEqual(self.run_plate(0, "inspect", bundle)["groups"], built["groups"])

            patch = root / "revision.json"
            patch.write_text(json.dumps({"panels": [{"id": "plot", "rect": {"w": 48}}]}))
            edited = self.run_plate(0, "apply", bundle, patch, "--output", revised)
            self.assertEqual(edited["panels"][0]["rect_mm"]["w"], 48)
            self.assertEqual(edited["panels"][1], built["panels"][1])
            self.assertEqual(self.run_plate(0, "inspect", bundle)["panels"][0]["rect_mm"]["w"], 45)

            export = root / "figure.pdf"
            self.assertEqual(self.run_plate(0, "export", revised, "--output", export)["export"], str(export.resolve()))
            with pymupdf.open(export) as pdf:
                self.assertIn("First rendering", pdf[0].get_text())
                self.assertIn("Synthetic data", pdf[0].get_text())

            (root / "value.txt").write_text("Updated rendering")
            inspected = self.run_plate(0, "inspect", revised, "--compare-environment")
            self.assertEqual(inspected["panels"][0]["state"], "stale")
            self.assertIn("matplotlib", inspected["provenance"]["plot"]["packages"])
            self.assertEqual(inspected["environment"]["panels"][0]["differences"], [])
            self.run_plate(0, "export", revised, "--output", export)
            with pymupdf.open(export) as pdf:
                self.assertIn("Updated rendering", pdf[0].get_text())

            relocated = root / "relocated"
            relocated.mkdir()
            (relocated / "value.txt").write_text("Relocated rendering")
            self.run_plate(0, "export", revised, "--data-root", relocated, "--force", "--output", export)
            with pymupdf.open(export) as pdf:
                self.assertIn("Relocated rendering", pdf[0].get_text())

            (root / "value.txt").unlink()
            self.assertEqual(self.run_plate(1, "export", revised, "--output", export)
                             ["export_issues"][0]["panel"], "plot")
            with pymupdf.open(export) as pdf:
                self.assertIn("Relocated rendering", pdf[0].get_text())
            draft = self.run_plate(0, "export", revised, "--draft", "--output", export)
            self.assertTrue(draft["draft"])
            self.assertTrue(draft["export_issues"][0]["uses_previous"])
            with pymupdf.open(export) as pdf:
                self.assertIn("First rendering", pdf[0].get_text())
            (root / "value.txt").write_text("Updated rendering")

            valid_bundle = revised.read_bytes()
            patch.write_text(json.dumps({"panels": [{"id": "plot", "script": "raise ValueError('Broken plot')"}]}))
            failure = self.run_plate(1, "apply", revised, patch, "--output", revised)
            self.assertEqual(failure["panels"][0]["state"], "error")
            self.assertIn("Broken plot", failure["panels"][0]["stderr"])
            self.assertEqual(revised.read_bytes(), valid_bundle)
