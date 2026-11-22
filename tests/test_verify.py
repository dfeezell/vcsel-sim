from vcsel_sim.verify import verify_tmm


def test_verify_tmm():
    failed = [c.name for c in verify_tmm(verbose=False) if not c.passed]
    assert not failed, failed
