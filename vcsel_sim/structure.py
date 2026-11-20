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


@dataclass
class Group:
    name: str = "Group"
    repeats: int = 1
    children: List[Union["Layer", "Group"]] = field(default_factory=list)
    role: str = "none"
    apertured: bool = False
    color: Optional[str] = None
    kind: str = "group"

    def to_dict(self):
        return {"kind": "group", "name": self.name, "repeats": self.repeats, "role": self.role,
                "apertured": self.apertured, "color": self.color,
                "children": [c.to_dict() for c in self.children]}

    @staticmethod
    def from_dict(d):
        return Group(name=d.get("name", "Group"), repeats=int(d.get("repeats", 1)),
                     role=d.get("role", "none"), apertured=bool(d.get("apertured", False)),
                     color=d.get("color"),
                     children=[item_from_dict(c) for c in d.get("children", [])])


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
