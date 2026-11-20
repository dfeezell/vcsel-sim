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
P   electrons (interim): n-GaAs at 1.5 um, 4e-18 cm^2 (D. C. Look et al., Appl. Phys. Lett. 65, 2188 (1994), as
    quoted in D. K. Schroder, Semiconductor Material and Device Characterization, eq. 2.63).
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

# p-type InP family: (wavelength nm, alpha per 1e18 holes in cm^-1)
_IVBA_P = ((1300.0, 14.0), (1500.0, 20.0), (1600.0, 25.0))

REFS = {
    ("As", "n"): "Casey, J. Appl. Phys. 49, 3684 (1978), eq. 9 (3e-18 n + 7e-18 p)",
    ("As", "p"): "Casey, J. Appl. Phys. 49, 3684 (1978), eq. 9 (3e-18 n + 7e-18 p)",
    ("AlGaInP", "n"): "estimate: interpolated between GaAs (Casey 1978, × (λ/870 nm)²) and n-GaP (Spitzer et al. 1959, "
                      "extrapolated below 1.2 µm) by Al fraction x/0.51",
    ("AlGaInP", "p"): "estimate: GaAs value (Casey 1978) × (λ/870 nm)²",
    ("P", "n"): "interim: n-GaAs at 1.5 µm (Look et al., Appl. Phys. Lett. 65, 2188 (1994))",
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


def sigma(material, carrier, wavelength_nm, variant=None, x=0.0):
    """Cross-section in cm^2 (array like wavelength) for carrier 'n' or 'p'; None if no model."""
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
            return np.full_like(lam, 4e-18)
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
        s = sigma(layer.material, c, lam, getattr(layer, "fca_model", None), layer.x)
        if s is None:
            return np.zeros_like(lam)
    return np.asarray(s, dtype=float) * N + np.zeros_like(lam)
