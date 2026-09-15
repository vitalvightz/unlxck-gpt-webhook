"""Weight-cut severity must shape dose before it deletes calendar.

Regression cover for the production case where a routine 5.3% cut 16 days out
collapsed a five-day week into a single meaningful non-combat slot, because the
same cut signal was charged against weekly capacity in three independent layers.
"""

import pytest

from fightcamp.athlete_model import _derive_readiness_flags
from fightcamp.goal_preservation import classify_goal_preservation
from fightcamp.stage2_role_map import (
    _compression_floor_value,
    _compute_readiness_compression,
    _cut_severity_compression_points,
)
from fightcamp.weight_cut import (
    compute_cut_severity_score,
    cut_health_bucket,
    cut_justifies_goal_deferral,
    cut_severity_bucket,
    cut_training_compression_points,
    weight_cut_supervision_required,
)


def _production_athlete(**overrides):
    """The exact athlete from the production report."""
    model = {
        "sport": "boxing",
        "fatigue": "low",
        "days_until_fight": 16,
        "weight_cut_pct": 5.3,
        "weight_cut_risk": True,
        "training_frequency": 5,
        "training_days": ["Monday", "Tuesday", "Thursday", "Saturday", "Sunday"],
        "hard_sparring_days": ["Sunday"],
        "reduced_contact_requested": True,
        "injuries": [],
        "key_goals": ["power", "skill_refinement"],
        "weaknesses": ["footwork"],
    }
    model.update(overrides)
    score = compute_cut_severity_score(
        model["weight_cut_pct"], model["days_until_fight"]
    )
    model.setdefault("cut_severity_score", score)
    model.setdefault("cut_severity_bucket", cut_severity_bucket(score))
    model.setdefault("cut_health_bucket", cut_health_bucket(score))
    model.setdefault(
        "readiness_flags",
        _derive_readiness_flags(
            fatigue=model["fatigue"],
            weight_cut_risk=True,
            weight_cut_pct=model["weight_cut_pct"],
            injuries=[],
            short_notice=False,
            days_until_fight=model["days_until_fight"],
        ),
    )
    return model


# ── The production regression case ───────────────────────────────────────────

def test_production_cut_classifies_moderate_not_high():
    model = _production_athlete()
    assert model["cut_severity_score"] == 35.3
    assert model["cut_severity_bucket"] == "moderate"


def test_production_cut_removes_no_weekly_capacity():
    """A moderate cut shapes dose; it must not delete a single session."""
    assert _cut_severity_compression_points(_production_athlete()) == 0


def test_production_case_keeps_three_of_four_non_spar_slots():
    """The reported collapse was 4 non-spar slots -> 1. Only taper may trim now."""
    model = _production_athlete()
    compression = _compute_readiness_compression(model)
    floor = _compression_floor_value(compression)

    # 5 weekly sessions, Sunday locked to hard sparring -> 4 non-spar slots.
    non_spar_cap = 4
    assert non_spar_cap - floor == 3
    # The single remaining charge is generic taper proximity, not the cut.
    assert floor == 1


def test_production_cut_is_not_flagged_aggressive():
    """The raw >=5% rule fired here regardless of days-out. It no longer does."""
    assert "aggressive_weight_cut" not in _production_athlete()["readiness_flags"]


def test_production_cut_does_not_defer_requested_goals():
    """Power / skill refinement must survive a routine active cut."""
    model = _production_athlete()
    assert cut_justifies_goal_deferral(model["cut_severity_bucket"]) is False
    for entry in classify_goal_preservation(model):
        assert "weight_cut_pressure" not in entry["reason_codes"]


def test_production_cut_still_shapes_dose_via_strain_scale():
    """Relaxing calendar deletion must not relax load shaping."""
    assert _production_athlete()["cut_health_bucket"] == "high"


# ── No stacked penalties ─────────────────────────────────────────────────────

def test_fight_proximity_is_not_charged_twice_for_a_cutting_athlete():
    """days_until_fight is already inside the severity score."""
    cutting = _production_athlete(
        weight_cut_pct=12.0,
        cut_severity_score=None,
        cut_severity_bucket=None,
        cut_health_bucket=None,
    )
    score = compute_cut_severity_score(12.0, 16)
    cutting["cut_severity_score"] = score
    cutting["cut_severity_bucket"] = cut_severity_bucket(score)
    assert _cut_severity_compression_points(cutting) > 0
    # Cut charge + proximity charge must not both land on the same countdown.
    assert _compute_readiness_compression(cutting) == _cut_severity_compression_points(
        cutting
    )


def test_non_cutting_athlete_keeps_generic_proximity_compression():
    """Taper behaviour for a non-cutting athlete is unchanged."""
    model = {
        "fatigue": "low",
        "injuries": [],
        "days_until_fight": 16,
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "readiness_flags": [],
    }
    assert _compute_readiness_compression(model) == 1


def test_no_second_late_camp_cut_overlay_exists():
    """aggressive_cut_extra_compression was a duplicate of the same charge."""
    with pytest.raises(ImportError):
        from fightcamp.allocator_priority import (  # noqa: F401
            readiness_compression_floor_with_late_cut,
        )
    with pytest.raises(ModuleNotFoundError):
        import fightcamp.late_camp_safety  # noqa: F401


# ── Severity -> training consequence hierarchy ───────────────────────────────

@pytest.mark.parametrize(
    "bucket,expected_points",
    [
        ("none", 0),
        ("low", 0),
        ("moderate", 0),   # dose only, never calendar
        ("high", 1),
        ("critical", 2),
        ("extreme", 2),
    ],
)
def test_capacity_removal_is_reserved_for_restrictive_cuts(bucket, expected_points):
    assert cut_training_compression_points(bucket) == expected_points


@pytest.mark.parametrize("bucket", ["none", "low", "moderate", "high"])
def test_goal_deferral_requires_more_than_a_routine_cut(bucket):
    assert cut_justifies_goal_deferral(bucket) is False


@pytest.mark.parametrize("bucket", ["critical", "extreme"])
def test_goal_deferral_allowed_only_at_critical_plus(bucket):
    assert cut_justifies_goal_deferral(bucket) is True


# ── Health risk stays independent of training pressure ───────────────────────

def test_health_escalation_is_not_relaxed_by_capacity_recalibration():
    """5% at D-6: keep the sessions, keep the supervision warning."""
    score = compute_cut_severity_score(5.0, 6)
    assert cut_severity_bucket(score) == "moderate"
    assert cut_training_compression_points(cut_severity_bucket(score)) == 0
    assert cut_health_bucket(score) == "high"
    assert weight_cut_supervision_required(True, 5.0, 6) is True


def test_magnitude_floor_still_escalates_health_regardless_of_days_out():
    assert weight_cut_supervision_required(True, 6.5, 40) is True


def test_extreme_cut_still_removes_capacity():
    """Do not overcorrect: a genuinely extreme cut must still suppress work."""
    score = compute_cut_severity_score(15.0, 3)
    assert cut_severity_bucket(score) == "extreme"
    assert cut_training_compression_points(cut_severity_bucket(score)) == 2


# ── Frequency scaling: must not destroy low-frequency plans ──────────────────

@pytest.mark.parametrize("frequency", [2, 3, 4, 5, 6])
def test_moderate_cut_never_reduces_weekly_capacity_at_any_frequency(frequency):
    model = _production_athlete(training_frequency=frequency)
    assert _cut_severity_compression_points(model) == 0


@pytest.mark.parametrize("frequency", [2, 3, 4, 5, 6])
def test_restrictive_cut_charge_is_bounded_at_any_frequency(frequency):
    """A cut may cost at most two slots, so a low-frequency week survives it."""
    score = compute_cut_severity_score(15.0, 3)
    model = _production_athlete(
        training_frequency=frequency,
        cut_severity_score=score,
        cut_severity_bucket=cut_severity_bucket(score),
        cut_health_bucket=cut_health_bucket(score),
    )
    charge = _cut_severity_compression_points(model)
    assert charge <= 2
    # Even at frequency 2 the cut alone cannot empty the week.
    assert _compression_floor_value(charge) < max(1, frequency)


# ── Unknown magnitude is not evidence of severity ────────────────────────────

def test_unmeasurable_cut_does_not_remove_capacity():
    model = {
        "fatigue": "low",
        "injuries": [],
        "days_until_fight": 28,
        "weight_cut_risk": True,
        "weight_cut_pct": "unknown",
        "readiness_flags": ["active_weight_cut"],
    }
    assert _cut_severity_compression_points(model) == 0
