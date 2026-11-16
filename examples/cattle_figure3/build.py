"""Build a synthetic, script-backed recreation of the cattle atlas Figure 3 layout."""

from pathlib import Path
from tempfile import TemporaryDirectory
import sys

from plate.model import FigureSize, Panel, Project
from plate.server import Session

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parents[1] / "output" / "cattle-atlas-figure-3"
PANELS = [
    ("a", "Immune cells across tissues", (1, 1, 68, 117), "a", "plot"),
    ("b", "Triangular correlation heatmap", (72, 1, 110, 109), "b", "plot"),
    ("c", "Myeloid cell embedding", (72, 69.5, 44, 41), "c", "plot"),
    ("c-key", "Cell subtype key", (116.5, 71, 27, 40), "", "key"),
    ("d", "Transcription factor activity", (1, 117, 64, 82), "d", "plot"),
    ("e", "Pseudotime trajectory and inset", (67.5, 117, 56, 51), "e", "plot"),
    ("f", "Proportion of states", (128, 117, 54, 41), "f", "plot"),
    ("g-ribbons", "Cluster connectors", (44, 166, 47, 108), "", "ribbons"),
    ("g-table", "GO enrichment table", (0, 200, 59, 68), "", "table"),
    ("g", "Expression heatmap and dendrogram", (64.05, 168, 60, 100), "g", "plot"),
    ("h", "Marker expression trajectories", (125.9, 168, 56, 103), "h", "plot"),
]
COLORS = {
    "State 1": "#e58227", "State 2": "#0076af", "State 3": "#b93c2a",
    "State 4": "#7c77ae", "State 5": "#1f8050",
    "MA0": "#8ccfbd", "MA1": "#ecaa96", "MA2": "#4f9f61", "MA3": "#e8ac5e",
    "MA4": "#50bde3", "MA5": "#c5da8d", "MO0": "#ba946c", "MO1": "#91529e", "MO2": "#535454",
    "DC0": "#426d86", "DC1": "#d75c61", "DC2": "#dc86b2", "DC3": "#c23a90", "DC4": "#34513e",
    "Cluster 1": "#ad96df", "Cluster 2": "#ed8d85", "Cluster 4": "#84bf42", "Cluster 3": "#db74d4",
}


def make_project():
    common = (HERE / "panels/common.py").read_text()
    rects, panels = {}, []
    for panel_id, name, rect, label, part in PANELS:
        code = (HERE / "panels" / f"{panel_id.split('-')[0]}.py").read_text()
        settings = {"geometry_refs": ["g", "g-table"]} if part == "ribbons" else {}
        panels.append(Panel(id=panel_id, name=name, label=label, settings=settings,
                            script=f"{common}\nPART = {part!r}\n\n{code}"))
        rects[panel_id] = dict(zip(("x", "y", "w", "h"), rect, strict=True))
    native = [
        (Panel(id="state-key", type="legend", name="Shared state legend",
               settings={"direction": "horizontal", "keys": [f"State {i}" for i in range(1, 6)]}),
         (92, 160.5, 66, 6.5)),
        (Panel(id="synthetic", type="text", name="Synthetic data label",
               settings={"text": "Synthetic data · Figure 3 layout study", "align": "left"},
               overrides={"font_main_pt": 5.7}), (1, 272, 100, 5)),
    ]
    for panel, rect in native:
        panels.append(panel)
        rects[panel.id] = dict(zip(("x", "y", "w", "h"), rect, strict=True))
    return Project(
        name="Cattle immune atlas · Figure 3 (synthetic data)",
        size=FigureSize(preset_id="custom", width_mm=182.6, height_mm=277, minimum_mm=4),
        panels=panels,
        layout={"mode": "grid", "step_mm": 1, "rects": rects},
        palettes={"colors": COLORS},
        style={"font_family": "Arial", "font_main_pt": 6.0, "font_min_pt": 4.1,
               "axis_title_pt": 5.7, "tick_label_pt": 5.25, "legend_text_pt": 5.5,
               "annotation_pt": 5.2, "panel_label_pt": 10.5, "label_reserve_mm": 0,
               "label_offset_x_mm": 0, "label_offset_y_mm": 0, "line_axis_pt": .45,
               "tick_length_pt": 1.7, "tick_width_pt": .45, "background": "none"},
        groups=[
            {"id": "c-group", "name": "c · Myeloid cell subtypes", "panels": ["c", "c-key"]},
            {"id": "g-group", "name": "g · Expression and enrichment", "panels": ["g-table", "g"]},
        ],
    )


def main():
    output = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    bundle = output / "cattle-immune-atlas-figure-3-synthetic.plate"
    with TemporaryDirectory(prefix="plate-cattle-atlas-") as scratch:
        workspaces = Path(scratch) / "workspaces"
        session = Session(workspaces=workspaces)
        session.store_project(make_project(), write_scripts=True)
        session.bundle = bundle
        session.refresh_pending()
        state = session.state()
        for panel in state["project"]["panels"]:
            render = state["renders"][panel["id"]]
            print(panel["id"], render["state"], render.get("seconds", ""), flush=True)
            if render["state"] == "error":
                print(render.get("error"), render.get("stderr"), file=sys.stderr)
        if any(render["state"] != "fresh" for render in state["renders"].values()):
            raise SystemExit("Some panels failed.")
        session.save(bundle, cache=True)
        pdf = output / "cattle-immune-atlas-figure-3-synthetic.pdf"
        session.export({"format": "pdf", "path": str(pdf)})
        print(bundle, pdf, sep="\n")
        for check in state["checks"]:
            print(check.get("panel"), check["kind"], check["message"])


if __name__ == "__main__":
    main()
