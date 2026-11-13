"""Compose editable PDF forms, then rasterize the final page when requested."""

from io import BytesIO
import math
import re

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
    return outer[0]


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
    overflow = not clip.contains(full) or any(
        not full.contains(pdf.Rect(entry[1])) for entry in source_page.get_bboxlog()
    )
    return flatten_placement(page.parent, page, content), overflow


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
        for entry in panels:
            path, box, *label_data = entry
            rect = pdf_rect(box)
            if path is None:
                source = empty_page(rect.width, rect.height)
            elif isinstance(path, bytes):
                source = pdf.open(stream=path, filetype="pdf")
            else:
                source = pdf.open(path)
            with source:
                form, overflow = placement(page, source, rect)
            if label_data:
                label, panel_box, style = label_data
                if label:
                    append_label(document, page, label, pdf_rect(panel_box), style, form, overflow)
                    page = document[0]
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


def append_label(document, page, label, rect, style, form, overflow):
    """Append a label within the panel form's resources and coordinate system."""
    from .fonts import get_font

    kind, value = document.xref_get_key(form, "Matrix")
    a, _, _, d, e, f = [float(n) for n in value.strip("[]").split()] if kind == "array" else (1, 0, 0, 1, 0, 0)
    font = get_font(style["font_family"], style["panel_label_weight"] == "bold")
    size = style["panel_label_pt"]
    offset_x = style["label_offset_x_mm"] * PT_PER_MM
    offset_y = style["label_offset_y_mm"] * PT_PER_MM
    top = page.rect.height - rect.y0
    x = (rect.x0 + offset_x - e) / a
    y = (top - offset_y - font.ascender * size - f) / d

    # Keep existing overflow clipping when expanding the form to include the label.
    _, bbox = document.xref_get_key(form, "BBox")
    stream = document.xref_stream(form)
    x0, y0, x1, y1 = [float(n) for n in bbox.strip("[]").split()]
    clip = f"q {x0:.8f} {y0:.8f} {x1-x0:.8f} {y1-y0:.8f} re W n\n".encode()
    bounds = [(rect.x0-e)/a, (page.rect.height-rect.y1-f)/d, (rect.x1-e)/a, (top-f)/d]
    if overflow and min(bounds[0]-x0, bounds[1]-y0, x1-bounds[2], y1-bounds[3]) < -.001:
        stream = clip + stream + b"\nQ"
    document.xref_set_key(form, "BBox", "[" + " ".join(f"{v:.8f}" for v in bounds) + "]")

    with pdf.open() as scratch:
        label_page = scratch.new_page(width=rect.width, height=rect.height)
        writer = pdf.TextWriter(label_page.rect)
        writer.append((0, size), label, font=font, fontsize=size)
        writer.write_text(label_page)
        scratch.subset_fonts()
        # Graft the embedded font via a temporary page, then share its reference.
        document.insert_pdf(scratch)
        graft = document[-1]
        source_fonts = graft.get_fonts()
        label_stream = graft.read_contents()
        document.delete_page(-1)

    resources_kind, resources = document.xref_get_key(form, "Resources")
    resource_ref = document.get_new_xref()
    resource_object = document.xref_object(int(resources.split()[0])) if resources_kind == "xref" else resources
    document.update_object(resource_ref, resource_object if resource_object.startswith("<<") else "<<>>")
    document.xref_set_key(form, "Resources", f"{resource_ref} 0 R")
    font_kind, fonts = document.xref_get_key(resource_ref, "Font")
    font_ref = document.get_new_xref()
    font_object = document.xref_object(int(fonts.split()[0])) if font_kind == "xref" else fonts
    document.update_object(font_ref, font_object if font_object.startswith("<<") else "<<>>")
    document.xref_set_key(resource_ref, "Font", f"{font_ref} 0 R")
    for index, entry in enumerate(source_fonts):
        resource = f"PlateLabel{index}"
        document.xref_set_key(font_ref, resource, f"{entry[0]} 0 R")
        label_stream = re.sub(rb"/" + re.escape(entry[4].encode()) + rb"(?=\s)", f"/{resource}".encode(), label_stream)
    height = rect.height
    transform = f"q {1/a:.8f} 0 0 {1/d:.8f} {x:.8f} {y-(height-size)/d:.8f} cm\n".encode()
    document.update_stream(form, b"q\n" + stream + b"\nQ\n" + transform + label_stream + b"\nQ\n")
