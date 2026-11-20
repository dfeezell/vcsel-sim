"""Layer-stack data model.

A design is a tree: the stack is a list of items ordered from the TOP of the
wafer (just below the exit medium) down to the substrate. Each item is either a
`Layer` or a `Group`; a group holds its own ordered list (top to bottom) and a
repetition count, so DBRs and multi-quantum-well active regions are a group of
two layers repeated N times.

Everything here is plain data with `to_dict` / `from_dict` so a design can be
saved as JSON (the native ".vcsel.json" format) and passed between the browser
and the Python engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union
import copy

import numpy as np

from . import materials, fca

# Layer "type" values (mirrors Vertical's Layer Type list, plus dielectric types)
LAYER_TYPES = ["undoped", "n-type", "p-type", "active", "dielectric", "oxide", "metal", "other"]

# Group roles. Roles tell the analysis which parts are mirrors / cavity.
GROUP_ROLES = ["none", "top_dbr", "bottom_dbr", "active"]


@dataclass
class Layer:
    name: str = "GaAs"
    material: str = "AlGaAs"         # key into materials.MATERIALS
    x: float = 0.0                    # first composition fraction (meaning depends on material)
    y: float = 0.0                    # second composition fraction
    thickness: float = 0.25           # value in `thickness_unit`
    thickness_unit: str = "waves"     # "nm" or "waves" (optical thickness in units of design wavelength)
    index_mode: str = "model"         # "model" -> materials database, "fixed" -> use n_real/n_imag
    n_real: float = 3.5
    n_imag: float = 0.0               # extinction coefficient kappa (>0 = loss), added to model value
    absorption: float = 0.0           # power absorption coefficient alpha in cm^-1 (>0 loss, <0 gain)
    layer_type: str = "undoped"       # see LAYER_TYPES; "active" layers receive the threshold gain
    doping: float = 0.0               # cm^-3 (magnitude); for Mg-doped nitrides the Mg concentration
    absorption_mode: str = "manual"   # "manual" -> `absorption`; "doping" -> alpha = sigma * doping (see fca.py)
    sigma_fc: Optional[float] = None  # cm^2, overrides the literature cross-section in "doping" mode
    fca_model: str = ""               # literature variant where several exist (see fca.VARIANTS); "" = default
    apertured: bool = False           # reserved for the 2D (aperture) phase
    marked: bool = False              # thickness is adjusted by "Tune cavity" (Vertical's Marks / Force Wave)
    color: Optional[str] = None
    kind: str = "layer"

    # ---- optics -------------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self.layer_type == "active"

    def index(self, wavelength_nm, gain_cm=0.0):
        """Complex refractive index n + i*kappa at wavelength(s) in nm.

        Convention: fields vary as exp(i(kz - wt)), so kappa > 0 is loss.
        `absorption` (cm^-1) and, for active layers, a material gain `gain_cm`
        are converted to kappa = alpha * lambda / (4 pi).
        """
        lam = np.asarray(wavelength_nm, dtype=float)
        if self.index_mode == "fixed":
            n = np.full_like(lam, self.n_real, dtype=complex) + 1j * self.n_imag
        else:
            n = materials.index(self.material, lam, self.x, self.y) + 1j * self.n_imag
        alpha = self.alpha(lam) - (gain_cm if self.is_active else 0.0)
        if np.any(alpha != 0):
            n = n + 1j * alpha * 1e-7 * lam / (4 * np.pi)   # alpha [cm^-1] -> [nm^-1]
        return n

    def alpha(self, wavelength_nm):
        """Background power absorption coefficient (cm^-1) at wavelength(s): the manual value, or the
        doping-induced free-carrier absorption when absorption_mode == "doping" (active layers stay manual)."""
        if self.absorption_mode == "doping" and not self.is_active:
            return fca.alpha(self, wavelength_nm)
        return np.zeros_like(np.asarray(wavelength_nm, dtype=float)) + float(self.absorption or 0.0)

    def physical_thickness(self, design_wavelength_nm) -> float:
        """Thickness in nm. 'waves' means optical thickness n*d in units of the design wavelength."""
        if self.thickness_unit == "nm":
            return float(self.thickness)
        # Layers given in waves are grown once: convert them at the reference temperature so that changing the
        # structure temperature changes the index of a fixed physical layer (thermal tuning) rather than the layer.
        t_now = materials.TEMPERATURE_C
        materials.set_temperature(materials.REFERENCE_TEMPERATURE_C)
        try:
            n = float(np.real(self.index(design_wavelength_nm)))
        finally:
            materials.set_temperature(t_now)
        return float(self.thickness) * design_wavelength_nm / n

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        d = dict(d)
        d.pop("kind", None)
        known = {f for f in Layer.__dataclass_fields__}
        return Layer(**{k: v for k, v in d.items() if k in known})


GRADING_PROFILES = ["none", "linear", "biparabolic"]


@dataclass
class Group:
    name: str = "Group"
    repeats: int = 1
    children: List[Union["Layer", "Group"]] = field(default_factory=list)
    role: str = "none"
    apertured: bool = False
    color: Optional[str] = None
    # Graded interfaces between the layers of a periodic group (DBR), see graded_periods():
    # {"profile": "linear" | "biparabolic" | "none", "thickness_nm": 20, "steps": 10, "keep_period": True}
    grading: Optional[dict] = None
    kind: str = "group"

    def to_dict(self):
        d = {"kind": "group", "name": self.name, "repeats": self.repeats, "role": self.role,
             "apertured": self.apertured, "color": self.color,
             "children": [c.to_dict() for c in self.children]}
        if self.grading:
            d["grading"] = dict(self.grading)
        return d

    @staticmethod
    def from_dict(d):
        return Group(name=d.get("name", "Group"), repeats=int(d.get("repeats", 1)),
                     role=d.get("role", "none"), apertured=bool(d.get("apertured", False)),
                     color=d.get("color"), grading=d.get("grading") or None,
                     children=[item_from_dict(c) for c in d.get("children", [])])

    @property
    def is_graded(self) -> bool:
        g = self.grading or {}
        return (g.get("profile", "none") not in ("none", "", None) and float(g.get("thickness_nm", 0) or 0) > 0
                and int(self.repeats) >= 1 and len(self.children) >= 2
                and all(isinstance(c, Layer) for c in self.children))


# ---------------------------------------------------------------- graded interfaces
def _grade_shape(profile, t):
    """Fraction of the way from layer A to layer B at relative position t (0..1) through the grade."""
    if profile == "biparabolic":            # two parabolas, zero slope at both ends (S-shaped)
        return 2 * t * t if t < 0.5 else 1 - 2 * (1 - t) ** 2
    return t                                # linear


def _n_ref(L: "Layer", lam):
    """Real index at the design wavelength and the reference temperature (as used for 'waves')."""
    t_now = materials.TEMPERATURE_C
    materials.set_temperature(materials.REFERENCE_TEMPERATURE_C)
    try:
        return float(np.real(np.atleast_1d(L.index(lam))[0]))
    finally:
        materials.set_temperature(t_now)


def can_grade(A: "Layer", B: "Layer") -> bool:
    """A composition grade needs the same alloy model on both sides, with an index from the model."""
    return (A.material == B.material and A.index_mode == "model" and B.index_mode == "model"
            and materials.MATERIALS.get(A.material, {}).get("x_label") is not None)


def graded_periods(g: Group, lam):
    """Expand a graded periodic group into explicit layers.

    Every interface inside the group (between the layers of one period and between one period and
    the next) is replaced by a composition grade of total thickness g, centred on the original
    interface: each neighbouring layer gives up g/2. The outer faces of the group stay abrupt.
    The grade is drawn as `steps` sub-layers whose composition follows the profile (linear or
    bi-parabolic) between the two layers' compositions; doping, absorption and layer type come from
    the nearer layer. With keep_period (default) the uniform parts of all layers are scaled by one
    common factor so that the optical thickness of a full period at the design wavelength is the same
    as without grading, which keeps the Bragg wavelength in place.

    Returns a list of periods; each is a list of (Layer, thickness_nm, label).
    Raises ValueError when a grade is thicker than a layer can give up.
    """
    gd = g.grading or {}
    prof = gd.get("profile", "linear")
    gt = float(gd.get("thickness_nm", 0) or 0)
    ns = max(int(gd.get("steps", 10) or 10), 1)
    keep = bool(gd.get("keep_period", True))
    kids = list(g.children)
    m, N = len(kids), max(int(g.repeats), 0)
    d0 = [k.physical_thickness(lam) for k in kids]
    # which interfaces can be graded: i -> between kids[i] and kids[(i+1) % m]
    ok = [can_grade(kids[i], kids[(i + 1) % m]) for i in range(m)]
    if not any(ok):
        raise ValueError(f"group '{g.name}': grading needs layers of the same alloy (e.g. AlGaAs) on both sides")

    def steps(i):
        A, B = kids[i], kids[(i + 1) % m]
        out = []
        for j in range(ns):
            t = (j + 0.5) / ns
            f = _grade_shape(prof, t)
            src = A if t < 0.5 else B
            L = copy.deepcopy(src)
            L.x = float(A.x + (B.x - A.x) * f)
            L.y = float(A.y + (B.y - A.y) * f)
            L.thickness, L.thickness_unit, L.marked = gt / ns, "nm", False
            L.name = f"{A.name}→{B.name} grade {j + 1}/{ns}"
            out.append((L, gt / ns, f"grade {A.name}→{B.name} {j + 1}/{ns}"))
        return out

    # scale factor for the uniform parts (from a full interior period)
    cut = [(gt / 2 if ok[i - 1] else 0) + (gt / 2 if ok[i] else 0) for i in range(m)]
    for i in range(m):
        if d0[i] - cut[i] <= 0:
            raise ValueError(f"group '{g.name}': a {gt:g} nm grade is too thick for layer '{kids[i].name}' ({d0[i]:.1f} nm)")
    f = 1.0
    if keep:
        n0 = [_n_ref(k, lam) for k in kids]
        ot_orig = sum(n0[i] * d0[i] for i in range(m))
        ot_uni = sum(n0[i] * (d0[i] - cut[i]) for i in range(m))
        ot_gr = sum(_n_ref(L, lam) * d for i in range(m) if ok[i] for (L, d, _) in steps(i))
        if ot_uni > 0:
            f = (ot_orig - ot_gr) / ot_uni
    gsteps = [steps(i) if ok[i] else [] for i in range(m)]
    periods = []
    for k in range(N):
        first, last = k == 0, k == N - 1
        per = []
        for i in range(m):
            top_cut = gt / 2 if (ok[i - 1] and (i > 0 or not first)) else 0.0
            bot_cut = gt / 2 if (ok[i] and (i < m - 1 or not last)) else 0.0
            L = copy.deepcopy(kids[i])
            # uniform part, scaled; edge layers keep their unscaled outer half
            d = (d0[i] - cut[i]) * f + (cut[i] - top_cut - bot_cut)
            L.thickness, L.thickness_unit = d, "nm"
            per.append((L, d, kids[i].name))
            if i < m - 1 or not last:
                per += gsteps[i]
        periods.append(per)
    return periods


def ungraded_equivalent(g: Group, lam) -> Group:
    """The same layers as a graded group, written as plain groups of explicit layers (first period,
    the identical interior periods, last period). Used where grading cannot be stored, e.g. .vrt files."""
    per = graded_periods(g, lam)
    N = len(per)
    mk = lambda name, reps, p: Group(name=name, repeats=reps, children=[L for (L, d, lab) in p])
    if N <= 1:
        kids = [mk(g.name, 1, per[0])] if per else []
    else:
        kids = [mk(f"{g.name} first", 1, per[0])]
        if N > 2:
            kids.append(mk(g.name, N - 2, per[1]))
        kids.append(mk(f"{g.name} last", 1, per[-1]))
    return Group(name=g.name, repeats=1, role=g.role, color=g.color, children=kids)


def item_from_dict(d):
    return Group.from_dict(d) if d.get("kind") == "group" else Layer.from_dict(d)


@dataclass
class FlatLayer:
    """One physical layer after groups have been expanded."""
    layer: Layer
    thickness_nm: float
    path: str            # e.g. "P-DBR[3]/AlAs"
    group_role: str      # role of the innermost enclosing group with a role ("none" otherwise)
    top_group: str       # name of the outermost group (or "" for top-level layers)


@dataclass
class Structure:
    name: str = "Untitled VCSEL"
    design_wavelength: float = 980.0          # nm
    temperature: float = 23.0                 # deg C, used by temperature-dependent material models
    top: Layer = field(default_factory=lambda: Layer(name="Air", material="Air", thickness=0,
                                                     thickness_unit="nm", layer_type="other"))
    substrate: Layer = field(default_factory=lambda: Layer(name="GaAs substrate", material="AlGaAs",
                                                           x=0.0, thickness=0, thickness_unit="nm",
                                                           layer_type="n-type"))
    stack: List[Union[Layer, Group]] = field(default_factory=list)   # top -> bottom
    notes: str = ""

    # ---- expansion ----------------------------------------------------
    def flatten(self) -> List[FlatLayer]:
        out: List[FlatLayer] = []
        lam = self.design_wavelength

        def walk(items, prefix, role, top_group):
            for it in items:
                if isinstance(it, Group):
                    r = it.role if it.role != "none" else role
                    tg = top_group or it.name
                    if it.is_graded:
                        for k, per in enumerate(graded_periods(it, lam)):
                            for (L, d, lab) in per:
                                out.append(FlatLayer(L, d, f"{prefix}{it.name}[{k + 1}]/{lab}", r, tg))
                        continue
                    for k in range(max(int(it.repeats), 0)):
                        walk(it.children, f"{prefix}{it.name}[{k + 1}]/", r, tg)
                else:
                    out.append(FlatLayer(it, it.physical_thickness(lam), prefix + it.name, role, top_group))

        walk(self.stack, "", "none", "")
        return out

    def to_dict(self):
        return {"format": "vcsel-sim", "version": 1, "name": self.name,
                "design_wavelength": self.design_wavelength, "temperature": self.temperature,
                "top": self.top.to_dict(), "substrate": self.substrate.to_dict(),
                "stack": [i.to_dict() for i in self.stack], "notes": self.notes}

    @staticmethod
    def from_dict(d):
        return Structure(name=d.get("name", "Untitled"), design_wavelength=float(d.get("design_wavelength", 980)),
                         temperature=float(d.get("temperature", 23.0)),
                         top=Layer.from_dict(d["top"]), substrate=Layer.from_dict(d["substrate"]),
                         stack=[item_from_dict(i) for i in d.get("stack", [])], notes=d.get("notes", ""))

    def copy(self):
        return copy.deepcopy(self)

    def rescale_to_wavelength(self, new_wavelength):
        """Vertical's 'Design' button: change the design wavelength. Layers given in waves
        scale automatically; layers given in nm are unchanged."""
        self.design_wavelength = float(new_wavelength)
