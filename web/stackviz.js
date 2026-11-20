/* Visual layer-stack diagram (Vertical-style) and labelled plot toolbars.
 * Loaded before app.js; uses its globals (S, $, $$, esc, fmt, layerColor, matText, getAt, parentList, ...) at call time. */
"use strict";

/* ------------------------------------------------------------------ building blocks for the palette */
const PALETTE = {
  layer: { label: "Layer", hint: "single layer (GaAs, quarter wave)", make: () => newLayer() },
  dbr: { label: "DBR", hint: "Al0.9GaAs / GaAs quarter-wave pair × 20", make: () => newGroup({ name: "DBR", repeats: 20, role: "none",
    children: [newLayer({ name: "Al0.90GaAs", x: 0.9 }), newLayer({ name: "GaAs", x: 0 })] }) },
  qw: { label: "QWs", hint: "8 nm GaAs barrier + 6 nm In0.2GaAs well × 3", make: () => newGroup({ name: "Active region", repeats: 3, role: "active",
    children: [newLayer({ name: "GaAs barrier", thickness: 8, thickness_unit: "nm" }),
      newLayer({ name: "In0.2GaAs QW", material: "InGaAs", x: 0.2, thickness: 6, thickness_unit: "nm", layer_type: "active" })] }) },
  spacer: { label: "Spacer", hint: "Al0.3GaAs, quarter wave, marked for tuning", make: () => newLayer({ name: "Al0.30GaAs spacer", x: 0.3, marked: true }) },
  group: { label: "Group", hint: "repeated block to drop layers into", make: () => newGroup({ name: "Group", repeats: 1, children: [] }) },
  oxide: { label: "Oxide", hint: "AlOx aperture layer, 20 nm", make: () => newLayer({ name: "AlOx", material: "AlOx", thickness: 20, thickness_unit: "nm" }) },
};

const DG = { drag: null, scale: "fit" };
try { DG.scale = localStorage.getItem("vcsel-dg-scale2") || "fit"; } catch (_) { /* */ }

function dgHeight(d) {
  if (!(d > 0)) return 18;
  if (DG.scale === "equal") return 26;
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
const DG_LABEL_W = 92;
function diagramHTML(design, info, opts = {}) {
  const nodes = info?.nodes || []; let k = 0;
  const ed = !!opts.editable; const selKey = opts.selKey || "";
  const bnd = (L, key, label, n) => `<div class="dg-bnd ${selKey === key ? "sel" : ""}" data-path="${key}" data-drop="${key === "top" ? "after" : "before"}">
      <span class="dg-sw" style="background:${layerColor(L)}"></span><b>${esc(L.name)}</b><span class="dg-meta">${label} · ${esc(matText(L))}${n ? ` · n ${fmt(n.n, 4)}` : ""}</span></div>`;
  // Layers are drawn flush (touching, like Vertical); each group's name and repeat box sit in a
  // bracketed label column to the left, one column per nesting level.
  const LW = DG_LABEL_W;
  const depthOf = (items, d = 0) => items.reduce((m, it) => Math.max(m, it.kind === "group" ? depthOf(it.children, d + 1) : d), d);
  const maxD = depthOf(design.stack);
  const walk = (items, path, depth = 0) => items.map((it, i) => {
    const p = [...path, i]; const key = p.join(",");
    if (it.kind === "group") {
      const roleTxt = it.role !== "none" ? (ROLES.find((r) => r[0] === it.role)?.[1] || it.role) : "";
      const body = it.children.length ? walk(it.children, p, depth + 1) : `<div class="dg-empty" data-path="${key}" data-drop="into">${ed ? "drop layers here" : "empty"}</div>`;
      const rep = ed ? `<span class="rep">×<input type="number" min="0" step="1" value="${it.repeats}" data-rep="${key}" title="Repetitions"></span>` : `<span class="rep">×${it.repeats}</span>`;
      return `<div class="dg-group ${selKey === key ? "sel" : ""}" data-path="${key}" ${ed ? 'draggable="true"' : ""}>
        <div class="dg-glab" data-path="${key}" data-drop="head" style="left:${-(maxD - depth) * LW}px;width:${LW}px" title="${esc(it.name)}: repeated ${it.repeats}×${roleTxt ? ` (${esc(roleTxt)})` : ""}${ed ? ". Drag to move; drop layers here to add them to this group" : ""}">
          <div class="dg-gtxt"><span class="dg-name">${esc(it.name)}</span>${rep}${roleTxt ? `<span class="dg-role">${esc(roleTxt)}</span>` : ""}</div></div>
        ${body}</div>`;
    }
    const ni = nodes[k++] || {};
    const bg = layerColor(it); const fg = textOn(bg);
    const h = dgHeight(ni.d);
    const tags = `${it.layer_type === "active" ? '<span class="badge active">active</span>' : ""}${it.marked ? '<span class="badge mark" title="marked for cavity tuning">λ</span>' : ""}`;
    return `<div class="dg-layer ${selKey === key ? "sel" : ""}" data-path="${key}" data-drop="layer" ${ed ? 'draggable="true"' : ""}
        style="height:${h.toFixed(1)}px;background:${bg};color:${fg}" title="${esc(it.name)} — ${esc(matText(it))}, ${fmt(ni.d, 5)} nm, n = ${fmt(ni.n, 5)}">
      <span class="dg-name">${esc(it.name)}</span>${tags}<span class="dg-meta">${esc(matText(it))} · ${fmt(ni.d, 4)} nm · n ${fmt(ni.n, 4)}</span></div>`;
  }).join("");
  return `<div class="dg-wrap" style="padding-left:${maxD * LW}px">${bnd(design.top, "top", "exit medium", info?.top)}<div class="dg-stack" data-path="stack">${walk(design.stack, ["stack"])}</div>${bnd(design.substrate, "sub", "substrate", info?.substrate)}</div>`;
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
  if (kind === "head") return f < 0.12 ? "before" : f > 0.88 ? "after" : "into";
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
const VIEW = { mode: "diagram", wide: false };
try { VIEW.mode = localStorage.getItem("vcsel-stack-view2") || "diagram"; VIEW.wide = localStorage.getItem("vcsel-stack-wide") === "1"; } catch (_) { /* */ }

function renderDiagramView() {
  const host = $("#stack-diagram"); if (!host || !S.design || VIEW.mode !== "diagram") return;
  const keep = $(".dg-blocks", host)?.scrollTop || 0;
  const pal = Object.entries(PALETTE).map(([k, p]) => `<span class="chip" draggable="true" data-tpl="${k}" title="Drag into the stack: ${esc(p.hint)}">${esc(p.label)}</span>`).join("");
  host.innerHTML = `<div class="dg-palette"><span class="dg-hint">Drag in:</span>${pal}
</div>
    <div class="dg-body"><div class="dg-blocks">${diagramHTML(S.design, S.nodeInfo, { selKey: S.sel.join(","), editable: true })}</div>
      <div class="dg-strip" title="Whole stack to scale; click a layer to select it"></div></div>`;
  $("#dg-scale").value = DG.scale;
  const blocks = $(".dg-blocks", host);
  if (DG.scale === "fit") fitBlocks(blocks);
  blocks.scrollTop = keep;
  const strip = $(".dg-strip", host);
  strip.innerHTML = stripSVG(S.design, S.nodeInfo, S.sel.join(","), Math.max(blocks.clientHeight - 4, 120));
  VIEW.lastSize = `${host.clientWidth}x${host.clientHeight}`;
  const sel = $(".dg-blocks .sel", host); if (sel && VIEW.scrollToSel) { sel.scrollIntoView({ block: "nearest" }); VIEW.scrollToSel = false; }
}
/* Shrink layer blocks so the whole stack fits the visible panel (thickest layers stay tallest). */
function fitBlocks(blocks) {
  blocks.classList.remove("fitted");
  const avail = blocks.clientHeight;
  if (blocks.scrollHeight <= avail + 1) {               // spare room: stretch the blocks to fill the panel
    const layers = $$(".dg-layer", blocks); const extra = avail - (blocks.firstElementChild?.getBoundingClientRect().height || avail) - 4;
    if (!layers.length || extra < 8) return;
    const h0 = layers.map((l) => l.getBoundingClientRect().height); const sum0 = h0.reduce((a, b) => a + b, 0);
    const k = Math.min(1 + extra / sum0, 2.5);           // at most 2.5x taller than normal
    layers.forEach((l, i) => { l.style.height = (h0[i] * k).toFixed(2) + "px"; });
    return;
  }
  blocks.classList.add("fitted");                       // compact headers / margins first
  const layers = $$(".dg-layer", blocks);
  const h0 = layers.map((l) => l.getBoundingClientRect().height);
  const sum0 = h0.reduce((a, b) => a + b, 0); if (!sum0) return;
  const target = avail - (blocks.scrollHeight - sum0) - 2;   // room left for the layer blocks
  const N = layers.length;
  // water-filling: heights = max(m, f*h0) with the largest readable minimum m that still fits
  let tgt = target;
  for (let pass = 0; pass < 8; pass++) {
    const m = Math.min(13, Math.max(2, tgt / N));
    const total = (f) => h0.reduce((a, h) => a + Math.max(m, f * h), 0);
    let lo = 0, hi = 1;
    for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; if (total(mid) > tgt) hi = mid; else lo = mid; }
    layers.forEach((l, i) => {
      const h = Math.max(m, lo * h0[i]); l.style.height = h.toFixed(2) + "px";
      l.classList.toggle("tiny", h < 16); l.classList.toggle("micro", h < 10);
    });
    const over = blocks.scrollHeight - blocks.clientHeight;   // headers can change size once text is hidden
    if (over <= 0) break;
    tgt -= over + 2;
  }
}
function initStackViews() {
  const host = $("#stack-diagram");
  $("#dg-ctrls").innerHTML = `<select id="dg-scale" title="Block heights in the diagram"><option value="fit">Fit panel</option><option value="log">By thickness</option><option value="equal">Equal heights</option></select>
    <button class="pb" data-fig="png" title="Download a labelled drawing of the stack as PNG">PNG</button><button class="pb" data-fig="svg" title="Download a labelled drawing of the stack as SVG">SVG</button>`;
  $("#dg-scale").value = DG.scale;
  $("#dg-ctrls").addEventListener("click", (e) => { const b = e.target.closest("[data-fig]"); if (b) exportStackFigure(S.design, S.nodeInfo, b.dataset.fig, slug()); });
  $("#dg-scale").addEventListener("change", (e) => { DG.scale = e.target.value; try { localStorage.setItem("vcsel-dg-scale2", DG.scale); } catch (_) { /* */ } renderDiagramView(); });
  if (window.ResizeObserver) new ResizeObserver(() => {
    if (VIEW.mode !== "diagram" || !S.design) return;
    const sz = `${host.clientWidth}x${host.clientHeight}`; if (sz === VIEW.lastSize) return;
    clearTimeout(VIEW.rt); VIEW.rt = setTimeout(renderDiagramView, 120);
  }).observe(host);
  bindDiagram(host, { editable: true, onSelect: (p) => { S.sel = p; renderStack(); renderProps(); } });
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
  const setProps = (hide) => {
    document.body.classList.toggle("props-collapsed", hide); $("#btn-props").textContent = hide ? "▸ Show" : "▾ Hide";
    try { localStorage.setItem("vcsel-props-hidden", hide ? "1" : "0"); } catch (_) { /* */ }
  };
  $("#btn-props").addEventListener("click", () => setProps(!document.body.classList.contains("props-collapsed")));
  let hid = false; try { hid = localStorage.getItem("vcsel-props-hidden") === "1"; } catch (_) { /* */ }
  setProps(hid);
  setStackView(VIEW.mode, false); setWide(VIEW.wide, false);
}
function setStackView(mode, render = true) {
  VIEW.mode = mode === "diagram" ? "diagram" : "list";
  try { localStorage.setItem("vcsel-stack-view2", VIEW.mode); } catch (_) { /* */ }
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

/* ------------------------------------------------------------------ stack drawing for export (SVG / PNG) */
function stackFigureSVG(design, info, title) {
  const nodes = info?.nodes || []; let k = 0;
  const depthOf = (items, d = 0) => items.reduce((m, it) => Math.max(m, it.kind === "group" ? depthOf(it.children, d + 1) : d), d);
  const maxD = depthOf(design.stack);
  const LW = 150, BX = 24 + maxD * LW, BW = 250, TX = BX + BW + 16, W = TX + 430;
  const F = 'font-family="Arial, Helvetica, sans-serif"';
  const out = []; const brackets = []; let y = title ? 46 : 16;
  const hgt = (d) => (d > 0 ? Math.max(22, Math.min(72, 14 + 26 * Math.log10(1 + d / 8))) : 22);
  const label = (L, ni) => `${esc(L.name)} — ${esc(matText(L))}, ${fmt(ni.d, 5)} nm, n = ${fmt(ni.n, 5)}${L.layer_type === "active" ? " (active)" : ""}`;
  const bnd = (L, txt, n) => {
    out.push(`<rect x="${BX}" y="${y}" width="${BW}" height="30" fill="url(#hatch)" stroke="#555" stroke-width="1"/>
      <rect x="${BX}" y="${y}" width="${BW}" height="30" fill="${layerColor(L)}" fill-opacity="0.35"/>
      <text x="${TX}" y="${y + 19}" font-size="13" ${F} fill="#333"><tspan font-style="italic">${esc(L.name)}</tspan> — ${txt}, ${esc(matText(L))}${n ? `, n = ${fmt(n.n, 5)}` : ""}</text>`);
    y += 30;
  };
  bnd(design.top, "exit medium", info?.top);
  const walk = (items, depth) => items.forEach((it) => {
    if (it.kind === "group") {
      const y0 = y;
      if (!it.children.length) { out.push(`<rect x="${BX}" y="${y}" width="${BW}" height="16" fill="none" stroke="#999" stroke-dasharray="4 3"/>`); y += 16; }
      walk(it.children, depth + 1);
      brackets.push({ y0, y1: y, depth, name: it.name, rep: it.repeats, role: it.role });
    } else {
      const ni = nodes[k++] || {}; const h = hgt(ni.d);
      out.push(`<rect x="${BX}" y="${y.toFixed(1)}" width="${BW}" height="${h.toFixed(1)}" fill="${layerColor(it)}" stroke="#333" stroke-width="0.8"/>
        <text x="${TX}" y="${(y + h / 2 + 4.5).toFixed(1)}" font-size="13" ${F} fill="#111">${label(it, ni)}</text>`);
      y += h;
    }
  });
  walk(design.stack, 0);
  bnd(design.substrate, "substrate", info?.substrate);
  for (const b of brackets) {
    const x = BX - 10 - (maxD - 1 - b.depth) * LW; const xm = x - 8;
    out.push(`<path d="M${x} ${b.y0 + 1} H${xm} V${b.y1 - 1} H${x}" fill="none" stroke="#1f5fae" stroke-width="1.6"/>`);
    const cy = (b.y0 + b.y1) / 2; const role = b.role && b.role !== "none" ? (ROLES.find((r) => r[0] === b.role)?.[1] || b.role) : "";
    out.push(`<text x="${xm - 6}" y="${(role ? cy - 2 : cy + 4.5).toFixed(1)}" text-anchor="end" font-size="13" ${F} fill="#1f5fae" font-weight="bold">${esc(b.name)} ×${b.rep}</text>`);
    if (role) out.push(`<text x="${xm - 6}" y="${(cy + 13).toFixed(1)}" text-anchor="end" font-size="11.5" ${F} fill="#1f5fae">${esc(role)}</text>`);
  }
  const H = y + 16;
  const head = title ? `<text x="16" y="26" font-size="16" font-weight="bold" ${F} fill="#111">${esc(title)}</text>` : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<defs><pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="8" height="8" fill="#fff"/><line x1="0" y1="0" x2="0" y2="8" stroke="#bbb" stroke-width="2"/></pattern></defs>
<rect width="100%" height="100%" fill="#fff"/>${head}${out.join("\n")}</svg>`;
}
function exportStackFigure(design, info, fmtx, name) {
  const title = `${design.name || "Layer stack"} (λ design = ${design.design_wavelength} nm; groups drawn once, ×N = repeats)`;
  const svg = stackFigureSVG(design, info, title);
  if (fmtx === "svg") return download(`${name}_stack.svg`, svg, "image/svg+xml");
  const img = new Image(); const scale = 3;
  img.onload = () => {
    const c = document.createElement("canvas"); c.width = img.width * scale; c.height = img.height * scale;
    const g = c.getContext("2d"); g.scale(scale, scale); g.drawImage(img, 0, 0);
    c.toBlob((b) => download(`${name}_stack.png`, b, "image/png"), "image/png");
  };
  img.onerror = () => toast("Could not render the PNG; try SVG", true);
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

/* ------------------------------------------------------------------ labelled plot toolbar */
const PLOT_TOOLS = [["zoom", "⬚ Zoom", "Drag a box to zoom (double-click the plot to reset)"], ["pan", "✥ Pan", "Drag to pan"],
  ["in", "＋", "Zoom in"], ["out", "－", "Zoom out"], ["reset", "⟲ Reset", "Reset axes"], ["png", "PNG", "Download as high-resolution PNG"], ["svg", "SVG", "Download as SVG (vector)"]];
function addPlotBar(el) {
  if (!el || el.previousElementSibling?.classList.contains("plot-bar")) return;
  const bar = document.createElement("div"); bar.className = "plot-bar";
  // double-click resets through the same path as the Reset button (Plotly's own autorange reset is off)
  el.addEventListener("dblclick", () => bar.querySelector('[data-pb="reset"]')?.click());
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
      // back to the ranges of the last full redraw (explicit ranges: no autorange pass, which could
      // fail when it ran at the same time as another relayout)
      const home = el._home; const upd = {};
      if (home) for (const [ax, r] of Object.entries(home)) { upd[`${ax}.range`] = r.slice(); upd[`${ax}.autorange`] = false; }
      else for (const ax of Object.keys(el.layout || {}).filter((a) => /^[xy]axis\d*$/.test(a))) upd[`${ax}.autorange`] = true;
      plotQueue(el, () => Plotly.relayout(el, upd)).then(() => {
        // if the relayout did not land (Plotly error), redraw from the last full plot instead
        const L = el._fullLayout || {};
        const off = home && Object.entries(home).some(([ax, r]) => !L[ax] || Math.abs(L[ax].range[0] - r[0]) + Math.abs(L[ax].range[1] - r[1]) > 1e-9 * (1 + Math.abs(r[1] - r[0])));
        if (off && el._last) plotQueue(el, () => Plotly.react(el, el._last.data, JSON.parse(el._last.layout), el._last.config));
      });
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
  host.innerHTML = `<div class="dg-title">Layer structure <span class="dg-hint">(incident medium on top)</span>
      <button class="pb" data-dfig="png" title="Download a drawing of this mirror as PNG">PNG</button><button class="pb" data-dfig="svg" title="Download a drawing of this mirror as SVG">SVG</button></div>
    <div class="dg-body small"><div class="dg-blocks">${diagramHTML(d, info, { editable: false })}</div><div class="dg-strip"></div></div>`;
  const strip = $(".dg-strip", host); strip.innerHTML = stripSVG(d, info, "", Math.max($(".dg-blocks", host).scrollHeight - 4, 120));
}
function initDbrExtras() {
  $("#dbr-structure").addEventListener("click", (e) => {
    const b = e.target.closest("[data-dfig]"); if (!b) return;
    const d = dbrDesign(); if (!d) return;
    let info = null; try { info = call("node_info", JSON.stringify(d)); } catch (_) { /* */ }
    exportStackFigure(d, info, b.dataset.dfig, `dbr_${$("#dbr-pairs").value}pairs`);
  });
  $("#btn-dbr-layers").addEventListener("click", () => {
    const d = dbrDesign(); if (!d) return;
    try { const r = call("csv_export", JSON.stringify(d), "structure", "{}"); download(`dbr_${$("#dbr-pairs").value}pairs_layers.csv`, r.csv); } catch (e) { toast(e.message, true); }
  });
  $("#btn-dbr-save").addEventListener("click", () => {
    const d = dbrDesign(); if (!d) return;
    download(`dbr_${$("#dbr-pairs").value}pairs.vcsel.json`, JSON.stringify(d, null, 1), "application/json");
  });
}
