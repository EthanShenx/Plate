from importlib.util import find_spec
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from plate.interpreters import probe
from plate.model import ROOT
from plate.server import Session
from plate.style import PT_PER_MM


class Sample(unittest.TestCase):
    def test_sample_bundle_and_export(self):
        r = shutil.which("Rscript")
        if not r or probe(r, "script-r")["missing"]:
            self.skipTest("Sample render requires Rscript and R plotting packages.")
        if probe(sys.executable, "script-py")["missing"]:
            self.skipTest("Sample render requires matplotlib.")
        if not find_spec("seaborn"):
            self.skipTest("Sample render requires seaborn.")
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            session = Session(ROOT / "examples/nature-double.plate", root / "workspaces")
            self.assertEqual(session.project.size.width_mm, 183)
            session.refresh([panel.id for panel in session.project.panels])
            state = session.state()
            self.assertTrue(all(item["state"] == "fresh" for item in state["renders"].values()),
                            {key: item.get("stderr") for key, item in state["renders"].items()})
            self.assertEqual(state["checks"], [])
            output = session.export({"format": "pdf", "path": str(root / "figure.pdf")})
            with pymupdf.open(output["path"]) as document:
                page = document[0]
                self.assertAlmostEqual(page.rect.width / PT_PER_MM, 183, delta=.01)
                self.assertEqual(sum(item[2] == 0 for item in page.get_xobjects()), 6)
                lines = page.get_text().replace("\xa0", " ").splitlines()
                for line in ("a", "b", "c", "d", "e", "f", "Control", "Treatment", "Cortex"):
                    self.assertIn(line, lines)
                self.assertEqual([(item["width"], item["height"]) for item in page.get_image_info()],
                                 [(900, 670)])
