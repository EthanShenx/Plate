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
        build(bundle, smoke=True)
        subprocess.run([bundle / "Contents/MacOS/Plate"], check=True, timeout=210 + args.soak_seconds,
                       env={**os.environ, "PLATE_SMOKE_SUPPORT": str(directory / "Support"),
                            "PLATE_SMOKE_FIXTURE": str(fixture), "PLATE_SMOKE_SOAK": str(args.soak_seconds)})
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
