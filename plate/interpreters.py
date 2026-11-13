"""Discover and check the user's R and Python interpreters."""

from functools import lru_cache
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

R_NAMES = ("Rscript",)
PYTHON_NAMES = ("python3", "python")
R_PACKAGES = ("ggplot2", "jsonlite", "systemfonts")


@lru_cache(maxsize=1)
def login_path():
    inherited = os.environ.get("PATH", "")
    try:
        result = subprocess.run(
            ["/bin/zsh", "-lc", 'printf "%s" "$PATH"'], capture_output=True, text=True,
            timeout=4, check=True,
        )
        shell_path = result.stdout.splitlines()[-1]
    except (OSError, IndexError, subprocess.SubprocessError):
        shell_path = ""
    return os.pathsep.join(dict.fromkeys(filter(None, (
        inherited + os.pathsep + shell_path + ":/opt/homebrew/bin:/usr/local/bin:/usr/bin:"
        "/Library/Frameworks/R.framework/Resources/bin"
    ).split(os.pathsep))))


def is_conda_r(path):
    return any((parent / "conda-meta").is_dir() for parent in Path(path).resolve().parents)


def candidates(names, paths):
    for folder in paths:
        for name in names:
            file = Path(folder).expanduser() / name
            if file.is_file() and os.access(file, os.X_OK):
                yield str(file.absolute())


def discovery(extra=()):
    search = login_path().split(os.pathsep)
    python = [sys.executable, *candidates(PYTHON_NAMES, search)]
    roots = [Path(item).expanduser() for item in extra]
    for parent in (Path.home() / ".virtualenvs", Path.home() / ".venvs"):
        if parent.is_dir():
            roots.extend(sorted(parent.iterdir()))
    conda = shutil.which("conda", path=login_path())
    if conda:
        try:
            result = subprocess.run([conda, "env", "list", "--json"], capture_output=True,
                                    timeout=6, check=True)
            roots.extend(Path(env) for env in json.loads(result.stdout)["envs"])
        except (OSError, KeyError, ValueError, subprocess.SubprocessError):
            pass
    python.extend(candidates(PYTHON_NAMES, [root / "bin" for root in roots]))
    r = [path for path in candidates(R_NAMES, search) if not is_conda_r(path)]
    return {"script-py": list(dict.fromkeys(python)), "script-r": list(dict.fromkeys(r))}


def interpreter(project, panel):
    configured = panel.interpreter or project.interpreters.get(panel.type)
    if configured:
        path = Path(configured).expanduser()
        found = str(path) if path.is_absolute() else shutil.which(str(path), path=login_path())
    elif panel.type == "script-py":
        found = sys.executable
    else:
        found = next((path for path in candidates(R_NAMES, login_path().split(os.pathsep))
                      if not is_conda_r(path)), None)
    if not found or not Path(found).is_file() or not os.access(found, os.X_OK):
        raise ValueError(f"{panel.type.removeprefix('script-').upper()} interpreter not found.")
    if panel.type == "script-r" and is_conda_r(found):
        raise ValueError("Choose the system or Homebrew Rscript.")
    return found


@lru_cache(maxsize=64)
def _probe(path, language, modified, refresh):
    if language == "script-py":
        args = ["-c", 'import sys, importlib.util as u; print(sys.version.split()[0]); '
                'print(",".join(p for p in ["matplotlib"] if not u.find_spec(p)))']
        install = f"{shlex.quote(path)} -m pip install matplotlib"
    else:
        names = ",".join(f'"{pkg}"' for pkg in R_PACKAGES)
        args = ["--vanilla", "-e",
                f'cat(as.character(getRversion()), "\\n"); p <- c({names}); '
                'cat(paste(p[!sapply(p, requireNamespace, quietly=TRUE)], collapse=","), "\\n"); '
                'ok <- tryCatch({ f <- tempfile(); cairo_pdf(f); plot.new(); dev.off(); '
                'unlink(f); TRUE }, warning=function(w) FALSE, error=function(e) FALSE); '
                'cat(if(ok) "cairo-ok" else "cairo-missing")']
        install = f'{shlex.quote(path)} -e \'install.packages(c({names}), repos="https://cloud.r-project.org")\''
    result = subprocess.run([path, *args], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Interpreter check failed.")
    lines = result.stdout.rstrip().splitlines()
    missing = [pkg.strip() for pkg in lines[1].split(",") if pkg.strip()] if len(lines) > 1 else []
    if language == "script-r" and lines[-1] != "cairo-ok":
        missing.append("Cairo PDF device")
        install = "brew install --cask xquartz\n" + install
    return {"version": lines[0].strip(), "missing": missing,
            "install": install, "path": path}


def probe(path, language, refresh=False):
    if refresh:
        _probe.cache_clear()
    return _probe(path, language, Path(path).stat().st_mtime_ns, False)
