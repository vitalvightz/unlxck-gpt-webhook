from fightcamp.strength import _evaluate_strength_late_window


def _ex(tags):
    return {"name":"x","tags":tags,"equipment":["bodyweight"],"late_windows":["d21_to_d14","d13_to_d8","d7","d6_to_d5","d4_to_d2","d1"],"cut_buckets_allowed":["none","low","moderate","high"]}


def test_d1_requires_d1_tags():
    result = _evaluate_strength_late_window(_ex(["rehab_friendly"]), window="d1", cut_bucket="none")
    assert "late_strength_block_d1_requires_d1_tags" in result["block_codes"]


def test_d4_to_d2_blocks_no_d4_to_d1():
    result = _evaluate_strength_late_window(_ex(["rehab_friendly","no_d4_to_d1"]), window="d4_to_d2", cut_bucket="none")
    assert "late_strength_block_no_d4_to_d1" in result["block_codes"]


def test_d7_to_d5_blocks_no_d7_to_d1():
    result = _evaluate_strength_late_window(_ex(["rehab_friendly","no_d7_to_d1"]), window="d6_to_d5", cut_bucket="none")
    assert "late_strength_block_no_d7_to_d1" in result["block_codes"]


def test_high_cut_blocks_balance_risk_tags():
    result = _evaluate_strength_late_window(_ex(["single_leg","d1_ok"]), window="d6_to_d5", cut_bucket="high")
    assert "late_strength_block_high_cut_balance_risk" in result["block_codes"]
