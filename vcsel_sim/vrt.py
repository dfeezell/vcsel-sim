"""Import of legacy *Vertical* design files (.vrt).

Vertical was an MFC (Microsoft Foundation Classes) Windows program; its files
are an MFC CArchive. The layout below was reverse-engineered from example
files and cross-checked against Vertical's own Layer Parameter dialog:

* header: CString "Vertical Document File", program options (doubles), ...
* the structure is a tree of `CVStruct` objects. Each object starts with the
  tag 0xFFFD followed by a 16-bit type code:
    - 0x63 (99) group: followed by a 16-bit child count, then the children
      (bottom of the wafer first), then the group's display record whose int32
      before the name is the repetition count.
    - other codes: a layer (1 = ordinary layer, 4 = active layer, 13/14 = top
      boundary "Air"). Fields (little-endian doubles) after a 14-byte header:
      x, y, n_real, n_imag, doping(1e18 cm^-3, sign = n(-)/p(+)), thickness (nm),
      absorption (nm^-1, negative = gain), wavelength (nm), type flag, band gap (eV), ...
      followed by display data and the layer name (1-byte length prefix).
* The top-level CVStruct is a group (the wafer) whose children are listed from
  the substrate upward; the top boundary (Air) and substrate objects follow it.
"""
from __future__ import annotations

import struct

from .structure import Layer, Group, Structure

_GROUP = 0x63


class _Reader:
    def __init__(self, b):
        self.b = b
        self.p = 0

    def find(self, pat, start=None):
        i = self.b.find(pat, self.p if start is None else start)
        if i < 0:
            raise ValueError("unexpected end of .vrt file")
        return i


def _read_name_after(b, p):
    """Display record: ... int32 left, top, right, bottom-ish, COLORREF, 2 bytes, int32 reps,
    then 1-byte-length name. We locate the name as the first printable length-prefixed string
    following a plausible repetition int32. Returns (name, reps, end_position)."""
    # scan forward for pattern: <int32 reps (1..10000)> <len> <printable * len> followed by 350,300 or similar
    for q in range(p, min(p + 200, len(b) - 6)):
        reps = struct.unpack_from("<i", b, q)[0]
        ln = b[q + 4]
        if 1 <= reps <= 100000 and 1 <= ln <= 64 and q + 5 + ln <= len(b):
            s = b[q + 5:q + 5 + ln]
            if all(32 <= c < 127 for c in s):
                # sanity: name should be followed by more record data, not inside doubles
                return s.decode("latin-1"), reps, q + 5 + ln
    raise ValueError("could not locate object name in .vrt")


def _layer_fields(b, tag_pos):
    p = tag_pos + 14
    vals = struct.unpack_from("<10d", b, p)
    return vals


def _parse_object(b, pos):
    """Parse a CVStruct object whose 0xFFFD tag is at `pos`. Returns (obj, end)."""
    assert b[pos:pos + 2] == b"\xfd\xff", hex(pos)
    typ = struct.unpack_from("<H", b, pos + 2)[0]
    if typ == _GROUP:
        count = struct.unpack_from("<H", b, pos + 4)[0]
        p = pos + 6
        children = []
        for _ in range(count):
            # skip class tag (0xFFFF new class / 0x8001 class ref)
            nxt = b.find(b"\xfd\xff", p)
            child, p = _parse_object(b, nxt)
            children.append(child)
        name, reps, end = _read_name_after(b, p)
        g = Group(name=name, repeats=reps, children=list(reversed(children)))
        return g, end
    vals = _layer_fields(b, pos)
    x, y, nr, ni, dop, thick, absn, wl, tflag, eg = vals
    name, reps, end = _read_name_after(b, pos + 14 + 80)
    # The 16-bit code after the tag is Vertical's material model (0 generic, 1 AlGaAs, 4 InGaAs,
    # 6 SiO2, 13/14 boundary media ...), NOT the layer type. The "active" flag is the 16-bit word
    # 10 bytes after the ten doubles (1 = active layer).
    is_active = struct.unpack_from("<H", b, pos + 14 + 80 + 10)[0] == 1
    lt = "active" if is_active else ("n-type" if dop < 0 else "p-type" if dop > 0 else "undoped")
    lay = Layer(name=name, material="AlGaAs", x=x, y=y, thickness=thick, thickness_unit="nm",
                index_mode="fixed", n_real=nr, n_imag=-ni,
                absorption=(0.0 if is_active else absn * 1e7), layer_type=lt, doping=abs(dop) * 1e18)
    lay._vrt = {"type": typ, "active": is_active, "wavelength": wl, "bandgap": eg, "absorption_nm": absn}
    return lay, end


def read_vrt(data: bytes, name="Imported Vertical design") -> Structure:
    b = bytes(data)
    if b"Vertical Document File" not in b[:40]:
        raise ValueError("not a Vertical .vrt file")
    i = b.find(b"CVStruct")
    if i < 0:
        raise ValueError("no structure found in .vrt file")
    root_tag = b.rfind(b"\xfd\xff", 0, i)
    # parse the wafer (root group) children only; its own display record is not needed
    count = struct.unpack_from("<H", b, root_tag + 4)[0]
    p = root_tag + 6
    children = []
    for _ in range(count):
        nxt = b.find(b"\xfd\xff", p)
        child, p = _parse_object(b, nxt)
        children.append(child)
    root = Group(name="Wafer", children=list(reversed(children)))
    # The top boundary and the substrate are the last two layer objects in the file.
    # (Objects parked in Vertical's "Extra" area sit between the wafer and these and are ignored.)
    tags = [m for m in _layer_tags(b) if m > p - 1]
    if len(tags) < 2:
        raise ValueError("could not find top boundary / substrate in .vrt")
    n_extra = len(tags) - 2
    top, _ = _parse_object(b, tags[-2])
    sub, _ = _parse_object(b, tags[-1])
    design_wl = getattr(sub, "_vrt", {}).get("wavelength", 980.0)

    # Top boundary: Vertical stores the exit medium's complex index in the same record.
    # Vertical uses the n - ik convention (loss = negative imaginary part).
    tv = getattr(top, "_vrt", {})
    nr_top, ni_top = top.n_real, top.n_imag   # sign already converted in _parse_object
    if abs(nr_top - 1.0) < 1e-9 and abs(ni_top) < 1e-12:
        top = Layer(name=top.name or "Air", material="Air", thickness=0, thickness_unit="nm", layer_type="other")
    else:
        top = Layer(name=top.name, material="Generic", index_mode="fixed", n_real=nr_top, n_imag=ni_top,
                    thickness=0, thickness_unit="nm", layer_type="other")
        top._vrt = tv
    top.layer_type = "other"

    # name materials from Vertical layer names when obvious
    def tag(item):
        if isinstance(item, Group):
            for c in item.children:
                tag(c)
            nm = item.name.lower()
            if "active" in nm:
                item.role = "active"
            return
        item.material = _guess_material(item)

    for c in root.children:
        tag(c)
    tag(sub)

    # mirror roles: groups above / below the active region
    items = root.children
    act_idx = next((k for k, it in enumerate(items) if _contains_active(it)), None)
    if act_idx is not None:
        for k, it in enumerate(items):
            if isinstance(it, Group) and not _contains_active(it):
                if k < act_idx and it.role == "none":
                    it.role = "top_dbr"
                elif k > act_idx and it.role == "none":
                    it.role = "bottom_dbr"
    s = Structure(name=name, design_wavelength=design_wl, top=top, substrate=sub, stack=items)
    s.notes = "Imported from Vertical .vrt (indices fixed at the values stored in the file)."
    if n_extra:
        s.notes += f" {n_extra} unused object(s) in Vertical's Extra area were ignored."
    return s


# Materials whose name alone identifies them (no composition needed). Indices stay fixed at the
# values stored in the file; the material only sets the label and colour.
_NAME_MATS = [("sio2", "SiO2"), ("ta2o5", "Ta2O5"), ("tio2", "TiO2"), ("hfo2", "HfO2"), ("nb2o5", "Nb2O5"),
              ("si3n4", "Si3N4"), ("al2o3", "Al2O3_film"), ("al203", "Al2O3_film"), ("alox", "AlOx"),
              ("silver", "Ag"), ("gold", "Au"), ("titanium", "Ti"), ("chrom", "Cr"), ("platinum", "Pt"),
              ("algan", None), ("ingan", None), ("aln", "AlN"), ("gan", "GaN"), ("inp", "InP")]


def _guess_material(item):
    typ = getattr(item, "_vrt", {}).get("type")
    nm = item.name.lower().replace(" ", "")
    if typ == 1:
        return "AlGaAs"
    if typ == 4 or "ingaas" in nm:
        return "InGaAs"
    if nm == "air":
        return "Air"
    for key, mat in _NAME_MATS:
        if key in nm:
            return mat or "Generic"
    if "algaas" in nm or nm in ("gaas", "alas") or nm.endswith("gaas"):
        return "AlGaAs"
    return "Generic"


def _contains_active(it):
    if isinstance(it, Group):
        return any(_contains_active(c) for c in it.children)
    return it.layer_type == "active"


def _layer_tags(b):
    out = []
    i = b.find(b"\xfd\xff")
    while i >= 0:
        if b[i + 8:i + 10] == b"\xfc\xff":
            out.append(i)
        i = b.find(b"\xfd\xff", i + 2)
    return out
