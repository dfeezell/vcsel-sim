"""Refractive-index database.

Every material is a function n(lambda_nm, x, y) -> complex index (k > 0 = loss)
plus metadata (composition labels, ranges, band gap, literature reference).
Models were chosen from classic, widely used references; each entry carries its
citation, and `catalog()` exposes them to the GUI's Materials tab.

Composition conventions
-----------------------
AlGaAs     Al(x)Ga(1-x)As
InGaAs     In(x)Ga(1-x)As
AlGaInP    (Al(x)Ga(1-x))0.51In0.49P   (lattice matched to GaAs)
InGaAsP    In(1-x)Ga(x)As(y)P(1-y)     (y = As fraction; x set for lattice match to InP if x<0)
InAlGaAs   In0.53(Al(x)Ga(1-x))0.47As  (lattice matched to InP)
AlGaN      Al(x)Ga(1-x)N   (wurtzite, ordinary index)
InGaN      In(x)Ga(1-x)N   (wurtzite, ordinary index)
"""
from __future__ import annotations

import numpy as np

from . import _tables as T

HC = 1239.841984  # eV nm


# ---------------------------------------------------------------------------
# generic dispersion helpers
# ---------------------------------------------------------------------------
def _E(lam_nm):
    return HC / np.asarray(lam_nm, dtype=float)


def _um(lam_nm):
    return np.asarray(lam_nm, dtype=float) / 1000.0


def afromowitz(E, E0, Ed, Eg):
    """Modified single-effective-oscillator (MSEO) model,
    M. A. Afromowitz, Solid State Commun. 15, 59-63 (1974):
        n^2 = 1 + Ed/E0 + Ed E^2/E0^3 + (eta/pi) E^4 ln[(2E0^2 - Eg^2 - E^2)/(Eg^2 - E^2)]
        eta = pi Ed / (2 E0^3 (E0^2 - Eg^2))
    Above the gap the logarithm becomes complex, which gives the model's (approximate)
    band-to-band absorption, as in Vertical."""
    eta = np.pi * Ed / (2 * E0 ** 3 * (E0 ** 2 - Eg ** 2))
    arg = (2 * E0 ** 2 - Eg ** 2 - E ** 2) / (Eg ** 2 - E ** 2 + 0j)
    n2 = 1 + Ed / E0 + Ed * E ** 2 / E0 ** 3 + eta / np.pi * E ** 4 * np.log(arg)
    n = np.sqrt(n2 + 0j)
    # choose the branch with k >= 0 (loss) for our exp(-i w t) convention
    return np.real(n) + 1j * np.abs(np.imag(n))


def wemple(E, E0, Ed):
    """Wemple-DiDomenico single oscillator: n^2 - 1 = E0 Ed / (E0^2 - E^2)."""
    return np.sqrt(1 + E0 * Ed / (E0 ** 2 - E ** 2) + 0j)


def sellmeier_ri1(lam_um, c):
    """refractiveindex.info 'formula 1': n^2 - 1 = c0 + sum c_i l^2/(l^2 - c_{i+1}^2)."""
    l2 = lam_um ** 2
    n2 = 1 + c[0]
    for i in range(1, len(c) - 1, 2):
        n2 = n2 + c[i] * l2 / (l2 - c[i + 1] ** 2)
    return np.sqrt(n2 + 0j)


def _table(tab, lam_nm):
    lam = _um(lam_nm)
    wl, n, k = (np.asarray(v, float) for v in tab)
    return np.interp(lam, wl, n) + 1j * np.interp(lam, wl, k)


# ---------------------------------------------------------------------------
# III-As on GaAs
# ---------------------------------------------------------------------------
def eg_algaas(x):
    return 1.424 + 1.266 * x + 0.26 * x * x   # direct (Gamma) gap, Afromowitz / Casey & Panish


def algaas(lam, x, y=0.0):
    E0 = 3.65 + 0.871 * x + 0.179 * x * x
    Ed = 36.1 - 2.45 * x
    return afromowitz(_E(lam), E0, Ed, eg_algaas(x))


def eg_ingaas(x):
    return 1.425 - 1.337 * x + 0.270 * x * x   # Takagi (1978)


def ingaas(lam, x, y=0.0):
    """Takagi, Jpn. J. Appl. Phys. 17, 1813 (1978): Wemple-DiDomenico oscillator with
    E0 = 3.65 - 2.15x, Ed = 36.1 - 19.9x (eV). Real index only (used for QWs)."""
    E0 = 3.65 - 2.15 * x
    Ed = 36.1 - 19.9 * x
    n = wemple(_E(lam), E0, Ed)
    return np.real(n) + 0j


# ---------------------------------------------------------------------------
# InP-based
# ---------------------------------------------------------------------------
def eg_ingaasp(y, _=0.0):
    return 1.35 - 0.72 * y + 0.12 * y * y     # 300 K, lattice matched to InP


def ingaasp(lam, y, _unused=0.0):
    """In(1-x)Ga(x)As(y)P(1-y) lattice matched to InP, MSOM of
    H. Fiedler and A. Schlachetzki, Solid-State Electron. 30, 73 (1987):
        E0 = 3.391 - 1.652y + 0.863y^2 - 0.123y^3,  Ed = 28.91 - 9.278y + 5.626y^2,
        Eg = 1.35 - 0.72y + 0.12y^2 (eV), inserted in the Afromowitz form."""
    E0 = 3.391 - 1.652 * y + 0.863 * y ** 2 - 0.123 * y ** 3
    Ed = 28.91 - 9.278 * y + 5.626 * y ** 2
    return afromowitz(_E(lam), E0, Ed, eg_ingaasp(y))


def inp(lam, x=0.0, y=0.0):
    """InP: Sellmeier from Handbook of Optics (data of G. D. Pettit & W. J. Turner,
    J. Appl. Phys. 36, 2081 (1965)), valid 0.95-10 um."""
    return np.real(sellmeier_ri1(_um(lam), [6.255, 2.316, 0.6263, 2.765, 32.935])) + 0j


# ---------------------------------------------------------------------------
# Nitrides
# ---------------------------------------------------------------------------
def gan(lam, x=0.0, y=0.0):
    """A. S. Barker Jr. & M. Ilegems, Phys. Rev. B 7, 743 (1973), ordinary ray, 0.35-10 um."""
    return np.real(sellmeier_ri1(_um(lam), [2.60, 1.75, 0.256, 4.1, 17.86])) + 0j


def aln(lam, x=0.0, y=0.0):
    """J. Pastrnak & L. Roskovcova, Phys. Stat. Sol. 14, K5 (1966), ordinary ray, 0.22-5 um."""
    return np.real(sellmeier_ri1(_um(lam), [2.1399, 1.3786, 0.1715, 3.861, 15.03])) + 0j


# Ternary nitrides: Adachi (1982) form n^2 = a (E/Eg)^-2 [2 - sqrt(1+E/Eg) - sqrt(1-E/Eg)] + b
# with binary parameters (Table 2) and alloy bowing (Table 3) of A. Alam, V. Z. Zubialevich, B. Ghafary,
# P. J. Parbrook, Sci. Rep. 10, 16205 (2020). Parameters are interpolated in the reduced band gap
# xi = (Eg_alloy - Eg_B)/(Eg_A - Eg_B), as in that paper.
_NIT = {"GaN": (3.438, 10.1, 2.67), "AlN": (6.24, 17.6, -0.3), "InN": (0.65, 9.4, 5.0)}  # Eg(apparent), a, b


def _adachi_nitride(E, Eg, a, b):
    chi = E / Eg
    f = chi ** -2 * (2 - np.sqrt(1 + chi + 0j) - np.sqrt(1 - chi + 0j))
    n = np.sqrt(a * f + b + 0j)
    return np.real(n) + 1j * np.abs(np.imag(n))


def eg_algan(x, _=0.0):
    return 6.015 * x + 3.438 * (1 - x) - 0.94 * x * (1 - x)   # bowing 0.94 eV (Alam et al. 2020, ref. 21)


def eg_ingan(x, _=0.0):
    return 0.65 * x + 3.438 * (1 - x) - 1.4 * x * (1 - x)     # bowing 1.4 eV (Vurgaftman & Meyer 2003)


def algan(lam, x, y=0.0):
    EgA, aA, bA = _NIT["AlN"]; EgB, aB, bB = _NIT["GaN"]
    Eg = EgA * x + EgB * (1 - x) - 0.94 * x * (1 - x)          # apparent (E perp c) gap for the index model
    xi = (Eg - EgB) / (EgA - EgB)
    a = aA * xi + aB * (1 - xi) - 4.3 * xi * (1 - xi)
    b = bA * xi + bB * (1 - xi) + 0.7 * xi * (1 - xi)          # beta_b = -0.7
    return _adachi_nitride(_E(lam), Eg, a, b)


def ingan(lam, x, y=0.0):
    EgA, aA, bA = _NIT["InN"]; EgB, aB, bB = _NIT["GaN"]
    Eg = eg_ingan(x)
    xi = (Eg - EgB) / (EgA - EgB)
    a = aA * xi + aB * (1 - xi)                                 # no parameter bowing (recommended for InGaN)
    b = bA * xi + bB * (1 - xi)
    return _adachi_nitride(_E(lam), Eg, a, b)


# ---------------------------------------------------------------------------
# Dielectrics, oxides, metals
# ---------------------------------------------------------------------------
def sio2(lam, x=0.0, y=0.0):
    """I. H. Malitson, J. Opt. Soc. Am. 55, 1205 (1965), fused silica."""
    return np.real(sellmeier_ri1(_um(lam), [0, 0.6961663, 0.0684043, 0.4079426, 0.1162414, 0.8974794, 9.896161])) + 0j


def si3n4(lam, x=0.0, y=0.0):
    """K. Luke et al., Opt. Lett. 40, 4823 (2015), LPCVD Si3N4."""
    return np.real(sellmeier_ri1(_um(lam), [0, 3.0249, 0.1353406, 40314, 1239.842])) + 0j


def al2o3_sapphire(lam, x=0.0, y=0.0):
    """I. H. Malitson & M. J. Dodge, J. Opt. Soc. Am. 62, 1405 (1972), sapphire ordinary ray."""
    return np.real(sellmeier_ri1(_um(lam), [0, 1.4313493, 0.0726631, 0.65054713, 0.1193242, 5.3414021, 18.028251])) + 0j


def tio2_rutile(lam, x=0.0, y=0.0):
    """J. R. DeVore, J. Opt. Soc. Am. 41, 416 (1951), rutile ordinary: n^2 = 5.913 + 0.2441/(l^2 - 0.0803)."""
    l2 = _um(lam) ** 2
    return np.sqrt(5.913 + 0.2441 / (l2 - 0.0803)) + 0j


def hfo2(lam, x=0.0, y=0.0):
    """M. F. Al-Kuhaili, Opt. Mater. 27, 383 (2004), e-beam film: n = 1.875 + 6.28e-3/l^2 + 5.80e-4/l^4."""
    l = _um(lam)
    return 1.875 + 6.28e-3 / l ** 2 + 5.80e-4 / l ** 4 + 0j


def constant(value):
    def f(lam, x=0.0, y=0.0):
        return np.full(np.shape(np.asarray(lam, float)), complex(value))
    return f


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
MATERIALS = {}


def register(key, fn, label, category, x_label=None, y_label=None, x_range=(0, 1), y_range=(0, 1),
             bandgap=None, reference="", notes="", valid_nm=None, default_type="undoped"):
    MATERIALS[key] = dict(key=key, fn=fn, label=label, category=category, x_label=x_label, y_label=y_label,
                          x_range=x_range, y_range=y_range, bandgap=bandgap, reference=reference, notes=notes,
                          valid_nm=valid_nm, default_type=default_type)


register("AlGaAs", algaas, "AlxGa1-xAs", "GaAs-based", "x (Al)", None, bandgap=eg_algaas,
         reference="M. A. Afromowitz, Solid State Commun. 15, 59 (1974). Same model as Vertical "
                   "(reproduces Vertical's GaAs/Al0.2GaAs/AlAs indices to 1e-5).",
         notes="Modified single-oscillator model; complex above the band gap (approximate absorption). "
               "x = 0 is GaAs, x = 1 is AlAs.")
register("InGaAs", ingaas, "InxGa1-xAs", "GaAs-based", "x (In)", None, x_range=(0, 0.5), bandgap=eg_ingaas,
         reference="M. Takagi, Jpn. J. Appl. Phys. 17, 1813 (1978) (Wemple-DiDomenico parameters). "
                   "Same model as Vertical (In0.2GaAs: 3.57717 at 980 nm).",
         notes="Real index only; typically used for strained quantum wells on GaAs. Band gap is the "
               "unstrained bulk value (Takagi).", default_type="active")
register("InGaAsP", ingaasp, "InGaAsP / InP (lattice matched)", "InP-based", "y (As)", None,
         bandgap=eg_ingaasp,
         reference="H. Fiedler and A. Schlachetzki, Solid-State Electron. 30, 73 (1987) (MSOM parameters); "
                   "Eg = 1.35 - 0.72y + 0.12y^2 (Nahory et al.).",
         notes="In(1-x)Ga(x)As(y)P(1-y) lattice matched to InP, x ~ y/2.2. y = 0 is InP, y = 1 is In0.53Ga0.47As. "
               "Complex above the band gap (approximate).")
register("InP", inp, "InP", "InP-based",
         reference="Handbook of Optics Vol. 2 (1994) Sellmeier, data of G. D. Pettit and W. J. Turner, "
                   "J. Appl. Phys. 36, 2081 (1965).", notes="Valid 950 nm - 10 um.", valid_nm=(950, 10000),
         bandgap=lambda x=0, y=0: 1.344)
register("GaN", gan, "GaN", "Nitrides", reference="A. S. Barker Jr. and M. Ilegems, Phys. Rev. B 7, 743 (1973).",
         notes="Wurtzite, ordinary ray (TE, normal incidence). Valid 350 nm - 10 um.", valid_nm=(350, 10000),
         bandgap=lambda x=0: 3.42 + 0 * x)
register("AlN", aln, "AlN", "Nitrides", reference="J. Pastrnak and L. Roskovcova, Phys. Stat. Sol. 14, K5 (1966).",
         notes="Wurtzite, ordinary ray. Valid 220 nm - 5 um.", valid_nm=(220, 5000), bandgap=lambda x=0: 6.0 + 0 * x)
register("AlGaN", algan, "AlxGa1-xN", "Nitrides", "x (Al)", None, bandgap=eg_algan,
         reference="Adachi (1982) model with binary and bowing parameters of A. Alam et al., Sci. Rep. 10, 16205 (2020); "
                   "Eg bowing 0.94 eV.",
         notes="Wurtzite, ordinary (E perp c) index. Valid below the band gap; the value above the gap is not physical.")
register("InGaN", ingan, "InxGa1-xN", "Nitrides", "x (In)", None, x_range=(0, 0.4), bandgap=eg_ingan,
         reference="Adachi (1982) model with parameters of A. Alam et al., Sci. Rep. 10, 16205 (2020); "
                   "Eg bowing 1.4 eV (I. Vurgaftman and J. R. Meyer, J. Appl. Phys. 94, 3675 (2003)).",
         notes="Wurtzite, ordinary index, below the band gap. Typically used for QWs (use Layer type = active).",
         default_type="active")
register("SiO2", sio2, "SiO2", "Dielectrics", reference="I. H. Malitson, J. Opt. Soc. Am. 55, 1205 (1965).",
         notes="Fused silica bulk. Deposited films may differ by ~0.01-0.02.", default_type="dielectric")
register("Si3N4", si3n4, "Si3N4", "Dielectrics", reference="K. Luke et al., Opt. Lett. 40, 4823 (2015).",
         notes="Stoichiometric LPCVD film. PECVD SiNx is often 1.9-2.0 (use a fixed index).", default_type="dielectric")
register("Ta2O5", lambda lam, x=0, y=0: _table(T.TA2O5, lam), "Ta2O5", "Dielectrics",
         reference="L. Gao, F. Lemarchand, M. Lequime, Opt. Express 20, 15734 (2012).",
         notes="Ion-assisted e-beam film, tabulated 350-1800 nm.", valid_nm=(350, 1800), default_type="dielectric")
register("TiO2", lambda lam, x=0, y=0: _table(T.TIO2, lam), "TiO2 (film)", "Dielectrics",
         reference="T. Siefke et al., Adv. Opt. Mater. 4, 1780 (2016) (ALD film).",
         notes="Amorphous/ALD film, tabulated. For bulk rutile use 'TiO2 rutile'.", default_type="dielectric")
register("TiO2_rutile", tio2_rutile, "TiO2 rutile", "Dielectrics",
         reference="J. R. DeVore, J. Opt. Soc. Am. 41, 416 (1951).", notes="Bulk rutile, ordinary ray, 430-1530 nm.",
         valid_nm=(430, 1530), default_type="dielectric")
register("HfO2", hfo2, "HfO2", "Dielectrics", reference="M. F. Al-Kuhaili, Opt. Mater. 27, 383 (2004).",
         notes="E-beam film, Cauchy, 200-2000 nm.", valid_nm=(200, 2000), default_type="dielectric")
register("Nb2O5", lambda lam, x=0, y=0: _table(T.NB2O5, lam), "Nb2O5", "Dielectrics",
         reference="F. Lemarchand (2013), method in L. Gao et al., Opt. Express 20, 15734 (2012).",
         notes="Magnetron-sputtered film, tabulated 300-2500 nm.", default_type="dielectric")
register("Al2O3", al2o3_sapphire, "Al2O3 sapphire", "Dielectrics",
         reference="I. H. Malitson and M. J. Dodge, J. Opt. Soc. Am. 62, 1405 (1972).", notes="Sapphire, ordinary ray.",
         default_type="dielectric")
register("Al2O3_film", lambda lam, x=0, y=0: _table(T.AL2O3_FILM, lam), "Al2O3 (film)", "Dielectrics",
         reference="R. Boidin et al., Ceramics International 42, 1177 (2016).", notes="Amorphous PLD film.",
         default_type="dielectric")
register("AlOx", constant(1.60), "AlOx (oxidised AlGaAs)", "Dielectrics",
         reference="Typical value for wet-oxidised Al(0.98)GaAs, n ~ 1.55-1.65 (e.g. Choquette et al., "
                   "IEEE JSTQE 3, 916 (1997)).",
         notes="Constant n = 1.60. Use a fixed index if you have a measured value for your process.",
         default_type="oxide")
register("Air", constant(1.0), "Air / vacuum", "Other", reference="n = 1", default_type="other")
register("Generic", constant(3.5), "Generic (fixed index)", "Other",
         reference="User-defined", notes="Set Index source = Fixed and enter n and k.", default_type="other")
register("Au", lambda lam, x=0, y=0: _table(T.AU, lam), "Au", "Metals",
         reference="P. B. Johnson and R. W. Christy, Phys. Rev. B 6, 4370 (1972).", default_type="metal")
register("Ag", lambda lam, x=0, y=0: _table(T.AG, lam), "Ag", "Metals",
         reference="P. B. Johnson and R. W. Christy, Phys. Rev. B 6, 4370 (1972).", default_type="metal")
register("Ti", lambda lam, x=0, y=0: _table(T.TI, lam), "Ti", "Metals",
         reference="P. B. Johnson and R. W. Christy, Phys. Rev. B 9, 5056 (1974).", default_type="metal")
register("Cr", lambda lam, x=0, y=0: _table(T.CR, lam), "Cr", "Metals",
         reference="P. B. Johnson and R. W. Christy, Phys. Rev. B 9, 5056 (1974).", default_type="metal")
register("Pt", lambda lam, x=0, y=0: _table(T.PT, lam), "Pt", "Metals",
         reference="W. S. M. Werner, K. Glantschnig, C. Ambrosch-Draxl, J. Phys. Chem. Ref. Data 38, 1013 (2009).",
         default_type="metal")


def index(material, lam, x=0.0, y=0.0):
    if material not in MATERIALS:
        raise KeyError(f"Unknown material '{material}'")
    return np.asarray(MATERIALS[material]["fn"](lam, float(x), float(y)), dtype=complex)


def bandgap(material, x=0.0, y=0.0):
    f = MATERIALS[material].get("bandgap")
    if f is None:
        return None
    try:
        return float(f(x, y))
    except TypeError:
        return float(f(x))


def catalog():
    out = []
    for k, m in MATERIALS.items():
        out.append({kk: vv for kk, vv in m.items() if kk not in ("fn", "bandgap")} | {"has_bandgap": m["bandgap"] is not None})
    return out
