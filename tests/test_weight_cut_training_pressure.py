"""Weight-cut severity must shape dose before it deletes calendar.

Regression cover for the production case where a routine 5.3% cut 16 days out
collapsed a five-day week into a single meaningful non-combat slot, because the
same cut signal was charged against weekly capacity in three independent layers.
"""

import pytest

from fightcamp.athlete_model import _derive_readiness_flags
from fightcamp.goal_preservation import classify_goal_preservation
from fightcamp.stage2_role_map import (
    _apply_high_fatigue_week_compression,
    _boxing_crowded_week_policy_state,
    _effective_compression_floor,
    _minimum_required_non_spar_exposures,
    _compression_floor_value,
    _compute_readiness_compression,
    _cut_severity_compression_points,
    _readiness_compression_floor,
)
from fightcamp.weight_cut import (
    compute_cut_severity_score,
    is_high_pressure_weight_cut,
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


# ── End-to-end: the allocator removes exactly what the authority promises ────
#
# _compression_floor_value is deliberately lossy (1 and 2 points both mean one
# slot). Folding the cut charge into that curve silently halved what a critical
# or extreme cut was supposed to remove. These cases run at D-25 so generic
# proximity compression is out of the picture and the floor reflects the cut
# alone.

@pytest.mark.parametrize(
    "cut_pct,expected_bucket,expected_slots",
    [
        (3.0, "low", 0),
        (5.0, "moderate", 0),
        (7.0, "moderate", 0),
        (9.0, "high", 1),
        (11.0, "high", 1),
        (13.0, "critical", 2),
        (15.0, "extreme", 2),
        (22.0, "extreme", 2),
    ],
)
def test_final_compression_floor_matches_promised_slot_count(
    cut_pct, expected_bucket, expected_slots
):
    days_out = 25
    score = compute_cut_severity_score(cut_pct, days_out)
    model = {
        "fatigue": "low",
        "injuries": [],
        "days_until_fight": days_out,
        "weight_cut_risk": True,
        "weight_cut_pct": cut_pct,
        "cut_severity_score": score,
        "cut_severity_bucket": cut_severity_bucket(score),
        "cut_health_bucket": cut_health_bucket(score),
        "readiness_flags": [],
    }
    assert cut_severity_bucket(score) == expected_bucket
    # The authority's promise...
    assert cut_training_compression_points(expected_bucket) == expected_slots
    # ...and what the allocator actually removes.
    assert _readiness_compression_floor(model) == expected_slots


def test_critical_and_extreme_are_not_flattened_into_one_slot():
    """Regression: the lossy generic curve used to cap these at a single slot."""
    for cut_pct in (13.0, 15.0):
        score = compute_cut_severity_score(cut_pct, 25)
        model = {
            "fatigue": "low",
            "injuries": [],
            "days_until_fight": 25,
            "weight_cut_risk": True,
            "weight_cut_pct": cut_pct,
            "cut_severity_score": score,
            "cut_severity_bucket": cut_severity_bucket(score),
            "readiness_flags": [],
        }
        assert _readiness_compression_floor(model) == 2
        # The old path routed the cut through the generic curve and lost a slot.
        assert _compression_floor_value(_compute_readiness_compression(model)) == 1


# ── Readiness compression may never empty a declared training week ──────────
#
# A fixed ceiling cannot protect a low-frequency week: for a two-session athlete
# no constant is small enough, and in TAPER ``min_non_spar_active`` is 0, so a
# critical cut could take a declared 2-session week to 0/2. These run the real
# weekly allocator rather than inspecting the floor in isolation.

def _severe_cut_athlete(cut_pct, *, days_out=5, training_days, frequency, spar_days=(), **overrides):
    score = compute_cut_severity_score(cut_pct, days_out)
    model = {
        "fatigue": "low",
        "injuries": [],
        "days_until_fight": days_out,
        "weight_cut_risk": True,
        "weight_cut_pct": cut_pct,
        "cut_severity_score": score,
        "cut_severity_bucket": cut_severity_bucket(score),
        "cut_health_bucket": cut_health_bucket(score),
        "readiness_flags": [],
        "training_days": list(training_days),
        "hard_sparring_days": list(spar_days),
        "training_frequency": frequency,
    }
    model.update(overrides)
    return model


def _taper_week(days):
    return {
        "phase": "TAPER",
        "calendar_days": [
            {"weekday": day, "d_day": 6 - index} for index, day in enumerate(days)
        ],
        "resolved_rule_state": {},
    }


def _role(index, day, role_key="aerobic_support_day", category="conditioning"):
    return {
        "session_index": index,
        "category": category,
        "role_key": role_key,
        "preferred_system": "aerobic" if category == "conditioning" else None,
        "scheduled_day_hint": day,
    }


@pytest.mark.parametrize(
    "cut_pct,expected_bucket",
    [(8.0, "critical"), (13.0, "extreme")],
)
def test_frequency_two_taper_no_spar_keeps_one_physical_session(cut_pct, expected_bucket):
    """The reported hole: TAPER + no spar + severe cut emptied the week."""
    days = ["monday", "thursday"]
    athlete = _severe_cut_athlete(cut_pct, training_days=days, frequency=2)
    assert cut_severity_bucket(athlete["cut_severity_score"]) == expected_bucket

    kept, _suppressed = _apply_high_fatigue_week_compression(
        _taper_week(days),
        [_role(1, "monday"), _role(2, "thursday", "strength_touch_day", "strength")],
        [],
        athlete,
    )
    assert len(kept) >= 1, "a declared 2-session week must not compress to zero"


def test_frequency_two_taper_with_combat_may_drop_non_spar_to_zero():
    """A declared combat session is physical work — do not manufacture filler."""
    days = ["monday", "thursday"]
    athlete = _severe_cut_athlete(
        8.0, training_days=days, frequency=2, spar_days=["thursday"]
    )
    kept, _suppressed = _apply_high_fatigue_week_compression(
        _taper_week(days),
        [
            _role(1, "monday"),
            _role(2, "thursday", "hard_sparring_day", "sparring"),
        ],
        [],
        athlete,
    )
    kept_keys = {role["role_key"] for role in kept}
    # The combat exposure survives; taper policy may legitimately take non-spar
    # work to zero because the week still contains real physical work.
    assert "hard_sparring_day" in kept_keys
    assert _effective_compression_floor(athlete, non_spar_cap=1, combat_role_count=1) == 1


@pytest.mark.parametrize("frequency,spar_days", [(2, ()), (3, ()), (4, ()), (5, ()), (6, ())])
def test_no_frequency_is_compressed_to_zero_physical_sessions(frequency, spar_days):
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"][:frequency]
    athlete = _severe_cut_athlete(
        15.0, training_days=days, frequency=frequency, spar_days=spar_days
    )
    roles = [_role(index + 1, day) for index, day in enumerate(days)]
    kept, _suppressed = _apply_high_fatigue_week_compression(
        _taper_week(days), roles, [], athlete
    )
    assert len(kept) >= 1


@pytest.mark.parametrize(
    "authority",
    [
        {"injury_mode": "medical_hold"},
        {"injury_mode": "restricted_rehab_only"},
        {"readiness_flags": ["red_flag_injury"]},
        {"days_until_fight": 0},
    ],
)
def test_explicit_safety_authority_may_still_take_the_week_to_zero(authority):
    """Only medical / fight-day authority may zero a week — never compression."""
    days = ["monday", "thursday"]
    athlete = _severe_cut_athlete(15.0, training_days=days, frequency=2, **authority)
    assert _effective_compression_floor(athlete, non_spar_cap=2, combat_role_count=0) == 2


def test_compression_alone_is_never_a_zero_week_authority():
    """Every soft signal stacked together still leaves one physical session."""
    days = ["monday", "thursday"]
    athlete = _severe_cut_athlete(
        15.0,
        training_days=days,
        frequency=2,
        fatigue="high",
        injuries=["moderate knee sprain"],
        readiness_flags=["high_fatigue", "injury_management"],
    )
    assert _effective_compression_floor(athlete, non_spar_cap=2, combat_role_count=0) == 1


# ── The compound rule is a compound rule, not a second cut penalty ───────────

def _crowded_week_model(**overrides):
    model = {
        "sport": "boxing",
        "fatigue": "high",
        "days_until_fight": 28,
        "weight_cut_risk": True,
        "weight_cut_pct": 4.0,
        "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "hard_sparring_days": ["Wednesday"],
        "readiness_flags": ["high_fatigue", "active_weight_cut"],
        "injuries": [],
    }
    model.update(overrides)
    score = compute_cut_severity_score(
        model["weight_cut_pct"], model["days_until_fight"]
    )
    model.setdefault("cut_severity_score", score)
    model.setdefault("cut_severity_bucket", cut_severity_bucket(score))
    return model


def _override_reason(model):
    state = _boxing_crowded_week_policy_state({"declared_hard_sparring_days": []}, model)
    return state.get("override_reason") or ""


def test_high_fatigue_plus_active_cut_still_triggers_crowded_week():
    """The compound rule is intentional and must survive the cut rework."""
    assert _override_reason(_crowded_week_model()) == "high_fatigue_active_cut"


def test_crowded_week_override_needs_both_halves_of_the_compound():
    """Neither signal alone fires it — that is what makes it compound."""
    # A routine cut without high fatigue: no override.
    assert _override_reason(_crowded_week_model(
        fatigue="low", readiness_flags=["active_weight_cut"]
    )) != "high_fatigue_active_cut"
    # High fatigue without any cut: no override.
    assert _override_reason(_crowded_week_model(
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        readiness_flags=["high_fatigue"],
        cut_severity_score=0.0,
        cut_severity_bucket="none",
    )) != "high_fatigue_active_cut"


def test_crowded_week_compound_does_not_charge_the_cut_for_capacity():
    """It changes week policy; it must not also remove a slot for the cut.

    This is the line between a legitimate compound interaction and a second cut
    penalty: the 4% cut here is capacity-low, so its slot charge stays zero even
    while the compound rule fires.
    """
    model = _crowded_week_model()
    assert _override_reason(model) == "high_fatigue_active_cut"
    assert _cut_severity_compression_points(model) == 0
    # The only capacity charge is high fatigue, which is not the cut.
    assert _readiness_compression_floor(model) == 1
    assert _readiness_compression_floor(
        _crowded_week_model(
            weight_cut_risk=False,
            weight_cut_pct=0.0,
            readiness_flags=["high_fatigue"],
            cut_severity_score=0.0,
            cut_severity_bucket="none",
        )
    ) == 1


# ── No contradictory third severity system ──────────────────────────────────

def test_high_pressure_cut_follows_strain_not_a_raw_percentage():
    """A 5% cut far from the fight is no longer force-flagged high pressure."""
    far = {"weight_cut_risk": True, "weight_cut_pct": 5.0,
           "fatigue": "low", "days_until_fight": 40}
    assert is_high_pressure_weight_cut(far) is False
    # The same percentage close in is strain-escalated, so it still flags.
    near = dict(far, days_until_fight=6)
    assert is_high_pressure_weight_cut(near) is True
    assert cut_health_bucket(compute_cut_severity_score(5.0, 6)) == "high"


def test_high_pressure_cut_still_flags_on_fatigue_and_proximity():
    """Do not overcorrect: the non-severity clauses are untouched."""
    assert is_high_pressure_weight_cut(
        {"weight_cut_risk": True, "weight_cut_pct": 2.0,
         "fatigue": "high", "days_until_fight": 40}
    ) is True
    assert is_high_pressure_weight_cut(
        {"weight_cut_risk": True, "weight_cut_pct": 2.0,
         "fatigue": "low", "days_until_fight": 10}
    ) is True
    assert is_high_pressure_weight_cut(
        {"weight_cut_risk": False, "weight_cut_pct": 9.0,
         "fatigue": "high", "days_until_fight": 3}
    ) is False


def test_declared_spar_day_without_a_combat_role_still_keeps_one_session():
    """The zero-non-spar exemption must follow real combat work, not intake.

    A declared hard-sparring day whose combat role was never built, or was
    suppressed before allocation, is not physical work. Basing the exemption on
    the declaration let compression strip every remaining non-spar role and
    leave the week with nothing at all.
    """
    days = ["monday", "thursday"]
    athlete = _severe_cut_athlete(
        13.0, training_days=days, frequency=2, spar_days=["thursday"]
    )
    # Thursday is declared hard sparring, but no hard_sparring_day role exists.
    kept, _suppressed = _apply_high_fatigue_week_compression(
        _taper_week(days), [_role(1, "monday")], [], athlete
    )
    assert len(kept) >= 1
    assert _minimum_required_non_spar_exposures(athlete, combat_role_count=0) == 1
    assert _minimum_required_non_spar_exposures(athlete, combat_role_count=1) == 0
