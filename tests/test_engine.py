"""Physics sanity checks that do not depend on Vertical."""
import json
import pathlib

import numpy as np
import pytest

from vcsel_sim import api, materials, laser, templates
from vcsel_sim.structure import Structure, Layer, Group

EX = pathlib.Path(__file__).resolve().parent.parent / "examples"


def test_quarter_wave_dbr_peak_reflectance():
    """N-pair quarter-wave stack: R = ((1 - q)/(1 + q))^2, q = (n0/ns) (nL/nH)^(2N)."""
    nH, nL, n0, ns, lam, N = 3.5, 3.0, 1.0, 3.5, 980.0, 10
    s = Structure(name="qw", design_wavelength=lam,
                  top=Layer(name="air", material="Generic", index_mode="fixed", n_real=n0),
                  substrate=Layer(name="sub", material="Generic", index_mode="fixed", n_real=ns),
                  stack=[Group(name="DBR", repeats=N, children=[
                      Layer(name="H", material="Generic", index_mode="fixed", n_real=nH, thickness=0.25, thickness_unit="waves"),
                      Layer(name="L", material="Generic", index_mode="fixed", n_real=nL, thickness=0.25, thickness_unit="waves")])])
    spec = laser.reflectance_spectrum(s, lam, lam, 1, "full_top")
    q = (n0 / ns) * (nL / nH) ** (2 * N)
    assert spec["R"][0] == pytest.approx(((1 - q) / (1 + q)) ** 2, rel=1e-10)
    assert spec["R"][0] + spec["T"][0] == pytest.approx(1.0, abs=1e-12)    # lossless


def test_energy_conservation_lossless_spectrum():
    s = templates.dielectric_dbr()
    spec = laser.reflectance_spectrum(s, 500, 1500, 201, "full_top")
    ok = ~np.isnan(spec["R"])
    assert np.all(spec["R"][ok] + spec["T"][ok] <= 1 + 1e-9)


def test_design_json_round_trip():
    d = json.loads((EX / "gaas_980nm_vcsel.vcsel.json").read_text())
    s = Structure.from_dict(d)
    assert Structure.from_dict(s.to_dict()).to_dict() == s.to_dict()


def test_templates_lase_near_design_wavelength():
    for name in ("gaas_980", "algaas_850"):
        s = getattr(templates, name)()
        a = laser.analyze(s)
        assert a.converged
        assert abs(a.wavelength - s.design_wavelength) < 0.5
        assert a.rt_gain == pytest.approx(a.rt_loss + a.rt_transmission, rel=1e-6)


def test_tune_cavity_recovers_design_wavelength():
    s = templates.gaas_980()
    for L in laser._marked_layers(s):
        L.thickness = 0.45
    rep = laser.tune_marked(s)
    assert rep["converged"] and abs(rep["resonance"] - 980.0) < 1e-3


def test_reflectance_from_absorbing_substrate_blanks_only_absorbing_band():
    s = templates.gaas_980()
    spec = laser.reflectance_spectrum(s, 833, 1127, 295, "full_bottom")
    bad = np.isnan(spec["R"])
    assert bad.any() and not bad.all()
    assert spec["wavelength"][bad].max() < 875          # GaAs band edge ~871 nm


def test_material_values():
    # GaAs ~3.52 near 980 nm (Afromowitz); SiO2 1.4507 at 980 nm (Malitson)
    assert materials.index("AlGaAs", 980.0, 0.0).real == pytest.approx(3.52, abs=0.02)
    assert materials.index("SiO2", 980.0).real == pytest.approx(1.4507, abs=2e-3)
    assert materials.bandgap("AlGaAs", 0.0) == pytest.approx(1.424, abs=0.01)


def test_api_returns_json_without_nan():
    d = (EX / "gaas_980nm_vcsel.vcsel.json").read_text()
    out = api.run_analysis(d, "{}")
    assert "NaN" not in out and json.loads(out)["ok"]


def test_coldren_penetration_depth_limits():
    from vcsel_sim.cavity import coldren_leff
    n1, n2, lam = 2.95, 3.52, 980.0
    period = lam / 4 / n1 + lam / 4 / n2
    big = coldren_leff(n1, n2, 400, period)
    r = (n2 - n1) / (n2 + n1)
    # long-mirror limit of A7.25: m_eff -> 1/tanh(ln(n2/n1)) = (x^2+1)/(x^2-1), x = n2/n1
    x = n2 / n1
    m_inf = (x * x + 1) / (x * x - 1)
    assert big["L_eff"] == pytest.approx(0.5 * period * (m_inf / (1 + r * r) - 0.5), rel=1e-9)
    assert big["L_eff"] == pytest.approx(period / (4 * r) - period / 4, rel=0.01)   # ~ Lambda/4r - Lambda/4
    assert big["L_eff_tanh"] == pytest.approx(period / (4 * r), rel=1e-6)


def test_cavity_report_ece577():
    from vcsel_sim.vrt import read_vrt
    from vcsel_sim import cavity
    s = read_vrt((EX / "ECE577_Final_Project_DF.vrt").read_bytes())
    a = laser.analyze(s)
    rep = cavity.cavity_report(laser.Model(s), a)
    K = rep["coldren"]
    assert rep["complete"]
    assert K["L"] == pytest.approx(rep["L_cav"] + K["L_eff_top"] + K["L_eff_bottom"])
    assert K["modal_gain"] == pytest.approx(K["alpha_i"] + K["alpha_m"], rel=1e-9)   # self-consistency
    assert K["alpha_m"] == pytest.approx(K["alpha_m_R"], rel=1e-9)
    assert abs(2 * K["chi"] - round(2 * K["chi"])) < 0.15        # close to a half-wave multiple
