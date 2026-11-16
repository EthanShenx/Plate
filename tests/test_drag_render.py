from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from plate.bundle import save_bundle
from plate.grid import apply_grid
from plate.layout import Layout, leaf, split
from plate.model import Panel, Project
from plate.server import Session
from plate.style import context_for


class GridLayout(unittest.TestCase):
    def test_old_bundle_keeps_geometry_and_position_changes_do_not_render(self):
        a, b = [Panel(id=id, type="text") for id in ("a", "b")]
        project = Project(panels=[a, b], layout=split("x", [leaf(a.id), leaf(b.id)]))
        original = Layout(project).rects
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "legacy.plate"
            save_bundle(project, root / "working", bundle)
            session = Session(bundle, root / "open")
            self.assertEqual(session.state()["geometry"]["rects"], original)
            session.refresh(["a", "b"])
            key = session.renders["a"]["key"]

            moved = session.update_layout({"kind": "place", "panel": "a", "auto_render": True,
                                           "rect": {**original["a"], "x": 18, "y": 0}})
            self.assertEqual(moved["panels_to_refresh"], [])
            self.assertEqual(moved["renders"]["a"]["key"], key)
            self.assertEqual(moved["geometry"]["rects"]["b"], original["b"])

            rect = {"x": 18, "y": 0, "w": 70, "h": 75}
            resized = session.update_layout({"kind": "place", "panel": "a", "rect": rect, "auto_render": True})
            self.assertEqual(resized["panels_to_refresh"], ["a"])
            self.assertEqual(resized["geometry"]["rects"]["b"], original["b"])
            session.refresh(["a"])
            self.assertNotEqual(session.renders["a"]["key"], key)

            output = root / "grid.plate"
            session.action("/api/save", {"path": str(output), "cache": True})
            reopened = Session(output, root / "open")
            self.assertEqual(reopened.state()["geometry"]["rects"], {"a": rect, "b": original["b"]})

    def test_independent_rectangles_allow_gaps_overlap_and_layers(self):
        panels = [Panel(id=id, type="text", label=id) for id in "abcdef"]
        rects = {
            "a": dict(x=4, y=4, w=42, h=42), "b": dict(x=52, y=4, w=42, h=42),
            "c": dict(x=104, y=4, w=65, h=69), "d": dict(x=4, y=52, w=90, h=52),
            "e": dict(x=8, y=54, w=22, h=20), "f": dict(x=104, y=82, w=65, h=22),
        }
        project = Project(panels=panels, layout={"mode": "grid", "rects": rects})
        stacked = apply_grid(project, {"kind": "stack", "panel": "e", "direction": "back"})
        self.assertEqual(Layout(stacked).rects, rects)
        self.assertEqual(stacked.panels[0].id, "e")
        deleted = apply_grid(stacked, {"kind": "delete", "panel": "b"})
        self.assertEqual(Layout(deleted).rects, {id: r for id, r in rects.items() if id != "b"})
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "grid.plate"
            save_bundle(deleted, root / "working", bundle)
            session = Session(bundle, root / "open")
            result = session.export({"path": str(root / "figure.pdf"), "format": "pdf"})
            with pymupdf.open(result["path"]) as pdf:
                self.assertEqual(pdf[0].get_text().split(), ["e", "a", "c", "d", "f"])

    def test_bounds_and_size_locks(self):
        panel = Panel(id="a", locks={"w": 40})
        rect = dict(x=6, y=8, w=40, h=30)
        project = Project(panels=[panel], layout={"mode": "grid", "rects": {"a": rect}})
        for invalid in ({**rect, "w": 45}, {**rect, "x": 180}, {**rect, "h": 1}):
            with self.assertRaises(ValueError):
                apply_grid(project, {"kind": "place", "panel": "a", "rect": invalid})
        self.assertEqual(Layout(project).rects["a"], rect)

    def test_referenced_panel_motion_invalidates_only_the_dependent_plot(self):
        target = Panel(id="target", script="print('target')")
        overlay = Panel(id="overlay", script="print('overlay')",
                        settings={"geometry_refs": [target.id]})
        boxes = {"target": dict(x=30, y=17, w=40, h=45), "overlay": dict(x=20, y=10, w=72, h=63)}
        project = Project(panels=[target, overlay], layout={"mode": "grid", "rects": boxes})
        with TemporaryDirectory() as directory:
            session = Session(workspaces=Path(directory))
            session.store_project(project)
            for panel in project.panels:
                session.store_render(panel, boxes[panel.id], {"state": "fresh"})
            original = context_for(project, overlay, boxes["overlay"])["panel_boxes_mm"]["target"]
            self.assertEqual(original, dict(x=10, y=7, w=40, h=45))

            moved = session.update_layout({"kind": "place", "panel": "target", "auto_render": True,
                                           "rect": {**boxes["target"], "x": 32}})
            self.assertEqual(moved["panels_to_refresh"], ["overlay"])
            self.assertEqual(moved["renders"]["target"]["state"], "fresh")
            referenced = context_for(session.project, overlay, boxes["overlay"])["panel_boxes_mm"]["target"]
            self.assertEqual(referenced, {**original, "x": 12})

            removed = session.update_layout({"kind": "delete", "panel": "target", "auto_render": True})
            self.assertEqual(removed["panels_to_refresh"], ["overlay"])
            self.assertEqual(context_for(session.project, overlay, boxes["overlay"])["panel_boxes_mm"], {})
