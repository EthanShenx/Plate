from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image
import pymupdf

from plate.server import Session
from plate.style import PT_PER_MM


class NativePanels(unittest.TestCase):
    def test_render_import_and_compose(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            session = Session(workspaces=root)
            for type in ("text", "legend", "image", "vector"):
                session.action("/api/layout", {"kind": "add", "type": type, "name": type, "edge": "right"})
            state = session.state()
            project = state["project"]
            project["palettes"]["colors"] = {"Control": "#555555"}
            for panel, label in zip(project["panels"], ["a", "b", "c", "d"], strict=True):
                panel["label"] = label
            project["panels"][0]["settings"]["text"] = "Native text"
            project["panels"][2]["settings"].update(crop=[.25, .25, .5, .5], fit="cover")
            session.update(project)

            path = root / "image.png"
            Image.new("RGB", (81, 97), "red").save(path)
            session.action("/api/asset", {"path": str(path), "panel": project["panels"][2]["id"]})
            path = root / "vector.pdf"
            with pymupdf.open() as source:
                source.new_page().insert_text((10, 30), "Vector text", fontsize=12)
                source.save(path)
            session.action("/api/asset", {"path": str(path), "panel": project["panels"][3]["id"]})

            result = session.export({"path": str(root / "export.pdf"), "format": "pdf"})
            with pymupdf.open(result["path"]) as exported:
                page = exported[0]
                self.assertAlmostEqual(page.rect.width / PT_PER_MM, 183, delta=.01)
                self.assertEqual(len(page.get_xobjects()), 4)
                self.assertTrue(all(item[2] == 0 for item in page.get_xobjects()))
                text = page.get_text().replace("\xa0", " ").splitlines()
                for expected in ("a", "b", "c", "d", "Native text", "Control", "Vector text"):
                    self.assertIn(expected, text)
                self.assertEqual([(item["width"], item["height"]) for item in page.get_image_info()],
                                 [(81, 97)])
