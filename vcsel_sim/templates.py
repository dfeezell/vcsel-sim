"""Starting designs (also handy from Python: `from vcsel_sim.templates import gaas_980`)."""
from __future__ import annotations

import numpy as np

from .structure import Layer, Group, Structure
from . import materials


def L(name, material, x=0.0, t=0.25, unit="waves", typ="undoped", alpha=0.0, doping=0.0, **kw):
    return Layer(name=name, material=material, x=x, thickness=t, thickness_unit=unit, layer_type=typ,
                 absorption=alpha, doping=doping, **kw)


def _tune(s):
    from .laser import tune_marked
    tune_marked(s)
    # round for readability
    def walk(items):
        for it in items:
            if isinstance(it, Group):
                walk(it.children)
            elif it.marked:
                it.thickness = round(it.thickness, 6)
    walk(s.stack)


def gaas_980(top_pairs=22, bottom_pairs=32, n_qw=3):
    """Generic 980 nm top-emitting VCSEL with dispersive (model) indices."""
    lam = 980.0
    p = dict(typ="p-type", alpha=11.5, doping=1e18)
    n = dict(typ="n-type", alpha=5.0, doping=1e18)
    qw_t, b_t = 6.0, 8.0
    n_qw_ = float(np.real(materials.index("InGaAs", lam, 0.2)))
    n_b = float(np.real(materials.index("AlGaAs", lam, 0.0)))
    act_opt = (n_qw * qw_t * n_qw_ + (n_qw + 1) * b_t * n_b) / lam
    sp = (1.0 - act_opt) / 2
    stack = [
        Group("P-DBR", top_pairs, [L("GaAs", "AlGaAs", 0.0, **p), L("Al0.90GaAs", "AlGaAs", 0.9, **p)], role="top_dbr"),
        L("Al0.30GaAs spacer", "AlGaAs", 0.3, sp, marked=True, **p),
        Group("Active region", n_qw, [L("GaAs barrier", "AlGaAs", 0.0, b_t, "nm"),
                                      L("In0.2GaAs QW", "InGaAs", 0.2, qw_t, "nm", typ="active")], role="active"),
        L("GaAs barrier", "AlGaAs", 0.0, b_t, "nm"),
        L("Al0.30GaAs spacer", "AlGaAs", 0.3, sp, marked=True, **n),
        Group("N-DBR", bottom_pairs, [L("Al0.90GaAs", "AlGaAs", 0.9, **n), L("GaAs", "AlGaAs", 0.0, **n)], role="bottom_dbr"),
    ]
    s = Structure(name="980 nm InGaAs/GaAs VCSEL", design_wavelength=lam,
                     top=Layer(name="Air", material="Air", thickness=0, thickness_unit="nm", layer_type="other"),
                     substrate=Layer(name="n-GaAs substrate", material="AlGaAs", x=0.0, thickness=0,
                                     thickness_unit="nm", layer_type="n-type", doping=2e18),
                     stack=stack, notes="1-lambda Al0.3GaAs cavity, 3 x 6 nm In0.2GaAs QWs, Al0.9GaAs/GaAs DBRs. "
                                        "Spacers are marked and were tuned so the cavity resonates at 980 nm.")
    _tune(s)
    return s


def algaas_850(top_pairs=22, bottom_pairs=34, n_qw=3):
    lam = 850.0
    p = dict(typ="p-type", alpha=11.5, doping=1e18)
    n = dict(typ="n-type", alpha=5.0, doping=1e18)
    qw_t, b_t = 7.0, 8.0
    n_qw_ = float(np.real(materials.index("AlGaAs", lam, 0.0)))
    n_b = float(np.real(materials.index("AlGaAs", lam, 0.3)))
    act_opt = (n_qw * qw_t * n_qw_ + (n_qw + 1) * b_t * n_b) / lam
    sp = (1.0 - act_opt) / 2
    qw = Layer(name="GaAs QW", material="AlGaAs", x=0.0, thickness=qw_t, thickness_unit="nm", layer_type="active",
               index_mode="fixed", n_real=round(n_qw_, 5))
    stack = [
        Group("P-DBR", top_pairs, [L("Al0.12GaAs", "AlGaAs", 0.12, **p), L("Al0.90GaAs", "AlGaAs", 0.9, **p)], role="top_dbr"),
        L("Al0.60GaAs spacer", "AlGaAs", 0.6, sp, marked=True, **p),
        Group("Active region", n_qw, [L("Al0.3GaAs barrier", "AlGaAs", 0.3, b_t, "nm"), qw], role="active"),
        L("Al0.3GaAs barrier", "AlGaAs", 0.3, b_t, "nm"),
        L("Al0.60GaAs spacer", "AlGaAs", 0.6, sp, marked=True, **n),
        Group("N-DBR", bottom_pairs, [L("Al0.90GaAs", "AlGaAs", 0.9, **n), L("Al0.12GaAs", "AlGaAs", 0.12, **n)], role="bottom_dbr"),
    ]
    s = Structure(name="850 nm GaAs/AlGaAs VCSEL", design_wavelength=lam,
                     top=Layer(name="Air", material="Air", thickness=0, thickness_unit="nm", layer_type="other"),
                     substrate=Layer(name="n-GaAs substrate", material="Generic", index_mode="fixed", n_real=3.65,
                                     thickness=0, thickness_unit="nm", layer_type="n-type"),
                     stack=stack,
                     notes="GaAs QWs use a fixed (below-gap) index; the GaAs substrate is absorbing at 850 nm "
                           "and is given a real index here so that only the outgoing wave matters. "
                           "Spacers are marked and were tuned so the cavity resonates at 850 nm.")
    _tune(s)
    return s


def dielectric_dbr(pairs=8):
    lam = 980.0
    stack = [Group("Ta2O5/SiO2 DBR", pairs, [L("Ta2O5", "Ta2O5", typ="dielectric"), L("SiO2", "SiO2", typ="dielectric")],
                   role="top_dbr"),
             L("GaAs (cavity side)", "AlGaAs", 0.0, 1.0)]
    return Structure(name="Ta2O5/SiO2 dielectric DBR", design_wavelength=lam,
                     top=Layer(name="Air", material="Air", thickness=0, thickness_unit="nm", layer_type="other"),
                     substrate=Layer(name="GaAs", material="AlGaAs", thickness=0, thickness_unit="nm"),
                     stack=stack, notes="Mirror-only example: use the Reflectance tab.")
