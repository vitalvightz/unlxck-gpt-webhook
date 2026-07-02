"""Stable, non-severe surface injuries train through as a skin/friction constraint.

A "moderate stable lower-back graze" is a skin/friction hygiene note, not a
lumbar injury. It must NOT:
  * generate rehab drills / body-part rehab (cat-cow, pelvic tilt, supine brace),
  * block normal exercises because of the anatomical location alone,
  * block combat-pressure / fight-pace conditioning just because severity reads
    "moderate".
It surfaces only one hygiene/friction note. Severe / red-flag surface cases keep
their existing danger gates.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_registry import (
    SURFACE_MINOR_TRAIN_THROUGH_NOTE,
    is_stable_train_through_surface_injury,
)
from fightcamp.injury_guard import injury_decision
from fightcamp.rehab_protocols import generate_rehab_protocols
from fightcamp.stage2_role_map import (
    _active_injury_is_moderate_plus,
    _build_weekly_role_map,
    _combat_pressure_floor_blockers,
)


LIMITER = {"key": "conditioning_endurance"}

# A moderate, stable lower-back graze as it appears once parsed into the model.
GRAZE = {
    "injury_type": "graze",
    "rehab_type": "graze",
    "canonical_location": "lower_back",
    "location": "lower back",
    "severity": "moderate",
    "flags": [],
}


def _graze_athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "fight_date": "2027-07-18",
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "injury_mode": "full_plan",
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        # Real pipeline shape: raw strings + parsed dicts + the injury_management
        # readiness flag that a graze would otherwise trigger.
        "injuries": ["moderate stable lower-back graze"],
        "parsed_injuries": [dict(GRAZE)],
        "readiness_flags": ["injury_management"],
    }
    athlete.update(overrides)
    return athlete


def _progression(phase_by_week, *, conditioning=1, span=7):
    weeks = []
    for idx, phase in enumerate(phase_by_week):
        weeks.append(
            {
                "week_index": idx + 1,
                "phase": phase,
                "stage_key": "general_capacity",
                "span_days": span,
                "session_counts": {"strength": 1, "conditioning": conditioning, "recovery": 1},
                "conditioning_sequence": ["aerobic", "glycolytic"],
            }
        )
    return {"weeks": weeks}


def _week(role_map, week_index):
    return next(w for w in role_map["weeks"] if w["week_index"] == week_index)


def _floor_role(week):
    return next(
        (
            role
            for role in week["session_roles"]
            if role.get("category") == "conditioning" and role.get("combat_pressure_floor")
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Predicate
# ---------------------------------------------------------------------------

def test_predicate_flags_stable_surface_and_spares_danger_cases():
    # Every surface/skin type trains through when stable (not high severity, no
    # red flag) — cut and laceration included: skin is skin, not tissue.
    assert is_stable_train_through_surface_injury(GRAZE) is True
    assert is_stable_train_through_surface_injury(
        {"injury_type": "abrasion", "severity": "low"}
    ) is True
    assert is_stable_train_through_surface_injury({"injury_type": "cut", "severity": "low"}) is True
    assert is_stable_train_through_surface_injury({"injury_type": "laceration", "severity": "moderate"}) is True
    # Severity, red flags (infection / stitches / bleeding / review) and real
    # tissue keep their danger gates.
    assert not is_stable_train_through_surface_injury({"injury_type": "graze", "severity": "high"})
    assert not is_stable_train_through_surface_injury({"injury_type": "laceration", "severity": "high"})
    assert not is_stable_train_through_surface_injury(
        {"injury_type": "cut", "severity": "moderate", "flags": ["needs_stitches"]}
    )
    assert not is_stable_train_through_surface_injury(
        {"injury_type": "graze", "severity": "moderate", "flags": ["suspected_infection"]}
    )
    assert not is_stable_train_through_surface_injury({"injury_type": "sprain", "severity": "moderate"})


def test_predicate_rejects_string_and_malformed_red_flag_inputs():
    assert not is_stable_train_through_surface_injury(
        {"injury_type": "graze", "severity": "moderate", "flags": "infected"}
    )
    assert not is_stable_train_through_surface_injury(
        {"injury_type": "graze", "severity": "moderate", "flags": "urgent"}
    )
    assert not is_stable_train_through_surface_injury(
        {"injury_type": "graze", "severity": "moderate", "flags": 1}
    )


# ---------------------------------------------------------------------------
# 1. Full-plan / train-through behavior
# ---------------------------------------------------------------------------

def test_moderate_stable_graze_is_not_treated_as_active_injury():
    assert _active_injury_is_moderate_plus(_graze_athlete()) is False


def test_malformed_or_partial_parsed_surface_injuries_do_not_bypass_active_injury_gate():
    missing_parsed_entry = _graze_athlete(
        injuries=["moderate stable lower-back graze", "moderate knee sprain"],
        parsed_injuries=[dict(GRAZE)],
    )
    malformed_parsed_entry = _graze_athlete(
        injuries=["moderate stable lower-back graze", "moderate knee sprain"],
        parsed_injuries=[dict(GRAZE), "moderate knee sprain"],
    )

    assert _active_injury_is_moderate_plus(missing_parsed_entry) is True
    assert _active_injury_is_moderate_plus(malformed_parsed_entry) is True


def test_surface_only_flag_removes_injury_management_compression_reason():
    # The role-map reason-code layer must not tag a surface-only injury as
    # injury_management (which the finalizer renders as "compressed to protect
    # tissue"). A real injury alongside it still tags injury_management.
    from fightcamp.stage2_role_map import _high_fatigue_compression_reason_codes

    surface_codes = _high_fatigue_compression_reason_codes(_graze_athlete(fatigue="high"))
    assert "high_fatigue" in surface_codes
    assert "injury_management" not in surface_codes

    mixed = _graze_athlete(
        fatigue="high",
        injuries=["moderate stable lower-back graze", "moderate knee sprain"],
        parsed_injuries=[dict(GRAZE), {"injury_type": "sprain", "severity": "moderate", "flags": []}],
    )
    assert "injury_management" in _high_fatigue_compression_reason_codes(mixed)


def test_surface_only_neutralizes_payload_injury_pressure():
    from fightcamp.stage2_payload import (
        _active_injury_affects_generic_compression,
        _active_injury_is_moderate_plus as payload_active_injury_is_moderate_plus,
    )

    surface_model = dict(
        injuries=["moderate stable lower-back graze"],
        parsed_injuries=[dict(GRAZE)],
        readiness_flags=["injury_management", "moderate_fatigue"],
        surface_injury_only=True,
    )
    assert payload_active_injury_is_moderate_plus(surface_model) is False
    assert _active_injury_affects_generic_compression(surface_model) is False

    real_model = dict(
        injuries=["moderate knee sprain"],
        parsed_injuries=[{"injury_type": "sprain", "severity": "moderate", "flags": []}],
        readiness_flags=["injury_management"],
        surface_injury_only=False,
    )
    assert payload_active_injury_is_moderate_plus(real_model) is True
    assert _active_injury_affects_generic_compression(real_model) is True


def test_build_athlete_model_bakes_surface_injury_only():
    from types import SimpleNamespace

    from fightcamp.stage2_render_guards import (
        _all_active_injuries_surface_only_from_training_context,
    )

    surface_ctx = SimpleNamespace(
        injuries=["moderate stable lower-back graze"],
        parsed_injuries=[dict(GRAZE)],
        injury_restrictions=[],
    )
    assert _all_active_injuries_surface_only_from_training_context(surface_ctx) is True

    real_ctx = SimpleNamespace(
        injuries=["moderate knee sprain"],
        parsed_injuries=[{"injury_type": "sprain", "severity": "moderate", "flags": []}],
        injury_restrictions=[],
    )
    assert _all_active_injuries_surface_only_from_training_context(real_ctx) is False

    # The parser dropping an entry (raw/parsed count mismatch) must fail safe:
    # the unparsed remainder could be a real injury.
    dropped_entry_ctx = SimpleNamespace(
        injuries=["moderate stable lower-back graze", "moderate knee sprain"],
        parsed_injuries=[dict(GRAZE)],
        injury_restrictions=[],
    )
    assert _all_active_injuries_surface_only_from_training_context(dropped_entry_ctx) is False


def test_shared_surface_only_helper_fails_safe_on_length_mismatch_and_malformed_input():
    from fightcamp.injury_registry import all_stable_train_through_surface
    from fightcamp.stage2_render_guards import _all_active_injuries_surface_only

    # Raw/parsed count mismatch → keep normal injury handling.
    assert _all_active_injuries_surface_only(
        {
            "injuries": ["moderate stable lower-back graze", "moderate knee sprain"],
            "parsed_injuries": [dict(GRAZE)],
        }
    ) is False
    # Non-iterable truthy parsed_injuries must return False, not raise.
    assert all_stable_train_through_surface(42) is False
    assert all_stable_train_through_surface(True) is False


def test_surface_only_injury_does_not_steer_limiter_to_tissue_state():
    # An injury-driven tissue_state limiter would reintroduce tissue-protection
    # framing for a graze. Declared weaknesses / real injuries still steer it.
    from fightcamp.stage2_planning_brief import _primary_limiter_key

    base = {
        "readiness_flags": ["injury_management", "fight_week"],
        "short_notice": True,
        "days_until_fight": 10,
        "key_goals": [],
        "weaknesses": [],
        "style_technical": [],
        "style_tactical": [],
    }
    surface_model = dict(base, injuries=["lower-back graze"], parsed_injuries=[dict(GRAZE)])
    assert _primary_limiter_key(surface_model, []) != "tissue_state"

    real_model = dict(
        base,
        injuries=["moderate knee sprain"],
        parsed_injuries=[{"injury_type": "sprain", "severity": "moderate", "flags": []}],
    )
    assert _primary_limiter_key(real_model, []) == "tissue_state"

    # A declared mobility weakness is a legitimate tissue signal even when the
    # only injury is a surface graze.
    weakness_model = dict(surface_model, weaknesses=["mobility"])
    assert _primary_limiter_key(weakness_model, []) == "tissue_state"


def test_moderate_stable_graze_gets_full_plan_combat_floor():
    role_map = _build_weekly_role_map(
        _graze_athlete(),
        _progression(["GPP", "GPP", "SPP", "TAPER"], conditioning=1),
        LIMITER,
    )
    week = _week(role_map, 1)
    assert week["combat_pressure_floor"]["active"] is True
    assert _floor_role(week) is not None


# ---------------------------------------------------------------------------
# 2. No lumbar rehab drills
# ---------------------------------------------------------------------------

def test_moderate_stable_graze_generates_no_lumbar_rehab():
    for phase in ("GPP", "SPP", "TAPER"):
        block, _ = generate_rehab_protocols(
            injury_string="moderate stable lower-back graze",
            exercise_data=[],
            current_phase=phase,
            parsed_entries=[dict(GRAZE)],
        )
        # One calm hygiene note, and none of the lumbar rehab/mobility/bracing work.
        assert SURFACE_MINOR_TRAIN_THROUGH_NOTE in block, phase
        lowered = block.lower()
        for banned in ("cat-cow", "cat cow", "pelvic tilt", "brace", "bracing", "isometric", "eccentric"):
            assert banned not in lowered, (phase, banned)


# ---------------------------------------------------------------------------
# 3. Normal combat exercises are not blocked by location alone
# ---------------------------------------------------------------------------

def test_moderate_stable_graze_does_not_block_normal_exercises():
    # A lumbar-loading hinge would be excluded for a real lower-back injury; a
    # pure surface graze on the lower back must not block it on location alone.
    exercise = {
        "name": "Trap Bar Deadlift",
        "tags": ["hinge_heavy", "lumbar_loaded", "posterior_chain_heavy"],
    }
    decision = injury_decision(exercise, ["moderate stable lower-back graze"], "GPP", "low")
    assert decision.action != "exclude"


# ---------------------------------------------------------------------------
# 4. Combat-pressure conditioning floor is not blocked
# ---------------------------------------------------------------------------

def test_moderate_stable_graze_does_not_block_pressure_floor():
    far_week = {"phase": "GPP", "calendar_days": [{"weekday": "monday", "d_day": 45}]}
    reasons = _combat_pressure_floor_blockers(far_week, _graze_athlete())
    assert "active_injury_blocks_hard_work" not in reasons
    assert reasons == []


# ---------------------------------------------------------------------------
# 5. Severe / red-flag surface cases still block or route to review
# ---------------------------------------------------------------------------

def test_high_severity_surface_still_blocks_hard_work():
    athlete = _graze_athlete(parsed_injuries=[{"injury_type": "graze", "severity": "high", "flags": []}])
    assert _active_injury_is_moderate_plus(athlete) is True
    far_week = {"phase": "GPP", "calendar_days": [{"weekday": "monday", "d_day": 45}]}
    assert "active_injury_blocks_hard_work" in _combat_pressure_floor_blockers(far_week, athlete)


def test_infected_surface_still_blocks_hard_work():
    athlete = _graze_athlete(
        parsed_injuries=[{"injury_type": "graze", "severity": "moderate", "flags": ["suspected_infection"]}]
    )
    assert _active_injury_is_moderate_plus(athlete) is True


def test_deep_cut_surface_still_routes_to_review():
    # An infected/red-flag surface wound still routes to manual review in the guard.
    decision = injury_decision({"name": "Jog", "tags": ["low_impact"]}, ["infected cut on shin"], "GPP", "low")
    reason = decision.reason if isinstance(decision.reason, dict) else {}
    assert reason.get("bucket") == "surface_red_flag"
    assert "manual_review" in (decision.mods or [])
