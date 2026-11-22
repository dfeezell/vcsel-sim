from vcsel_sim.verify import verify_tmm


def test_verify_tmm():
    failed = [c.name for c in verify_tmm(verbose=False) if not c.passed]
    assert not failed, failed


def test_dbr_r_vs_pairs_one_pass_and_limits():
    """The one-pass R-versus-pairs curve equals separate calculations, and invalid pair counts are refused."""
    import json
    from vcsel_sim import api
    o = {"lambda0": 980, "pairs": 12, "first": {"material": "AlGaAs", "x": 0.9}, "second": {"material": "AlGaAs", "x": 0},
         "incident": {"material": "AlGaAs", "x": 0}, "exit": {"material": "Air"}}
    r = json.loads(api.dbr_design(json.dumps(o)))
    d = r.get("data", r)
    for k in (1, 5, 12, 24):
        rk = json.loads(api.dbr_design(json.dumps(dict(o, pairs=k))))
        assert abs(d["R_vs_pairs"][k - 1] - rk.get("data", rk)["at_design"]["R"]) < 1e-12
    for bad in (0, -3, 2.5, 1001):
        assert not json.loads(api.dbr_design(json.dumps(dict(o, pairs=bad))))["ok"]
    bad = json.loads(api.reflectance(json.dumps(json.loads(open("examples/gaas_980nm_vcsel.vcsel.json").read())),
                                     json.dumps({"lambda_min": 900, "lambda_max": 1100, "points": 0})))
    assert not bad["ok"] and "Points" in bad["error"]
