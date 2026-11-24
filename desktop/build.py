"""Build the local macOS application from the same assets as the web app."""

from argparse import ArgumentParser
from importlib.metadata import distribution
from io import BytesIO
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from PIL import Image
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
APP_ID = "org.platesci.Plate"
MINIMUM_MACOS = "14.0"


def stable_python():
    path = Path(sys._base_executable).resolve()
    # Homebrew's opt symlink survives patch-level upgrades of the same formula.
    for parent in path.parents:
        if parent.name == "Cellar":
            formula, _, *relative = path.relative_to(parent).parts
            opt = parent.parent.joinpath("opt", formula, *relative)
            if opt.is_file():
                return opt
    return path


def bundle_libraries(destination):
    destination.mkdir()
    entries = set()
    for name in ("PyMuPDF", "Pillow", "fonttools"):
        package = distribution(name)
        for member in package.files or ():
            if ".." not in member.parts:
                entries.add(package.locate_file(member.parts[0]))
    subprocess.run(["/bin/cp", "-cR", *map(str, sorted(entries)), str(destination)], check=True)
    for cache in destination.rglob("__pycache__"):
        shutil.rmtree(cache)


def create_icon(resources):
    with pymupdf.open(ROOT / "plate/web/plate-mark.svg") as document:
        page = document[0]
        pixels = page.get_pixmap(matrix=pymupdf.Matrix(1024 / page.rect.width, 1024 / page.rect.height),
                                 alpha=True)
        with Image.open(BytesIO(pixels.tobytes("png"))) as image:
            image.save(resources / "Plate.icns")


def verify_delivery(bundle):
    # Desktop sync can attach Finder information to the outer folder on move.
    names = subprocess.check_output(["/usr/bin/xattr", str(bundle)], text=True).splitlines()
    for attribute in ("com.apple.FinderInfo", "com.apple.ResourceFork"):
        if attribute in names:
            subprocess.run(["/usr/bin/xattr", "-d", attribute, str(bundle)], check=True)
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(bundle)], check=True)


def build(destination, smoke):
    if sys.platform != "darwin":
        raise SystemExit("Run the macOS build on a Mac.")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    identifier = APP_ID + (".Smoke" if smoke else "")
    if destination.exists():
        with (destination / "Contents/Info.plist").open("rb") as stream:
            if plistlib.load(stream).get("CFBundleIdentifier") != identifier:
                raise SystemExit(f"The existing app has a different identifier: {destination}")
    # Sign in the system temp directory so Finder and Desktop sync do not
    # add metadata to the staging bundle while codesign is sealing it.
    with TemporaryDirectory(prefix="plate-build-") as scratch:
        work = Path(scratch)
        bundle = work / "Plate.app"
        contents = bundle / "Contents"
        resources = contents / "Resources"
        executable = contents / "MacOS/Plate"
        resources.mkdir(parents=True)
        executable.parent.mkdir()

        documents = [("org.platesci.figure", "Plate Figure", "plate"),
                     ("org.platesci.project", "Plate Project", "plateproject")]
        plist = {
            "CFBundleName": "Plate", "CFBundleDisplayName": "Plate",
            "CFBundleIdentifier": identifier, "CFBundlePackageType": "APPL",
            "CFBundleExecutable": "Plate", "CFBundleIconFile": "Plate.icns",
            "CFBundleShortVersionString": "0.1.0", "CFBundleVersion": "1",
            "LSMinimumSystemVersion": MINIMUM_MACOS, "NSHighResolutionCapable": True,
            "NSSupportsAutomaticGraphicsSwitching": True,
            "PlatePython": str(stable_python()), "PlatePlotPython": sys.executable,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": label, "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner", "LSItemContentTypes": [identifier],
            } for identifier, label, _ in documents],
            "UTExportedTypeDeclarations": [{
                "UTTypeIdentifier": identifier, "UTTypeDescription": label,
                "UTTypeConformsTo": ["public.data"], "UTTypeTagSpecification": {
                    "public.filename-extension": [suffix],
                },
            } for identifier, label, suffix in documents],
        }
        with (contents / "Info.plist").open("wb") as stream:
            plistlib.dump(plist, stream)
        for folder in ("plate", "helpers", "presets"):
            shutil.copytree(ROOT / folder, resources / folder,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".plate-build"))
        shutil.copy2(ROOT / "desktop/backend.py", resources)
        bundle_libraries(resources / "site-packages")
        if not (resources / "plate/web/vendor/editor.js").is_file():
            raise SystemExit("Run make editor before packaging Plate.")
        create_icon(resources)
        sources = [ROOT / "desktop" / name for name in ("Backend.swift", "PlateApp.swift")]
        command = ["/usr/bin/swiftc", "-swift-version", "5", "-O",
                   "-module-cache-path", str(work / "modules"),
                   "-target", f"{platform.machine()}-apple-macosx{MINIMUM_MACOS}"]
        if smoke:
            command += ["-D", "PLATE_SMOKE"]
            sources.append(ROOT / "desktop/Smoke.swift")
        subprocess.run([*command, *map(str, sources), "-o", str(executable)], check=True)
        # The staging copy can inherit Finder metadata that codesign rejects.
        subprocess.run(["/usr/bin/xattr", "-cr", str(bundle)], check=True)
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(bundle)], check=True)
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(bundle)], check=True)

        with TemporaryDirectory(prefix=".plate-delivery-", dir=destination.parent) as delivery:
            previous = Path(delivery) / "Previous.app"
            if destination.exists():
                destination.rename(previous)
            try:
                shutil.move(bundle, destination)
                verify_delivery(destination)
            except (OSError, subprocess.CalledProcessError):
                if destination.exists():
                    shutil.rmtree(destination)
                if previous.exists():
                    previous.rename(destination)
                raise
    print(destination)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/Plate.app")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    build(args.output, args.smoke)
