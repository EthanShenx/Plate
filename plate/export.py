"""Compose editable PDF forms, then rasterize the final page when requested."""

from io import BytesIO
import math

from PIL import Image
import pymupdf as pdf

from .style import MM_PER_IN, PT_PER_MM

DPIS = (300, 600, 1200)
FORMATS = {"pdf", "png", "tiff"}


def pdf_rect(rect):
    x, y, w, h = (rect[key] * PT_PER_MM for key in ("x", "y", "w", "h"))
    return pdf.Rect(x, y, x + w, y + h)


def flatten_placement(document, page, content):
    # MuPDF wraps each source page in a second form to handle placement. Move
    # the source resources and stream into the outer form, retaining its matrix.
    outer = next(item for item in reversed(page.get_xobjects()) if item[2] == 0)
    resources = document.xref_get_key(content, "Resources")[1]
    document.xref_set_key(outer[0], "Resources", resources)
    document.update_stream(outer[0], document.xref_stream(content))


def placement(page, source, rect):
    source_page = source[0]
    full = source_page.rect
    if source_page.rotation:
        source_page.remove_rotation()
        full = source_page.rect
    # Stale plots retain their rendered typography. If necessary, clip the
    # overflowing edges at the current panel boundary and center the remainder.
    crop_w, crop_h = min(rect.width, full.width), min(rect.height, full.height)
    x, y = (full.width - crop_w) / 2, (full.height - crop_h) / 2
    clip = pdf.Rect(x, y, x + crop_w, y + crop_h)
    dx, dy = (rect.width - crop_w) / 2, (rect.height - crop_h) / 2
    destination = pdf.Rect(rect.x0 + dx, rect.y0 + dy, rect.x1 - dx, rect.y1 - dy)
    content = page.show_pdf_page(destination, source, 0, clip=clip, keep_proportion=False)
    flatten_placement(page.parent, page, content)


def empty_page(width, height):
    source = pdf.open()
    page = source.new_page(width=width, height=height)
    xref = source.get_new_xref()
    source.update_object(xref, "<<>>")
    source.update_stream(xref, b"q Q\n")
    page.set_contents(xref)
    return source


def compose_pdf(width_mm, height_mm, panels):
    """Combine a sequence of (PDF path or bytes, rectangle in mm) entries."""
    with pdf.open() as document:
        page = document.new_page(width=width_mm * PT_PER_MM, height=height_mm * PT_PER_MM)
        for path, box in panels:
            rect = pdf_rect(box)
            if path is None:
                source = empty_page(rect.width, rect.height)
            elif isinstance(path, bytes):
                source = pdf.open(stream=path, filetype="pdf")
            else:
                source = pdf.open(path)
            with source:
                placement(page, source, rect)
        return document.tobytes(garbage=4, deflate=True)


def rasterize(data, width_mm, height_mm, format, dpi):
    if format not in {"png", "tiff"} or dpi not in DPIS:
        raise ValueError("Choose PNG or TIFF at 300, 600 or 1200 dpi.")
    width, height = (math.floor(mm / MM_PER_IN * dpi + .5) for mm in (width_mm, height_mm))
    if width * height > 160_000_000:
        raise ValueError("The selected size and dpi exceed the raster export memory limit.")
    with pdf.open(stream=data, filetype="pdf") as document:
        page = document[0]
        image = page.get_pixmap(matrix=pdf.Matrix((width - 0.001) / page.rect.width,
                                                  (height - 0.001) / page.rect.height),
                                colorspace=pdf.csRGB, alpha=False)
        result = Image.frombytes("RGB", (image.width, image.height), image.samples)
    if result.size != (width, height):
        raise ValueError("Raster device returned unexpected image dimensions.")
    output = BytesIO()
    options = {"compression": "tiff_lzw"} if format == "tiff" else {}
    result.save(output, format=format.upper(), dpi=(dpi, dpi), **options)
    return output.getvalue()
