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
    assert K["alpha_m"] == pytest.approx(a.rt_transmission / (2 * K["L"] * 1e-7), rel=1e-9)   # linear form
    assert abs(2 * K["chi"] - round(2 * K["chi"])) < 0.15        # close to a half-wave multiple


def test_dbr_designer_matches_analytic():
    r = json.loads(api.dbr_design(json.dumps({
        "lambda0": 980, "pairs": 20, "first": {"material": "AlGaAs", "x": 0.9}, "second": {"material": "AlGaAs", "x": 0},
        "incident": {"material": "AlGaAs", "x": 0}, "exit": {"material": "AlGaAs", "x": 0}})))
    assert r["ok"]
    assert r["at_design"]["R"] == pytest.approx(r["R_analytic"], rel=1e-9)
    assert r["pairs_needed"]["0.99"] == next(i + 1 for i, v in enumerate(r["R_vs_pairs"]) if v >= 0.99)


def test_exact_round_trip_model():
    from vcsel_sim.vrt import read_vrt
    from vcsel_sim import cavity
    s = read_vrt((EX / "ECE577_Final_Project_DF.vrt").read_bytes())
    lin = laser.analyze(s)
    ex = laser.analyze(s, rt_model="exact")
    assert ex.threshold_gain == lin.threshold_gain                       # the solve itself is unchanged
    assert ex.R_top == pytest.approx(1 - ex.rt_transmission_top)
    assert lin.R_top == pytest.approx(np.exp(-lin.rt_transmission_top))
    assert 0 < ex.alpha_i / lin.alpha_i - 1 < 0.01                        # -ln(1-x) > x, small difference
    K = cavity.cavity_report(laser.Model(s), ex)["coldren"]
    assert K["modal_gain"] == pytest.approx(K["alpha_i"] + K["alpha_m"], rel=1e-12)
    assert K["alt"]["rt_model"] == "linear"


def test_inalgaas_mondry():
    # Al0.48In0.52As (X = 1) at 1550 nm from the Mondry et al. (1992) Sellmeier fit
    assert materials.index("InAlGaAs", 1550.0, 1.0).real == pytest.approx(3.1997, abs=1e-3)
    # index rises toward the GaInAs end and is above InP at the same wavelength
    assert materials.index("InAlGaAs", 1550.0, 0.3).real > materials.index("InAlGaAs", 1550.0, 1.0).real
    assert materials.bandgap("InAlGaAs", 1.0) == pytest.approx(1.45)


def test_algainp_and_ingaasp_match_vertical():
    # values read from Vertical's layer dialog at 980 nm
    assert materials.index("AlGaInP", 980.0, 0.0).real == pytest.approx(3.25885, abs=2e-5)
    assert materials.index("AlGaInP", 980.0, 0.3).real == pytest.approx(3.12045, abs=2e-5)
    assert materials.bandgap("InGaAsP_xy", 0.42, 0.2) == pytest.approx(1.53714, abs=1e-5)


def test_algainp_adachi():
    # Adachi et al. (1994): A + B = eps_inf = 9.39 - 0.85z, and n(Ga0.5In0.5P) near the gap above 3.5
    lam_long = 1e6
    for x in (0.0, 0.255, 0.51):
        z = x / 0.51
        assert materials.index("AlGaInP_Adachi", lam_long, x).real ** 2 == pytest.approx(9.39 - 0.85 * z, abs=0.01)
    assert materials.index("AlGaInP_Adachi", 1033.0, 0.0).real == pytest.approx(3.1977, abs=1e-3)
    assert 3.5 < materials.index("AlGaInP_Adachi", 650.0, 0.0).real < 3.6


def test_algaas_gehrsitz():
    import numpy as np
    from vcsel_sim.structure import Structure
    g = lambda lam, x, T: complex(np.ravel(materials.algaas_gehrsitz(lam, x, 0.0, T))[0]).real
    # Fig. 5 of the paper (x = 0.334, 23 C) and Fig. 4 (AlAs near 800 nm)
    assert g(730, 0.334, 23) == pytest.approx(3.462, abs=3e-3)
    assert g(830, 0.334, 23) == pytest.approx(3.370, abs=3e-3)
    assert g(800, 1.0, 23) == pytest.approx(3.005, abs=3e-3)
    # GaAs gap at 23 C and blank above it
    assert materials.eg_gaas_proctor(296.15) == pytest.approx(1.424, abs=3e-3)
    assert np.isnan(g(850, 0.0, 23))
    # dn/dT near 1 um of the same order as Talghader & Smith (2.67e-4 GaAs, 1.43e-4 AlAs)
    assert 2.5e-4 < (g(1000, 0, 73) - g(1000, 0, 23)) / 50 < 3.8e-4
    assert 1.1e-4 < (g(1000, 1, 73) - g(1000, 1, 23)) / 50 < 1.6e-4
    # temperature round-trips through the design JSON
    assert Structure.from_dict(Structure(temperature=85.0).to_dict()).temperature == 85.0


def test_thermal_tuning_gehrsitz():
    import json
    from vcsel_sim import templates, api
    d = templates.gaas_980().to_dict()

    def sw(o):
        if isinstance(o, dict):
            if o.get("material") == "AlGaAs":
                o["material"] = "AlGaAs_Gehrsitz"
            for v in o.values():
                sw(v)
        elif isinstance(o, list):
            for v in o:
                sw(v)
    sw(d)
    lam = []
    for T in (23.0, 73.0):
        d["temperature"] = T
        lam.append(json.loads(api.run_analysis(json.dumps(d)))["results"]["wavelength"])
    # GaAs/AlGaAs VCSEL resonances move about 0.06-0.07 nm/K
    assert 0.05 < (lam[1] - lam[0]) / 50 < 0.08


def test_absorption_from_doping():
    from vcsel_sim import fca
    from vcsel_sim.structure import Layer
    L = Layer(material="AlGaAs", x=0.9, layer_type="p-type", doping=1e18, absorption=11.5, absorption_mode="doping")
    assert abs(float(L.alpha(980.0)) - 7.0) < 1e-9                       # Casey 1978: 7e-18 p
    L.layer_type = "n-type"
    assert abs(float(L.alpha(980.0)) - 3.0) < 1e-9
    L.sigma_fc = 5e-18                                                     # user override
    assert abs(float(L.alpha(980.0)) - 5.0) < 1e-9
    L.absorption_mode = "manual"
    assert float(L.alpha(980.0)) == 11.5
    s = fca.sigma("InP", "p", [1300.0, 1500.0])                            # Casey & Carter 1984
    assert abs(s[0] - 14e-18) < 1e-30 and abs(s[1] - 20e-18) < 1e-30
    act = Layer(material="InGaAs", layer_type="active", doping=1e18, absorption=2.0, absorption_mode="doping")
    assert float(act.alpha(980.0)) == 2.0                                  # active layers stay manual


def test_doping_absorption_literature_values():
    from vcsel_sim import fca
    from vcsel_sim.structure import Layer
    assert abs(fca.sigma("GaN", "n", 450.0) - 0.587e-18) < 0.01e-18        # Kioupakis APEX 2010, E perp c
    assert fca.sigma("GaN", "p", 450.0) == 1e-17                           # Sizov 2013 per activated Mg
    assert abs(fca.sigma("GaN", "p", 520.0, "kioupakis") - 1.38e-18) < 0.02e-18
    assert abs(fca.sigma("InGaAsP", "p", 1600.0) - 25e-18) < 1e-30          # Henry 1983
    L = Layer(material="InP", layer_type="p-type", doping=5e17, absorption_mode="doping")
    assert abs(float(L.alpha(1300.0)) - 7.0) < 1e-9


def test_n_inp_walukiewicz():
    from vcsel_sim import fca
    # Table III at 10 um, 1e18: 24.22 + 3.699 + 47.01 cm^-1
    assert abs(float(fca.sigma("InP", "n", 10000.0, N=1e18)) * 1e18 - 74.93) < 0.05
    s = float(fca.sigma("InGaAsP", "n", 1550.0, N=1e18))
    assert 0.6e-18 < s < 0.8e-18


def test_stopband_threshold_grows_with_pairs():
    import json
    from vcsel_sim import api
    w = []
    for m in (10, 20, 30):
        o = {"lambda0": 980, "pairs": m, "first": {"material": "AlGaAs", "x": 0.9}, "second": {"material": "AlGaAs", "x": 0},
             "incident": {"material": "AlGaAs", "x": 0}, "exit": {"material": "AlGaAs", "x": 0}, "points": 2001}
        w.append(json.loads(api.dbr_design(json.dumps(o)))["stopband"]["width_nm"])
    assert w[0] == 0 and 0 < w[1] < w[2] < 99.4


def _graded_980(gt=20.0, profile="linear", keep=True):
    d = json.loads(api.template("gaas_980")); d = d.get("design", d)
    for it in d["stack"]:
        if it.get("kind") == "group" and it["role"] in ("top_dbr", "bottom_dbr"):
            it["grading"] = {"profile": profile, "thickness_nm": gt, "steps": 10, "keep_period": keep}
    return d


def test_grading_layers_and_bragg_period():
    from vcsel_sim.structure import graded_periods, _n_ref
    s = Structure.from_dict(_graded_980(20.0))
    g = s.stack[0]
    per = graded_periods(g, s.design_wavelength)
    assert len(per) == g.repeats
    lam = s.design_wavelength
    ot = lambda p: sum(_n_ref(L, lam) * d for (L, d, _) in p)
    ot0 = sum(_n_ref(L, lam) * L.physical_thickness(lam) for L in g.children)
    # an interior period keeps its optical thickness (Bragg wavelength unchanged)
    assert abs(ot(per[1]) - ot0) < 1e-6 * ot0
    # the grade runs monotonically from x=0 to x=0.9 between GaAs and Al0.90Ga0.10As
    xs = [L.x for (L, d, lab) in per[1] if "grade GaAs→" in lab]
    assert len(xs) == 10 and all(b > a for a, b in zip(xs, xs[1:])) and 0 < xs[0] < xs[-1] < 0.9
    # outer faces of the group stay abrupt: first layer keeps its outer half
    assert abs(per[0][0][1] - per[1][0][1] - 10.0) < 1e-9


def test_grading_raises_threshold_and_survives_save():
    from vcsel_sim.vrt_write import write_vrt
    from vcsel_sim.vrt import read_vrt
    s0 = Structure.from_dict(_graded_980(0.0))
    a0 = laser.analyze(s0)
    s = Structure.from_dict(_graded_980(20.0))
    a = laser.analyze(s)
    assert a.threshold_gain > a0.threshold_gain * 1.02            # grading lowers the mirror reflectance
    assert abs(a.wavelength - a0.wavelength) < 1.0                # Bragg period kept: resonance stays put
    s2 = Structure.from_dict(json.loads(json.dumps(s.to_dict())))
    assert abs(laser.analyze(s2).threshold_gain - a.threshold_gain) < 1e-9
    s3 = read_vrt(write_vrt(s))                                   # Vertical gets the explicit layers
    assert len(s3.flatten()) == len(s.flatten())
    assert abs(laser.analyze(s3).threshold_gain - a.threshold_gain) / a.threshold_gain < 2e-3


def test_sweep_point_matches_full_analysis():
    d = json.loads(api.template("gaas_980")); d = d.get("design", d)
    p = json.loads(api.sweep_point(json.dumps(d)))["point"]
    r = json.loads(api.run_analysis(json.dumps(d)))["results"]
    for k in ("threshold_gain", "wavelength", "slope_top", "alpha_m", "confinement"):
        assert abs(p[k] - r[k]) < 1e-9 * max(1.0, abs(r[k]))
