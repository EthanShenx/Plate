"""Advisory checks for rendered and imported panels."""

import re


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
    for span in metadata.get("text", []):
        size = span["size"]
        if size < style["font_min_pt"] - 0.05:
            checks.append(check("font-size", f'{span["text"]} · {size:.2f} pt',
                                bbox=span["bbox"], page_pt=metadata["page_pt"], size=size))
    if not panel.overrides.get("opt_out"):
        fonts = {span["font"] for span in metadata.get("text", [])}
        for actual in sorted(fonts):
            if not font_matches(style["font_family"], actual):
                checks.append(check("font-family", f'Expected {style["font_family"]}; rendered {actual}.'))
    for dpi in metadata.get("effective_dpi", []):
        if dpi < 300:
            checks.append(check("raster-dpi", f"Raster image · {dpi:.0f} dpi (minimum 300 dpi)."))
    checks.extend(check("script-path", message) for message in render.get("warnings", []))
    if render.get("state") == "stale":
        checks.append(check("stale", "Panel needs refresh."))
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
