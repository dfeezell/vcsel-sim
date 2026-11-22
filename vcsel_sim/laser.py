"""VCSEL analysis: threshold gain, standing-wave field, gain/loss budget,
confinement & enhancement factors, efficiencies and mirror reflectance.

Physics summary (see docs/theory.md for the derivation)
-------------------------------------------------------
Threshold: the material gain g (cm^-1) of all active layers and the wavelength
are adjusted until the structure supports a field with only OUTGOING waves in
the exit medium and substrate (the transfer-matrix condition for an infinite
transmission). It is solved as a quasi-normal-mode problem: for a trial gain g the complex wavelength
of the mode (zero of 1 - r_up r_down at the top of the first active layer) is found, and g is adjusted
until Im(lambda) = 0 (see solve_threshold). Convention exp(-i w t): a decaying mode has Im(lambda) > 0.

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
        self.z_bot = np.cumsum(self.d) if len(self.d) else np.zeros(0)
        self.z_top = np.concatenate([[0.0], self.z_bot[:-1]]) if len(self.d) else np.zeros(0)
        # same cumulative sum for both, so a layer's bottom is bit-identical to the next layer's top
        self.total_thickness = float(self.z_bot[-1]) if len(self.d) else 0.0

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


def _plane(model: Model):
    """Reference plane for the round-trip condition: the top of the first active layer (else mid-stack)."""
    act = np.where(model.active)[0]
    return int(act[0]) if len(act) else len(model.d) // 2


def round_trip_mismatch(model: Model, lam_c, ns, plane=None):
    """1 - r_up r_down at the top of flat layer `plane`, where r_up / r_down are the reflections of everything
    above / below that plane seen from inside it. Zero exactly when the structure has only outgoing waves
    (the same condition as A0 = 0), but each reflection is computed by propagating from its own exit medium
    toward the plane, the numerically stable direction, so it stays accurate for mirrors of any reflectance."""
    j = _plane(model) if plane is None else plane
    lam1 = np.atleast_1d(np.asarray(lam_c, dtype=complex))
    d = list(model.d)
    nj = ns[j + 1]
    up_n = [nj] + [ns[k + 1] for k in range(j - 1, -1, -1)] + [ns[0]]
    up_d = [d[k] for k in range(j - 1, -1, -1)]
    dn_n = [nj] + [ns[k + 1] for k in range(j, len(d))] + [ns[-1]]
    dn_d = d[j:]
    r_up = tmm.reflection_from_top(up_n, up_d, lam1)[0]
    r_dn = tmm.reflection_from_top(dn_n, dn_d, lam1)[0]
    return complex(1.0 - r_up[0] * r_dn[0])


def cold_cavity_mode(model: Model, lam_guess, gain=0.0, maxit=60):
    """Quasi-normal mode: complex wavelength at which the structure (indices frozen at
    Re(lambda)) has only outgoing waves, i.e. the zero of 1 - r_up r_down. Newton in the complex plane."""
    lam = complex(lam_guess)
    ns = model.indices(lam.real, gain)
    pl = _plane(model)
    for _ in range(maxit):
        f = round_trip_mismatch(model, lam, ns, pl)
        h = 1e-7 * abs(lam)
        df = (round_trip_mismatch(model, lam + h, ns, pl) - f) / h
        if df == 0:
            break
        step = -f / df
        if abs(step) > 1.0:
            step *= 1.0 / abs(step)
        lam += step
        if abs(step) < 1e-13 * abs(lam):
            break
    return lam


def _mode_at_gain(model: Model, lam_start, g, maxit=8):
    """Quasi-normal mode with material gain g in the active layers, the indices evaluated at Re(lambda)
    (re-evaluated until Re(lambda) stops moving, so dispersion is included)."""
    lam = complex(lam_start)
    for _ in range(maxit):
        new = cold_cavity_mode(model, lam, gain=g)
        if abs(new.real - lam.real) < 1e-12 * abs(lam):
            return new
        lam = new
    return lam


def solve_threshold(model: Model, lam_guess=None, g_guess=None, tol=1e-12, maxit=60) -> ThresholdResult:
    """Threshold = the material gain g at which the quasi-normal mode nearest the design wavelength becomes
    real (Im lambda = 0): the structure then supports only outgoing waves at a real wavelength.

    g is found by a secant / bisection search on Im lambda(g), which is close to linear in g. Each evaluation
    is a 1D complex Newton on the round-trip mismatch 1 - r_up r_down (round_trip_mismatch). This stays well conditioned however high the
    mirror reflectance is (the earlier 2D Newton on A0(lambda, g) diverged once the mirror transmission fell
    below ~1e-6). Falls back to that 2D Newton if the mode cannot be followed."""
    if not model.active.any():
        raise ValueError("The structure has no active layers (set Layer type = active on the quantum wells).")
    if not (model.d[model.active] > 0).any():
        raise ValueError("The active layers have zero thickness.")
    lam0 = model.s.design_wavelength if lam_guess is None else float(lam_guess)
    lamc = cold_cavity_mode(model, lam0)
    if not (abs(lamc.real - lam0) < 0.05 * lam0 and lamc.imag > 0):
        lam = find_resonance(model, center=lam0, span=0.06 * lam0, points=6001)
        lamc = cold_cavity_mode(model, lam)
    lamc = _mode_at_gain(model, lamc, 0.0)
    if g_guess is None:
        g_guess = _gain_guess(model, lamc)
    try:
        res = _threshold_qnm(model, lamc, float(g_guess), lam0)
        if res is not None:
            return res
    except (FloatingPointError, ZeroDivisionError, ValueError, np.linalg.LinAlgError):
        pass
    return _solve_threshold_newton2d(model, lamc.real, g_guess, tol, maxit)


def _gain_guess(model, lamc):
    lam = lamc.real
    nn, A, B = solve_field(model, lam, 0.0)
    I = np.array([float(tmm.layer_intensity_integral(A[j], B[j], nn[j], model.d[j - 1], lam))
                  for j in range(1, len(model.d) + 1)])
    W = nn[1:-1].real ** 2 * I
    gamma = float(np.sum(W[model.active]) / np.sum(W))
    ng = float(np.sum(nn[1:-1].real * W) / np.sum(W))
    alpha_tot = 4 * np.pi * ng * abs(lamc.imag) / lam ** 2 * 1e7   # cm^-1
    return alpha_tot / max(gamma, 1e-6)


def _threshold_qnm(model, lamc0, g0, lam0, maxit=60):
    """Secant / bisection on f(g) = Im lambda(g) / Re lambda. Returns ThresholdResult or None."""
    def f(g, start):
        m = _mode_at_gain(model, start, g)
        if not np.isfinite(m.real) or abs(m.real - lam0) > 0.05 * lam0:
            raise ValueError("mode lost")
        return m.imag / m.real, m

    f0, m0 = f(0.0, lamc0)
    g_a, f_a, m_a = 0.0, f0, m0
    # Im lambda is nearly linear in g, so any reasonable second point works; the field-based guess is
    # only trusted in a sane range (it degrades for extreme mirrors)
    g1 = g0 if np.isfinite(g0) and 0 < g0 < 1e5 else 100.0
    f1, m1 = f(g1, m0)
    # bracket the root: Im lambda decreases as the gain rises
    br = None
    if f_a * f1 <= 0:
        br = [(g_a, f_a, m_a), (g1, f1, m1)]
    it = 0
    gp, fp, mp = g_a, f_a, m_a
    gc, fc, mc = g1, f1, m1
    for it in range(1, maxit + 1):
        if abs(fc) < 1e-15:
            break
        if fc != fp:
            gn = gc - fc * (gc - gp) / (fc - fp)
        else:
            gn = gc * 2.0
        if br is not None:
            lo, hi = sorted([br[0][0], br[1][0]])
            if not (lo < gn < hi):
                gn = 0.5 * (lo + hi)
        elif gn > 0 and gn > 20 * max(gc, 1.0):
            gn = 20 * max(gc, 1.0)
        fn, mn = f(gn, mc)
        if br is not None:
            br = [br[0], (gn, fn, mn)] if br[0][1] * fn <= 0 else [(gn, fn, mn), br[1]]
        elif fc * fn <= 0:
            br = [(gc, fc, mc), (gn, fn, mn)]
        gp, fp, mp = gc, fc, mc
        gc, fc, mc = gn, fn, mn
        if abs(gc - gp) <= 1e-13 * max(abs(gc), 1.0):
            break
    conv = abs(fc) < 1e-13
    if not conv:
        return None
    lam = mc.real
    r = abs(round_trip_mismatch(model, lam, model.indices(lam, gc)))
    return ThresholdResult(lam, gc, True, it, r)


def _solve_threshold_newton2d(model: Model, lam_guess, g_guess, tol=1e-12, maxit=60) -> ThresholdResult:
    lam = float(lam_guess)
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
    d = list(model.d)
    tops = tmm.fields_up(ns, d, lam1, (one, ns[-1] * one))
    L = len(model.d)
    # Above the reference plane (top of the first active layer) the substrate-up propagation runs through the
    # top mirror in its unstable direction: rounding errors grow ~1/T_top and swamp the field once the mirror
    # transmits less than ~1e-10. There, propagate DOWN from the top medium instead (outgoing wave only,
    # also the stable direction) and scale that solution to match E at the plane.
    j = _plane(model)
    if L and 0 < j:
        dn = tmm.fields_down(ns, d, lam1, (one, -ns[0] * one))      # top medium: B = 1, A = 0
        Ej = tops[j + 1][0]
        Ed = dn[j + 1][0]
        if np.all(np.abs(Ed) > 0):
            sc = Ej / Ed
            for k in range(0, j + 1):
                tops[k] = (dn[k][0] * sc, dn[k][1] * sc)
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
        zz = model.z_top[j - 1] + u
        zz[-1] = model.z_bot[j - 1]                      # exact interface position (no rounding step backwards)
        zs.append(zz); E2s.append(e2)
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
    confinement_model: str = "dispersive" # energy weighting of Gamma: n n_g |E|^2 (dispersive) or n^2 |E|^2
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
            rt_model="linear", vertical_spacing=0.1, confinement_model="dispersive") -> Analysis:
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

    # group index of every layer (dispersive energy density (eps0/2) n n_g |E|^2), also used for the lifetime
    dl = 1e-3 * lam
    n_p = np.array([np.real(x[0]) for x in model.indices(lam + dl, g)])[inner]
    n_m = np.array([np.real(x[0]) for x in model.indices(lam - dl, g)])[inner]
    n_g = nl.real - lam * (n_p - n_m) / (2 * dl)
    # Confinement factor = share of the mode's stored energy in the active layers. "dispersive" (default) uses
    # the energy density n n_g |E|^2, consistent with the photon lifetime and with dN/dt = Gamma v_g g N;
    # "nondispersive" uses eps|E|^2 = n^2|E|^2 (the common textbook form, which ignores dispersion).
    W = (nl.real ** 2 if confinement_model == "nondispersive" else nl.real * n_g) * I
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
        confinement_model=confinement_model,
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


def _eval_part(model, lam, part):
    n_list, d_list, from_bottom, bad = _sub_structure_arrays(model, lam, part)
    f = tmm.reflection_from_bottom if from_bottom else tmm.reflection_from_top
    r, t, R, T = f(n_list, d_list, lam)
    return np.array(r, complex), np.array(R, float), np.array(T, float), bad


def _refine_points(model, lam, R, part, lo, hi):
    """Extra wavelengths that resolve narrow features a uniform grid can miss or alias:
    (1) a dense band of +-8 linewidths around the cold-cavity quasi-normal mode (a VCSEL dip can be far
    narrower than the grid step, and may not even register as a grid minimum), and (2) every local
    minimum of R on the grid, zoomed three times by 21-point sub-grids, so the plotted dip reaches its
    true depth at its true wavelength."""
    extra = []
    step = (hi - lo) / max(len(lam) - 1, 1)
    try:
        if not model.active.any():
            raise ValueError("no cavity")          # a mirror alone has no resonance to look for
        lc = cold_cavity_mode(model, model.s.design_wavelength)
        w = abs(lc.imag)
        if np.isfinite(lc.real) and lo < lc.real < hi and 0 < w < 2 * step * len(lam):
            half = max(8 * w, 2 * step)
            extra.append(np.linspace(max(lo, lc.real - half), min(hi, lc.real + half), 321))
    except Exception:
        pass
    if extra:
        lam2 = np.unique(np.concatenate([lam] + extra))
        R = _eval_part(model, lam2, part)[1]
        lam = lam2
    Rf = np.nan_to_num(R, nan=np.inf)
    idx = np.where((Rf[1:-1] < Rf[:-2]) & (Rf[1:-1] <= Rf[2:]))[0] + 1
    if len(idx) == 0 or len(idx) > 2000:
        return extra
    a, b = lam[idx - 1], lam[idx + 1]
    for _ in range(3):
        u = np.linspace(0.0, 1.0, 21)
        grid = a[:, None] + (b - a)[:, None] * u[None, :]
        Rg = _eval_part(model, grid.ravel(), part)[1].reshape(grid.shape)
        extra.append(grid.ravel())
        k = np.argmin(np.nan_to_num(Rg, nan=np.inf), axis=1)
        k = np.clip(k, 1, 19)
        rows = np.arange(len(k))
        a, b = grid[rows, k - 1], grid[rows, k + 1]
    return extra


def reflectance_spectrum(structure: Structure, lam_min, lam_max, points=1001, part="full_top", refine=True,
                         wavelengths=None):
    """Passive (as-grown, no gain) reflectance spectrum. Returns dict with arrays.

    With refine (default, when points > 1) the uniform grid is augmented near the cavity resonance and
    at every reflectance minimum (see _refine_points), so the returned wavelength grid is non-uniform.
    `wavelengths` evaluates exactly those points instead (no refinement)."""
    model = Model(structure)
    lo, hi = float(lam_min), float(lam_max)
    lam = np.linspace(lo, hi, int(points)) if wavelengths is None else np.asarray(wavelengths, float)
    r, R, T, bad = _eval_part(model, lam, part)
    if refine and wavelengths is None and len(lam) > 2 and hi > lo:
        extra = _refine_points(model, lam, R, part, lo, hi)
        if extra:
            lam = np.unique(np.concatenate([lam] + [e[(e >= lo) & (e <= hi)] for e in extra]))
            r, R, T, bad = _eval_part(model, lam, part)
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
    """Scale the thickness of the marked layers (or, when none are marked, the cavity spacers) by a common
    factor until the cold-cavity resonance equals `target` (default: design wavelength). Modifies `structure`
    in place; returns a report dict (unchanged design when it fails)."""
    from .retarget import tuning_layers, tune_layers
    layers, how = tuning_layers(structure)
    rep = tune_layers(structure, layers, target, tol=tol, maxit=maxit)
    rep["chosen"] = how
    return rep
