/* VCSEL Simulator — browser front end.
 * The physics runs in Python (package vcsel_sim) inside Pyodide; this file is the GUI:
 * stack editor, property forms, plots (Plotly), exports.
 */
"use strict";

const PY_FILES = ["__init__.py", "_tables.py", "materials.py", "structure.py", "tmm.py", "laser.py", "cavity.py", "fca.py", "retarget.py",
  "vrt.py", "vrt_write.py", "export.py", "templates.py", "api.py"];

const LAYER_TYPES = [["undoped", "undoped"], ["n-type", "n-type"], ["p-type", "p-type"], ["active", "active (gain)"],
  ["dielectric", "dielectric"], ["oxide", "oxide / aperture"], ["metal", "metal"], ["other", "other"]];
const ROLES = [["none", "—"], ["top_dbr", "Top DBR"], ["bottom_dbr", "Bottom DBR"], ["active", "Active region"]];

const S = {
  py: null, api: null, design: null, sel: ["stack", 0], collapsed: new Set(), nodeInfo: null,
  materials: [], matByKey: {}, analysis: null, refl: null, layerRows: null, dirty: true, uid: 1,
};

/* ------------------------------------------------------------------ utils */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fmt(v, d = 4) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (typeof v !== "number") return String(v);
  const a = Math.abs(v);
  if (a !== 0 && (a < 1e-3 || a >= 1e6)) return v.toExponential(d - 1);
  return Number(v.toPrecision(d + 2)).toString();
}
function toast(msg, err = false, ms = 3200) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast show" + (err ? " err" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.className = "toast"), ms);
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
// Save a file. Where the browser supports it (Chrome, Edge), a "Save as" dialog lets the user pick the folder
// and the file name; elsewhere (Firefox, Safari) it is an ordinary download to the browser's download folder.
async function download(name, text, type = "text/csv") {
  const blob = text instanceof Blob ? text : new Blob([text], { type });
  if (window.showSaveFilePicker && window.isSecureContext) {
    const ext = (name.match(/(\.vcsel\.json|\.[^.]+)$/) || [""])[0];
    const desc = { ".vcsel.json": "VCSEL design", ".json": "JSON", ".csv": "CSV data", ".vrt": "Vertical file", ".png": "PNG image", ".svg": "SVG image" }[ext] || "File";
    try {
      const h = await window.showSaveFilePicker({ suggestedName: name, id: "vcsel-sim",
        types: ext ? [{ description: desc, accept: { [type || "application/octet-stream"]: [ext.endsWith(".json") ? ".json" : ext] } }] : undefined });
      const w = await h.createWritable(); await w.write(blob); await w.close();
      toast(`Saved ${h.name}`);
      return;
    } catch (e) {
      if (e && e.name === "AbortError") return;            // the user cancelled the dialog
      // any other problem (e.g. the dialog is not allowed here): fall back to a normal download
    }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
const slug = () => (S.design?.name || "vcsel").replace(/[^\w.-]+/g, "_");

/* ------------------------------------------------------------------ python bridge */
function call(fn, ...args) {
  const out = S.api[fn](...args);
  const r = JSON.parse(out);
  if (!r.ok) throw new Error(r.error);
  return r;
}
async function boot() {
  const msg = $("#loading-msg");
  try {
    S.py = await loadPyodide();
    msg.textContent = "Loading numpy…";
    await S.py.loadPackage("numpy");
    msg.textContent = "Loading the VCSEL engine…";
    S.py.FS.mkdirTree("/home/pyodide/vcsel_sim");
    const ver = Date.now();
    for (const f of PY_FILES) {
      const txt = await (await fetch(`vcsel_sim/${f}?v=${ver}`)).text();
      S.py.FS.writeFile(`/home/pyodide/vcsel_sim/${f}`, txt);
    }
    S.py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
    S.api = S.py.pyimport("vcsel_sim.api");
    S.materials = call("material_catalog").materials;
    S.materials.forEach((m) => (S.matByKey[m.key] = m));
    initMaterialsTab(); initDbrTab(); initDbrExtras(); initStackViews(); initSweepTab();
    ["#plot-field", "#plot-refl", "#plot-mat", "#plot-dbr", "#plot-dbr-pairs"].forEach((sel) => addPlotBar($(sel)));
    let start = "gaas_980";
    try { const saved = localStorage.getItem("vcsel-design"); if (saved) { setDesign(JSON.parse(saved), false); start = null; } } catch (e) { /* ignore */ }
    if (start) loadTemplate(start);
    $("#loading").classList.add("hidden");
  } catch (e) {
    console.error(e);
    msg.innerHTML = `Could not start the Python engine.<br><small>${esc(e.message)}</small>`;
  }
}

/* ------------------------------------------------------------------ design model helpers */
function newLayer(over = {}) {
  return Object.assign({ kind: "layer", name: "GaAs", material: "AlGaAs", x: 0, y: 0, thickness: 0.25, thickness_unit: "waves",
    index_mode: "model", n_real: 3.5, n_imag: 0, absorption: 0, absorption_mode: "manual", sigma_fc: null, layer_type: "undoped", doping: 0,
    apertured: false, marked: false, color: null }, over);
}
function newGroup(over = {}) {
  return Object.assign({ kind: "group", name: "Group", repeats: 1, role: "none", apertured: false, color: null,
    children: [newLayer({ name: "GaAs" }), newLayer({ name: "AlAs", x: 1 })] }, over);
}
function tagIds(items) { for (const it of items) { it._id = it._id || S.uid++; if (it.kind === "group") tagIds(it.children); } }
function stripIds(o) { return JSON.parse(JSON.stringify(o, (k, v) => (k === "_id" ? undefined : v))); }
function designJSON() { return JSON.stringify(stripIds(S.design)); }

function getAt(path) {
  if (path[0] === "top") return S.design.top;
  if (path[0] === "sub") return S.design.substrate;
  let items = S.design.stack, it = null;
  for (let i = 1; i < path.length; i++) { it = items[path[i]]; if (!it) return null; items = it.children; }
  return it;
}
function parentList(path) {
  let items = S.design.stack;
  for (let i = 1; i < path.length - 1; i++) items = items[path[i]].children;
  return items;
}

function setDesign(d, rerun = true) {
  S.design = d; tagIds(d.stack); S.collapsed.clear(); S.analysis = null; S.refl = null;
  S.sel = d.stack.length ? ["stack", 0] : ["top"];
  $("#design-lambda").value = d.design_wavelength;
  if (d.temperature == null) d.temperature = 23;
  // air / vacuum is lossless: drop any stray k left on an Air boundary in material-model mode
  for (const L of [d.top, d.substrate]) if (L && L.material === "Air" && L.index_mode !== "fixed" && L.n_imag) L.n_imag = 0;
  // "Generic" has no dispersion model: it is always a fixed n, k layer (its old model value was n = 3.5)
  const fixGeneric = (L) => { if (L && L.material === "Generic" && L.index_mode !== "fixed") { L.index_mode = "fixed"; if (!(L.n_real > 0)) L.n_real = 3.5; } };
  fixGeneric(d.top); fixGeneric(d.substrate);
  // names written by older versions with the short alloy form (Al0.90GaAs) -> full form (Al0.90Ga0.10As)
  const fixName = (L) => {
    const m = /^(Al|In)(\d*\.\d+)Ga(As|N)\b(.*)$/.exec(L.name || "");
    if (m && ["AlGaAs", "AlGaAs_Gehrsitz", "InGaAs", "AlGaN", "InGaN"].includes(L.material) && Math.abs(+m[2] - (+L.x || 0)) < 1e-3) {
      const f = matFormula(L.material, L.x, L.y); if (f) L.name = f + m[4];
    }
  };
  const walkG = (items) => items.forEach((it) => (it.kind === "group" ? walkG(it.children) : (fixGeneric(it), fixName(it)))); walkG(d.stack);
  $("#design-temp").value = d.temperature;
  $("#design-name").textContent = d.name || "Untitled";
  const lam = d.design_wavelength;
  $("#r-min").value = Math.round(lam * 0.85); $("#r-max").value = Math.round(lam * 1.15);
  changed(rerun);
}
function loadTemplate(name) {
  try {
    if (name === "ece577") {
      fetch("examples/ECE577_Final_Project_DF.vcsel.json").then((r) => r.json()).then((d) => setDesign(d));
      return;
    }
    setDesign(call("template", name).design);
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------------------ change propagation */
const persist = debounce(() => { try { localStorage.setItem("vcsel-design", designJSON()); } catch (e) { /* ignore */ } }, 500);
const HIST = { list: [], i: -1, busy: false, max: 200 };
function snapshot() {
  if (HIST.busy || !S.design) return;
  const js = designJSON();
  if (HIST.list[HIST.i] === js) return;
  HIST.list = HIST.list.slice(0, HIST.i + 1); HIST.list.push(js);
  if (HIST.list.length > HIST.max) HIST.list.shift();
  HIST.i = HIST.list.length - 1; histButtons();
}
function histButtons() { $("#btn-undo").disabled = HIST.i <= 0; $("#btn-redo").disabled = HIST.i >= HIST.list.length - 1; }
function histGo(step) {
  const j = HIST.i + step; if (j < 0 || j >= HIST.list.length) return;
  HIST.i = j; HIST.busy = true;
  const sel = S.sel;
  try {
    const d = JSON.parse(HIST.list[j]); S.design = d; tagIds(d.stack);
    $("#design-lambda").value = d.design_wavelength; $("#design-temp").value = d.temperature ?? 23;
    $("#design-name").textContent = d.name || "Untitled";
    S.sel = getAt(sel) ? sel : (d.stack.length ? ["stack", 0] : ["top"]);
    changed();
  } finally { HIST.busy = false; }
  histButtons();
}
$("#btn-undo").addEventListener("click", () => histGo(-1));
$("#btn-redo").addEventListener("click", () => histGo(1));
document.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey)) return;
  const t = e.target; if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;   // keep native text undo
  const k = e.key.toLowerCase();
  if (k === "z" && !e.shiftKey) { e.preventDefault(); histGo(-1); }
  else if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); histGo(1); }
});
function changed(rerun = true) {
  S.dirty = true; snapshot();
  try { S.nodeInfo = call("node_info", designJSON()); } catch (e) { S.nodeInfo = null; toast(e.message, true); }
  renderStack(); renderProps(); persist();
  if (rerun) autoRun();
}
const autoRun = debounce(() => runAll(), 250);

function hasActive(items = S.design.stack) {
  return items.some((it) => (it.kind === "group" ? hasActive(it.children) : it.layer_type === "active"));
}
function runAll() {
  const tab = $(".tabs button.active").dataset.tab;
  runAnalysis(false);
  if (tab === "refl") runRefl();
  if (tab === "dbr" && !S.dbr) runDbr();
  if (tab === "layers") renderLayerTable();
  if (tab === "sweep") swRefresh();
}
function runAnalysis(explicit = true) {
  if (!S.design) return;
  if (!hasActive()) {
    S.analysis = null;
    try { S.profile = call("index_profile", designJSON()); } catch (e) { toast(e.message, true); }
    plotField(); renderResults();
    renderFoot();
    if (explicit) toast("No active layer: set Layer type = active on the quantum wells to compute threshold.", true);
    return;
  }
  const opts = { normalize: $("#f-norm").value, internal_efficiency: parseFloat($("#eta-i").value) || 1, rt_model: $("#rt-model").value, confinement_model: $("#gamma-model").value,
    spacing_passive: Math.max(parseFloat($("#f-sp-p").value) || 1, 0.01), spacing_active: Math.max(parseFloat($("#f-sp-a").value) || 0.02, 0.001) };
  try {
    const t0 = performance.now();
    S.analysis = call("run_analysis", designJSON(), JSON.stringify(opts));
    S.profile = S.analysis.profile;
    S.analysis.ms = performance.now() - t0;
    const W = S.analysis.results.warnings || [];
    if (W.length) toast(W.slice(0, 3).join(" ") + (W.length > 3 ? ` (+${W.length - 3} more)` : ""), true, 9000);
  } catch (e) { S.analysis = null; toast(e.message, true); try { S.profile = call("index_profile", designJSON()); } catch (_) { /* */ } }
  plotField(); renderResults(); renderFoot();
}

/* ------------------------------------------------------------------ stack view */
// colour ramps chosen for contrast between neighbouring layers (e.g. GaAs / Al0.2Ga0.8As / AlAs)
function ramp(stops, t) {
  t = Math.min(1, Math.max(0, +t || 0));
  let k = 0; while (k < stops.length - 2 && t > stops[k + 1][0]) k++;
  const [t0, c0] = stops[k], [t1, c1] = stops[k + 1]; const f = t1 > t0 ? (t - t0) / (t1 - t0) : 0;
  const h = (c, i) => parseInt(c.slice(1 + 2 * i, 3 + 2 * i), 16);
  return "#" + [0, 1, 2].map((i) => Math.round(h(c0, i) + f * (h(c1, i) - h(c0, i))).toString(16).padStart(2, "0")).join("");
}
const AL_RAMP = [[0, "#2f6fd0"], [0.15, "#22a6b3"], [0.3, "#37b24d"], [0.5, "#94d82d"], [0.7, "#fcc419"], [0.9, "#ffa94d"], [1, "#fd7e14"]];
const MAT_COLORS = { AlGaAs: (x) => ramp(AL_RAMP, x), AlGaAs_Gehrsitz: (x) => ramp(AL_RAMP, x), InGaAs: (x) => ramp([[0, "#2f6fd0"], [0.1, "#9c36b5"], [0.3, "#c2255c"]], x),
  InGaAsP: (y) => ramp([[0, "#e599f7"], [1, "#5f3dc4"]], y), InGaAsP_xy: (x, y) => ramp([[0, "#e599f7"], [1, "#5f3dc4"]], y), InP: () => "#f783ac",
  InAlGaAs: (x) => ramp([[0.3, "#5f3dc4"], [1, "#d0bfff"]], x), AlGaInP: (x) => ramp([[0, "#a61e4d"], [0.51, "#ffc9c9"]], x), AlGaInP_Adachi: (x) => ramp([[0, "#862e9c"], [0.51, "#fcc2d7"]], x),
  GaN: () => "#1864ab", AlN: () => "#a5d8ff", AlInN: (x) => ramp([[0, "#5f3dc4"], [0.82, "#74c0fc"], [1, "#a5d8ff"]], x), Sapphire_c: () => "#e5dbff", SiO2: () => "#e9ecef",
  Si3N4: () => "#ced4da", Ta2O5: () => "#ffd43b", TiO2: () => "#fab005", TiO2_rutile: () => "#f08c00", HfO2: () => "#ffe066",
  Nb2O5: () => "#fcc419", Al2O3: () => "#d0bfff", Al2O3_film: () => "#d0bfff", AlOx: () => "#495057", Air: () => "#ffffff",
  Generic: () => "#adb5bd", Au: () => "#d4a017", Ag: () => "#c0c0c0", Ti: () => "#7d8597", Cr: () => "#6c757d", Pt: () => "#a5a5a5" };
function layerColor(L) {
  if (L.color) return L.color;
  if (L.layer_type === "active") return "#e03131";
  const f = MAT_COLORS[L.material]; return f ? f(L.x || 0, L.y || 0) : "#adb5bd";
}
/* Chemical formula for a layer's composition; alloy end points collapse to the binary / ternary
   (AlGaAs x=0 -> GaAs, x=1 -> AlAs, InGaAsP y=0 -> InP, ...). */
const EPS_X = 5e-4;
function fx(v) { const s = (+v).toFixed(3); return s.endsWith("0") ? s.slice(0, -1) : s; }
function matFormula(material, x, y) {
  x = +x || 0; y = +y || 0;
  const is0 = (v) => Math.abs(v) < EPS_X, is1 = (v, e = 1) => Math.abs(v - e) < EPS_X;
  // standard notation with both fractions: Al0.90Ga0.10As
  const tern = (a, b, rest, v) => (is0(v) ? `${b}${rest}` : is1(v) ? `${a}${rest}` : `${a}${fx(v)}${b}${fx(1 - v)}${rest}`);
  switch (material) {
    case "AlGaAs": case "AlGaAs_Gehrsitz": return tern("Al", "Ga", "As", x);
    case "InGaAs": return tern("In", "Ga", "As", x);
    case "AlGaN": return tern("Al", "Ga", "N", x);
    case "InGaN": return tern("In", "Ga", "N", x);
    case "AlInN": return tern("Al", "In", "N", x);
    case "AlGaInP": case "AlGaInP_Adachi":
      return is0(x) ? "Ga0.51In0.49P" : is1(x, 0.51) ? "Al0.51In0.49P" : `Al${fx(x)}Ga${fx(0.51 - x)}In0.49P`;
    case "InGaAsP":                                            // lattice matched to InP, Ga = y/2.197
      return is0(y = x) ? "InP" : is1(y) ? "In0.53Ga0.47As" : `In${fx(1 - y / 2.197)}Ga${fx(y / 2.197)}As${fx(y)}P${fx(1 - y)}`;
    case "InGaAsP_xy": {                                       // In(1-x)Ga(x)As(y)P(1-y)
      const grp3 = is0(x) ? "In" : is1(x) ? "Ga" : `In${fx(1 - x)}Ga${fx(x)}`;
      const grp5 = is0(y) ? "P" : is1(y) ? "As" : `As${fx(y)}P${fx(1 - y)}`;
      return grp3 + grp5;
    }
    case "InAlGaAs":                                           // (Al0.48In0.52As)_X (Ga0.47In0.53As)_(1-X)
      return is1(x) ? "Al0.48In0.52As" : is0(x) ? "In0.53Ga0.47As" : `In${fx(0.52 * x + 0.53 * (1 - x))}Al${fx(0.48 * x)}Ga${fx(0.47 * (1 - x))}As`;
    default: return null;
  }
}
const MODEL_TAG = { AlGaAs_Gehrsitz: "Gehrsitz", AlGaInP_Adachi: "Adachi" };
// escaped HTML with alloy compositions subscripted: Al0.90Ga0.10As -> Al<sub>0.90</sub>Ga<sub>0.10</sub>As
const ALLOY_RE = /([A-Z][a-z]?)(\d*\.\d+)/g;
// dielectric compounds written with integer subscripts (SiO2 -> SiO<sub>2</sub>); a fixed list, so layer names like QW1 are left alone
const COMPOUND_RE = /\b(SiO2|Si3N4|Ta2O5|TiO2|HfO2|Nb2O5|Al2O3|Ga2O3|ZrO2|MgF2|CaF2|Y2O3|Sc2O3)\b/g;
function subHTML(s) { return esc(s).replace(ALLOY_RE, "$1<sub>$2</sub>").replace(COMPOUND_RE, (m) => m.replace(/(\d+)/g, "<sub>$1</sub>")); }
// the same for SVG text (lowered, smaller tspans; works in every SVG renderer)
function subSVG(s) {
  const t = (c) => `<tspan dy="3.5" font-size="0.75em">${c}</tspan><tspan dy="-3.5">\u200b</tspan>`;
  return esc(s).replace(ALLOY_RE, (m, el, c) => el + t(c)).replace(COMPOUND_RE, (m) => m.replace(/(\d+)/g, (d) => t(d)));
}
// material labels such as AlxGa1-xAs with Unicode subscripts (AlₓGa₁₋ₓAs), for <option> text that cannot hold HTML
const LABEL_RE = /([A-Z][a-z]?)(x|y|\d*\.?\d+-x|\d*\.?\d+)(?=[A-Z(\s\/,]|$)/g;
const UNI_SUB = { 0: "₀", 1: "₁", 2: "₂", 3: "₃", 4: "₄", 5: "₅", 6: "₆", 7: "₇", 8: "₈", 9: "₉", "-": "₋", x: "ₓ", y: "ᵧ" };
function uniLabel(s) { return String(s).replace(LABEL_RE, (m, el, c) => el + [...c].map((ch) => UNI_SUB[ch] ?? ch).join("")); }
function labelHTML(s) { return esc(s).replace(LABEL_RE, (m, el, c) => `${el}<sub>${c.replace("-", "−")}</sub>`); }
function matText(L) {
  const f = matFormula(L.material, L.x, L.y);
  let t = f || L.material;
  if (f && MODEL_TAG[L.material]) t += ` [${MODEL_TAG[L.material]}]`;
  if (L.index_mode === "fixed") t += " (fixed)";
  return t;
}
/* Is this layer name one the program made up (so it may follow composition changes)? */
function isAutoName(L) {
  const n = (L.name || "").trim();
  return !n || n === L.material || n === S.matByKey[L.material]?.label || n === matFormula(L.material, L.x, L.y);
}
function renderStack() {
  const el = $("#stack"); if (!S.design) return;
  if (VIEW.mode === "diagram") { renderDiagramView(); renderFoot(); return; }
  const info = S.nodeInfo?.nodes || [];
  let k = 0; const rows = [];
  const selKey = S.sel.join(",");
  const boundary = (L, key, label) => {
    const n = key === "top" ? S.nodeInfo?.top : S.nodeInfo?.substrate;
    rows.push(`<div class="row boundary ${selKey === key ? "sel" : ""}" data-path="${key}">
      <div class="nm"><span class="caret"></span><span class="sw" style="background:${layerColor(L)}"></span><span class="t">${subHTML(L.name)}</span> <span class="badge">${label}</span></div>
      <div class="mat">${subHTML(matText(L))}</div><div class="num">∞</div><div class="num">${n ? fmt(n.n, 4) : ""}</div></div>`);
  };
  boundary(S.design.top, "top", "exit medium");
  const walk = (items, path, depth) => {
    items.forEach((it, i) => {
      const p = [...path, i]; const key = p.join(",");
      const pad = `style="padding-left:${10 + depth * 16}px"`;
      if (it.kind === "group") {
        const coll = S.collapsed.has(it._id);
        const k0 = k; const countLayers = (g) => g.children.reduce((a, c) => a + (c.kind === "group" ? countLayers(c) : 1), 0);
        const per = sumThick(it, k0, info);
        rows.push(`<div class="row group ${selKey === key ? "sel" : ""}" data-path="${key}" ${pad} title="${countLayers(it)} layer${countLayers(it) === 1 ? "" : "s"} per period, repeated ${it.repeats}×">
          <div class="nm"><span class="caret" data-toggle="${it._id}">${coll ? "▸" : "▾"}</span><span class="t">${subHTML(it.name)}</span>
          <span class="rep">× <input type="number" min="0" step="1" value="${it.repeats}" data-rep="${key}"></span>
          ${it.role !== "none" ? `<span class="badge role">${ROLES.find((r) => r[0] === it.role)?.[1] || it.role}</span>` : ""}${isGraded(it) ? `<span class="badge grade" title="${gradeTag(it)}">graded</span>` : ""}</div>
          <div class="num" title="period × repeats">${fmt(per * it.repeats, 4)}</div><div class="num"></div></div>`);
        if (!coll) walk(it.children, p, depth + 1); else k += countLeaves(it);
      } else {
        const ni = info[k++] || {};
        rows.push(`<div class="row ${selKey === key ? "sel" : ""}" data-path="${key}" ${pad}>
          <div class="nm"><span class="caret"></span><span class="sw" style="background:${layerColor(it)}"></span><span class="t">${subHTML(it.name)}</span>
          ${it.layer_type === "active" ? '<span class="badge active">active</span>' : ""}${it.marked ? '<span class="badge mark" title="marked for cavity tuning">λ</span>' : ""}</div>
          <div class="mat">${subHTML(matText(it))}</div><div class="num">${fmt(ni.d, 4)}</div><div class="num">${fmt(ni.n, 4)}</div></div>`);
      }
    });
  };
  walk(S.design.stack, ["stack"], 0);
  boundary(S.design.substrate, "sub", "substrate");
  el.innerHTML = rows.join("");
  renderFoot();
}
function renderFoot() {
  const ni = S.nodeInfo;
  $("#stack-foot").innerHTML = ni ? `<span><b>${ni.n_layers}</b> layers</span><span>total <b>${fmt(ni.total_nm / 1000, 4)}</b> µm</span>
    ${S.analysis ? `<span>λ<sub>las</sub> <b>${fmt(S.analysis.results.wavelength, 6)}</b> nm</span><span>g<sub>th</sub> <b>${fmt(S.analysis.results.threshold_gain, 5)}</b> cm⁻¹</span>` : ""}` : "";
}
function countLeaves(g) { return g.children.reduce((a, c) => a + (c.kind === "group" ? countLeaves(c) : 1), 0); }
function sumThick(g, k0, info) {
  // physical thickness of ONE period of group g, whose first leaf has DFS index k0 in info
  let k = k0;
  const period = (grp) => grp.children.reduce((t, c) => {
    if (c.kind === "group") return t + period(c) * c.repeats;
    return t + (info[k++]?.d || 0);
  }, 0);
  return period(g);
}

$("#stack").addEventListener("click", (e) => {
  const tog = e.target.closest("[data-toggle]");
  if (tog) { const id = +tog.dataset.toggle; S.collapsed.has(id) ? S.collapsed.delete(id) : S.collapsed.add(id); renderStack(); return; }
  if (e.target.matches("input")) return;
  const row = e.target.closest(".row"); if (!row) return;
  S.sel = row.dataset.path.split(",").map((v) => (/^\d+$/.test(v) ? +v : v));
  renderStack(); renderProps();
});
$("#stack").addEventListener("change", (e) => {
  if (!e.target.dataset.rep) return;
  const path = e.target.dataset.rep.split(",").map((v) => (/^\d+$/.test(v) ? +v : v));
  const g = getAt(path); g.repeats = Math.max(0, parseInt(e.target.value) || 0); changed();
});

function stackAction(act, payload) {
  const path = S.sel; const inStack = path[0] === "stack" && path.length > 1;
  const sel = inStack ? getAt(path) : null;
  const list = inStack ? parentList(path) : S.design.stack;
  const idx = inStack ? path[path.length - 1] : (path[0] === "top" ? -1 : S.design.stack.length - 1);
  const base = inStack ? path.slice(0, -1) : ["stack"];
  const insertAfter = (obj) => { tagIds([obj]); list.splice(idx + 1, 0, obj); S.sel = [...base, idx + 1]; };
  switch (act) {
    case "add-layer": {
      const tmpl = sel && sel.kind === "layer" ? Object.assign(stripIds(sel), { marked: false }) : newLayer();
      insertAfter(newLayer(tmpl)); break;
    }
    case "add-group": insertAfter(newGroup({ name: "DBR", repeats: 10 })); break;
    case "insert": insertAfter(payload); break;
    case "dup": if (!sel) return; insertAfter(stripIds(sel)); break;
    case "del": if (!sel) return; list.splice(idx, 1); S.sel = list.length ? [...base, Math.min(idx, list.length - 1)] : (base.length > 1 ? base : ["top"]); break;
    case "up": if (!sel || idx === 0) return; [list[idx - 1], list[idx]] = [list[idx], list[idx - 1]]; S.sel = [...base, idx - 1]; break;
    case "down": if (!sel || idx >= list.length - 1) return; [list[idx + 1], list[idx]] = [list[idx], list[idx + 1]]; S.sel = [...base, idx + 1]; break;
    case "indent": {
      if (!sel || idx === 0 || list[idx - 1].kind !== "group") { toast("Select an item directly below a group to move it into that group."); return; }
      const g = list[idx - 1]; list.splice(idx, 1); g.children.push(sel); S.collapsed.delete(g._id);
      S.sel = [...base, idx - 1, g.children.length - 1]; break;
    }
    case "outdent": {
      if (!sel || base.length < 2) return;
      const gpath = base; const glist = parentList(gpath); const gidx = gpath[gpath.length - 1];
      list.splice(idx, 1); glist.splice(gidx + 1, 0, sel); S.sel = [...gpath.slice(0, -1), gidx + 1]; break;
    }
    default: return;
  }
  changed();
}
$$(".stack-tools [data-act]").forEach((b) => b.addEventListener("click", () => stackAction(b.dataset.act)));

/* ------------------------------------------------------------------ properties */
function matOptions(cur) {
  const cats = {};
  S.materials.forEach((m) => (cats[m.category] = cats[m.category] || []).push(m));
  return Object.entries(cats).map(([c, ms]) => `<optgroup label="${esc(c)}">${ms.map((m) =>
    `<option value="${m.key}" ${m.key === cur ? "selected" : ""}>${esc(uniLabel(m.label))}</option>`).join("")}</optgroup>`).join("");
}
function renderProps() {
  if (window.selHighlight) setTimeout(selHighlight, 0);
  const el = $("#props"); const it = S.design && getAt(S.sel);
  if (!it) { el.innerHTML = '<div class="empty">Select a layer or group.</div>'; $("#props-title").textContent = "Properties"; return; }
  const isBoundary = S.sel[0] !== "stack";
  if (it.kind === "group") {
    $("#props-title").textContent = "Group";
    el.innerHTML = `<div class="form">
      <label>Name</label><input type="text" data-f="name" value="${esc(it.name)}">
      <label>Repetitions</label><div class="pair"><input type="number" min="0" step="1" data-f="repeats" value="${it.repeats}"><span class="hint">number of periods (DBR pairs, QWs…)</span></div>
      <label>Role</label><select data-f="role">${ROLES.map(([v, l]) => `<option value="${v}" ${v === it.role ? "selected" : ""}>${l}</option>`).join("")}</select>
      <div class="full hint">Mark the mirror groups as Top / Bottom DBR so the Reflectance tab can show each mirror from the cavity, and the loss budget can be split by region. Layers inside a group are listed top → bottom.</div>
      <label>Apertured</label><div class="pair"><input type="checkbox" data-f="apertured" ${it.apertured ? "checked" : ""} disabled><span class="hint">2D aperture analysis — coming in phase 2</span></div>
      ${gradingForm(it)}
    </div>`;
  } else {
    $("#props-title").textContent = isBoundary ? (S.sel[0] === "top" ? "Exit medium (top, semi-infinite)" : "Substrate (bottom, semi-infinite)") : "Layer";
    const m = S.matByKey[it.material] || {};
    const ni = nodeValue(S.sel);
    const canFca = !isBoundary && (it.layer_type === "n-type" || it.layer_type === "p-type");
    const useFca = canFca && it.absorption_mode === "doping";
    el.innerHTML = `<div class="form">
      <label>Name</label><input type="text" data-f="name" value="${esc(it.name)}">
      <label>Material</label><select data-f="material">${matOptions(it.material)}</select>
      ${m.x_label ? `<label>${esc(m.x_label)}</label><div class="pair"><input type="number" step="0.01" min="${m.x_range?.[0] ?? 0}" max="${m.x_range?.[1] ?? 1}" data-f="x" value="${it.x}">${ni?.eg ? `<span class="hint">E<sub>g</sub>(Γ) = ${fmt(ni.eg, 4)} eV (${fmt(1239.842 / ni.eg, 4)} nm)</span>` : ""}</div>` : ""}
      ${m.y_label ? `<label>${esc(m.y_label)}</label><input type="number" step="0.01" data-f="y" value="${it.y}">` : ""}
      <label>Index source</label>${it.material === "Generic" ? '<div class="hint">Fixed n, k (Generic has no material model)</div>' : `<div class="seg" data-seg="index_mode"><button data-v="model" class="${it.index_mode === "model" ? "on" : ""}">Material model</button><button data-v="fixed" class="${it.index_mode === "fixed" ? "on" : ""}">Fixed n, k</button></div>`}
      ${it.index_mode === "fixed" ? `<label>n (real)</label><input type="number" step="0.0001" data-f="n_real" value="${it.n_real}">` :
        `<label>n at λ<sub>design</sub></label><div class="hint">${ni ? `${fmt(ni.n, 6)} + ${fmt(ni.k, 3)} i` : "—"}</div>`}
      <label>k (added)</label><div class="pair"><input type="number" step="0.0001" data-f="n_imag" value="${it.n_imag}"><span class="hint">extinction coeff., &gt;0 = loss</span></div>
      ${isBoundary ? "" : `<label>Thickness</label><div class="pair"><input type="number" step="any" data-f="thickness" value="${it.thickness}">
        <div class="seg" data-seg="thickness_unit"><button data-v="nm" class="${it.thickness_unit === "nm" ? "on" : ""}">nm</button><button data-v="waves" class="${it.thickness_unit === "waves" ? "on" : ""}">waves</button></div></div>
        <label></label><div class="hint">${ni ? `= ${fmt(ni.d, 6)} nm physical, ${fmt(ni.n * ni.d / S.design.design_wavelength, 5)} λ optical` : ""}</div>`}
      <label>Layer type</label><select data-f="layer_type">${LAYER_TYPES.map(([v, l]) => `<option value="${v}" ${v === it.layer_type ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Doping</label><div class="pair"><input type="text" inputmode="decimal" data-f="doping" data-num="1" style="width:110px" value="${it.doping ? (+it.doping).toExponential(2).replace("e+", "e") : 0}"><span class="hint">cm⁻³${useFca ? (ni?.fca?.family === "N" && it.layer_type === "p-type" ? " — Mg concentration (absorption scales with Mg, not holes)" : "") : (canFca ? " (sets α only with “From doping” below)" : " (recorded only)")}</span></div>
      ${canFca ? `<label>Absorption α</label><div class="seg" data-seg="absorption_mode"><button data-v="manual" class="${useFca ? "" : "on"}">Manual</button><button data-v="doping" class="${useFca ? "on" : ""}">From doping</button></div>` : ""}
      ${useFca && (ni?.fca?.variants || []).length > 1 ? `<label>Model</label><select data-f="fca_model">${ni.fca.variants.map(([v, l], i) => `<option value="${v}" ${(it.fca_model || ni.fca.variants[0][0]) === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>` : ""}
      ${useFca ? `<label>σ (${ni?.fca?.family === "N" && it.layer_type === "p-type" ? "per Mg" : it.layer_type === "p-type" ? "holes" : "electrons"})</label><div class="pair"><input type="text" inputmode="decimal" data-f="sigma_fc" style="width:110px" placeholder="${ni?.fca?.sigma ? (+ni.fca.sigma).toExponential(2).replace("e+", "e") : "none"}" value="${it.sigma_fc ? (+it.sigma_fc).toExponential(2).replace("e+", "e") : ""}"><span class="hint">cm² (blank = literature value)</span></div>
      <label></label><div class="hint">α = σ·N = <b>${ni ? fmt(ni.alpha, 4) : "—"}</b> cm⁻¹ at λ<sub>design</sub>${ni?.fca?.ref ? `<br>${esc(ni.fca.ref)}` : (it.sigma_fc ? "" : "<br>No literature model for this material; enter σ.")}</div>` :
        `<label>${canFca ? "" : "Absorption α"}</label><div class="pair"><input type="number" step="0.1" data-f="absorption" value="${it.absorption}"><span class="hint">cm⁻¹ (free-carrier etc.; ${it.layer_type === "active" ? "background loss — threshold gain is added on top" : "&lt;0 = gain"})</span></div>`}
      ${isBoundary ? "" : `<label>Marked</label><div class="pair"><input type="checkbox" data-f="marked" ${it.marked ? "checked" : ""}><span class="hint">adjusted by “Tune cavity” and “Center wells” (mark one layer above and one below the wells)</span></div>
      <label>Apertured</label><div class="pair"><input type="checkbox" data-f="apertured" ${it.apertured ? "checked" : ""} disabled><span class="hint">phase 2</span></div>`}
      ${m.reference ? `<div class="full hint">Model: ${esc(m.reference)}${m.notes ? " — " + esc(m.notes) : ""}</div>` : ""}
    </div>`;
  }
}
/* ---- graded interfaces (group option) */
const GRADE_DEF = { profile: "none", thickness_nm: 20, steps: 10, keep_period: true };
function gradable(g) {
  if (!g || g.kind !== "group" || g.children.length < 2 || g.children.some((c) => c.kind === "group")) return false;
  const m = g.children.length;
  return g.children.some((A, i) => { const B = g.children[(i + 1) % m];
    return A.material === B.material && A.index_mode === "model" && B.index_mode === "model" && !!S.matByKey[A.material]?.x_label; });
}
function isGraded(g) { return !!(g && g.grading && g.grading.profile && g.grading.profile !== "none" && +g.grading.thickness_nm > 0 && gradable(g)); }
function gradeTag(g) { return isGraded(g) ? `${fmt(+g.grading.thickness_nm, 3)} nm ${g.grading.profile === "biparabolic" ? "bi-parabolic" : "linear"} grade` : ""; }
function gradingForm(g) {
  const isDbr = g.role === "top_dbr" || g.role === "bottom_dbr";
  if (!gradable(g)) return isDbr ? `<div class="full sec-h">Graded interfaces</div><div class="full hint">Grading needs a group of plain layers with the same alloy on both sides of an interface (e.g. two AlGaAs compositions).</div>` : "";
  const G = Object.assign({}, GRADE_DEF, g.grading || {}); const on = G.profile !== "none";
  return `<div class="full sec-h">Graded interfaces</div>
      <label>Grading</label><select data-f="g_profile">${[["none", "abrupt (none)"], ["linear", "linear"], ["biparabolic", "bi-parabolic (S-shaped)"]].map(([v, l]) => `<option value="${v}" ${v === G.profile ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Grade thickness</label><div class="pair"><input type="number" min="0" step="1" data-f="g_thickness_nm" value="${G.thickness_nm}" ${on ? "" : "disabled"}><span class="hint">nm per interface, centred on it</span></div>
      <label>Steps</label><div class="pair"><input type="number" min="1" max="100" step="1" data-f="g_steps" value="${G.steps}" ${on ? "" : "disabled"}><span class="hint">sub-layers per grade (${fmt(G.thickness_nm / Math.max(G.steps, 1), 3)} nm each)</span></div>
      <label>Keep Bragg period</label><div class="pair"><input type="checkbox" data-f="g_keep_period" ${G.keep_period ? "checked" : ""} ${on ? "" : "disabled"}><span class="hint">rescale the uniform parts so a period keeps its optical thickness</span></div>
      <div class="full hint">Every interface inside the group is graded, including those between periods; the group's outer faces stay abrupt. Composition follows the profile in equal-thickness steps; doping and absorption come from the nearer layer.</div>`;
}
function nodeValue(path) {
  if (!S.nodeInfo) return null;
  if (path[0] === "top") return Object.assign({ d: 0, eg: null }, S.nodeInfo.top);
  if (path[0] === "sub") return Object.assign({ d: 0, eg: null }, S.nodeInfo.substrate);
  // DFS index of this layer
  let k = 0, found = null;
  const walk = (items, p) => { items.forEach((it, i) => { const q = [...p, i]; if (it.kind === "group") walk(it.children, q); else { if (q.join(",") === path.join(",")) found = k; k++; } }); };
  walk(S.design.stack, ["stack"]);
  return found === null ? null : S.nodeInfo.nodes[found];
}
$("#props").addEventListener("change", (e) => {
  const f = e.target.dataset.f; if (!f) return;
  const it = getAt(S.sel);
  if (f.startsWith("g_")) {                                   // grading settings of a group
    const k = f.slice(2); let v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    if (k === "thickness_nm") v = Math.max(0, parseFloat(v) || 0);
    if (k === "steps") v = Math.min(100, Math.max(1, parseInt(v) || 1));
    it.grading = Object.assign({}, GRADE_DEF, it.grading || {}, { [k]: v });
    changed(); renderProps(); return;
  }
  let v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
  if (e.target.dataset.num) v = Math.abs(parseFloat(v)) || 0;
  if (f === "doping" && v > 0 && it.absorption_mode !== "doping" && (it.layer_type === "n-type" || it.layer_type === "p-type")) {
    const ni = nodeValue(S.sel);                                  // fill α from the literature model when one exists
    if (ni?.fca?.family) { it.absorption_mode = "doping"; toast("Absorption α now follows the doping (literature model). Choose “Manual” to type your own α."); }
  }
  if (f === "sigma_fc") { const t = String(v).trim(); v = t === "" ? null : (Math.abs(parseFloat(t)) || null); }
  if (e.target.type === "number") v = f === "repeats" ? Math.max(0, parseInt(v) || 0) : (parseFloat(v) || 0);
  if (f === "material" && v === "Generic" && it.index_mode !== "fixed") {   // keep the current index as the fixed value
    const ni = nodeValue(S.sel); it.index_mode = "fixed"; if (ni) it.n_real = +ni.n.toFixed(6);   // k stays the "added" k; absorption α is kept separately
  }
  if (f === "material") {
    const m = S.matByKey[v];
    if (m && it.layer_type !== "active" && ["dielectric", "metal", "oxide"].includes(m.default_type)) it.layer_type = m.default_type;
  }
  if (f === "thickness_unit") return;
  if (f === "material" || f === "x" || f === "y") {           // auto-named layers follow the composition
    const auto = isAutoName(it); it[f] = v;
    if (auto) it.name = matFormula(it.material, it.x, it.y) || it.material;
    changed(); return;
  }
  it[f] = v; changed();
});
$("#props").addEventListener("click", (e) => {
  const b = e.target.closest(".seg button"); if (!b) return;
  const f = b.parentElement.dataset.seg; const it = getAt(S.sel); const v = b.dataset.v;
  if (it[f] === v) {        // re-clicking "Material model" still clears a leftover fixed k
    if (f === "index_mode" && v === "model" && it.n_imag) { it.n_imag = 0; toast("Cleared the extra k; the material model now sets n and k"); changed(); }
    return;
  }
  if (f === "thickness_unit") {
    // keep the physical thickness when switching units
    const ni = nodeValue(S.sel); const lam = S.design.design_wavelength;
    if (ni && ni.d) it.thickness = v === "nm" ? +ni.d.toFixed(4) : +(ni.d * ni.n / lam).toFixed(6);
  }
  if (f === "index_mode" && v === "fixed") { const ni = nodeValue(S.sel); if (ni) it.n_real = +ni.n.toFixed(6); }
  if (f === "index_mode" && v === "model" && it.n_imag) { toast(`Cleared the fixed k = ${fmt(it.n_imag, 4)}; the material model now sets n and k`); it.n_imag = 0; }
  it[f] = v; changed();
});
$("#design-name").addEventListener("input", () => { S.design.name = $("#design-name").textContent.trim(); persist(); });
$("#design-temp").addEventListener("change", (e) => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) S.design.temperature = v; changed(); });
$("#design-lambda").addEventListener("change", (e) => { S.design.design_wavelength = parseFloat(e.target.value) || S.design.design_wavelength; changed(); });

/* ------------------------------------------------------------------ field plot */
// remember each plot's axis ranges after every full redraw, for the Reset button
const _plotlyReact = Plotly.react;
Plotly.react = function (el, ...args) {
  const [data, layout, config] = args;
  try { el._last = { data, layout: JSON.stringify(layout || {}), config }; } catch (_) { /* */ }
  return Promise.resolve(_plotlyReact.call(Plotly, el, ...args)).then((gd) => {
    const g = gd || el, L = g._fullLayout || {}; const home = {};
    for (const ax of Object.keys(L).filter((a) => /^[xy]axis\d*$/.test(a))) if (L[ax] && Array.isArray(L[ax].range)) home[ax] = L[ax].range.slice();
    g._home = home;
    if (g._autoLegend) placeLegend(g);
    return g;
  });
};
// legend inside the axes, in the corner where it covers the fewest data points
function placeLegend(el) {
  const L = el._fullLayout; if (!L || !L.showlegend) return;
  const lg = el.querySelector(".legend"); if (!lg) return;
  const bb = lg.getBBox ? lg.getBBox() : null; const xa = L.xaxis, ya = L.yaxis; if (!bb || !xa || !ya) return;
  // work in pixels; the legend box is padded so a curve running along its edge also counts as covered
  const W = xa._length, Hh = ya._length, PAD = 10;
  const px = (ax, v, len) => { const r = ax.range; const t = ax.type === "log" ? Math.log10(Math.max(v, 1e-300)) : v; return (t - r[0]) / (r[1] - r[0]) * len; };
  const corners = [["right", "top", 0.99, 0.98], ["left", "top", 0.01, 0.98], ["right", "bottom", 0.99, 0.02], ["left", "bottom", 0.01, 0.02]];
  // polylines of every visible trace, in plot pixels (y up)
  const lines = [];
  for (const tr of el.data || []) {
    if (tr.visible === false || tr.visible === "legendonly" || !tr.x || !tr.y) continue;
    const yax = tr.yaxis === "y2" ? L.yaxis2 : ya; if (!yax) continue;
    const step = Math.max(1, Math.floor(tr.x.length / 2000)); const pts = [];
    for (let i = 0; i < tr.x.length; i += step) {
      const v = tr.y[i]; if (v == null || !Number.isFinite(+v)) { pts.push(null); continue; }
      pts.push([px(xa, +tr.x[i], W), px(yax, +v, Hh)]);
    }
    lines.push(pts);
  }
  let best = null;
  for (const [xan, yan, x, y] of corners) {
    const bw = bb.width, bh = bb.height;
    const x0 = (xan === "right" ? x * W - bw : x * W) - PAD, x1 = x0 + bw + 2 * PAD;
    const y0 = (yan === "top" ? y * Hh - bh : y * Hh) - PAD, y1 = y0 + bh + 2 * PAD;
    const inside = (p) => p[0] >= x0 && p[0] <= x1 && p[1] >= y0 && p[1] <= y1;
    let n = 0;   // length (px) of curve inside the padded box, plus a little for each point
    for (const pts of lines) for (let i = 0; i < pts.length; i++) {
      const p = pts[i]; if (!p) continue;
      if (inside(p)) n += 3;
      const q = pts[i + 1]; if (!q) continue;
      const len = Math.hypot(q[0] - p[0], q[1] - p[1]); const k = Math.min(200, Math.ceil(len / 2));
      if (k <= 1) { if (inside(p)) n += len; continue; }
      for (let j = 0; j < k; j++) { const t = (j + 0.5) / k; if (inside([p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])])) n += len / k; }
    }
    if (!best || n < best.n - 1e-6) best = { n, xan, yan, x, y };
    if (n === 0) break;
  }
  const cur = L.legend;
  if (!best) return;
  // every corner hides a real stretch of curve (dense phase plots): put the legend under the plot instead
  if (best.n > 40) {
    if (cur.yref === "container") return;
    const h = bb.height + 12;
    plotQueue(el, () => Plotly.relayout(el, { "legend.xref": "paper", "legend.x": 0, "legend.xanchor": "left", "legend.yref": "container", "legend.y": 0.01, "legend.yanchor": "bottom",
      "margin.b": (L.margin?.b || 50) + h }));
    return;
  }
  if (cur.xanchor !== best.xan || cur.yanchor !== best.yan)
    plotQueue(el, () => Plotly.relayout(el, { "legend.x": best.x, "legend.xanchor": best.xan, "legend.y": best.y, "legend.yanchor": best.yan }));
}
// wrap long legend text at about `width` characters (Plotly legends do not wrap on their own)
function wrapLegend(html, width = 34) {
  html = html.replace(/ = /g, "&nbsp;=&nbsp;");          // keep "λ0 = 980 nm" on one line
  html = html.replace(/(\d) nm/g, "$1&nbsp;nm");
  return html.split("<br>").map((line) => {
    const words = line.split(" "); const out = []; let cur = "";
    const vis = (s) => s.replace(/<[^>]+>/g, "").replace(/&[a-z]+;/g, "x").length;
    for (const w of words) { if (cur && vis(cur) + 1 + vis(w) > width) { out.push(cur); cur = w; } else cur = cur ? cur + " " + w : w; }
    if (cur) out.push(cur); return out.join("<br>");
  }).join("<br>");
}
// alloy formula with subscripted compositions: Al0.90Ga0.10As -> Al<sub>0.90</sub>Ga<sub>0.10</sub>As
function subFormula(f) { return String(f).replace(/([A-Za-z])(\d*\.\d+|\d+)/g, "$1<sub>$2</sub>"); }
// run relayouts on one plot one after another
function plotQueue(el, fn) { el._q = (el._q || Promise.resolve()).then(fn).catch((e) => console.warn(e)); return el._q; }
window.plotQueue = plotQueue;
const PLOT_FONT = { family: "Inter, Arial, sans-serif", size: 13, color: "#18202b" };
const PLOT_CONFIG = { responsive: true, displaylogo: false, doubleClick: false, toImageButtonOptions: { format: "png", scale: 4, filename: "vcsel_plot" },
  modeBarButtonsToRemove: ["lasso2d", "select2d"], displayModeBar: false };   // labelled toolbar above each plot instead (stackviz.js)
function xmap(z, P) {
  const units = $("#f-units").value; const origin = $("#f-origin").value;
  const tot = P.total_thickness;
  const zz = origin === "top" ? z : tot - z;
  return units === "um" ? zz / 1000 : zz;
}
function plotField() {
  const P = S.profile; const el = $("#plot-field"); if (!P) return;
  const show = $("#f-show").value; const units = $("#f-units").value;
  const traces = []; const A = S.analysis;
  const nx = P.z.map((z) => xmap(z, P));
  if (show !== "E2" || !A) traces.push({ x: nx, y: P.n, name: "refractive index n", type: "scatter", mode: "lines",
    line: { color: "#1f5fae", width: 1.4, shape: "linear" }, yaxis: A && show === "both" ? "y2" : "y", hovertemplate: "n = %{y:.5f}<extra></extra>" });
  if (A && show !== "n") {
    const f = A.field;
    traces.push({ x: f.z.map((z) => xmap(z, P)), y: f.E2, name: "|E|²", type: "scatter", mode: "lines", line: { color: "#d9480f", width: 1.5 },
      yaxis: "y", hovertemplate: "|E|² = %{y:.5g}<extra></extra>" });
  }
  const shapes = []; const annotations = [];
  if ($("#f-shade").checked) {
    for (const L of P.layers) {
      let color = null;
      if (L.type === "active") color = "rgba(224,49,49,0.18)";
      else if (L.role === "top_dbr" || L.role === "bottom_dbr") continue;
      if (!color) continue;
      const a = xmap(L.z0, P), b = xmap(L.z1, P);
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: Math.min(a, b), x1: Math.max(a, b), y0: 0, y1: 1, fillcolor: color, line: { width: 0 }, layer: "below" });
    }
  }
  const nv = P.n.filter((v) => Number.isFinite(v)); const nmin = Math.min(...nv), nmax = Math.max(...nv), ns = Math.max(nmax - nmin, 0.05);
  const nRange = [nmin - 0.05 * ns, nmax + 0.06 * ns];
  const xl = `${$("#f-origin").value === "top" ? "Depth from top surface" : "Height above substrate"} (${units === "um" ? "µm" : "nm"})`;
  const normTxt = { bottom: "normalized to substrate", top: "normalized to exit medium", peak: "normalized to peak" }[$("#f-norm").value];
  const layout = {
    font: PLOT_FONT, margin: { l: 70, r: 70, t: 34, b: 56 }, paper_bgcolor: "#fff", plot_bgcolor: "#fff",
    xaxis: { title: { text: xl }, zeroline: false, showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5" },
    yaxis: { title: { text: A && show !== "n" ? `|E|² (${normTxt})` : "Refractive index n" }, zeroline: false, showline: true, mirror: !(A && show === "both"), linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5", rangemode: A && show !== "n" ? "tozero" : "normal", range: A && show !== "n" ? undefined : nRange },
    yaxis2: { title: { text: "Refractive index n", font: { color: "#1f5fae" } }, overlaying: "y", side: "right", showgrid: false, showline: true, linecolor: "#444", ticks: "outside", tickfont: { color: "#1f5fae" }, range: nRange },
    // legend between the title and the axes, so it never covers the curves (also in exported figures)
    legend: { orientation: "h", xref: "paper", x: 1, xanchor: "right", yref: "paper", y: 1.01, yanchor: "bottom", bgcolor: "rgba(0,0,0,0)", borderwidth: 0 }, shapes, annotations,
  };
  renderKpis();                       // before plotting, so the plot gets its final height
  S.fieldShapes = shapes;
  layout.shapes = shapes.concat(selShapes(P)); el._selKey = JSON.stringify(layout.shapes);
  Plotly.react(el, traces, layout, PLOT_CONFIG);
}
// faint blue band on the Field plot over the item open in the layer editor (every repeat of it)
function selShapes(P) {
  const open = typeof ED === "undefined" || !ED.float || ED.open;
  if (!open || !P || !S.design || !S.sel) return [];
  const sel = S.sel, key = sel.join("/"), out = [];
  const band = (a, b) => out.push({ type: "rect", xref: "x", yref: "paper", x0: Math.min(a, b), x1: Math.max(a, b), y0: 0, y1: 1,
    fillcolor: "rgba(28,126,214,0.20)", line: { width: 1, color: "rgba(28,126,214,0.55)" }, layer: "below" });
  if (sel[0] === "top") { band(xmap(P.z[0], P), xmap(0, P)); return out; }
  if (sel[0] === "sub") { band(xmap(P.total_thickness, P), xmap(P.z[P.z.length - 1], P)); return out; }
  // flatten the tree in the engine's order, remembering each layer's tree path
  const paths = [];
  const walk = (items, pre) => items.forEach((it, i) => {
    const q = [...pre, i];
    if (it.kind === "group") { for (let k = 0; k < Math.max(+it.repeats || 0, 0); k++) walk(it.children, q); } else paths.push(q.join("/"));
  });
  walk(S.design.stack, ["stack"]);
  if (paths.length !== P.layers.length) return [];
  let run = null;                                   // merge neighbouring selected layers into one band
  paths.forEach((pth, j) => {
    const hit = pth === key || pth.startsWith(key + "/");
    const L = P.layers[j];
    if (hit) run = run ? [run[0], L.z1] : [L.z0, L.z1];
    if ((!hit || j === paths.length - 1) && run) { band(xmap(run[0], P), xmap(run[1], P)); run = null; }
  });
  return out;
}
function selHighlight() {
  const el = $("#plot-field"); if (!el || !el.data || !S.profile) return;
  const shapes = (S.fieldShapes || []).concat(selShapes(S.profile));
  const key = JSON.stringify(shapes); if (el._selKey === key) return; el._selKey = key;
  plotQueue(el, () => Plotly.relayout(el, { shapes }));
}
window.selHighlight = selHighlight;
// keep plots fitted to their boxes when the layout around them changes (tabs, KPI rows, window size)
if (window.ResizeObserver) {
  const ro = new ResizeObserver((entries) => entries.forEach((en) => {
    const el = en.target; if (el.data && el.offsetParent) Plotly.Plots.resize(el);
  }));
  ["#plot-field", "#plot-refl", "#plot-mat", "#plot-dbr", "#plot-dbr-pairs"].forEach((sel) => { const el = $(sel); if (el) ro.observe(el); });
}
function kpi(k, v, u = "") { return `<div class="kpi"><div class="k">${k}</div><div class="v">${v}<span class="u">${u}</span></div></div>`; }
function renderKpis() {
  const el = $("#field-summary"); const A = S.analysis;
  if (!A) { el.innerHTML = hasActive() ? "" : '<div class="note">No active layer in the structure — showing the index profile only.</div>'; return; }
  const r = A.results;
  el.innerHTML = [kpi("Lasing wavelength", fmt(r.wavelength, 7), "nm"), kpi("Threshold material gain", fmt(r.threshold_gain, 6), "cm⁻¹"),
    kpi("Threshold modal gain Γg<sub>th</sub>", fmt(r.modal_gain, 5), "cm⁻¹"), kpi("Confinement Γ", fmt(r.confinement, 5)),
    kpi("Gain enhancement Γ<sub>enh</sub>", fmt(r.enhancement, 5)), kpi("α<sub>i</sub> / α<sub>m</sub>", `${fmt(r.alpha_i, 4)} / ${fmt(r.alpha_m, 4)}`, "cm⁻¹"),
    kpi("External efficiency (top / bottom)", `${fmt(r.ext_eff_top, 4)} / ${fmt(r.ext_eff_bottom, 4)}`),
    kpi("Peak |E|² / |E|² at active", `${fmt(r.peak_E2, 5)} / ${fmt(r.E2_active_max, 5)}`)].join("");
}
["#f-show", "#f-origin", "#f-units", "#f-shade"].forEach((s) => $(s).addEventListener("change", plotField));
$("#f-norm").addEventListener("change", () => runAnalysis());
$("#eta-i").addEventListener("change", () => runAnalysis());

/* ------------------------------------------------------------------ reflectance */
const PART_LABEL = { top_dbr: "Top DBR (from cavity)", bottom_dbr: "Bottom DBR (from cavity)", full_top: "Whole wafer, from top", full_bottom: "Whole wafer, from substrate" };
const PART_COLOR = { top_dbr: "#1f5fae", bottom_dbr: "#d9480f", full_top: "#2b8a3e", full_bottom: "#862e9c" };
function runRefl() {
  if (!S.design) return;
  const parts = $$(".r-part:checked").map((c) => c.value);
  if (!parts.length) { toast("Pick at least one spectrum."); return; }
  const opts = { lambda_min: +$("#r-min").value, lambda_max: +$("#r-max").value, points: +$("#r-pts").value, parts, threshold: stopThr("#r-thr") };
  try { S.refl = call("reflectance", designJSON(), JSON.stringify(opts)); } catch (e) { toast(e.message, true); return; }
  plotRefl();
}
function plotRefl() {
  const R = S.refl; if (!R) return; const mode = $("#r-mode").value; const traces = []; const errs = []; const notes = [];
  for (const [p, sp] of Object.entries(R.spectra)) {
    if (sp.error) { errs.push(`${PART_LABEL[p]}: ${sp.error}`); continue; }
    if (sp.note) notes.push(`${PART_LABEL[p]}: ${sp.note}`);
    const base = { x: sp.wavelength, type: "scatter", mode: "lines", name: PART_LABEL[p], line: { color: PART_COLOR[p], width: 1.6 } };
    if (mode === "R" || mode === "both") traces.push({ ...base, y: sp.R, hovertemplate: "R = %{y:.6f}<extra>" + PART_LABEL[p] + "</extra>" });
    if (mode === "T") traces.push({ ...base, y: sp.T, hovertemplate: "T = %{y:.4g}<extra></extra>" });
    if (mode === "loss") traces.push({ ...base, y: sp.R.map((r) => (r == null ? null : Math.max(1 - r, 1e-12))), hovertemplate: "1−R = %{y:.4g}<extra></extra>" });
    if (mode === "phase" || mode === "both") traces.push({ ...base, y: sp.phase_deg, yaxis: mode === "both" ? "y2" : "y", showlegend: mode !== "both",
      line: { color: PART_COLOR[p], width: 1.2, dash: mode === "both" ? "dot" : "solid" }, hovertemplate: "φ = %{y:.2f}°<extra></extra>" });
  }
  const yt = { R: "Reflectance R", T: "Transmission T", loss: "1 − R", phase: "Phase of r (deg)", both: "Reflectance R" }[mode];
  const layout = {
    font: PLOT_FONT, margin: { l: 70, r: mode === "both" ? 70 : 24, t: 14, b: 56 }, paper_bgcolor: "#fff", plot_bgcolor: "#fff", showlegend: legendOn("#tab-refl"),
    xaxis: { title: { text: "Wavelength (nm)" }, showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5", zeroline: false },
    yaxis: { title: { text: yt }, showline: true, mirror: mode !== "both", linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5", zeroline: false,
      type: mode === "loss" ? "log" : "linear", range: mode === "R" || mode === "both" ? [0, 1.02] : undefined, exponentformat: "power" },
    yaxis2: { title: { text: "Phase (deg, dotted)" }, overlaying: "y", side: "right", showgrid: false, range: [-180, 180], showline: true, linecolor: "#444", ticks: "outside" },
    // inside the axes, in a corner the curves rarely reach: R (and phase) plots upper left, outside the
    // stopband where the side lobes stay low; 1 − R and T plots lower left
    legend: { x: 0.01, xanchor: "left", y: mode === "loss" || mode === "T" ? 0.02 : 0.98, yanchor: mode === "loss" || mode === "T" ? "bottom" : "top",
      bgcolor: "rgba(255,255,255,0.88)", bordercolor: "#ced4da", borderwidth: 1, font: { size: 11.5 },
      title: { text: wrapLegend(`${esc(S.design.name || "Design")}, λ<sub>design</sub> = ${R.design_wavelength} nm`), font: { size: 11.5 } } },
    shapes: [{ type: "line", x0: R.design_wavelength, x1: R.design_wavelength, yref: "paper", y0: 0, y1: 1, line: { color: "#868e96", width: 1, dash: "dash" } }],
    // spectra that could not be computed: say why right on the plot, not only in the table below
    annotations: errs.map((e, i) => ({ xref: "paper", yref: "paper", x: 0.5, y: 0.5 - i * 0.16, showarrow: false, align: "center", width: 520,
      text: esc(e).replace(/(.{1,80})(\s|$)/g, "$1<br>"), font: { size: 12.5, color: "#b35c00" }, bgcolor: "#fff8e6", bordercolor: "#f0c36d", borderpad: 6 })),
  };
  $("#plot-refl")._autoLegend = true;
  Plotly.react($("#plot-refl"), traces, layout, PLOT_CONFIG);
  const rows = Object.entries(R.spectra).filter(([, sp]) => !sp.error).map(([p, sp]) => `<tr><td><span class="sw" style="display:inline-block;background:${PART_COLOR[p]}"></span> ${PART_LABEL[p]}</td>
    <td class="n">${fmt(sp.at_design.R, 7)}</td><td class="n">${fmt(sp.at_design.phase_deg, 4)}</td><td class="n">${fmt(sp.at_design.T, 4)}</td>
    <td class="n">${fmt(sp.stopband.R_max, 7)}</td><td class="n">${fmt(sp.stopband.lambda_at_max, 6)}</td>${stopCells(sp.stopband)}</tr>`);
  const thr = R.spectra && Object.values(R.spectra).find((s) => s.stopband)?.stopband.threshold;
  $("#refl-table").innerHTML = `<table class="t"><thead><tr><th>Spectrum</th><th class="r">R at λ<sub>design</sub></th><th class="r">phase (°)</th><th class="r">T at λ<sub>design</sub></th><th class="r">R<sub>max</sub></th><th class="r">λ at R<sub>max</sub> (nm)</th><th class="r">stopband, R ≥ ${thr ?? 0.99} (nm)</th><th class="r">width (nm)</th><th class="r">center (nm)</th></tr></thead><tbody>${rows.join("")}</tbody></table>
    <p class="note">The top of a DBR stopband is very flat, so λ at R<sub>max</sub> can sit several nm from the design wavelength when the two mirror materials absorb differently (the standing wave moves from the low-index layers on the short-wavelength side to the high-index layers on the long side). The stopband center is the better measure of where the mirror is centered.</p>
    ${notes.map((e) => `<p class="note">${esc(e)}</p>`).join("")}${errs.map((e) => `<p class="note" style="color:var(--warn)">${esc(e)}</p>`).join("")}`;
}
$("#btn-refl").addEventListener("click", runRefl);
$("#r-mode").addEventListener("change", plotRefl);
$("#r-thr").addEventListener("change", runRefl);
$("#tab-refl .legend-tog").addEventListener("change", plotRefl);
function stopThr(sel) { const v = parseFloat($(sel).value); return Number.isFinite(v) && v > 0 && v < 1 ? v : 0.99; }
function stopCells(st) {
  if (st.edge_short == null) return `<td class="n" colspan="3">R stays below ${st.threshold}</td>`;
  return `<td class="n">${fmt(st.edge_short, 5)} – ${fmt(st.edge_long, 5)}</td><td class="n">${fmt(st.width_nm, 4)}</td><td class="n">${fmt(st.center, 5)}</td>`;
}
$$(".r-part").forEach((c) => c.addEventListener("change", runRefl));

/* ------------------------------------------------------------------ results table */
const RES = [
  ["Operating point", [
    ["wavelength", "Lasing wavelength", "nm", "Wavelength at which the structure supports an outgoing-only field with gain"],
    ["threshold_gain", "Threshold material gain g<sub>th</sub>", "cm⁻¹", "Gain applied uniformly to all active layers", "Gth (cm^-1)"],
    ["modal_gain", "Threshold modal gain Γg<sub>th</sub>", "cm⁻¹", "= α<sub>i</sub> + α<sub>m</sub>"],
    ["photon_energy", "Photon energy", "eV"], ["lifetime_ps", "Photon lifetime τ<sub>p</sub>", "ps", "stored energy / power lost (absorption + output), with the group index n<sub>g</sub> of each layer"]]],
  ["Round-trip budget (fractions per round trip)", [
    ["rt_gain", "Round-trip gain", "", "2 g<sub>th</sub> L<sub>a</sub> Γ<sub>enh</sub>", "round trip gain"],
    ["rt_loss", "Round-trip internal loss", "", "absorption in all passive layers", "round trip loss"],
    ["rt_transmission", "Round-trip transmission (mirror loss)", "", "power leaving top + bottom", "round trip transmission"],
    ["rt_transmission_top", "   … through top", "", "", "transmission up"], ["rt_transmission_bottom", "   … through bottom", "", "", "transmission down"]]],
  ["Losses per unit length (using the energy-based L below)", [
    ["alpha_i", "Internal loss α<sub>i</sub>", "cm⁻¹", "RT loss / 2L (linear) or −ln(1 − RT loss)/2L (exact)"], ["alpha_m", "Mirror loss α<sub>m</sub>", "cm⁻¹", "(1/2L) ln(1/(R<sub>top</sub>R<sub>bottom</sub>))"],
    ["alpha_m_top", "   … top mirror", "cm⁻¹"], ["alpha_m_bottom", "   … bottom mirror", "cm⁻¹"],
    ["R_top", "Effective R<sub>top</sub>", "", "exp(−trans. up) (linear) or 1 − trans. up (exact)"], ["R_bottom", "Effective R<sub>bottom</sub>", "", "exp(−trans. down) (linear) or 1 − trans. down (exact)"]]],
  ["Confinement", [
    ["active_thickness", "Active thickness L<sub>a</sub>", "nm", "sum of active layers", "active thickness (nm)"],
    ["enhancement", "Gain enhancement Γ<sub>enh</sub>", "", "⟨|E|²⟩ over active ÷ local standing-wave mean", "gain enhancement"],
    ["confinement", "Confinement Γ (energy-weighted)", "", "share of the stored energy in the active layers: ∫<sub>a</sub> n n<sub>g</sub>|E|² ÷ ∫<sub>stack</sub> n n<sub>g</sub>|E|² (dispersive, default) or the same with n² (Γ weighting option above); the course-notes Γ = Γ<sub>enh</sub>L<sub>a</sub>/L is further up"],
    ["effective_length", "Energy length L<sub>E</sub> = Γ<sub>enh</sub>L<sub>a</sub>/Γ", "nm", "the length that makes Γ = Γ<sub>enh</sub>L<sub>a</sub>/L exact with the energy-weighted Γ; the per-length losses below use it. Not the Coldren effective cavity length (Mirrors section)"],
    ["@L_cav_between", "Cavity length (between the DBRs)", "nm", "physical thickness of all layers between the Top DBR and Bottom DBR groups"],
    ["@cavity_optical_waves", "Cavity optical thickness", "λ", "Σ n d / λ<sub>las</sub> over the layers between the DBR groups (1 = one-wavelength cavity)"]]],
  ["Mirrors at λ<sub>las</sub>", [
    ["@top.periods", "Top DBR periods", "", "repeats of the Top DBR group"],
    ["@R_top_passive", "Top DBR reflectance (from cavity)", "", "passive mirror, light incident from the cavity layer next to it"],
    ["@top.L_eff_phase", "Top DBR penetration depth", "nm", "computed: ½|dφ/dβ| of the mirror's actual reflection phase, β = 2πn/λ in the cavity layer next to it; valid for any mirror and includes material dispersion (group delay), so it is typically 10–15% longer than the dispersion-free Coldren A7.25 value in the hand-check section below"],
    ["@bottom.periods", "Bottom DBR periods", "", "repeats of the Bottom DBR group"],
    ["@R_bottom_passive", "Bottom DBR reflectance (from cavity)", "", "passive mirror, light incident from the cavity layer next to it"],
    ["@bottom.L_eff_phase", "Bottom DBR penetration depth", "nm", "computed from the reflection phase, as above"],
    ["@phase.L", "Effective cavity length L (Coldren)", "nm", "L<sub>cav</sub> + L<sub>pen,top</sub> + L<sub>pen,bot</sub>, with the computed penetration depths (compare the energy length L<sub>E</sub> above)"]]],
  ["Efficiency", [
    ["internal_efficiency", "Internal efficiency η<sub>i</sub>", "", "input"],
    ["ext_eff", "External differential efficiency", "", "η<sub>i</sub> × RT transmission / RT gain", "external efficiency"],
    ["ext_eff_top", "   … top", "", "", "external efficiency top"], ["ext_eff_bottom", "   … bottom", "", "", "external efficiency bottom"],
    ["slope_top", "Slope efficiency, top", "W/A"], ["slope_bottom", "Slope efficiency, bottom", "W/A"]]],
  ["Standing-wave field", [
    ["peak_E2", "Peak |E|²", "", "normalized as selected on the Field tab", "peak E2"],
    ["E2_active_max", "|E|² at active (max)", "", "", "E2 at active"], ["E2_active_mean", "|E|² at active (mean)", ""],
    ["E2_top", "|E|² in exit medium", "", "", "E2 top"], ["E2_bottom", "|E|² in substrate", "", "", "E2 bottom"],
    ["avg_index_rms", "Average index (|E|²-weighted rms)", "", "Vertical's 'avg core index'"], ["avg_cavity_index", "Average cavity index", "", "thickness-weighted, between DBR groups"]]],
];
function cavityRows(C, showV) {
  const span = showV ? 5 : 4;
  let h = `<tr class="sec course-toggle" title="Click to show or hide"><td colspan="${span}">${S.showCourse ? "▾" : "▸"} Hand-calculation cross-check: penetration-depth model (course notes, Coldren &amp; Corzine App. 7)</td></tr>`;
  if (!S.showCourse) return h + `<tr><td colspan="${span}" class="def">The textbook estimate L = L<sub>cav</sub> + L<sub>eff,1</sub> + L<sub>eff,2</sub>, Γ = Γ<sub>enh</sub>L<sub>a</sub>/L, used to check hand calculations. It differs from the exact values in this table because it replaces the mirrors by penetration depths; the exact values come from the computed field. Click the heading to show it.</td></tr>`;
  if (!C || !C.complete) return h + `<tr><td colspan="${span}" class="def">${esc(C?.note || "Not available.")}</td></tr>`;
  // course-notes model with Coldren A7.25 depths; the depths from the computed mirror phase are the check row
  const K = C.coldren, KV = C.coldren_vertical_enh || {}, P = C.phase || {};
  const row = (label, v, unit, def, vv) => `<tr><td>${label}</td><td class="n">${fmt(v, 6)}</td><td>${unit}</td>${showV ? `<td class="n">${vv === undefined ? "" : fmt(vv, 6)}</td>` : ""}<td class="def">${def}</td></tr>`;
  const half = Math.round(2 * K.chi) / 2;
  h += row("Cavity length L<sub>cav</sub>", C.L_cav, "nm", "physical thickness between the DBRs (active + barriers + SCH)");
  h += row(`Top DBR penetration L<sub>eff,1</sub>`, K.L_eff_top, "nm", "Coldren A7.25 (exact for a quarter-wave stack, delay measured in the mirror's average index n̄ = λ/2Λ); see the mirror table below");
  h += row(`Bottom DBR penetration L<sub>eff,2</sub>`, K.L_eff_bottom, "nm", "Coldren A7.25");
  h += row("Effective cavity length L", K.L, "nm", "L<sub>cav</sub> + L<sub>eff,1</sub> + L<sub>eff,2</sub>");
  h += row("Confinement factor Γ", K.confinement, "", "Γ<sub>enh</sub> L<sub>a</sub> / L (Vertical column: Vertical's Γ<sub>enh</sub> and round-trip values)", KV.confinement);
  h += row("Modal gain Γg<sub>th</sub>", K.modal_gain, "cm⁻¹", K.rt_model === "linear" ? "Γ g<sub>th</sub> = ⟨α<sub>i</sub>⟩ + α<sub>m</sub>" : `⟨α<sub>i</sub>⟩ + α<sub>m</sub> (exact); Γ g<sub>th</sub> = ${fmt(K.modal_gain_gamma_g, 6)}`, KV.modal_gain);
  const lin = K.rt_model === "linear", X = K.alt, xn = lin ? "exact" : "linear";
  h += row("Internal loss ⟨α<sub>i</sub>⟩", K.alpha_i, "cm⁻¹", `${lin ? "RT loss / 2L (linear, as Vertical)" : "−ln(1 − RT loss)/2L (exact)"}; ${xn}: ${fmt(X.alpha_i, 6)}`, KV.alpha_i);
  h += row("Mirror loss α<sub>m</sub>", K.alpha_m, "cm⁻¹", `(1/L) ln(1/√(R<sub>up</sub>R<sub>down</sub>))${lin ? " = RT transmission / 2L" : ""}; ${xn}: ${fmt(X.alpha_m, 6)}`, KV.alpha_m);
  h += row("R<sub>up</sub>", K.R_up, "", `${lin ? "exp(−trans. up)" : "1 − trans. up"}; ${xn}: ${fmt(X.R_up, 7)}. Passive top DBR from the cavity: ${fmt(C.R_top_passive, 7)}`, KV.R_up);
  h += row("R<sub>down</sub>", K.R_down, "", `${lin ? "exp(−trans. down)" : "1 − trans. down"}; ${xn}: ${fmt(X.R_down, 7)}. Passive bottom DBR from the cavity: ${fmt(C.R_bottom_passive, 7)}`, KV.R_down);
  h += row("Cavity optical thickness χ", K.chi, "λ", `L n<sub>eff</sub>/λ<sub>0</sub>, n<sub>eff</sub> = average core index. Nearest half-wave multiple: ${half}`, KV.chi);
  if (P.L !== undefined) h += row("L using phase penetration depths", P.L, "nm", `check: ½|dφ/dβ| of the computed mirror reflection with β = 2πn<sub>cav</sub>/λ, measured in the cavity layer next to each mirror (top ${fmt(P.L_eff_top, 5)}, bottom ${fmt(P.L_eff_bottom, 5)} nm); Γ = ${fmt(P.confinement, 5)}. For an ideal quarter-wave mirror next to its high-index layer this equals A7.25 × n̄/n<sub>cav</sub>`);
  h += `<tr class="sec"><td colspan="${span}">DBR penetration depths at λ<sub>las</sub></td></tr>`;
  h += `<tr><td colspan="${span}" style="padding:0 0 6px"><table class="t"><thead><tr><th>Mirror</th><th class="r">periods m</th><th class="r">Λ (nm)</th><th class="r">n<sub>1</sub> / n<sub>2</sub></th><th class="r">r</th><th class="r">m<sub>eff</sub></th><th class="r">κ (cm⁻¹)</th><th class="r">L<sub>eff</sub> A7.25</th><th class="r">tanh(2mr)/2κ</th><th class="r">Λ/4r</th><th class="r">λ/4Δn</th><th class="r">phase ½|dφ/dβ|</th></tr></thead><tbody>${
    [C.top, C.bottom].map((m) => `<tr><td>${esc(m.name)}${m.cavity_side_high ? ' <span class="badge">high-index layer next to cavity counted in L<sub>cav</sub></span>' : ""}${m.layers_per_period !== 2 ? ` <span class="badge">${m.layers_per_period} layers/period: n<sub>1</sub>, n<sub>2</sub> = min, max</span>` : ""}</td><td class="n">${m.periods}</td><td class="n">${fmt(m.period_nm, 6)}</td><td class="n">${fmt(m.n_low, 5)} / ${fmt(m.n_high, 5)}</td><td class="n">${fmt(m.r, 5)}</td><td class="n">${fmt(m.m_eff, 5)}</td><td class="n">${fmt(m.kappa_cm, 5)}</td><td class="n"><b>${fmt(m.L_eff, 5)}</b></td><td class="n">${fmt(m.L_eff_tanh, 5)}</td><td class="n">${fmt(m.L_eff_long, 5)}</td><td class="n">${fmt(m.L_eff_lambda, 5)}</td><td class="n">${fmt(m.L_eff_phase, 5)}</td></tr>`).join("")}</tbody></table></td></tr>`;
  return h;
}
function renderResults() {
  const el = $("#results"); const A = S.analysis;
  if (!A) { el.innerHTML = `<p class="note" style="padding-top:12px">${hasActive() ? "Run the analysis (▶ Analyze)." : "No active layer in the structure. Set Layer type = active on the gain layers."}</p>`; return; }
  const r = A.results; const V = r.vertical || {}; const showV = $("#res-vertical").checked;
  let h = `<table class="t res-table"><colgroup><col style="width:${showV ? 24 : 28}%"><col style="width:${showV ? 17 : 20}%"><col style="width:9%">${showV ? '<col style="width:17%">' : ""}<col></colgroup><thead><tr><th>Quantity</th><th class="r">Value</th><th>Unit</th>${showV ? '<th class="r">Vertical convention</th>' : ""}<th>Definition</th></tr></thead><tbody>`;
  for (const [sec, rows] of RES) {
    h += `<tr class="sec"><td colspan="${showV ? 5 : 4}">${sec}</td></tr>`;
    for (const [key, label, unit, def, vkey] of rows) {
      const val = key.startsWith("@") ? key.slice(1).split(".").reduce((o, k) => (o == null ? undefined : o[k]), r.cavity) : r[key];
      if (key.startsWith("@") && val == null) continue;
      h += `<tr><td>${label}</td><td class="n">${fmt(val, 6)}</td><td>${unit || ""}</td>${showV ? `<td class="n">${vkey && V[vkey] !== undefined ? fmt(V[vkey], 6) : ""}</td>` : ""}<td class="def">${def || ""}</td></tr>`;
    }
  }
  h += `<tr class="sec"><td colspan="${showV ? 5 : 4}">Internal loss by region (fraction per round trip)</td></tr>`;
  for (const b of r.loss_breakdown) h += `<tr><td>${esc(b.region)}</td><td class="n">${fmt(b.rt_loss, 5)}</td><td></td>${showV ? "<td></td>" : ""}<td class="def">${fmt(b.alpha_cm, 4)} cm⁻¹ of α<sub>i</sub></td></tr>`;
  h += `<tr class="sec"><td colspan="${showV ? 5 : 4}">Transfer matrix at λ<sub>las</sub> (characteristic [E,H] matrix, substrate → top)</td></tr>`;
  ["m11", "m12", "m21", "m22"].forEach((m, i) => {
    const c = r.matrix[i], cv = r.matrix_vertical[i];
    h += `<tr><td>${m}</td><td class="n cx">${fmt(c[0], 6)} ${c[1] < 0 ? "−" : "+"} ${fmt(Math.abs(c[1]), 6)}i</td><td></td>${showV ? `<td class="n cx">${fmt(cv[0], 6)} ${cv[1] < 0 ? "−" : "+"} ${fmt(Math.abs(cv[1]), 6)}i</td>` : ""}<td class="def">${i === 0 ? "this program: exp(−iωt), k&gt;0 = loss; Vertical column: Vertical's sign convention" : ""}</td></tr>`;
  });
  h += cavityRows(r.cavity, showV);
  h += `</tbody></table><p class="note">Solved in ${fmt(A.ms, 3)} ms. “Vertical convention” reproduces Vertical's numerical rules (|E|² sampled at the chosen point spacing, Γ<sub>enh</sub> relative to peak|E|²/2, transmission split by |E|² at the boundaries) for cross-checking old results; the Value column is the exact energy balance. See Help &amp; theory.</p>`;
  el.innerHTML = h;
}
$("#res-vertical").addEventListener("change", renderResults);
$("#results").addEventListener("click", (e) => { if (e.target.closest(".course-toggle")) { S.showCourse = !S.showCourse; renderResults(); } });
$("#rt-model").addEventListener("change", () => { runAnalysis(false); persistOpts(); });
$("#gamma-model").addEventListener("change", () => { runAnalysis(false); persistOpts(); });
["#f-sp-p", "#f-sp-a"].forEach((sel) => $(sel).addEventListener("change", () => { runAnalysis(false); persistOpts(); }));
function persistOpts() { try { localStorage.setItem("vcsel-sim-opts-v2", JSON.stringify({ rt: $("#rt-model").value, gm: $("#gamma-model").value, sp: $("#f-sp-p").value, sa: $("#f-sp-a").value })); } catch (_) { /* */ } }
(function restoreOpts() { try { const o = JSON.parse(localStorage.getItem("vcsel-sim-opts-v2") || "null"); if (o) { $("#rt-model").value = o.rt || "exact"; $("#gamma-model").value = o.gm || "dispersive"; $("#f-sp-p").value = o.sp || 1; $("#f-sp-a").value = o.sa || 0.02; } } catch (_) { /* */ } })();

/* ------------------------------------------------------------------ layer table */
function renderLayerTable() {
  try { S.layerRows = call("layer_table", designJSON()).layers; } catch (e) { toast(e.message, true); return; }
  const cols = [["index", "#"], ["path", "Layer"], ["material", "Material"], ["x", "x"], ["type", "Type"], ["thickness_nm", "d (nm)"], ["z_top_nm", "z top (nm)"],
    ["n", "n"], ["k", "k"], ["absorption_cm", "α (cm⁻¹)"], ["optical_thickness_waves", "n·d/λ"], ["bandgap_eV", "E<sub>g</sub> (eV)"], ["doping_cm3", "doping (cm⁻³)"]];
  // quaternaries need y as well as x
  if (S.layerRows.some((r) => S.matByKey[r.material]?.y_label)) cols.splice(4, 0, ["y", "y"]);
  $("#layers-note").innerHTML = `${S.layerRows.length} layers at λ = ${S.design.design_wavelength} nm, top → bottom`;
  $("#layer-table").innerHTML = `<table class="t"><thead><tr>${cols.map(([, l]) => `<th>${l}</th>`).join("")}</tr></thead><tbody>${S.layerRows.map((r) =>
    `<tr>${cols.map(([k]) => (typeof r[k] === "number" ? `<td class="n">${k === "index" ? r[k] : fmt(r[k], 6)}</td>` : `<td>${k === "path" || k === "material" ? subHTML(r[k] ?? "") : esc(r[k] ?? "")}</td>`)).join("")}</tr>`).join("")}</tbody></table>`;
}

/* ------------------------------------------------------------------ materials tab */
function initMaterialsTab() {
  $("#m-mat").innerHTML = matOptions("AlGaAs");
  const refs = S.materials.map((m) => `<tr><td><b>${labelHTML(m.label)}</b></td><td>${esc(m.category)}</td><td>${esc(m.reference)}</td><td class="def">${esc(m.notes || "")}</td></tr>`).join("");
  $("#mat-refs").innerHTML = `<table class="t"><thead><tr><th>Material</th><th>Family</th><th>Model / reference</th><th>Notes</th></tr></thead><tbody>${refs}</tbody></table>
  <p class="note">Any layer can instead use a fixed n, k (Index source → Fixed), e.g. to enter a measured value. Indices imported from Vertical .vrt files are fixed at the values stored in the file.</p>`;
  ["#m-mat", "#m-x", "#m-y", "#m-min", "#m-max", "#m-at"].forEach((s) => $(s).addEventListener("change", plotMaterial));
  plotMaterial();
}
function plotMaterial() {
  const key = $("#m-mat").value; const m = S.matByKey[key];
  $("#m-x-l").style.display = m.x_label ? "" : "none"; $("#m-y-l").style.display = m.y_label ? "" : "none";
  if (m.x_label) $("#m-x-l").firstChild.textContent = m.x_label + " ";
  let r; try { r = call("material_index", key, +$("#m-x").value, +$("#m-y").value, +$("#m-min").value, +$("#m-max").value, 500, S.design?.temperature ?? 23); } catch (e) { toast(e.message, true); return; }
  const tr = [{ x: r.wavelength, y: r.n, name: "n", line: { color: "#1f5fae", width: 2 } }];
  if (r.k.some((v) => v > 1e-9)) tr.push({ x: r.wavelength, y: r.k, name: "k", yaxis: "y2", line: { color: "#d9480f", width: 2, dash: "dot" } });
  const shapes = r.bandgap ? [{ type: "line", x0: 1239.842 / r.bandgap, x1: 1239.842 / r.bandgap, yref: "paper", y0: 0, y1: 1, line: { color: "#868e96", dash: "dash", width: 1 } }] : [];
  const cv = (lbl, v) => { const [sym, ...rest] = lbl.trim().split(/\s+/); return `${sym} = ${fmt(v, 4)}${rest.length ? " " + rest.join(" ") : ""}`; };
  const comp = [m.x_label ? cv(m.x_label, +$("#m-x").value) : "", m.y_label ? cv(m.y_label, +$("#m-y").value) : ""].filter(Boolean).join(", ");
  const title = `${labelHTML(m.label)}${comp ? `,&nbsp; ${comp}` : ""}${r.bandgap ? `;&nbsp;&nbsp;band gap E<sub>g</sub> = ${r.bandgap.toFixed(3)} eV (${(1239.842 / r.bandgap).toFixed(1)} nm, dashed line)` : ""}`;
  const at = parseFloat($("#m-at").value);
  if (Number.isFinite(at) && at > 0) {
    try {
      const q = call("material_index", key, +$("#m-x").value, +$("#m-y").value, at, at, 1, S.design?.temperature ?? 23);
      const n = q.n[0], k = q.k[0];
      $("#m-at-out").innerHTML = `n = <b>${fmt(n, 6)}</b>, k = <b>${fmt(k, 4)}</b>${k > 0 ? `, α = 4πk/λ = <b>${fmt(4 * Math.PI * k / (at * 1e-7), 4)}</b> cm⁻¹` : ""}`;
    } catch (e) { $("#m-at-out").textContent = e.message; }
  } else $("#m-at-out").textContent = "";
  Plotly.react($("#plot-mat"), tr, { font: PLOT_FONT, margin: { l: 64, r: 64, t: 30, b: 50 }, title: { text: title, font: { size: 13 }, x: 0.01, xanchor: "left" },
    xaxis: { title: { text: "Wavelength (nm)" }, showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5" },
    yaxis: { title: { text: "n" }, showline: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5" },
    yaxis2: { title: { text: "k" }, overlaying: "y", side: "right", showgrid: false, zeroline: false, showline: true, linecolor: "#444", ticks: "outside" },
    legend: { x: 0.99, xanchor: "right", y: 0.98, yanchor: "top", bgcolor: "rgba(255,255,255,0.85)", bordercolor: "#ced4da", borderwidth: 1 }, shapes }, PLOT_CONFIG);
  $("#plot-mat")._autoLegend = true;
}


/* ------------------------------------------------------------------ DBR design tab */
const DBR_DEFAULT = { incident: { material: "AlGaAs", x: 0 }, first: { material: "AlGaAs", x: 0.9 }, second: { material: "AlGaAs", x: 0 }, exit: { material: "AlGaAs", x: 0 } };
function initDbrTab() {
  $$(".dbr-medium").forEach((w) => {
    const k = w.dataset.k, d = DBR_DEFAULT[k];
    w.querySelector(".dbr-mat").innerHTML = matOptions(d.material);
    w.querySelector(".dbr-x").value = d.x;
    w.querySelector(".dbr-mat").addEventListener("change", () => { dbrSyncX(w); runDbr(); });
    w.querySelector(".dbr-x").addEventListener("change", runDbr);
    w.querySelector(".dbr-y").addEventListener("change", runDbr);
    dbrSyncX(w);
  });
  ["#dbr-lam", "#dbr-pairs", "#dbr-min", "#dbr-max", "#dbr-thr", "#dbr-grade", "#dbr-grade-t"].forEach((sel) => $(sel).addEventListener("change", runDbr));
  $("#dbr-pairs-mode").addEventListener("change", plotDbr);
  $("#dbr-role").addEventListener("change", () => { dbrRoleLabels(); renderDbrStructure(); });
  dbrRoleLabels();
  $("#dbr-mode").addEventListener("change", plotDbr);
  $("#tab-dbr .legend-tog").addEventListener("change", plotDbr);
  $("#btn-dbr-swap").addEventListener("click", () => {
    const a = $('.dbr-medium[data-k="first"]'), b = $('.dbr-medium[data-k="second"]');
    for (const c of [".dbr-mat", ".dbr-x", ".dbr-y"]) {
      const va = a.querySelector(c).value; a.querySelector(c).value = b.querySelector(c).value; b.querySelector(c).value = va;
    }
    dbrSyncX(a); dbrSyncX(b); runDbr();
  });
  $("#btn-dbr-insert").addEventListener("click", () => {
    if (!S.dbr) runDbr();
    if (!S.dbr) return;
    const g = dbrDesign().stack[0];                         // oriented as drawn: the 1st layer touches the cavity
    let what = "Inserted";
    if (g.role === "none") stackAction("insert", g);
    else {
      // a mirror with a role goes where that mirror belongs: replace the existing one, else at the end of the stack
      const st = S.design.stack; const i = st.findIndex((it) => it.kind === "group" && it.role === g.role);
      tagIds([g]);
      if (i >= 0) { g.name = st[i].name || g.name; st.splice(i, 1, g); S.sel = ["stack", i]; what = "Replaced the " + (g.role === "bottom_dbr" ? "bottom" : "top") + " DBR with"; }
      else if (g.role === "bottom_dbr") { st.push(g); S.sel = ["stack", st.length - 1]; }
      else { st.unshift(g); S.sel = ["stack", 0]; }
      changed();
    }
    const note = +$("#dbr-lam").value !== S.design.design_wavelength ? ` (layers are in waves, so in the stack they are quarter-wave at λdesign = ${S.design.design_wavelength} nm)` : "";
    toast(`${what} ${g.name}: ${g.repeats} pairs${note}. Undo (Ctrl+Z) restores the previous stack.`, false, 6000);
  });
  $("#btn-dbr-csv").addEventListener("click", () => {
    if (!S.dbr) return;
    const D = S.dbr, sp = D.spectrum;
    let t = `# quarter-wave DBR at ${$("#dbr-lam").value} nm, ${$("#dbr-pairs").value} pairs\nwavelength_nm,R,T,phase_deg\n`;
    for (let i = 0; i < sp.wavelength.length; i++) t += `${sp.wavelength[i]},${sp.R[i]},${sp.T[i]},${sp.phase_deg[i]}\n`;
    t += `\npairs,R_at_lambda0\n` + D.R_vs_pairs.map((r, i) => `${i + 1},${r}`).join("\n") + "\n";
    download(`dbr_${$("#dbr-pairs").value}pairs.csv`, t);
  });
}
function dbrRoleLabels() {
  const v = dbrView();
  const lbl = (k, t, tip) => { const b = $(`.dbr-medium[data-k="${k}"] .dbr-lbl`); b.textContent = t; b.title = tip; };
  lbl("incident", v.cavity ? "Cavity side" : "Incident", v.cavity ? "The cavity layer next to the mirror; light arrives from here" : "Medium the light arrives from");
  lbl("first", "1st layer", v.cavity ? "The mirror layer that touches the cavity" : "The mirror layer that touches the incident medium");
  lbl("exit", v.cavity ? (v.up ? "Exit (top)" : "Exit (substrate)") : "Exit", v.up ? "Medium above the mirror" : "Medium below the mirror");
  // a stand-alone mirror is an optical element of its own (filter, coating), not part of the VCSEL stack
  const ins = $("#btn-dbr-insert"); ins.disabled = !v.cavity;
  ins.title = v.cavity ? "Replaces the stack's existing " + (v.up ? "top" : "bottom") + " DBR group (or goes just " + (v.up ? "below the exit medium" : "above the substrate")
    + " if there is none), with the 1st layer next to the cavity. Undo restores the old stack."
    : "Stand-alone mirrors are not inserted into the VCSEL; choose Top DBR or Bottom DBR to insert. Save as design keeps a stand-alone mirror as its own file.";
}
function dbrSyncX(w) {
  const m = S.matByKey[w.querySelector(".dbr-mat").value]; const x = w.querySelector(".dbr-x");
  const generic = m && m.key === "Generic";
  x.style.display = m && (m.x_label || generic) ? "" : "none";
  x.title = generic ? "refractive index n" : (m && m.x_label) || "";
  x.placeholder = generic ? "n" : "x";
  const xl = w.querySelector(".dbr-xl");
  xl.style.display = x.style.display;
  xl.textContent = generic ? "n =" : `${((m && m.x_label) || "x").trim().split(/\s/)[0]} =`;
  xl.title = x.title;
  const y = w.querySelector(".dbr-y"), yl = w.querySelector(".dbr-yl");
  const hasY = !!(m && m.y_label);
  y.style.display = yl.style.display = hasY ? "" : "none";
  if (hasY) { yl.textContent = `${m.y_label.trim().split(/\s/)[0]} =`; y.title = yl.title = m.y_label; }
  if (generic && +x.value < 1) x.value = 3.0;
}
function dbrSpec(k) {
  const w = $(`.dbr-medium[data-k="${k}"]`); const mat = w.querySelector(".dbr-mat").value; const v = +w.querySelector(".dbr-x").value || 0;
  const m = S.matByKey[mat]; const yv = m && m.y_label ? (+w.querySelector(".dbr-y").value || 0) : 0;
  if (mat === "Generic") return { material: mat, index_mode: "fixed", n_real: v || 3, name: `n=${v}` };
  const lbl = matFormula(mat, v, yv) || (m && m.label) || mat;
  return { material: mat, x: v, y: yv, name: lbl };
}
function runDbr() {
  if (!$("#dbr-lam").value) $("#dbr-lam").value = S.design.design_wavelength;
  const lam = +$("#dbr-lam").value;
  if (!$("#dbr-min").value || !$("#dbr-max").value) { $("#dbr-min").value = Math.round(lam * 0.8); $("#dbr-max").value = Math.round(lam * 1.2); }
  const o = { lambda0: lam, pairs: +$("#dbr-pairs").value, first: dbrSpec("first"), second: dbrSpec("second"), incident: dbrSpec("incident"), exit: dbrSpec("exit"),
    lambda_min: +$("#dbr-min").value, lambda_max: +$("#dbr-max").value, points: 2001, temperature: S.design?.temperature ?? 23, threshold: stopThr("#dbr-thr") };
  $("#dbr-grade-t").disabled = $("#dbr-grade").value === "none";
  if ($("#dbr-grade").value !== "none") o.grading = { profile: $("#dbr-grade").value, thickness_nm: Math.max(0, +$("#dbr-grade-t").value || 0), steps: 10, keep_period: true };
  try { S.dbr = call("dbr_design", JSON.stringify(o)); } catch (e) { S.dbr = null; toast(e.message, true); return; }
  if (S.dbr.graded_note) toast(S.dbr.graded_note, true, 6000);
  plotDbr();
}
function dbrDesc(withPairs = true) {
  const nm = (k) => { const s = dbrSpec(k); return s.material === "Generic" ? s.name : subFormula(s.name); };
  const gr = S.dbr?.graded ? `, ${$("#dbr-grade-t").value} nm ${$("#dbr-grade").value === "biparabolic" ? "bi-parabolic" : "linear"} grades` : "";
  return wrapLegend(`${withPairs ? $("#dbr-pairs").value + "-pair " : ""}${nm("first")}/${nm("second")} DBR${gr}, λ<sub>0</sub> = ${$("#dbr-lam").value} nm<br>from ${nm("incident")}, exit ${nm("exit")}`);
}
function legendOn(tab) { const c = $(`${tab} .legend-tog`); return !c || c.checked; }
function insideLegend(where = "top") {
  return { x: 0.99, xanchor: "right", y: where === "top" ? 0.98 : 0.03, yanchor: where === "top" ? "top" : "bottom",
    bgcolor: "rgba(255,255,255,0.88)", bordercolor: "#ced4da", borderwidth: 1, font: { size: 11.5 } };
}
function plotDbr() {
  const D = S.dbr; if (!D) return;
  const mode = $("#dbr-mode").value; const sp = D.spectrum; const lam0 = +$("#dbr-lam").value;
  const y = mode === "R" ? sp.R : mode === "phase" ? sp.phase_deg : sp.R.map((r) => (r == null ? null : Math.max(1 - r, 1e-12)));
  const yt = { R: "Reflectance R", phase: "Phase of r (deg)", loss: "1 − R" }[mode];
  const desc = dbrDesc();
  $("#plot-dbr")._autoLegend = true; $("#plot-dbr-pairs")._autoLegend = true;
  const blank = sp.R.some((r) => r == null);
  $("#dbr-blank-note").textContent = blank ? `The spectrum is left blank below ${Math.round(Math.max(...sp.wavelength.filter((_, i) => sp.R[i] == null)))} nm, where the incident medium absorbs strongly and reflectance seen from inside it is not defined.` : "";
  Plotly.react($("#plot-dbr"), [{ x: sp.wavelength, y, type: "scatter", mode: "lines", name: desc, line: { color: "#1f5fae", width: 1.8 }, hovertemplate: "%{x:.2f} nm<br>%{y:.6g}<extra></extra>" }], {
    font: PLOT_FONT, margin: { l: 70, r: 24, t: 14, b: 52 }, paper_bgcolor: "#fff", plot_bgcolor: "#fff", showlegend: legendOn("#tab-dbr"),
    legend: insideLegend(mode === "loss" ? "bottom" : "top"),
    xaxis: { title: { text: "Wavelength (nm)" }, showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5", zeroline: false },
    yaxis: { title: { text: yt }, showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5", zeroline: false, type: mode === "loss" ? "log" : "linear", range: mode === "R" ? [0, 1.02] : undefined, exponentformat: "power" },
    shapes: [{ type: "line", x0: lam0, x1: lam0, yref: "paper", y0: 0, y1: 1, line: { color: "#868e96", width: 1, dash: "dash" } }],
  }, PLOT_CONFIG);
  const P = D.penetration || {};
  $("#dbr-kpis").innerHTML = [
    kpi(`R at λ<sub>0</sub> (TMM${D.graded ? ", graded" : ""} / analytic${D.graded ? ", abrupt" : ""})`, `${fmt(D.at_design.R, 7)} / ${fmt(D.R_analytic, 7)}`),
    kpi("1 − R at λ<sub>0</sub>", fmt(1 - D.at_design.R, 4)),
    kpi(`Stopband R ≥ ${D.stopband.threshold} / infinite stack`, `${D.stopband.edge_short == null ? "none" : fmt(D.stopband.width_nm, 4)} / ${fmt(D.stopband_analytic, 4)}`, "nm"),
    kpi("n<sub>1</sub> / n<sub>2</sub> at λ<sub>0</sub>", `${fmt(D.n_first, 5)} / ${fmt(D.n_second, 5)}`),
    kpi("d<sub>1</sub> / d<sub>2</sub> (λ/4)", `${fmt(D.d_first, 5)} / ${fmt(D.d_second, 5)}`, "nm"),
    kpi("Period Λ / total", `${fmt(D.period, 5)} nm / ${fmt(D.total_thickness / 1000, 4)}`, "µm"),
    kpi(`Penetration L<sub>eff</sub> (A7.25${D.graded ? ", abrupt" : ""})`, fmt(P.L_eff, 5), "nm"),
    kpi("tanh(2mr)/2κ · Λ/4r", `${fmt(P.L_eff_tanh, 5)} · ${fmt(P.L_eff_long, 5)}`, "nm"),
    kpi("r · m<sub>eff</sub> · κ", `${fmt(P.r, 4)} · ${fmt(P.m_eff, 4)} · ${fmt(P.kappa_cm, 4)}`, "κ in cm⁻¹"),
  ].join("");
  const need = Object.entries(D.pairs_needed);
  $("#dbr-table").innerHTML = `<table class="t"><thead><tr><th>Target R at λ<sub>0</sub></th><th class="r">pairs needed</th></tr></thead><tbody>${
    need.map(([t, k]) => `<tr><td>${t}</td><td class="n">${k == null ? `more than ${D.R_vs_pairs.length}` : k}</td></tr>`).join("")}</tbody></table>`;
  const ks = D.R_vs_pairs.map((_, i) => i + 1);
  const pm = $("#dbr-pairs-mode").value, lossP = pm === "loss";
  Plotly.react($("#plot-dbr-pairs"), [{ x: ks, y: lossP ? D.R_vs_pairs.map((r) => Math.max(1 - r, 1e-12)) : D.R_vs_pairs, type: "scatter", mode: "lines+markers", marker: { size: 4 }, line: { color: "#d9480f", width: 1.5 },
    name: dbrDesc(false),
    hovertemplate: lossP ? "%{x} pairs: 1−R = %{y:.3g}<extra></extra>" : "%{x} pairs: R = %{y:.6f}<extra></extra>" }], {
    font: PLOT_FONT, margin: { l: 64, r: 16, t: 28, b: 46 }, paper_bgcolor: "#fff", plot_bgcolor: "#fff",
    title: { text: `${lossP ? "1 − R" : "R"} at λ<sub>0</sub> versus number of pairs`, font: { size: 12 }, x: 0.01, xanchor: "left" },
    showlegend: legendOn("#tab-dbr"), legend: insideLegend(lossP ? "top" : "bottom"),
    xaxis: { title: { text: "pairs" }, showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5" },
    yaxis: lossP ? { type: "log", title: { text: "1 − R" }, showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5", exponentformat: "power" }
      : { type: "linear", title: { text: "R" }, range: [0, 1.02], showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5" },
    shapes: [{ type: "line", x0: +$("#dbr-pairs").value, x1: +$("#dbr-pairs").value, yref: "paper", y0: 0, y1: 1, line: { color: "#868e96", width: 1, dash: "dash" } }],
    // the curve runs to twice the chosen pairs (at least 40) so the approach to R = 1 is visible
    annotations: [{ x: +$("#dbr-pairs").value, y: lossP ? 0.02 : 0.5, xref: "x", yref: "paper", text: `${$("#dbr-pairs").value} pairs (chosen)`,
      showarrow: false, xanchor: "left", xshift: 4, font: { size: 11, color: "#495057" }, bgcolor: "rgba(255,255,255,0.8)" }],
  }, PLOT_CONFIG);
  renderDbrStructure();
}

/* ------------------------------------------------------------------ tabs, menus, files */
$$("#tabs button").forEach((b) => b.addEventListener("click", () => {
  $$("#tabs button").forEach((x) => x.classList.toggle("active", x === b));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + b.dataset.tab));
  const tab = b.dataset.tab;
  if (tab === "refl") runRefl();
  if (tab === "dbr" && !S.dbr) runDbr();
  if (tab === "layers") renderLayerTable();
  if (tab === "sweep") swRefresh();
  if (tab === "about") $("#about").innerHTML = window.ABOUT_HTML || "";
  window.dispatchEvent(new Event("resize"));
}));
document.addEventListener("click", (e) => {
  const m = e.target.closest("[data-menu]");
  $$(".menu-list").forEach((l) => { if (!m || l.id !== "menu-" + m.dataset.menu) l.classList.remove("open"); });
  if (m) $("#menu-" + m.dataset.menu).classList.toggle("open");
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-act]"); if (!b || b.closest(".stack-tools")) return;
  const act = b.dataset.act;
  if (act === "new-blank") setDesign({ name: "New design", design_wavelength: 980, top: newLayer({ name: "Air", material: "Air", thickness: 0, thickness_unit: "nm", layer_type: "other" }),
    substrate: newLayer({ name: "GaAs substrate", thickness: 0, thickness_unit: "nm", layer_type: "n-type" }), stack: [newLayer({ thickness: 0.5 })], notes: "" });
  else if (act.startsWith("tpl-")) loadTemplate(act.slice(4));
  else if (act === "open") $("#file-input").click();
  else if (act === "save") download(`${slug()}.vcsel.json`, JSON.stringify(stripIds(S.design), null, 1), "application/json");
  else if (act === "save-vrt") {
    try {
      const r = call("export_vrt", designJSON(), S.analysis?.results?.threshold_gain ?? 0);
      const bin = atob(r.b64); const bytes = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      download(`${slug()}.vrt`, bytes, "application/octet-stream");
      toast("Saved for the old Vertical: all layers use fixed n, k at the design wavelength", false, 6000);
    } catch (err) { toast("Could not write the .vrt: " + err.message, true, 6000); }
  }
  else if (act.startsWith("csv-")) exportCSV(act.slice(4));
});
$("#file-input").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return; e.target.value = "";
  try {
    if (f.name.toLowerCase().endsWith(".vrt")) {
      const buf = new Uint8Array(await f.arrayBuffer());
      const pyb = S.py.toPy(Array.from(buf));
      const r = JSON.parse(S.api.import_vrt_bytes(pyb, f.name)); pyb.destroy();
      if (!r.ok) throw new Error(r.error);
      setDesign(r.design);
      const tp = r.design.top; const fake = /air/i.test(tp.name) && tp.material !== "Air";
      toast(fake ? `Imported ${f.name}. Note: Vertical stored its top "${tp.name}" as n = ${fmt(tp.n_real, 4)} − ${fmt(tp.n_imag, 4)}i, not real air (kept so results match Vertical; set the exit medium to Air for physical results).`
        : `Imported ${f.name} from Vertical`, false, fake ? 12000 : undefined);
    } else {
      const d = JSON.parse(await f.text());
      if (!d.stack || !d.top || !d.substrate) throw new Error("Not a VCSEL design file");
      setDesign(d); toast(`Opened ${f.name}`);
    }
  } catch (err) { toast("Could not open file: " + err.message, true, 6000); }
});
function noActive() {
  const walk = (items) => items.some((it) => (it.kind === "group" ? walk(it.children) : it.layer_type === "active"));
  return !(S.design && walk(S.design.stack));
}
function exportCSV(kind) {
  try {
    if (kind === "field") {
      const A = S.analysis;
      if (!A) throw new Error(noActive() ? "No |E|² field: the design has no active layer, so there is no lasing mode. File ▸ Export CSV ▸ Index profile gives the index profile." : "Run the analysis first");
      const f = A.field; let t = `# ${S.design.name}\n# lasing wavelength ${A.results.wavelength} nm, |E|^2 normalized to ${A.results.normalization}\n# z measured from the top surface (nm)\nz_nm,E2,n\n`;
      for (let i = 0; i < f.z.length; i++) t += `${f.z[i]},${f.E2[i]},${f.n[i]}\n`;
      return download(`${slug()}_field.csv`, t);
    }
    if (kind === "reflectance") {
      if (!S.refl) runRefl(); const R = S.refl; if (!R) throw new Error("No spectra");
      const parts = Object.entries(R.spectra).filter(([, s]) => !s.error);
      let t = `# ${S.design.name}: passive reflectance (no gain)\nwavelength_nm,${parts.map(([p]) => `R_${p},phase_deg_${p},T_${p}`).join(",")}\n`;
      const lam = parts[0][1].wavelength;
      for (let i = 0; i < lam.length; i++) t += `${lam[i]},${parts.map(([, s]) => `${s.R[i]},${s.phase_deg[i]},${s.T[i]}`).join(",")}\n`;
      return download(`${slug()}_reflectance.csv`, t);
    }
    if (kind === "results" && !S.analysis) throw new Error(noActive() ? "No threshold results: the design has no active layer (set Layer type = active on the gain layers)." : "Run the analysis first");
    const payload = kind === "results" ? { results: S.analysis.results } : {};
    const r = call("csv_export", designJSON(), kind, JSON.stringify(payload));
    download(`${slug()}_${kind}.${kind === "inputs" ? "json" : "csv"}`, r.csv, kind === "inputs" ? "application/json" : "text/csv");
  } catch (e) { toast(e.message, true); }
}
$$("[data-export]").forEach((b) => b.addEventListener("click", () => {
  const el = $("#" + b.dataset.export); const fmtx = b.dataset.fmt;
  const w = el.clientWidth, h = el.clientHeight;
  Plotly.downloadImage(el, { format: fmtx, width: w, height: h, scale: fmtx === "png" ? 4 : 1, filename: `${slug()}_${b.dataset.export.replace("plot-", "")}` });
}));
$("#btn-run").addEventListener("click", () => { runAnalysis(true); renderStack(); });
document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runAnalysis(true); } });
$("#btn-tune").addEventListener("click", () => {
  try {
    const r = call("tune_cavity", designJSON(), S.design.design_wavelength);
    const rep = r.report;
    // copy the tuned thicknesses back, keeping ids / selection
    const walkPair = (a, b) => a.forEach((it, i) => { if (it.kind === "group") walkPair(it.children, b[i].children); else it.thickness = b[i].thickness; });
    walkPair(S.design.stack, r.design.stack);
    changed(false); runAll();
    if (rep.converged) toast(`Tuned ${rep.layers.length} ${rep.chosen || "marked layer(s)"} by ×${rep.scale.toFixed(5)}: cavity resonance ${rep.resonance.toFixed(4)} nm`, false, 5000);
    else toast(`Tune cavity failed: no thickness of the ${rep.chosen || "marked layer(s)"} between 2% and 10× of the present value puts the resonance at ${fmt(S.design.design_wavelength, 6)} nm (closest ${rep.resonance.toFixed(2)} nm). The design is unchanged. Mark a thicker layer, or a layer on the other side of the wells.`, true, 9000);
  } catch (e) { toast(e.message, true, 6000); }
});
$("#btn-center").addEventListener("click", () => {
  toast("Centering the wells on the standing wave…", false, 20000);
  setTimeout(() => {
    try {
      const r = call("center_wells", designJSON(), S.design.design_wavelength);
      const rep = r.report;
      const walkPair = (a, b) => a.forEach((it, i) => { if (it.kind === "group") walkPair(it.children, b[i].children); else it.thickness = +(+b[i].thickness).toPrecision(9); });
      walkPair(S.design.stack, r.design.stack);
      changed(false); runAll();
      const ch = (x) => `${x.name} ${fmt(x.old, 5)} → ${fmt(x.new, 5)} ${x.unit}`;
      toast(`Wells centered: Γenh ${fmt(rep.enhancement_before, 4)} → ${fmt(rep.enhancement_after, 4)}, resonance ${fmt(rep.resonance, 7)} nm. ${[...rep.above, ...rep.below].map(ch).join("; ")}.` +
        (rep.at_limit ? " The upper layer reached its minimum thickness: mark a thicker layer above the wells to center them fully." : "") + " Undo reverts it.", !!rep.at_limit, 10000);
    } catch (e) { toast(e.message, true, 9000); }
  }, 30);
});

boot();
