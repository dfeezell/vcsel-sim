"""Doping-induced absorption: alpha = sigma * N.

Optional per-layer model ("absorption from doping"). A layer that uses it gets alpha = sigma * N, where
N is the layer's doping (cm^-3) and sigma (cm^2) the literature cross-section for the material family,
carrier type and wavelength. Manual alpha stays the default.

Sources
-------
As  (AlGaAs, InGaAs): H. C. Casey, Jr., J. Appl. Phys. 49, 3684 (1978), eq. (9):
    alpha_fc = 3e-18 n + 7e-18 p cm^-1, GaAs near the band gap at room temperature (Casey applies the same
    loss to the AlGaAs cladding).
P   (InP, InGaAsP, InAlGaAs) holes, intervalence band absorption, per 1e18 holes:
    14 cm^-1 at 1.3 um and 20 cm^-1 at 1.5 um (H. C. Casey, Jr. and P. L. Carter, Appl. Phys. Lett. 44, 82
    (1984)); 25 cm^-1 at 1.6 um (C. H. Henry et al., IEEE J. Quantum Electron. QE-19, 947 (1983), who find the
    same values for InP, In0.53Ga0.47As and GaAs and so for the whole lattice-matched quaternary).
    J. Taylor and V. Tolstikhin, J. Appl. Phys. 87, 1054 (2000) reproduce them (14 and 24 cm^-1).
P   electrons: W. Walukiewicz et al., J. Appl. Phys. 51, 2659 (1980), Table III (300 K, lambda = 10 um, uncompensated
    n-InP): optical-phonon, ionized-impurity and acoustic-phonon parts, scaled to other wavelengths with their eq. (2),
    lambda^2.5, lambda^3.5 and lambda^1.5. Impurity scattering grows faster than n, so sigma depends on N (about
    0.7e-18 cm^2 at 1.55 um and 1e18). The InP value is used for the lattice-matched alloys too.
N   (GaN, AlGaN, InGaN, AlN) electrons: phonon-assisted cross-section of E. Kioupakis, P. Rinke and
    C. G. Van de Walle, Appl. Phys. Express 3, 082101 (2010), Table I, light polarized in the c-plane (the
    VCSEL field of a c-plane device), 380-680 nm. About 0.6e-18 cm^2 at 450 nm, which matches the measurement
    of S. Pimputkar et al., J. Cryst. Growth 432, 49 (2015).
N   Mg-doped: most of the loss is absorption by holes bound to (activated, neutral) Mg acceptors, so N is the
    Mg concentration, not the free-hole density. Two literature values:
      "sizov"     (default, measured) D. Sizov, R. Bhat and C. Zah, J. Appl. Phys. 113, 203108 (2013):
                  about 1e-17 cm^2 per activated Mg, weakly wavelength and temperature dependent, isotropic.
      "kioupakis" (first principles) Kioupakis et al. (2010), Table I holes, c-plane polarization, applied to
                  free + acceptor-bound holes (0.9e-18 cm^2 at 450 nm, 1.4e-18 at 520 nm).
AlGaInP (estimate, interpolated between binaries as is common for this alloy; no direct measurement found):
    electrons: sigma = (1 - f) sigma_GaAs + f sigma_GaP with f = x / 0.51 (GaInP at x = 0, AlInP at x = 0.51), where
    sigma_GaAs = 3e-18 (lambda/870 nm)^2 (Casey 1978, Drude-like scaling) and sigma_GaP is n-GaP at 295 K from
    W. G. Spitzer, M. Gershenzon, C. J. Frosch and D. F. Gibbs, J. Phys. Chem. Solids 11, 339 (1959) (figure on the
    Ioffe NSM GaP page): about 40 cm^-1 at 1.2 um for n = 1e18, rising as lambda^1.56 toward the 3 um intervalley peak;
    extrapolated below 1.2 um with the same power. Indirect (X-valley) electrons absorb much more than in GaAs.
    holes: GaAs value 7e-18 (lambda/870 nm)^2 (no p-GaP data).
"""
from __future__ import annotations

import numpy as np

FAMILY = {
    "AlGaAs": "As", "AlGaAs_Gehrsitz": "As", "InGaAs": "As",
    "AlGaInP": "AlGaInP", "AlGaInP_Adachi": "AlGaInP",
    "InP": "P", "InGaAsP": "P", "InGaAsP_xy": "P", "InAlGaAs": "P",
    "GaN": "N", "AlGaN": "N", "InGaN": "N", "AlN": "N",
}

# Kioupakis et al., APEX 3, 082101 (2010), Table I, f_el-ph, light perpendicular to c; sigma/1e-18 cm^2 = sum a_n (lam/nm)^n
_K_E_PERP = (-2.629e1, 1.999e-1, -5.406e-4, 6.294e-7, -2.673e-10)
_K_H_PERP = (5.548, -5.631e-2, 2.035e-4, -3.060e-7, 1.794e-10)

# Walukiewicz et al., JAP 51, 2659 (1980), Table III, 300 K, lambda = 10 um: n (cm^-3), alpha_imp, alpha_ac, alpha_op (cm^-1)
_WAL_N = (1e16, 1.5e16, 2e16, 3e16, 4e16, 5e16, 6e16, 7e16, 8e16, 9e16, 1e17, 1.5e17, 2e17, 3e17, 4e17, 5e17, 6e17, 7e17,
          8e17, 9e17, 1e18, 1.5e18, 2e18, 3e18, 4e18, 5e18, 6e18)
_WAL_IMP = (0.004, 0.008, 0.014, 0.031, 0.056, 0.086, 0.123, 0.167, 0.217, 0.273, 0.314, 0.690, 1.201, 2.602, 4.474, 6.790,
            9.510, 12.64, 16.13, 20.00, 24.22, 50.28, 83.91, 170.3, 276.7, 396.1, 522.8)
_WAL_AC = (0.034, 0.052, 0.069, 0.104, 0.139, 0.173, 0.208, 0.243, 0.278, 0.313, 0.325, 0.491, 0.660, 1.005, 1.360, 1.726,
           2.100, 2.488, 2.879, 3.285, 3.699, 5.912, 8.354, 13.87, 20.12, 26.98, 34.34)
_WAL_OP = (0.623, 0.932, 1.239, 1.850, 2.456, 3.051, 3.646, 4.240, 4.815, 5.397, 5.578, 8.227, 10.79, 15.75, 20.52, 25.16,
           29.65, 34.11, 38.44, 42.75, 47.01, 67.80, 88.02, 127.0, 164.1, 199.6, 233.4)


def _loglog(n, xs, ys):
    lx, ly = np.log(xs), np.log(ys)
    ln = np.log(n)
    if ln >= lx[-1]:                                   # extend with the slope of the last interval
        return float(np.exp(ly[-1] + (ln - lx[-1]) * (ly[-1] - ly[-2]) / (lx[-1] - lx[-2])))
    return float(np.exp(np.interp(ln, lx, ly)))


def _sigma_n_inp(lam, N):
    """Electron cross-section (cm^2) in n-InP from Walukiewicz (1980), uncompensated, 300 K."""
    N = float(N) if N and N > 0 else 1e18
    N = max(N, _WAL_N[0])
    r = lam / 10000.0
    a = (_loglog(N, _WAL_N, _WAL_OP) * r ** 2.5 + _loglog(N, _WAL_N, _WAL_IMP) * r ** 3.5
         + _loglog(N, _WAL_N, _WAL_AC) * r ** 1.5)
    return a / N


# p-type InP family: (wavelength nm, alpha per 1e18 holes in cm^-1)
_IVBA_P = ((1300.0, 14.0), (1500.0, 20.0), (1600.0, 25.0))

REFS = {
    ("As", "n"): "Casey, J. Appl. Phys. 49, 3684 (1978), eq. 9 (3e-18 n + 7e-18 p)",
    ("As", "p"): "Casey, J. Appl. Phys. 49, 3684 (1978), eq. 9 (3e-18 n + 7e-18 p)",
    ("AlGaInP", "n"): "estimate: interpolated between GaAs (Casey 1978, × (λ/870 nm)²) and n-GaP (Spitzer et al. 1959, "
                      "extrapolated below 1.2 µm) by Al fraction x/0.51",
    ("AlGaInP", "p"): "estimate: GaAs value (Casey 1978) × (λ/870 nm)²",
    ("P", "n"): "Walukiewicz et al., J. Appl. Phys. 51, 2659 (1980): n-InP, 300 K, Table III scaled from 10 µm by eq. 2",
    ("P", "p"): "Casey & Carter, Appl. Phys. Lett. 44, 82 (1984); Henry et al., IEEE JQE 19, 947 (1983)",
    ("N", "n"): "Kioupakis et al., Appl. Phys. Express 3, 082101 (2010), E ⊥ c; matches Pimputkar et al., "
                "J. Cryst. Growth 432, 49 (2015)",
    ("N", "p", "sizov"): "Sizov et al., J. Appl. Phys. 113, 203108 (2013): ~1e-17 cm² per activated Mg (measured)",
    ("N", "p", "kioupakis"): "Kioupakis et al., Appl. Phys. Express 3, 082101 (2010): free + Mg-bound holes, "
                             "E ⊥ c (first principles)",
}

# selectable variants (first = default)
VARIANTS = {("N", "p"): [("sizov", "Measured, Sizov 2013"), ("kioupakis", "First principles, Kioupakis 2010")]}


def family(material):
    return FAMILY.get(material)


def variants(material, carrier):
    return VARIANTS.get((FAMILY.get(material), carrier), [])


def _variant(material, carrier, variant):
    opts = [v for v, _ in variants(material, carrier)]
    if not opts:
        return None
    return variant if variant in opts else opts[0]


def reference(material, carrier, variant=None):
    fam = FAMILY.get(material)
    v = _variant(material, carrier, variant)
    return REFS.get((fam, carrier, v) if v else (fam, carrier))


def _poly(coef, lam):
    lc = np.clip(lam, 380.0, 680.0)
    return sum(a * lc ** k for k, a in enumerate(coef)) * 1e-18


def sigma(material, carrier, wavelength_nm, variant=None, x=0.0, N=None):
    """Cross-section in cm^2 (array like wavelength) for carrier 'n' or 'p'; None if no model.
    N (cm^-3) matters only where sigma depends on doping (n-InP family); default 1e18."""
    fam = FAMILY.get(material)
    lam = np.asarray(wavelength_nm, dtype=float)
    if fam is None or carrier not in ("n", "p"):
        return None
    if fam == "As":
        return np.full_like(lam, 3e-18 if carrier == "n" else 7e-18)
    if fam == "AlGaInP":
        if carrier == "p":
            return 7e-18 * (lam / 870.0) ** 2
        f = min(max(float(x or 0.0) / 0.51, 0.0), 1.0)
        s_gaas = 3e-18 * (lam / 870.0) ** 2
        s_gap = 40e-18 * (np.minimum(lam, 2800.0) / 1200.0) ** 1.56
        return (1 - f) * s_gaas + f * s_gap
    if fam == "P":
        if carrier == "n":
            return _sigma_n_inp(lam, N)
        x, y = zip(*_IVBA_P)
        return np.interp(lam, x, y) * 1e-18          # held constant outside 1.3-1.6 um
    if fam == "N":
        if carrier == "n":
            return _poly(_K_E_PERP, lam)
        if _variant(material, carrier, variant) == "kioupakis":
            return _poly(_K_H_PERP, lam)
        return np.full_like(lam, 1e-17)
    return None


def carrier_of(layer_type):
    return {"n-type": "n", "p-type": "p"}.get(layer_type)


def alpha(layer, wavelength_nm):
    """Doping-induced absorption (cm^-1) of a layer, or 0 if the layer type / material has no model."""
    lam = np.asarray(wavelength_nm, dtype=float)
    c = carrier_of(layer.layer_type)
    N = float(layer.doping or 0.0)
    if c is None or N <= 0:
        return np.zeros_like(lam)
    s = layer.sigma_fc if layer.sigma_fc not in (None, "") else None
    if s is None:
        s = sigma(layer.material, c, lam, getattr(layer, "fca_model", None), layer.x, N)
        if s is None:
            return np.zeros_like(lam)
    return np.asarray(s, dtype=float) * N + np.zeros_like(lam)
