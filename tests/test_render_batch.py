from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Lock
import sys
import unittest
from unittest.mock import patch

from plate.bundle import save_bundle
from plate.interpreters import probe
from plate.layout import leaf, split
from plate.model import Panel, Project
from plate.render import plot_process
from plate.server import Session


class RenderBatch(unittest.TestCase):
    def test_identical_renders_share_work_and_a_failed_script_keeps_other_results(self):
        if probe(sys.executable, "script-py")["missing"]:
            self.skipTest("Python matplotlib unavailable")
        source = "import matplotlib.pyplot as plt\nplt.plot([1, 2], [2, 1])\n"
        panels = [
            Panel(script=source),
            Panel(script=source),
            Panel(script="raise ValueError('deliberate render failure')\n"),
        ]
        project = Project(panels=panels, layout=split("x", [leaf(panel.id) for panel in panels]))
        barrier = Barrier(2, timeout=10)
        lock = Lock()
        calls = []

        def overlap(*args):
            with lock:
                calls.append(args[0])
            barrier.wait()
            return plot_process(*args)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "batch.plate"
            save_bundle(project, root / "source", bundle)
            session = Session(bundle, root / "workspaces")
            with patch("plate.server.os.cpu_count", return_value=2), patch("plate.render.plot_process", overlap):
                session.refresh([panel.id for panel in panels])
            a, b, failed = [session.renders[panel.id] for panel in panels]
            self.assertEqual(len(calls), 2)
            self.assertEqual(a["state"], "fresh")
            self.assertEqual(b["state"], "fresh")
            self.assertEqual(a["key"], b["key"])
            self.assertEqual(failed["state"], "error")
            self.assertIn("deliberate render failure", failed["stderr"])
