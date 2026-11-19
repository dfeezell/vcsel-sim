/* Visual layer-stack diagram (Vertical-style) and labelled plot toolbars.
 * Loaded before app.js; uses its globals (S, $, $$, esc, fmt, layerColor, matText, getAt, parentList, ...) at call time. */
"use strict";

/* ------------------------------------------------------------------ building blocks for the palette */
const PALETTE = {
  layer: { label: "Layer", hint: "single layer (GaAs, quarter wave)", make: () => newLayer() },
  dbr: { label: "DBR pairs", hint: "Al0.9GaAs / GaAs quarter-wave pair × 20", make: () => newGroup({ name: "DBR", repeats: 20, role: "none",
    children: [newLayer({ name: "Al0.90GaAs", x: 0.9 }), newLayer({ name: "GaAs", x: 0 })] }) },
  qw: { label: "QW + barrier", hint: "8 nm GaAs barrier + 6 nm In0.2GaAs well × 3", make: () => newGroup({ name: "Active region", repeats: 3, role: "active",
    children: [newLayer({ name: "GaAs barrier", thickness: 8, thickness_unit: "nm" }),
      newLayer({ name: "In0.2GaAs QW", material: "InGaAs", x: 0.2, thickness: 6, thickness_unit: "nm", layer_type: "active" })] }) },
  spacer: { label: "Cavity spacer", hint: "Al0.3GaAs, quarter wave, marked for tuning", make: () => newLayer({ name: "Al0.30GaAs spacer", x: 0.3, marked: true }) },
  group: { label: "Empty group", hint: "repeated block to drop layers into", make: () => newGroup({ name: "Group", repeats: 1, children: [] }) },
  oxide: { label: "Oxide layer", hint: "AlOx aperture layer, 20 nm", make: () => newLayer({ name: "AlOx", material: "AlOx", thickness: 20, thickness_unit: "nm" }) },
};

const DG = { drag: null, scale: "log" };
try { DG.scale = localStorage.getItem("vcsel-dg-scale") || "log"; } catch (_) { /* */ }

function dgHeight(d) {
  if (!(d > 0)) return 18;
  if (DG.scale === "equal") return 24;
  return Math.max(18, Math.min(80, 12 + 26 * Math.log10(1 + d / 8)));
}
function textOn(bg) {
  // pick black/white label colour for a CSS colour string
  const c = document.createElement("canvas").getContext("2d"); c.fillStyle = bg; const h = c.fillStyle;
  if (!/^#/.test(h)) return "#111";
  const r = parseInt(h.slice(1, 3), 16), g = parseInt(h.slice(3, 5), 16), b = parseInt(h.slice(5, 7), 16);
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#111" : "#fff";
}

/* Render a design as nested blocks.
 * opts: { info (node_info result), selKey, editable, prefix (id namespace) } */
function diagramHTML(design, info, opts = {}) {
  const nodes = info?.nodes || []; let k = 0;
  const ed = !!opts.editable; const selKey = opts.selKey || "";
  const bnd = (L, key, label, n) => `<div class="dg-bnd ${selKey === key ? "sel" : ""}" data-path="${key}" data-drop="${key === "top" ? "after" : "before"}">
      <span class="dg-sw" style="background:${layerColor(L)}"></span><b>${esc(L.name)}</b><span class="dg-meta">${label} · ${esc(matText(L))}${n ? ` · n ${fmt(n.n, 4)}` : ""}</span></div>`;
  const walk = (items, path) => items.map((it, i) => {
    const p = [...path, i]; const key = p.join(",");
    if (it.kind === "group") {
      const role = it.role !== "none" ? `<span class="badge role">${ROLES.find((r) => r[0] === it.role)?.[1] || it.role}</span>` : "";
      const body = it.children.length ? walk(it.children, p) : `<div class="dg-empty" data-path="${key}" data-drop="into">${ed ? "drop layers here" : "empty"}</div>`;
      return `<div class="dg-group ${selKey === key ? "sel" : ""}" data-path="${key}" ${ed ? 'draggable="true"' : ""}>
        <div class="dg-ghead" data-path="${key}" data-drop="head"><span class="dg-name">${esc(it.name)}</span>
          ${ed ? `<span class="rep">× <input type="number" min="0" step="1" value="${it.repeats}" data-rep="${key}"></span>` : `<span class="rep">× ${it.repeats}</span>`}${role}</div>
        <div class="dg-gbody"><div class="dg-rail" title="repeated ${it.repeats}×">×${it.repeats}</div><div class="dg-kids">${body}</div></div></div>`;
    }
    const ni = nodes[k++] || {};
    const bg = layerColor(it); const fg = textOn(bg);
    const h = dgHeight(ni.d);
    const tags = `${it.layer_type === "active" ? '<span class="badge active">active</span>' : ""}${it.marked ? '<span class="badge mark" title="marked for cavity tuning">λ</span>' : ""}`;
    return `<div class="dg-layer ${selKey === key ? "sel" : ""}" data-path="${key}" data-drop="layer" ${ed ? 'draggable="true"' : ""}
        style="height:${h.toFixed(1)}px;background:${bg};color:${fg}" title="${esc(it.name)} — ${esc(matText(it))}, ${fmt(ni.d, 5)} nm, n = ${fmt(ni.n, 5)}">
      <span class="dg-name">${esc(it.name)}</span>${tags}<span class="dg-meta">${esc(matText(it))} · ${fmt(ni.d, 4)} nm · n ${fmt(ni.n, 4)}</span></div>`;
  }).join("");
  return `${bnd(design.top, "top", "exit medium", info?.top)}<div class="dg-stack" data-path="stack">${walk(design.stack, ["stack"])}</div>${bnd(design.substrate, "sub", "substrate", info?.substrate)}`;
}

/* Full wafer to scale, every repeat expanded (thin strip next to the blocks). */
function stripSVG(design, info, selKey, heightPx) {
  const nodes = info?.nodes || []; const segs = []; let k = 0;
  const walk = (items, path) => items.forEach((it, i) => {
    const p = [...path, i];
    if (it.kind === "group") {
      const k0 = k; let kEnd = k0;
      for (let r = 0; r < Math.max(it.repeats, 0); r++) { k = k0; walk(it.children, p); kEnd = k; }
      if (it.repeats <= 0) { const cnt = (g) => g.children.reduce((a, c) => a + (c.kind === "group" ? cnt(c) : 1), 0); k = k0 + cnt(it); } else k = kEnd;
    } else {
      const ni = nodes[k++] || {}; segs.push({ d: ni.d || 0, c: layerColor(it), key: p.join(",") });
    }
  });
  walk(design.stack, ["stack"]);
  const tot = segs.reduce((a, s) => a + s.d, 0) || 1;
  const H = Math.max(heightPx, 100); let y = 0, y0 = null, y1 = null;
  const rects = segs.map((s) => {
    const h = (s.d / tot) * H; const r = `<rect x="0" y="${y.toFixed(3)}" width="24" height="${Math.max(h, 0.15).toFixed(3)}" fill="${s.c}" data-path="${s.key}"/>`;
    if (selKey && (s.key === selKey || s.key.startsWith(selKey + ","))) { y0 = y0 ?? y; y1 = y + h; }
    y += h; return r;
  }).join("");
  const mark = y0 == null ? "" : `<rect x="26" y="${y0.toFixed(2)}" width="6" height="${Math.max(y1 - y0, 3).toFixed(2)}" fill="#1f5fae" rx="1"/>`;
  return `<svg class="dg-strip-svg" width="34" height="${H}" viewBox="0 0 34 ${H}" preserveAspectRatio="none"><title>Whole stack to scale (${fmt(tot / 1000, 4)} µm), every repeat drawn; the blue bar marks the selection</title>${rects}${mark}</svg>`;
}

function parsePath(key) { return key.split(",").map((v) => (/^\d+$/.test(v) ? +v : v)); }
function findPath(obj, items = S.design.stack, path = ["stack"]) {
  for (let i = 0; i < items.length; i++) {
    if (items[i] === obj) return [...path, i];
    if (items[i].kind === "group") { const r = findPath(obj, items[i].children, [...path, i]); if (r) return r; }
  }
  return null;
}

/* Insert a template or move an existing node next to / into a target. where: before | after | into */
function dgDrop(src, targetKey, where) {
  let obj, srcList = null, srcIdx = -1;
  if (src.kind === "move") {
    const sp = parsePath(src.key); obj = getAt(sp); srcList = parentList(sp); srcIdx = sp[sp.length - 1];
    if (targetKey === src.key || targetKey.startsWith(src.key + ",")) return;      // onto itself / its own children
  } else { obj = PALETTE[src.tpl].make(); tagIds([obj]); }
  let tlist, tobj = null, intoStart = false;
  if (targetKey === "top") { tlist = S.design.stack; intoStart = true; }
  else if (targetKey === "sub" || targetKey === "stack") { tlist = S.design.stack; }
  else {
    const tp = parsePath(targetKey); const t = getAt(tp);
    if (where === "into" && t.kind === "group") { tlist = t.children; intoStart = true; S.collapsed?.delete(t._id); }
    else { tlist = parentList(tp); tobj = t; }
  }
  if (srcList) srcList.splice(srcIdx, 1);
  let idx;
  if (intoStart) idx = 0;
  else if (tobj) idx = tlist.indexOf(tobj) + (where === "after" ? 1 : 0);
  else idx = tlist.length;
  tlist.splice(idx, 0, obj);
  S.sel = findPath(obj) || ["top"];
  changed();
  if (src.kind !== "move") toast(`Added ${PALETTE[src.tpl].label.toLowerCase()} — edit it below`);
}

function dropWhere(el, ev) {
  const kind = el.dataset.drop; const r = el.getBoundingClientRect(); const f = (ev.clientY - r.top) / r.height;
  if (kind === "after" || kind === "before" || kind === "into") return kind;
  if (kind === "head") return f < 0.35 ? "before" : "into";
  return f < 0.5 ? "before" : "after";
}
function clearDropMarks(root) { $$(".drop-before,.drop-after,.drop-into", root).forEach((e) => e.classList.remove("drop-before", "drop-after", "drop-into")); }

/* Wire a diagram container. handlers: {onSelect(path), editable} */
function bindDiagram(root, handlers) {
  root.addEventListener("click", (e) => {
    if (e.target.matches("input")) return;
    const el = e.target.closest("[data-path]"); if (!el || !handlers.onSelect) return;
    const key = el.dataset.path; if (key === "stack") return;
    handlers.onSelect(parsePath(key));
  });
  if (!handlers.editable) return;
  root.addEventListener("change", (e) => {
    if (!e.target.dataset.rep) return;
    const g = getAt(parsePath(e.target.dataset.rep)); g.repeats = Math.max(0, parseInt(e.target.value) || 0); changed();
  });
  root.addEventListener("dragstart", (e) => {
    const el = e.target.closest("[draggable][data-path]"); if (!el) return;
    DG.drag = { kind: "move", key: el.dataset.path }; e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", el.dataset.path); el.classList.add("dragging");
  });
  root.addEventListener("dragend", (e) => { $$(".dragging", root).forEach((x) => x.classList.remove("dragging")); clearDropMarks(root); DG.drag = null; });
  root.addEventListener("dragover", (e) => {
    if (!DG.drag) return;
    const el = e.target.closest("[data-drop]"); if (!el) return;
    e.preventDefault(); e.dataTransfer.dropEffect = DG.drag.kind === "move" ? "move" : "copy";
    clearDropMarks(root); el.classList.add("drop-" + dropWhere(el, e));
  });
  root.addEventListener("dragleave", (e) => { if (!root.contains(e.relatedTarget)) clearDropMarks(root); });
  root.addEventListener("drop", (e) => {
    if (!DG.drag) return;
    const el = e.target.closest("[data-drop]"); if (!el) return;
    e.preventDefault(); const where = dropWhere(el, e); clearDropMarks(root);
    const src = DG.drag; DG.drag = null; dgDrop(src, el.dataset.path, where);
  });
}

/* ------------------------------------------------------------------ main stack panel: list / diagram views */
const VIEW = { mode: "list", wide: false };
try { VIEW.mode = localStorage.getItem("vcsel-stack-view") || "list"; VIEW.wide = localStorage.getItem("vcsel-stack-wide") === "1"; } catch (_) { /* */ }

function renderDiagramView() {
  const host = $("#stack-diagram"); if (!host || !S.design || VIEW.mode !== "diagram") return;
  const keep = $(".dg-blocks", host)?.scrollTop || 0;
  const pal = Object.entries(PALETTE).map(([k, p]) => `<span class="chip" draggable="true" data-tpl="${k}" title="Drag into the stack: ${esc(p.hint)}">${esc(p.label)}</span>`).join("");
  host.innerHTML = `<div class="dg-palette"><span class="dg-hint">Drag in:</span>${pal}
      <span class="spacer"></span><label class="dg-hint">Heights <select id="dg-scale"><option value="log">by thickness</option><option value="equal">equal</option></select></label></div>
    <div class="dg-body"><div class="dg-blocks">${diagramHTML(S.design, S.nodeInfo, { selKey: S.sel.join(","), editable: true })}</div>
      <div class="dg-strip" title="Whole stack to scale; click a layer to select it"></div></div>`;
  $("#dg-scale", host).value = DG.scale;
  $(".dg-blocks", host).scrollTop = keep;
  const strip = $(".dg-strip", host);
  strip.innerHTML = stripSVG(S.design, S.nodeInfo, S.sel.join(","), Math.max(strip.clientHeight - 4, 120));
  const sel = $(".dg-blocks .sel", host); if (sel && VIEW.scrollToSel) { sel.scrollIntoView({ block: "nearest" }); VIEW.scrollToSel = false; }
}
function initStackViews() {
  const host = $("#stack-diagram");
  bindDiagram(host, { editable: true, onSelect: (p) => { S.sel = p; renderStack(); renderProps(); } });
  host.addEventListener("change", (e) => {
    if (e.target.id === "dg-scale") { DG.scale = e.target.value; try { localStorage.setItem("vcsel-dg-scale", DG.scale); } catch (_) { /* */ } renderDiagramView(); }
  });
  host.addEventListener("dragstart", (e) => {
    const chip = e.target.closest(".chip[data-tpl]"); if (!chip) return;
    DG.drag = { kind: "tpl", tpl: chip.dataset.tpl }; e.dataTransfer.effectAllowed = "copy"; e.dataTransfer.setData("text/plain", chip.dataset.tpl);
  });
  host.addEventListener("click", (e) => {               // strip click selects
    const r = e.target.closest(".dg-strip rect[data-path]"); if (!r) return;
    S.sel = parsePath(r.dataset.path); VIEW.scrollToSel = true; renderStack(); renderProps();
  });
  $$("#view-seg button").forEach((b) => b.addEventListener("click", () => setStackView(b.dataset.view)));
  $("#btn-wide").addEventListener("click", () => setWide(!VIEW.wide));
  setStackView(VIEW.mode, false); setWide(VIEW.wide, false);
}
function setStackView(mode, render = true) {
  VIEW.mode = mode === "diagram" ? "diagram" : "list";
  try { localStorage.setItem("vcsel-stack-view", VIEW.mode); } catch (_) { /* */ }
  $$("#view-seg button").forEach((b) => b.classList.toggle("on", b.dataset.view === VIEW.mode));
  document.body.classList.toggle("view-diagram", VIEW.mode === "diagram");
  if (render) renderStack();
}
function setWide(on, render = true) {
  VIEW.wide = !!on; try { localStorage.setItem("vcsel-stack-wide", on ? "1" : "0"); } catch (_) { /* */ }
  document.body.classList.toggle("wide-stack", VIEW.wide);
  $("#btn-wide").title = VIEW.wide ? "Make the stack panel narrower" : "Make the stack panel wider";
  $("#btn-wide").classList.toggle("on", VIEW.wide);
  if (render) { renderStack(); window.dispatchEvent(new Event("resize")); }
}

/* ------------------------------------------------------------------ labelled plot toolbar */
const PLOT_TOOLS = [["zoom", "⬚ Zoom", "Drag a box to zoom (double-click the plot to reset)"], ["pan", "✥ Pan", "Drag to pan"],
  ["in", "＋", "Zoom in"], ["out", "－", "Zoom out"], ["reset", "⟲ Reset", "Reset axes"], ["png", "PNG", "Download as high-resolution PNG"], ["svg", "SVG", "Download as SVG (vector)"]];
function addPlotBar(el) {
  if (!el || el.previousElementSibling?.classList.contains("plot-bar")) return;
  const bar = document.createElement("div"); bar.className = "plot-bar";
  bar.innerHTML = PLOT_TOOLS.map(([k, l, t]) => `<button class="pb" data-pb="${k}" title="${t}">${l}</button>`).join("");
  el.parentNode.insertBefore(bar, el);
  const zoomBy = (f) => {
    if (!el.layout) return; const upd = {};
    for (const ax of Object.keys(el.layout).filter((a) => /^[xy]axis\d*$/.test(a))) {
      const r = el._fullLayout?.[ax]?.range; if (!r || el._fullLayout[ax].type === "category") continue;
      const log = el._fullLayout[ax].type === "log";
      const c = (r[0] + r[1]) / 2, h = (r[1] - r[0]) / 2 * f;
      upd[`${ax}.range`] = [c - h, c + h]; if (log) upd[`${ax}.autorange`] = false;
    }
    Plotly.relayout(el, upd);
  };
  bar.addEventListener("click", (e) => {
    const b = e.target.closest("[data-pb]"); if (!b || !el.data) return;
    const k = b.dataset.pb;
    if (k === "zoom" || k === "pan") { Plotly.relayout(el, { dragmode: k }); $$(".pb", bar).forEach((x) => x.classList.toggle("on", x === b)); }
    else if (k === "in") zoomBy(0.5);
    else if (k === "out") zoomBy(2);
    else if (k === "reset") {
      const upd = {}; for (const ax of Object.keys(el._fullLayout || {}).filter((a) => /^[xy]axis\d*$/.test(a))) upd[`${ax}.autorange`] = true;
      Plotly.relayout(el, upd);
    } else {
      Plotly.downloadImage(el, { format: k, width: el.clientWidth, height: el.clientHeight, scale: k === "png" ? 4 : 1,
        filename: `${(S.design?.name || "vcsel").replace(/[^\w.-]+/g, "_")}_${el.id.replace("plot-", "")}` });
    }
  });
  $(".pb[data-pb=zoom]", bar).classList.add("on");
}

/* ------------------------------------------------------------------ DBR tab: structure drawing + export */
function dbrDesign() {
  const D = S.dbr; if (!D) return null;
  const sp = (k) => { const s = dbrSpec(k); return newLayer({ name: s.name, material: s.material, x: s.x || 0, index_mode: s.index_mode || "model",
    n_real: s.n_real || 3.5, thickness: 0, thickness_unit: "nm", layer_type: "other" }); };
  const g = JSON.parse(JSON.stringify(D.group)); g.role = $("#dbr-role").value;
  g.name = { bottom_dbr: "N-DBR", top_dbr: "P-DBR", none: "DBR" }[g.role];
  return { name: `${$("#dbr-pairs").value}-pair DBR at ${$("#dbr-lam").value} nm`, design_wavelength: +$("#dbr-lam").value,
    temperature: S.design?.temperature ?? 23, top: sp("incident"), substrate: sp("exit"), stack: [g], notes: "Made with the DBR design tab" };
}
function renderDbrStructure() {
  const host = $("#dbr-structure"); if (!host) return;
  const d = dbrDesign(); if (!d) { host.innerHTML = ""; return; }
  let info = null; try { info = call("node_info", JSON.stringify(d)); } catch (_) { /* */ }
  host.innerHTML = `<div class="dg-title">Layer structure <span class="dg-hint">(incident medium on top)</span></div>
    <div class="dg-body small"><div class="dg-blocks">${diagramHTML(d, info, { editable: false })}</div><div class="dg-strip"></div></div>`;
  const strip = $(".dg-strip", host); strip.innerHTML = stripSVG(d, info, "", Math.max($(".dg-blocks", host).scrollHeight - 4, 120));
}
function initDbrExtras() {
  $("#btn-dbr-layers").addEventListener("click", () => {
    const d = dbrDesign(); if (!d) return;
    try { const r = call("csv_export", JSON.stringify(d), "structure", "{}"); download(`dbr_${$("#dbr-pairs").value}pairs_layers.csv`, r.csv); } catch (e) { toast(e.message, true); }
  });
  $("#btn-dbr-save").addEventListener("click", () => {
    const d = dbrDesign(); if (!d) return;
    download(`dbr_${$("#dbr-pairs").value}pairs.vcsel.json`, JSON.stringify(d, null, 1), "application/json");
  });
}
