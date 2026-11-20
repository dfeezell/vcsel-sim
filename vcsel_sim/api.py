"""JSON-in / JSON-out entry points used by the browser GUI (via Pyodide).

Every function takes and returns plain JSON strings so the JavaScript side never
touches Python objects. The same functions are convenient from Jupyter.
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import materials, laser, vrt, export, templates, cavity, fca
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
        a = laser.analyze(s, lam_guess=o.get("lambda_guess"), normalize=o.get("normalize", "bottom"),
                          spacing_passive=float(o.get("spacing_passive", 2.0)),
                          spacing_active=float(o.get("spacing_active", 0.1)),
                          internal_efficiency=float(o.get("internal_efficiency", 1.0)),
                          rt_model=o.get("rt_model", "exact"))
        prof = a.field
        res = a.summary()
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


def reflectance(design_json, options_json="{}"):
    try:
        s = _structure(design_json)
        o = json.loads(options_json or "{}")
        lam0 = s.design_wavelength
        span = float(o.get("span", 0.3 * lam0))
        lo = float(o.get("lambda_min", lam0 - span / 2))
        hi = float(o.get("lambda_max", lam0 + span / 2))
        parts = o.get("parts", ["full_top"])
        out = {}
        for p in parts:
            try:
                spec = laser.reflectance_spectrum(s, lo, hi, int(o.get("points", 2001)), p)
                st = laser.stopband(spec)
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
                    sg = fca.sigma(it.material, car, lam, it.fca_model, it.x) if (fam and car) else None
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
        m = max(int(o.get("pairs", 20)), 1)
        A = _layer_spec(o["first"], "first", o.get("first_waves", 0.25))
        B = _layer_spec(o["second"], "second", o.get("second_waves", 0.25))
        inc = _layer_spec(o.get("incident", {"material": "Air"}), "incident")
        ext = _layer_spec(o.get("exit", {"material": "AlGaAs", "x": 0}), "exit")

        def build(npairs):
            return Structure(name="DBR", design_wavelength=lam0, top=inc, substrate=ext,
                             stack=[Group(name=o.get("name", "DBR"), repeats=npairs, children=[A, B])])

        s = build(m)
        lo = float(o.get("lambda_min", lam0 * 0.8))
        hi = float(o.get("lambda_max", lam0 * 1.2))
        spec = laser.reflectance_spectrum(s, lo, hi, int(o.get("points", 2001)), "full_top")
        st = laser.stopband(spec)
        at = laser.reflectance_spectrum(s, lam0, lam0, 1, "full_top")
        nB = float(np.real(np.atleast_1d(B.index(lam0))[0]))
        nA = float(np.real(np.atleast_1d(A.index(lam0))[0]))
        n0 = float(np.real(np.atleast_1d(inc.index(lam0))[0]))
        ns = float(np.real(np.atleast_1d(ext.index(lam0))[0]))
        nH, nL = max(nA, nB), min(nA, nB)
        dA, dB = A.physical_thickness(lam0), B.physical_thickness(lam0)
        # analytic quarter-wave reflectance (lossless, real indices)
        Y = (nA / nB) ** (2 * m) * ns
        R_an = ((n0 - Y) / (n0 + Y)) ** 2
        dl_stop = 4 * lam0 / math.pi * math.asin((nH - nL) / (nH + nL)) if nH > nL else 0.0
        pen = coldren_leff(nL, nH, m, dA + dB) if nH > nL else {}
        # R at lambda0 versus number of pairs
        M = int(o.get("max_pairs", max(2 * m, 40)))
        Rm = []
        for k in range(1, M + 1):
            Rm.append(float(laser.reflectance_spectrum(build(k), lam0, lam0, 1, "full_top")["R"][0]))
        need = {}
        for t in o.get("targets", [0.99, 0.995, 0.999, 0.9995, 0.9999]):
            k = next((i + 1 for i, r in enumerate(Rm) if r >= t), None)
            need[str(t)] = k
        grp = Group(name=o.get("name", "DBR"), repeats=m, role=o.get("role", "none"), children=[A, B])
        return ok({
            "spectrum": {"wavelength": spec["wavelength"], "R": spec["R"], "T": spec["T"],
                         "phase_deg": spec["phase_deg"]},
            "stopband": st, "at_design": {"R": float(at["R"][0]), "T": float(at["T"][0]),
                                          "phase_deg": float(at["phase_deg"][0])},
            "n_first": nA, "n_second": nB, "n_incident": n0, "n_exit": ns,
            "d_first": dA, "d_second": dB, "period": dA + dB, "total_thickness": m * (dA + dB),
            "R_analytic": R_an, "stopband_analytic": dl_stop, "penetration": pen,
            "R_vs_pairs": Rm, "pairs_needed": need, "group": grp.to_dict(),
        })
    except Exception as e:
        return fail(e)
