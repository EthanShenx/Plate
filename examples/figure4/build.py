"""Build the synthetic Figure 4 reconstruction as a portable Plate project.

From the repository root: .venv/bin/python -m examples.figure4.build
Add --render to export a PDF and store previews in the bundle.
"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from plate.bundle import save_bundle
from plate.model import FigureSize, Panel, Project
from plate.server import Session

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parents[1] / "output" / "pdf"

# Artboard geometry in mm, measured from the reference's panel arrangement.
PLACEMENTS = {
    "a": ("Mouse perturbation AUC", (2, 8, 62, 31)),
    "b": ("Human perturbation AUC", (66, 8, 63, 31)),
    "c": ("Differential expression overlap", (132, 8, 49, 31)),
    "d": ("Mouse pathway enrichment", (2, 42, 62, 56)),
    "e": ("Human pathway enrichment", (66, 42, 59, 56)),
    "f": ("Paired gene effects", (127, 42, 54, 56)),
    "i": ("Regulator classes", (102, 168, 79, 19)),
    "k": ("Regulator activity shifts", (132, 190, 49, 52)),
}

GROUPS = {
    "g": ("Cell interaction strengths", (2, 101), [
        ("Human healthy", (2, 108, 48, 38)),
        ("Human psoriasis", (51, 108, 48, 38)),
        ("Mouse healthy", (2, 148, 48, 38)),
        ("Mouse IMQ", (51, 148, 48, 38)),
        ("Count legend", (67, 101, 32, 7)),
    ]),
    "h": ("Pathway information flow", (102, 101), [
        ("Human sender", (102, 108, 19, 57)),
        ("Human target", (122, 108, 19, 57)),
        ("Mouse sender", (142, 108, 19, 57)),
        ("Mouse target", (162, 108, 19, 57)),
        ("Condition legend", (139, 101, 42, 7)),
    ]),
    "j": ("Regulatory subnetworks", (2, 190), [
        ("Mouse network", (2, 196, 50, 46)),
        ("Human network", (53, 196, 50, 46)),
        ("Edge legend", (105, 204, 24, 22)),
    ]),
}


def project_source(letter, part=None):
    # Paired panels use the same grammar and carry their own inputs inside the bundle.
    grammar = {"a": "auc", "b": "auc", "d": "enrichment", "e": "enrichment"}.get(letter, letter)
    header = f'"""Panel {letter}. Synthetic fixture for the Figure 4 layout."""\n'
    if grammar != letter:
        header += f"PANEL = {letter!r}\n"
    if part is not None:
        header += f"PART = {part!r}\n"
    return header + (HERE / "panels" / f"{grammar}.py").read_text()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="Render every panel and export the assembled PDF.")
    options = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    bundle = OUTPUT / "figure4-grouped.plate"
    project = Project(
        id="figure4-grouped", name="Figure 4 (synthetic data)",
        size=FigureSize(preset_id="custom", width_mm=183, height_mm=244, minimum_mm=4),
        layout={"mode": "grid", "step_mm": 1, "rects": {
            letter: dict(zip(("x", "y", "w", "h"), box, strict=True))
            for letter, (_, box) in PLACEMENTS.items()
        }},
        style={
            "font_family": "Arial", "font_main_pt": 6, "font_min_pt": 4,
            "axis_title_pt": 5.6, "tick_label_pt": 5.1, "legend_title_pt": 5.3,
            "legend_text_pt": 5, "annotation_pt": 5, "panel_label_pt": 9.5,
            "label_reserve_mm": 0, "label_offset_x_mm": 0, "label_offset_y_mm": 0,
            "line_axis_pt": .42, "background": "none",
        },
        panels=[Panel(id=letter, label=letter, name=name, script=project_source(letter))
                for letter, (name, _) in PLACEMENTS.items()],
    )
    project.panels.insert(0, Panel(
        id="title", type="text", name="Synthetic data label",
        settings={"text": "Figure 4 | Synthetic data"},
        overrides={"font_main_pt": 7.5},
    ))
    project.layout["rects"]["title"] = {"x": 0, "y": 0, "w": 183, "h": 7}
    project.palettes["colors"] = {
        "Healthy": "#ed8b86", "Disease": "#43516e", "Up": "#c9363c", "Down": "#5084a3",
    }
    for letter, (name, (x, y), children) in GROUPS.items():
        members = [Panel(id=letter, type="text", label=letter, name=f"Panel {letter} letter")]
        project.layout["rects"][letter] = dict(x=x, y=y, w=6, h=7)
        for index, (child_name, box) in enumerate(children):
            part = "legend" if index == len(children) - 1 else index
            panel = Panel(id=f"{letter}-{part}", name=child_name, script=project_source(letter, part))
            members.append(panel)
            project.layout["rects"][panel.id] = dict(zip(("x", "y", "w", "h"), box, strict=True))
        project.groups.append({"id": f"group-{letter}", "name": f"{letter}  {name}",
                               "panels": [panel.id for panel in members]})
        project.panels.extend(members)
    project.panels.sort(key=lambda panel: "" if panel.id == "title" else panel.id)
    with TemporaryDirectory(prefix="plate-figure4-") as scratch:
        work = Path(scratch)
        save_bundle(project, work / "source", bundle)
        if options.render:
            session = Session(bundle, work / "open")
            session.refresh([panel.id for panel in session.project.panels])
            state = session.state()
            errors = {key: render.get("stderr") or render.get("error", render["state"])
                      for key, render in state["renders"].items()
                      if render["state"] != "fresh"}
            if errors:
                raise SystemExit(str(errors))
            for check in state["checks"]:
                print(check["panel"], check["kind"], check["message"])
            session.action("/api/save", {"path": str(bundle), "cache": True})
            session.export({"path": str(OUTPUT / "figure4-grouped.pdf"), "format": "pdf"})
    print(bundle)


if __name__ == "__main__":
    main()
