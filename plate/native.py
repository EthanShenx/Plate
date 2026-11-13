"""Physical rendering of raster, vector, text and legend panels."""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image
import pymupdf as pdf

from .bundle import atomic_write, write_json
from .export import flatten_placement
from .fonts import get_font, name_embedded_fonts, write_text
from .interpreters import login_path
from .render import make_preview, pdf_metadata
from .style import PT_PER_MM, context_for


def rgb(color):
    return tuple(int(color[index:index+2], 16) / 255 for index in (1, 3, 5))


def fit_rect(width, height, bounds, cover=False, crop=None):
    x, y, w, h = crop or (0, 0, 1, 1)
    factor = (max if cover else min)(bounds.width / (width*w), bounds.height / (height*h))
    left = (bounds.width - width*w*factor) / 2 - width*x*factor
    top = (bounds.height - height*h*factor) / 2 - height*y*factor
    return pdf.Rect(bounds.x0 + left, bounds.y0 + top,
                    bounds.x0 + left + width*factor, bounds.y0 + top + height*factor)


def raster_page(page, path, settings):
    with Image.open(path) as image:
        width, height = image.size
        if image.format in {"JPEG", "PNG"}:
            data = path.read_bytes()
        else:
            stream = BytesIO()
            image.convert("RGBA" if "A" in image.getbands() else "RGB").save(stream, format="PNG")
            data = stream.getvalue()
    target = fit_rect(width, height, page.rect, settings.get("fit") == "cover", settings.get("crop"))
    before = set(page.get_contents())
    page.insert_image(target, stream=data, keep_proportion=False)
    x, y, w, h = settings.get("crop") or (0, 0, 1, 1)
    clip = pdf.Rect(target.x0 + x*target.width, target.y0 + y*target.height,
                    target.x0 + (x+w)*target.width, target.y0 + (y+h)*target.height) & page.rect
    if clip != page.rect and not clip.contains(target):
        for ref in set(page.get_contents()) - before:
            body = page.parent.xref_stream(ref)
            page.parent.update_stream(ref, f"q {clip.x0:.8f} {page.rect.height-clip.y1:.8f} "
                                      f"{clip.width:.8f} {clip.height:.8f} re W n\n".encode()
                                      + body + b"\nQ\n")


def vector_source(path, workspace):
    if path.suffix.lower() == ".pdf":
        return pdf.open(path)
    converter = shutil.which("rsvg-convert", path=login_path())
    if not converter:
        raise ValueError("Install the SVG converter with brew install librsvg.")
    with TemporaryDirectory(dir=workspace) as folder:
        target = Path(folder) / "vector.pdf"
        result = subprocess.run([converter, "--format=pdf", "--output", str(target), str(path)],
                                capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError(result.stderr.decode(errors="replace").strip())
        return pdf.open(stream=target.read_bytes(), filetype="pdf")


def vector_page(page, path, workspace):
    with vector_source(path, workspace) as source:
        if not source.page_count:
            raise ValueError("The vector asset has no pages.")
        box = source[0].rect
        target = fit_rect(box.width, box.height, page.rect)
        if source[0].rotation:
            source[0].remove_rotation()
        document = page.parent
        ref = page.show_pdf_page(target, source, 0)
        form = flatten_placement(document, page, ref)
        # A vector panel is a placed page with no additional native drawings.
        # Move the source form's matrix, content and resources onto the page.
        _, matrix = document.xref_get_key(form, "Matrix")
        _, bounds = document.xref_get_key(form, "BBox")
        x0, y0, x1, y1 = [float(value) for value in bounds.strip("[]").split()]
        transforms = " ".join(matrix.strip("[]").split())
        clip = f"{x0} {y0} {x1-x0} {y1-y0} re W n\n"
        if all(pdf.Rect(box).contains(pdf.Rect(entry[1])) for entry in source[0].get_bboxlog()):
            clip = ""
        document.xref_set_key(page.xref, "Resources", document.xref_get_key(form, "Resources")[1])
        ref = page.get_contents()[-1]
        document.update_stream(ref, f"q {transforms} cm\n{clip}".encode()
                               + document.xref_stream(form) + b"\nQ\n")


def wrapped_lines(text, font, size, width):
    for paragraph in text.splitlines():
        words = paragraph.split()
        if not words:
            yield ""
            continue
        line = words[0]
        for word in words[1:]:
            combined = f"{line} {word}"
            if font.text_length(combined, fontsize=size) > width:
                yield line
                line = word
            else:
                line = combined
        yield line


def text_panel(page, panel, style):
    font = get_font(style["font_family"])
    size = style["annotation_pt" if panel.settings.get("role") == "annotation" else "font_main_pt"]
    align = panel.settings.get("align", "left")
    lines = []
    margin = 2 * PT_PER_MM
    y = margin + font.ascender * size
    for line in wrapped_lines(panel.settings.get("text", ""), font, size, max(1, page.rect.width - 2*margin)):
        span = font.text_length(line, fontsize=size)
        x = {"left": margin, "center": (page.rect.width - span)/2,
             "right": page.rect.width - span - margin}.get(align, margin)
        if line:
            lines.append((x, y, line))
        y += 1.25 * size
    if lines:
        write_text(page, lines, font, size)


def legend_panel(page, panel, context):
    style, colors = context["style"], context["colors"]
    keys = panel.settings.get("keys", list(colors))
    direction = panel.settings.get("direction", "vertical")
    shape = panel.settings.get("swatch", "patch")
    size = style["legend_text_pt"]
    font = get_font(style["font_family"])
    lines = []
    margin = 2 * PT_PER_MM
    x, y = margin, margin + font.ascender * size
    for key in keys:
        if key not in colors:
            continue
        color = rgb(colors[key])
        width = size * 1.7 + font.text_length(key, fontsize=size)
        if direction == "horizontal" and x > margin and x + width > page.rect.width - margin:
            x, y = margin, y + size * 1.65
        if shape == "line":
            page.draw_line((x, y - size*.35), (x+size, y-size*.35),
                           color=color, width=style["line_data_pt"])
        elif shape == "point":
            page.draw_circle((x+size/2, y-size*.35), style["marker_size_pt"]/2, color=None, fill=color)
        else:
            page.draw_rect(pdf.Rect(x, y-size*.75, x+size, y), color=None, fill=color)
        lines.append((x+size*1.4, y, key))
        if direction == "horizontal":
            x += width + size
        else:
            y += size * 1.65
    if lines:
        write_text(page, lines, font, size)


def native_signature(project, panel, rect):
    data = (4, panel.type, panel.settings, panel.asset, context_for(project, panel, rect))
    return sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def render_native(project, panel, rect, workspace):
    context = context_for(project, panel, rect)
    key = native_signature(project, panel, rect)
    directory = workspace / "cache"
    directory.mkdir(exist_ok=True)
    output, preview, record = [directory / f"{key}.{ext}" for ext in ("pdf", "png", "json")]
    if all(path.is_file() for path in (output, preview, record)):
        return json.loads(record.read_text())
    width, height = (mm * PT_PER_MM for mm in context["size_mm"])
    with pdf.open() as document:
        page = document.new_page(width=width, height=height)
        if panel.type in {"image", "vector"}:
            if not panel.asset:
                return {"state": "stale", "signature": key}
            if panel.type == "image":
                raster_page(page, workspace / panel.asset, panel.settings)
            else:
                vector_page(page, workspace / panel.asset, workspace)
        elif panel.type == "text":
            text_panel(page, panel, context["style"])
        elif panel.type == "legend":
            legend_panel(page, panel, context)
        if not page.get_contents():
            stream = document.get_new_xref()
            document.update_object(stream, "<<>>")
            document.update_stream(stream, b"q Q\n")
            page.set_contents(stream)
        if panel.type in {"text", "legend"}:
            document.subset_fonts()
            name_embedded_fonts(document, page)
        atomic_write(output, lambda tmp: tmp.write_bytes(document.tobytes(garbage=4, deflate=True)))
    metadata = pdf_metadata(output)
    make_preview(output, preview)
    result = {"state": "fresh", "key": key, "signature": key, "metadata": metadata}
    write_json(record, result)
    return result
