"""Write a design as a .vrt file for the original (pre-2.x) Vertical program.

The byte layout was reverse-engineered from Vertical's own files (see vrt.py for the reader):
a fixed document header, the wafer as nested CVStruct objects (groups and layers, bottom first),
an empty "Extra" area, the top boundary and substrate objects, and a fixed trailer.
Every layer is written with Vertical's "generic" material model (code 0), i.e. its complex index
and absorption are frozen at the design wavelength, so Vertical reproduces this program's indices.
"""
import base64
import struct

import numpy as np

from .structure import Group, Layer, Structure
from . import materials

# Document header and trailer of an older-format Vertical file (options, plot settings, fonts).
_HEADER = base64.b64decode(
    "FlZlcnRpY2FsIERvY3VtZW50IEZpbGULAAAAAAAAAEzNQAAAAAAAwHJAAAAAAADgdUAAAAAAAABJQAAAAAAAAPA/AAAAAAAANUAAAAAAAADwPwAAAAAAAPA/AAAAAAAA8D+amZmZmZnJP5qZmZmZmfk/AAAAAAAA8D/NzMzMzMwMQAAAAAAAAElAAAAAAAAAVEAAAAAAAAA0QAAAAAAAAPA/pWYPtAJDhj8zMzMzMzP3PwYOaOkKtkE//Knx0k1ioD8AAAAAAIBpQFpkO99Pjac/AQAAAAAAAADwPwAAAAAAAPA/AQABAAEAAQABAAEACwALAAEAAQABAAEACwALAAEAAQABAAsACwABAAEAAQABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOB1QAAAAAAAQHBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABOQAAAAAAAcIdAAAAAAABAj0AAAAAAAABOQAAAAAAAiKNAAAAAAABAf0AAAAAAAHC3QAAAAAAAAFlAAAAAAACAQUAAAAAAAMByQAAAAAAAADlAAAAAAADAgkAAAAAAAGCNQAAAAAAAACTAAAAAAAAALkAAAAAAAAAuQAAAAAAAAC5AAAAAAAAALkAAAAAAAAAkQAAAAAAAACRAAAAAAACcmkCkcD0K1yMgQAAAAAAA5KBA0SLb+X4qIEBcj8L1qK2gQKabxCCwciBAAAAAAACMp0AK16NwPQolQAAAAAAAeqBAj8L1KFyPIEAAAAAAAD6cQJqZmZmZGSBACtejcD3qQ0AfhetRuM5WQAAAAAAAAD5AMzMzMzOzREAAAAAAAAA+QAAAAAAAAD5AAAAAAAAAPkAAAAAAAAA+QAAAAAAAAD5AAAAAAAAAPkAAAAAAAAA+QAAAAAAAAFlAAAAAAAAAAAAAAAAAAAAA2INAAAAAAABAj0AAAAAAAAAkQAAAAAAAAPA/AAAAAAAAAEABAAAAAAAAAABAHAEAAAkAAADxBAAACgMAANMcXXzlAfA/LDMojWe0MUABUecVSm0EQXTRN2bKj8A/b7xRuVH/UD/vvEnzdDUkP4xdRfzWlP0/CY71VjfiEEEAAAAAAFB5QACihvPPyHBADfS6VwCGUz8=")
_TRAILER = base64.b64decode(
    "AAAFAAAAAAAAAPA/AAAAAAAA8D8AAAAAAAAAAABQeUAAAAAAAFB5QACihvPPyHBAeAAAABkAAAAAAAAAAAAAAAAAAAAAAAAAvAIAAAAAAAABAgIiBUFyaWFsAAAAAAAAAAAAAAAAAAAAAAAAAAAAABRAAAAAAAAAJ0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFEAAAAAAAAAnQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAUQAAAAAAAACdAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABRAAAAAAAAAJ0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFEAAAAAAAAAnQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAUQAAAAAAAACdAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABRAAAAAAAAAJ0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFEAAAAAAAAAnQAAAAAAAAAAAAAAAAAAAAAA=")
_HDR_WL, _HDR_GTH = 0x33E, 0x346          # design wavelength / last threshold in the header
_TR_WL1, _TR_WL2, _TR_GTH = 24, 32, 40    # same, in the trailer
_CLASSDEF = b"\xff\xff\x02\x00\x08\x00CVStruct"
_CLASSREF = b"\x01\x80"
_ROW = 25                                  # Vertical's row height in its structure window


def _name(s):
    raw = (s or "layer").encode("latin-1", "replace")[:60]
    return bytes([len(raw)]) + raw


def _color(hexcol, default=(255, 255, 255)):
    try:
        h = hexcol.lstrip("#")
        return bytes((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 0))
    except Exception:
        return bytes(default) + b"\x00"


class _Writer:
    def __init__(self, s: Structure, lam: float):
        self.s, self.lam = s, lam
        self.out = bytearray()
        self.first = True
        self.y = 200

    def _prefix(self):
        self.out += _CLASSDEF if self.first else _CLASSREF
        self.first = False

    def _rect(self):
        r = struct.pack("<4i", 0, self.y, 120, self.y + _ROW)
        self.y += _ROW
        return r

    def layer(self, L: Layer, embedded=False, color=None):
        if L.index_mode == "fixed":                           # complex index without the absorption term
            n = complex(L.n_real, L.n_imag)
        else:
            n = complex(np.asarray(materials.index(L.material, np.array([self.lam]), L.x, L.y))[0]) + 1j * L.n_imag
        if not np.isfinite(n.real):
            raise ValueError(f"layer '{L.name}': index undefined at {self.lam} nm (outside the material model's range)")
        active = L.layer_type == "active"
        a = 0.0 if active else float(np.atleast_1d(L.alpha(self.lam))[0])    # cm^-1
        dop = float(L.doping or 0.0) / 1e18
        sgn = -1.0 if L.layer_type == "n-type" else (1.0 if L.layer_type == "p-type" else 0.0)
        d = float(L.physical_thickness(self.lam)) if (L.thickness or 0) > 0 else 0.0
        if not embedded:
            self._prefix()
        o = self.out
        o += b"\xfd\xff\x00\x00\x00\x00\x00\x00\xfc\xff\x00\x00\x00\x00"
        o += struct.pack("<10d", float(L.x or 0), float(L.y or 0), float(n.real), -float(n.imag),
                         sgn * dop, d, a * 1e-7, self.lam, sgn, 0.0)
        o += b"\x00" * 8 + struct.pack("<5H", 0, 1 if active else 0, 0, 0, 0) + struct.pack("<d", 300.0)
        o += self._rect() + b"\x00\x00" + (color or _color(getattr(L, "_vcol", None)))
        o += struct.pack("<i", 1) + _name(L.name) + b"\x00" * 8 + struct.pack("<2i", 350, 300)

    def group(self, g: Group):
        if g.is_graded:                                      # Vertical has no grading: write the explicit layers
            from .structure import ungraded_equivalent
            g = ungraded_equivalent(g, self.lam)
        self._prefix()
        self.out += b"\xfd\xff\x63\x00" + struct.pack("<H", len(g.children))
        y0 = self.y
        for c in reversed(g.children):                       # Vertical stores bottom first
            self.item(c)
        self.out += b"\x00\x00" + struct.pack("<4i", 0, y0, 120, y0 + _ROW) + b"\x00\x00\x7f\x7f\x7f\x00"
        self.out += struct.pack("<i", max(int(g.repeats), 0)) + _name(g.name) + struct.pack("<4i", 400, 44, 750, 344)

    def item(self, it):
        self.group(it) if isinstance(it, Group) else self.layer(it)


def write_vrt(s: Structure, colors=None, threshold_gain=0.0) -> bytes:
    """Return the bytes of an older-format Vertical .vrt for structure `s`."""
    lam = float(s.design_wavelength)
    w = _Writer(s, lam)
    head = bytearray(_HEADER)
    struct.pack_into("<d", head, _HDR_WL, lam)
    struct.pack_into("<d", head, _HDR_GTH, float(threshold_gain or 0.0))
    w.out += head
    # wafer (root group): children bottom-first
    w.out += b"\xfd\xff\x63\x00" + struct.pack("<H", len(s.stack))
    for it in reversed(s.stack):
        w.item(it)
    # empty "Extra" area
    w.out += struct.pack("<H", 0) + struct.pack("<4i", 0, 0, 0, 0) + b"\x00\x00\x7f\x7f\x7f\x00"   # count, rect, flags, colour
    w.out += struct.pack("<i", 1) + _name("Group") + struct.pack("<4i", 16, 36, 258, 585)
    # boundaries (embedded objects, no class tag)
    w.y = 175
    w.layer(s.top, embedded=True)
    w.y = 200 + _ROW * (len(s.stack) + 1)
    w.layer(s.substrate, embedded=True)
    tail = bytearray(_TRAILER)
    struct.pack_into("<d", tail, _TR_WL1, lam)
    struct.pack_into("<d", tail, _TR_WL2, lam)
    struct.pack_into("<d", tail, _TR_GTH, float(threshold_gain or 0.0))
    w.out += tail
    return bytes(w.out)
