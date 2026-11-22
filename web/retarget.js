/* "Retarget λ…": scale the design to another wavelength, preview the threshold change and the
 * absorption checks, then apply (undoable). Uses app.js globals (S, $, esc, fmt, call, designJSON, ...). */
const RT = { result: null };

function rtOpen() {
  $("#rt-old").textContent = fmt(S.design.design_wavelength, 6);
  if (!$("#rt-new").value) $("#rt-new").value = S.design.design_wavelength;
  $("#rt-out").innerHTML = ""; $("#rt-apply").disabled = true; RT.result = null;
  $("#rt-dlg").showModal(); $("#rt-new").focus(); $("#rt-new").select();
}

function rtPreview() {
  const lam = parseFloat($("#rt-new").value);
  if (!(lam >= 100 && lam <= 20000)) { toast("Enter a wavelength between 100 nm and 20 µm", true); return; }
  const o = { wavelength: lam, keep_active: $("#rt-keep-active").checked, keep_metal: $("#rt-keep-metal").checked,
    tune: $("#rt-tune").checked, rt_model: $("#rt-model").value, confinement_model: $("#gamma-model").value, lambda_guess: S.analysis?.results?.wavelength };
  let r;
  try { r = call("retarget_design", designJSON(), JSON.stringify(o)); } catch (e) { $("#rt-out").innerHTML = `<ul class="rt-chk"><li class="error">${esc(e.message)}</li></ul>`; return; }
  RT.result = r;
  const b = r.before || {}, a = r.after || {}, rep = r.report;
  const row = (l, k, u, n = 6) => `<tr><td>${l}</td><td>${b[k] == null ? "—" : fmt(b[k], n)}</td><td>${a[k] == null || a.converged === false ? "—" : fmt(a[k], n)}</td><td>${u}</td></tr>`;
  let h = "";
  if (a.error || b.error) h += `<p class="hint">Threshold analysis: ${esc(a.error || b.error)}</p>`;
  else h += `<table class="rt-tbl"><tr><th></th><th>Now (${fmt(rep.old_lambda, 6)} nm)</th><th>Retargeted (${fmt(rep.new_lambda, 6)} nm)</th><th></th></tr>
    ${row("Lasing wavelength λ<sub>las</sub>", "wavelength", "nm", 7)}${row("Threshold gain g<sub>th</sub>", "threshold_gain", "cm⁻¹", 5)}
    ${row("Threshold modal gain Γg<sub>th</sub>", "modal_gain", "cm⁻¹", 5)}${row("Confinement Γ", "confinement", "", 5)}${row("Slope efficiency, top", "slope_top", "W/A", 4)}</table>`;
  if (a.converged === false) h += `<p class="hint">The threshold solver did not converge at the new wavelength.</p>`;
  const items = [];
  const t = rep.tune;
  if (t) {
    if (t.converged) items.push({ level: "ok", msg: `Tuned ${t.layers.length} layer(s), ${t.chosen}, by ×${fmt(t.scale, 6)}: cold-cavity resonance ${fmt(t.resonance, 8)} nm.` });
    else items.push({ level: "warn", msg: `Cavity not tuned: ${t.error || "no solution within ±70 % of the layer thickness"}. The resonance sits where the scaling put it.` });
  }
  items.push({ level: "info", msg: `${rep.scaled_layers} layer(s) scaled${rep.kept.length ? `; kept at their physical thickness: ${rep.kept.map(uniLabel).join(", ")}` : ""}.` });
  const ch = rep.checks || [];
  if (!ch.some((c) => c.level === "error" || c.level === "warn")) items.push({ level: "ok", msg: `No passive layer absorbs at ${fmt(rep.new_lambda, 6)} nm (every band gap at least ${0.1} eV above the photon energy).` });
  ch.forEach((c) => items.push({ level: c.level, msg: `${uniLabel(c.layer)}: ${c.msg}` }));
  h += `<ul class="rt-chk">${items.map((i) => `<li class="${i.level}">${i.level === "error" ? "✕ " : i.level === "warn" ? "⚠ " : ""}${esc(i.msg)}</li>`).join("")}</ul>`;
  $("#rt-out").innerHTML = h;
  $("#rt-apply").disabled = false;
  $("#rt-apply").textContent = ch.some((c) => c.level === "error") ? "Apply anyway" : "Apply";
}

function rtApply() {
  const r = RT.result; if (!r) return;
  const nd = r.design;
  // copy thicknesses / grading back so ids, selection and collapsed groups survive
  const walk = (a, b) => a.forEach((it, i) => {
    if (it.kind === "group") { if (b[i].grading) it.grading = b[i].grading; walk(it.children, b[i].children); }
    else { it.thickness = +(+b[i].thickness).toPrecision(9); }
  });
  walk(S.design.stack, nd.stack);
  S.design.design_wavelength = nd.design_wavelength;
  $("#design-lambda").value = nd.design_wavelength;
  $("#r-min").value = Math.round(nd.design_wavelength * 0.85); $("#r-max").value = Math.round(nd.design_wavelength * 1.15);
  $("#rt-dlg").close();
  changed(false); runAll();
  toast(`Design retargeted to ${fmt(nd.design_wavelength, 6)} nm (Undo reverts it)`, false, 4000);
}

$("#btn-retarget").addEventListener("click", rtOpen);
$("#rt-preview").addEventListener("click", rtPreview);
$("#rt-apply").addEventListener("click", rtApply);
$("#rt-new").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); rtPreview(); } });
// a changed input makes the preview stale (Enter in the box previews first, then fires "change" with the same value)
["#rt-new", "#rt-keep-active", "#rt-keep-metal", "#rt-tune"].forEach((s) => $(s).addEventListener("change", () => {
  if (RT.result && s === "#rt-new" && Math.abs(parseFloat($("#rt-new").value) - RT.result.report.new_lambda) < 1e-9) return;
  $("#rt-apply").disabled = true; RT.result = null;
}));
