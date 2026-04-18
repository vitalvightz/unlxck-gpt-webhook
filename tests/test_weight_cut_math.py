from fightcamp.weight_cut import (
    compute_cut_severity_score,
    compute_weight_cut_pct,
    cut_severity_bucket,
    parse_weight_value,
)


def test_compute_weight_cut_pct_uses_current_body_mass_denominator():
    # 102 -> 98 is 3.9% of current body mass (not ~7%).
    assert compute_weight_cut_pct(102, 98) == 3.9


def test_parse_weight_value_handles_unit_suffixes():
    assert parse_weight_value("102 kg") == 102.0
    assert parse_weight_value("98.5kg") == 98.5


def test_compute_weight_cut_pct_returns_zero_for_near_zero_current_weight():
    assert compute_weight_cut_pct("0.001 kg", 0) == 0.0


def test_cut_severity_score_examples_match_expected_calibration():
    assert compute_cut_severity_score(2.0, 21) == 8.7
    assert compute_cut_severity_score(3.8, 18) == 19.3
    assert compute_cut_severity_score(3.8, 7) == 28.1
    assert compute_cut_severity_score(5.0, 10) == 33.9
    assert compute_cut_severity_score(6.0, 4) == 55.4


def test_cut_severity_bucket_thresholds():
    assert cut_severity_bucket(0) == "none"
    assert cut_severity_bucket(9.9) == "none"
    assert cut_severity_bucket(10.0) == "low"
    assert cut_severity_bucket(17.9) == "low"
    assert cut_severity_bucket(18.0) == "moderate"
    assert cut_severity_bucket(34.9) == "moderate"
    assert cut_severity_bucket(35.0) == "high"
    assert cut_severity_bucket(54.9) == "high"
    assert cut_severity_bucket(55.0) == "critical"
