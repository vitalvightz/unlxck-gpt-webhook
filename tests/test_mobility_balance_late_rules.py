from fightcamp.strength import _evaluate_strength_late_window


def _ex(tags, equipment=("bodyweight",)):
    return {"name":"x","tags":tags,"equipment":list(equipment),"late_windows":["d21_to_d14","d13_to_d8","d7","d6_to_d5","d4_to_d2","d1"],"cut_buckets_allowed":["none","low","moderate","high"]}


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


# --- Safety-critical hard blocks must survive outside the tight windows ---


def test_d13_to_d8_high_cut_blocks_balance_risk():
    for tag in ("single_leg", "balance_challenge", "vestibular_sensitive"):
        result = _evaluate_strength_late_window(_ex([tag, "d1_ok"]), window="d13_to_d8", cut_bucket="high")
        assert "late_strength_block_high_cut_balance_risk" in result["block_codes"], tag
        assert result["blocked"] is True


def test_d13_to_d8_blocks_familiarity_required():
    result = _evaluate_strength_late_window(_ex(["familiarity_required"]), window="d13_to_d8", cut_bucket="none")
    assert "late_strength_block_familiarity_required_late" in result["block_codes"]
    assert result["blocked"] is True


def test_d13_to_d8_without_high_cut_does_not_block_balance_risk():
    # Balance-risk work is only hard-blocked under a high cut; a normal cut at
    # D13-D8 must not trip the safety block.
    result = _evaluate_strength_late_window(_ex(["single_leg"]), window="d13_to_d8", cut_bucket="none")
    assert "late_strength_block_high_cut_balance_risk" not in result["block_codes"]


def test_d7_to_d1_high_cut_still_blocks_balance_risk():
    for window in ("d7", "d6_to_d5", "d4_to_d2", "d1"):
        result = _evaluate_strength_late_window(_ex(["single_leg", "d1_ok"]), window=window, cut_bucket="high")
        assert "late_strength_block_high_cut_balance_risk" in result["block_codes"], window


def test_d1_blocks_all_band_work_including_primers():
    result = _evaluate_strength_late_window(
        _ex(["neural_primer"], equipment=["bands"]), window="d1", cut_bucket="none"
    )
    assert "late_strength_block_band_work_lockout" in result["block_codes"]
    assert result["blocked"] is True


def test_d7_to_d2_keeps_low_dose_band_primers():
    for window in ("d7", "d6_to_d5", "d4_to_d2"):
        result = _evaluate_strength_late_window(
            _ex(["neural_primer"], equipment=["bands"]), window=window, cut_bucket="none"
        )
        assert "late_strength_block_band_work_lockout" not in result["block_codes"], window
        assert result["blocked"] is False, window
