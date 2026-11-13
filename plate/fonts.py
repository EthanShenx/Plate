"""Find installed font files for native Plate text and labels."""

from functools import lru_cache
from pathlib import Path

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
    from io import BytesIO

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
