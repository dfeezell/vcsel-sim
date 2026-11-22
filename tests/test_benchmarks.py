"""Analytical benchmarks: closed-form results the transfer-matrix engine must reproduce.

All layers use fixed (non-dispersive) indices so the formulas apply exactly. Each test prints its
worst deviation when run with `pytest -s`.
"""
import math

import numpy as np

from vcsel_sim import laser, tmm
from vcsel_sim.structure import Group, Layer, Structure

C_NM_PS = 2.99792458e5


def fixed(name, n, d_nm, typ="undoped", alpha=0.0, k=0.0):
    return Layer(name=name, material="Generic", index_mode="fixed", n_real=n, n_imag=k, thickness=d_nm,
                 thickness_unit="nm", layer_type=typ, absorption=alpha)


def medium(n, name="medium"):
    return fixed(name, n, 0.0, typ="other")


# ---------------------------------------------------------------- B1: Fabry-Perot etalon (Airy)
def test_B1_airy_etalon():
    """Lossless slab (n, d) between media n0: R = F sin^2(delta) / (1 + F sin^2(delta)), F = 4R1/(1-R1)^2,
    delta = 2 pi n d / lambda. Absorbing slab: exact Airy sum with complex Fresnel coefficients,
    t = t01 t10 e^{i delta} / (1 - r10^2 e^{2 i delta}), delta = 2 pi (n + i kappa) d / lambda. R + T + A = 1."""
    n0, n, d = 1.0, 3.5, 1000.0
    lam = np.linspace(900.0, 1100.0, 2001)
    r, t, R, T = tmm.reflection_from_top([n0 + 0j, n + 0j, n0 + 0j], [d], lam)
    R1 = ((n - n0) / (n + n0)) ** 2
    F = 4 * R1 / (1 - R1) ** 2
    s2 = np.sin(2 * np.pi * n * d / lam) ** 2
    err1 = max(np.max(np.abs(R - F * s2 / (1 + F * s2))), np.max(np.abs(R + T - 1)))
    nc = n + 1j * 50e-7 * lam / (4 * np.pi)            # alpha = 50 cm^-1
    _, _, R2, T2 = tmm.reflection_from_top([n0 + 0j, nc, n0 + 0j], [d], lam)
    r01, t01, t10 = (n0 - nc) / (n0 + nc), 2 * n0 / (n0 + nc), 2 * nc / (n0 + nc)
    r10 = -r01
    ph = np.exp(2j * np.pi * nc * d / lam)
    den = 1 - r10 ** 2 * ph ** 2
    t_an = t01 * t10 * ph / den
    r_an = r01 + t01 * t10 * r10 * ph ** 2 / den
    err2 = max(np.max(np.abs(T2 - np.abs(t_an) ** 2)), np.max(np.abs(R2 - np.abs(r_an) ** 2)))
    assert np.all(R2 + T2 < 1)                           # absorbing: A = 1 - R - T > 0 (loss, not gain)
    print(f"\nB1 Airy: lossless max |R - R_airy|, |R+T-1| = {err1:.1e}; absorbing slab max |R,T - Airy| = {err2:.1e}")
    assert err1 < 1e-12 and err2 < 1e-12


# ---------------------------------------------------------------- B2: quarter-wave DBR
def test_B2_quarter_wave_dbr():
    """R(lambda0) = ((n0 - Y)/(n0 + Y))^2, Y = (n1/n2)^(2N) n_s; phase of r at lambda0 = 0 or pi;
    infinite-stack stopband in normalised frequency: Delta(lambda0/lambda) = (4/pi) arcsin((nH - nL)/(nH + nL))."""
    lam0, n0, ns, nH, nL = 980.0, 3.2, 3.5, 3.5, 2.9
    worst = 0.0
    for N in (1, 5, 20, 40):
        for first, second in ((nH, nL), (nL, nH)):
            ns_list = [n0 + 0j] + [first + 0j, second + 0j] * N + [ns + 0j]
            d = [lam0 / (4 * first), lam0 / (4 * second)] * N
            r, _, R, _ = tmm.reflection_from_top(ns_list, d, np.array([lam0]))
            Y = (first / second) ** (2 * N) * ns
            worst = max(worst, abs(R[0] - ((n0 - Y) / (n0 + Y)) ** 2))
            ph = abs(np.angle(r[0]))
            assert min(ph, abs(ph - math.pi)) < 1e-9          # real reflection coefficient at the Bragg wavelength
    # stopband edges of a long stack: R falls to 50 % at the Bloch band edges (sharp for N = 300)
    N = 300
    ns_list = [nH + 0j] + [nL + 0j, nH + 0j] * N + [nH + 0j]
    d = [lam0 / (4 * nL), lam0 / (4 * nH)] * N
    lam = np.linspace(800.0, 1200.0, 40001)
    _, _, R, _ = tmm.reflection_from_top(ns_list, d, lam)
    inband = np.where(R > 0.5)[0]
    # contiguous band containing lambda0
    i0 = int(np.argmin(np.abs(lam - lam0)))
    lo = i0
    while lo > 0 and R[lo - 1] > 0.5:
        lo -= 1
    hi = i0
    while hi < len(R) - 1 and R[hi + 1] > 0.5:
        hi += 1
    dg_num = lam0 / lam[lo] - lam0 / lam[hi]
    dg_an = 4 / math.pi * math.asin((nH - nL) / (nH + nL))
    rel = abs(dg_num - dg_an) / dg_an
    print(f"\nB2 DBR: max |R - R_analytic| = {worst:.1e}; stopband (N=300) {dg_num:.5f} vs {dg_an:.5f} ({rel:.1e} rel.)")
    assert worst < 1e-12 and rel < 5e-3


# ---------------------------------------------------------------- B3: Fabry-Perot slab laser threshold
def slab_laser(n=3.5, L=None, lam0=980.0, m=20, alpha=0.0, n_out=1.0):
    L = L or m * lam0 / (2 * n)                     # m half-waves: resonance exactly at lam0
    s = Structure(name="slab", design_wavelength=lam0, top=medium(n_out, "out1"), substrate=medium(n_out, "out2"),
                  stack=[fixed("gain slab", n, L, typ="active", alpha=alpha)])
    return s, L


def slab_exact(n, L, alpha, n_out, m, lam0=980.0):
    """Independent solution of the slab-laser characteristic equation r_c^2 exp(2 i k L) = 1 with the
    complex Fresnel coefficient r_c = (n_c - n_out)/(n_c + n_out), n_c = n + i (alpha - g) lambda / 4 pi.
    Returns (g in cm^-1, lambda in nm). Plain 2x2 Newton, no transfer matrices."""
    import cmath

    def F(x):
        g, lam = x
        nc = n + 1j * (alpha - g) * lam / (4 * math.pi)
        v = 2 * cmath.log((nc - n_out) / (nc + n_out)) + 4j * math.pi * nc * L / lam - 2j * math.pi * m
        return np.array([v.real, v.imag])
    x = np.array([alpha + 2 * math.log((n + n_out) / (n - n_out)) / L, lam0])
    for _ in range(40):
        J = np.empty((2, 2))
        for i, h in enumerate((1e-10 * x[0], 1e-7)):
            dx = np.zeros(2); dx[i] = h
            J[:, i] = (F(x + dx) - F(x - dx)) / (2 * h)
        x = x - np.linalg.solve(J, F(x))
    return x[0] * 1e7, x[1]


def test_B3_slab_laser_threshold():
    """Uniform gain slab in a uniform medium. Textbook result g_th = alpha + (1/L) ln(1/R) at lambda_m = 2 n L / m,
    R = ((n - n_out)/(n + n_out))^2. That formula neglects the gain's own kappa in the Fresnel coefficient
    (a ~1e-4 relative effect), so the code is checked against the exact characteristic equation (slab_exact),
    and the textbook formula is checked to the size of that neglected term."""
    worst_g, worst_l, worst_tb = 0.0, 0.0, 0.0
    for n, m, alpha, n_out in ((3.5, 20, 0.0, 1.0), (3.5, 7, 25.0, 1.0), (2.5, 40, 10.0, 1.5)):
        s, L = slab_laser(n=n, m=m, alpha=alpha, n_out=n_out)
        a = laser.analyze(s)
        assert a.converged
        g_ex, lam_ex = slab_exact(n, L, alpha * 1e-7, n_out, m)
        worst_g = max(worst_g, abs(a.threshold_gain - g_ex) / g_ex)
        worst_l = max(worst_l, abs(a.wavelength - lam_ex))
        g_tb = alpha + math.log(1 / ((n - n_out) / (n + n_out)) ** 2) / (L * 1e-7)
        worst_tb = max(worst_tb, abs(a.threshold_gain - g_tb) / g_tb)
    print(f"\nB3 slab laser: rel. |g_th - exact| = {worst_g:.1e}, |lambda - exact| = {worst_l:.1e} nm; "
          f"textbook ln(1/R)/L formula within {worst_tb:.1e} (rel.)")
    assert worst_g < 1e-9 and worst_l < 1e-9 and worst_tb < 2e-3


# ---------------------------------------------------------------- B4: photon lifetime and energy balance
def test_B4_lifetime_and_energy_balance():
    """Uniform non-dispersive gain slab: confinement factor Gamma = 1 and photon lifetime tau = n / (c g_th)
    (Coldren: 1/tau = v_g <alpha_i + alpha_m>, and at threshold <alpha_i + alpha_m> = g_th, v_g = c/n).
    At threshold, power generated = power absorbed + power emitted (round-trip gain = loss + transmission),
    for any structure; checked on the slab and on a half-gain / half-absorbing slab."""
    s, _ = slab_laser(n=3.5, m=20)
    a = laser.analyze(s)
    tau_an = 3.5 / (C_NM_PS * a.threshold_gain * 1e-7)
    e_tau = abs(a.lifetime_ps - tau_an) / tau_an
    e_gam = abs(a.confinement - 1.0)
    bal = abs(a.rt_gain - a.rt_loss - a.rt_transmission) / a.rt_gain
    n, lam0, m = 3.5, 980.0, 20
    L = m * lam0 / (2 * n)
    s2 = Structure(name="split", design_wavelength=lam0, top=medium(1.0), substrate=medium(1.0),
                   stack=[fixed("gain", n, L / 2, typ="active"), fixed("loss", n, L / 2, alpha=40.0)])
    a2 = laser.analyze(s2)
    bal2 = abs(a2.rt_gain - a2.rt_loss - a2.rt_transmission) / a2.rt_gain
    print(f"\nB4 lifetime: rel. |tau - n/(c g_th)| = {e_tau:.1e}; |Gamma - 1| = {e_gam:.1e}; "
          f"energy balance {bal:.1e} (slab), {bal2:.1e} (half absorbing)")
    assert e_tau < 1e-9 and e_gam < 1e-12 and bal < 1e-10 and bal2 < 1e-10


# ---------------------------------------------------------------- B5: standing-wave enhancement factor
def test_B5_enhancement_factor():
    """In a high-Q cavity the field is a pure standing wave, |E|^2 = 2|A|^2 (1 + cos 2kz). A layer of thickness d
    centred on an antinode has Gamma_enh = 1 + sin(kd)/(kd); on a node 1 - sin(kd)/(kd) (k = 2 pi n / lambda).
    Built as a one-wavelength cavity of index nc between 40-pair DBRs whose layer next to the cavity is low-index
    (nc > nL, so r = +|r| at the cavity boundary, so antinodes at both ends and in the middle)."""
    lam0, nc, nH, nL = 980.0, 3.0, 3.5, 2.9
    worst = 0.0
    for where, sign in (("antinode", +1), ("node", -1)):
        # (a 0.5 nm layer on a node needs g_th ~ 2e6 cm^-1; that much gain unbalances the two travelling
        # waves, so the pure-standing-wave formula no longer applies there and the case is left out)
        for d in ((0.5, 10.0, 40.0) if sign > 0 else (10.0, 40.0)):
            Lc = lam0 / nc                                   # one wavelength
            zc = Lc / 2 if where == "antinode" else Lc / 4   # centre: antinode; quarter: node
            top = Group(name="top", repeats=40, role="top_dbr",
                        children=[fixed("H", nH, lam0 / (4 * nH)), fixed("L", nL, lam0 / (4 * nL))])
            bot = Group(name="bot", repeats=40, role="bottom_dbr",
                        children=[fixed("L", nL, lam0 / (4 * nL)), fixed("H", nH, lam0 / (4 * nH))])
            cav = [fixed("sp1", nc, zc - d / 2), fixed("act", nc, d, typ="active"), fixed("sp2", nc, Lc - zc - d / 2)]
            s = Structure(name="sw", design_wavelength=lam0, top=medium(nH), substrate=medium(nH), stack=[top] + cav + [bot])
            a = laser.analyze(s)
            kd = 2 * math.pi * nc * d / lam0
            enh_an = 1 + sign * math.sin(kd) / kd
            worst = max(worst, abs(a.enhancement - enh_an))
    print(f"\nB5 enhancement: max |Gamma_enh - (1 ± sin(kd)/kd)| = {worst:.1e}")
    assert worst < 1e-8
