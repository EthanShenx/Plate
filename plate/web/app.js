const $ = selector => document.querySelector(selector);
const { createEditor } = await import("/vendor/editor.js").catch(() => ({
  createEditor(parent, language, source, onChange) {
    const input = document.createElement("textarea");
    input.setAttribute("aria-label", "Panel script");
    input.value = source;
    input.oninput = () => onChange(input.value);
    parent.append(input);
    return { replace(value) { input.value = value; }, destroy() { input.remove(); } };
  },
}));
let state;
let editor;
let editorId;
let interpreters = {};
const drafts = new Map();
let journals;
let selected = null;
const CSS_PX_PER_MM = 96 / 25.4;
let zoom = 3.1;
let viewMode = "fit";
let past = [];
let future = [];
let busy = false;
let showChecks = false;
let dragged = null;
let cornerDrag = null;
const panels = new Map();
const typeNames = {"script-py": "Python", "script-r": "R", image: "Image", vector: "Vector", text: "Text", legend: "Legend"};
const isScript = panel => panel.type.startsWith("script-");
const edgeNames = ["left", "right", "top", "bottom"];
const corners = {
  "top-left": ["left", "top"], "top-right": ["right", "top"],
  "bottom-left": ["left", "bottom"], "bottom-right": ["right", "bottom"],
};

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
  if (busy || cornerDrag) return false;
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
  try { mutate(project); } catch (error) { report(error.message); return Promise.resolve(false); }
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
    if (!dragged || dragged === target || (dragged === "new" && edge === "center")) return;
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
    if (panel === "new") {
      if (edge !== "center") addPanel(target, edge);
    } else if (panel && panel !== target) layout("move", { panel, target, edge });
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

function positionPanels(rects) {
  for (const [id, rect] of Object.entries(rects)) {
    const tile = panels.get(id);
    if (tile) rectangle(tile, rect);
  }
}

function cornerHandle(tile, panelId, corner, edges) {
  const node = document.createElement("button");
  node.type = "button";
  node.className = `corner-handle ${corner}`;
  const caption = `Resize from ${corner.replace("-", " ")}`;
  node.setAttribute("aria-label", caption);

  const mobility = () => {
    const shared = state.geometry.panel_edges?.[panelId] || [];
    return edges.map(edge => shared.includes(edge));
  };
  const operation = (dx, dy, snap = 0) => ({ panel: panelId, corner, dx, dy, snap });

  node.onclick = event => event.stopPropagation();
  node.ondragstart = event => event.preventDefault();
  node.onkeydown = event => {
    const step = event.shiftKey ? 5 : 1;
    const [dx, dy] = {
      ArrowLeft: [-step, 0], ArrowRight: [step, 0],
      ArrowUp: [0, -step], ArrowDown: [0, step],
    }[event.key] || [0, 0];
    const [x, y] = mobility();
    if (!(x && dx || y && dy)) return;
    event.preventDefault();
    layout("resize-corner", operation(dx, dy));
  };

  node.onpointerdown = event => {
    if (event.button !== 0 || event.isPrimary === false || busy || cornerDrag) return;
    const [x, y] = mobility();
    if (!x && !y) return;
    event.stopPropagation();
    const frame = $("#frame");
    const start = [event.clientX, event.clientY];
    const scale = zoom;
    const snap = Math.min(20, 5 / scale);
    const movement = point => operation(
      x ? (point.clientX - start[0]) / scale : 0,
      y ? (point.clientY - start[1]) / scale : 0, snap);
    const pointer = event.pointerId;
    const frameClass = "resizing-corner";
    let pending = null;
    let inFlight = false;
    let raf = 0;
    const gesture = {};
    cornerDrag = gesture;
    frame.classList.add(frameClass);
    tile.draggable = false;
    node.setPointerCapture(pointer);

    const schedule = () => {
      if (!inFlight && !raf && pending) raf = requestAnimationFrame(preview);
    };
    async function preview() {
      raf = 0;
      const next = pending;
      pending = null;
      inFlight = true;
      try {
        const result = await request("/api/preview-corner", next);
        if (cornerDrag === gesture) positionPanels(result.rects);
      } catch {
        // The final layout request reports errors and restores the committed geometry.
      } finally {
        inFlight = false;
        if (cornerDrag === gesture) schedule();
      }
    }

    node.onpointermove = move => {
      if (move.pointerId !== pointer) return;
      pending = movement(move);
      schedule();
    };
    const finish = async (end, save) => {
      if (end.pointerId !== pointer || cornerDrag !== gesture) return;
      node.onpointermove = null;
      node.onpointerup = null;
      node.onpointercancel = null;
      node.onlostpointercapture = null;
      cancelAnimationFrame(raf);
      pending = null;
      cornerDrag = null;
      tile.draggable = true;
      const next = movement(end);
      frame.classList.remove(frameClass);
      if (save && (Math.abs(next.dx) > .1 || Math.abs(next.dy) > .1)) {
        if (await layout("resize-corner", next)) return;
      }
      positionPanels(state.geometry.rects);
    };
    node.onpointerup = end => finish(end, true);
    node.onpointercancel = end => finish(end, false);
    node.onlostpointercapture = end => finish(end, false);
  };
  return node;
}

function calibratedScale() {
  const value = Number(state.pixels_per_mm);
  return value > 0 ? value : CSS_PX_PER_MM;
}

function fitScale() {
  const viewport = $(".viewport");
  const {width_mm, height_mm} = state.project.size;
  return Math.max(.1, Math.min((viewport.clientWidth - 56) / width_mm,
                              (viewport.clientHeight - 56) / height_mm));
}

function drawCanvas() {
  if (cornerDrag) return;
  const frame = $("#frame");
  const { project, geometry } = state;
  if (viewMode === "fit") zoom = fitScale();
  else if (viewMode === "actual") zoom = calibratedScale();
  $("#fit-view").setAttribute("aria-pressed", String(viewMode === "fit"));
  $("#actual-size").setAttribute("aria-pressed", String(viewMode === "actual"));
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
      const highlights = document.createElement("div");
      highlights.className = "highlights";
      const label = document.createElement("span");
      label.className = "panel-label";
      tile.append(caption, preview, highlights, label, badge);
      for (const edge of [...edgeNames, "center"]) dropZone(tile, edge, panel.id);
      for (const [corner, edges] of Object.entries(corners)) {
        tile.append(cornerHandle(tile, panel.id, corner, edges));
      }
      tile.onclick = () => selectPanel(panel.id);
      tile.onkeydown = event => {
        if (event.target === tile && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          selectPanel(panel.id);
        }
      };
      tile.ondragstart = event => dragPanel(event, panel.id);
      tile.ondragend = endDrag;
      panels.set(panel.id, tile);
      frame.append(tile);
    }
    tile.classList.toggle("selected", panel.id === selected);
    const shared = geometry.panel_edges?.[panel.id] || [];
    for (const [corner, [horizontal, vertical]] of Object.entries(corners)) {
      const handle = tile.querySelector(`.corner-handle.${corner}`);
      const x = shared.includes(horizontal);
      const y = shared.includes(vertical);
      handle.disabled = !x && !y;
      handle.dataset.movement = x && y ? "both" : x ? "x" : y ? "y" : "fixed";
      handle.title = handle.disabled ? "This corner is fixed by the figure margins" :
        `${handle.getAttribute("aria-label")}${x && y ? "" : x ? " horizontally" : " vertically"}`;
    }
    tile.querySelector(".tile-caption").textContent = panel.name;
    const render = state.renders[panel.id];
    const image = tile.querySelector(".plot-preview");
    const src = render?.key ? `/preview/${render.key}` : "";
    if (src && image.getAttribute("src") !== src) image.src = src;
    image.hidden = !src;
    const rect = geometry.rects[panel.id];
    const content = render?.box || rect;
    const contentTop = (content.y - rect.y) / rect.h * 100;
    image.style.top = `${contentTop}%`;
    image.style.height = `${100 - contentTop}%`;
    const label = tile.querySelector(".panel-label");
    label.textContent = panel.label;
    const style = render.style;
    Object.assign(label.style, {
      top: `${style.label_offset_y_mm * zoom}px`, left: `${style.label_offset_x_mm * zoom}px`,
      fontFamily: style.font_family, fontWeight: style.panel_label_weight,
      fontSize: `${style.panel_label_pt * 25.4 / 72 * zoom}px`,
    });
    tile.querySelector(".tile-caption").hidden = !!src;
    const badge = tile.querySelector(".render-badge");
    badge.textContent = render?.state || "";
    badge.dataset.state = render?.state || "";
    const highlights = state.checks.filter(check => check.panel === panel.id && check.bbox)
      .map(check => {
        const node = document.createElement("span");
        const [x0, y0, x1, y1] = check.bbox;
        const [w, h] = check.page_pt;
        Object.assign(node.style, { left: `${x0 / w * 100}%`, top: `${(check.label ? 0 : contentTop) + y0 / h * (check.label ? 100 : 100 - contentTop)}%`,
          width: `${(x1 - x0) / w * 100}%`, height: `${(y1 - y0) / h * (check.label ? 100 : 100 - contentTop)}%` });
        return node;
      });
    tile.querySelector(".highlights").replaceChildren(...highlights);
    rectangle(tile, geometry.rects[panel.id]);
  }
  for (const [key, handle] of Object.entries(geometry.handles)) frame.append(resizeHandle(key, handle));
  for (const edge of edgeNames) dropZone(frame, edge, null, true);
  const journal = journals.find(item => item.id === project.size.preset_id);
  if (journal?.max_height_mm) {
    const guide = document.createElement("div");
    guide.className = "height-guide";
    guide.classList.toggle("outside", journal.max_height_mm > height_mm);
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
    meta.textContent = [typeNames[panel.type], panel.label, render?.state].filter(Boolean).join(" · ");
    if (panel.type === "vector") meta.textContent += " · original style";
    if (Object.keys(panel.overrides).length) meta.textContent += " · styled locally";
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
      if (!source || source === "new" || source === panel.id) return;
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

function stringField(caption, value, onChange) {
  const input = document.createElement("input");
  Object.assign(input, { type: "text", value });
  input.onchange = () => onChange(input.value);
  return field(caption, input);
}

async function refresh(ids) {
  if (busy || cornerDrag) return;
  const panels = ids || state.project.panels.filter(
    item => ["stale", "error"].includes(state.renders[item.id]?.state)).map(item => item.id);
  if (!panels.length) return;
  for (let size = 0; size !== panels.length;) {
    size = panels.length;
    for (const group of state.project.alignment) {
      if (group.panels.some(id => panels.includes(id))) {
        panels.push(...group.panels.filter(id => !panels.includes(id)));
      }
    }
  }
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

const styleGroups = {
  "Typography": ["font_family", "font_main_pt", "font_min_pt", "axis_title_pt", "tick_label_pt",
    "legend_title_pt", "legend_text_pt", "annotation_pt", "panel_label_pt", "panel_label_weight"],
  "Lines and markers": ["line_data_pt", "line_axis_pt", "tick_length_pt", "tick_width_pt",
    "tick_direction", "marker_size_pt"],
  "Axes": ["spines", "grid", "background"],
  "Spacing": ["margin_mm", "gutter_mm", "label_reserve_mm", "label_offset_x_mm", "label_offset_y_mm",
    "collapse_empty_labels"],
};
const titles = {
  font_main_pt: "Main font (pt)", font_min_pt: "Minimum font (pt)", line_data_pt: "Data stroke (pt)",
  line_axis_pt: "Axis stroke (pt)", label_reserve_mm: "Label reservation (mm)",
  label_offset_x_mm: "Label left offset (mm)", label_offset_y_mm: "Label top offset (mm)",
};

function titleFor(key) {
  const label = titles[key] || key.replace(/_(pt|mm)$/, " ($1)").replaceAll("_", " ");
  return label[0].toUpperCase() + label.slice(1);
}

function section(title, children, open = false) {
  const group = document.createElement("details");
  group.open = open;
  const summary = document.createElement("summary");
  summary.textContent = title;
  group.append(summary, ...children);
  return group;
}

function selectField(caption, values, current, onChange) {
  const select = document.createElement("select");
  for (const [value, name] of values) select.add(new Option(name, value));
  select.value = current ?? "";
  select.onchange = () => onChange(select.value);
  return field(caption, select);
}

function checkField(caption, value, onChange) {
  const control = document.createElement("input");
  Object.assign(control, { type: "checkbox", checked: Boolean(value) });
  control.onchange = () => onChange(control.checked);
  return field(caption, control);
}

function styleField(key, value, update) {
  const fallback = state.style_tokens[key];
  const caption = titleFor(key);
  const options = state.style_options[key];
  if (options) return selectField(caption, options.map(option => [option, option]), value ?? fallback, update);
  if (typeof fallback === "boolean") return checkField(caption, value ?? fallback, update);
  if (key === "font_family") return stringField(caption, value ?? fallback, update);
  const control = document.createElement("input");
  Object.assign(control, { type: "number", step: "any", value: value ?? fallback ?? "",
    min: key.startsWith("label_offset_") ? -100 : 0 });
  if (fallback === null) control.placeholder = "Derived from main and minimum";
  control.onchange = () => {
    if (!control.value && fallback === null) update(null);
    else if (control.validity.valid && Number.isFinite(control.valueAsNumber)) update(control.valueAsNumber);
  };
  return field(caption, control);
}

function downloadJson(name, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function allPalettes() {
  return { ...state.palettes, ...(state.project.palettes.custom || {}) };
}

function paletteChoices() {
  return Object.entries(allPalettes()).map(([id, item]) => [id, item.name + (item.safe ? " · colourblind-safe" : "")]);
}

function drawPaletteInspector() {
  const { palettes } = state.project;
  const active = palettes.active || "okabe-ito";
  const palette = allPalettes()[active];
  const semantic = palettes.colors || {};
  const edit = mutate => change(project => mutate(project.palettes));
  const updatePalette = mutate => edit(record => mutate(record.custom[active]));
  const items = [
    selectField("Palette", paletteChoices(), active, value => edit(p => { p.active = value; })),
  ];
  const swatches = document.createElement("div");
  swatches.className = "swatches";
  for (const color of palette.colors) {
    const sample = document.createElement("span");
    sample.style.background = color;
    sample.title = color;
    swatches.append(sample);
  }
  items.push(swatches, button("Duplicate as custom palette", () => {
    const name = prompt("Palette name", `${palette.name} copy`);
    if (!name?.trim()) return;
    edit(p => {
      const id = `custom-${crypto.randomUUID()}`;
      (p.custom ||= {})[id] = { name: name.trim(), safe: false, colors: [...palette.colors] };
      p.active = id;
    });
  }));
  if (palettes.custom?.[active]) {
    items.push(stringField("Palette name", palette.name, value => updatePalette(p => { p.name = value.trim(); })));
    for (const [index, color] of palette.colors.entries()) {
      const row = document.createElement("div");
      row.className = "inline-fields";
      const move = delta => updatePalette(p => {
        [p.colors[index], p.colors[index + delta]] = [p.colors[index + delta], p.colors[index]];
      });
      const up = button("↑", () => move(-1));
      const down = button("↓", () => move(1));
      up.disabled = index === 0;
      down.disabled = index === palette.colors.length - 1;
      const remove = button("Remove", () => updatePalette(p => p.colors.splice(index, 1)));
      remove.disabled = palette.colors.length === 1;
      row.append(stringField(`Colour ${index + 1}`, color, value => updatePalette(p => { p.colors[index] = value; })),
        up, down, remove);
      items.push(row);
    }
    items.push(button("Add colour", () => updatePalette(p => p.colors.push("#808080"))));
  }
  const importer = document.createElement("input");
  importer.type = "file";
  importer.accept = ".json,application/json";
  importer.hidden = true;
  importer.onchange = async () => {
    try {
      const raw = JSON.parse(await importer.files[0].text());
      if (!Array.isArray(raw.colors) || typeof raw.name !== "string") throw new Error("Expected palette name and colours.");
      await edit(p => {
        const id = `custom-${crypto.randomUUID()}`;
        (p.custom ||= {})[id] = { name: raw.name, colors: raw.colors, safe: raw.safe === true };
        p.active = id;
      });
    } catch (error) { report(error.message); }
  };
  items.push(importer, button("Import palette", () => importer.click()),
    button("Export palette", () => downloadJson("palette.json", palette)));
  const heading = document.createElement("h3");
  heading.textContent = "Semantic colours";
  items.push(heading);
  for (const [key, color] of Object.entries(semantic)) {
    const row = document.createElement("div");
    row.className = "inline-fields";
    row.append(stringField("Group", key, value => edit(p => {
      value = value.trim();
      if (!value || (value !== key && value in p.colors)) throw new Error("Enter a unique group name.");
      p.colors = Object.fromEntries(Object.entries(p.colors).map(([name, hex]) => [name === key ? value : name, hex]));
    })), stringField("Hex", color, value => edit(p => { p.colors[key] = value; })),
    button("Remove", () => edit(p => { delete p.colors[key]; })));
    items.push(row);
  }
  items.push(button("Add group", () => {
    const group = prompt("Semantic group name")?.trim();
    if (!group || Object.hasOwn(semantic, group)) return;
    edit(p => { p.colors = { ...p.colors, [group]: "#808080" }; });
  }));
  return section("Palette and semantic colours", items);
}

function drawOverrides(panel) {
  const keys = Object.keys(panel.overrides).filter(key => key !== "opt_out");
  const controls = [checkField("Use script’s own style", panel.overrides.opt_out,
    value => editPanel(panel, p => {
      if (value) p.overrides.opt_out = true;
      else delete p.overrides.opt_out;
    }))];
  for (const key of keys) {
    let input;
    const set = value => editPanel(panel, p => { p.overrides[key] = value; });
    if (key === "palette") input = selectField("Palette", paletteChoices(), panel.overrides.palette, set);
    else if (key === "colors") input = stringField("Semantic map (JSON)", JSON.stringify(panel.overrides.colors), value => {
      try { set(JSON.parse(value)); } catch (error) { report(error.message); }
    });
    else input = styleField(key, panel.overrides[key], set);
    const row = document.createElement("div");
    row.className = "inline-fields";
    row.append(input, button("Reset", () => editPanel(panel, p => { delete p.overrides[key]; })));
    controls.push(row);
  }
  const available = [...Object.keys(state.style_tokens), "palette", "colors"]
    .filter(key => !key.startsWith("label_offset_") && !Object.hasOwn(panel.overrides, key));
  controls.push(selectField("Add override", [["", "Choose a style token"], ...available.map(key => [key, titleFor(key)])],
    "", key => {
      if (!key) return;
      const value = key === "palette" ? state.project.palettes.active || "okabe-ito" :
        key === "colors" ? {} : (state.project.style[key] ?? state.style_tokens[key]);
      editPanel(panel, p => { p.overrides[key] = value; });
    }));
  return section("Style overrides", controls,
    keys.length > 0 || panel.overrides.opt_out);
}

function nativeInspector(panel) {
  const settings = panel.settings;
  const render = state.renders[panel.id];
  const update = (key, value) => editPanel(panel, p => { p.settings[key] = value; });
  const options = (caption, key, values, fallback) => selectField(caption,
    values.map(value => [value, titleFor(value)]), settings[key] || fallback, value => update(key, value));
  if (panel.type === "text") {
    const text = document.createElement("textarea");
    text.value = settings.text || "";
    text.rows = 6;
    text.onchange = () => update("text", text.value);
    return [field("Text", text), options("Alignment", "align", ["left", "center", "right"], "left"),
      options("Text role", "role", ["main", "annotation"], "main")];
  }
  if (panel.type === "legend") {
    const keys = Object.keys({ ...state.project.palettes.colors, ...panel.overrides.colors });
    const selectedKeys = settings.keys || keys;
    return [options("Direction", "direction", ["vertical", "horizontal"], "vertical"),
      options("Swatch", "swatch", ["patch", "line", "point"], "patch"),
      section("Semantic groups", keys.map(key => checkField(key, selectedKeys.includes(key), include =>
        update("keys", keys.filter(item => item === key ? include : selectedKeys.includes(item))))), true)];
  }
  const asset = document.createElement("p");
  asset.className = "asset-meta";
  const dpi = render.metadata?.effective_dpi?.[0];
  asset.textContent = [settings.filename || "No asset imported", dpi ? `${Math.round(dpi)} effective dpi` : "",
    panel.type === "vector" ? "Original vector style" : "", render.error].filter(Boolean).join(" · ");
  const controls = [asset, button("Import file", () => {
    const path = prompt(panel.type === "vector" ? "Path to a PDF or SVG" : "Path to an image");
    if (path) commit("/api/asset", { panel: panel.id, path });
  })];
  if (panel.type === "image") {
    controls.push(options("Fit", "fit", ["contain", "cover"], "contain"),
      stringField("Crop x, y, w, h (0–1)", (settings.crop || [0, 0, 1, 1]).join(", "), value =>
        update("crop", value.split(",").map(part => Number(part.trim())))));
  }
  return controls;
}

function drawAlignment(panel) {
  const groups = state.project.alignment;
  const others = state.project.panels.filter(item => item.id !== panel.id && isScript(item));
  const controls = [];
  for (const axis of ["row", "column"]) {
    const current = groups.find(group => group.axis === axis && group.panels.includes(panel.id));
    const members = new Set(current?.panels || [panel.id]);
    const options = others.map(item => checkField(item.name, members.has(item.id), checked => {
      if (checked) members.add(item.id);
      else members.delete(item.id);
    }));
    const apply = button(`Set ${axis} lock`, () => change(project => {
      if (members.size < 2) throw new Error("Select another script panel for this lock.");
      project.alignment = project.alignment.filter(group =>
        group.axis !== axis || !group.panels.includes(panel.id));
      project.alignment.push({ axis, panels: [...members] });
    }));
    apply.disabled = !others.length;
    const remove = button(`Remove ${axis} lock`, () => change(project => {
      project.alignment = project.alignment.filter(group =>
        group.axis !== axis || !group.panels.includes(panel.id));
    }));
    controls.push(section(axis === "row" ? "Row · top and bottom" : "Column · left and right",
      [...options, apply, ...(current ? [remove] : [])], Boolean(current)));
  }
  return section("Plot alignment", controls, groups.some(group => group.panels.includes(panel.id)));
}

function drawPanelInspector(panel) {
  const {x, y, w, h} = state.geometry.rects[panel.id];
  const dimensions = Object.entries({x, y, w, h}).map(([key, value]) =>
    numeric(`${key.toUpperCase()} (mm)`, Number(value.toFixed(5)),
      next => layout("edit", { field: key, value: next })));
  const locks = ["w", "h"].map(key => {
    const box = document.createElement("input");
    Object.assign(box, { type: "checkbox", checked: key in panel.locks });
    box.onchange = () => layout("lock", { field: key, enabled: box.checked });
    return field(key === "w" ? "Lock width" : "Lock height", box);
  });
  const basics = [
    stringField("Panel name", panel.name, value => editPanel(panel, p => { p.name = value.trim() || p.name; })),
    stringField("Manual label", panel.label, value => editPanel(panel, p => { p.label = value; })),
    section("Geometry", [...dimensions, ...locks], true),
  ];
  if (!isScript(panel)) {
    $("#settings").replaceChildren(...basics, ...nativeInspector(panel), drawOverrides(panel),
      button("Refresh panel", () => refresh([panel.id])),
      button("Delete panel", () => layout("delete")));
    return;
  }
  $("#settings").replaceChildren(...basics,
    interpreterField("Interpreter override", panel.type, panel.interpreter,
      value => editPanel(panel, p => { p.interpreter = value; })),
    drawAlignment(panel), drawOverrides(panel), button("Delete panel", () => layout("delete")));

}

function interpreterField(caption, type, value, update) {
  const wrapper = stringField(caption, value, update);
  const input = wrapper.querySelector("input");
  const list = document.createElement("datalist");
  list.id = `interpreters-${type}`;
  input.setAttribute("list", list.id);
  for (const path of interpreters[type] || []) list.append(new Option(path, path));
  wrapper.append(list);
  return wrapper;
}

function draftFor(panel) {
  if (!drafts.has(panel.id)) drafts.set(panel.id, { base: panel.script, value: panel.script });
  return drafts.get(panel.id);
}

function reconcileDraft(panel, promptConflict = true) {
  const draft = draftFor(panel);
  if (panel.script === draft.base) return draft;
  if (draft.value === draft.base || draft.value === panel.script) draft.value = panel.script;
  else if (promptConflict && !confirm(`“${panel.name}” changed on disk. Keep your unsaved editor changes? Cancel loads the disk version.`)) {
    draft.value = panel.script;
  } else if (!promptConflict) return draft;
  draft.base = panel.script;
  return draft;
}

function editorStatus(draft) {
  $("#editor-status").textContent = draft.value === draft.base ? "" : "Unsaved edits";
  $("#save-script").disabled = draft.value === draft.base;
}

function drawEditor(panel) {
  const open = panel && isScript(panel);
  $("#script-drawer").hidden = !open;
  $(".stage").classList.toggle("with-editor", Boolean(open));
  if (!open || editorId !== panel.id) {
    editor?.destroy();
    editor = null;
    editorId = null;
  }
  if (!open) return;
  const draft = reconcileDraft(panel);
  if (!editor) {
    editorId = panel.id;
    editor = createEditor($("#script-editor"), panel.type, draft.value, text => {
      draft.value = text;
      editorStatus(draft);
    });
  } else editor.replace(draft.value);
  editorStatus(draft);
  $("#editor-title").textContent = `${typeNames[panel.type]} · ${panel.name}`;
  const render = state.renders[panel.id] || {};
  $("#console").textContent = [render.error, render.stdout, render.stderr, ...(render.warnings || [])]
    .filter(Boolean).join("\n") || "Run the script to see render output.";
}

async function saveDraft(panel) {
  if (busy || cornerDrag) return false;
  const draft = reconcileDraft(panel);
  if (draft.value === draft.base) return true;
  busy = true;
  try {
    while (true) {
      const sent = draft.value;
      const result = await request("/api/script", { panel: panel.id, script: sent, base: draft.base });
      if (!result.conflict) {
        draft.base = sent;
        state = result;
        draw();
        return true;
      }
      panel.script = result.script;
      reconcileDraft(panel);
      if (draft.value === draft.base) {
        state = await request("/api/project");
        draw();
        return true;
      }
    }
  } catch (error) { report(error.message); return false; }
  finally { busy = false; }
}

async function pollScripts() {
  if (busy || !state) return;
  try {
    const result = await request("/api/scripts");
    if (busy || result.id !== state.project.id) return;
    const changed = state.project.panels.some(panel => isScript(panel) && result.scripts[panel.id] !== panel.script);
    if (changed) {
      const latest = await request("/api/project");
      if (busy || latest.project.id !== state.project.id) return;
      state = latest;
      drawEditor(activeScript());
      drawCanvas();
      drawPanels();
      drawChecks();
    }
  } catch { /* The next poll can reconnect after a transient failure. */ }
}

function activeScript() {
  return state.project.panels.find(panel => panel.id === selected && isScript(panel));
}

async function runSelected() {
  const panel = activeScript();
  if (panel && await saveDraft(panel)) refresh([panel.id]);
}

async function findInterpreters() {
  try {
    interpreters = await request("/api/interpreters", { venvs: state.project.interpreters.venvs || [] });
    if (!busy) {
      for (const list of $("#settings").querySelectorAll("datalist")) {
        const paths = interpreters[list.id.replace("interpreters-", "")] || [];
        list.replaceChildren(...paths.map(path => new Option(path, path)));
      }
    }
  } catch (error) { report(error.message); }
}

function drawChecks() {
  $("#show-inspector").setAttribute("aria-pressed", String(!showChecks));
  $("#show-checks").setAttribute("aria-pressed", String(showChecks));
  $("#show-checks").textContent = `Checks${state.checks.length ? ` · ${state.checks.length}` : ""}`;
  $("#settings").hidden = showChecks;
  $("#inspector-title").hidden = showChecks;
  $("#checks").hidden = !showChecks;
  if (!showChecks) return;
  if (!state.checks.length) {
    $("#checks").textContent = "No warnings.";
    return;
  }
  $("#checks").replaceChildren(...state.checks.map(check => {
    const panel = state.project.panels.find(item => item.id === check.panel);
    const row = button(check.message, () => {
      if (!panel) return;
      selectPanel(panel.id);
      panels.get(panel.id)?.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
    row.className = "check-row";
    if (!panel) row.disabled = true;
    else if (panel.id === selected) row.classList.add("selected");
    const title = document.createElement("small");
    title.textContent = panel?.name || "Figure";
    row.prepend(title);
    return row;
  }));
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
  drawEditor(panel);
  drawCanvas();
  drawPanels();
  drawChecks();
  report(bundle || "Working copy · Save to create a .plate bundle");
  const openGroups = new Set([...$("#settings").querySelectorAll("details[open] summary")]
    .map(summary => summary.textContent));
  const previousScope = $("#settings").dataset.scope;
  const scope = panel?.id || "figure";
  $("#settings").dataset.scope = scope;
  const restoreGroups = () => {
    if (previousScope !== scope) return;
    for (const item of $("#settings").querySelectorAll("details")) {
      item.open ||= openGroups.has(item.querySelector("summary").textContent);
    }
  };
  if (panel) { drawPanelInspector(panel); restoreGroups(); return; }
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
  const projectOptions = [
    stringField("Data root", project.data_root, value => change(p => { p.data_root = value; })),
    numeric("Render timeout (seconds)", project.timeout_s, value => change(p => { p.timeout_s = value; }), 1),
    ...["script-r", "script-py"].map(type =>
      interpreterField(type === "script-r" ? "Default Rscript" : "Default Python", type, project.interpreters[type] || "",
        value => change(p => { p.interpreters[type] = value; }))),
    stringField("Extra venv paths (comma separated)", (project.interpreters.venvs || []).join(", "), async value => {
      if (await change(p => { p.interpreters.venvs = value.split(",").map(path => path.trim()).filter(Boolean); })) {
        findInterpreters();
      }
    }),
    button("Detect interpreters", findInterpreters),
    button("Export style JSON", async () => {
      try { downloadJson("plate-style.json", await request("/api/style-json", {})); }
      catch (error) { report(error.message); }
    }),
  ];
  $("#settings").replaceChildren(
    section("Figure size", [field("Journal width", preset), field("Height (mm)", height),
      numeric("Minimum panel size (mm)", project.size.minimum_mm,
        value => change(p => { p.size.minimum_mm = value; }), 1)], true),
    ...Object.entries(styleGroups).map(([name, keys]) => section(name, keys.map(key =>
      styleField(key, project.style[key], value => change(p => { p.style[key] = value; }))))),
    drawPaletteInspector(), section("Runtime", projectOptions));
  restoreGroups();
}

async function action(name, data = {}) {
  if (busy || cornerDrag) return;
  busy = true;
  try {
    state = await request(`/api/${name}`, data);
    if (name === "new" || name === "open") {
      selected = null; past = []; future = []; drafts.clear();
      findInterpreters();
    }
    draw();
    return true;
  }
  catch (error) { report(error.message); return false; }
  finally { busy = false; }
}

async function addPanel(target = selected, edge = "right") {
  const type = $("#panel-type").value;
  const name = `${typeNames[type]} panel`;
  if (await layout("add", { type, name, panel: target, edge })) {
    showChecks = false;
    selectPanel(state.project.panels.at(-1).id);
  }
}
$("#add").onclick = () => addPanel();
$("#add").draggable = true;
$("#add").title = "Click to split the selection, or drag to a target";
$("#add").ondragstart = event => dragPanel(event, "new");
$("#add").ondragend = endDrag;
$("#frame").onclick = event => { if (event.target === $("#frame")) selectPanel(null); };
$("#undo").onclick = () => history(past, future);
$("#redo").onclick = () => history(future, past);
function setView(mode) { viewMode = mode; drawCanvas(); }
$("#fit-view").onclick = () => setView("fit");
$("#actual-size").onclick = () => {
  if (!state.pixels_per_mm) $("#calibrate").click();
  else setView("actual");
};
$("#zoom-out").onclick = () => { zoom = Math.max(.1, zoom / 1.2); setView("custom"); };
$("#zoom-in").onclick = () => { zoom = Math.min(25, zoom * 1.2); setView("custom"); };
new ResizeObserver(() => { if (state && viewMode === "fit") drawCanvas(); }).observe($(".viewport"));
const calibration = $("#calibration-dialog");
const scaleInput = $("#calibration-scale");
scaleInput.oninput = () => {
  $("#calibration-ruler").style.width = `${50 * scaleInput.valueAsNumber}px`;
};
$("#calibrate").onclick = () => {
  scaleInput.value = calibratedScale();
  scaleInput.oninput();
  calibration.showModal();
};
$("#cancel-calibrate").onclick = () => calibration.close();
$("#calibration-form").onsubmit = async event => {
  event.preventDefault();
  try {
    const result = await request("/api/calibrate", { pixels_per_mm: scaleInput.valueAsNumber });
    state.pixels_per_mm = result.pixels_per_mm;
    calibration.close();
    setView("actual");
  } catch (error) { report(error.message); }
};
document.addEventListener("keydown", event => {
  if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z"
      || event.target.matches("input, textarea, [contenteditable]")) return;
  event.preventDefault();
  if (event.shiftKey) history(future, past);
  else history(past, future);
});

$("#show-inspector").onclick = () => { showChecks = false; drawChecks(); };
$("#show-checks").onclick = () => { showChecks = true; drawChecks(); };

const exportDialog = $("#export-dialog");
$("#export-format").onchange = () => { $("#dpi-field").hidden = $("#export-format").value === "pdf"; };
$("#export").onclick = () => {
  if (busy) return;
  const descriptions = { "font-size": "small text", "font-family": "font mismatch", "raster-dpi": "low dpi",
    stale: "stale", "render-error": "render error", preset: "provisional preset", "script-path": "absolute path", alignment: "alignment warning" };
  const counts = {};
  for (const item of state.checks) counts[item.kind] = (counts[item.kind] || 0) + 1;
  $("#export-warnings").textContent = Object.entries(counts)
    .map(([key, count]) => `${count} ${descriptions[key]}`).join(" · ");
  $("#export-path").value = state.bundle.replace(/\.plate$/i, ".pdf");
  $("#export-format").onchange();
  exportDialog.showModal();
};
$("#cancel-export").onclick = () => exportDialog.close();
$("#export-form").onsubmit = async event => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  try {
    const result = await request("/api/export", {
      format: $("#export-format").value, dpi: Number($("#export-dpi").value), path: $("#export-path").value,
    });
    exportDialog.close();
    report(`Exported ${result.path}`);
  } catch (error) { $("#export-warnings").textContent = error.message; }
  finally { submit.disabled = false; }
};
$("#save-script").onclick = () => { const panel = activeScript(); if (panel) saveDraft(panel); };
$("#run-script").onclick = runSelected;
$("#dependencies").onclick = async () => {
  const panel = activeScript();
  if (!panel) return;
  try {
    const info = await request("/api/dependencies", { panel: panel.id });
    $("#console").textContent = info.missing.length ? `Missing ${info.missing.join(", ")}\n${info.install}` :
      `${info.path} · ${info.version}\nRequired packages are available.`;
  } catch (error) { $("#console").textContent = error.message; }
};
$("#reveal-script").onclick = async () => {
  const panel = activeScript();
  if (!panel) return;
  try { report((await request("/api/reveal-script", { panel: panel.id })).path); }
  catch (error) { report(error.message); }
};
async function refreshAll() {
  if (await saveAllDrafts()) refresh();
}
$("#refresh-all").onclick = refreshAll;
document.addEventListener("keydown", event => {
  if (!(event.metaKey || event.ctrlKey) || event.key !== "Enter") return;
  event.preventDefault();
  if (event.shiftKey) refreshAll();
  else if (activeScript()) runSelected();
  else if (selected) refresh([selected]);
});
function canSwitchProject() {
  return ![...drafts.values()].some(draft => draft.value !== draft.base)
    || confirm("Leave this project with unsaved script edits?");
}

$("#project-folder").onclick = async () => {
  try { report((await request("/api/reveal-workspace", {})).path); }
  catch (error) { report(error.message); }
};
$("#new").onclick = () => { if (canSwitchProject()) action("new"); };
$("#open").onclick = () => {
  const path = prompt("Path to a .plate bundle");
  if (path && canSwitchProject()) action("open", { path });
};
async function saveAllDrafts() {
  if (busy) return false;
  for (const panel of state.project.panels.filter(isScript)) {
    const draft = drafts.get(panel.id);
    if (draft && draft.value !== draft.base && !await saveDraft(panel)) return false;
  }
  return true;
}

const saveDialog = $("#save-dialog");
$("#save").onclick = () => {
  if (busy) return;
  $("#bundle-path").value = state.bundle;
  $("#bundle-cache").checked = Boolean(state.keep_cache);
  saveDialog.showModal();
};
$("#cancel-save").onclick = () => saveDialog.close();
$("#save-form").onsubmit = async event => {
  event.preventDefault();
  if (!await saveAllDrafts()) return;
  if (await action("save", { path: $("#bundle-path").value, cache: $("#bundle-cache").checked })) {
    saveDialog.close();
  }
};
$("#project-name").onchange = event => change(p => { p.name = event.target.value.trim() || "Untitled figure"; });

try {
  [state, journals] = await Promise.all([request("/api/project"), request("/api/presets")]);
  draw();
  findInterpreters();
  setInterval(pollScripts, 1000);
} catch (error) { report(error.message); }
