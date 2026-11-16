"""Advisory checks for rendered and imported panels."""

import re


def text_collisions(page):
    """Find substantial intersections between separately drawn text runs."""
    runs = []
    for span in page.get_texttrace():
        if span["type"] == 3 or span["opacity"] < .05:
            continue
        text = "".join(chr(char[0]) for char in span["chars"]).strip()
        if not text:
            continue
        x0, y0, x1, y1 = span["bbox"]
        # Trim line-height padding in the direction perpendicular to the baseline.
        dx, dy = span["dir"]
        x_padding = min((x1 - x0) * .2, span["size"] * .15 * abs(dy))
        y_padding = min((y1 - y0) * .2, span["size"] * .15 * abs(dx))
        box = (max(0, x0 + x_padding), max(0, y0 + y_padding),
               min(page.rect.width, x1 - x_padding), min(page.rect.height, y1 - y_padding))
        if box[2] > box[0] and box[3] > box[1]:
            runs.append((box, text, span["seqno"]))

    active = []
    matches = []
    count = 0
    for box, text, sequence in sorted(runs):
        x0, y0, x1, y1 = box
        active = [run for run in active if run[0][2] > x0]
        for other, name, other_sequence in active:
            if sequence == other_sequence:
                continue
            width = min(x1, other[2]) - max(x0, other[0])
            height = min(y1, other[3]) - max(y0, other[1])
            if min(width, height) < .7:
                continue
            smaller_area = min((x1-x0)*(y1-y0), (other[2]-other[0])*(other[3]-other[1]))
            proportion = width * height / smaller_area
            if proportion < .24 or (text == name and proportion >= .93):
                continue
            count += 1
            if len(matches) < 24:
                matches.append({"texts": [name, text], "boxes": [other, box]})
        active.append((box, text, sequence))
    return matches, count


def font_key(name):
    name = re.sub(r"^[A-Z]{6}\+", "", name).lower()
    name = re.sub(r"[^a-z0-9]", "", name)
    return re.sub(r"(?:(?:postscript|regular|italic|oblique|bold|medium|light|semibold|psmt|mt|ps|roman|book))+$",
                  "", name)


def font_matches(expected, actual):
    a, b = font_key(expected), font_key(actual)
    return a == b or {"timesnewroman", "timesnewromanps"} == {a, b}


def panel_checks(panel, render, style):
    def check(kind, message, **fields):
        return {"kind": kind, "panel": panel.id, "message": message, **fields}

    checks = []
    metadata = render.get("metadata", {})
    label = render.get("label_metadata")
    spans = metadata.get("text", []) + ([label] if label else [])
    for span in spans:
        size = span["size"]
        if size < style["font_min_pt"] - 0.05:
            checks.append(check("font-size", f'“{span["text"]}” is {size:.2f} pt (minimum {style["font_min_pt"]:g} pt).',
                                bbox=span["bbox"], page_pt=span.get("page_pt", metadata.get("page_pt")),
                                label=span is label, size=size))
    if not panel.overrides.get("opt_out"):
        fonts = {span["font"] for span in spans}
        for actual in sorted(fonts):
            if not font_matches(style["font_family"], actual):
                checks.append(check("font-family", f'Expected {style["font_family"]}; rendered {actual}.'))
    for dpi in metadata.get("effective_dpi", []):
        if round(dpi) < 300:
            checks.append(check("raster-dpi", f"Image resolution is {dpi:.0f} dpi (minimum 300 dpi)."))
    collisions = metadata.get("text_collisions", [])
    for pair in collisions:
        first, second = pair["texts"]
        checks.append(check("text-overlap", f'“{first[:80]}” overlaps “{second[:80]}”.',
                            boxes=pair["boxes"], page_pt=metadata["page_pt"]))
    remaining = metadata.get("text_collision_count", 0) - len(collisions)
    if remaining > 0:
        checks.append(check("text-overlap", f"{remaining} more possible text overlaps."))
    checks.extend(check("script-path" if "absolute path" in message else
                        "text-fit" if "scaled to fit" in message else "alignment", message)
                  for message in render.get("warnings", []))
    if render.get("state") == "stale":
        checks.append(check("stale", "This panel is out of date."))
    elif render.get("state") == "error":
        checks.append(check("render-error", render.get("error", "Render failed.")))
    return checks


def project_checks(project, renders, presets, resolve):
    result = []
    preset = next((item for item in presets if item["id"] == project.size.preset_id), None)
    if preset and not preset["verified"]:
        result.append({"kind": "preset", "message": f'{preset["name"]} dimensions are provisional.'})
    for panel in project.panels:
        result.extend(panel_checks(panel, renders[panel.id], resolve(project, panel)["style"]))
    return result
