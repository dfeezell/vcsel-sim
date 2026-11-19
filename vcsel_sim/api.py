"""JSON-in / JSON-out entry points used by the browser GUI (via Pyodide).

Every function takes and returns plain JSON strings so the JavaScript side never
touches Python objects. The same functions are convenient from Jupyter.
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import materials, laser, vrt, export, templates
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
    return Structure.from_dict(d)


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
                          internal_efficiency=float(o.get("internal_efficiency", 1.0)))
        prof = a.field
        # decimate passive regions for plotting if huge
        fld = {"z": prof.z, "E2": prof.E2, "n": prof.n}
        return ok({"results": a.summary(), "field": fld,
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


def material_index(material, x, y, lam_min, lam_max, points=400):
    try:
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
                    nodes.append({"d": it.physical_thickness(lam), "n": n.real, "k": n.imag,
                                  "eg": materials.bandgap(it.material, it.x, it.y) if it.index_mode == "model" else None})
        walk(s.stack)
        flat = s.flatten()
        nt = complex(np.atleast_1d(s.top.index(lam))[0])
        nsub = complex(np.atleast_1d(s.substrate.index(lam))[0])
        return ok({"nodes": nodes, "n_layers": len(flat), "total_nm": float(sum(f.thickness_nm for f in flat)),
                   "top": {"n": nt.real, "k": nt.imag}, "substrate": {"n": nsub.real, "k": nsub.imag}})
    except Exception as e:
        return fail(e)
