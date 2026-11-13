const $ = selector => document.querySelector(selector);
let state;
let journals;

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

async function change(mutate) {
  const project = structuredClone(state.project);
  mutate(project);
  try {
    state = await request("/api/project", project);
    draw();
  } catch (error) { report(error.message); }
}

function draw() {
  const { project, bundle } = state;
  $("#project-name").value = project.name;
  $("#measure").textContent = `${project.size.width_mm} × ${project.size.height_mm} mm`;
  $("#frame").style.width = `${project.size.width_mm * 3.1}px`;
  $("#frame").style.height = `${project.size.height_mm * 3.1}px`;
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
  report(bundle || "Working copy · Save to create a .plate bundle");
}

async function action(name, data = {}) {
  try { state = await request(`/api/${name}`, data); draw(); }
  catch (error) { report(error.message); }
}

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
