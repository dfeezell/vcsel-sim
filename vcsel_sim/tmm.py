"""Transfer-matrix core (normal incidence, 1D).

Conventions
-----------
* Layers are ordered top -> bottom: index 0 is the semi-infinite exit (top)
  medium, the last entry is the semi-infinite substrate.
* z is measured DOWNWARD from the top surface (z=0 at the top of the first
  stack layer). The "forward" (+z) wave travels down toward the substrate.
* Time dependence exp(-i w t); complex index n = n' + i k with k > 0 = loss.
* In each layer E(z) = A exp(ik(z-z_top)) + B exp(-ik(z-z_top)) and the
  normalised magnetic field H = n (A e^{..} - B e^{..}) (units of the free-space
  admittance). [E, H] is continuous at every interface.
* Characteristic matrix of a layer (thickness d, phase delta = 2 pi n d / lambda):
      [E;H](z+d) = [[cos d, i sin d / n], [i n sin d, cos d]] [E;H](z)

All functions are vectorised over wavelength (1D numpy array).
"""
from __future__ import annotations

import numpy as np


def _expint(c, d):
    """Integral_0^d exp(c u) du for complex c (vectorised, stable for c->0)."""
    c = np.asarray(c, dtype=complex)
    small = np.abs(c * d) < 1e-8
    safe = np.where(small, 1.0, c)
    val = np.expm1(np.where(small, 0.0, c * d)) / safe   # never evaluate exp of a discarded branch
    return np.where(small, d * (1 + c * d / 2), val)


def fields_up(n_list, d_list, lam, start):
    """Propagate [E,H] from the top of the substrate up to the top surface.

    n_list : list of complex arrays (len L+2) incl. top medium [0] and substrate [-1]
    d_list : thicknesses (nm) of the L inner layers (len L)
    start  : (E, H) at the substrate interface (arrays)
    Returns list EH_top[j] for inner layers j=1..L (E,H at top of layer j), plus
    EH at z=0 seen from the top medium (same as EH_top[1]).
    """
    E, H = start
    L = len(d_list)
    tops = [None] * (L + 2)
    tops[L + 1] = (E, H)  # top of substrate
    for j in range(L, 0, -1):
        n = n_list[j]
        delta = 2 * np.pi * n * d_list[j - 1] / lam
        c, s = np.cos(delta), np.sin(delta)
        # propagate upward by d: inverse matrix (delta -> -delta)
        E, H = c * E - 1j * s / n * H, -1j * n * s * E + c * H
        tops[j] = (E, H)
    tops[0] = (E, H)
    return tops


def fields_down(n_list, d_list, lam, start):
    """Propagate [E,H] from the top surface (z=0) down to the substrate.
    Returns list of (E,H) at the TOP of each layer (index 1..L) and at the top of the substrate."""
    E, H = start
    L = len(d_list)
    tops = [None] * (L + 2)
    tops[0] = (E, H)
    for j in range(1, L + 1):
        tops[j] = (E, H)
        n = n_list[j]
        delta = 2 * np.pi * n * d_list[j - 1] / lam
        c, s = np.cos(delta), np.sin(delta)
        E, H = c * E + 1j * s / n * H, 1j * n * s * E + c * H
    tops[L + 1] = (E, H)
    return tops


def amplitudes(E, H, n):
    """Forward (down-going, A) and backward (up-going, B) amplitudes from E,H."""
    return 0.5 * (E + H / n), 0.5 * (E - H / n)


def characteristic_matrix(n_list, d_list, lam):
    """Total characteristic matrix M of the inner layers such that
    [E;H](bottom) = M [E;H](top). Returns (m11, m12, m21, m22)."""
    m11 = np.ones_like(lam, dtype=complex); m12 = np.zeros_like(m11)
    m21 = np.zeros_like(m11); m22 = np.ones_like(m11)
    for j in range(1, len(d_list) + 1):
        n = n_list[j]
        delta = 2 * np.pi * n * d_list[j - 1] / lam
        c, s = np.cos(delta), np.sin(delta)
        p11, p12, p21, p22 = c, 1j * s / n, 1j * n * s, c
        m11, m12, m21, m22 = (p11 * m11 + p12 * m21, p11 * m12 + p12 * m22,
                              p21 * m11 + p22 * m21, p21 * m12 + p22 * m22)
    return m11, m12, m21, m22


def reflection_from_top(n_list, d_list, lam):
    """Amplitude reflection & transmission for light incident from the top medium.
    Returns r, t (field), R, T (power)."""
    n0, ns = n_list[0], n_list[-1]
    # outgoing-only in substrate: A_s = 1, B_s = 0 -> E=1, H=ns
    tops = fields_up(n_list, d_list, lam, (np.ones_like(lam, dtype=complex), ns * np.ones_like(lam, dtype=complex)))
    E0, H0 = tops[0]
    A0, B0 = amplitudes(E0, H0, n0)
    r = B0 / A0
    t = 1.0 / A0
    R = np.abs(r) ** 2
    T = np.real(ns) / np.real(n0) * np.abs(t) ** 2
    return r, t, R, T


def reflection_from_bottom(n_list, d_list, lam):
    """Reflection for light incident from the substrate going up."""
    return reflection_from_top(list(n_list[::-1]), list(d_list[::-1]), lam)


def layer_intensity_integral(A, B, n, d, lam):
    """Integral over a layer of |E|^2 dz (exact, analytic) for E = A e^{iku} + B e^{-iku}."""
    k = 2 * np.pi * n / lam
    kr, ki = np.real(k), np.imag(k)
    return (np.abs(A) ** 2 * np.real(_expint(-2 * ki, d)) + np.abs(B) ** 2 * np.real(_expint(2 * ki, d))
            + 2 * np.real(A * np.conj(B) * _expint(2j * kr, d)))
