"""Cavity length, DBR penetration depths and the confinement factor, computed the way
the ECE 577 course notes ("Vertical Gain and Loss Definitions") and Coldren & Corzine
Appendix 7 do it.

    L      = L_cav + L_eff,top + L_eff,bottom
    Gamma  = Gamma_enh * L_a / L
    g_mod  = Gamma * g_th
    alpha_i, alpha_m from the round-trip fractions and L
    R_up   = exp(-trans. up),  R_down = exp(-trans. down)
    chi    = L * n_eff / lambda0          (cavity optical thickness in waves)

DBR penetration depth (Coldren & Corzine eqs. A7.13 and A7.25, closed form for a quarter-wave stack):

    r      = (n2 - n1) / (n2 + n1)
    m_eff  = tanh[m ln(n2/n1)] / tanh[ln(n2/n1)]
    L_eff  = (m_eff * Lambda / 2) * [1/(1 + r^2) - 1/(2 m_eff)]

The DBR's effective length starts at its first low-index layer counted from the cavity. A
high-index DBR layer that touches the cavity is counted as part of the cavity.

The depth is also computed from the actual reflection phase of the mirror,
L_phase = (1/2) |d(phi)/d(beta)|, with beta = 2 pi n_inc / lambda. This needs no
quarter-wave assumption and serves as a check on the closed-form value.
"""
from __future__ import annotations

import numpy as np

from . import tmm
from .structure import Group


def _role_group(items, role):
    for it in items:
        if isinstance(it, Group):
            if it.role == role:
                return it
            g = _role_group(it.children, role)
            if g is not None:
                return g
    return None


def _flatten_once(group, lam):
    out = []

    def walk(items):
        for it in items:
            if isinstance(it, Group):
                for _ in range(max(int(it.repeats), 0)):
                    walk(it.children)
            else:
                out.append(it)
    walk(group.children)
    return out


def coldren_leff(n1, n2, m, period):
    """Coldren A7.25 / A7.13 (exact quarter-wave expressions) plus the Ch. 3 approximations."""
    n1, n2 = min(n1, n2), max(n1, n2)
    r = (n2 - n1) / (n2 + n1)
    t1 = np.tanh(np.log(n2 / n1))
    m_eff = np.tanh(m * np.log(n2 / n1)) / t1
    L_exact = 0.5 * m_eff * period * (1 / (1 + r ** 2) - 1 / (2 * m_eff))
    kappa = 2 * r / period
    return {
        "r": float(r), "m_eff": float(m_eff), "L_eff": float(L_exact),
        "kappa_cm": float(kappa * 1e7),
        "L_eff_tanh": float(np.tanh(2 * m * r) / (2 * kappa)),     # (1/2kappa) tanh(2mr)
        "L_eff_long": float(period / (4 * r)),                       # Lambda / 4r
        "m_eff_approx": float(np.tanh(2 * m * r) / (2 * r)),
    }


def _phase_depth(model, lam, part, n_inc, h=0.02):
    """(1/2)|d phi / d beta| of the mirror seen from the cavity, in nm."""
    from .laser import _sub_structure_arrays
    lams = np.array([lam - h, lam + h])
    n_list, d_list, _, _ = _sub_structure_arrays(model, lams, part)
    r, _, _, _ = tmm.reflection_from_top(n_list, d_list, lams)
    dphi = np.angle(r[1] / r[0])
    dbeta = 2 * np.pi * n_inc * (1 / lams[1] - 1 / lams[0])
    return float(abs(0.5 * dphi / dbeta))


def mirror(model, lam, role):
    """Penetration-depth report for the DBR group with the given role, or None."""
    s = model.s
    grp = _role_group(s.stack, role)
    idx = np.where(model.role_mask(role))[0]
    if grp is None or len(idx) == 0:
        return None
    ns = model.indices(lam, 0.0)
    nr = np.array([float(np.real(np.atleast_1d(ns[j + 1])[0])) for j in range(len(model.d))])
    period_layers = _flatten_once(grp, lam)
    period = float(sum(L.physical_thickness(s.design_wavelength) for L in period_layers))
    pn = [float(np.real(np.atleast_1d(L.index(lam))[0])) for L in period_layers]
    n1, n2 = min(pn), max(pn)
    m = int(grp.repeats)
    out = {"name": grp.name, "role": role, "periods": m, "period_nm": period, "n_low": n1, "n_high": n2,
           "delta_n": n2 - n1, "length_nm": float(model.d[idx].sum()), "layers_per_period": len(period_layers)}
    if n2 <= n1 or m < 1:
        out["error"] = "The mirror has no index contrast."
        return out
    out.update(coldren_leff(n1, n2, m, period))
    out["L_eff_lambda"] = float(lam / (4 * (n2 - n1)))               # lambda0 / (4 delta n)
    # cavity-side layer of the mirror; a high-index layer there belongs to the cavity
    j_adj = idx.max() if role == "top_dbr" else idx.min()
    adj_high = nr[j_adj] > 0.5 * (n1 + n2)
    out["cavity_side_layer"] = model.flat[j_adj].layer.name
    out["cavity_side_high"] = bool(adj_high)
    out["moved_to_cavity_nm"] = float(model.d[j_adj]) if adj_high else 0.0
    # phase penetration depth, referenced to the first low-index layer
    j_inc = j_adj + 1 if role == "top_dbr" else j_adj - 1
    if 0 <= j_inc < len(model.d):
        n_inc = nr[j_inc]
        try:
            Lp = _phase_depth(model, lam, role, n_inc)
            if adj_high:
                Lp -= nr[j_adj] * model.d[j_adj] / n_inc
            out["L_eff_phase"] = Lp
            out["n_incident"] = n_inc
        except Exception:                                            # pragma: no cover
            pass
    return out


def cavity_report(model, analysis):
    """Course-notes cavity model from a finished threshold analysis (laser.Analysis)."""
    lam = analysis.wavelength
    top = mirror(model, lam, "top_dbr")
    bot = mirror(model, lam, "bottom_dbr")
    it = np.where(model.role_mask("top_dbr"))[0]
    ib = np.where(model.role_mask("bottom_dbr"))[0]
    lo = it.max() + 1 if len(it) else 0
    hi = ib.min() if len(ib) else len(model.d)
    Lcav = float(model.d[lo:hi].sum())
    for mrep in (top, bot):
        if mrep and "error" not in mrep:
            Lcav += mrep["moved_to_cavity_nm"]
    rep = {"top": top, "bottom": bot, "L_cav": Lcav, "L_a": analysis.active_thickness}
    ok_t = top is not None and "error" not in top
    ok_b = bot is not None and "error" not in bot
    rep["complete"] = ok_t and ok_b
    if not rep["complete"]:
        rep["note"] = ("Needs one group with role Top DBR and one with role Bottom DBR, "
                       "each with index contrast, to compute L.")
        return rep

    a = analysis
    exact_rt = (a.rt_loss, a.rt_transmission, a.rt_transmission_top, a.rt_transmission_bottom)

    from .laser import rt_to_per_length, rt_to_reflectance

    def losses(rt_l, t_up, t_dn, Lcm, mode):
        Rup, Rdn = rt_to_reflectance(t_up, mode), rt_to_reflectance(t_dn, mode)
        ai = rt_to_per_length(rt_l, Lcm, mode)
        RR = Rup * Rdn
        am = float(np.log(1 / RR) / (2 * Lcm)) if RR > 0 else float("nan")   # (1/L) ln(1/sqrt(R_up R_down))
        return ai, am, Rup, Rdn

    def block(Lt, Lb, enh, rts=exact_rt, mode=None):
        mode = mode or a.rt_model
        other = "exact" if mode == "linear" else "linear"
        L = Lcav + Lt + Lb
        Lcm = L * 1e-7
        gam = enh * a.active_thickness / L
        rt_l, rt_t, t_up, t_dn = rts
        ai, am, Rup, Rdn = losses(rt_l, t_up, t_dn, Lcm, mode)
        ai2, am2, Rup2, Rdn2 = losses(rt_l, t_up, t_dn, Lcm, other)
        return {
            "rt_model": mode, "L": L, "L_eff_top": Lt, "L_eff_bottom": Lb, "confinement": gam,
            # linear: Gamma*g_th (identical to alpha_i + alpha_m); exact: alpha_i + alpha_m
            "modal_gain": gam * a.threshold_gain if mode == "linear" else ai + am,
            "modal_gain_gamma_g": gam * a.threshold_gain,
            "alpha_i": ai, "alpha_m": am, "R_up": Rup, "R_down": Rdn,
            "alt": {"rt_model": other, "alpha_i": ai2, "alpha_m": am2, "R_up": Rup2, "R_down": Rdn2},
            "chi": L * a.avg_index_rms / lam,
        }

    rep["coldren"] = block(top["L_eff"], bot["L_eff"], analysis.enhancement)
    if "L_eff_phase" in top and "L_eff_phase" in bot:
        rep["phase"] = block(top["L_eff_phase"], bot["L_eff_phase"], analysis.enhancement)
    V = a.vertical
    if V.get("gain enhancement"):
        rep["coldren_vertical_enh"] = block(top["L_eff"], bot["L_eff"], V["gain enhancement"],
                                            (V["round trip loss"], V["round trip transmission"],
                                             V["transmission up"], V["transmission down"]), mode="linear")
    # passive mirror reflectance at the lasing wavelength, for comparison with exp(-trans.)
    from .laser import reflectance_spectrum
    for key, part in (("R_top_passive", "top_dbr"), ("R_bottom_passive", "bottom_dbr")):
        try:
            rep[key] = float(reflectance_spectrum(model.s, lam, lam, 1, part)["R"][0])
        except Exception:                                            # pragma: no cover
            rep[key] = None
    return rep
