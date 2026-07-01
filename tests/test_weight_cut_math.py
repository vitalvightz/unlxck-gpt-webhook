from fightcamp.weight_cut import (
    compute_cut_severity_score,
    compute_weight_cut_pct,
    cut_severity_bucket,
    cut_severity_rank,
    cut_warnings_escalate,
    parse_weight_value,
    weight_cut_risk_band,
    weight_cut_supervision_required,
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
    assert compute_cut_severity_score(2.0, 21) == 10.3
    assert compute_cut_severity_score(3.8, 18) == 22.9
    assert compute_cut_severity_score(3.8, 7) == 31.6
    assert compute_cut_severity_score(5.0, 10) == 39.2
    assert compute_cut_severity_score(6.0, 4) == 59.8


def test_cut_severity_bucket_thresholds():
    assert cut_severity_bucket(0) == "none"
    assert cut_severity_bucket(4.9) == "none"
    assert cut_severity_bucket(5.0) == "low"
    assert cut_severity_bucket(14.9) == "low"
    assert cut_severity_bucket(15.0) == "moderate"
    assert cut_severity_bucket(34.9) == "moderate"
    assert cut_severity_bucket(35.0) == "high"
    assert cut_severity_bucket(54.9) == "high"
    assert cut_severity_bucket(55.0) == "critical"
    assert cut_severity_bucket(84.9) == "critical"
    assert cut_severity_bucket(85.0) == "extreme"


def test_cut_severity_rank_orders_buckets():
    assert cut_severity_rank("none") == 0
    assert cut_severity_rank("moderate") < cut_severity_rank("high")
    assert cut_severity_rank("extreme") == 5
    # Unknown / empty buckets fall back to the calmest rank.
    assert cut_severity_rank("nonsense") == 0
    assert cut_severity_rank(None) == 0


def test_cut_warnings_escalate_only_above_moderate():
    # A cut that is not worse than moderate must NOT trip alarm-tier copy.
    assert cut_warnings_escalate("none") is False
    assert cut_warnings_escalate("low") is False
    assert cut_warnings_escalate("moderate") is False
    # High and above warrant supervision / stop-report language.
    assert cut_warnings_escalate("high") is True
    assert cut_warnings_escalate("critical") is True
    assert cut_warnings_escalate("extreme") is True


def test_weight_cut_risk_band_stays_moderate_for_routine_cut():
    # The ~3.5% cut from the reported plan (moderate bucket) must NOT read as
    # "high" — that over-escalation is exactly what was shouting at the athlete.
    assert weight_cut_risk_band(True, 3.5, 18) == "moderate"
    # An inactive cut is never banded.
    assert weight_cut_risk_band(False, 3.5, 18) == "none"
    # Time pressure alone does not promote a small cut above moderate.
    assert weight_cut_risk_band(True, 2.0, 5) == "moderate"


def test_weight_cut_risk_band_escalates_only_when_severity_demands():
    # Magnitude floor: a >=6% cut is severe regardless of days-out.
    assert weight_cut_risk_band(True, 6.5, 40) == "severe"
    # A genuinely high smart-score cut bands as high.
    assert weight_cut_risk_band(True, 5.0, 6) == "high"


def test_weight_cut_supervision_gated_on_severity():
    # Routine / moderate cuts never demand qualified supervision.
    assert weight_cut_supervision_required(True, 3.5, 18) is False
    assert weight_cut_supervision_required(True, 2.0, 5) is False
    # Heavy or escalated cuts do.
    assert weight_cut_supervision_required(True, 6.5, 40) is True
    assert weight_cut_supervision_required(True, 5.0, 6) is True
    assert weight_cut_supervision_required(False, 7.0, 5) is False
