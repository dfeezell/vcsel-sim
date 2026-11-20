"""Free-carrier (doping-induced) absorption: alpha = sigma * N.

Optional per-layer model ("absorption from doping"). A layer that uses it gets
alpha = sigma_n * N for n-type or sigma_p * N for p-type layers, where N is the
layer's doping (cm^-3) and sigma (cm^2) is the literature cross-section for
the material family at the wavelength. Manual alpha stays the default.

Sources
-------
As  (AlGaAs, InGaAs):  H. C. Casey, Jr., J. Appl. Phys. 49, 3684 (1978), eq. (9):
    alpha_fc = 3e-18 n + 7e-18 p cm^-1 for GaAs near the band gap (room temperature);
    Casey applies the same loss to the AlGaAs cladding.
P   (InP, InGaAsP, InAlGaAs) holes: H. C. Casey, Jr. and P. L. Carter, Appl. Phys. Lett. 44, 82 (1984):
    alpha = 14 (p/1e18) cm^-1 at 1.3 um and 20 (p/1e18) cm^-1 at 1.5 um (intervalence band absorption,
    297 K), interpolated linearly in wavelength. J. Taylor and V. Tolstikhin, J. Appl. Phys. 87, 1054 (2000)
    reproduce these values with a 6x6 Luttinger-Kohn model.
P   electrons (interim): n-GaAs at 1.5 um, 4e-18 cm^2 (D. C. Look et al., Appl. Phys. Lett. 65, 2188 (1994),
    as quoted in D. K. Schroder, Semiconductor Material and Device Characterization, eq. 2.63) until an
    InP-specific value is added.
N   (GaN, AlGaN, InGaN) electrons: S. Pimputkar et al., J. Cryst. Growth 432, 49 (2015): alpha at 450 nm rises
    linearly to 5.2 cm^-1 at n = 9e18 (sigma ~ 0.6e-18 cm^2), in agreement with the first-principles
    phonon-assisted absorption of E. Kioupakis et al., Phys. Rev. B 81, 241201(R) (2010).
N   Mg-doped (interim): Kioupakis et al. (2010) find ~12 cm^-1 for [Mg] = 2e19 cm^-3 (green), dominated by holes
    bound to Mg, so the p-type value is per Mg atom (enter the Mg concentration as the doping): 0.6e-18 cm^2.
AlGaInP (estimate): the GaAs values scaled by (lambda / 870 nm)^2 (Drude-like free-carrier scaling); no
    dedicated measurement has been added yet.
"""
from __future__ import annotations

import numpy as np

FAMILY = {
    "AlGaAs": "As", "AlGaAs_Gehrsitz": "As", "InGaAs": "As",
    "AlGaInP": "AlGaInP", "AlGaInP_Adachi": "AlGaInP",
    "InP": "P", "InGaAsP": "P", "InGaAsP_xy": "P", "InAlGaAs": "P",
    "GaN": "N", "AlGaN": "N", "InGaN": "N", "AlN": "N",
}

REFS = {
    "As": "Casey, J. Appl. Phys. 49, 3684 (1978), eq. 9: 3e-18 n + 7e-18 p cm^-1",
    "AlGaInP": "estimate: GaAs values (Casey 1978) scaled by (lambda/870 nm)^2",
    "P": "holes: Casey & Carter, Appl. Phys. Lett. 44, 82 (1984); electrons (interim): n-GaAs at 1.5 um, "
         "Look et al., Appl. Phys. Lett. 65, 2188 (1994)",
    "N": "electrons: Pimputkar et al., J. Cryst. Growth 432, 49 (2015) and Kioupakis et al., Phys. Rev. B 81, "
         "241201(R) (2010); Mg (interim, per Mg atom): Kioupakis et al. (2010)",
}


def family(material):
    return FAMILY.get(material)


def sigma(material, carrier, wavelength_nm):
    """Cross-section in cm^2 (array like wavelength) for carrier 'n' or 'p'; None if no model."""
    fam = FAMILY.get(material)
    lam = np.asarray(wavelength_nm, dtype=float)
    if fam is None or carrier not in ("n", "p"):
        return None
    if fam == "As":
        return np.full_like(lam, 3e-18 if carrier == "n" else 7e-18)
    if fam == "AlGaInP":
        return (3e-18 if carrier == "n" else 7e-18) * (lam / 870.0) ** 2
    if fam == "P":
        if carrier == "n":
            return np.full_like(lam, 4e-18)
        lc = np.clip(lam, 1250.0, 1650.0)
        return (14.0 + (lc - 1300.0) * (6.0 / 200.0)) * 1e-18
    if fam == "N":
        return np.full_like(lam, 0.6e-18)
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
        s = sigma(layer.material, c, lam)
        if s is None:
            return np.zeros_like(lam)
    return np.asarray(s, dtype=float) * N + np.zeros_like(lam)
