"""Stand-alone analytical sanity checks of the transfer-matrix solver.

Run from the repository root:

    python -m vcsel_sim.verify

or call `verify_tmm()` from Python; it returns a list of check results and raises nothing, so it can also
be used inside a notebook. Every structure here uses fixed, non-dispersive indices so the closed forms
hold exactly.

Checks
------
1. Energy conservation: R + T = 1 for lossless stacks (random multilayers, a 40-pair DBR, a VCSEL-like
   cavity), from both sides, with different incident and exit indices, across a full wavelength sweep.
2. Quarter-wave DBR peak reflectance at lambda_B = 4 n_H d_H = 4 n_L d_L:
       R_max = ((1 - (n_H/n_L)^{2N} n_s/n_0) / (1 + (n_H/n_L)^{2N} n_s/n_0))^2
   for the stack n_0 | (H L)^N | n_s, and lambda_B is the stopband centre (R symmetric in 1/lambda).
3. Cavity resonance and phase condition: a lossless lambda/2 or lambda cavity between mirror-image DBRs,
   in the same outer medium on both sides, is a resonant transmission filter: R(lambda_B) = 0 and the dip is
   the minimum of R. The |E|^2 maximum (found analytically, not on a sampling grid) sits at the centre of the
   cavity, where the quantum well goes.

Antinode placement depends on the sign of the reflection at the cavity edges: with the low-index DBR layer
next to the cavity (n_c > n_L, r > 0) the edges are antinodes and a lambda cavity has an antinode at its
centre; with the high-index layer next to it (n_c < n_H, r < 0) the edges are nodes and a lambda/2 cavity
has its antinode at the centre. The two cases below use those standard layouts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

import numpy as np

from . import tmm


@dataclass
class Check:
    name: str
    value: float        # measured deviation
    tol: float
    detail: str = ""

    @property
    def passed(self) -> bool:
        return bool(np.isfinite(self.value) and self.value <= self.tol)


def _qw(n, lam):
    """Quarter-wave thickness (nm)."""
    return lam / (4.0 * n)


def intensity_maxima(A, B, n, d, lam):
    """Exact positions u (0..d, nm from the layer top) of the local maxima of |E|^2 in a lossless layer
    where E(u) = A e^{iku} + B e^{-iku}: |E|^2 = |A|^2 + |B|^2 + 2|A B| cos(2ku + arg(A B*))."""
    k = 2 * math.pi * float(np.real(n)) / lam
    phi = float(np.angle(A * np.conj(B)))
    period = math.pi / k
    u = (-phi / (2 * k)) % period
    out = []
    while u <= d + 1e-12:
        out.append(u)
        u += period
    return out


def _fields(n_list, d_list, lam):
    """Down/up amplitudes at the top of every medium for light incident from the top (exit medium: outgoing only)."""
    lam1 = np.array([lam])
    tops = tmm.fields_up([np.atleast_1d(complex(x)) for x in n_list], list(d_list), lam1,
                         (np.ones(1, complex), np.atleast_1d(complex(n_list[-1]))))
    A, B = [], []
    for j, (E, H) in enumerate(tops):
        a, b = tmm.amplitudes(E, H, complex(n_list[j]))
        A.append(complex(a[0])); B.append(complex(b[0]))
    return A, B


def check_energy_conservation(seed=1) -> Check:
    rng = np.random.default_rng(seed)
    lam = np.linspace(700.0, 1300.0, 6001)
    worst = 0.0
    cases = []
    for _ in range(20):                                     # random lossless multilayers
        L = int(rng.integers(1, 60))
        n = [complex(rng.uniform(1.0, 2.0))] + list(rng.uniform(1.3, 3.7, L) + 0j) + [complex(rng.uniform(1.0, 3.6))]
        d = list(rng.uniform(5.0, 400.0, L))
        cases.append((n, d))
    nH, nL = 3.52, 2.98                                     # 40-pair GaAs/AlAs-like DBR on GaAs, from air
    cases.append(([1.0 + 0j] + [nH + 0j, nL + 0j] * 40 + [nH + 0j], [_qw(nH, 980), _qw(nL, 980)] * 40))
    for n, d in cases:
        for f in (tmm.reflection_from_top, tmm.reflection_from_bottom):
            _, _, R, T = f(n, d, lam)
            worst = max(worst, float(np.max(np.abs(R + T - 1.0))))
    return Check("1. Energy conservation  max|R + T - 1|", worst, 1e-13,
                 f"{len(cases)} lossless stacks x 2 sides x {lam.size} wavelengths (700-1300 nm)")


def check_dbr_peak() -> List[Check]:
    lamB, nH, nL = 980.0, 3.52, 2.98
    worst, worst_pk = 0.0, 0.0
    for n0, ns in ((1.0, 3.52), (1.0, 1.0), (3.2, 1.45)):
        for N in (1, 2, 5, 10, 20, 30):
            n = [n0 + 0j] + [nH + 0j, nL + 0j] * N + [ns + 0j]
            d = [_qw(nH, lamB), _qw(nL, lamB)] * N
            _, _, R, _ = tmm.reflection_from_top(n, d, np.array([lamB]))
            q = (nH / nL) ** (2 * N) * ns / n0
            worst = max(worst, abs(float(R[0]) - ((1 - q) / (1 + q)) ** 2))
            # lambda_B is the centre of the stopband: for quarter-wave layers R depends on the phase
            # delta = (pi/2) lambda_B / lambda only through cos(delta), so R is exactly symmetric in 1/lambda about 1/lambda_B
            eps = np.linspace(1e-4, 0.15, 400)
            _, _, Rp, _ = tmm.reflection_from_top(n, d, lamB / (1 + eps))
            _, _, Rm, _ = tmm.reflection_from_top(n, d, lamB / (1 - eps))
            worst_pk = max(worst_pk, float(np.max(np.abs(Rp - Rm))))
    return [Check("2a. DBR peak  max|R(lambda_B) - R_max|", worst, 1e-13, "N = 1-30, three n0/ns pairs"),
            Check("2b. DBR  stopband symmetry about 1/lambda_B", worst_pk, 1e-12,
                  "max|R(lambda_B/(1+e)) - R(lambda_B/(1-e))|, e up to 0.15: lambda_B is the stopband centre")]


def _cavity(lamB, nH, nL, nc, waves, N, n_out, low_next_to_cavity):
    """Mirror-image DBRs around a cavity of `waves` x lambda optical thickness, split into spacer | QW | spacer
    (the QW: 1 nm of the cavity material at the centre, so the stack stays lossless and uniform)."""
    pair = [(nH, _qw(nH, lamB)), (nL, _qw(nL, lamB))]
    if low_next_to_cavity:
        top = pair * N                                      # ... H L | cavity
    else:
        top = pair[::-1] * N                                # ... L H | cavity
    bot = top[::-1]
    Lc = waves * lamB / nc
    qw = 1.0
    cav = [(nc, (Lc - qw) / 2), (nc, qw), (nc, (Lc - qw) / 2)]
    layers = top + cav + bot
    n = [n_out + 0j] + [x[0] + 0j for x in layers] + [n_out + 0j]
    d = [x[1] for x in layers]
    return n, d, len(top), Lc


def check_cavity() -> List[Check]:
    lamB, nH, nL, nc, N, n_out = 980.0, 3.52, 2.98, 3.25, 20, 3.52
    worst_R, worst_dip, worst_z = 0.0, 0.0, 0.0
    det = []
    for waves, low_next in ((1.0, True), (0.5, False)):
        n, d, j0, Lc = _cavity(lamB, nH, nL, nc, waves, N, n_out, low_next)
        _, _, R0, _ = tmm.reflection_from_top(n, d, np.array([lamB]))
        worst_R = max(worst_R, float(R0[0]))
        # dip position: R minimum by golden-section search on the exact R(lambda) (no grid)
        f = lambda x: float(tmm.reflection_from_top(n, d, np.array([x]))[2][0])
        a, b = lamB - 0.5, lamB + 0.5
        g = (math.sqrt(5) - 1) / 2
        for _ in range(120):
            c1, c2 = b - g * (b - a), a + g * (b - a)
            if f(c1) < f(c2):
                b = c2
            else:
                a = c1
        worst_dip = max(worst_dip, abs((a + b) / 2 - lamB))
        # |E|^2 maxima inside the cavity (layers j0+1..j0+3 in the medium list), exact positions
        A, B = _fields(n, d, lamB)
        z_top = j0 and sum(d[:j0]) or 0.0
        best, zbest = -1.0, None
        z = z_top
        for k in range(3):
            j = j0 + 1 + k
            for u in intensity_maxima(A[j], B[j], n[j], d[j - 1], lamB):
                kk = 2 * math.pi * nc / lamB
                e2 = abs(A[j] * np.exp(1j * kk * u) + B[j] * np.exp(-1j * kk * u)) ** 2
                zz = z + u
                # prefer the maximum nearest the cavity centre among equal-height antinodes
                if e2 > best * (1 + 1e-9) or (abs(e2 - best) <= 1e-9 * best and abs(zz - z_top - Lc / 2) < abs(zbest - z_top - Lc / 2)):
                    best, zbest = e2, zz
            z += d[j - 1]
        off = abs(zbest - (z_top + Lc / 2))
        worst_z = max(worst_z, off)
        det.append(f"{'lambda' if waves == 1 else 'lambda/2'} cavity: R = {R0[0]:.1e}, antinode {off:.1e} nm from QW centre")
    return [Check("3a. Cavity  R(lambda_B) for symmetric lossless cavity", worst_R, 1e-12, "; ".join(det)),
            Check("3b. Cavity  |lambda_dip - lambda_B| (nm)", worst_dip, 1e-6, "golden-section minimum of exact R"),
            Check("3c. Cavity  |z_antinode - z_QW| (nm)", worst_z, 1e-9, "analytic |E|^2 maxima, no sampling grid")]


def verify_tmm(verbose=True) -> List[Check]:
    checks = [check_energy_conservation()] + check_dbr_peak() + check_cavity()
    if verbose:
        for c in checks:
            print(f"{'PASS' if c.passed else 'FAIL'}  {c.name:58s} {c.value:9.2e}  (tol {c.tol:.0e})  {c.detail}")
    return checks


if __name__ == "__main__":
    import sys
    sys.exit(0 if all(c.passed for c in verify_tmm()) else 1)
