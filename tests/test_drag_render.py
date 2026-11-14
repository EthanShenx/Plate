from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from plate.bundle import save_bundle
from plate.layout import leaf, split
from plate.model import Panel, Project
from plate.server import Session


class DragRender(unittest.TestCase):
    def test_layout_changes_target_only_affected_panels(self):
        a, b, c = [Panel(id=id, type="text") for id in ("a", "b", "c")]
        empty = Panel(id="empty", type="script-py")
        project = Project(
            panels=[a, b, c, empty],
            layout=split("y", [
                split("x", [leaf(a.id), leaf(b.id), leaf(empty.id)]), leaf(c.id),
            ]),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "drag.plate"
            save_bundle(project, root / "working", bundle)
            session = Session(bundle, root / "open")
            session.refresh([a.id, b.id])
            old_key = session.renders[a.id]["key"]
            drag = {"panel": a.id, "corner": "top-right", "dx": 5, "dy": 0}

            session.action("/api/preview-corner", drag)
            self.assertEqual(session.state()["renders"][a.id]["state"], "fresh")
            updated = session.action("/api/layout", {**drag, "kind": "resize-corner", "auto_render": True})
            self.assertEqual(updated["panels_to_refresh"], [a.id, b.id])
            self.assertEqual(updated["renders"][c.id]["state"], "stale")
            self.assertEqual(updated["renders"][a.id]["key"], old_key)

            refreshed = session.action("/api/refresh", {"panels": updated["panels_to_refresh"]})
            self.assertEqual(refreshed["renders"][a.id]["state"], "fresh")
            self.assertNotEqual(refreshed["renders"][a.id]["key"], old_key)
            self.assertEqual(refreshed["renders"][c.id]["state"], "stale")
            unchanged = session.action("/api/layout", {
                **drag, "kind": "resize-corner", "dx": 0, "auto_render": True,
            })
            self.assertEqual(unchanged["panels_to_refresh"], [])
