"""Move a design to another wavelength and keep a cavity on resonance.

* `tuning_layers` picks the layers that "Tune cavity" and the sweep's re-tune option adjust: the layers marked
  for tuning, or (when none are marked) the cavity spacers, i.e. the non-active layers between the top and
  bottom mirrors. Layers inside excluded parts of the tree are skipped, so a sweep can vary one spacer and
  re-tune the other.
* `tune_layers` scales those layers by one common factor until the cold-cavity resonance sits on the target.
* `retarget` rescales every layer so that it keeps its optical thickness in waves at the new wavelength,
  including the material dispersion: d_new = d_old (lam_new / lam_old) n(lam_old) / n(lam_new). Quantum
  wells (active layers) and metals keep their physical thickness by default, and a final small re-tune of the
  cavity spacers puts the resonance exactly on the new wavelength.
* `absorption_check` lists layers whose band gap is at or close to the photon energy at a wavelength, and
  reports where the active layer's band edge sits.
"""
from __future__ import annotations

import numpy as np

from . import materials
from .structure import Group, Structure

HC_EV_NM = 1239.84193
NEAR_EDGE_EV = 0.10           # passive layers closer than this to their direct gap get a warning


# ---------------------------------------------------------------------------
# tree helpers
# ---------------------------------------------------------------------------
def at_path(structure: Structure, path):
    it = None
    items = structure.stack
    for i in path:
        it = items[int(i)]
        items = getattr(it, "children", [])
    return it


def walk_layers(items, path=(), inside=()):
    """Yield (layer, path, enclosing groups) for every layer of a tree, top to bottom."""
    for i, it in enumerate(items):
        p = (*path, i)
        if isinstance(it, Group):
            yield from walk_layers(it.children, p, (*inside, it))
        else:
            yield it, p, inside


def _excluded(path, exclude):
    return any(tuple(path[:len(e)]) == tuple(e) for e in exclude)


def tuning_layers(structure: Structure, exclude=()):
    """Layers adjusted when tuning the cavity, with a short description of how they were chosen."""
    exclude = [tuple(e) for e in (exclude or []) if e is not None]
    marked = [(L, p) for L, p, _ in walk_layers(structure.stack) if L.marked and not _excluded(p, exclude)]
    if marked:
        return [L for L, _ in marked], "marked layers"
    # no marked layers: the cavity spacers between the mirrors (top-level layers, or layers in groups without
    # a mirror / active role), excluding active layers
    stack = structure.stack
    tops = [i for i, it in enumerate(stack) if isinstance(it, Group) and it.role == "top_dbr"]
    bots = [i for i, it in enumerate(stack) if isinstance(it, Group) and it.role == "bottom_dbr"]
    lo = max(tops) + 1 if tops else 0
    hi = min(bots) if bots else len(stack)
    out = []
    for L, p, groups in walk_layers(stack[lo:hi], (), ()):
        p = (p[0] + lo, *p[1:])
        if L.is_active or L.layer_type == "metal" or _excluded(p, exclude):
            continue
        if any(g.role in ("active", "top_dbr", "bottom_dbr") or g.repeats != 1 for g in groups):
            continue
        out.append(L)
    if not out:
        raise ValueError("No layers to tune: mark the cavity spacer layer(s) with 'Marked for tuning' "
                         "(a sweep cannot re-tune with the layer it is varying).")
    return out, "cavity spacers (no layers are marked)"


def tune_layers(structure: Structure, layers, target=None, tol=1e-6, maxit=40, start=1.0):
    """Scale the thickness of `layers` by a common factor until the real part of the cold-cavity mode equals
    `target` (default: design wavelength). Modifies the layers in place; returns a report dict. On failure
    the thicknesses are restored. `start` is the first scale tried; a sweep passes the previous point's factor
    so the cavity stays on the same longitudinal order (a factor far from it can land one half-wave longer)."""
    from .laser import Model, cold_cavity_mode
    target = float(target or structure.design_wavelength)
    base = [(L, L.thickness) for L in layers]

    def resonance(scale):
        for L, t0 in base:
            L.thickness = t0 * scale
        # always start the mode search at the target so the solver stays on the cavity mode
        return cold_cavity_mode(Model(structure), target).real - target

    s_lo, s_hi = 0.3, 3.0
    s0 = float(start) if start and 0.3 < float(start) < 3.0 else 1.0
    s1 = s0 * 1.02
    f0 = resonance(s0)
    if abs(f0) < tol:
        return {"scale": s0, "resonance": f0 + target, "converged": True, "iterations": 1,
                "layers": [{"name": L.name, "old": t0, "new": L.thickness, "unit": L.thickness_unit} for L, t0 in base]}
    f1 = resonance(s1)
    br = (s0, f0, s1, f1) if f0 * f1 < 0 else None
    it = 0
    for it in range(maxit):
        if abs(f1) < tol:
            break
        s2 = s1 - f1 * (s1 - s0) / (f1 - f0) if f1 != f0 else s1 * (0.9 if f1 > 0 else 1.1)
        s2 = min(max(s2, 0.8 * s1, s_lo), 1.25 * s1, s_hi)      # at most ±20–25 % per step
        if br is not None and not (min(br[0], br[2]) < s2 < max(br[0], br[2])):
            s2 = 0.5 * (br[0] + br[2])
        f2 = resonance(s2)
        if br is not None:
            br = (br[0], br[1], s2, f2) if br[1] * f2 < 0 else (s2, f2, br[2], br[3])
        elif f1 * f2 < 0:
            br = (s1, f1, s2, f2)
        s0, f0, s1, f1 = s1, f1, s2, f2
        if br is None and s1 in (s_lo, s_hi) and s0 == s1:
            break
    ok = abs(f1) <= 1e-3
    if not ok:
        for L, t0 in base:
            L.thickness = t0
    return {"scale": s1, "resonance": f1 + target, "converged": ok, "iterations": it + 2,
            "layers": [{"name": L.name, "old": t0, "new": L.thickness, "unit": L.thickness_unit} for L, t0 in base]}


# ---------------------------------------------------------------------------
# retarget
# ---------------------------------------------------------------------------
def _n_ref(L, lam):
    """Real index at the reference temperature (the one layers given in waves are converted at)."""
    if L.index_mode == "fixed":
        return float(L.n_real)
    t_now = materials.TEMPERATURE_C
    materials.set_temperature(materials.REFERENCE_TEMPERATURE_C)
    try:
        return float(np.real(materials.index(L.material, lam, L.x, L.y)))
    finally:
        materials.set_temperature(t_now)


def _is_metal(L):
    return L.layer_type == "metal" or materials.MATERIALS.get(L.material, {}).get("category") == "Metals"


def retarget(structure: Structure, new_lam, keep_active=True, keep_metal=True, tune=True):
    """Rescale `structure` in place from its design wavelength to `new_lam` (nm). Returns a report."""
    old = float(structure.design_wavelength)
    new = float(new_lam)
    if not (100 <= new <= 20000):
        raise ValueError("The new wavelength must be between 100 nm and 20 µm.")
    changed, kept = 0, []
    for L, _, _ in walk_layers(structure.stack):
        keep = (keep_active and L.is_active) or (keep_metal and _is_metal(L))
        if L.thickness_unit == "waves":
            if keep:                                  # same physical thickness, expressed in waves at the new lambda
                d = L.physical_thickness(old)
                L.thickness = d * _n_ref(L, new) / new
                kept.append(L.name)
            else:
                changed += 1                          # same optical thickness: nothing to do once lambda changes
        else:
            if keep:
                kept.append(L.name)
                continue
            n_o, n_n = _n_ref(L, old), _n_ref(L, new)
            ratio = n_o / n_n if n_o > 0.05 and n_n > 0.05 else 1.0
            L.thickness = float(L.thickness) * new / old * ratio
            changed += 1

    def grades(items):
        for it in items:
            if isinstance(it, Group):
                if it.grading and float(it.grading.get("thickness_nm", 0) or 0) > 0:
                    it.grading = {**it.grading, "thickness_nm": float(it.grading["thickness_nm"]) * new / old}
                grades(it.children)
    grades(structure.stack)
    structure.design_wavelength = new

    rep = {"old_lambda": old, "new_lambda": new, "scaled_layers": changed, "kept": sorted(set(kept)), "tune": None}
    if tune:
        try:
            layers, how = tuning_layers(structure)
            t = tune_layers(structure, layers, new)
            t["chosen"] = how
            rep["tune"] = t
        except ValueError as e:
            rep["tune"] = {"converged": False, "error": str(e)}
    rep["checks"] = absorption_check(structure, new)
    return rep


# ---------------------------------------------------------------------------
# safeguards
# ---------------------------------------------------------------------------
def absorption_check(structure: Structure, lam):
    """Compare the photon energy at `lam` with each semiconductor layer's direct gap.

    Returns a list of {level: "error"|"warn"|"info", layer, msg}. Passive layers (and the substrate) at or above
    their gap absorb band-to-band, which the index models here do not include; within NEAR_EDGE_EV of it the
    Urbach tail adds loss and the dispersion models lose accuracy. For the active layer the bulk band edge is
    reported: a quantum well emits above the bulk gap by its confinement energy, so its composition (not the
    mirrors) sets where the gain is."""
    E = HC_EV_NM / float(lam)
    seen, out = set(), []

    def check(L, where):
        if L.index_mode == "fixed":
            return
        m = materials.MATERIALS.get(L.material, {})
        vr = m.get("valid_nm")
        key = (L.material, round(float(L.x or 0), 4), round(float(L.y or 0), 4), L.is_active, where)
        if key in seen:
            return
        seen.add(key)
        if vr and not (vr[0] <= lam <= vr[1]):
            out.append({"level": "warn", "layer": L.name,
                        "msg": f"{m.get('label', L.material)} index model is valid {vr[0]:g}–{vr[1]:g} nm."})
        try:
            Eg = materials.bandgap(L.material, L.x, L.y)
        except Exception:
            Eg = None
        if Eg is None:
            return
        lg = HC_EV_NM / Eg
        if L.is_active:
            d = E - Eg
            if d < -0.01:
                out.append({"level": "error", "layer": L.name, "msg":
                            f"Photon energy {E:.3f} eV is below the active layer's bulk gap {Eg:.3f} eV (λg = {lg:.0f} nm): "
                            "it cannot provide gain here. Change its composition."})
            elif d > 0.15:
                out.append({"level": "warn", "layer": L.name, "msg":
                            f"Photon energy is {1000 * d:.0f} meV above the active layer's bulk gap {Eg:.3f} eV (λg = {lg:.0f} nm), "
                            "more than a typical quantum-well confinement shift. The gain peak will not follow the cavity: "
                            "change the well composition or thickness."})
            else:
                out.append({"level": "info", "layer": L.name, "msg":
                            f"Active layer bulk gap {Eg:.3f} eV (λg = {lg:.0f} nm); the photon is {1000 * d:.0f} meV above it. "
                            "Check the quantum-well transition against the new wavelength."})
            return
        what = "Substrate" if where == "substrate" else "Layer"
        if E >= Eg:
            out.append({"level": "error", "layer": L.name, "msg":
                        f"{what} absorbs: photon energy {E:.3f} eV ≥ its gap {Eg:.3f} eV (λg = {lg:.0f} nm). "
                        "Band-to-band absorption is not in the index model, so the result would be optimistic."})
        elif Eg - E < NEAR_EDGE_EV:
            out.append({"level": "warn", "layer": L.name, "msg":
                        f"{what} gap {Eg:.3f} eV (λg = {lg:.0f} nm) is only {1000 * (Eg - E):.0f} meV above the photon energy: "
                        "band-tail absorption and index-model error grow near the edge."})

    for L, _, _ in walk_layers(structure.stack):
        check(L, "stack")
    check(structure.substrate, "substrate")
    order = {"error": 0, "warn": 1, "info": 2}
    out.sort(key=lambda w: order[w["level"]])
    return out
