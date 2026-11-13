const $ = selector => document.querySelector(selector);
let state;
let journals;
let selected = null;
let zoom = 3.1;
let past = [];
let future = [];
let busy = false;
let dragged = null;
const panels = new Map();
const edgeNames = ["left", "right", "top", "bottom"];

async function request(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function field(caption, input) {
  const label = document.createElement("label");
  label.className = "field";
  label.append(caption, input);
  return label;
}

function report(message) {
  $("#status").textContent = message;
}

async function commit(path, body, remember = true) {
  if (busy) return false;
  busy = true;
  try {
    const before = state.project;
    state = await request(path, body);
    if (remember && JSON.stringify(before) !== JSON.stringify(state.project)) {
      past.push(before);
      future = [];
    }
    draw();
    return true;
  } catch (error) { report(error.message); return false; }
  finally { busy = false; }
}

function change(mutate) {
  const project = structuredClone(state.project);
  mutate(project);
  return commit("/api/project", project);
}

function layout(kind, fields = {}) {
  return commit("/api/layout", { kind, panel: selected, ...fields });
}

async function history(from, to) {
  if (!from.length || busy) return;
  const previous = state.project;
  const next = from.pop();
  to.push(previous);
  if (!await commit("/api/project", next, false)) {
    to.pop();
    from.push(next);
    draw();
  }
}

function selectPanel(id) {
  selected = id;
  draw();
}

function button(caption, action) {
  const control = document.createElement("button");
  control.textContent = caption;
  control.onclick = action;
  return control;
}

function numeric(caption, value, onChange, minimum = 0) {
  const input = document.createElement("input");
  Object.assign(input, { type: "number", min: minimum, step: "any", value });
  input.onchange = () => {
    if (input.validity.valid && Number.isFinite(input.valueAsNumber)) onChange(input.valueAsNumber);
  };
  return field(caption, input);
}

function rectangle(node, {x, y, w, h}) {
  Object.assign(node.style, {
    left: `${x * zoom}px`, top: `${y * zoom}px`, width: `${w * zoom}px`, height: `${h * zoom}px`,
  });
}

function dropZone(parent, edge, target, frame = false) {
  const zone = document.createElement("div");
  zone.className = `drop-zone ${edge}${frame ? " frame-zone" : ""}`;
  zone.ondragover = event => {
    if (!dragged || dragged === target) return;
    event.preventDefault();
    zone.classList.add("over");
    event.dataTransfer.dropEffect = "move";
  };
  zone.ondragleave = () => zone.classList.remove("over");
  zone.ondrop = event => {
    event.preventDefault();
    event.stopPropagation();
    const panel = dragged;
    endDrag();
    if (panel && panel !== target) layout("move", { panel, target, edge });
  };
  parent.append(zone);
}

function endDrag() {
  dragged = null;
  $("#frame").classList.remove("dragging");
  document.querySelectorAll(".drop-zone.over,.tile.drag-source")
    .forEach(node => node.classList.remove("over", "drag-source"));
}

function dragPanel(event, id) {
  dragged = id;
  event.dataTransfer.setData("text/plain", id);
  event.dataTransfer.effectAllowed = "move";
  requestAnimationFrame(() => {
    if (!dragged) return;
    $("#frame").classList.add("dragging");
    panels.get(id)?.classList.add("drag-source");
  });
}

function resizeHandle(key, handle) {
  const node = document.createElement("div");
  node.className = `handle ${handle.axis}`;
  node.tabIndex = 0;
  node.setAttribute("role", "separator");
  node.setAttribute("aria-label", "Resize adjoining panels");
  node.setAttribute("aria-orientation", handle.axis === "x" ? "vertical" : "horizontal");
  const vertical = handle.axis === "x";
  const rect = vertical
    ? {x: handle.at, y: handle.start, w: 0, h: handle.length}
    : {x: handle.start, y: handle.at, w: handle.length, h: 0};
  rectangle(node, rect);
  const pointer = event => vertical ? event.clientX : event.clientY;
  node.onpointerdown = event => {
    if (event.button !== 0) return;
    const start = pointer(event);
    const group = [...$("#frame").querySelectorAll(".handle")].filter(
      item => item.dataset.axis === handle.axis && Math.abs(Number(item.dataset.at) - handle.at) < 1e-7
    );
    node.setPointerCapture(event.pointerId);
    node.classList.add("resizing");
    node.onpointermove = move => {
      const delta = pointer(move) - start;
      for (const item of group) {
        item.style.transform = vertical ? `translateX(${delta}px)` : `translateY(${delta}px)`;
      }
    };
    const finish = (end, commitResize) => {
      node.classList.remove("resizing");
      node.onpointermove = null;
      for (const item of group) item.style.transform = "";
      const delta = (pointer(end) - start) / zoom;
      if (commitResize && Math.abs(delta) > 0.1) layout("resize", { handle: key, delta, snap: 5 / zoom });
    };
    node.onpointerup = end => finish(end, true);
    node.onpointercancel = end => finish(end, false);
  };
  node.onkeydown = event => {
    const directions = vertical ? ["ArrowLeft", "ArrowRight"] : ["ArrowUp", "ArrowDown"];
    if (!directions.includes(event.key)) return;
    event.preventDefault();
    layout("resize", { handle: key, delta: (event.shiftKey ? 5 : 1) * (event.key === directions[0] ? -1 : 1) });
  };
  Object.assign(node.dataset, { axis: handle.axis, at: handle.at });
  return node;
}

function drawCanvas() {
  const frame = $("#frame");
  const { project, geometry } = state;
  const { width_mm, height_mm } = project.size;
  frame.style.width = `${width_mm * zoom}px`;
  frame.style.height = `${height_mm * zoom}px`;
  for (const node of frame.querySelectorAll(":scope > :not(.tile)")) node.remove();
  for (const [id, node] of panels) {
    if (!(id in geometry.rects)) { node.remove(); panels.delete(id); }
  }
  for (const panel of project.panels) {
    let tile = panels.get(panel.id);
    if (!tile) {
      tile = document.createElement("div");
      tile.className = "tile";
      tile.tabIndex = 0;
      tile.draggable = true;
      const caption = document.createElement("span");
      caption.className = "tile-caption";
      const preview = document.createElement("img");
      preview.className = "plot-preview";
      preview.alt = "";
      preview.draggable = false;
      const badge = document.createElement("span");
      badge.className = "render-badge";
      tile.append(caption, preview, badge);
      for (const edge of [...edgeNames, "center"]) dropZone(tile, edge, panel.id);
      tile.onclick = () => selectPanel(panel.id);
      tile.onkeydown = event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectPanel(panel.id); }
      };
      tile.ondragstart = event => dragPanel(event, panel.id);
      tile.ondragend = endDrag;
      panels.set(panel.id, tile);
      frame.append(tile);
    }
    tile.classList.toggle("selected", panel.id === selected);
    tile.querySelector(".tile-caption").textContent = panel.name;
    const render = state.renders[panel.id];
    const image = tile.querySelector(".plot-preview");
    const src = render?.key ? `/preview/${render.key}` : "";
    if (src && image.getAttribute("src") !== src) image.src = src;
    image.hidden = !src;
    tile.querySelector(".tile-caption").hidden = !!src;
    const badge = tile.querySelector(".render-badge");
    badge.textContent = render?.state || "";
    badge.dataset.state = render?.state || "";
    rectangle(tile, geometry.rects[panel.id]);
  }
  for (const [key, handle] of Object.entries(geometry.handles)) frame.append(resizeHandle(key, handle));
  for (const edge of edgeNames) dropZone(frame, edge, null, true);
  const journal = journals.find(item => item.id === project.size.preset_id);
  if (journal?.max_height_mm) {
    const guide = document.createElement("div");
    guide.className = "height-guide";
    guide.style.top = `${Math.min(journal.max_height_mm, height_mm) * zoom}px`;
    guide.textContent = `${journal.name} guide · ${journal.max_height_mm} mm`;
    frame.append(guide);
  }
  if (!project.panels.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Add a panel to start your figure.";
    frame.append(empty);
  }
}

function drawPanels() {
  const list = $("#panel-list");
  list.replaceChildren(...state.project.panels.map(panel => {
    const render = state.renders[panel.id];
    const row = button(panel.name, () => selectPanel(panel.id));
    row.className = "panel-row";
    const meta = document.createElement("small");
    meta.textContent = [panel.type === "script-r" ? "R" : "Python", render?.state].filter(Boolean).join(" · ");
    row.append(meta);
    row.classList.toggle("selected", panel.id === selected);
    row.draggable = true;
    row.ondragstart = event => dragPanel(event, panel.id);
    row.ondragend = endDrag;
    row.ondragover = event => { if (dragged && dragged !== panel.id) event.preventDefault(); };
    row.ondrop = event => {
      event.preventDefault();
      const source = dragged;
      endDrag();
      if (!source || source === panel.id) return;
      change(project => {
        const index = project.panels.findIndex(p => p.id === panel.id);
        const [moved] = project.panels.splice(project.panels.findIndex(p => p.id === source), 1);
        project.panels.splice(index, 0, moved);
      });
    };
    return row;
  }));
}

function editPanel(panel, mutate) {
  return change(project => mutate(project.panels.find(item => item.id === panel.id)));
}

function stringField(caption, value, onChange, type = "text") {
  const input = document.createElement("input");
  Object.assign(input, { type, value });
  input.onchange = () => onChange(input.value);
  return field(caption, input);
}

async function refresh(ids) {
  if (busy) return;
  const panels = ids || state.project.panels.filter(
    item => ["stale", "error"].includes(state.renders[item.id]?.state)).map(item => item.id);
  if (!panels.length) return;
  const previous = state.renders;
  state.renders = { ...previous };
  for (const id of panels) state.renders[id] = { ...previous[id], state: "rendering" };
  drawCanvas();
  drawPanels();
  if (!await commit("/api/refresh", { panels }, false)) {
    state.renders = previous;
    drawCanvas();
    drawPanels();
  }
}

function drawPanelInspector(panel) {
  const {x, y, w, h} = state.geometry.rects[panel.id];
  const dimensions = Object.entries({x, y, w, h}).map(([key, value]) =>
    numeric(`${key.toUpperCase()} (mm)`, Number(value.toFixed(5)),
      next => layout("edit", { field: key, value: next }), key.length));
  const locks = ["w", "h"].map(key => {
    const box = document.createElement("input");
    Object.assign(box, { type: "checkbox", checked: key in panel.locks });
    box.onchange = () => layout("lock", { field: key, enabled: box.checked });
    return field(key === "w" ? "Lock width" : "Lock height", box);
  });
  const script = document.createElement("textarea");
  script.rows = 9;
  script.value = panel.script;
  script.spellcheck = false;
  const render = state.renders[panel.id] || {};
  const output = document.createElement("pre");
  output.className = "console";
  output.textContent = [render.error, render.stdout, render.stderr, ...(render.warnings || [])]
    .filter(Boolean).join("\n");
  $("#settings").replaceChildren(...dimensions, ...locks,
    stringField("Interpreter override", panel.interpreter, value => editPanel(panel, p => { p.interpreter = value; })),
    field("Plot script", script),
    button("Refresh panel", async () => {
      if (script.value !== panel.script && !await editPanel(panel, p => { p.script = script.value; })) return;
      refresh([panel.id]);
    }),
    button("Check dependencies", async () => {
      try {
        const info = await request("/api/dependencies", { panel: panel.id });
        output.textContent = info.missing.length ? `Missing ${info.missing.join(", ")}\n${info.install}` :
          `${info.path} · ${info.version}\nRequired packages are available.`;
      } catch (error) { output.textContent = error.message; }
    }),
    output, button("Delete panel", () => layout("delete")));
}

function draw() {
  const { project, bundle } = state;
  const panel = project.panels.find(item => item.id === selected);
  if (!panel) selected = null;
  $("#project-name").value = project.name;
  $("#measure").textContent = `${project.size.width_mm} × ${project.size.height_mm} mm`;
  $("#undo").disabled = !past.length;
  $("#redo").disabled = !future.length;
  $("#inspector-title").textContent = panel ? panel.name : "Figure settings";
  drawCanvas();
  drawPanels();
  report(bundle || "Working copy · Save to create a .plate bundle");
  if (panel) { drawPanelInspector(panel); return; }
  const preset = document.createElement("select");
  for (const journal of journals) {
    for (const width of journal.widths || [null]) {
      const option = new Option(width ? `${journal.name} · ${width} mm` : journal.name,
                                `${journal.id}:${width}`);
      option.disabled = width === null;
      preset.add(option);
    }
  }
  preset.value = `${project.size.preset_id}:${project.size.width_mm}`;
  preset.onchange = () => change(p => {
    const [id, width] = preset.value.split(":");
    Object.assign(p.size, { preset_id: id, width_mm: Number(width) });
  });
  const height = document.createElement("input");
  Object.assign(height, { type: "number", min: "1", step: "0.1", value: project.size.height_mm });
  height.onchange = () => change(p => { if (height.validity.valid) p.size.height_mm = height.valueAsNumber; });
  $("#settings").replaceChildren(field("Journal width", preset), field("Height (mm)", height));
  $("#settings").append(numeric("Minimum panel size (mm)", project.size.minimum_mm,
    value => change(p => { p.size.minimum_mm = value; }), 1),
    stringField("Data root", project.data_root, value => change(p => { p.data_root = value; })),
    numeric("Render timeout (seconds)", project.timeout_s, value => change(p => { p.timeout_s = value; }), 1),
    ...["script-r", "script-py"].map(type =>
      stringField(type === "script-r" ? "Default Rscript" : "Default Python", project.interpreters[type] || "",
        value => change(p => { p.interpreters[type] = value; }))));

}

async function action(name, data = {}) {
  if (busy) return;
  busy = true;
  try {
    state = await request(`/api/${name}`, data);
    if (name === "new" || name === "open") { selected = null; past = []; future = []; }
    draw();
  }
  catch (error) { report(error.message); }
  finally { busy = false; }
}

$("#add").onclick = async () => {
  const type = $("#panel-type").value;
  const name = `${type === "script-r" ? "R" : "Python"} panel`;
  if (await layout("add", { type, name })) selectPanel(state.project.panels.at(-1).id);
};
$("#frame").onclick = event => { if (event.target === $("#frame")) selectPanel(null); };
$("#undo").onclick = () => history(past, future);
$("#redo").onclick = () => history(future, past);
$("#zoom-out").onclick = () => { zoom = Math.max(1, zoom / 1.2); drawCanvas(); };
$("#zoom-in").onclick = () => { zoom = Math.min(20, zoom * 1.2); drawCanvas(); };
document.addEventListener("keydown", event => {
  if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z"
      || event.target.matches("input, textarea, [contenteditable]")) return;
  event.preventDefault();
  if (event.shiftKey) history(future, past);
  else history(past, future);
});

$("#refresh-all").onclick = () => refresh();
document.addEventListener("keydown", event => {
  if (!(event.metaKey || event.ctrlKey) || event.key !== "Enter") return;
  event.preventDefault();
  if (event.shiftKey) refresh();
  else if (selected) refresh([selected]);
});
$("#new").onclick = () => action("new");
$("#open").onclick = () => {
  const path = prompt("Path to a .plate bundle");
  if (path) action("open", { path });
};
$("#save").onclick = () => {
  const path = state.bundle || prompt("Save .plate bundle to this path");
  if (path) action("save", { path });
};
$("#project-name").onchange = event => change(p => { p.name = event.target.value.trim() || "Untitled figure"; });

try {
  [state, journals] = await Promise.all([request("/api/project"), request("/api/presets")]);
  draw();
} catch (error) { report(error.message); }
