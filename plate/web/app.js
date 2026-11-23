const $ = selector => document.querySelector(selector);
const desktop = window.webkit?.messageHandlers?.plate;
const HISTORY_LIMIT = 50;
const { createEditor } = await import("/vendor/editor.js").catch(() => ({
  createEditor(parent, language, source, onChange) {
    const input = document.createElement("textarea");
    input.setAttribute("aria-label", "Panel script");
    input.spellcheck = false;
    input.value = source;
    input.oninput = () => onChange(input.value);
    parent.append(input);
    return { replace(value) { input.value = value; }, destroy() { input.remove(); } };
  },
}));
let state;
let editor;
let editorId;
let editorOpen = false;
let hasEditorProject = false;
let library = { projects: [], tabs: [], active: null };
const figureViews = new Map();
let switchingFigure = false;
let scriptSaveTimer;
let idleScriptSave;
let projectRename;
let renderLibrary;
let libraryLoad = 0;
let interpreters = {};
const drafts = new Map();
let journals;
let selected = null;
let selectedGroup = null;
const multiSelection = new Set();
let selectedCheck = null;
const CSS_PX_PER_MM = 96 / 25.4;
let zoom = 3.1;
let viewMode = "fit";
let past = [];
let future = [];
let busy = false;
let pendingChange;
let automaticRefresh;
let refreshTimer;
let pollTimer;
let polling = false;
let desktopVisible = true;
let showChecks = false;
let dragged = null;
let draggedType = null;
let panelGesture = null;
const panels = new Map();
const typeNames = {"script-py": "Python", "script-r": "R", image: "Image", vector: "Vector", text: "Text", legend: "Legend"};
const typeIcons = {"script-py": "code", "script-r": "code", image: "image", vector: "vector", text: "text", legend: "legend"};
const inspectorIcons = {
  "Artboard": "figure", "Figure style": "sliders", "Project": "folder",
  "Typography": "text", "Lines and markers": "line-chart", "Axes": "axes",
  "Spacing": "ruler", "Colours": "palette", "Advanced": "gear",
};
const renderLabels = { stale: "Out of date", rendering: "Rendering…", error: "Render failed" };
const isScript = panel => panel.type.startsWith("script-");
const corners = {
  "top-left": ["left", "top"], "top-right": ["right", "top"],
  "bottom-left": ["left", "bottom"], "bottom-right": ["right", "bottom"],
};

function renderFailure(render) {
  if (render?.state !== "error") return "";
  const error = render.error || renderLabels.error;
  const detail = render.stderr?.trim().split("\n").at(-1)?.trim();
  return error.startsWith("Plot process exited") && detail ? `${error} ${detail}` : error;
}

function drawRenderFailure() {
  const message = renderFailure(state.renders[selected]);
  const failure = $("#render-failure");
  if (failure.textContent !== message) failure.textContent = message;
  failure.hidden = !message;
}

async function request(path, body, keepalive = false) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {
      "Content-Type": "application/json",
      ...(state ? { "X-Plate-Workspace": state.workspace_id } : {}),
    }, body: JSON.stringify(body), keepalive,
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || response.statusText);
    error.exportIssues = data.export_issues;
    throw error;
  }
  return data;
}

function field(caption, input) {
  const label = document.createElement("label");
  label.className = "field";
  if (input.type === "checkbox") {
    label.classList.add("checkbox");
    label.append(input, caption);
  } else {
    label.append(caption, input);
  }
  input.name ||= caption.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-$/, "");
  input.autocomplete = "off";
  return label;
}

function report(message) {
  const status = $("#status");
  status.textContent = message;
  status.title = message;
}

async function commit(path, body, remember = true) {
  if (!state || busy || panelGesture) return false;
  busy = true;
  try {
    const before = state.project;
    state = await request(path, body);
    if (remember && JSON.stringify(before) !== JSON.stringify(state.project)) {
      past.push(before);
      if (past.length > HISTORY_LIMIT) past.shift();
      future = [];
    }
    draw();
    scheduleRefresh();
    return true;
  } catch (error) { report(error.message); return false; }
  finally { busy = false; }
}

function change(mutate) {
  if (pendingChange) return pendingChange.then(() => change(mutate));
  if (automaticRefresh) return automaticRefresh.then(() => change(mutate));
  const project = structuredClone(state.project);
  try { mutate(project); } catch (error) { report(error.message); return Promise.resolve(false); }
  pendingChange = commit("/api/project", project).finally(() => { pendingChange = null; });
  return pendingChange;
}

async function layout(kind, fields = {}) {
  const body = { kind, panel: selected, ...fields };
  if (automaticRefresh) await automaticRefresh;
  return commit("/api/layout", body);
}

async function history(from, to) {
  if (automaticRefresh) await automaticRefresh;
  if (!from.length || busy || panelGesture) return;
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
  if (!state) return;
  selectedGroup = null;
  multiSelection.clear();
  selectedCheck = null;
  if (id !== selected) editorOpen = false;
  selected = id;
  draw(false);
}

function selectGroup(group) {
  selected = null;
  editorOpen = false;
  showChecks = false;
  selectedCheck = null;
  selectedGroup = group.id;
  multiSelection.clear();
  draw(false);
}

function selectedPanelIds() {
  if (selected) return new Set([selected]);
  const group = state.project.groups?.find(item => item.id === selectedGroup);
  return new Set(group?.panels || multiSelection);
}

function selectPanels(ids) {
  showChecks = false;
  if (ids.size < 2) {
    selectPanel(ids.values().next().value ?? null);
    return;
  }
  selected = null;
  selectedGroup = null;
  selectedCheck = null;
  editorOpen = false;
  multiSelection.clear();
  for (const id of ids) multiSelection.add(id);
  draw(false);
}

function toggleSelection(ids) {
  const selection = selectedPanelIds();
  const remove = ids.every(id => selection.has(id));
  for (const id of ids) {
    if (remove) selection.delete(id);
    else selection.add(id);
  }
  selectPanels(selection);
}

function canGroupSelection() {
  return multiSelection.size > 1 &&
    !state.project.groups?.some(group => group.panels.some(id => multiSelection.has(id)));
}

function groupBounds(rects) {
  const x = Math.min(...rects.map(rect => rect.x));
  const y = Math.min(...rects.map(rect => rect.y));
  return {x, y, w: Math.max(...rects.map(rect => rect.x + rect.w)) - x,
          h: Math.max(...rects.map(rect => rect.y + rect.h)) - y};
}

function button(caption, action) {
  const control = document.createElement("button");
  control.type = "button";
  control.textContent = caption;
  control.onclick = action;
  return control;
}

function icon(name) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  node.setAttribute("class", "icon");
  node.setAttribute("aria-hidden", "true");
  const glyph = document.createElementNS(node.namespaceURI, "use");
  glyph.setAttribute("href", `./icons.svg#${name}`);
  node.append(glyph);
  return node;
}

function numeric(caption, value, onChange, minimum = 0, maximum) {
  const input = document.createElement("input");
  Object.assign(input, { type: "number", min: minimum, step: "any", value: value ?? "" });
  if (maximum !== undefined) input.max = maximum;
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

function endDrag() {
  if (draggedType) $("#panel-types").hidePopover();
  dragged = null;
  draggedType = null;
  $("#frame").classList.remove("placing-panel");
}

function startListDrag(event, id, type = null) {
  if (busy || panelGesture) {
    event.preventDefault();
    return;
  }
  dragged = id;
  draggedType = type;
  event.dataTransfer.setData("text/plain", type || id);
  event.dataTransfer.effectAllowed = type ? "copy" : "move";
  if (type) $("#frame").classList.add("placing-panel");
}

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const cleanMm = value => Number(value.toFixed(8));

function snapped(value, low, high) {
  const step = state.geometry.grid_step;
  const gridLine = clamp(Math.round(value / step) * step,
    Math.ceil(low / step) * step, Math.floor(high / step) * step);
  const bounded = clamp(value, low, high);
  if (bounded === low || bounded === high || gridLine < low || gridLine > high) return bounded;
  return gridLine;
}

function panelPlacement(rect, locks, edges, dx, dy, minimums = {}) {
  const result = { ...rect };
  const {width_mm, height_mm, minimum_mm} = state.project.size;
  for (const [axis, dim, delta, span, leading] of [
    ["x", "w", dx, width_mm, "left"], ["y", "h", dy, height_mm, "top"],
  ]) {
    if (!delta) continue;
    if (!edges) {
      result[axis] = cleanMm(snapped(rect[axis] + delta, 0, span - rect[dim]));
    } else if (!(dim in locks)) {
      const isLeading = edges.includes(leading);
      const far = rect[axis] + rect[dim];
      const minimum = minimums[dim] ?? minimum_mm;
      if (isLeading) {
        result[axis] = cleanMm(snapped(rect[axis] + delta, 0, far - minimum));
        result[dim] = cleanMm(far - result[axis]);
      } else {
        result[dim] = cleanMm(snapped(far + delta, rect[axis] + minimum, span) - rect[axis]);
      }
    }
  }
  return result;
}

function selectionLayout(ids) {
  const entries = [...ids].map(id => [id, state.geometry.rects[id]]);
  const rects = entries.map(([, rect]) => rect);
  const bounds = rects.length > 1 ? groupBounds(rects) : rects[0];
  const locks = {};
  const minimums = {};
  const minimum = state.project.size.minimum_mm;
  for (const dim of ["w", "h"]) {
    if (state.project.panels.some(panel => ids.has(panel.id) && dim in panel.locks)) locks[dim] = true;
    const smallest = Math.min(...rects.map(rect => rect[dim]));
    minimums[dim] = Math.min(bounds[dim], minimum * (bounds[dim] / smallest));
  }
  return { entries, bounds, locks, minimums };
}

function transformRect(rect, from, to) {
  const result = { ...rect };
  for (const [axis, dim] of [["x", "w"], ["y", "h"]]) {
    if (from[axis] === to[axis] && from[dim] === to[dim]) continue;
    const scale = to[dim] / from[dim];
    result[axis] = cleanMm(to[axis] + (rect[axis] - from[axis]) * scale);
    if (from[dim] !== to[dim]) result[dim] = cleanMm(rect[dim] * scale);
  }
  return result;
}

function storeSelectionBounds(project, { entries, bounds }, rect) {
  for (const [id, original] of entries) project.layout.rects[id] = transformRect(original, bounds, rect);
}

function applySelectionBounds(target, rect) {
  const { entries, bounds } = target;
  if (!Object.keys(rect).some(key => rect[key] !== bounds[key])) return false;
  if (entries.length === 1) return layout("place", { panel: entries[0][0], rect });
  return change(project => storeSelectionBounds(project, target, rect));
}

function trackPanelGesture(event, move, finish) {
  const handle = event.currentTarget;
  const pointer = event.pointerId;
  const gesture = {};
  panelGesture = gesture;
  handle.setPointerCapture(pointer);

  const update = point => { if (point.pointerId === pointer) move(point); };
  const end = point => {
    if (point.pointerId !== pointer || panelGesture !== gesture) return;
    panelGesture = null;
    handle.removeEventListener("pointermove", update);
    window.removeEventListener("keydown", cancel);
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) handle.removeEventListener(type, end);
    finish(point.type === "pointerup" ? point : null);
  };
  const cancel = key => {
    if (key.key === "Escape" && handle.hasPointerCapture(pointer)) {
      key.preventDefault();
      handle.releasePointerCapture(pointer);
      end({ pointerId: pointer, type: "pointercancel" });
    }
  };
  handle.addEventListener("pointermove", update);
  window.addEventListener("keydown", cancel);
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) handle.addEventListener(type, end);
}

function resizeKeys(event, id, edges = null) {
  const direction = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
  if (!direction || event.altKey || event.metaKey || event.ctrlKey || (busy && !automaticRefresh) || panelGesture) return;
  event.preventDefault();
  const step = state.geometry.grid_step * (event.shiftKey ? 5 : 1);
  const selection = selectedPanelIds();
  const target = selectionLayout(id === null || !edges && selection.has(id) ? selection : new Set([id]));
  const rect = panelPlacement(target.bounds, target.locks, edges, direction[0] * step, direction[1] * step,
    target.minimums);
  applySelectionBounds(target, rect);
}

function startPanelGesture(event, id, edges = null) {
  if (event.button !== 0 || !event.isPrimary || (busy && !automaticRefresh) || panelGesture || draggedType) return;
  event.stopPropagation();
  const tile = panels.get(id);
  if (event.shiftKey && !edges) {
    event.preventDefault();
    tile.focus({ preventScroll: true });
    toggleSelection([id]);
    return;
  }
  const selection = selectedPanelIds();
  if (id !== null && !selection.has(id)) {
    showChecks = false;
    selectPanel(id);
  } else if (showChecks) {
    showChecks = false;
    drawChecks();
  }
  const start = [event.clientX, event.clientY];
  const scale = zoom;
  const canvas = $("#frame");
  const initialFrame = canvas.getBoundingClientRect();
  const target = selectionLayout(id === null || !edges && selection.has(id) ? selection : new Set([id]));
  const { entries, bounds, locks, minimums } = target;
  const multiple = entries.length > 1;
  let moved = false;
  function placement(point) {
    const frame = canvas.getBoundingClientRect();
    const dx = point.clientX - start[0] - (frame.left - initialFrame.left);
    const dy = point.clientY - start[1] - (frame.top - initialFrame.top);
    if (!moved && Math.hypot(dx, dy) < 4) return bounds;
    moved = true;
    canvas.classList.add("editing-panel");
    tile?.classList.toggle("moving-panel", !multiple);
    return panelPlacement(bounds, locks, edges, dx / scale, dy / scale, minimums);
  }
  const move = point => {
    const rect = placement(point);
    for (const [member, original] of entries) {
      rectangle(panels.get(member), multiple ? transformRect(original, bounds, rect) : rect);
    }
    if (multiple) rectangle($("#group-outline"), rect);
    rectangle($("#panel-handles"), rect);
  };
  const finish = async point => {
    const rect = point ? placement(point) : bounds;
    canvas.classList.remove("editing-panel");
    tile?.classList.remove("moving-panel");
    if (!await applySelectionBounds(target, rect)) drawCanvas();
  };
  trackPanelGesture(event, move, finish);
}

function startMarquee(event) {
  if (!state || !event.isPrimary || event.button !== 0 || event.pointerType === "touch" ||
      (event.target !== frame && event.target !== viewport) || panelGesture || dragged || draggedType) return;
  event.preventDefault();
  viewport.focus({ preventScroll: true });
  const marquee = $("#selection-marquee");
  const { width_mm, height_mm } = state.project.size;
  const artboardPoint = point => {
    const board = frame.getBoundingClientRect();
    return {
      x: clamp((point.clientX - board.left) / zoom, 0, width_mm),
      y: clamp((point.clientY - board.top) / zoom, 0, height_mm),
    };
  };
  const origin = artboardPoint(event);
  const additive = event.shiftKey;
  const previous = selectedPanelIds();
  let moved = false;
  let hits = new Set();

  function update(point) {
    if (!moved && Math.hypot(point.clientX - event.clientX, point.clientY - event.clientY) < 4) return;
    moved = true;
    const corner = artboardPoint(point);
    const x = Math.min(origin.x, corner.x);
    const y = Math.min(origin.y, corner.y);
    const right = Math.max(origin.x, corner.x);
    const bottom = Math.max(origin.y, corner.y);
    hits = additive ? new Set(previous) : new Set();
    if (right > x && bottom > y) {
      for (const [id, rect] of Object.entries(state.geometry.rects)) {
        if (rect.x < right && rect.x + rect.w > x && rect.y < bottom && rect.y + rect.h > y) hits.add(id);
      }
    }
    frame.classList.add("selecting-panels");
    rectangle(marquee, { x, y, w: right - x, h: bottom - y });
    marquee.hidden = false;
    drawCanvasSelection(hits);
  }

  trackPanelGesture(event, update, point => {
    if (point) update(point);
    frame.classList.remove("selecting-panels");
    marquee.hidden = true;
    if (point && (moved || !additive)) selectPanels(hits);
    else drawCanvas();
  });
}

function cornerHandle(id, corner, edges) {
  const node = button("", event => event.stopPropagation());
  node.className = `corner-handle ${corner}`;
  node.setAttribute("aria-label", `Resize ${id === null ? "selection " : ""}from ${corner.replace("-", " ")}`);
  node.onkeydown = event => resizeKeys(event, id, edges);
  node.onpointerdown = event => startPanelGesture(event, id, edges);
  return node;
}

function drawHandles(selection) {
  const layer = $("#panel-handles");
  const id = selection.size === 1 ? selection.values().next().value : null;
  const outline = $("#group-outline");
  outline.hidden = selection.size < 2;
  layer.hidden = !selection.size;
  if (!selection.size) return;
  const { bounds, locks } = selectionLayout(selection);
  if (layer.dataset.panel !== (id ?? "")) {
    layer.dataset.panel = id ?? "";
    layer.replaceChildren(...Object.entries(corners).map(([corner, edges]) =>
      cornerHandle(id, corner, edges)));
  }
  const x = !("w" in locks);
  const y = !("h" in locks);
  for (const handle of layer.children) {
    handle.disabled = !x && !y;
    handle.dataset.movement = x && y ? "both" : x ? "x" : y ? "y" : "fixed";
  }
  rectangle(layer, bounds);
  if (!outline.hidden) rectangle(outline, bounds);
}

function fitScale() {
  const viewport = $(".viewport");
  const {width_mm, height_mm} = state.project.size;
  const padding = parseFloat(getComputedStyle(viewport).paddingInlineStart) * 2;
  const horizontal = (viewport.clientWidth - padding) / width_mm;
  const vertical = (viewport.clientHeight - padding) / height_mm;
  return Math.max(.1, viewMode === "width" ? horizontal : Math.min(horizontal, vertical));
}

function drawCanvasSelection(selection) {
  for (const [id, tile] of panels) {
    tile.classList.toggle("selected", selection.has(id));
    tile.setAttribute("aria-pressed", String(selection.has(id)));
  }
}

let hitSample;

function panelHasInk(tile, x, y) {
  const label = tile.querySelector(".panel-label");
  const bounds = label.getBoundingClientRect();
  if (label.textContent && x >= bounds.left && x < bounds.right && y >= bounds.top && y < bounds.bottom) return true;

  const preview = tile.querySelector(".plot-preview");
  if (preview.hidden || !preview.complete || !preview.naturalWidth) return true;
  const {left, top, width, height} = preview.getBoundingClientRect();
  const sourceWidth = preview.naturalWidth;
  const sourceHeight = preview.naturalHeight;
  const scale = Math.min(width / sourceWidth, height / sourceHeight);
  if (!scale) return false;
  const sx = Math.floor((x - left - (width - sourceWidth * scale) / 2) / scale);
  const sy = Math.floor((y - top - (height - sourceHeight * scale) / 2) / scale);
  if (sx < 0 || sy < 0 || sx >= sourceWidth || sy >= sourceHeight) return false;

  if (!hitSample) {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    hitSample = canvas.getContext("2d", {willReadFrequently: true});
    if (!hitSample) return true;
  }
  hitSample.clearRect(0, 0, 1, 1);
  // Draw at the density-corrected size. A source crop would use the encoded
  // pixels of the selected srcset candidate in some browsers.
  hitSample.drawImage(preview, -sx, -sy, sourceWidth, sourceHeight);
  return hitSample.getImageData(0, 0, 1, 1).data[3] > 12;
}

function panelAtPointer(event, fallback) {
  const {clientX, clientY} = event;
  const layers = document.elementsFromPoint(clientX, clientY).filter(node => node.matches(".tile[data-panel]"));
  if (layers.length < 2) return fallback;
  return layers.find(tile => panelHasInk(tile, clientX, clientY))?.dataset.panel ?? fallback;
}

function drawCanvas() {
  if (panelGesture) return;
  const frame = $("#frame");
  const { project, geometry } = state;
  const selection = selectedPanelIds();
  if (viewMode === "fit" || viewMode === "width") zoom = fitScale();
  else if (viewMode === "actual") zoom = CSS_PX_PER_MM;
  $("#fit-view").setAttribute("aria-pressed", String(viewMode === "fit"));
  $("#fit-width").setAttribute("aria-pressed", String(viewMode === "width"));
  $("#actual-size").setAttribute("aria-pressed", String(viewMode === "actual"));
  const { width_mm, height_mm } = project.size;
  frame.style.setProperty("--grid-step", `${geometry.grid_step * zoom}px`);
  frame.style.setProperty("--active-panel-order", project.panels.length + 2);
  frame.style.width = `${width_mm * zoom}px`;
  frame.style.height = `${height_mm * zoom}px`;
  frame.querySelector(".height-guide")?.remove();
  for (const [id, node] of panels) {
    if (!(id in geometry.rects)) { node.remove(); panels.delete(id); }
  }
  for (const [index, panel] of project.panels.entries()) {
    let tile = panels.get(panel.id);
    if (!tile) {
      tile = document.createElement("div");
      tile.className = "tile";
      tile.tabIndex = 0;
      tile.setAttribute("role", "button");
      tile.dataset.panel = panel.id;
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
      tile.ondblclick = event => {
        const id = panelAtPointer(event, panel.id);
        if (!event.shiftKey && isScript(state.project.panels.find(item => item.id === id))) openEditor(id);
      };
      tile.onpointerdown = event => {
        if (event.button !== 0 || !event.isPrimary) return;
        const id = panelAtPointer(event, panel.id);
        if (id !== panel.id) {
          event.preventDefault();
          panels.get(id).focus({preventScroll: true});
        }
        startPanelGesture(event, id);
      };
      tile.onkeydown = event => {
        if (event.target !== tile) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (event.shiftKey) toggleSelection([panel.id]);
          else {
            showChecks = false;
            selectPanel(panel.id);
          }
        } else resizeKeys(event, panel.id);
      };
      panels.set(panel.id, tile);
      frame.append(tile);
    }
    tile.setAttribute("aria-label", panel.name);
    tile.style.setProperty("--panel-order", index + 1);
    tile.querySelector(".tile-caption").textContent = panel.name;
    const render = state.renders[panel.id];
    const image = tile.querySelector(".plot-preview");
    const src = render?.key ? `/preview/${state.workspace_id}/${render.key}` : "";
    if (src && image.getAttribute("src") !== src) image.src = src;
    image.hidden = !src;
    const rect = geometry.rects[panel.id];
    image.width = Math.round(rect.w * zoom);
    image.height = Math.round(rect.h * zoom);
    const content = render?.box || rect;
    const contentTop = (content.y - rect.y) / rect.h * 100;
    const page = render?.metadata?.page_pt;
    const scale = page ? Math.min(content.w / page[0], content.h / page[1]) : 0;
    const previewWidth = page ? Math.max(1, Math.round(page[0] * scale * zoom)) : 0;
    if (src && page) {
      image.sizes = `${previewWidth}px`;
      // Match the server's raster budget even for unusually large panels.
      const pixelDpi = Math.max(1, Math.floor(72 * Math.sqrt(12000000 / (page[0] * page[1]))));
      const widths = new Set();
      image.srcset = [130, 260, 520, 1040].map(dpi => {
        const width = Math.ceil(page[0] * Math.min(dpi, pixelDpi) / 72);
        if (widths.has(width)) return "";
        widths.add(width);
        return `${src}${dpi === 130 ? "" : `?dpi=${dpi}`} ${width}w`;
      }).filter(Boolean).join(", ");
    } else image.removeAttribute("srcset");
    image.style.top = `${contentTop}%`;
    image.style.height = `${100 - contentTop}%`;
    const label = tile.querySelector(".panel-label");
    label.textContent = panel.label;
    if (render.label_metadata) {
      const style = render.style;
      const {bbox: [x, y], size} = render.label_metadata;
      const pxPerPoint = 25.4 / 72 * zoom;
      Object.assign(label.style, {
        left: `${x * pxPerPoint}px`, top: `${y * pxPerPoint}px`,
        fontFamily: style.font_family, fontWeight: style.panel_label_weight,
        fontSize: `${size * pxPerPoint}px`,
      });
    }
    tile.querySelector(".tile-caption").hidden = !!src;
    const badge = tile.querySelector(".render-badge");
    badge.textContent = renderLabels[render?.state] || "";
    badge.hidden = !badge.textContent;
    badge.dataset.state = render?.state || "";
    const description = renderFailure(render);
    if (description) {
      tile.title = description;
      tile.setAttribute("aria-description", description);
    } else {
      tile.removeAttribute("title");
      tile.removeAttribute("aria-description");
    }
    const highlights = state.checks.filter(check => check.panel === panel.id &&
      (check.bbox || (check.boxes && check === selectedCheck)))
      .flatMap(check => (check.boxes || [check.bbox]).map(box => {
        const node = document.createElement("span");
        const [x0, y0, x1, y1] = box;
        const [w, h] = check.page_pt;
        const factor = check.label ? rect.w / w : scale;
        const dx = check.label ? 0 : (content.w - w*factor) / 2;
        const dy = check.label ? 0 : content.y - rect.y + (content.h - h*factor) / 2;
        Object.assign(node.style, {left: `${(dx + x0*factor) / rect.w * 100}%`,
          top: `${(dy + y0*factor) / rect.h * 100}%`,
          width: `${(x1-x0)*factor / rect.w * 100}%`, height: `${(y1-y0)*factor / rect.h * 100}%`});
        return node;
      }));
    tile.querySelector(".highlights").replaceChildren(...highlights);
    rectangle(tile, geometry.rects[panel.id]);
  }
  drawCanvasSelection(selection);
  drawHandles(selection);
  const journal = journals.find(item => item.id === project.size.preset_id);
  if (journal?.max_height_mm) {
    const guide = document.createElement("div");
    guide.className = "height-guide";
    guide.classList.toggle("outside", journal.max_height_mm > height_mm);
    guide.style.top = `${Math.min(journal.max_height_mm, height_mm) * zoom}px`;
    guide.textContent = `${journal.name} limit: ${journal.max_height_mm} mm`;
    frame.append(guide);
  }
  $("#empty-canvas").hidden = Boolean(project.panels.length);
}

function drawPanels() {
  const list = $("#panel-list");
  const focused = list.contains(document.activeElement) && document.activeElement;
  const selection = selectedPanelIds();
  $("#figure-settings").setAttribute("aria-pressed", String(!selection.size));
  $("#group-panels").hidden = !canGroupSelection();
  const rows = new Map(state.project.panels.map(panel => {
    const render = state.renders[panel.id];
    const row = button("", event => {
      showChecks = false;
      if (event.shiftKey) toggleSelection([panel.id]);
      else selectPanel(panel.id);
    });
    row.className = "panel-row";
    row.dataset.panel = panel.id;
    row.setAttribute("aria-label", panel.name);
    row.setAttribute("aria-pressed", String(selection.has(panel.id)));
    row.append(icon(typeIcons[panel.type]));
    const name = document.createElement("span");
    name.className = "panel-name";
    name.textContent = panel.name;
    if (panel.label) {
      const label = document.createElement("span");
      label.className = "panel-letter";
      label.textContent = panel.label;
      row.append(label);
    }
    row.append(name);
    if (renderLabels[render?.state]) {
      const status = document.createElement("span");
      status.className = "panel-state";
      status.dataset.state = render.state;
      status.textContent = render.state === "rendering" ? "…" : "!";
      status.title = renderFailure(render) || renderLabels[render.state];
      status.setAttribute("aria-hidden", "true");
      row.setAttribute("aria-description", status.title);
      row.append(status);
    }
    row.draggable = true;
    row.ondragstart = event => startListDrag(event, panel.id);
    row.ondragend = endDrag;
    row.ondragover = event => { if (!draggedType && dragged && dragged !== panel.id) event.preventDefault(); };
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
    return [panel.id, row];
  }));
  const sections = new Map();
  for (const group of state.project.groups || []) {
    const region = document.createElement("div");
    region.className = "panel-group";
    const header = button(group.name, event => {
      if (event.shiftKey) toggleSelection(group.panels);
      else selectGroup(group);
    });
    header.className = "panel-row group-row";
    header.dataset.group = group.id;
    header.setAttribute("aria-pressed", String(group.panels.every(id => selection.has(id))));
    region.append(header, ...[...rows].filter(([id]) => group.panels.includes(id)).map(([, row]) => row));
    for (const id of group.panels) sections.set(id, region);
  }
  list.replaceChildren(...new Set([...rows].map(([id, row]) => sections.get(id) || row)));
  for (const key of ["panel", "group"]) {
    if (focused?.dataset?.[key]) list.querySelector(`[data-${key}="${CSS.escape(focused.dataset[key])}"]`)?.focus({ preventScroll: true });
  }
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

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  if (!workspaceVisible() || !stalePanels().length) return;
  refreshTimer = setTimeout(() => {
    if (!workspaceVisible()) return;
    if (busy || panelGesture || dragged || draggedType) {
      scheduleRefresh();
      return;
    }
    const ids = stalePanels();
    if (!ids.length) return;
    automaticRefresh = refresh(ids).finally(() => { automaticRefresh = null; });
  }, 350);
}

function stalePanels() {
  return state.project.panels.filter(panel => state.renders[panel.id]?.state === "stale").map(panel => panel.id);
}

function drawRenderState() {
  drawEditor(activeScript());
  drawCanvas();
  drawPanels();
  drawChecks();
  syncRefresh();
}

async function refresh(ids, force = false) {
  if (busy || panelGesture) return;
  const panels = ids || pendingPanels();
  if (!panels.length) return;
  clearTimeout(refreshTimer);
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
  for (const id of panels) {
    if (previous[id]?.state !== "empty") state.renders[id] = { ...previous[id], state: "rendering" };
  }
  drawRenderFailure();
  drawCanvas();
  drawPanels();
  syncRefresh();
  busy = true;
  try {
    state = await request("/api/refresh", { panels, force });
    drawRenderState();
    scheduleRefresh();
  } catch (error) {
    state.renders = previous;
    drawRenderState();
    report(error.message);
  } finally { busy = false; }
}

function pendingPanels() {
  return state.project.panels.filter(panel =>
    ["stale", "error"].includes(state.renders[panel.id]?.state) ||
    (isScript(panel) && drafts.get(panel.id)?.value !== drafts.get(panel.id)?.base)
  ).map(panel => panel.id);
}

function syncRefresh() {
  const rendering = Object.values(state.renders).some(render => render.state === "rendering");
  $("#refresh-all").disabled = rendering || !pendingPanels().length;
  $("#refresh-all span").textContent = rendering ? "Rendering…" : "Refresh panels";
  $("#refresh-selected").hidden = !selected;
  $("#refresh-selected").disabled = rendering || state.renders[selected]?.state === "empty" &&
    drafts.get(selected)?.value === drafts.get(selected)?.base;
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
  font_main_pt: "Main font size (pt)", font_min_pt: "Minimum font size (pt)", line_data_pt: "Data stroke (pt)",
  line_axis_pt: "Axis stroke (pt)", label_reserve_mm: "Space for labels (mm)",
  colors: "Group colours",
  label_offset_x_mm: "Label left offset (mm)", label_offset_y_mm: "Label top offset (mm)",
};

function titleFor(key) {
  const label = titles[key] || key.replace(/_(pt|mm)$/, " ($1)").replaceAll("_", " ");
  return label[0].toUpperCase() + label.slice(1);
}

function section(title, children, open = false, key = title) {
  const group = document.createElement("details");
  group.open = open;
  group.dataset.section = key;
  const summary = document.createElement("summary");
  summary.textContent = title;
  if (inspectorIcons[title]) summary.prepend(icon(inspectorIcons[title]));
  group.append(summary, ...children);
  return group;
}

function inspectorGroup(title, children) {
  const group = document.createElement("section");
  group.className = "inspector-group";
  const heading = document.createElement("h3");
  heading.textContent = title;
  if (inspectorIcons[title]) heading.prepend(icon(inspectorIcons[title]));
  group.append(heading, ...children);
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
  if (options) return selectField(caption, options.map(option =>
    [option, option === "left-bottom" ? "Left and bottom" : titleFor(option)]), value ?? fallback, update);
  if (typeof fallback === "boolean") return checkField(caption, value ?? fallback, update);
  if (key === "font_family") return stringField(caption, value ?? fallback, update);
  const control = document.createElement("input");
  Object.assign(control, { type: "number", step: "any", value: value ?? fallback ?? "",
    min: key.startsWith("label_offset_") ? -100 : 0 });
  if (fallback === null) control.placeholder = "Automatic";
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
  return Object.entries(allPalettes()).map(([id, item]) => [id, item.name + (item.safe ? " (colourblind-safe)" : "")]);
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
  items.push(swatches, button("Duplicate palette", () => {
    edit(p => {
      const id = `custom-${crypto.randomUUID()}`;
      (p.custom ||= {})[id] = { name: `${palette.name} copy`, safe: false, colors: [...palette.colors] };
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
      up.setAttribute("aria-label", `Move colour ${index + 1} up`);
      down.setAttribute("aria-label", `Move colour ${index + 1} down`);
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
    askValue("Add group", "Group name", "Add", group => {
      if (Object.hasOwn(semantic, group)) throw new Error("Enter a unique group name.");
      return edit(p => { p.colors = { ...p.colors, [group]: "#808080" }; });
    });
  }));
  return section("Colours", items);
}

function drawOverrides(panel) {
  const keys = Object.keys(panel.overrides).filter(key => key !== "opt_out");
  const controls = [checkField(isScript(panel) ? "Use the script’s style" : "Allow other fonts", panel.overrides.opt_out,
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
    const plotSetting = !["panel_label_pt", "panel_label_weight", "label_reserve_mm",
      "collapse_empty_labels", "font_min_pt"].includes(key);
    input.querySelector("input, select").disabled = isScript(panel) && panel.overrides.opt_out && plotSetting;
    const row = document.createElement("div");
    row.className = "inline-fields";
    row.append(input, button("Reset", () => editPanel(panel, p => { delete p.overrides[key]; })));
    controls.push(row);
  }
  const labelStyles = ["font_family", "font_min_pt", "font_main_pt", "panel_label_pt",
    "panel_label_weight", "label_reserve_mm", "collapse_empty_labels"];
  const scope = isScript(panel) ? [...Object.keys(state.style_tokens), "palette", "colors"] :
    [...labelStyles, ...(panel.type === "text" ? ["annotation_pt"] :
      panel.type === "legend" ? ["legend_text_pt", "colors", "line_data_pt", "marker_size_pt"] : [])];
  const available = scope.filter(key => !key.startsWith("label_offset_") &&
    !["margin_mm", "gutter_mm"].includes(key) && !Object.hasOwn(panel.overrides, key));
  controls.push(selectField("Add override", [["", "Select setting"], ...available.map(key => [key, titleFor(key)])],
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
      selectField("Symbol", [["patch", "Box"], ["line", "Line"], ["point", "Point"]],
        settings.swatch || "patch", value => update("swatch", value)),
      section("Groups", keys.map(key => checkField(key, selectedKeys.includes(key), include =>
        update("keys", keys.filter(item => item === key ? include : selectedKeys.includes(item))))), true)];
  }
  const asset = document.createElement("p");
  asset.className = "asset-meta";
  const dpi = render.metadata?.effective_dpi?.[0];
  asset.textContent = dpi && settings.filename ? `${settings.filename} (${Math.round(dpi)} dpi)` : settings.filename || "";
  const vector = panel.type === "vector";
  const controls = [button(settings.filename ? "Replace file…" : "Import file…", async () => {
    if (desktop) {
      const path = await chooseDesktopPath(vector ? "openVector" : "openRaster");
      if (automaticRefresh) await automaticRefresh;
      if (path) await commit("/api/asset", { panel: panel.id, path });
      return;
    }
    askValue(vector ? "Import vector" : "Import image", vector ? "PDF or SVG path" : "Image path", "Import",
      path => commit("/api/asset", { panel: panel.id, path }));
  })];
  if (asset.textContent) controls.unshift(asset);
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
  const help = document.createElement("p");
  help.className = "inspector-hint";
  help.textContent = "Use the same plot margins across panels. Each plot follows its panel’s position and size.";
  const controls = [help];
  for (const axis of ["row", "column"]) {
    const current = groups.find(group => group.axis === axis && group.panels.includes(panel.id));
    const members = new Set(current?.panels || [panel.id]);
    const options = others.map(item => checkField(item.name, members.has(item.id), checked => {
      if (checked) members.add(item.id);
      else members.delete(item.id);
      apply.disabled = members.size < 2;
    }));
    const apply = button("Apply", () => change(project => {
      project.alignment = project.alignment.filter(group =>
        group.axis !== axis || !group.panels.includes(panel.id));
      project.alignment.push({ axis, panels: [...members] });
    }));
    apply.disabled = members.size < 2;
    const remove = button("Remove lock", () => change(project => {
      project.alignment = project.alignment.filter(group =>
        group.axis !== axis || !group.panels.includes(panel.id));
    }));
    controls.push(section(axis === "row" ? "Row · Top and bottom" : "Column · Left and right",
      [...options, apply, ...(current ? [remove] : [])], Boolean(current)));
  }
  const alignment = section("Plot alignment", controls);
  const count = groups.filter(group => group.panels.includes(panel.id)).length;
  if (count) {
    const status = document.createElement("span");
    status.className = "disclosure-status";
    status.textContent = `${count} active`;
    alignment.firstElementChild.append(status);
  }
  return alignment;
}

function drawGeometryReferences(panel) {
  const refs = panel.settings.geometry_refs || [];
  const hint = document.createElement("p");
  hint.className = "inspector-hint";
  hint.textContent = "Give the script access to these panels’ positions and sizes. The script rerenders when their relative geometry changes.";
  const options = state.project.panels.filter(item => item.id !== panel.id).map(item =>
    checkField(item.name, refs.includes(item.id), checked => editPanel(panel, p => {
      p.settings.geometry_refs = checked ? [...refs, item.id] : refs.filter(id => id !== item.id);
    })));
  return section("Referenced panels", [hint, ...options]);
}

function drawPanelInspector(panel) {
  const {x, y, w, h} = state.geometry.rects[panel.id];
  const dimensionNames = { x: "X", y: "Y", w: "Width", h: "Height" };
  const dimensions = Object.entries({x, y, w, h}).map(([key, value]) =>
    numeric(`${dimensionNames[key]} (mm)`, Number(value.toFixed(5)),
      next => layout("edit", { field: key, value: next })));
  const locks = ["w", "h"].map(key => {
    const box = document.createElement("input");
    Object.assign(box, { type: "checkbox", checked: key in panel.locks });
    box.onchange = () => layout("lock", { field: key, enabled: box.checked });
    return field(key === "w" ? "Lock width" : "Lock height", box);
  });
  const script = isScript(panel);
  const identity = fieldGrid([
    stringField("Name", panel.name, value => editPanel(panel, p => { p.name = value.trim() || p.name; })),
    stringField("Label", panel.label, value => editPanel(panel, p => { p.label = value; })),
  ]);
  identity.classList.add("panel-identity-fields");
  const controls = [
    inspectorGroup("Panel", [identity]),
    inspectorGroup("Geometry", [fieldGrid(dimensions), fieldGrid(locks),
      ...(script ? [drawAlignment(panel), drawGeometryReferences(panel)] : [])]),
    inspectorGroup("Appearance", [drawOverrides(panel)]),
  ];
  if (script) {
    const editScript = button("Edit script", () => openEditor(panel.id));
    editScript.id = "edit-script";
    editScript.className = "inspector-edit";
    editScript.prepend(icon("code"));
    const inputs = document.createElement("textarea");
    Object.assign(inputs, { rows: 3, value: (panel.input_files || []).join("\n"), spellcheck: false });
    inputs.onchange = () => editPanel(panel, p => {
      p.input_files = inputs.value.split("\n").map(path => path.trim()).filter(Boolean);
    });
    const hint = document.createElement("p");
    hint.className = "inspector-hint";
    hint.textContent = "Enter one data file or helper script per line. Relative paths start at the data folder.";
    controls.push(inspectorGroup("Source", [editScript, section("Interpreter", [
      interpreterField("Interpreter path", panel.type, panel.interpreter,
        value => editPanel(panel, p => { p.interpreter = value; })),
    ]), section("Render inputs", [field("Input files", inputs), hint])]));
  } else controls.splice(1, 0, inspectorGroup("Content", nativeInspector(panel)));
  const actions = document.createElement("div");
  actions.className = "panel-actions";
  const group = state.project.groups?.find(item => item.panels.includes(panel.id));
  if (group) actions.append(button("Remove from group", () => change(project => {
    const record = project.groups.find(item => item.id === group.id);
    record.panels = record.panels.filter(id => id !== panel.id);
    if (record.panels.length < 2) project.groups = project.groups.filter(item => item.id !== group.id);
  })));
  if (state.project.panels.length > 1) {
    const front = button("Bring to front", () => layout("stack", {direction: "front"}));
    const back = button("Send to back", () => layout("stack", {direction: "back"}));
    front.disabled = state.project.panels.at(-1).id === panel.id;
    back.disabled = state.project.panels[0].id === panel.id;
    actions.append(front, back);
  }
  if (actions.childElementCount) controls.push(inspectorGroup("Arrange", [actions]));
  $("#settings").replaceChildren(...controls);
}

async function deletePanel() {
  const panel = state?.project.panels.find(item => item.id === selected);
  if (!panel || busy && !automaticRefresh || panelGesture) return;
  const draft = drafts.get(panel.id);
  if (draft && draft.value !== draft.base &&
      !confirm(`Delete “${panel.name}” and discard its unsaved script edits?`)) return;
  if (await layout("delete", { panel: panel.id })) {
    drafts.delete(panel.id);
    $("#figure-settings").focus({ preventScroll: true });
    report(`Deleted ${panel.name}. Use Undo to restore it.`);
  }
}

function fieldGrid(children) {
  const grid = document.createElement("div");
  grid.className = "field-grid";
  grid.append(...children);
  return grid;
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
  else if (promptConflict && !confirm(`“${panel.name}” changed on disk. Select OK to keep your edits or Cancel to load the file from disk.`)) {
    draft.value = panel.script;
  } else if (!promptConflict) return draft;
  draft.base = panel.script;
  return draft;
}

function editorStatus(draft) {
  $("#editor-status").textContent = draft.value === draft.base ? "" : "Unsaved edits";
  $("#save-script").disabled = draft.value === draft.base;
  syncRefresh();
}

function drawEditor(panel) {
  const open = editorOpen && panel && isScript(panel);
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
      clearTimeout(scriptSaveTimer);
      scriptSaveTimer = setTimeout(saveScriptsOnIdle, 700);
    });
  } else editor.replace(draft.value);
  editorStatus(draft);
  $("#editor-title").textContent = `${typeNames[panel.type]} script`;
  const render = state.renders[panel.id] || {};
  showConsole([render.error, render.stdout, render.stderr, ...(render.warnings || [])]
    .filter(Boolean).join("\n"));
}

function showConsole(message) {
  $("#console").textContent = message;
  $("#console").hidden = !message;
}

function openEditor(id) {
  showChecks = false;
  selectedCheck = null;
  selectedGroup = null;
  multiSelection.clear();
  selected = id;
  editorOpen = true;
  draw(false);
  $("#script-editor :is(.cm-content, textarea)")?.focus();
}

async function saveDraft(panel, autosave = false) {
  if (busy || panelGesture) return false;
  const draft = reconcileDraft(panel, !autosave);
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
        if (!autosave) scheduleRefresh();
        return true;
      }
      panel.script = result.script;
      if (autosave) {
        report("Script changed on disk. Open the script to review both versions.");
        return false;
      }
      reconcileDraft(panel);
      if (draft.value === draft.base) {
        state = await request("/api/project");
        draw();
        scheduleRefresh();
        return true;
      }
    }
  } catch (error) { report(error.message); return false; }
  finally { busy = false; }
}

async function saveScriptsOnIdle() {
  if (busy || panelGesture || switchingFigure || pendingChange) {
    scriptSaveTimer = setTimeout(saveScriptsOnIdle, 700);
    return;
  }
  idleScriptSave = saveAllDrafts(true).finally(() => { idleScriptSave = null; });
  await idleScriptSave;
}

async function pollScripts() {
  if (busy || panelGesture || !state) return;
  const previous = state;
  try {
    const result = await request("/api/scripts");
    if (busy || panelGesture || state !== previous || result.workspace_id !== state.workspace_id) return;
    const changed = state.project.panels.some(panel => isScript(panel) && result.scripts[panel.id] !== panel.script);
    const updatedInputs = result.stale_inputs.some(id => state.renders[id]?.state !== "stale");
    if (changed || updatedInputs) {
      const latest = await request("/api/project");
      if (busy || panelGesture || state !== previous || latest.workspace_id !== state.workspace_id) return;
      state = latest;
      drawRenderState();
      scheduleRefresh();
      reportProjectStatus();
    }
  } catch { /* The next poll can reconnect after a transient failure. */ }
}

function activeScript() {
  return state.project.panels.find(panel => panel.id === selected && isScript(panel));
}

function workspaceVisible() {
  return desktopVisible && !document.hidden;
}

function queuePoll(delay = 1000) {
  clearTimeout(pollTimer);
  if (!state || polling || !workspaceVisible()) return;
  pollTimer = setTimeout(async () => {
    if (!workspaceVisible()) return;
    polling = true;
    try { await pollScripts(); }
    finally { polling = false; queuePoll(); }
  }, delay);
}

function resumeVisibleWork() {
  queuePoll(0);
  if (state) scheduleRefresh();
}

async function runSelected(force = false) {
  if (automaticRefresh) await automaticRefresh;
  if (pendingChange && !await pendingChange) return;
  const panel = activeScript();
  if (panel && await saveDraft(panel)) await refresh([panel.id], force);
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
  drawRenderFailure();
  $("#show-inspector").setAttribute("aria-pressed", String(!showChecks));
  $("#show-checks").setAttribute("aria-pressed", String(showChecks));
  $("#check-count").textContent = state.checks.length;
  $("#check-count").hidden = !state.checks.length;
  $("#settings").hidden = showChecks;
  $("#inspector-heading").hidden = showChecks;
  $("#checks").hidden = !showChecks;
  if (!showChecks) return;
  if (!state.checks.length) {
    $("#checks").textContent = "No warnings";
    return;
  }
  const list = document.createElement("ul");
  list.className = "check-list";
  for (const check of state.checks) {
    const panel = state.project.panels.find(item => item.id === check.panel);
    const item = document.createElement("li");
    const row = panel ? button(check.message, () => {
      selectPanel(panel.id);
      const tile = panels.get(panel.id);
      selectedCheck = check;
      if (check.boxes) {
        const rect = state.geometry.rects[panel.id];
        const box = state.renders[panel.id].box;
        const [w, h] = check.page_pt;
        const factor = Math.min(box.w / w, box.h / h);
        const x = box.x + box.w / 2 + (Math.min(...check.boxes.map(b => b[0])) +
          Math.max(...check.boxes.map(b => b[2])) - w) * factor / 2;
        const y = box.y + box.h / 2 + (Math.min(...check.boxes.map(b => b[1])) +
          Math.max(...check.boxes.map(b => b[3])) - h) * factor / 2;
        if (zoom < 9) {
          zoom = 9;
          setView("custom");
        } else drawCanvas();
        const view = viewport.getBoundingClientRect();
        const board = frame.getBoundingClientRect();
        viewport.scrollBy(board.left + x*zoom - view.left - view.width/2,
                          board.top + y*zoom - view.top - view.height/2);
      } else tile?.scrollIntoView({ block: "nearest", inline: "nearest" });
      tile?.focus({ preventScroll: true });
    }) : document.createElement("p");
    row.className = "check-row";
    if (!panel) row.textContent = check.message;
    else {
      if (panel.id === selected) row.classList.add("selected");
      const title = document.createElement("span");
      title.textContent = panel.name;
      row.prepend(title);
    }
    item.append(row);
    list.append(item);
  }
  $("#checks").replaceChildren(list);
}

function drawGroupInspector(group) {
  const available = state.project.panels.filter(panel =>
    !state.project.groups.some(item => item.panels.includes(panel.id)));
  const settings = $("#settings");
  settings.replaceChildren(stringField("Group name", group.name, value => change(project => {
    project.groups.find(item => item.id === group.id).name = value.trim() || group.name;
  })));
  if (available.length) settings.append(selectField("Add to group",
    [["", "Choose a panel"], ...available.map(panel => [panel.id, panel.name])], "", id => {
      if (id) change(project => project.groups.find(item => item.id === group.id).panels.push(id));
    }));
  settings.append(button("Ungroup", () => change(project => {
    project.groups = project.groups.filter(item => item.id !== group.id);
  })), drawSelectionInspector(new Set(group.panels)));
}

function drawSelectionInspector(ids) {
  const { bounds, entries, locks, minimums } = selectionLayout(ids);
  const { width_mm, height_mm, minimum_mm } = state.project.size;
  const boundsFields = [
    ["x", "X (mm)", 0, width_mm - bounds.w],
    ["y", "Y (mm)", 0, height_mm - bounds.h],
    ["w", "Width (mm)", minimums.w, width_mm - bounds.x],
    ["h", "Height (mm)", minimums.h, height_mm - bounds.y],
  ].map(([key, caption, min, max]) => {
    const control = numeric(caption, cleanMm(bounds[key]), value => change(project => {
      const target = selectionLayout(ids);
      storeSelectionBounds(project, target, { ...target.bounds, [key]: value });
    }), cleanMm(min), cleanMm(max));
    control.querySelector("input").disabled = key in locks;
    return control;
  });
  const sizeFields = [
    ["w", "x", "Panel width (mm)", width_mm],
    ["h", "y", "Panel height (mm)", height_mm],
  ].map(([dim, axis, caption, span]) => {
    const [first] = entries;
    const uniform = entries.every(([, rect]) => rect[dim] === first[1][dim]);
    const max = Math.min(...entries.map(([, rect]) => span - rect[axis]));
    const control = numeric(caption, uniform ? cleanMm(first[1][dim]) : null, value => change(project => {
      for (const id of ids) project.layout.rects[id][dim] = value;
    }), minimum_mm, cleanMm(max));
    const input = control.querySelector("input");
    if (!uniform) input.placeholder = "Mixed";
    input.disabled = dim in locks;
    return control;
  });
  const hint = document.createElement("p");
  hint.className = "selection-hint";
  const locked = ["width", "height"].filter(dim => dim[0] in locks);
  hint.textContent = locked.length ? `A panel has a locked ${locked.join(" and ")}.` :
    "Drag a corner to scale the selection.";
  return inspectorGroup("Selection geometry", [
    fieldGrid(boundsFields), hint, section("Set panel sizes", [fieldGrid(sizeFields)]),
  ]);
}

function hasUnsavedScriptEdits() {
  return state.project.panels.some(panel => {
    const draft = drafts.get(panel.id);
    return draft && draft.value !== draft.base;
  });
}

function reportProjectStatus() {
  if ($("#workspace").hidden) return;
  if (!state.bundle) return report(hasUnsavedScriptEdits() ? "Unsaved script edits" : "Local draft");
  const name = state.bundle.split("/").at(-1);
  report(state.bundle_dirty || hasUnsavedScriptEdits() ? `${name} (local changes)` : name);
  $("#status").title = state.bundle;
}

function draw(updateStatus = true) {
  const { project } = state;
  const group = project.groups?.find(item => item.id === selectedGroup);
  if (!group) selectedGroup = null;
  for (const id of multiSelection) if (!state.geometry.rects[id]) multiSelection.delete(id);
  if (multiSelection.size === 1) {
    selected = multiSelection.values().next().value;
    multiSelection.clear();
  }
  const panel = project.panels.find(item => item.id === selected);
  if (!panel) {
    selected = null;
    editorOpen = false;
  }
  $("#project-name").value = project.name;
  drawFigureTabs();
  $("#measure").textContent = `${project.size.width_mm} × ${project.size.height_mm} mm`;
  $("#undo").disabled = !past.length;
  $("#redo").disabled = !future.length;
  $("#delete-panel").disabled = !panel;
  $("#inspector-title").textContent = panel?.name || group?.name ||
    (multiSelection.size ? `${multiSelection.size} panels selected` : "Figure settings");
  $("#inspector-type").textContent = panel ? (isScript(panel) ? `${typeNames[panel.type]} script` : typeNames[panel.type]) :
    group ? "Panel group" : "";
  $("#inspector-type").hidden = !panel && !group;
  drawEditor(panel);
  drawCanvas();
  drawPanels();
  drawChecks();
  syncRefresh();
  if (updateStatus) reportProjectStatus();
  const settings = $("#settings");
  const scope = panel ? `panel:${panel.id}` : group ? `group:${group.id}` :
    multiSelection.size ? "selection" : "figure";
  const sameScope = settings.dataset.scope === scope;
  const groups = sameScope
    ? new Map([...settings.querySelectorAll("details")].map(item => [item.dataset.section, item.open]))
    : new Map();
  if (!sameScope) $("#inspector-content").scrollTop = 0;
  settings.dataset.scope = scope;
  const focused = settings.contains(document.activeElement) && document.activeElement.name;
  const restoreGroups = () => {
    for (const item of settings.querySelectorAll("details")) {
      if (groups.has(item.dataset.section)) item.open = groups.get(item.dataset.section);
    }
    if (focused) settings.querySelector(`[name="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
  };
  if (panel) { drawPanelInspector(panel); restoreGroups(); return; }
  if (group) { drawGroupInspector(group); restoreGroups(); return; }
  if (multiSelection.size) {
    settings.replaceChildren(drawSelectionInspector(new Set(multiSelection)));
    restoreGroups();
    return;
  }
  const preset = document.createElement("select");
  const matchesPreset = journals.some(journal =>
    journal.id === project.size.preset_id && journal.widths?.includes(project.size.width_mm));
  for (const journal of journals) {
    for (const width of journal.widths || [null]) {
      const option = new Option(width ? `${journal.name} (${width} mm)` : journal.name,
                                `${journal.id}:${width}`);
      option.disabled = width === null;
      preset.add(option);
    }
  }
  preset.add(new Option("Custom", "custom"));
  preset.value = matchesPreset ? `${project.size.preset_id}:${project.size.width_mm}` : "custom";
  preset.onchange = () => change(p => {
    if (preset.value === "custom") {
      p.size.preset_id = "custom";
      return;
    }
    const [id, width] = preset.value.split(":");
    Object.assign(p.size, { preset_id: id, width_mm: Number(width) });
  });
  const height = document.createElement("input");
  Object.assign(height, { type: "number", min: "1", step: "0.1", value: project.size.height_mm });
  height.onchange = () => change(p => { if (height.validity.valid) p.size.height_mm = height.valueAsNumber; });
  const swapDimensions = button("Swap width and height", () => change(p => {
    const size = p.size;
    [size.width_mm, size.height_mm] = [size.height_mm, size.width_mm];
    const widths = journals.find(journal => journal.id === size.preset_id)?.widths;
    if (!widths?.includes(size.width_mm)) size.preset_id = "custom";
  }));
  swapDimensions.name = "swap-artboard-dimensions";
  swapDimensions.disabled = project.size.width_mm === project.size.height_mm;
  const localData = stringField("Local data folder", state.data_root_override, async value => {
    if (pendingChange && !await pendingChange) return;
    if (automaticRefresh) await automaticRefresh;
    await commit("/api/local-data-folder", { path: value.trim() }, false);
  });
  const projectOptions = [
    stringField("Data folder", project.data_root, value => change(p => { p.data_root = value; })),
    desktop ? pathPicker(localData, "chooseFolder") : localData,
    button("Compare render environment", showEnvironmentReport),
    numeric("Render timeout (s)", project.timeout_s, value => change(p => { p.timeout_s = value; }), 1),
    ...["script-r", "script-py"].map(type =>
      interpreterField(type === "script-r" ? "Default Rscript" : "Default Python", type, project.interpreters[type] || "",
        value => change(p => { p.interpreters[type] = value; }))),
    stringField("Virtual environments (comma-separated paths)", (project.interpreters.venvs || []).join(", "), async value => {
      if (await change(p => { p.interpreters.venvs = value.split(",").map(path => path.trim()).filter(Boolean); })) {
        findInterpreters();
      }
    }),
    button("Detect interpreters", findInterpreters),
    button("Export style (.json)", async () => {
      try {
        if (desktop) {
          const path = await chooseDesktopPath("saveStyle", "plate-style.json");
          if (path) report((await request("/api/save-style", {path})).path);
        } else {
          downloadJson("plate-style.json", await request("/api/style-json", {}));
        }
      }
      catch (error) { report(error.message); }
    }),
  ];
  $("#settings").replaceChildren(
    inspectorGroup("Artboard", [
      field("Journal width", preset),
      fieldGrid([
        ...(!matchesPreset ? [numeric("Width (mm)", project.size.width_mm,
          width => change(p => { Object.assign(p.size, { preset_id: "custom", width_mm: width }); }), 1)] : []),
        field("Height (mm)", height),
        numeric("Grid spacing (mm)", state.geometry.grid_step,
          value => change(p => { p.layout.step_mm = value; }), .5),
      ]),
      swapDimensions,
    ]),
    inspectorGroup("Figure style", [
      ...Object.entries(styleGroups).map(([name, keys]) => section(name, keys.map(key =>
        styleField(key, project.style[key], value => change(p => { p.style[key] = value; }))))),
      drawPaletteInspector(),
    ]),
    inspectorGroup("Project", [section("Advanced", [
      numeric("Minimum panel size (mm)", project.size.minimum_mm,
        value => change(p => { p.size.minimum_mm = value; }), 1), ...projectOptions,
    ])]));
  restoreGroups();
}

async function action(name, data = {}) {
  if (pendingChange && !await pendingChange) return false;
  if (automaticRefresh) await automaticRefresh;
  if (busy || panelGesture) return;
  busy = true;
  try {
    state = await request(`/api/${name}`, data);
    if (state.library) library = state.library;
    if (!switchingFigure) {
      draw();
      scheduleRefresh();
    }
    return true;
  }
  catch (error) { report(error.message); return false; }
  finally { busy = false; }
}

function currentProject() {
  return library.projects.find(project => project.figures.some(figure => figure.id === library.active));
}

const figureTabs = $("#figure-tabs");

function updateFigureTabEdges() {
  const maxScroll = figureTabs.scrollWidth - figureTabs.clientWidth;
  const left = figureTabs.scrollLeft;
  figureTabs.toggleAttribute("data-fade-left", maxScroll > 1 && left > 1);
  figureTabs.toggleAttribute("data-fade-right", maxScroll > 1 && maxScroll - left > 1);
}

function revealFigureTab(tab) {
  tab?.parentElement.scrollIntoView({ block: "nearest", inline: "nearest" });
}

figureTabs.addEventListener("scroll", updateFigureTabEdges, { passive: true });
new ResizeObserver(updateFigureTabEdges).observe(figureTabs);
document.fonts.ready.then(updateFigureTabEdges);
figureTabs.addEventListener("wheel", event => {
  const mode = event.deltaMode;
  if (event.deltaX || !event.deltaY || event.ctrlKey || event.shiftKey) return;
  const before = figureTabs.scrollLeft;
  const step = mode === 1 ? 16 : mode === 2 ? figureTabs.clientWidth : 1;
  figureTabs.scrollLeft += event.deltaY * step;
  if (figureTabs.scrollLeft !== before) event.preventDefault();
}, { passive: false });

function drawFigureTabs() {
  const figures = new Map(library.projects.flatMap(project => project.figures.map(figure => [figure.id, { figure, project }])));
  const current = currentProject();
  const figure = figures.get(state.workspace_id)?.figure;
  if (figure) figure.name = state.project.name;
  const names = new Map();
  for (const id of library.tabs) {
    const name = figures.get(id)?.figure.name;
    names.set(name, (names.get(name) || 0) + 1);
  }
  $("#collection-name").value = current?.name || "";
  $("#figure-strip").hidden = !library.tabs.length;
  $("#new-figure").disabled = !current;
  $("#project-figures").disabled = !current;
  $("#move-figure").disabled = library.projects.length < 2;
  const focus = figureTabs.contains(document.activeElement) ? document.activeElement.dataset.figure : null;
  const scroll = figureTabs.scrollLeft;
  figureTabs.replaceChildren(...library.tabs.flatMap(id => {
    const entry = figures.get(id);
    if (!entry) return [];
    const { figure: item, project } = entry;
    const active = library.active === id;
    const label = names.get(item.name) > 1 ? `${item.name} · ${project.name}` : item.name;
    const tab = button(label, () => switchFigure("resume", { workspace: id }));
    tab.id = "figure-tab-" + id;
    tab.dataset.figure = id;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(active));
    tab.setAttribute("aria-controls", "workspace");
    tab.tabIndex = active ? 0 : -1;
    tab.title = `${project.name} / ${item.name}`;
    if (active) $("#workspace").setAttribute("aria-labelledby", tab.id);
    const close = button("", () => switchFigure("close-tab", { workspace: id }));
    close.className = "figure-tab-close";
    close.setAttribute("aria-label", "Close tab for " + label);
    close.append(icon("close"));
    const wrapper = document.createElement("div");
    wrapper.className = "figure-tab";
    wrapper.setAttribute("role", "presentation");
    wrapper.append(tab, close);
    return [wrapper];
  }));
  figureTabs.scrollLeft = scroll;
  updateFigureTabEdges();
  if (focus) document.getElementById("figure-tab-" + focus)?.focus({ preventScroll: true });
  $("#figure-actions").replaceChildren(...(current?.figures || []).map(item =>
    button(item.name, () => {
      $("#figure-actions").hidePopover();
      switchFigure("resume", { workspace: item.id });
    })));
}

figureTabs.onkeydown = event => {
  const tabs = [...figureTabs.querySelectorAll('[role="tab"]')];
  const index = tabs.indexOf(event.target);
  const next = {
    ArrowLeft: (index + tabs.length - 1) % tabs.length, ArrowRight: (index + 1) % tabs.length,
    Home: 0, End: tabs.length - 1,
  }[event.key];
  if (index < 0 || next === undefined) return;
  event.preventDefault();
  tabs[next].focus({ preventScroll: true });
  revealFigureTab(tabs[next]);
};

async function flushFigure() {
  document.activeElement?.blur();
  if (pendingChange && !await pendingChange) return false;
  if (projectRename && !await projectRename) return false;
  clearTimeout(scriptSaveTimer);
  if (idleScriptSave) await idleScriptSave;
  return !hasUnsavedScriptEdits() || await saveAllDrafts();
}

async function switchFigure(name, data = {}) {
  if (!state || switchingFigure || panelGesture) return false;
  switchingFigure = true;
  try {
    const focusTab = figureTabs.contains(document.activeElement);
    if (!await flushFigure()) return false;
    const previous = state.workspace_id;
    if (!$("#workspace").hidden) {
      figureViews.set(previous, { past, future, selected, selectedGroup, selectedCheck,
        selectedPanels: [...multiSelection], zoom, viewMode, editorOpen, showChecks,
        scrollLeft: viewport.scrollLeft, scrollTop: viewport.scrollTop });
    }
    if (!await action(name, data)) return false;
    if (!library.active) {
      hasEditorProject = false;
      drawFigureTabs();
      showHome();
      return true;
    }
    if (previous !== state.workspace_id) {
      const view = figureViews.get(state.workspace_id) || {};
      past = view.past || []; future = view.future || [];
      selected = view.selected ?? null; selectedGroup = view.selectedGroup ?? null;
      selectedCheck = view.selectedCheck ?? null;
      multiSelection.clear();
      for (const id of view.selectedPanels || []) multiSelection.add(id);
      zoom = view.zoom ?? 3.1; viewMode = view.viewMode || "fit";
      editorOpen = Boolean(view.editorOpen); showChecks = Boolean(view.showChecks);
      drafts.clear();
      editor?.destroy();
      editor = null; editorId = null;
      $("#panel-handles").removeAttribute("data-panel");
    }
    showEditor(false);
    draw();
    const view = figureViews.get(state.workspace_id);
    if (view && previous !== state.workspace_id) viewport.scrollTo(view.scrollLeft, view.scrollTop);
    const tab = document.getElementById("figure-tab-" + library.active);
    if (previous !== state.workspace_id || focusTab) revealFigureTab(tab);
    if (focusTab) tab?.focus({ preventScroll: true });
    scheduleRefresh();
    findInterpreters();
    return true;
  } finally { switchingFigure = false; }
}

const projectModule = import("/vendor/projects.js").catch(() => null);

async function loadLibrary() {
  const id = ++libraryLoad;
  const container = $("#project-library");
  container.setAttribute("aria-busy", "true");
  try {
    const [module, result] = await Promise.all([projectModule, request("/api/projects")]);
    if (id !== libraryLoad) return;
    if (!module) throw new Error("The project browser is unavailable. Run make editor and reload Plate.");
    renderLibrary ||= module.mountProjects(container, workspace => switchFigure("resume", { workspace }));
    renderLibrary(result.projects);
  } catch (error) {
    if (id !== libraryLoad) return;
    if (renderLibrary) report(error.message);
    else container.querySelector(".library-message").textContent = error.message;
  } finally {
    if (id === libraryLoad) container.setAttribute("aria-busy", "false");
  }
}

function showHome(focus = true) {
  if ($(":popover-open")) $(":popover-open").hidePopover();
  $("#workspace").hidden = true;
  $(".project-crumb").hidden = true;
  $(".project-actions").hidden = true;
  $("#home").hidden = false;
  $("#return-to-editor").hidden = !hasEditorProject;
  $(".skip-link").hash = "#home";
  report("");
  loadLibrary();
  if (focus) $("#home").focus({ preventScroll: true });
}

function showEditor(focus = true) {
  hasEditorProject = true;
  $("#home").hidden = true;
  $("#return-to-editor").hidden = true;
  $(".project-crumb").hidden = false;
  $(".project-actions").hidden = false;
  $("#workspace").hidden = false;
  $(".skip-link").hash = "#workspace";
  drawCanvas();
  reportProjectStatus();
  if (focus) requestAnimationFrame(() => {
    if (!$("#workspace").hidden) $("#workspace").focus({ preventScroll: true });
  });
}

function formError(selector, message = "") {
  const error = $(selector);
  error.textContent = message;
  error.hidden = !message;
}

const inputDialog = $("#input-dialog");
function askValue(title, label, submitLabel, onSubmit) {
  const form = $("#input-form");
  const submit = form.querySelector("button[type=submit]");
  $("#input-title").textContent = title;
  $("#input-label").textContent = label;
  $("#input-value").value = "";
  submit.textContent = submitLabel;
  formError("#input-error");
  form.onsubmit = async event => {
    event.preventDefault();
    const value = $("#input-value").value.trim();
    if (!value) {
      formError("#input-error", `Enter a value for ${label.toLowerCase()}.`);
      return;
    }
    submit.disabled = true;
    formError("#input-error");
    try {
      const result = await onSubmit(value);
      if (result) inputDialog.close();
      else if (result === false) formError("#input-error", $("#status").textContent);
    } catch (error) {
      formError("#input-error", error.message);
    } finally {
      submit.disabled = false;
    }
  };
  inputDialog.showModal();
}
$("#cancel-input").onclick = () => inputDialog.close();

async function chooseDesktopPath(kind, suggested = "") {
  try { return await desktop.postMessage({ kind, suggested }); }
  catch (error) { report(error.message); return null; }
}

function pathPicker(label, kind) {
  const row = document.createElement("div");
  row.className = "path-picker";
  const input = label.querySelector("input");
  row.append(label, button("Choose…", async () => {
    const path = await chooseDesktopPath(kind);
    if (path) {
      input.value = path;
      input.dispatchEvent(new Event("change"));
    }
  }));
  return row;
}

async function addPanel(type, position) {
  const name = `${typeNames[type]} panel`;
  if (await layout("add", { type, name, position })) {
    showChecks = false;
    selectPanel(state.project.panels.at(-1).id);
  }
}
for (const [type, name] of Object.entries(typeNames)) {
  const option = button(name, () => {
    $("#panel-types").hidePopover();
    addPanel(type);
  });
  option.prepend(icon(typeIcons[type]));
  option.draggable = true;
  option.ondragstart = event => startListDrag(event, null, type);
  option.ondragend = endDrag;
  $("#panel-types").append(option);
}

for (const popup of document.querySelectorAll(".popover")) {
  popup.addEventListener("toggle", event => {
    if (event.newState !== "open") return;
    const trigger = event.source || document.querySelector(`[popovertarget="${popup.id}"]`);
    const anchor = trigger.getBoundingClientRect();
    const below = anchor.bottom + 4;
    popup.style.left = `${Math.max(8, Math.min(anchor.left, innerWidth - popup.offsetWidth - 8))}px`;
    popup.style.top = `${below + popup.offsetHeight <= innerHeight ? below :
      Math.max(8, anchor.top - popup.offsetHeight - 4)}px`;
    popup.querySelector("button:enabled")?.focus({ preventScroll: true });
  });
}

$("#figure-settings").onclick = () => {
  showChecks = false;
  selectPanel(null);
};
$("#group-panels").onclick = () => {
  if (!canGroupSelection()) return;
  const group = {id: crypto.randomUUID(), panels: [...multiSelection], name: ""};
  askValue("Group panels", "Group name", "Group", async name => {
    group.name = name;
    if (!await change(project => { (project.groups ||= []).push(group); })) return false;
    selectGroup(group);
    return true;
  });
};
$("#frame").ondragover = event => {
  if (!draggedType && !dragged) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = draggedType ? "copy" : "move";
};
$("#frame").ondrop = event => {
  if (!draggedType && !dragged) return;
  event.preventDefault();
  const frame = $("#frame").getBoundingClientRect();
  const {width_mm, height_mm} = state.project.size;
  const position = {x: snapped((event.clientX - frame.left) / zoom, 0, width_mm),
                    y: snapped((event.clientY - frame.top) / zoom, 0, height_mm)};
  const type = draggedType;
  const id = dragged;
  endDrag();
  if (type) addPanel(type, position);
  else {
    const panel = state.project.panels.find(item => item.id === id);
    const rect = state.geometry.rects[id];
    if (rect) layout("place", {panel: id, rect: panelPlacement(rect, panel.locks, null,
      position.x - rect.x, position.y - rect.y)});
  }
};
$("#undo").onclick = () => history(past, future);
$("#redo").onclick = () => history(future, past);
$("#delete-panel").onclick = deletePanel;
function setView(mode) { if (state) { viewMode = mode; drawCanvas(); } }
$("#fit-view").onclick = () => setView("fit");
$("#fit-width").onclick = () => {
  setView("width");
  viewport.scrollTo(0, 0);
};
$("#actual-size").onclick = () => setView("actual");
$("#show-grid").onclick = event => {
  const visible = $("#frame").classList.toggle("show-grid");
  event.currentTarget.setAttribute("aria-pressed", String(visible));
};
const viewport = $(".viewport");
const frame = $("#frame");
viewport.addEventListener("pointerdown", startMarquee);
viewport.addEventListener("click", event => {
  if (state && event.pointerType === "touch" && (event.target === frame || event.target === viewport)) {
    selectPanels(new Set());
  }
});
let zoomFrame;
function zoomAt(scale, clientX, clientY) {
  if (!state || panelGesture || dragged || draggedType) return;
  const next = Math.min(25, Math.max(.1, scale));
  if (next === zoom) return;
  const view = viewport.getBoundingClientRect();
  const before = frame.getBoundingClientRect();
  const x = clientX ?? (view.left + view.width / 2);
  const y = clientY ?? (view.top + view.height / 2);
  const ratio = next / zoom;
  zoom = next;
  frame.classList.add("zooming");
  setView("custom");
  const after = frame.getBoundingClientRect();
  viewport.scrollBy(after.left + (x - before.left) * ratio - x,
                    after.top + (y - before.top) * ratio - y);
  cancelAnimationFrame(zoomFrame);
  zoomFrame = requestAnimationFrame(() => frame.classList.remove("zooming"));
}
$("#zoom-out").onclick = () => zoomAt(zoom / 1.2);
$("#zoom-in").onclick = () => zoomAt(zoom * 1.2);
let gestureZoom;
viewport.addEventListener("wheel", event => {
  if (!event.ctrlKey) return;
  event.preventDefault();
  if (gestureZoom !== undefined) return;
  const factor = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1;
  zoomAt(zoom * Math.exp(-event.deltaY * factor * .01), event.clientX, event.clientY);
}, { passive: false });
viewport.addEventListener("gesturestart", event => {
  event.preventDefault();
  gestureZoom = zoom;
}, { passive: false });
viewport.addEventListener("gesturechange", event => {
  if (gestureZoom === undefined) return;
  event.preventDefault();
  zoomAt(gestureZoom * event.scale, event.clientX, event.clientY);
}, { passive: false });
viewport.addEventListener("gestureend", event => {
  if (gestureZoom === undefined) return;
  event.preventDefault();
  gestureZoom = undefined;
}, { passive: false });
new ResizeObserver(() => {
  if (state && (viewMode === "fit" || viewMode === "width")) drawCanvas();
}).observe(viewport);

const workbench = $("#workspace");
for (const divider of workbench.querySelectorAll(".sidebar-divider")) {
  const side = divider.dataset.side;
  const left = side === "left";
  const pane = document.getElementById(divider.getAttribute("aria-controls"));
  const minimum = left ? 148 : 224;
  const maximum = () => Math.min(left ? 360 : 440,
    Math.floor(workbench.clientWidth * (left ? .29 : .39)));
  let drag;

  function announce(width) {
    divider.setAttribute("aria-valuemin", minimum);
    divider.setAttribute("aria-valuemax", maximum());
    divider.setAttribute("aria-valuenow", width);
    divider.setAttribute("aria-valuetext", `${width} pixels`);
  }

  function resize(width) {
    const next = clamp(Math.round(width), minimum, maximum());
    workbench.style.setProperty(`--sidebar-${side}`, `${next}px`);
    announce(next);
  }

  divider.onpointerdown = event => {
    if (drag || event.button !== 0) return;
    event.preventDefault();
    divider.focus({ preventScroll: true });
    divider.setPointerCapture(event.pointerId);
    divider.dataset.dragging = "";
    drag = { id: event.pointerId, x: event.clientX, width: pane.offsetWidth };
  };
  divider.onpointermove = event => {
    if (drag?.id === event.pointerId) resize(drag.width + (event.clientX - drag.x) * (left ? 1 : -1));
  };
  divider.onlostpointercapture = event => {
    if (drag?.id !== event.pointerId) return;
    drag = undefined;
    delete divider.dataset.dragging;
  };
  divider.onkeydown = event => {
    const step = (event.shiftKey ? 48 : 16) * (left ? 1 : -1);
    const keys = { ArrowLeft: pane.offsetWidth - step, ArrowRight: pane.offsetWidth + step,
      Home: minimum, End: maximum() };
    if (!Object.hasOwn(keys, event.key)) return;
    event.preventDefault();
    resize(keys[event.key]);
  };
  divider.ondblclick = () => {
    workbench.style.removeProperty(`--sidebar-${side}`);
    announce(pane.offsetWidth);
  };
  new ResizeObserver(() => {
    if (divider.offsetWidth) announce(pane.offsetWidth);
  }).observe(workbench);
}

document.addEventListener("keydown", event => {
  if ($("#workspace").hidden || event.defaultPrevented ||
      event.target.closest("input, textarea, select, [contenteditable], dialog, :popover-open")) return;
  if (event.key === "Escape" && state && !panelGesture && selectedPanelIds().size) {
    event.preventDefault();
    selectPanels(new Set());
    return;
  }
  if (["Delete", "Backspace"].includes(event.key) && !event.metaKey && !event.ctrlKey && !event.altKey && selected) {
    event.preventDefault();
    if (!event.repeat) deletePanel();
    return;
  }
  if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") return;
  event.preventDefault();
  if (event.shiftKey) history(future, past);
  else history(past, future);
});

$("#show-inspector").onclick = () => { if (state) { showChecks = false; drawChecks(); } };
$("#show-checks").onclick = () => { if (state) { showChecks = true; drawChecks(); } };

const exportDialog = $("#export-dialog");
let reviewedExportIssues = [];

function drawExportIssues(issues) {
  reviewedExportIssues = issues;
  $("#export-incomplete").hidden = !issues.length;
  $("#export-draft").checked = false;
  $("#export-issues").replaceChildren(...issues.map(issue => {
    const item = document.createElement("li");
    const name = issue.label ? `${issue.label} · ${issue.name}` : issue.name;
    item.textContent = `${name}. ${issue.reason} ${issue.uses_previous ?
      "Draft uses the previous render." : "Draft omits the artwork."}`;
    return item;
  }));
  syncExportButton();
}

function syncExportButton() {
  const draft = $("#export-draft").checked;
  $("#submit-export").textContent = draft ? "Export draft" : "Export";
  $("#submit-export").disabled = reviewedExportIssues.length > 0 && !draft;
}

$("#export-draft").onchange = syncExportButton;
$("#export-format").onchange = () => {
  const format = $("#export-format").value;
  const path = $("#export-path");
  $("#dpi-field").hidden = format === "pdf";
  path.placeholder = `/path/to/figure.${format}`;
  path.value = path.value.replace(/\.(pdf|png|tiff?)$/i, `.${format}`);
};
$("#export").onclick = async () => {
  if (automaticRefresh) await automaticRefresh;
  if (!state || busy || (pendingChange && !await pendingChange) || !await saveAllDrafts()) return;
  busy = true;
  clearTimeout(refreshTimer);
  report("Preparing export…");
  try {
    state = await request("/api/export-preflight", {});
    drawRenderState();
    reportProjectStatus();
  } catch (error) {
    report(error.message);
    return;
  } finally { busy = false; }
  drawExportIssues(state.export_issues);
  const count = state.checks.length;
  $("#export-warnings").hidden = !count;
  $("#export-warnings").textContent = `Review ${count} ${count === 1 ? "warning" : "warnings"}`;
  formError("#export-error");
  const format = $("#export-format").value;
  $("#export-path").value = state.bundle.replace(/\.plate$/i, `.${format}`);
  $("#export-format").onchange();
  exportDialog.showModal();
};
$("#export-warnings").onclick = () => {
  exportDialog.close();
  $("#show-checks").click();
  $("#show-checks").focus();
};
$("#cancel-export").onclick = () => exportDialog.close();
$("#browse-export").onclick = async () => {
  const extension = $("#export-format").value;
  const kind = { pdf: "exportPDF", png: "exportPNG", tiff: "exportTIFF" }[extension];
  const input = $("#export-path");
  const path = await chooseDesktopPath(kind, input.value || state.project.name + "." + extension);
  if (path) input.value = path;
};
$("#export-form").onsubmit = async event => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  $("#export-draft").disabled = true;
  formError("#export-error");
  try {
    const result = await request("/api/export", {
      format: $("#export-format").value, dpi: Number($("#export-dpi").value), path: $("#export-path").value,
      draft: $("#export-draft").checked, reviewed_issues: reviewedExportIssues,
    });
    exportDialog.close();
    report(`Exported ${result.draft ? "draft to " : ""}${result.path}`);
  } catch (error) {
    if (error.exportIssues) drawExportIssues(error.exportIssues);
    formError("#export-error", error.message);
  } finally {
    $("#export-draft").disabled = false;
    syncExportButton();
  }
};
$("#save-script").onclick = () => { const panel = activeScript(); if (panel) saveDraft(panel); };
$("#run-script").onclick = () => runSelected();
$("#force-render").onclick = () => runSelected(true);
$("#close-editor").onclick = () => {
  editorOpen = false;
  drawEditor(activeScript());
  $("#edit-script")?.focus();
};
$("#script-actions").addEventListener("click", event => {
  if (event.target.matches("button:enabled")) $("#script-actions").hidePopover();
});
$("#dependencies").onclick = async () => {
  const panel = activeScript();
  if (!panel) return;
  try {
    const info = await request("/api/dependencies", { panel: panel.id });
    if (editorId !== panel.id) return;
    showConsole(info.missing.length ? `Missing packages: ${info.missing.join(", ")}\n${info.install}` :
      `${info.version}\n${info.path}\nRequired packages are installed.`);
  } catch (error) { if (editorId === panel.id) showConsole(error.message); }
};

async function showEnvironmentReport() {
  const dialog = $("#environment-dialog");
  const content = $("#environment-report");
  content.textContent = "Checking local interpreters and fonts…";
  dialog.showModal();
  try {
    const result = await request("/api/environment", {});
    const folder = document.createElement("p");
    folder.textContent = `Data folder ${result.data_folder}${result.data_folder_available ? "" : " (unavailable)"}`;
    content.replaceChildren(folder);
    if (!result.panels.length) {
      const empty = document.createElement("p");
      empty.textContent = "Render a panel to record its environment.";
      content.append(empty);
    }
    for (const panel of result.panels) {
      const label = document.createElement("summary");
      label.textContent = panel.name + (panel.differences.length ?
        ` · ${panel.differences.length} differences` : " · Matches");
      const details = document.createElement("details");
      details.open = panel.differences.length > 0;
      details.append(label);
      if (panel.recorded.version) {
        const interpreter = document.createElement("p");
        interpreter.textContent = `Recorded ${panel.recorded.interpreter} (${panel.recorded.version}). Local ${panel.local.interpreter || "interpreter unavailable"}.`;
        details.append(interpreter);
      }
      const changes = document.createElement("ul");
      for (const difference of panel.differences) {
        const item = document.createElement("li");
        item.textContent = `${difference.item} — recorded ${difference.recorded}, local ${difference.local ?? "unavailable"}${difference.detail ? ` (${difference.detail})` : ""}`;
        changes.append(item);
      }
      if (changes.childElementCount) details.append(changes);
      const files = document.createElement("p");
      const packages = Object.entries(panel.recorded.packages || {}).map(([name, version]) => `${name} ${version}`);
      const fonts = Object.keys(panel.recorded.fonts);
      files.textContent = [packages.length && `Packages · ${packages.join(", ")}`,
        fonts.length && `Fonts · ${fonts.join(", ")}`].filter(Boolean).join("\n");
      if (files.textContent) details.append(files);
      content.append(details);
    }
  } catch (error) { content.textContent = error.message; }
}
$("#reveal-script").onclick = async () => {
  const panel = activeScript();
  if (!panel) return;
  try { report((await request("/api/reveal-script", { panel: panel.id })).path); }
  catch (error) { report(error.message); }
};
async function refreshSelected() {
  if (automaticRefresh) await automaticRefresh;
  if (pendingChange && !await pendingChange) return;
  const panel = activeScript();
  if (panel) await runSelected();
  else if (selected) await refresh([selected]);
}
async function refreshAll() {
  if (automaticRefresh) await automaticRefresh;
  if (pendingChange && !await pendingChange) return;
  if (state && await saveAllDrafts()) await refresh();
}
$("#refresh-selected").onclick = refreshSelected;
$("#refresh-all").onclick = refreshAll;
document.addEventListener("keydown", event => {
  if (!state || $("#workspace").hidden || document.querySelector("dialog[open]") ||
      !(event.metaKey || event.ctrlKey) || event.key !== "Enter") return;
  event.preventDefault();
  if (event.shiftKey) refreshAll();
  else if (selected) refreshSelected();
});
$("#file-actions").addEventListener("click", event => {
  if (event.target.closest("button:enabled")) $("#file-actions").hidePopover();
});
$("#project-folder").onclick = async () => {
  try { report((await request("/api/reveal-workspace", {})).path); }
  catch (error) { report(error.message); }
};
function newProject() {
  switchFigure("new");
}

function newFigure() {
  const project = currentProject();
  if (project) switchFigure("new-figure", { project: project.id });
}

function openPath(path) {
  const project = $("#workspace").hidden ? null : currentProject()?.id;
  return switchFigure("open", { path, project });
}

async function openProject() {
  if (!state || busy && !automaticRefresh && !pendingChange) return;
  if (desktop) {
    const path = await chooseDesktopPath("openProject");
    if (path) await openPath(path);
    return;
  }
  askValue("Open figure", "Path to a .plate file", "Open", openPath);
}

$("#home-button").onclick = () => showHome();
$("#return-to-editor").onclick = () => showEditor();
$("#new").onclick = $("#home-new").onclick = newProject;
$("#open").onclick = $("#home-open").onclick = openProject;
$("#new-figure").onclick = newFigure;
const moveFigureDialog = $("#move-figure-dialog");
$("#move-figure").onclick = () => {
  const current = currentProject();
  const projects = library.projects.filter(project => project !== current);
  $("#move-figure-target").replaceChildren(...projects.map(project => new Option(project.name, project.id)));
  formError("#move-figure-error");
  moveFigureDialog.showModal();
};
$("#cancel-move-figure").onclick = () => moveFigureDialog.close();
$("#move-figure-form").onsubmit = async event => {
  event.preventDefault();
  if (await action("move-figure", { project: $("#move-figure-target").value })) moveFigureDialog.close();
  else formError("#move-figure-error", $("#status").textContent);
};
async function saveAllDrafts(autosave = false) {
  if (automaticRefresh) await automaticRefresh;
  if (busy) return false;
  for (const panel of state.project.panels.filter(isScript)) {
    const draft = drafts.get(panel.id);
    while (draft && draft.value !== draft.base) {
      if (!await saveDraft(panel, autosave)) return false;
    }
  }
  return true;
}

const saveDialog = $("#save-dialog");
let sharingCopy = false;
function showSaveDialog(share = false) {
  if (!state || (busy && !automaticRefresh)) return;
  sharingCopy = share;
  $("#save-title").textContent = share ? "Save shareable copy" : "Save figure";
  $("#save-form button[type=submit]").textContent = share ? "Save copy" : "Save";
  $("#bundle-path").value = share ? "" : state.bundle;
  $("#bundle-cache").checked = share || Boolean(state.keep_cache);
  const inputs = share ? [...new Set(state.project.panels.flatMap(panel => panel.input_files))] : [];
  $("#share-inputs-note").hidden = !share;
  $("#share-inputs-note").textContent = inputs.length
    ? "The copy includes the files listed in Render inputs. Use relative paths in your scripts."
    : "List any data files your scripts need under Source → Render inputs to include them in the copy.";
  $("#share-inputs").hidden = !inputs.length;
  $("#share-inputs").open = false;
  $("#share-input-files").replaceChildren(...inputs.map(path => {
    const item = document.createElement("li");
    item.textContent = path;
    return item;
  }));
  formError("#save-error");
  saveDialog.showModal();
}
$("#save-as").onclick = () => showSaveDialog();
$("#share-copy").onclick = () => showSaveDialog(true);
$("#save").onclick = async () => {
  if (!state || (busy && !automaticRefresh)) return;
  if (!state.bundle) return showSaveDialog();
  if (await saveAllDrafts()) await action("save", { cache: Boolean(state.keep_cache) });
};
$("#cancel-save").onclick = () => saveDialog.close();
$("#browse-bundle").onclick = async () => {
  const input = $("#bundle-path");
  const suggested = state.project.name + (sharingCopy ? "-shared.plate" : ".plate");
  const path = await chooseDesktopPath("saveProject", input.value || suggested);
  if (path) input.value = path;
};
$("#save-form").onsubmit = async event => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  formError("#save-error");
  try {
    if ((pendingChange && !await pendingChange) || !await saveAllDrafts()) {
      formError("#save-error", $("#status").textContent);
      return;
    }
    const options = { path: $("#bundle-path").value, cache: $("#bundle-cache").checked };
    if (sharingCopy) {
      busy = true;
      try {
        const result = await request("/api/share", options);
        saveDialog.close();
        report("Saved shareable copy to " + result.path);
      } finally { busy = false; }
    } else if (await action("save", options)) {
      saveDialog.close();
    } else {
      formError("#save-error", $("#status").textContent);
    }
  } catch (error) {
    formError("#save-error", error.message);
  } finally {
    submit.disabled = false;
  }
};
document.addEventListener("keydown", event => {
  if (!state || $("#workspace").hidden || document.querySelector("dialog[open]") ||
      !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "s") return;
  event.preventDefault();
  if (event.shiftKey) showSaveDialog();
  else $("#save").click();
});
window.addEventListener("beforeunload", event => {
  if (!state) return;
  document.activeElement?.blur();
  if (!pendingChange && !projectRename && !hasUnsavedScriptEdits()) return;
  event.preventDefault();
  event.returnValue = "";
});
document.addEventListener("visibilitychange", resumeVisibleWork);
window.addEventListener("pageshow", resumeVisibleWork);
window.addEventListener("pagehide", () => {
  clearTimeout(pollTimer);
  clearTimeout(refreshTimer);
  if (!desktop && state) {
    for (const [panel, draft] of drafts) {
      if (draft.value !== draft.base) {
        request("/api/script", { panel, base: draft.base, script: draft.value }, true).catch(() => {});
      }
    }
  }
});
$("#project-name").onchange = event => change(p => { p.name = event.target.value.trim() || "Untitled figure"; });
$("#collection-name").onchange = event => {
  const input = event.target;
  projectRename = action("rename-project", { name: input.value.trim() }).then(saved => {
    if (!saved) input.value = currentProject()?.name || "";
    return saved;
  }).finally(() => { projectRename = null; });
};

if (desktop) {
  document.documentElement.dataset.desktop = "";
  $("#browse-bundle").hidden = $("#browse-export").hidden = false;
  document.addEventListener("contextmenu", event => {
    if (!event.target.closest("input, textarea, [contenteditable], pre") && !String(getSelection())) {
      event.preventDefault();
    }
  });
  window.plateDesktopCommand = async (name, value) => {
    if (!state) return name === "prepareQuit";
    if (name === "visibility") {
      desktopVisible = value;
      resumeVisibleWork();
    } else if (name === "appearance") {
      document.documentElement.dataset.appearance = value;
    } else if (name === "prepareQuit") {
      return flushFigure();
    } else if (name === "openPath") {
      return typeof value === "string" && await openPath(value);
    } else if (name === "undo" || name === "redo") {
      const input = document.activeElement;
      if ($("#script-editor").contains(input) && editor?.history) editor.history(name === "redo");
      else if (input.matches("input, textarea, [contenteditable]")) document.execCommand(name);
      else $("#" + name).click();
    } else if (name === "new" || name === "open") {
      if (!$("dialog[open]")) $("#" + name).click();
    } else if (hasEditorProject) {
      const target = { save: "#save", saveAs: "#save-as", shareCopy: "#share-copy", newFigure: "#new-figure",
        export: "#export", refresh: "#refresh-all" }[name];
      if (target && !$("dialog[open]")) {
        if ($("#workspace").hidden) showEditor();
        $(target).click();
      }
    }
    return true;
  };
}

try {
  [state, journals] = await Promise.all([request("/api/project"), request("/api/presets")]);
  library = state.library;
  $("#home-open").disabled = $("#home-new").disabled = false;
  if (library.active) showEditor(false);
  else showHome(false);
  draw();
  revealFigureTab(figureTabs.querySelector('[aria-selected="true"]'));
  scheduleRefresh();
  findInterpreters();
  queuePoll();
  if (desktop) await desktop.postMessage({ kind: "ready" });
} catch (error) { report(error.message); }
