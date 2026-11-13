"""Run plot scripts in fresh processes and retain previews by content hash."""

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic

from .bundle import script_path, write_json, atomic_write
from .interpreters import interpreter, login_path, probe
from .style import HELPERS, PT_PER_MM, context_for

WORKERS = Path(__file__).parent / "workers"
ABSOLUTE_PATH = re.compile(r"""['"](?:/(?!/)|[A-Za-z]:[\\/]|~/)""")
ENGINE_VERSION = 1


def signature(project, panel, rect, context=None, path=None, version=None):
    payload = {
        "engine": ENGINE_VERSION, "script": panel.script, "type": panel.type,
        "context": context if context is not None else context_for(project, panel, rect),
        "interpreter": path or panel.interpreter or project.interpreters.get(panel.type),
        "version": version, "data_root": project.data_root,
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def pdf_metadata(path):
    import pymupdf

    with pymupdf.open(path) as pdf:
        if pdf.page_count != 1:
            raise ValueError("A script must produce exactly one plot page.")
        page = pdf[0]
        text = []
        for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if span["text"].strip():
                        text.append({key: span[key] for key in ("text", "font", "size", "bbox")})
        return {"text": text, "page_pt": [page.rect.width, page.rect.height]}


def normalize_r_pdf(path, size_mm):
    import pymupdf

    with pymupdf.open(path) as document:
        # Cairo R rounds the MediaBox to whole points. Restore the requested page
        # size without scaling content or changing any font or stroke widths.
        if document.page_count == 2 and not document[0].get_bboxlog():
            document.delete_page(0)
        if document.page_count == 1:
            expected = [mm * PT_PER_MM for mm in size_mm]
            page = document[0]
            if all(abs(value - actual) <= 1 for value, actual in
                   zip(expected, (page.rect.width, page.rect.height), strict=True)):
                page.set_mediabox(pymupdf.Rect(0, 0, *expected))
                changed = document.tobytes(garbage=3)
            else:
                return
        else:
            return
    path.write_bytes(changed)


def make_preview(pdf_path, png_path):
    import pymupdf

    with pymupdf.open(pdf_path) as pdf:
        pixmap = pdf[0].get_pixmap(dpi=130, alpha=True)
        atomic_write(png_path, lambda path: path.write_bytes(pixmap.tobytes("png")))


class RenderError(ValueError):
    def __init__(self, message, stdout="", stderr=""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def plot_process(command, cwd, env, timeout):
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, start_new_session=True) as process:
        try:
            output, errors = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            output, errors = process.communicate()
            raise RenderError(f"Render timed out after {timeout:g} seconds.",
                              output.decode(errors="replace"), errors.decode(errors="replace")) from None
        return process.returncode, output.decode(errors="replace"), errors.decode(errors="replace")


def render_script(project, panel, rect, workspace, bundle, context=None):
    started = monotonic()
    context = context or context_for(project, panel, rect)
    path = interpreter(project, panel)
    info = probe(path, panel.type)
    if info["missing"]:
        info = probe(path, panel.type, refresh=True)
    if info["missing"]:
        raise RenderError("Missing packages: " + ", ".join(info["missing"]), stderr=info["install"])
    cwd = Path(project.data_root).expanduser() if project.data_root else (
        bundle.parent if bundle else workspace)
    if not cwd.is_dir():
        raise RenderError(f"Data root does not exist: {cwd}")
    key = signature(project, panel, rect, context, path, info["version"] + str(cwd.resolve()))
    cache = workspace / "cache"
    cache.mkdir(exist_ok=True)
    output, preview, record = [cache / f"{key}.{ext}" for ext in ("pdf", "png", "json")]
    if output.is_file() and preview.is_file() and record.is_file():
        return {**json.loads(record.read_text()), "cached": True}

    with TemporaryDirectory(dir=workspace) as folder:
        folder = Path(folder)
        write_json(folder / "style.json", context)
        env = {**os.environ, "PATH": login_path(), "PLATE_STYLE": str(folder / "style.json"),
               "MPLBACKEND": "Agg", "PYTHONPATH": str(HELPERS / "python") + (
                   os.pathsep + os.environ["PYTHONPATH"] if "PYTHONPATH" in os.environ else "")}
        if panel.type == "script-py":
            config = workspace / "matplotlib"
            config.mkdir(exist_ok=True)
            env["MPLCONFIGDIR"] = str(config)
        script = script_path(workspace, panel)
        pdf = folder / "panel.pdf"
        metadata = folder / "metadata.json"
        args = [str(script), str(pdf), str(metadata)]
        if panel.type == "script-py":
            command = [path, str(WORKERS / "python_plot.py"), *args]
        else:
            command = [path, "--vanilla", str(WORKERS / "r_plot.R"), *args,
                       str(HELPERS / "r/plate")]
        status, stdout, stderr = plot_process(command, cwd, env, project.timeout_s)
        if status or not pdf.is_file():
            raise RenderError(f"Plot process exited with status {status}.", stdout, stderr)
        try:
            if panel.type == "script-r":
                normalize_r_pdf(pdf, context["size_mm"])
            parsed = pdf_metadata(pdf)
            parsed.update(json.loads(metadata.read_text()))
            if any(abs(mm * PT_PER_MM - pt) > 0.01 * PT_PER_MM
                   for mm, pt in zip(context["size_mm"], parsed["page_pt"], strict=True)):
                raise ValueError("Plot device did not produce the requested physical size.")
        except (OSError, ValueError, RuntimeError) as error:
            raise RenderError(str(error), stdout, stderr) from error
        make_preview(pdf, preview)
        os.replace(pdf, output)
        result = {
            "key": key, "signature": signature(project, panel, rect, context), "state": "fresh",
            "stdout": stdout, "stderr": stderr, "seconds": monotonic() - started,
            "warnings": ["Script contains an absolute path."] if ABSOLUTE_PATH.search(panel.script) else [],
            "metadata": parsed,
        }
        write_json(record, result)
        return result
