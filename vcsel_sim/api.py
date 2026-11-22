"""JSON-in / JSON-out entry points used by the browser GUI (via Pyodide).

Every function takes and returns plain JSON strings so the JavaScript side never
touches Python objects. The same functions are convenient from Jupyter.
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import materials, laser, tmm, vrt, export, templates, cavity, fca, retarget as _rt
from .structure import Structure


def _clean(o):
    """Make numpy / complex values JSON serialisable (NaN/inf -> None)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, complex) or isinstance(o, np.complexfloating):
        return [_clean(o.real), _clean(o.imag)]
    return o


def _structure(design_json):
    d = json.loads(design_json) if isinstance(design_json, str) else design_json
    s = Structure.from_dict(d)
    materials.set_temperature(s.temperature)
    return s


def check_design(s, lam=None):
    """Input checks. Returns a list of warnings; raises ValueError for inputs that have no physical meaning.
    Errors: negative thickness or repeat count, a material model that is undefined at the wavelength.
    Warnings: a composition outside the material's fitted range, a wavelength outside the model's range."""
    if not (np.isfinite(s.design_wavelength) and s.design_wavelength > 0):
        raise ValueError(f"The design wavelength must be a positive number of nm (got {s.design_wavelength:g}).")
    if not s.temperature > -273.15:
        raise ValueError(f"The temperature must be above absolute zero, -273.15 °C (got {s.temperature:g} °C).")
    lam = float(lam or s.design_wavelength)
    warns, seen = [], set()
    if not 100 <= s.design_wavelength <= 20000:
        warns.append(f"The design wavelength {s.design_wavelength:g} nm is outside 100-20000 nm, beyond every material model.")

    def layer_check(L, where):
        if (L.thickness or 0) < 0:
            raise ValueError(f"{where} '{L.name}' has a negative thickness ({L.thickness:g} {L.thickness_unit}).")
        if L.index_mode == "fixed":
            return
        m = materials.MATERIALS.get(L.material)
        if m is None:
            raise ValueError(f"{where} '{L.name}': unknown material '{L.material}'.")
        key = (L.material, float(L.x or 0), float(L.y or 0))
        if key in seen:
            return
        seen.add(key)
        n = complex(np.atleast_1d(materials.index(L.material, lam, L.x, L.y))[0])
        if not np.isfinite(n.real):
            raise ValueError(f"{where} '{L.name}': the {m['label']} model is undefined at {lam:g} nm "
                             f"(the wavelength is at or above its band gap). Use a model that covers absorption.")
        for v, lab, rng in ((L.x, m.get("x_label"), m.get("x_range")), (L.y, m.get("y_label"), m.get("y_range"))):
            if lab and rng and not (rng[0] - 1e-9 <= float(v or 0) <= rng[1] + 1e-9):
                warns.append(f"{L.name}: {lab.split()[0]} = {float(v or 0):g} is outside the {m['label']} model's range "
                             f"({rng[0]:g}-{rng[1]:g}); the index is extrapolated.")
        vr = m.get("valid_nm")
        if vr and not (vr[0] <= lam <= vr[1]):
            warns.append(f"{L.name}: {lam:g} nm is outside the {m['label']} model's range ({vr[0]:g}-{vr[1]:g} nm); "
                         f"the index is extrapolated.")

    def walk(items):
        for it in items:
            if getattr(it, "kind", "layer") == "group":
                if int(it.repeats) < 0:
                    raise ValueError(f"Group '{it.name}' has a negative repeat count.")
                walk(it.children)
            else:
                layer_check(it, "Layer")
    layer_check(s.top, "Exit medium")
    layer_check(s.substrate, "Substrate")
    walk(s.stack)
    return warns


def ok(payload):
    return json.dumps({"ok": True, **_clean(payload)})


def fail(e):
    return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})


# ---------------------------------------------------------------------------
def material_catalog():
    try:
        return ok({"materials": materials.catalog()})
    except Exception as e:  # pragma: no cover
        return fail(e)


def layer_table(design_json, wavelength=None):
    """Expanded layer list with thickness, index and optical thickness at `wavelength`."""
    try:
        s = _structure(design_json)
        return ok({"layers": export.layer_rows(s, wavelength)})
    except Exception as e:
        return fail(e)


def index_profile(design_json, wavelength=None):
    try:
        s = _structure(design_json)
        return ok(export.index_profile(s, wavelength))
    except Exception as e:
        return fail(e)


def run_analysis(design_json, options_json="{}"):
    try:
        s = _structure(design_json)
        o = json.loads(options_json or "{}")
        warns = check_design(s)
        a = laser.analyze(s, lam_guess=o.get("lambda_guess"), normalize=o.get("normalize", "bottom"),
                          spacing_passive=float(o.get("spacing_passive", 2.0)),
                          spacing_active=float(o.get("spacing_active", 0.1)),
                          internal_efficiency=float(o.get("internal_efficiency", 1.0)),
                          rt_model=o.get("rt_model", "exact"),
                          confinement_model=o.get("confinement_model", "dispersive"))
        if not a.converged:
            raise ValueError("The threshold solver did not converge for this structure, so no results are shown. "
                             "Check for layers with very large absorption, or mirrors with almost no reflectance.")
        prof = a.field
        res = a.summary()
        if a.threshold_gain < 0:
            warns.append("The threshold gain is negative: the structure has net gain without pumping the wells "
                         "(a passive layer with negative absorption?). Efficiencies and losses are not meaningful.")
        res["warnings"] = warns
        try:
            res["cavity"] = cavity.cavity_report(laser.Model(s), a)
        except Exception as e:                       # never let the extra report break the analysis
            res["cavity"] = {"complete": False, "note": f"Cavity-length report failed: {e}"}
        # decimate passive regions for plotting if huge
        fld = {"z": prof.z, "E2": prof.E2, "n": prof.n}
        return ok({"results": res, "field": fld,
                   "profile": export.index_profile(s, a.wavelength)})
    except Exception as e:
        return fail(e)


SWEEP_KEYS = ["wavelength", "threshold_gain", "modal_gain", "confinement", "enhancement", "alpha_i", "alpha_m",
              "alpha_m_top", "alpha_m_bottom", "R_top", "R_bottom", "ext_eff", "ext_eff_top", "ext_eff_bottom",
              "slope_top", "slope_bottom", "lifetime_ps", "effective_length", "converged"]


def sweep_point(design_json, options_json="{}"):
    """One point of a parameter sweep: the threshold analysis without the field profile, returning
    only scalar results (plus passive mirror reflectances and the cavity optical thickness)."""
    try:
        s = _structure(design_json)
        o = json.loads(options_json or "{}")
        check_design(s)                                   # errors only; warnings are shown by the Results tab
        tuned = None
        if o.get("retune"):
            # keep the cavity on the design wavelength: re-tune the marked layers (or the cavity spacers),
            # skipping the parts of the design that the sweep itself is varying
            if o.get("tune_paths"):                     # the layers the user picked for re-tuning
                ex = [tuple(e) for e in (o.get("exclude") or []) if e is not None]
                picked = [tuple(p) for p in o["tune_paths"]]
                clash = [p for p in picked if any(p[:len(e)] == e for e in ex)]
                if clash:
                    raise ValueError("a re-tune layer is also being varied by the sweep")
                layers = [_rt.at_path(s, p) for p in picked]
                layers = [L for L in layers if L is not None and getattr(L, "kind", "layer") == "layer"]
                if not layers:
                    raise ValueError("no re-tune layers")
            else:
                layers, _ = _rt.tuning_layers(s, o.get("exclude") or [])
            t = _rt.tune_layers(s, layers, s.design_wavelength, start=float(o.get("retune_start") or 1.0))
            if not t["converged"]:
                raise ValueError(f"re-tuning to {s.design_wavelength:g} nm failed")
            ids = {id(L) for L in layers}
            tuned = {"scale": t["scale"], "layers": [{"path": list(p), "thickness": L.thickness}
                                                     for L, p, _ in _rt.walk_layers(s.stack) if id(L) in ids]}
            o["lambda_guess"] = s.design_wavelength
        a = laser.analyze(s, lam_guess=o.get("lambda_guess"), normalize="bottom", spacing_passive=50.0,
                          spacing_active=1.0, internal_efficiency=float(o.get("internal_efficiency", 1.0)),
                          rt_model=o.get("rt_model", "exact"),
                          confinement_model=o.get("confinement_model", "dispersive"))
        if not a.converged:
            raise ValueError("threshold solver did not converge")
        r = a.summary()
        out = {k: r.get(k) for k in SWEEP_KEYS}
        flat = s.flatten()
        out["total_thickness_um"] = float(sum(f.thickness_nm for f in flat)) / 1000
        try:
            c = cavity.cavity_report(laser.Model(s), a)
            out["R_top_passive"] = c.get("R_top_passive")
            out["R_bottom_passive"] = c.get("R_bottom_passive")
            out["cavity_optical_waves"] = c.get("cavity_optical_waves")
            out["L_pen_top"] = (c.get("top") or {}).get("L_eff_phase")
            out["L_pen_bottom"] = (c.get("bottom") or {}).get("L_eff_phase")
            out["L_cav"] = c.get("L_cav")
            out["L_cav_pen"] = (c.get("phase") or {}).get("L")          # L_cav + both phase penetration depths
        except Exception:
            pass
        if tuned:
            out["retune_scale"] = tuned["scale"]
            out["tuned"] = tuned["layers"]
        return ok({"point": out})
    except Exception as e:
        return fail(e)


def reflectance(design_json, options_json="{}"):
    try:
        s = _structure(design_json)
        o = json.loads(options_json or "{}")
        lam0 = s.design_wavelength
        span = float(o.get("span", 0.3 * lam0))
        lo = float(o.get("lambda_min", lam0 - span / 2))
        hi = float(o.get("lambda_max", lam0 + span / 2))
        parts = o.get("parts", ["full_top"])
        npts = o.get("points", 2001)
        if not (np.isfinite(lo) and np.isfinite(hi) and lo > 0 and hi > 0):
            raise ValueError(f"The wavelength range must be positive (got {lo:g} to {hi:g} nm).")
        if not (isinstance(npts, (int, float)) and float(npts).is_integer() and 2 <= npts <= 200001):
            raise ValueError(f"Points must be a whole number from 2 to 200001 (got {npts}).")
        if lo > hi:
            lo, hi = hi, lo
        out = {}
        # every spectrum on one common grid (the union of each part's refined grid), so CSV columns line up
        grids = []
        for p in parts:
            try:
                grids.append(laser.reflectance_spectrum(s, lo, hi, int(o.get("points", 2001)), p)["wavelength"])
            except ValueError:
                pass
        common = np.unique(np.concatenate(grids)) if grids else None
        for p in parts:
            try:
                spec = laser.reflectance_spectrum(s, lo, hi, int(o.get("points", 2001)), p, wavelengths=common)
                st = laser.stopband(spec, float(o.get("threshold", 0.99)), lam0)
                try:
                    at = laser.reflectance_spectrum(s, lam0, lam0, 1, p)
                    at_d = {"R": float(at["R"][0]), "T": float(at["T"][0]), "phase_deg": float(at["phase_deg"][0])}
                except ValueError:
                    at_d = {"R": None, "T": None, "phase_deg": None}
                note = None
                if np.any(spec["undefined"]):
                    w = spec["wavelength"][spec["undefined"]]
                    note = ("Blank below %.0f nm: the incident medium absorbs strongly there, so reflectance "
                            "seen from inside it is not defined." % w.max()) if w.max() < hi else (
                            "Some points are blank where the incident medium absorbs strongly.")
                out[p] = {"wavelength": spec["wavelength"], "R": spec["R"], "T": spec["T"], "A": spec["A"],
                          "phase_deg": spec["phase_deg"], "stopband": st, "at_design": at_d, "note": note}
            except ValueError as e:
                out[p] = {"error": str(e)}
        return ok({"spectra": out, "design_wavelength": lam0})
    except Exception as e:
        return fail(e)


def export_vrt(design_json, threshold_gain=0.0):
    """Design -> older-format Vertical .vrt, returned base64-encoded."""
    try:
        import base64
        from .vrt_write import write_vrt
        s = _structure(design_json)
        return ok({"b64": base64.b64encode(write_vrt(s, threshold_gain=float(threshold_gain or 0.0))).decode()})
    except Exception as e:
        return fail(e)


def import_vrt_bytes(data, filename="design.vrt"):
    try:
        s = vrt.read_vrt(bytes(data), name=filename.rsplit(".", 1)[0])
        return ok({"design": s.to_dict()})
    except Exception as e:
        return fail(e)


def csv_export(design_json, kind, payload_json="{}"):
    try:
        s = _structure(design_json)
        return ok({"csv": export.csv(s, kind, json.loads(payload_json or "{}"))})
    except Exception as e:
        return fail(e)


def tune_cavity(design_json, target=None):
    """Vertical's Force Wave: scale marked layers so the cold cavity resonates at the target wavelength."""
    try:
        s = _structure(design_json)
        rep = laser.tune_marked(s, target)
        return ok({"design": s.to_dict(), "report": rep})
    except Exception as e:
        return fail(e)


def center_wells(design_json, target=None):
    """Slide the active region onto a standing-wave peak (marked layer above the wells) while keeping the
    cavity resonant (marked layer below), see retarget.center_wells."""
    try:
        s = _structure(design_json)
        rep = _rt.center_wells(s, target)
        return ok({"design": s.to_dict(), "report": rep})
    except Exception as e:
        return fail(e)


def retarget_design(design_json, options_json="{}"):
    """Move the design to a new wavelength (see retarget.py). Returns the new design, a report with the
    absorption checks, and a before / after comparison of the threshold analysis."""
    try:
        o = json.loads(options_json or "{}")
        s = _structure(design_json)

        def brief(st, guess):
            try:
                a = laser.analyze(st, lam_guess=guess, normalize="bottom", spacing_passive=50.0, spacing_active=1.0,
                                  rt_model=o.get("rt_model", "exact"),
                                  confinement_model=o.get("confinement_model", "dispersive"))
                r = a.summary()
                return {k: r.get(k) for k in ("wavelength", "threshold_gain", "modal_gain", "slope_top", "confinement", "converged")}
            except Exception as e:  # e.g. no active layer
                return {"error": str(e)}
        before = brief(s, o.get("lambda_guess"))
        rep = _rt.retarget(s, float(o["wavelength"]), keep_active=bool(o.get("keep_active", True)),
                           keep_metal=bool(o.get("keep_metal", True)), tune=bool(o.get("tune", True)))
        after = brief(s, s.design_wavelength)
        return ok({"design": s.to_dict(), "report": rep, "before": before, "after": after})
    except Exception as e:
        return fail(e)


def absorption_check(design_json, wavelength=None):
    try:
        s = _structure(design_json)
        return ok({"checks": _rt.absorption_check(s, float(wavelength or s.design_wavelength))})
    except Exception as e:
        return fail(e)


def material_index(material, x, y, lam_min, lam_max, points=400, temperature=None):
    try:
        if temperature is not None:
            materials.set_temperature(temperature)
        lam = np.linspace(float(lam_min), float(lam_max), int(points))
        n = materials.index(material, lam, x, y)
        return ok({"wavelength": lam, "n": n.real, "k": n.imag, "bandgap": materials.bandgap(material, x, y)})
    except Exception as e:
        return fail(e)


def template(name):
    try:
        f = {"gaas_980": templates.gaas_980, "algaas_850": templates.algaas_850,
             "dielectric_dbr": templates.dielectric_dbr}[name]
        return ok({"design": f().to_dict()})
    except Exception as e:
        return fail(e)


def node_info(design_json):
    """Per-layer values for every layer node of the (unexpanded) tree, in depth-first order,
    plus totals. Used by the GUI's stack view."""
    try:
        s = _structure(design_json)
        lam = s.design_wavelength
        nodes = []

        def walk(items):
            for it in items:
                if getattr(it, "kind", "layer") == "group":
                    walk(it.children)
                else:
                    n = complex(np.atleast_1d(it.index(lam))[0])
                    fam = fca.family(it.material)
                    car = fca.carrier_of(it.layer_type)
                    sg = fca.sigma(it.material, car, lam, it.fca_model, it.x, it.doping) if (fam and car) else None
                    nodes.append({"d": it.physical_thickness(lam), "n": n.real, "k": n.imag,
                                  "alpha": float(np.atleast_1d(it.alpha(lam))[0]),
                                  "fca": {"family": fam, "carrier": car, "ref": fca.reference(it.material, car, it.fca_model) if car else None,
                                          "variants": fca.variants(it.material, car),
                                          "sigma": float(np.atleast_1d(sg)[0]) if sg is not None else None},
                                  "eg": materials.bandgap(it.material, it.x, it.y) if it.index_mode == "model" else None})
        walk(s.stack)
        flat = s.flatten()
        nt = complex(np.atleast_1d(s.top.index(lam))[0])
        nsub = complex(np.atleast_1d(s.substrate.index(lam))[0])
        return ok({"nodes": nodes, "n_layers": len(flat), "total_nm": float(sum(f.thickness_nm for f in flat)),
                   "top": {"n": nt.real, "k": nt.imag}, "substrate": {"n": nsub.real, "k": nsub.imag}})
    except Exception as e:
        return fail(e)


def _layer_spec(d, name, thickness=None, unit="waves"):
    from .structure import Layer
    L = Layer(name=d.get("name") or name, material=d.get("material", "Generic"), x=float(d.get("x", 0) or 0),
              y=float(d.get("y", 0) or 0), index_mode=d.get("index_mode", "model"),
              n_real=float(d.get("n_real", 3.5) or 3.5), n_imag=float(d.get("n_imag", 0) or 0),
              absorption=float(d.get("absorption", 0) or 0), layer_type=d.get("layer_type", "undoped"))
    if thickness is not None:
        L.thickness, L.thickness_unit = float(thickness), unit
    if L.material in ("Generic",):
        L.index_mode = "fixed"
    return L


def _r_vs_pairs(build, M, lam0):
    """R at lam0 of the 1..M-pair mirror in one pass: identical periods give the characteristic matrix P^k, so
    the field at the top follows from the substrate by applying P^-1 once per added pair (same convention as
    laser.reflectance_spectrum 'full_top': incident medium taken as lossless)."""
    s1 = build(1)
    model = laser.Model(s1)
    lam = np.array([float(lam0)])
    ns = model.indices(lam, 0.0)
    n0 = np.real(ns[0]) + 0j
    m11, m12, m21, m22 = (complex(x[0]) for x in tmm.characteristic_matrix(ns, list(model.d), lam))
    det = m11 * m22 - m12 * m21
    i11, i12, i21, i22 = m22 / det, -m12 / det, -m21 / det, m11 / det          # P^-1: bottom -> top of one pair
    E, H = 1.0 + 0j, complex(ns[-1][0])                                        # outgoing wave in the exit medium
    out = []
    for _ in range(M):
        E, H = i11 * E + i12 * H, i21 * E + i22 * H
        A0, B0 = 0.5 * (E + H / n0[0]), 0.5 * (E - H / n0[0])
        out.append(float(abs(B0 / A0) ** 2))
    return out


def dbr_design(options_json):
    """Stand-alone quarter-wave DBR designer.

    options: {lambda0, pairs, first: {material,x,...}, second: {...}, incident: {...}, exit: {...},
              lambda_min, lambda_max, points, targets: [0.99, ...], role, name}
    `first` is the layer next to the incident medium. Both are quarter-wave at lambda0
    unless `first_waves` / `second_waves` are given.
    """
    try:
        from .structure import Group, Layer
        from .cavity import coldren_leff
        o = json.loads(options_json) if isinstance(options_json, str) else options_json
        lam0 = float(o.get("lambda0", 980))
        materials.set_temperature(o.get("temperature", 23.0))
        try:
            pf = float(o.get("pairs", 20))
        except (TypeError, ValueError):
            raise ValueError("Pairs must be a whole number.")
        if pf != int(pf):
            raise ValueError(f"Pairs must be a whole number (got {pf:g}).")
        m = int(pf)
        if not 1 <= m <= 1000:
            raise ValueError(f"Pairs must be between 1 and 1000 (got {m}).")
        A = _layer_spec(o["first"], "first", o.get("first_waves", 0.25))
        B = _layer_spec(o["second"], "second", o.get("second_waves", 0.25))
        inc = _layer_spec(o.get("incident", {"material": "Air"}), "incident")
        ext = _layer_spec(o.get("exit", {"material": "AlGaAs", "x": 0}), "exit")

        grading = o.get("grading") or None
        if grading and (grading.get("profile", "none") in ("none", "") or not float(grading.get("thickness_nm", 0) or 0)):
            grading = None

        def build(npairs):
            return Structure(name="DBR", design_wavelength=lam0, top=inc, substrate=ext,
                             stack=[Group(name=o.get("name", "DBR"), repeats=npairs, children=[A, B], grading=grading)])

        s = build(m)
        lo = float(o.get("lambda_min", lam0 * 0.8))
        hi = float(o.get("lambda_max", lam0 * 1.2))
        # a bare mirror has no narrow features, so the uniform grid needs no refinement
        spec = laser.reflectance_spectrum(s, lo, hi, int(o.get("points", 2001)), "full_top", refine=False)
        st = laser.stopband(spec, float(o.get("threshold", 0.99)), lam0)
        at = laser.reflectance_spectrum(s, lam0, lam0, 1, "full_top")
        nB = float(np.real(np.atleast_1d(B.index(lam0))[0]))
        nA = float(np.real(np.atleast_1d(A.index(lam0))[0]))
        n0 = float(np.real(np.atleast_1d(inc.index(lam0))[0]))
        ns = float(np.real(np.atleast_1d(ext.index(lam0))[0]))
        nH, nL = max(nA, nB), min(nA, nB)
        dA, dB = A.physical_thickness(lam0), B.physical_thickness(lam0)
        graded_note = None
        if grading:
            from .structure import can_grade
            if not can_grade(A, B):
                graded_note = "Grading ignored: it needs the same alloy model on both layers (e.g. AlGaAs with two compositions)."
                grading = None
        flat = build(m).flatten()
        # analytic quarter-wave reflectance (lossless, real indices)
        Y = (nA / nB) ** (2 * m) * ns
        R_an = ((n0 - Y) / (n0 + Y)) ** 2
        dl_stop = 4 * lam0 / math.pi * math.asin((nH - nL) / (nH + nL)) if nH > nL else 0.0
        pen = coldren_leff(nL, nH, m, dA + dB) if nH > nL else {}
        # R at lambda0 versus number of pairs
        M = min(int(o.get("max_pairs", max(2 * m, 40))), 2000)
        Rm = _r_vs_pairs(build, M, lam0) if not grading else [
            float(laser.reflectance_spectrum(build(k), lam0, lam0, 1, "full_top")["R"][0]) for k in range(1, M + 1)]
        need = {}
        for t in o.get("targets", [0.99, 0.995, 0.999, 0.9995, 0.9999]):
            k = next((i + 1 for i, r in enumerate(Rm) if r >= t), None)
            need[str(t)] = k
        grp = Group(name=o.get("name", "DBR"), repeats=m, role=o.get("role", "none"), children=[A, B], grading=grading)
        return ok({
            "spectrum": {"wavelength": spec["wavelength"], "R": spec["R"], "T": spec["T"],
                         "phase_deg": spec["phase_deg"]},
            "stopband": st, "at_design": {"R": float(at["R"][0]), "T": float(at["T"][0]),
                                          "phase_deg": float(at["phase_deg"][0])},
            "n_first": nA, "n_second": nB, "n_incident": n0, "n_exit": ns,
            "d_first": dA, "d_second": dB, "period": dA + dB, "total_thickness": float(sum(f.thickness_nm for f in flat)),
            "graded": bool(grading), "graded_note": graded_note,
            "layers": [{"name": f.layer.name, "x": f.layer.x, "y": f.layer.y, "material": f.layer.material, "d": f.thickness_nm} for f in flat],
            "R_analytic": R_an, "stopband_analytic": dl_stop, "penetration": pen,
            "R_vs_pairs": Rm, "pairs_needed": need, "group": grp.to_dict(),
        })
    except Exception as e:
        return fail(e)
