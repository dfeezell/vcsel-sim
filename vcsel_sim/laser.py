"""VCSEL analysis: threshold gain, standing-wave field, gain/loss budget,
confinement & enhancement factors, efficiencies and mirror reflectance.

Physics summary (see docs/theory.md for the derivation)
-------------------------------------------------------
Threshold: the material gain g (cm^-1) of all active layers and the wavelength
are adjusted until the structure supports a field with only OUTGOING waves in
the exit medium and substrate (the transfer-matrix condition for an infinite
transmission). This is solved with a 2D Newton iteration on (lambda, g).

Energy budget at threshold (exact, no approximations): in each layer the
time-averaged power absorbed (or generated) per unit length is alpha*n*|E|^2
and the power flux is n(|A|^2-|B|^2). Normalising every term by the one-way
power flux in the active region, P_ref = n_a(|A|^2+|B|^2)/2, gives Vertical's
"round-trip" quantities:
    RT gain         = sum_active  g n_a  int|E|^2 dz / P_ref  (= 2 g L_a Gamma_enh)
    RT loss         = sum_passive alpha n int|E|^2 dz / P_ref
    RT transmission = (flux out top + flux out bottom) / P_ref
and RT gain = RT loss + RT transmission exactly at threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from . import tmm
from .structure import Structure, FlatLayer

HC_EV_NM = 1239.841984


# ---------------------------------------------------------------------------
class Model:
    """A Structure flattened to arrays for fast evaluation."""

    def __init__(self, structure: Structure):
        self.s = structure
        self.flat: List[FlatLayer] = structure.flatten()
        self.d = np.array([f.thickness_nm for f in self.flat], dtype=float)
        self.active = np.array([f.layer.is_active for f in self.flat], dtype=bool)
        self.z_top = np.concatenate([[0.0], np.cumsum(self.d)[:-1]]) if len(self.d) else np.zeros(0)
        self.total_thickness = float(self.d.sum())

    def indices(self, lam, gain=0.0):
        lam = np.atleast_1d(np.asarray(lam, dtype=float))
        ns = [self.s.top.index(lam)]
        cache = {}
        for f in self.flat:
            key = id(f.layer)
            if key not in cache:
                cache[key] = f.layer.index(lam, gain)
            ns.append(cache[key])
        ns.append(self.s.substrate.index(lam))
        return ns

    # -- region helpers ---------------------------------------------------
    def role_mask(self, role):
        return np.array([f.group_role == role for f in self.flat], dtype=bool)

    def cavity_mask(self):
        """Layers that are not in a top_dbr / bottom_dbr group."""
        return ~(self.role_mask("top_dbr") | self.role_mask("bottom_dbr"))


# ---------------------------------------------------------------------------
def _top_amplitudes(model: Model, lam, gain):
    ns = model.indices(lam, gain)
    one = np.ones(1, dtype=complex)
    tops = tmm.fields_up(ns, list(model.d), np.atleast_1d(lam), (one, ns[-1] * one))
    E0, H0 = tops[0]
    A0, B0 = tmm.amplitudes(E0, H0, ns[0])
    return complex(A0[0]), complex(B0[0])


def outgoing_mismatch(model: Model, lam, gain):
    """Ratio A0/B0 at the top surface when the substrate has only an outgoing wave.
    Zero at threshold (no incoming wave from the top)."""
    A0, B0 = _top_amplitudes(model, lam, gain)
    return A0 / B0


def find_resonance(model: Model, center=None, span=None, points=4001, gain=0.0):
    """Wavelength of the cavity resonance nearest the design wavelength: minimum of |A0/B0|."""
    lam0 = model.s.design_wavelength if center is None else center
    span = span or 0.08 * lam0
    lam = np.linspace(lam0 - span / 2, lam0 + span / 2, points)
    ns = model.indices(lam, gain)
    one = np.ones_like(lam, dtype=complex)
    E0, H0 = tmm.fields_up(ns, list(model.d), lam, (one, ns[-1] * one))[0]
    A0, B0 = tmm.amplitudes(E0, H0, ns[0])
    m = np.abs(A0 / B0)
    # local minima, choose the deepest closest to design
    idx = np.where((m[1:-1] < m[:-2]) & (m[1:-1] < m[2:]))[0] + 1
    if len(idx) == 0:
        return lam0
    score = m[idx] / m.max() + 0.2 * np.abs(lam[idx] - lam0) / span
    return float(lam[idx[np.argmin(score)]])


@dataclass
class ThresholdResult:
    wavelength: float
    gain: float
    converged: bool
    iterations: int
    residual: float


def _A0_complex(model: Model, lam_c, ns):
    one = np.ones(1, dtype=complex)
    lam1 = np.atleast_1d(np.asarray(lam_c, dtype=complex))
    E0, H0 = tmm.fields_up(ns, list(model.d), lam1, (one, ns[-1] * one))[0]
    A0, B0 = tmm.amplitudes(E0, H0, ns[0])
    return complex(A0[0]), complex(B0[0])


def cold_cavity_mode(model: Model, lam_guess, gain=0.0, maxit=60):
    """Quasi-normal mode: complex wavelength at which the structure (indices frozen at
    Re(lambda)) has only outgoing waves, i.e. the zero of A0(lambda). Newton in the complex plane."""
    lam = complex(lam_guess)
    ns = model.indices(lam.real, gain)
    for _ in range(maxit):
        f, _ = _A0_complex(model, lam, ns)
        h = 1e-7 * abs(lam)
        df = (_A0_complex(model, lam + h, ns)[0] - f) / h
        if df == 0:
            break
        step = -f / df
        if abs(step) > 1.0:
            step *= 1.0 / abs(step)
        lam += step
        if abs(step) < 1e-13 * abs(lam):
            break
    return lam


def solve_threshold(model: Model, lam_guess=None, g_guess=None, tol=1e-12, maxit=60) -> ThresholdResult:
    if not model.active.any():
        raise ValueError("The structure has no active layers (set Layer type = active on the quantum wells).")
    lam0 = model.s.design_wavelength if lam_guess is None else float(lam_guess)
    # 1) cold-cavity quasi-normal mode nearest the design wavelength (complex Newton on A0)
    lamc = cold_cavity_mode(model, lam0)
    if not (abs(lamc.real - lam0) < 0.05 * lam0 and lamc.imag > 0):
        # fallback: start from the deepest passive resonance dip near the design wavelength
        lam = find_resonance(model, center=lam0, span=0.06 * lam0, points=6001)
        lamc = cold_cavity_mode(model, lam)
    lam = lamc.real
    if g_guess is None:
        nn, A, B = solve_field(model, lam, 0.0)
        I = np.array([float(tmm.layer_intensity_integral(A[j], B[j], nn[j], model.d[j - 1], lam))
                      for j in range(1, len(model.d) + 1)])
        W = nn[1:-1].real ** 2 * I
        gamma = float(np.sum(W[model.active]) / np.sum(W))
        ng = float(np.sum(nn[1:-1].real * W) / np.sum(W))
        alpha_tot = 4 * np.pi * ng * abs(lamc.imag) / lam ** 2 * 1e7   # cm^-1
        g_guess = alpha_tot / max(gamma, 1e-6)
    g = float(g_guess)
    # Newton on the incoming amplitude A0 itself (scaled by a fixed reference). A0 is an entire,
    # nearly linear function of (lambda, g) near threshold, whereas the ratio A0/B0 has a nearby pole
    # that shrinks Newton's basin to almost nothing in very high-Q cavities (dielectric DBRs).
    A_ref, B_ref = _top_amplitudes(model, lam, g)
    scale_ref = 1.0 / abs(B_ref) if abs(B_ref) > 0 else 1.0
    resid = lambda L_, G_: _top_amplitudes(model, L_, G_)[0] * scale_ref
    f = resid(lam, g)
    it = 0
    for it in range(1, maxit + 1):
        dl = 1e-7 * lam
        dg = 1e-5 * max(abs(g), 10.0)
        fl = (resid(lam + dl, g) - f) / dl
        fg = (resid(lam, g + dg) - f) / dg
        J = np.array([[fl.real, fg.real], [fl.imag, fg.imag]])
        try:
            step = np.linalg.solve(J, -np.array([f.real, f.imag]))
        except np.linalg.LinAlgError:
            break
        # damping: limit wavelength step to 2 nm and gain step to 50 %
        scale = 1.0
        if abs(step[0]) > 2.0:
            scale = min(scale, 2.0 / abs(step[0]))
        if abs(step[1]) > 0.5 * max(abs(g), 200.0):
            scale = min(scale, 0.5 * max(abs(g), 200.0) / abs(step[1]))
        lam_n, g_n = lam + scale * step[0], g + scale * step[1]
        f_n = resid(lam_n, g_n)
        # backtrack if the residual grew
        bt = 0
        while not abs(f_n) <= abs(f) and bt < 8:
            scale *= 0.5
            lam_n, g_n = lam + scale * step[0], g + scale * step[1]
            f_n = resid(lam_n, g_n)
            bt += 1
        lam, g, f = lam_n, g_n, f_n
        if abs(f) < tol or (abs(scale * step[0]) < 1e-12 and abs(scale * step[1]) < 1e-10):
            break
    r = abs(outgoing_mismatch(model, lam, g))
    return ThresholdResult(lam, g, bool(r < 1e-8), it, r)


# ---------------------------------------------------------------------------
@dataclass
class FieldProfile:
    z: np.ndarray            # nm from the top surface (0) downward; includes a stretch of each exit medium
    E2: np.ndarray           # |E|^2, normalised (see Analysis.normalization)
    n: np.ndarray            # real index at each point
    layer_index: np.ndarray  # flat-layer index of each point (-1 = top medium, L = substrate)

    @property
    def intensity(self):
        """n|E|^2: proportional to the local standing-wave power density."""
        return self.n * self.E2


def solve_field(model: Model, lam, gain):
    """Outgoing-wave solution. Returns (nn, A, B): complex index of every medium
    (top, layers..., substrate) and the down/up-going amplitudes at the TOP of each
    medium, normalised so that the substrate amplitude is 1 (|E|^2 = 1 at the bottom)."""
    ns = model.indices(lam, gain)
    lam1 = np.atleast_1d(lam)
    one = np.ones(1, dtype=complex)
    tops = tmm.fields_up(ns, list(model.d), lam1, (one, ns[-1] * one))
    L = len(model.d)
    A = np.zeros(L + 2, dtype=complex)
    B = np.zeros(L + 2, dtype=complex)
    for j in range(L + 2):
        E, H = tops[j]
        a, b = tmm.amplitudes(E, H, ns[j])
        A[j], B[j] = a[0], b[0]
    nn = np.array([n[0] for n in ns])
    return nn, A, B


def _layer_samples(model, lam, nn, A, B, j, spacing):
    d = model.d[j - 1]
    npts = max(int(np.ceil(d / spacing - 1e-9)) + 1, 2)
    u = np.linspace(0.0, d, npts)
    k = 2 * np.pi * nn[j] / lam
    E = A[j] * np.exp(1j * k * u) + B[j] * np.exp(-1j * k * u)
    return u, np.abs(E) ** 2


def sample_field(model: Model, lam, nn, A, B, spacing_passive=2.0, spacing_active=0.1, outside=300.0):
    zs, E2s, ns_, idx = [], [], [], []
    L = len(model.d)
    k = 2 * np.pi * nn / lam
    zt = np.linspace(-outside, 0.0, max(int(outside / spacing_passive), 2), endpoint=False)
    E = A[0] * np.exp(1j * k[0] * zt) + B[0] * np.exp(-1j * k[0] * zt)
    zs.append(zt); E2s.append(np.abs(E) ** 2); ns_.append(np.full(zt.shape, nn[0].real)); idx.append(np.full(zt.shape, -1))
    for j in range(1, L + 1):
        sp = spacing_active if model.active[j - 1] else spacing_passive
        u, e2 = _layer_samples(model, lam, nn, A, B, j, sp)
        zs.append(model.z_top[j - 1] + u); E2s.append(e2)
        ns_.append(np.full(u.shape, nn[j].real)); idx.append(np.full(u.shape, j - 1))
    u = np.linspace(0.0, outside, max(int(outside / spacing_passive), 2))
    E = A[-1] * np.exp(1j * k[-1] * u)
    zs.append(model.total_thickness + u); E2s.append(np.abs(E) ** 2)
    ns_.append(np.full(u.shape, nn[-1].real)); idx.append(np.full(u.shape, L))
    return FieldProfile(np.concatenate(zs), np.concatenate(E2s), np.concatenate(ns_), np.concatenate(idx))


# ---------------------------------------------------------------------------
@dataclass
class Analysis:
    # --- operating point
    wavelength: float                     # lasing wavelength, nm
    threshold_gain: float                 # threshold MATERIAL gain of the active layers, cm^-1
    converged: bool
    photon_energy: float                  # eV
    # --- round-trip budget (exact energy balance, normalised to one-way flux in the active layers)
    rt_gain: float
    rt_loss: float
    rt_transmission: float
    rt_transmission_top: float
    rt_transmission_bottom: float
    # --- confinement
    enhancement: float                    # gain enhancement factor Gamma_enh (exact, local standing wave)
    active_thickness: float               # nm
    confinement: float                    # longitudinal confinement factor Gamma (energy based)
    effective_length: float               # nm, L = Gamma_enh * L_a / Gamma
    modal_gain: float                     # Gamma * g_th, cm^-1
    # --- losses per unit length (cm^-1) using L
    alpha_i: float
    alpha_m: float
    alpha_m_top: float
    alpha_m_bottom: float
    R_top: float                          # effective mirror reflectances exp(-RT transmission)
    R_bottom: float
    # --- efficiencies
    internal_efficiency: float
    ext_eff: float
    ext_eff_top: float
    ext_eff_bottom: float
    slope_top: float                      # W/A
    slope_bottom: float
    lifetime_ps: float                    # cavity photon lifetime
    # --- field
    normalization: str
    peak_E2: float
    E2_active_max: float
    E2_active_mean: float
    E2_top: float
    E2_bottom: float
    avg_index_rms: float                  # sqrt(int n^2|E|^2 / int |E|^2) over the stack (Vertical "avg core index")
    avg_cavity_index: float               # thickness-weighted index of the cavity (between the DBR groups)
    loss_breakdown: list = field(default_factory=list)
    matrix: tuple = ()                    # characteristic matrix bottom->top, this program's convention
    matrix_vertical: tuple = ()           # same matrix in Vertical's sign convention (exp(+i w t))
    vertical: dict = field(default_factory=dict)   # quantities computed with Vertical's numerical conventions
    rt_model: str = "linear"              # how round-trip fractions were converted (see rt_to_per_length)
    field: Optional[FieldProfile] = None

    def summary(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("field",)}
        d["matrix"] = [[c.real, c.imag] for c in self.matrix]
        d["matrix_vertical"] = [[c.real, c.imag] for c in self.matrix_vertical]
        return d


def rt_to_per_length(rt, L_cm, rt_model="linear"):
    """Convert a round-trip power fraction to a loss per unit length (cm^-1).

    linear : rt / 2L                  (small-argument form, what Vertical uses)
    exact  : -ln(1 - rt) / 2L         (from rt = 1 - exp(-2 alpha L))
    """
    if rt_model == "exact":
        return float(-np.log(max(1.0 - rt, 1e-300)) / (2 * L_cm))
    return float(rt / (2 * L_cm))


def rt_to_reflectance(t, rt_model="linear"):
    """Effective mirror reflectance from the round-trip transmission through that mirror:
    linear R = exp(-t) (Vertical / course notes), exact R = 1 - t."""
    if rt_model == "exact":
        # t >= 1 means the cavity loses more than its stored energy per round trip; R = 1 - t is then undefined
        return float(1.0 - t) if t < 1.0 else float("nan")
    return float(np.exp(-t))


def analyze(structure: Structure, lam_guess=None, g_guess=None, normalize="bottom",
            spacing_passive=2.0, spacing_active=0.1, internal_efficiency=1.0,
            rt_model="linear", vertical_spacing=0.1) -> Analysis:
    """Threshold + full analysis of a VCSEL structure (Vertical's 'Analysis' command).

    rt_model: "linear" converts round-trip fractions to per-length losses and mirror
    reflectances with the small-argument forms Vertical uses; "exact" uses the
    exponential forms. spacing_* only set the plotted field samples: every integral
    is analytic. vertical_spacing is the |E|^2 sampling used for the Vertical column."""
    model = Model(structure)
    th = solve_threshold(model, lam_guess, g_guess)
    lam, g = th.wavelength, th.gain
    nn, A, B = solve_field(model, lam, g)
    L = len(model.d)
    inner = slice(1, L + 1)
    nl = nn[inner]
    act = model.active
    pas = ~act
    # exact integral of |E|^2 over every layer
    I = np.array([float(tmm.layer_intensity_integral(A[j], B[j], nn[j], model.d[j - 1], lam))
                  for j in range(1, L + 1)])
    La = float(model.d[act].sum())

    # one-way power flux in the active layers (thickness-weighted mean)
    # local standing-wave mean of |E|^2, i.e. |A(u)|^2+|B(u)|^2 averaged across each layer (the amplitudes
    # grow or decay inside gain / loss layers, so the value at the layer top is not quite the mean)
    kk = 2 * np.pi * nl / lam
    dd = np.where(model.d > 0, model.d, 1.0)
    sw = (np.abs(A[inner]) ** 2 * np.real(tmm._expint(-2 * kk.imag, dd)) +
          np.abs(B[inner]) ** 2 * np.real(tmm._expint(2 * kk.imag, dd))) / dd
    Pref = float(np.sum((nl.real * sw / 2)[act] * model.d[act]) / La)
    enh = float(np.sum(I[act]) / np.sum(sw[act] * model.d[act]))

    alpha_nm = 4 * np.pi * nl.imag / lam                          # power absorption coeff (nm^-1); <0 = gain
    power = alpha_nm * nl.real * I                                 # absorbed power per area (arb.)
    rt_gain = float(-np.sum(power[act]) / Pref)
    rt_loss = float(np.sum(power[pas]) / Pref)
    flux_top = float(nn[0].real * abs(B[0]) ** 2)
    flux_bot = float(nn[-1].real * abs(A[-1]) ** 2)
    rt_t_top, rt_t_bot = flux_top / Pref, flux_bot / Pref
    rt_t = rt_t_top + rt_t_bot

    W = nl.real ** 2 * I                                           # energy density ~ eps |E|^2
    gamma = float(np.sum(W[act]) / np.sum(W))
    Leff = enh * La / gamma
    Lcm = Leff * 1e-7
    Eph = HC_EV_NM / lam
    eta_t = internal_efficiency * rt_t_top / rt_gain
    eta_b = internal_efficiency * rt_t_bot / rt_gain
    a_i = rt_to_per_length(rt_loss, Lcm, rt_model)
    R_t, R_b = rt_to_reflectance(rt_t_top, rt_model), rt_to_reflectance(rt_t_bot, rt_model)
    a_mt, a_mb = float(np.log(1 / R_t) / (2 * Lcm)), float(np.log(1 / R_b) / (2 * Lcm))
    tot = a_i + a_mt + a_mb
    # photon lifetime = stored energy / power leaving the mode (absorption + transmission), with the
    # dispersive energy density (eps0/2) n n_g |E|^2.  Gain is not a loss: active layers count only their
    # background absorption.  Agrees with the cold-cavity quasi-normal-mode decay rate when n_g = n.
    dl = 1e-3 * lam
    n_p = np.array([np.real(x[0]) for x in model.indices(lam + dl, g)])[inner]
    n_m = np.array([np.real(x[0]) for x in model.indices(lam - dl, g)])[inner]
    n_g = nl.real - lam * (n_p - n_m) / (2 * dl)
    bg = np.array([4 * np.pi * (f.layer.index(lam, 0.0).imag) / lam if act[j] else alpha_nm[j]
                   for j, f in enumerate(model.flat)], dtype=float)
    p_out = float(np.sum(bg * nl.real * I) + flux_top + flux_bot)
    stored = float(np.sum(nl.real * n_g * I))
    tau = stored / (2.99792458e5 * p_out) if p_out > 0 else float("inf")      # c in nm/ps

    # field profile (|E|^2, Vertical style) and normalisation
    prof = sample_field(model, lam, nn, A, B, spacing_passive, spacing_active)
    in_stack = (prof.layer_index >= 0) & (prof.layer_index < L)
    E2_top_raw, E2_bot_raw = float(abs(B[0]) ** 2), float(abs(A[-1]) ** 2)
    norm = {"bottom": E2_bot_raw, "top": E2_top_raw, "peak": float(prof.E2[in_stack].max())}[normalize]
    prof.E2 = prof.E2 / norm
    act_layers = np.where(act)[0]
    act_pts = np.isin(prof.layer_index, act_layers)
    peak = float(prof.E2[in_stack].max())
    # refine the peak inside the layer holding the largest sample (independent of plot spacing)
    j_pk = int(prof.layer_index[in_stack][np.argmax(prof.E2[in_stack])])
    if 0 <= j_pk < L:
        _, e2f = _layer_samples(model, lam, nn, A, B, j_pk + 1, max(min(model.d[j_pk] / 20000, 0.005), 1e-4))
        peak = max(peak, float(e2f.max() / norm))

    # Vertical-convention quantities (numerical rules reproduced for cross-checking)
    s_sum = 0.0
    for j in act_layers:
        u, e2 = _layer_samples(model, lam, nn, A, B, j + 1, vertical_spacing)
        s_sum += e2.sum() * (u[1] - u[0])
    # Vertical takes the peak from its own samples (2 nm passive / 0.1 nm active)
    pv = sample_field(model, lam, nn, A, B, 2.0, vertical_spacing)
    in_v = (pv.layer_index >= 0) & (pv.layer_index < L)
    peak_v = float(pv.E2[in_v].max() / norm)
    enh_v = float(s_sum / norm / La / (peak_v / 2))
    rt_gain_v = 2 * g * 1e-7 * La * enh_v
    rt_t_v = rt_gain_v * rt_t / rt_gain
    split_top = E2_top_raw / (E2_top_raw + E2_bot_raw)
    vertical = {
        "Gth (cm^-1)": g, "lasing wavelength (nm)": lam,
        "round trip gain": rt_gain_v, "round trip loss": rt_gain_v - rt_t_v,
        "round trip transmission": rt_t_v, "transmission up": rt_t_v * split_top,
        "transmission down": rt_t_v * (1 - split_top), "gain enhancement": enh_v,
        "peak E2": peak_v, "E2 at active": float(prof.E2[act_pts].max()),
        "E2 bottom": E2_bot_raw / norm, "E2 top": E2_top_raw / norm,
        "active thickness (nm)": La,
        "external efficiency": internal_efficiency * rt_t / rt_gain,
        "external efficiency top": internal_efficiency * rt_t / rt_gain * split_top,
        "external efficiency bottom": internal_efficiency * rt_t / rt_gain * (1 - split_top),
    }

    breakdown = {}
    for j, f in enumerate(model.flat):
        if act[j]:
            continue
        key = f.top_group or f.layer.name
        breakdown.setdefault(key, 0.0)
        breakdown[key] += float(power[j] / Pref)
    loss_breakdown = [{"region": k, "rt_loss": v, "alpha_cm": a_i * v / rt_loss if rt_loss else 0.0}
                      for k, v in breakdown.items()]

    cav = model.cavity_mask()
    avg_core = float(np.sum(nl.real[cav] * model.d[cav]) / np.sum(model.d[cav])) if cav.any() else float("nan")
    avg_rms = float(np.sqrt(np.sum(nl.real ** 2 * I) / np.sum(I)))

    nr = [np.atleast_1d(x) for x in nn[::-1]]
    m = tmm.characteristic_matrix(nr, list(model.d[::-1]), np.atleast_1d(lam))
    matrix = tuple(complex(x[0]) for x in m)
    mv = (np.conj(matrix[0]), -np.conj(matrix[1]), -np.conj(matrix[2]), np.conj(matrix[3]))

    return Analysis(
        wavelength=lam, threshold_gain=g, converged=th.converged, photon_energy=Eph,
        rt_gain=rt_gain, rt_loss=rt_loss, rt_transmission=rt_t,
        rt_transmission_top=rt_t_top, rt_transmission_bottom=rt_t_bot,
        enhancement=enh, active_thickness=La, confinement=gamma, effective_length=Leff,
        modal_gain=(gamma * g if rt_model != "exact" else a_i + a_mt + a_mb), alpha_i=a_i, alpha_m=a_mt + a_mb,
        alpha_m_top=a_mt, alpha_m_bottom=a_mb, R_top=R_t, R_bottom=R_b, rt_model=rt_model,
        internal_efficiency=internal_efficiency, ext_eff=eta_t + eta_b, ext_eff_top=eta_t,
        ext_eff_bottom=eta_b, slope_top=eta_t * Eph, slope_bottom=eta_b * Eph, lifetime_ps=tau,
        normalization=normalize, peak_E2=peak, E2_active_max=float(prof.E2[act_pts].max()),
        E2_active_mean=float(np.sum(I[act]) / La / norm), E2_top=E2_top_raw / norm,
        E2_bottom=E2_bot_raw / norm, avg_index_rms=avg_rms, avg_cavity_index=avg_core,
        loss_breakdown=loss_breakdown, matrix=matrix, matrix_vertical=tuple(complex(x) for x in mv),
        vertical=vertical, field=prof)


# ---------------------------------------------------------------------------
# Passive reflectance / transmission spectra
# ---------------------------------------------------------------------------
def _sub_structure_arrays(model: Model, lam, part):
    """Index list & thickness list for a reflectance calculation.

    part = "full_top"     : whole wafer, light incident from the top (exit) medium
           "full_bottom"  : whole wafer, light incident from the substrate
           "top_dbr"      : top mirror seen from inside the cavity (incident medium = cavity
                            layer just below the top DBR), exits into the top medium
           "bottom_dbr"   : bottom mirror seen from the cavity, exits into the substrate
    Active layers are passive here (gain = 0): this is the as-grown mirror response.
    """
    ns = model.indices(lam, 0.0)
    d = list(model.d)
    L = len(d)
    if part in ("full_top", "full_bottom"):
        j = 0 if part == "full_top" else -1
        inc = np.asarray(ns[j]) * np.ones_like(lam, dtype=complex)
        bad = np.abs(np.imag(inc)) >= 1e-2 * np.abs(inc)     # incident half-space strongly absorbing here
        if np.all(bad):
            raise ValueError("The incident medium (%s) is absorbing over the whole range, so a reflectance from "
                             "that side is not defined. Use the mirror views or a transparent medium."
                             % ("top medium" if part == "full_top" else "substrate"))
        ns = list(ns)
        ns[j] = np.real(inc) + 0j          # weak (e.g. free-carrier) loss in the incident half-space ignored
        return ns, d, part == "full_bottom", bad
    role = "top_dbr" if part == "top_dbr" else "bottom_dbr"
    mask = model.role_mask(role)
    idx = np.where(mask)[0]
    if len(idx) == 0:
        raise ValueError(f"No group has the role '{role}'. Mark the mirror groups as Top DBR / Bottom DBR.")
    if role == "top_dbr":
        lo, hi = 0, idx.max()                     # all layers from the top surface to the end of the top DBR
        inc = hi + 1                              # first cavity layer below the mirror
        if inc >= L:
            raise ValueError("Top DBR is not followed by a cavity layer.")
        n_list = [ns[inc + 1]] + [ns[j + 1] for j in range(hi, lo - 1, -1)] + [ns[0]]
        d_list = [d[j] for j in range(hi, lo - 1, -1)]
    else:
        lo, hi = idx.min(), L - 1
        inc = lo - 1
        if inc < 0:
            raise ValueError("Bottom DBR is not preceded by a cavity layer.")
        n_list = [ns[inc + 1]] + [ns[j + 1] for j in range(lo, hi + 1)] + [ns[-1]]
        d_list = [d[j] for j in range(lo, hi + 1)]
    n_list[0] = np.real(n_list[0]) + 0j      # incident (cavity) medium taken as lossless
    return n_list, d_list, False, np.zeros(np.shape(lam), bool)


def reflectance_spectrum(structure: Structure, lam_min, lam_max, points=1001, part="full_top"):
    """Passive (as-grown, no gain) reflectance spectrum. Returns dict with arrays."""
    model = Model(structure)
    lam = np.linspace(float(lam_min), float(lam_max), int(points))
    n_list, d_list, from_bottom, bad = _sub_structure_arrays(model, lam, part)
    if from_bottom:
        r, t, R, T = tmm.reflection_from_bottom(n_list, d_list, lam)
    else:
        r, t, R, T = tmm.reflection_from_top(n_list, d_list, lam)
    R, T, r = np.array(R, float), np.array(T, float), np.array(r, complex)
    # where the incident medium itself absorbs strongly (e.g. GaAs substrate below its band gap
    # wavelength) a reflectance seen from inside it is not defined: blank those points
    R[bad] = np.nan
    T[bad] = np.nan
    r[bad] = np.nan
    return {"wavelength": lam, "R": R, "T": T, "A": np.clip(1 - R - T, 0, None),
            "phase_deg": np.degrees(np.angle(r)), "r": r, "undefined": bad}


def stopband(spec, threshold=0.99, lam0=None):
    """Peak reflectance and its wavelength, plus the stopband defined as the continuous band with
    R >= threshold (default 99 %, the usual VCSEL convention) that contains lam0 (or the peak when
    R(lam0) < threshold). Edges are interpolated linearly between grid points. If the peak stays below
    the threshold, the edges are None and the width is 0. The -3 dB (half-of-peak) band is also returned."""
    lam, R = spec["wavelength"], np.nan_to_num(spec["R"], nan=0.0)
    i = int(np.argmax(R))
    out = {"R_max": float(R[i]), "lambda_at_max": float(lam[i]), "threshold": float(threshold)}

    def band(level, k):
        lo = k
        while lo > 0 and R[lo - 1] >= level:
            lo -= 1
        hi = k
        while hi < len(R) - 1 and R[hi + 1] >= level:
            hi += 1

        def cross(a, b):                       # linear interpolation of R = level between points a, b
            if a == b or R[a] == R[b]:
                return float(lam[b])
            return float(lam[a] + (level - R[a]) * (lam[b] - lam[a]) / (R[b] - R[a]))
        e1 = cross(lo - 1, lo) if lo > 0 else float(lam[lo])
        e2 = cross(hi + 1, hi) if hi < len(R) - 1 else float(lam[hi])
        return e1, e2

    k = i
    if lam0 is not None and lam[0] <= lam0 <= lam[-1]:
        j = int(np.argmin(np.abs(lam - lam0)))
        if R[j] >= threshold:
            k = j
        else:
            # a narrow dip at lam0 (the cavity resonance seen through a whole wafer) splits the band:
            # join the two halves if both start within 3 % of lam0
            left = np.where((R[:j] >= threshold) & (lam[:j] >= lam0 * 0.97))[0]
            right = np.where((R[j:] >= threshold) & (lam[j:] <= lam0 * 1.03))[0]
            if len(left) and len(right):
                a1, _ = band(threshold, int(left[-1]))
                _, b2 = band(threshold, int(j + right[0]))
                out.update(edge_short=a1, edge_long=b2, width_nm=b2 - a1, center=(a1 + b2) / 2, split_by_dip=True)
                h1, h2 = band(R[i] / 2, i) if R[i] > 0 else (float(lam[i]), float(lam[i]))
                out.update(half_short=h1, half_long=h2, half_width_nm=h2 - h1, half_center=(h1 + h2) / 2)
                return out
    if R[k] >= threshold:
        e1, e2 = band(threshold, k)
        out.update(edge_short=e1, edge_long=e2, width_nm=e2 - e1, center=(e1 + e2) / 2)
    else:
        out.update(edge_short=None, edge_long=None, width_nm=0.0, center=None)
    h1, h2 = band(R[i] / 2, i) if R[i] > 0 else (float(lam[i]), float(lam[i]))
    out.update(half_short=h1, half_long=h2, half_width_nm=h2 - h1, half_center=(h1 + h2) / 2)
    return out


# ---------------------------------------------------------------------------
# Vertical's "Marks / Force Wave": tune marked layers so the cavity resonates at the design wavelength
# ---------------------------------------------------------------------------
def _marked_layers(structure):
    out = []

    def walk(items):
        for it in items:
            if getattr(it, "kind", "layer") == "group":
                walk(it.children)
            elif it.marked:
                out.append(it)
    walk(structure.stack)
    return out


def tune_marked(structure: Structure, target=None, tol=1e-6, maxit=40):
    """Scale the thickness of every marked layer by a common factor until the cold-cavity
    resonance (real part of the quasi-normal-mode wavelength) equals `target`
    (default: design wavelength). Modifies `structure` in place; returns a report dict."""
    marked = _marked_layers(structure)
    if not marked:
        raise ValueError("No layers are marked. Tick 'Marked for tuning' on the layer(s) to adjust (e.g. the cavity spacers).")
    target = float(target or structure.design_wavelength)
    base = [(L, L.thickness) for L in marked]

    def resonance(scale):
        for L, t0 in base:
            L.thickness = t0 * scale
        # always start the mode search at the target so the solver stays on the cavity mode
        return cold_cavity_mode(Model(structure), target).real - target

    # secant with a step limit, switching to bisection once the root is bracketed
    s_lo, s_hi = 0.3, 3.0
    s0, s1 = 1.0, 1.02
    f0, f1 = resonance(s0), resonance(s1)
    br = None                                   # (s_a, f_a, s_b, f_b) with f_a*f_b < 0
    if f0 * f1 < 0:
        br = (s0, f0, s1, f1)
    it = 0
    for it in range(maxit):
        if abs(f1) < tol:
            break
        if f1 != f0:
            s2 = s1 - f1 * (s1 - s0) / (f1 - f0)
        else:
            s2 = s1 * (0.9 if f1 > 0 else 1.1)
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
            break                               # pinned at a bound: no solution in range
    if abs(f1) > 1e-3:
        for L, t0 in base:                      # failed: leave the design unchanged
            L.thickness = t0
    return {"scale": s1, "resonance": f1 + target, "converged": abs(f1) <= 1e-3, "iterations": it + 1,
            "layers": [{"name": L.name, "old": t0, "new": L.thickness, "unit": L.thickness_unit} for L, t0 in base]}
