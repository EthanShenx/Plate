"""Run the desktop smoke test in a temporary workspace using real WKWebView."""

from argparse import ArgumentParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pymupdf

from build import ROOT, build


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--soak-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.soak_seconds < 0:
        parser.error("Soak duration must be nonnegative.")
    with TemporaryDirectory(prefix="plate-desktop-test-") as scratch:
        directory = Path(scratch)
        bundle = directory / "Smoke.app"
        fixture = directory / "Fixture.plate"
        shutil.copyfile(ROOT / "examples/nature-double.plate", fixture)
        for name in ("Results", "Methods"):
            (directory / f"{name}.json").write_text(json.dumps({"name": name}))
        manifest = directory / "Study.json"
        manifest.write_text(json.dumps({"name": "Study", "figures": ["Results.json", "Methods.json"]}))
        subprocess.run([sys.executable, "-m", "plate", "project", "build", str(manifest),
                        "--output", str(manifest.with_suffix(".plateproject"))],
                       cwd=ROOT, check=True, capture_output=True)
        build(bundle, smoke=True)
        executable = bundle / "Contents/MacOS/Plate"
        environment = {**os.environ, "PLATE_SMOKE_SUPPORT": str(directory / "Support"),
                       "PLATE_SMOKE_FIXTURE": str(fixture), "PLATE_SMOKE_SOAK": str(args.soak_seconds)}
        subprocess.run([executable], check=True, timeout=55, env=environment)
        subprocess.run([executable], check=True, timeout=210 + args.soak_seconds,
                       env={**environment, "PLATE_SMOKE_RESTORE": "1"})
        with ZipFile(directory / "Saved.plate") as saved:
            assert "provenance.json" in saved.namelist()
        with ZipFile(directory / "Shared.plate") as shared:
            assert json.loads(shared.read("manifest.json"))["embedded_data"] is True
        with pymupdf.open(directory / "Desktop.pdf") as pdf:
            assert pdf.page_count == 1
            assert "Cortex" in pdf[0].get_text()
            assert sum(form[2] == 0 for form in pdf[0].get_xobjects()) == 6
        print("Saved bundle and editable PDF passed inspection.")


if __name__ == "__main__":
    sys.exit(main())
