"""Find installed font files for native Plate text and labels."""

from functools import lru_cache
from io import BytesIO
from pathlib import Path
import re

from fontTools.ttLib import TTCollection, TTFont, TTLibError
import pymupdf

from .checks import font_key

DIRECTORIES = (
    Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"),
    Path.home() / "Library/Fonts", Path("/System/Library/Fonts"),
    Path("/usr/share/fonts"), Path("/opt/homebrew/share/fonts"),
)


@lru_cache(maxsize=1)
def font_index():
    index = {}
    for root in DIRECTORIES:
        for path in sorted(root.rglob("*")):
            suffix = path.suffix.lower()
            if suffix not in {".ttf", ".otf", ".ttc"}:
                continue
            try:
                collection = TTCollection(path, lazy=True) if suffix == ".ttc" else None
                fonts = collection.fonts if collection else [TTFont(path, lazy=True)]
                for number, font in enumerate(fonts):
                    names = font["name"]
                    family = font_key(names.getBestFamilyName() or path.stem)
                    style = (names.getBestSubFamilyName() or "").lower()
                    if style in {"regular", "normal", "book", "roman", "bold"}:
                        index.setdefault((family, style == "bold"), (path, number))
                for font in fonts:
                    font.close()
            except (OSError, KeyError, ValueError, TTLibError):
                continue
    return index


@lru_cache(maxsize=64)
def get_font(family, bold=False):
    index = font_index()
    name = font_key(family)
    match = index.get((name, bold)) or index.get((name, False))
    if not match:
        return pymupdf.Font(fontname="hebo" if bold else "helv")
    path, number = match
    if path.suffix.lower() == ".ttc":
        with TTFont(path, fontNumber=number) as font:
            output = BytesIO()
            font.save(output)
        return pymupdf.Font(fontbuffer=output.getvalue())
    return pymupdf.Font(fontfile=str(path))


def label_metrics(label, width, height, style):
    from .style import PT_PER_MM

    height = max(height, 1)
    font = get_font(style["font_family"], style["panel_label_weight"] == "bold")
    size = style["panel_label_pt"]
    text_width = font.text_length(label, fontsize=1)
    text_height = font.ascender - font.descender
    # A manual label can be longer than its panel. Fit it inside the page with
    # a small allowance for glyph overhangs and report the resulting print size.
    inset = min(1.0, width / 8, height / 8)
    size = min(size, (width - 2*inset) / max(text_width, .01), (height - 2*inset) / text_height)
    x = max(inset, min(style["label_offset_x_mm"] * PT_PER_MM, width - text_width*size - inset))
    y = max(inset, min(style["label_offset_y_mm"] * PT_PER_MM, height - text_height*size - inset))
    return font, size, (x, y, x + text_width*size, y + text_height*size)


def name_embedded_fonts(document, page):
    """Use actual PostScript names so editors can match installed font faces."""
    for xref, _, kind, name, *_ in page.get_fonts():
        if kind not in {"Type0", "TrueType"}:
            continue
        _, _, _, data = document.extract_font(xref)
        if not data:
            continue
        try:
            with TTFont(BytesIO(data), lazy=True) as embedded:
                postscript = embedded["name"].getDebugName(6)
        except (OSError, KeyError, ValueError, TTLibError):
            continue
        if not postscript:
            continue
        prefix = re.match(r"^[A-Z]{6}\+", name)
        if prefix and not re.match(r"^[A-Z]{6}\+", postscript):
            postscript = prefix.group() + postscript
        value = "/" + "".join(chr(byte) if byte in b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                              b"0123456789-_.+" else f"#{byte:02X}"
                              for byte in postscript.encode("utf-8"))
        document.xref_set_key(xref, "BaseFont", value)
        if kind == "Type0":
            _, descendants = document.xref_get_key(xref, "DescendantFonts")
            xref = int(descendants.strip("[]").split()[0])
            document.xref_set_key(xref, "BaseFont", value)
        tag, descriptor = document.xref_get_key(xref, "FontDescriptor")
        if tag == "xref":
            document.xref_set_key(int(descriptor.split()[0]), "FontName", value)


def write_text(page, lines, font, size):
    """Write simple Latin text where possible, and Unicode elsewhere."""
    if all(all(32 <= ord(char) <= 126 for char in text) for _, _, text in lines):
        # Simple encoding is more reliably editable in desktop PDF importers.
        resource = "PlateLatin"
        page.insert_font(fontname=resource, fontbuffer=font.buffer, set_simple=True)
        for x, y, text in lines:
            page.insert_text((x, y), text, fontname=resource, fontsize=size)
    else:
        writer = pymupdf.TextWriter(page.rect)
        for x, y, text in lines:
            writer.append((x, y), text, font=font, fontsize=size)
        writer.write_text(page)
