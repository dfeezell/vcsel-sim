/* Pop-up layer editor.
   In "pop-up" mode the Properties panel leaves the left column (so the stack gets the full height) and
   opens as a floating window beside the layer you click. ▲ / ▼ step to the layer above / below without
   leaving the editor; the window can be dragged by its title bar and remembers where you put it.
   "Dock" puts it back in the left column as before. */
const ED = { float: true, open: false, pos: null };

function edOrder() {                       // every editable item, top -> bottom, groups before their children
  const out = [["top"]];
  const walk = (items, p) => items.forEach((it, i) => { const q = [...p, i]; out.push(q); if (it.kind === "group") walk(it.children, q); });
  walk(S.design.stack, ["stack"]);
  out.push(["sub"]);
  return out;
}
function edStep(dir) {
  if (!S.design) return;
  const ord = edOrder(); const key = S.sel.join(",");
  let i = ord.findIndex((p) => p.join(",") === key);
  // arrows walk layers only (groups are reached by clicking their label)
  do { i += dir; } while (i > 0 && i < ord.length - 1 && getAt(ord[i])?.kind === "group");
  if (i < 0 || i >= ord.length) return;
  S.sel = ord[i]; VIEW.scrollToSel = true;
  renderStack(); renderProps(); edScrollList(); edUpdateNav();
  const first = $("#props input:not([disabled]), #props select"); if (first && ED.focusFirst) first.focus();
}
function edScrollList() {
  const row = $(`#stack .row[data-path="${S.sel.join(",")}"]`); if (row) row.scrollIntoView({ block: "nearest" });
}
function edUpdateNav() {
  if (!S.design) return;
  const ord = edOrder().filter((p) => getAt(p)?.kind !== "group" || p.join(",") === S.sel.join(","));
  const i = ord.findIndex((p) => p.join(",") === S.sel.join(","));
  $("#p-pos").textContent = i >= 0 ? `${i + 1} / ${ord.length}` : "";
  $("#p-prev").disabled = i <= 0; $("#p-next").disabled = i < 0 || i >= ord.length - 1;
}
function edPlace(anchor) {
  const panel = $(".props-panel");
  if (ED.pos) { panel.style.left = ED.pos.x + "px"; panel.style.top = ED.pos.y + "px"; return; }
  const left = $(".left").getBoundingClientRect();
  const w = panel.offsetWidth || 420, h = panel.offsetHeight || 400;
  let x = left.right + 10;
  if (x + w > innerWidth - 8) x = Math.max(8, innerWidth - w - 8);
  let y = anchor ? anchor.getBoundingClientRect().top - 40 : left.top + 40;
  y = Math.min(Math.max(8, y), Math.max(8, innerHeight - h - 8));
  panel.style.left = x + "px"; panel.style.top = y + "px";
}
function edOpen(anchor) {
  if (!ED.float) return;
  const wasOpen = ED.open;
  ED.open = true; document.body.classList.add("props-open");
  edUpdateNav();
  if (!wasOpen || !ED.pos) edPlace(anchor);
}
function edClose() { ED.open = false; document.body.classList.remove("props-open"); }
function edSetFloat(on, save = true) {
  ED.float = on;
  document.body.classList.toggle("props-float", on);
  if (on) { document.body.classList.remove("props-collapsed"); edClose(); }
  else { const p = $(".props-panel"); p.style.left = p.style.top = ""; }
  $("#btn-dock").textContent = on ? "⇲ Dock" : "⇱ Pop out";
  $("#btn-dock").title = on ? "Put the editor back under the stack" : "Edit layers in a pop-up window beside the stack";
  if (save) try { localStorage.setItem("vcsel-props-float", on ? "1" : "0"); } catch (_) { /* */ }
  edUpdateNav();
}

function initLayerEditor() {
  const head = $(".props-panel .panel-head");
  $("#props-title").insertAdjacentHTML("afterend", `<span class="pnav">
      <button class="icon" id="p-prev" title="Layer above (Alt+↑)">▲</button><span id="p-pos"></span>
      <button class="icon" id="p-next" title="Layer below (Alt+↓)">▼</button></span>
    <span class="spacer"></span><button class="icon" id="btn-dock"></button>
    <button class="icon" id="p-close" title="Close (Esc)">✕</button>`);
  $("#p-prev").addEventListener("click", () => edStep(-1));
  $("#p-next").addEventListener("click", () => edStep(1));
  $("#p-close").addEventListener("click", edClose);
  $("#btn-dock").addEventListener("click", () => { const f = !ED.float; edSetFloat(f); if (f) edOpen(); });

  // open on a click in the stack (list rows, diagram blocks, group labels, boundaries, the to-scale strip)
  document.addEventListener("click", (e) => {
    if (!ED.float) return;
    if (e.target.closest("input, select, [data-toggle], .chip, #dg-ctrls, .dg-palette")) return;
    const hit = e.target.closest("#stack .row[data-path], #stack-diagram [data-path], #stack-diagram .dg-strip rect[data-path]");
    if (!hit || hit.dataset.path === "stack") return;
    // the stack re-renders on selection, so open once the click has been handled
    setTimeout(() => edOpen($("#stack-diagram .dg-blocks .sel, #stack .row.sel")), 0);
  }, true);
  // clicking anywhere else (plots, tabs, toolbar) closes it, so it never sits over the graphs
  document.addEventListener("pointerdown", (e) => {
    if (!ED.float || !ED.open) return;
    if (e.target.closest(".props-panel, #stack, #stack-diagram, .stack-tools, .toast, .menu-list")) return;
    edClose();
  });
  // new layer / group from the toolbar -> edit it straight away
  $$(".stack-tools [data-act='add-layer'], .stack-tools [data-act='add-group']").forEach((b) =>
    b.addEventListener("click", () => setTimeout(() => edOpen($("#stack-diagram .sel, #stack .row.sel")), 0)));

  document.addEventListener("keydown", (e) => {
    if (!ED.float || !ED.open) return;
    if (e.key === "Escape") { edClose(); return; }
    if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      const a = document.activeElement; if (a && $("#props").contains(a)) a.dispatchEvent(new Event("change", { bubbles: true }));
      ED.focusFirst = $("#props").contains(document.activeElement);
      edStep(e.key === "ArrowUp" ? -1 : 1); ED.focusFirst = false;
    }
  });

  // drag the window by its title bar
  head.addEventListener("pointerdown", (e) => {
    if (!ED.float || e.target.closest("button, input, select")) return;
    const p = $(".props-panel"); const r = p.getBoundingClientRect();
    const dx = e.clientX - r.left, dy = e.clientY - r.top;
    head.setPointerCapture(e.pointerId);
    const mv = (ev) => {
      ED.pos = { x: Math.min(Math.max(0, ev.clientX - dx), innerWidth - 60), y: Math.min(Math.max(0, ev.clientY - dy), innerHeight - 40) };
      p.style.left = ED.pos.x + "px"; p.style.top = ED.pos.y + "px";
    };
    const up = () => { head.removeEventListener("pointermove", mv); head.removeEventListener("pointerup", up); };
    head.addEventListener("pointermove", mv); head.addEventListener("pointerup", up);
  });
  head.addEventListener("dblclick", (e) => { if (ED.float && !e.target.closest("button")) { ED.pos = null; edPlace($("#stack-diagram .sel, #stack .row.sel")); } });

  // keep the position counter right after any edit that re-renders the stack
  const _rp = window.renderProps;
  if (typeof _rp === "function") window.renderProps = function () { _rp.apply(this, arguments); edUpdateNav(); };

  let f = true; try { f = localStorage.getItem("vcsel-props-float") !== "0"; } catch (_) { /* */ }
  edSetFloat(f, false);
}
initLayerEditor();
