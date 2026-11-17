"""Record render environments and compare them with local installations."""

import json
import os
from pathlib import Path
import subprocess

from .bundle import PROVENANCE_FILE
from .fonts import DIRECTORIES, face_key, font_versions
from .interpreters import interpreter, login_path
from .model import SCRIPT_EXTENSIONS


def read_provenance(workspace):
    path = workspace / PROVENANCE_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def render_environment(panel, render):
    metadata = render.get("metadata", {})
    fonts = metadata.get("fonts", {span["font"]: "" for span in metadata.get("text", [])}).copy()
    if label := render.get("label_metadata"):
        fonts.setdefault(label["font"], "")
    if panel.type in SCRIPT_EXTENSIONS:
        if "runtime" not in render:
            return None
        return {**render["runtime"], "interpreter": render["interpreter_stamp"][0], "fonts": fonts}
    return {"fonts": fonts}


def installed_runtime(path, language, directory):
    if language == "script-py":
        command = [path, "-c",
                   "import importlib.metadata as m, importlib.util as u, json, sys\n"
                   "from pathlib import Path\n"
                   "packages = {}\n"
                   "for d in m.distributions():\n"
                   "    if name := d.metadata.get('Name'):\n"
                   "        packages.setdefault(name, d.version)\n"
                   "spec = u.find_spec('matplotlib')\n"
                   "fonts = str(Path(spec.origin).parent / 'mpl-data' / 'fonts') if spec and spec.origin else None\n"
                   "print(json.dumps({'version': sys.version.split()[0], 'packages': packages, 'fonts': fonts}))"]
    else:
        command = [path, "--vanilla", "-e",
                   'cat(as.character(getRversion()), "\\n", sep=""); '
                   'p <- installed.packages(); p <- p[!duplicated(p[, "Package"]), , drop=FALSE]; '
                   'write.table(p[, c("Package", "Version"), drop=FALSE], col.names=FALSE, '
                   'row.names=FALSE, quote=FALSE, sep="\\t")']
    result = subprocess.run(command, cwd=directory if directory.is_dir() else None,
                            env={**os.environ, "PATH": login_path()},
                            capture_output=True, text=True, timeout=15, check=True)
    if language == "script-py":
        return json.loads(result.stdout)
    version, *rows = result.stdout.splitlines()
    return {"version": version, "packages": dict(row.split("\t", 1) for row in rows)}


def compare_environment(project, recorded, directory):
    local_fonts = font_versions(DIRECTORIES)
    # The PDF standard faces may be supplied by a viewer without an installed file.
    for name in ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
                 "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
                 "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
                 "Symbol", "ZapfDingbats"):
        local_fonts.setdefault(face_key(name), "")
    runtimes = {}
    panels = []
    for panel in project.panels:
        baseline = recorded.get(panel.id)
        if not baseline:
            continue
        differences = []
        current = {"fonts": {}}
        fonts = local_fonts
        if panel.type in SCRIPT_EXTENSIONS and "version" in baseline:
            try:
                path = interpreter(project, panel)
                key = path, panel.type
                if key not in runtimes:
                    try:
                        runtime = installed_runtime(path, panel.type, directory)
                        bundled = font_versions((Path(runtime["fonts"]),)) if runtime.get("fonts") else {}
                        runtimes[key] = runtime, {**bundled, **local_fonts}
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        runtimes[key] = str(error)
                local = runtimes[key]
                if isinstance(local, str):
                    raise ValueError(local)
                runtime, fonts = local
                current.update(interpreter=path, version=runtime["version"], packages={})
                if baseline["version"] != runtime["version"]:
                    differences.append({"item": "Interpreter version", "recorded": baseline["version"],
                                        "local": runtime["version"]})
                packages = {name.lower().replace("_", "-"): version
                            for name, version in runtime["packages"].items()}
                for name, version in baseline["packages"].items():
                    installed = packages.get(name.lower().replace("_", "-"))
                    current["packages"][name] = installed
                    if installed != version:
                        differences.append({"item": name, "recorded": version, "local": installed})
            except (OSError, ValueError) as error:
                differences.append({"item": "Interpreter", "recorded": baseline["interpreter"],
                                    "local": None, "detail": str(error)})
        # Imported vectors carry their own font resources and may use custom fonts.
        if panel.type != "vector":
            for name, version in baseline["fonts"].items():
                installed = fonts.get(face_key(name))
                current["fonts"][name] = installed
                if installed is None or (version and installed and version != installed):
                    differences.append({"item": f"Font {name}", "recorded": version or "Available",
                                        "local": installed})
        panels.append({"id": panel.id, "name": panel.name, "recorded": baseline,
                       "local": current, "differences": differences})
    return {"data_folder": str(directory), "data_folder_available": directory.is_dir(), "panels": panels}
