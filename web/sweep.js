/* Parameter sweep tab: vary one design input (optionally a second one as a family of curves),
 * run the threshold analysis at each point and plot / tabulate the results.
 * Loaded after app.js; uses its globals (S, $, $$, esc, fmt, call, designJSON, matFormula, subHTML, ...). */

/* ---- what can be varied ------------------------------------------------- */
// target: "group" | "layer" | "gradable" | "xlayer" | "ylayer" | null
const SW_PARAMS = [
  { k: "repeats", label: "Repeats of a group (DBR pairs, QWs)", target: "group", unit: "", int: true },
  { k: "thickness", label: "Thickness of a layer", target: "layer", unit: "(layer's unit)" },
  { k: "x", label: "Composition x of a layer", target: "xlayer", unit: "" },
  { k: "y", label: "Composition y of a layer", target: "ylayer", unit: "" },
  { k: "group_scale", label: "Thickness scale of a group", target: "group", unit: "%" },
  { k: "all_scale", label: "Thickness scale of the whole stack (growth-rate error)", target: null, unit: "%" },
  { k: "grade_t", label: "Grading thickness of a group", target: "gradable", unit: "nm" },
  { k: "temperature", label: "Temperature", target: null, unit: "°C" },
  { k: "lambda", label: "Design wavelength (rescales layers given in waves)", target: null, unit: "nm" },
  { k: "alpha", label: "Absorption α of a layer (manual)", target: "layer", unit: "cm⁻¹" },
  { k: "doping", label: "Doping of a layer", target: "layer", unit: "cm⁻³", log: true },
];
/* ---- what can be plotted ------------------------------------------------ */
const SW_OUT = [
  ["threshold_gain", "Threshold material gain g<sub>th</sub>", "cm⁻¹"],
  ["modal_gain", "Threshold modal gain Γg<sub>th</sub>", "cm⁻¹"],
  ["wavelength", "Lasing wavelength λ<sub>las</sub>", "nm"],
  ["slope_top", "Slope efficiency, top", "W/A"],
  ["slope_bottom", "Slope efficiency, bottom", "W/A"],
  ["ext_eff", "External efficiency η<sub>d</sub> (total)", ""],
  ["ext_eff_top", "External efficiency, top", ""],
  ["ext_eff_bottom", "External efficiency, bottom", ""],
  ["alpha_i", "Internal loss ⟨α<sub>i</sub>⟩", "cm⁻¹"],
  ["alpha_m", "Mirror loss α<sub>m</sub>", "cm⁻¹"],
  ["alpha_m_top", "Mirror loss, top", "cm⁻¹"],
  ["alpha_m_bottom", "Mirror loss, bottom", "cm⁻¹"],
  ["R_top_passive", "Top DBR R (passive, from cavity)", ""],
  ["R_bottom_passive", "Bottom DBR R (passive, from cavity)", ""],
  ["T_top_passive", "Top DBR 1 − R (passive)", ""],
  ["T_bottom_passive", "Bottom DBR 1 − R (passive)", ""],
  ["confinement", "Confinement Γ", ""],
  ["enhancement", "Gain enhancement Γ<sub>enh</sub>", ""],
  ["lifetime_ps", "Photon lifetime", "ps"],
  ["effective_length", "Effective cavity length L", "nm"],
  ["cavity_optical_waves", "Cavity optical thickness", "λ"],
  ["L_pen_top", "Top DBR penetration depth", "nm"],
  ["L_pen_bottom", "Bottom DBR penetration depth", "nm"],
  ["total_thickness_um", "Total thickness", "µm"],
  ["retune_scale", "Re-tune factor on the chosen layers", ""],
];
const SW_LOGGY = new Set(["T_top_passive", "T_bottom_passive"]);
const SW_COLORS = ["#1f5fae", "#d9480f", "#2b8a3e", "#862e9c", "#e67700", "#0b7285", "#c2255c", "#5c940d"];
const SW = { running: false, stop: false, data: null, tune: null };   // tune: Set of JSON layer paths used for re-tuning

/* ---- the design tree --------------------------------------------------- */
function swAt(d, path) { let it = { children: d.stack }; for (const i of path) it = it.children[i]; return it; }
function swTargets(type) {
  const out = [];
  const walk = (items, path, prefix) => items.forEach((it, i) => {
    const p = [...path, i];
    if (it.kind === "group") {
      if (type === "group" || (type === "gradable" && gradable(it))) out.push([p, `${prefix}${it.name} ×${it.repeats}`]);
      walk(it.children, p, `${prefix}${it.name} / `);
    } else {
      const m = S.matByKey[it.material] || {};
      const ok = type === "layer" || (type === "xlayer" && m.x_label && it.index_mode === "model") || (type === "ylayer" && m.y_label && it.index_mode === "model");
      if (ok) out.push([p, `${prefix}${it.name}${it.layer_type === "active" ? " (active)" : ""}`]);
    }
  });
  walk(S.design.stack, [], "");
  return out;
}
function swLayers(it, f) { if (it.kind === "group") it.children.forEach((c) => swLayers(c, f)); else f(it); }
// current value of a parameter in design d
function swGet(d, P, path) {
  const it = path ? swAt(d, path) : null;
  switch (P.k) {
    case "repeats": return it.repeats;
    case "thickness": return it.thickness;
    case "x": return it.x || 0;
    case "y": return it.y || 0;
    case "group_scale": case "all_scale": return 100;
    case "grade_t": return +(it.grading?.profile && it.grading.profile !== "none" ? it.grading.thickness_nm : 0) || 0;
    case "temperature": return d.temperature ?? 23;
    case "lambda": return d.design_wavelength;
    case "alpha": return it.absorption_mode === "doping" ? 0 : (it.absorption || 0);
    case "doping": return it.doping || 0;
  }
  return 0;
}
// set a parameter in design d (a plain copy, or S.design for "apply")
function swSet(d, P, path, v) {
  const it = path ? swAt(d, path) : null;
  switch (P.k) {
    case "repeats": it.repeats = Math.max(0, Math.round(v)); break;
    case "thickness": it.thickness = Math.max(0, v); break;
    case "x": it.x = v; break;
    case "y": it.y = v; break;
    case "group_scale": swLayers(it, (L) => { L.thickness *= v / 100; }); break;
    case "all_scale": d.stack.forEach((c) => swLayers(c, (L) => { L.thickness *= v / 100; })); break;
    case "grade_t": {
      const g = Object.assign({}, GRADE_DEF, it.grading || {});
      if (g.profile === "none") g.profile = "linear";
      g.thickness_nm = Math.max(0, v); it.grading = g; break;
    }
    case "temperature": d.temperature = v; break;
    case "lambda": d.design_wavelength = v; break;
    case "alpha": it.absorption_mode = "manual"; it.absorption = v; break;
    case "doping": it.doping = Math.max(0, v); break;
  }
}
function swUnit(P, path) {
  if (P.k === "thickness" && path) return swAt(S.design, path).thickness_unit === "waves" ? "waves" : "nm";
  return P.unit;
}

/* ---- re-tune layers ------------------------------------------------------ */
// every layer of the design with its path (layers inside groups once, they change in every repeat)
function swAllLayers() { return swTargets("layer").filter(([p]) => swAt(S.design, p).layer_type !== "metal"); }
function swTuneList() {
  const box = $("#sw-tune-list"); if (!box) return;
  const all = swAllLayers(); const valid = new Set(all.map(([p]) => JSON.stringify(p)));
  if (SW.tune) SW.tune = new Set([...SW.tune].filter((k) => valid.has(k)));
  if (!SW.tune || !SW.tune.size) SW.tune = new Set(all.filter(([p]) => swAt(S.design, p).marked).map(([p]) => JSON.stringify(p)));
  box.innerHTML = all.map(([p, l]) => { const k = JSON.stringify(p); const on = SW.tune.has(k);
    return `<label class="${on ? "on" : ""}"><input type="checkbox" data-k="${esc(k)}" ${on ? "checked" : ""}>${esc(uniLabel(l))}</label>`; }).join("");
  box.classList.toggle("off", !$("#sw-retune").checked);
  $("#sw-lam").textContent = fmt(S.design.design_wavelength, 6);
}
/* ---- controls ---------------------------------------------------------- */
function swParam(which) { return SW_PARAMS.find((p) => p.k === $(`#sw-param${which}`).value); }
function swPath(which) { const v = $(`#sw-target${which}`).value; return v ? JSON.parse(v) : null; }
function swFillTargets(which) {
  const P = swParam(which); const sel = $(`#sw-target${which}`); const lab = $(`#sw-target${which}-l`);
  if (!P || !P.target) { lab.style.display = "none"; sel.innerHTML = ""; return; }
  const prev = sel.value; const T = swTargets(P.target);
  lab.style.display = "";
  sel.innerHTML = T.length ? T.map(([p, l]) => `<option value="${esc(JSON.stringify(p))}">${esc(uniLabel(l))}</option>`).join("") : `<option value="">(none in this design)</option>`;
  if (T.some(([p]) => JSON.stringify(p) === prev)) sel.value = prev;
  else if (P.target === "group" || P.target === "gradable") {           // default to a mirror
    const dbr = T.find(([p]) => /DBR/i.test(swAt(S.design, p).role || "") || /dbr/i.test(swAt(S.design, p).role)); if (dbr) sel.value = JSON.stringify(dbr[0]);
  }
  if (which === "2" && swSame()) {                                       // never default the curves to the swept input itself
    const p1 = $("#sw-target").value; const alt = T.find(([p]) => JSON.stringify(p) !== p1 && (P.target !== "group" && P.target !== "gradable" || /DBR/i.test(swAt(S.design, p).role || "")))
      || T.find(([p]) => JSON.stringify(p) !== p1);
    if (alt) sel.value = JSON.stringify(alt[0]);
  }
}
// true when the second parameter is the same input as the first (it would be overwritten at every point)
function swSame() {
  const a = $("#sw-param").value, b = $("#sw-param2").value;
  return !!b && a === b && ($("#sw-target").value || "") === ($("#sw-target2").value || "");
}
function swDefaults(which) {
  const P = swParam(which); if (!P) return;
  const path = swPath(which); if (P.target && !path) return;
  const c = swGet(S.design, P, path); const r = (v, n = 4) => +(+v).toPrecision(n);
  let lo, hi, n = 21;
  switch (P.k) {
    case "repeats": lo = Math.max(1, c - 8); hi = c + 8; n = hi - lo + 1; break;
    case "thickness": lo = r(c * 0.9); hi = r(c * 1.1); break;
    case "x": case "y": lo = r(Math.max(0, c - 0.1), 3); hi = r(Math.min(1, c + 0.1), 3); break;
    case "group_scale": case "all_scale": lo = 97; hi = 103; n = 25; break;
    case "grade_t": lo = 0; hi = 40; n = 21; break;
    case "temperature": lo = 0; hi = 100; break;
    case "lambda": lo = r(c - 10, 5); hi = r(c + 10, 5); break;
    case "alpha": lo = 0; hi = r(Math.max(2 * c, 50)); break;
    case "doping": lo = c > 0 ? r(c / 10, 2) : 1e17; hi = c > 0 ? r(c * 10, 2) : 1e19; n = 13; break;
  }
  const show = (v) => (P.log ? (+v).toExponential(1).replace("e+", "e") : v);
  if (which === "") { $("#sw-from").value = show(lo); $("#sw-to").value = show(hi); $("#sw-n").value = n; }
  else {
    // a few values for the family of curves
    const vals = P.int ? [c - 2, c, c + 2].filter((v) => v >= 0) : P.log ? [lo, c || Math.sqrt(lo * hi), hi] : [lo, (lo + hi) / 2, hi];
    $("#sw-vals2").value = vals.map((v) => (P.log ? (+v).toExponential(1).replace("e+", "e") : r(v))).join(", ");
  }
  $(`#sw-unit${which}`).textContent = swUnit(P, path);
  swCurrentLine();
}
function swCurrentLine() {
  const P = swParam(""); const path = swPath("");
  $("#sw-now").innerHTML = P && (!P.target || path) ? `now ${fmt(swGet(S.design, P, path), 6)} ${swUnit(P, path)}` : "";
}
function swXs() {
  const P = swParam(""); const a = parseFloat($("#sw-from").value), b = parseFloat($("#sw-to").value);
  let n = Math.max(2, Math.min(401, parseInt($("#sw-n").value) || 21));
  if (!Number.isFinite(a) || !Number.isFinite(b)) throw new Error("Enter the sweep range");
  if (P.int) { const lo = Math.round(Math.min(a, b)), hi = Math.round(Math.max(a, b)); const step = Math.max(1, Math.round((hi - lo) / (n - 1)));
    const xs = []; for (let v = lo; v <= hi; v += step) xs.push(v); return xs; }
  if (P.log && a > 0 && b > 0) return Array.from({ length: n }, (_, i) => a * Math.pow(b / a, i / (n - 1)));
  return Array.from({ length: n }, (_, i) => a + (b - a) * i / (n - 1));
}
function swVals2() {
  const P = swParam("2"); if (!P) return [null];
  const v = $("#sw-vals2").value.split(/[,;\s]+/).map(parseFloat).filter(Number.isFinite);
  if (!v.length) throw new Error("Enter the values of the second parameter, separated by commas");
  return (P.int ? v.map(Math.round) : v).slice(0, 8);
}

/* ---- run --------------------------------------------------------------- */
async function swRun() {
  if (SW.running) return;
  if (!hasActive()) { toast("The sweep needs an active layer (threshold analysis).", true); return; }
  let xs, v2s;
  try { xs = swXs(); v2s = swVals2(); } catch (e) { toast(e.message, true); return; }
  const P1 = swParam(""), P2 = swParam("2"), p1 = swPath(""), p2 = swPath("2");
  if (P1.target && !p1) { toast("Choose what to vary", true); return; }
  if (P2 && P2.target && !p2) { toast("Choose the target of the second parameter", true); return; }
  if (swSame()) { toast("\u201cCurves for\u201d is the same input as \u201cVary\u201d, so the x value would overwrite it at every point. Pick a different input or layer group for the curves.", true); return; }
  const base = JSON.parse(designJSON());
  const opts = { internal_efficiency: parseFloat($("#eta-i").value) || 1, rt_model: $("#rt-model").value };
  const retune = $("#sw-retune").checked;
  if (retune) {
    const paths = [...(SW.tune || [])].map((k) => JSON.parse(k));
    if (!paths.length) { toast("Pick the layer(s) to re-tune with (for example the cavity spacers).", true); return; }
    const varied = [P1.target ? p1 : null, P2 && P2.target ? p2 : null].filter(Boolean);
    const inside = (p, e) => e.every((v, i) => p[i] === v);
    const clash = paths.find((p) => varied.some((e) => inside(p, e)));
    if (clash) { toast(`“${swAt(base, clash).name}” is being varied by the sweep, so it cannot also be used to re-tune. Untick it or pick another layer.`, true, 6000); return; }
    if (P1.k === "all_scale" || P2?.k === "all_scale") toast("Note: re-tuning after a whole-stack scale undoes part of the scale in the chosen layers.", false, 5000);
    Object.assign(opts, { retune: true, tune_paths: paths, exclude: varied });
  }
  const lam0 = S.analysis?.results?.wavelength || base.design_wavelength;
  $("#sw-pick").textContent = "Click a point on the plot to see its values and apply it to the design.";
  SW.running = true; SW.stop = false; $("#sw-run").disabled = true; $("#sw-stop").disabled = false;
  SW.data = { P1, P2, p1, p2, u1: swUnit(P1, p1), u2: P2 ? swUnit(P2, p2) : "", t1: $("#sw-target").selectedOptions[0]?.textContent || "",
    t2: P2 ? ($("#sw-target2").selectedOptions[0]?.textContent || "") : "", retune: retune ? opts.tune_paths.map((p) => swAt(base, p).name) : null, curves: v2s.map((v2) => ({ v2, pts: [] })), base: JSON.parse(JSON.stringify(base)) };
  const total = xs.length * v2s.length; let done = 0, fails = 0; const t0 = performance.now(); let lastErr = "";
  // follow the lasing mode continuously: start at the point nearest the current design value and walk
  // outwards in both directions, each step starting the solver from the previous point's wavelength
  const cur = swGet(base, P1, p1);
  let i0 = 0; xs.forEach((x, i) => { if (Math.abs(x - cur) < Math.abs(xs[i0] - cur)) i0 = i; });
  const order = [...xs.keys()].slice(i0).concat([...xs.keys()].slice(0, i0).reverse());
  for (const cv of SW.data.curves) {
    let guess = lam0; const res = new Array(xs.length);
    for (const i of order) {
      if (SW.stop) break;
      if (i === i0 - 1) guess = res[i0]?.r?.wavelength || lam0;      // second branch starts again from the design point
      const x = xs[i];
      const d = JSON.parse(JSON.stringify(base));
      if (P2) swSet(d, P2, p2, cv.v2);
      swSet(d, P1, p1, x);
      let r = null;
      try { r = call("sweep_point", JSON.stringify(d), JSON.stringify({ ...opts, lambda_guess: retune ? d.design_wavelength : guess })).point; }
      catch (e) { fails++; lastErr = e.message; }
      if (r) {
        r.T_top_passive = r.R_top_passive != null ? 1 - r.R_top_passive : null;
        r.T_bottom_passive = r.R_bottom_passive != null ? 1 - r.R_bottom_passive : null;
        if (r.converged && Number.isFinite(r.wavelength)) guess = r.wavelength; else fails++;
      }
      res[i] = { x, r }; cv.pts = res.filter(Boolean).sort((a, b) => a.x - b.x);
      done++;
      if (done % 3 === 0 || done === total) {
        $("#sw-prog").textContent = `${done} / ${total} points · ${((performance.now() - t0) / 1000).toFixed(1)} s`;
        swPlot(); await new Promise((res) => setTimeout(res, 0));
      }
    }
    if (SW.stop) break;
  }
  SW.running = false; $("#sw-run").disabled = false; $("#sw-stop").disabled = true;
  $("#sw-prog").textContent = `${done} / ${total} points · ${((performance.now() - t0) / 1000).toFixed(1)} s${SW.stop ? " (stopped)" : ""}${fails ? ` · ${fails} point${fails > 1 ? "s" : ""} did not converge${lastErr ? ": " + lastErr.slice(0, 120) : ""}` : ""}`;
  swPlot(); swTable();
}

/* ---- plot & table ------------------------------------------------------ */
function swShort(P) { return P.label.replace(/ \(.*\)$/, "").replace(/ of (a|the) (layer|group|whole stack)$/, ""); }
function swOutLabel(k) { const o = SW_OUT.find((x) => x[0] === k); return o ? `${o[1]}${o[2] ? ` (${o[2]})` : ""}` : k; }
function swXLabel(D) {
  const tgt = D.P1.target ? `: ${D.t1}` : "";
  return `${swShort(D.P1)}${tgt.replace(/ ×\d+$/, "")}${D.u1 ? ` (${D.u1})` : ""}`;
}
function swCurveName(D, cv) {
  if (!D.P2) return "";
  const tg = D.t2 ? ` ${D.t2.replace(/ ×\d+$/, "")}` : "";
  const nm = D.P2.k === "repeats" ? `${tg.trim()} ×${cv.v2}` : `${swShort(D.P2)}${tg} = ${fmt(cv.v2, 4)}${D.u2 && D.u2 !== "%" ? " " + D.u2 : D.u2}`;
  return nm;
}
function swPlot() {
  const D = SW.data, el = $("#plot-sweep"); if (!D) return;
  const y1 = $("#sw-y1").value, y2 = $("#sw-y2").value;
  const traces = [];
  D.curves.forEach((cv, i) => {
    const col = SW_COLORS[i % SW_COLORS.length]; const nm = swCurveName(D, cv);
    const xs = cv.pts.map((p) => p.x);
    const val = (k) => cv.pts.map((p) => (p.r && p.r.converged !== false ? p.r[k] : null));
    traces.push({ x: xs, y: val(y1), type: "scatter", mode: "lines+markers", marker: { size: 5 }, line: { color: col, width: 2 },
      name: D.P2 ? nm : swOutLabel(y1).replace(/<[^>]+>/g, ""), legendgroup: "c" + i, customdata: cv.pts.map((_, j) => [i, j]),
      hovertemplate: `%{x:.6g}<br>%{y:.6g}<extra>${D.P2 ? esc(nm) : ""}</extra>` });
    if (y2) traces.push({ x: xs, y: val(y2), type: "scatter", mode: "lines+markers", yaxis: "y2", marker: { size: 4, symbol: "square-open" }, line: { color: col, width: 1.5, dash: "dot" },
      name: D.P2 ? nm + " (dotted: right axis)" : swOutLabel(y2).replace(/<[^>]+>/g, ""), legendgroup: "c" + i, showlegend: !D.P2, customdata: cv.pts.map((_, j) => [i, j]),
      hovertemplate: `%{x:.6g}<br>%{y:.6g}<extra>${D.P2 ? esc(nm) : ""}</extra>` });
  });
  const cur = swGet(D.base, D.P1, D.p1);
  const ax = { showline: true, mirror: true, linecolor: "#444", ticks: "outside", gridcolor: "#eef1f5", zeroline: false, exponentformat: "power" };
  const layout = {
    font: PLOT_FONT, margin: { l: 78, r: y2 ? 78 : 24, t: 14, b: 56 }, paper_bgcolor: "#fff", plot_bgcolor: "#fff",
    showlegend: legendOn("#tab-sweep") && (!!D.P2 || !!y2),
    legend: { x: 0.99, xanchor: "right", y: 0.98, yanchor: "top", bgcolor: "rgba(255,255,255,0.88)", bordercolor: "#ced4da", borderwidth: 1, font: { size: 11.5 },
      title: D.P2 && y2 ? { text: `solid: ${swOutLabel(y1)}<br>dotted: ${swOutLabel(y2)}`, font: { size: 11 } } : undefined },
    xaxis: { ...ax, title: { text: swXLabel(D) }, type: D.P1.log ? "log" : "linear" },
    yaxis: { ...ax, mirror: !y2, title: { text: swOutLabel(y1) }, type: SW_LOGGY.has(y1) ? "log" : "linear" },
    shapes: [{ type: "line", x0: cur, x1: cur, yref: "paper", y0: 0, y1: 1, line: { color: "#868e96", width: 1, dash: "dash" } }],
    annotations: [{ x: cur, yref: "paper", y: 1, yanchor: "bottom", text: "design", showarrow: false, font: { size: 10.5, color: "#868e96" } }],
  };
  if (y2) layout.yaxis2 = { ...ax, mirror: false, overlaying: "y", side: "right", title: { text: swOutLabel(y2) }, type: SW_LOGGY.has(y2) ? "log" : "linear" };
  el._autoLegend = true;
  Plotly.react(el, traces, layout, PLOT_CONFIG).then(() => {
    if (!el._swClick) { el._swClick = true; el.on("plotly_click", (ev) => { const cd = ev.points?.[0]?.customdata; if (cd) swPick(cd[0], cd[1]); }); }
  });
}
function swPick(i, j) {
  const D = SW.data; const cv = D.curves[i]; const p = cv.pts[j]; if (!p) return;
  const r = p.r || {};
  const keys = ["threshold_gain", "wavelength", "slope_top", "slope_bottom", "alpha_m", "R_top_passive", "R_bottom_passive", ...(D.retune ? ["retune_scale"] : [])];
  $("#sw-pick").innerHTML = `<b>${esc(swXLabel(D).replace(/<[^>]+>/g, ""))} = ${fmt(p.x, 6)}</b>${D.P2 ? `, ${esc(swCurveName(D, cv))}` : ""}:
    ${keys.map((k) => `${swOutLabel(k)} ${r[k] == null ? "—" : fmt(r[k], 6)}`).join(" · ")}
    <button class="btn sm primary" id="sw-apply">Apply to design</button>`;
  $("#sw-apply").onclick = () => {
    if (D.P2) swSet(S.design, D.P2, D.p2, cv.v2);
    swSet(S.design, D.P1, D.p1, p.x);
    (r.tuned || []).forEach((t) => { const L = swAt(S.design, t.path); if (L && L.kind !== "group") L.thickness = +t.thickness.toPrecision(8); });
    changed(); toast("Applied to the design (Undo reverts it)");
  };
}
const SW_TABLE_KEYS = ["threshold_gain", "modal_gain", "wavelength", "slope_top", "slope_bottom", "ext_eff", "alpha_i", "alpha_m", "R_top_passive", "R_bottom_passive", "confinement", "enhancement", "lifetime_ps"];
function swTable() {
  const D = SW.data; if (!D) { $("#sw-table").innerHTML = ""; return; }
  const h2 = D.P2 ? `${swShort(D.P2)}${D.t2 ? ": " + D.t2.replace(/ ×\d+$/, "") : ""}${D.u2 ? ` (${D.u2})` : ""}` : null;
  const TK = D.retune ? [...SW_TABLE_KEYS, "retune_scale"] : SW_TABLE_KEYS;
  const head = [h2, swXLabel(D), ...TK.map(swOutLabel)].filter((h) => h !== null);
  const rows = [];
  D.curves.forEach((cv) => cv.pts.forEach((p) => {
    const r = p.r || {};
    rows.push(`<tr>${D.P2 ? `<td class="n">${fmt(cv.v2, 6)}</td>` : ""}<td class="n">${fmt(p.x, 6)}</td>${TK.map((k) => `<td class="n">${r[k] == null || r.converged === false ? "—" : fmt(r[k], 6)}</td>`).join("")}</tr>`);
  }));
  $("#sw-table").innerHTML = `<table class="t"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
}
function swCSV() {
  const D = SW.data; if (!D) { toast("Run a sweep first", true); return; }
  const keys = SW_OUT.map((o) => o[0]);
  const plain = (s) => s.replace(/<sub>(.*?)<\/sub>/g, "_$1").replace(/<[^>]+>/g, "");
  let t = `# ${S.design.name}: parameter sweep\n# x = ${plain(swXLabel(D))}${D.P2 ? `; curves: ${plain(D.P2.label)}${D.t2 ? " of " + D.t2 : ""}` : ""}\n${D.retune ? `# re-tuned to ${S.design.design_wavelength} nm after each step by scaling: ${D.retune.join("; ")} (factor in retune_scale)\n` : ""}`;
  t += `${D.P2 ? "param2," : ""}param1,${keys.map((k) => plain(swOutLabel(k)).replace(/,/g, ";")).join(",")}\n`;
  D.curves.forEach((cv) => cv.pts.forEach((p) => {
    const r = p.r || {};
    t += `${D.P2 ? cv.v2 + "," : ""}${p.x},${keys.map((k) => (r[k] == null || r.converged === false ? "" : r[k])).join(",")}\n`;
  }));
  download(`${slug()}_sweep.csv`, t);
}

/* ---- init -------------------------------------------------------------- */
function initSweepTab() {
  const opts = SW_PARAMS.map((p) => `<option value="${p.k}">${esc(p.label)}</option>`).join("");
  $("#sw-param").innerHTML = opts; $("#sw-param2").innerHTML = `<option value="">none</option>` + opts;
  const outs = SW_OUT.map(([k, l, u]) => `<option value="${k}">${l.replace(/<sub>(.*?)<\/sub>/g, "$1")}${u ? ` (${u})` : ""}</option>`).join("");
  $("#sw-y1").innerHTML = outs; $("#sw-y2").innerHTML = `<option value="">none</option>` + outs;
  $("#sw-y1").value = "threshold_gain"; $("#sw-y2").value = "slope_top";
  for (const w of ["", "2"]) {
    $(`#sw-param${w}`).addEventListener("change", () => { swFillTargets(w); swDefaults(w); });
    $(`#sw-target${w}`).addEventListener("change", () => swDefaults(w));
  }
  ["#sw-y1", "#sw-y2"].forEach((s) => $(s).addEventListener("change", () => { swPlot(); }));
  $("#tab-sweep .legend-tog").addEventListener("change", swPlot);
  $("#sw-run").addEventListener("click", swRun);
  $("#sw-retune").addEventListener("change", swTuneList);
  $("#sw-tune-list").addEventListener("change", (e) => {
    const k = e.target.dataset.k; if (!k) return;
    if (e.target.checked) SW.tune.add(k); else SW.tune.delete(k);
    e.target.parentElement.classList.toggle("on", e.target.checked);
    if (!$("#sw-retune").checked && e.target.checked) { $("#sw-retune").checked = true; swTuneList(); }
  });
  $("#sw-stop").addEventListener("click", () => { SW.stop = true; });
  $("#sw-csv").addEventListener("click", swCSV);
  $("#sw-stop").disabled = true;
  addPlotBar($("#plot-sweep"));
}
// called when the tab is opened or the design changes: keep the target lists current
function swRefresh() {
  for (const w of ["", "2"]) {
    const had = $(`#sw-target${w}`).value;
    swFillTargets(w);
    if (!had || $(`#sw-target${w}`).value !== had) swDefaults(w);
  }
  if (!$("#sw-from").value) swDefaults("");
  swTuneList();
  swCurrentLine();
}
