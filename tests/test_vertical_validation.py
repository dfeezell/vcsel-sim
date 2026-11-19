"""Cross-check against the legacy program *Vertical* for the ECE 577 final-project
structure (examples/ECE577_Final_Project_DF.vrt). Reference numbers were read from
Vertical's Results dialog at 980 nm."""
import os
import numpy as np
import pytest

from vcsel_sim.vrt import read_vrt
from vcsel_sim.laser import analyze

HERE = os.path.dirname(__file__)
VRT = os.path.join(HERE, "..", "examples", "ECE577_Final_Project_DF.vrt")

VERTICAL = {
    "Gth": 2111.42, "rt_gain": 0.00831868, "rt_loss": 0.00205118, "rt_trans": 0.00626751,
    "trans_up": 0.00313441, "trans_down": 0.00313309, "enh": 1.96992, "peak_E2": 1242.53,
    "E2_active": 1217.62, "E2_top": 1.00042, "ext_eff": 0.753425, "ext_top": 0.376792,
    "ext_bottom": 0.376633, "avg_index": 3.28692,
    "m11": 0.999755 + 0.00073215j, "m12": 0.00010962 - 0.000141917j,
    "m21": -6.82492 + 3.8976j, "m22": 1.00005 + 0.000663804j,
}


@pytest.fixture(scope="module")
def result():
    with open(VRT, "rb") as f:
        s = read_vrt(f.read())
    return analyze(s)


def rel(a, b):
    return abs(a - b) / abs(b)


def test_threshold(result):
    assert result.converged
    assert rel(result.threshold_gain, VERTICAL["Gth"]) < 1e-5
    assert abs(result.wavelength - 980.0) < 1e-3


def test_vertical_convention_budget(result):
    v = result.vertical
    assert rel(v["round trip gain"], VERTICAL["rt_gain"]) < 1e-3
    assert rel(v["round trip loss"], VERTICAL["rt_loss"]) < 3e-3
    assert rel(v["round trip transmission"], VERTICAL["rt_trans"]) < 1e-3
    assert rel(v["transmission up"], VERTICAL["trans_up"]) < 1e-3
    assert rel(v["transmission down"], VERTICAL["trans_down"]) < 1e-3
    assert rel(v["gain enhancement"], VERTICAL["enh"]) < 1e-3
    assert rel(v["external efficiency"], VERTICAL["ext_eff"]) < 1e-3
    assert rel(v["external efficiency top"], VERTICAL["ext_top"]) < 1e-3
    assert rel(v["external efficiency bottom"], VERTICAL["ext_bottom"]) < 1e-3


def test_field(result):
    v = result.vertical
    assert rel(v["peak E2"], VERTICAL["peak_E2"]) < 1e-3
    assert rel(v["E2 at active"], VERTICAL["E2_active"]) < 1e-3
    assert abs(v["E2 top"] - VERTICAL["E2_top"]) < 1e-3
    assert rel(result.avg_index_rms, VERTICAL["avg_index"]) < 1e-4


def test_matrix(result):
    for name, got in zip(["m11", "m12", "m21", "m22"], result.matrix_vertical):
        ref = VERTICAL[name]
        assert abs(got - ref) < 2e-3 * max(abs(ref), 1e-3), (name, got, ref)


def test_exact_energy_balance(result):
    # exact budget closes: gain = loss + transmission
    assert abs(result.rt_gain - result.rt_loss - result.rt_transmission) < 1e-9 * result.rt_gain
    # modal gain = alpha_i + alpha_m
    assert abs(result.modal_gain - result.alpha_i - result.alpha_m) < 1e-6 * result.modal_gain
