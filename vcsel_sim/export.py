"""Tables and CSV export (structure, index profile, field, results, spectra, inputs)."""
from __future__ import annotations

import io
import json

import numpy as np

from . import materials
from .structure import Structure


def layer_rows(s: Structure, wavelength=None):
    lam = float(wavelength or s.design_wavelength)
    rows = []
    z = 0.0
    for i, f in enumerate(s.flatten()):
        L = f.layer
        n = complex(L.index(lam)[()] if np.ndim(L.index(lam)) == 0 else L.index(lam))
        d = f.thickness_nm
        rows.append({
            "index": i + 1, "path": f.path, "name": L.name, "material": L.material, "x": L.x, "y": L.y,
            "type": L.layer_type, "doping_cm3": L.doping, "thickness_nm": d, "z_top_nm": z, "z_bottom_nm": z + d,
            "n": n.real, "k": n.imag, "absorption_cm": L.absorption,
            "optical_thickness_waves": n.real * d / lam, "group_role": f.group_role,
            "bandgap_eV": materials.bandgap(L.material, L.x, L.y) if L.index_mode == "model" else None,
        })
        z += d
    return rows


def index_profile(s: Structure, wavelength=None, outside=300.0):
    """Step profile (z, n) suitable for plotting, plus layer boundaries & labels."""
    lam = float(wavelength or s.design_wavelength)
    rows = layer_rows(s, lam)
    ztop = complex(np.atleast_1d(s.top.index(lam))[0])
    zsub = complex(np.atleast_1d(s.substrate.index(lam))[0])
    zs, ns = [-outside, 0.0], [ztop.real, ztop.real]
    for r in rows:
        zs += [r["z_top_nm"], r["z_bottom_nm"]]
        ns += [r["n"], r["n"]]
    tot = rows[-1]["z_bottom_nm"] if rows else 0.0
    zs += [tot, tot + outside]
    ns += [zsub.real, zsub.real]
    return {"z": zs, "n": ns, "total_thickness": tot, "wavelength": lam,
            "layers": [{"z0": r["z_top_nm"], "z1": r["z_bottom_nm"], "name": r["name"], "type": r["type"],
                        "role": r["group_role"], "n": r["n"], "material": r["material"]} for r in rows]}


def _csv(header, rows, comments=()):
    buf = io.StringIO()
    for c in comments:
        buf.write(f"# {c}\n")
    buf.write(",".join(header) + "\n")
    for r in rows:
        buf.write(",".join("" if v is None else (f"{v:.10g}" if isinstance(v, float) else str(v).replace(",", ";"))
                           for v in r) + "\n")
    return buf.getvalue()


def csv(s: Structure, kind, payload=None):
    payload = payload or {}
    if kind == "structure":
        rows = layer_rows(s, payload.get("wavelength"))
        keys = list(rows[0].keys()) if rows else []
        return _csv(keys, [[r[k] for k in keys] for r in rows],
                    [f"{s.name}", f"design wavelength {s.design_wavelength} nm",
                     f"top medium: {s.top.name}; substrate: {s.substrate.name}"])
    if kind == "index_profile":
        p = index_profile(s, payload.get("wavelength"))
        return _csv(["z_nm", "n"], zip(p["z"], p["n"]), [f"{s.name}", f"lambda = {p['wavelength']} nm",
                                                           "z measured from the top surface, positive into the wafer"])
    if kind == "field":
        f = payload["field"]
        return _csv(["z_nm", "E2_normalised", "n"], zip(f["z"], f["E2"], f["n"]),
                    [f"{s.name}", f"lasing wavelength {payload.get('wavelength')} nm",
                     f"|E|^2 normalised to {payload.get('normalization', 'bottom')}",
                     "z measured from the top surface, positive into the wafer"])
    if kind == "reflectance":
        sp = payload["spectrum"]
        return _csv(["wavelength_nm", "R", "T", "A", "phase_deg"],
                    zip(sp["wavelength"], sp["R"], sp["T"], sp["A"], sp["phase_deg"]),
                    [f"{s.name}", f"reflectance: {payload.get('part', '')}", "passive (no gain)"])
    if kind == "results":
        res = payload["results"]
        flat = []
        def nested(prefix, d):
            for kk, vv in d.items():
                if isinstance(vv, dict):
                    nested(f"{prefix}{kk}: ", vv)
                elif not isinstance(vv, (list, tuple)):
                    flat.append([f"{prefix}{kk}", vv])
        for k, v in res.items():
            if isinstance(v, dict):
                nested(f"{k}: ", v)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                for item in v:
                    flat.append([f"loss: {item.get('region')}", item.get("rt_loss")])
            elif k.startswith("matrix"):
                for name, c in zip(["m11", "m12", "m21", "m22"], v):
                    flat.append([f"{k} {name}", f"{c[0]:.10g}{c[1]:+.10g}i"])
            else:
                flat.append([k, v])
        return _csv(["quantity", "value"], flat, [f"{s.name}"])
    if kind == "inputs":
        return json.dumps(s.to_dict(), indent=2)
    raise ValueError(f"unknown export kind {kind}")
