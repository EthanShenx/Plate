"""Run plot scripts in fresh processes and retain previews by content hash."""

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from itertools import chain
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
from stat import S_ISREG
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile
from threading import Lock
from time import monotonic
from uuid import uuid4

from .bundle import SAFE_ID, script_path, write_json, atomic_write
from .checks import text_collisions
from .fonts import pdf_font_versions
from .interpreters import interpreter, login_path, probe
from .style import HELPERS, PT_PER_MM, context_for

WORKERS = Path(__file__).parent / "workers"
ABSOLUTE_PATH = re.compile(r"""['"](?:/(?!/)|[A-Za-z]:[\\/]|~/)""")
ENGINE_VERSION = 5
PREVIEW_DPI = (130, 260, 520, 1040)
MAX_PREVIEW_PIXELS = 12_000_000
PLOT_LOCK = Lock()
ACTIVE_PLOTS = set()
STOPPING_PLOTS = False
LOG_TAIL_BYTES = 64 * 1024


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
        dpi = []
        for image in page.get_image_info():
            a, b, c, d, _, _ = image["transform"]
            w, h = math.hypot(a, b), math.hypot(c, d)
            if w and h:
                dpi.append(min(image["width"] * 72 / w, image["height"] * 72 / h))
        collisions, count = text_collisions(page)
        return {"text": text, "fonts": pdf_font_versions(pdf, page),
                "page_pt": [page.rect.width, page.rect.height], "effective_dpi": dpi,
                "text_collisions": collisions, "text_collision_count": count}


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


def fit_pdf_text(path, axes=None):
    """Contain remaining page overflow, including figure-level text and base R."""
    import pymupdf

    with pymupdf.open(path) as document:
        if document.page_count != 1:
            return axes, False
        page = document[0]
        frame = page.rect
        bounds = pymupdf.Rect(frame)
        for kind, bbox in page.get_bboxlog():
            if kind in {"fill-text", "stroke-text"}:
                bounds |= pymupdf.Rect(bbox)
        if bounds == frame:
            return axes, False
        margin = 1
        scale = min((frame.width - 2*margin) / bounds.width,
                    (frame.height - 2*margin) / bounds.height)
        x = (frame.width - scale*bounds.width) / 2 - scale*bounds.x0
        y = (frame.height - scale*bounds.height) / 2 - scale*bounds.y0
        # MuPDF bounds run down from the top, while PDF drawing coordinates run up.
        ty = frame.height * (1-scale) - y
        page.wrap_contents()
        wrappers = []
        for data in (f"q {scale:.10f} 0 0 {scale:.10f} {x:.8f} {ty:.8f} cm\n".encode(), b"\nQ\n"):
            ref = document.get_new_xref()
            document.update_object(ref, "<<>>")
            document.update_stream(ref, data)
            wrappers.append(ref)
        contents = [wrappers[0], *page.get_contents(), wrappers[1]]
        document.xref_set_key(page.xref, "Contents", "[" + " ".join(f"{ref} 0 R" for ref in contents) + "]")
        result = document.tobytes(garbage=3)
        if axes:
            axes = [scale*value + (x/frame.width if index % 2 == 0 else ty/frame.height)
                    for index, value in enumerate(axes)]
    path.write_bytes(result)
    return axes, True


def preview_dpi(width_pt, height_pt, requested):
    return max(1, min(requested, int(72 * math.sqrt(MAX_PREVIEW_PIXELS / (width_pt * height_pt)))))


def make_preview(pdf_path, png_path, dpi=PREVIEW_DPI[0]):
    import pymupdf

    with pymupdf.open(pdf_path) as pdf:
        page = pdf[0]
        pixmap = page.get_pixmap(dpi=preview_dpi(page.rect.width, page.rect.height, dpi), alpha=True)
        atomic_write(png_path, lambda path: path.write_bytes(pixmap.tobytes("png")))


class RenderError(ValueError):
    def __init__(self, message, stdout="", stderr=""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def kill_plot(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def stop_plot_processes():
    global STOPPING_PLOTS
    with PLOT_LOCK:
        STOPPING_PLOTS = True
        for process in ACTIVE_PLOTS:
            kill_plot(process)


def log_tail(stream):
    size = stream.tell()
    stream.seek(max(0, size - LOG_TAIL_BYTES))
    text = stream.read().decode(errors="replace")
    return f"[Earlier output omitted]\n{text}" if size > LOG_TAIL_BYTES else text


def plot_process(command, cwd, env, timeout):
    with TemporaryFile() as stdout, TemporaryFile() as stderr:
        with PLOT_LOCK:
            if STOPPING_PLOTS:
                raise RenderError("Plate is closing.")
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout,
                                       stderr=stderr, start_new_session=True)
            ACTIVE_PLOTS.add(process)
        try:
            status = process.wait(timeout=timeout)
            return status, log_tail(stdout), log_tail(stderr)
        except subprocess.TimeoutExpired:
            kill_plot(process)
            process.wait()
            raise RenderError(f"Render timed out after {timeout:g} seconds.",
                              log_tail(stdout), log_tail(stderr)) from None
        finally:
            with PLOT_LOCK:
                ACTIVE_PLOTS.discard(process)


def data_directory(project, workspace, bundle, override=None):
    if override:
        return Path(override)
    if project.data_root:
        root = Path(project.data_root).expanduser()
        return root if root.is_absolute() else (bundle.parent if bundle else workspace) / root
    return bundle.parent if bundle else workspace


@lru_cache(maxsize=512)
def file_digest(path, stamp):
    digest = sha256()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != stamp:
            raise OSError("Input changed while opening.")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        closed = os.fstat(stream.fileno())
        if (closed.st_dev, closed.st_ino, closed.st_size, closed.st_mtime_ns, closed.st_ctime_ns) != stamp:
            raise OSError("Input changed while reading.")
    return digest.hexdigest()


def input_fingerprints(panel, directory):
    fingerprints = {}
    for declared in sorted(set(panel.input_files)):
        try:
            path = (directory / Path(declared).expanduser()).resolve()
            stat = path.stat()
            if not S_ISREG(stat.st_mode):
                fingerprints[declared] = None
                continue
            stamp = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            fingerprints[declared] = file_digest(path, stamp)
        except (OSError, RuntimeError, ValueError):
            fingerprints[declared] = None
    return fingerprints


def seed_matplotlib_cache(cache, workspaces):
    """Reuse Plate's shared font inventory or an older project-local one."""
    if any(cache.glob("fontlist-*.json")):
        return
    for source in chain((workspaces.parent / "matplotlib").glob("fontlist-*.json"),
                        workspaces.glob("*/matplotlib/fontlist-*.json")):
        destination = cache / source.name
        if not destination.exists():
            atomic_write(destination, lambda tmp: shutil.copyfile(source, tmp))


@dataclass
class ScriptJob:
    key: str
    command: list[str]
    cwd: Path
    env: dict
    timeout: float

    def run(self):
        return plot_process(self.command, self.cwd, self.env, self.timeout)


@contextmanager
def prepare_script(project, panel, rect, workspace, bundle, context=None, *,
                   matplotlib_cache=None, data_root=None, force=False):
    started = monotonic()
    context = context or context_for(project, panel, rect)
    path = interpreter(project, panel)
    stamp = Path(path).stat().st_mtime_ns
    info = probe(path, panel.type)
    if info["missing"]:
        info = probe(path, panel.type, refresh=True)
    if info["missing"]:
        raise RenderError("Missing packages: " + ", ".join(info["missing"]), stderr=info["install"])
    cwd = data_directory(project, workspace, bundle, data_root).resolve()
    if not cwd.is_dir():
        raise RenderError(f"Data root does not exist: {cwd}")
    inputs = input_fingerprints(panel, cwd)
    unavailable = [name for name, digest in inputs.items() if digest is None]
    if unavailable:
        raise RenderError("Input files are missing, unreadable or changing: " + ", ".join(unavailable))
    version = json.dumps([info["version"], stamp, str(cwd), inputs], sort_keys=True)
    key = signature(project, panel, rect, context, path, version)
    cache = workspace / "cache"
    cache.mkdir(exist_ok=True)
    record = cache / f"{key}.json"
    if not force and record.is_file():
        cached = json.loads(record.read_text())
        artifact = cached["key"]
        if SAFE_ID.fullmatch(artifact) and all((cache / f"{artifact}.{ext}").is_file()
                                              for ext in ("pdf", "png")):
            yield {**cached, "cached": True}, None
            return

    with TemporaryDirectory(dir=workspace) as folder:
        folder = Path(folder)
        write_json(folder / "style.json", context)
        env = {**os.environ, "PATH": login_path(), "PLATE_STYLE": str(folder / "style.json"),
               "MPLBACKEND": "Agg", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(HELPERS / "python") + (
                   os.pathsep + os.environ["PYTHONPATH"] if "PYTHONPATH" in os.environ else "")}
        if panel.type == "script-py":
            config = matplotlib_cache or workspace / "matplotlib"
            config.mkdir(parents=True, exist_ok=True)
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

        def finish(process_result):
            status, stdout, stderr = process_result
            if status or not pdf.is_file():
                raise RenderError(f"Plot process exited with status {status}.", stdout, stderr)
            if input_fingerprints(panel, cwd) != inputs:
                raise RenderError("An input file changed during rendering. Refresh the panel.", stdout, stderr)
            try:
                if panel.type == "script-r":
                    normalize_r_pdf(pdf, context["size_mm"])
                layout = json.loads(metadata.read_text())
                runtime = layout.pop("runtime")
                layout["axes"], fitted = fit_pdf_text(pdf, layout.get("axes"))
                parsed = {**pdf_metadata(pdf), **layout}
                if any(abs(mm * PT_PER_MM - pt) > 0.01 * PT_PER_MM
                       for mm, pt in zip(context["size_mm"], parsed["page_pt"], strict=True)):
                    raise ValueError("Plot device did not produce the requested physical size.")
            except (OSError, ValueError, RuntimeError) as error:
                raise RenderError(str(error), stdout, stderr) from error
            # A forced render gets a new preview URL even with identical inputs.
            artifact = sha256(f"{key}:{uuid4().hex}".encode()).hexdigest() if force else key
            make_preview(pdf, cache / f"{artifact}.png")
            os.replace(pdf, cache / f"{artifact}.pdf")
            result = {
                "key": artifact, "signature": signature(project, panel, rect, context), "state": "fresh",
                "interpreter_stamp": [path, stamp],
                "stdout": stdout, "stderr": stderr, "seconds": monotonic() - started,
                "warnings": ["Script contains an absolute path."] if ABSOLUTE_PATH.search(panel.script) else [],
                "metadata": parsed, "runtime": runtime,
            }
            if fitted:
                result["warnings"].append("Content was scaled to fit the panel. Enlarge the panel to keep the requested font sizes.")
            write_json(record, result)
            return result

        yield ScriptJob(key, command, cwd, env, project.timeout_s), finish


def render_script(project, panel, rect, workspace, bundle, context=None, *,
                  matplotlib_cache=None, data_root=None, force=False):
    with prepare_script(project, panel, rect, workspace, bundle, context,
                        matplotlib_cache=matplotlib_cache, data_root=data_root, force=force) as (job, finish):
        return job if finish is None else finish(job.run())
