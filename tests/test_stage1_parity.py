"""Stage 1 self-parity baseline.

These tests run the Stage 2 validator against Stage 1's *own* rendered draft and
lock in the current gap so the "make Stage 1 match live" tracks can be measured.

Two invariants matter most:

* **Gating precondition** — Stage 1's draft already produces zero validator
  errors and zero hard blocking warnings for every representative scenario.
  That is the precondition for ever bypassing the Stage 2 LLM, so it must never
  regress.
* **Bounded soft gap** — every remaining soft review-flag code is in a known
  baseline set. New code types are a regression (the draft drifted further from
  live); removing codes is the win each rendering track is chasing, and is
  always allowed by a subset assertion.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytest.importorskip("fastapi")

from support import _build_request  # noqa: E402

from fightcamp.main import generate_plan_sync  # noqa: E402
from fightcamp.role_labels import (  # noqa: E402
    athlete_facing_label_for,
    humanize_role_key,
    stamp_weekly_role_map_labels,
)
from fightcamp.stage1_parity import (  # noqa: E402
    parity_breakdown,
    review_stage1_self_output,
    stage1_can_bypass_llm,
    stage1_parity_breakdown,
)


def _fight_date(days_out: int) -> str:
    return (date.today() + timedelta(days=days_out)).isoformat()


# Scenario overrides keyed by name. Dates are relative to today so the suite is
# stable regardless of when it runs.
def _scenarios() -> dict[str, dict]:
    return {
        "standard_amateur_boxing": {"fight_date": _fight_date(56)},
        "long_camp_pro": {
            "athlete": {"professional_status": "pro", "record": "12-1"},
            "fight_date": _fight_date(70),
            "weekly_training_frequency": 5,
            "training_availability": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Saturday",
            ],
        },
        "weight_cut": {
            "athlete": {"weight_kg": 80.0, "target_weight_kg": 70.0},
            "fight_date": _fight_date(56),
        },
        "injury_knee": {
            "injuries": "moderate left knee pain on deep squats",
            "fight_date": _fight_date(56),
        },
        "late_fight_countdown": {"fight_date": _fight_date(9)},
        "fight_week": {"fight_date": _fight_date(5)},
        "no_injury_clean": {"injuries": "", "fight_date": _fight_date(56)},
    }


# Soft review-flag codes Stage 1's own draft is currently allowed to emit.
# Driving this set toward empty is the whole point of the Stage 1 quality tracks.
# Adding a code here means the draft regressed; removing one is the goal.
BASELINE_REVIEW_FLAG_CODES = frozenset(
    {
        "template_like_session_render",
        "missing_week_session_role",
        "late_camp_session_incomplete",
        "missing_injury_lead_summary",
        "missing_weight_cut_lead_summary",
        "generic_instruction_opener",
        "sport_language_leak",
        "conditional_conditioning_choice",
        "late_fight_missing_countdown_header",
        "late_fight_active_role_overage",
        "late_fight_block_overage",
        "late_fight_meaningful_stress_overage",
        "late_fight_forbidden_content",
        "late_fight_unapproved_exercise_rendered",
        "late_fight_hard_sparring_overage",
        "late_fight_neural_power_stacking",
    }
)


def _run_stage1(overrides: dict) -> dict:
    result = generate_plan_sync(_build_request(overrides).to_payload())
    assert result.get("status") != "invalid_input", result
    assert isinstance(result.get("planning_brief"), dict) and result["planning_brief"], (
        f"scenario produced no planning_brief: {result.get('status')!r}"
    )
    return result


@pytest.mark.parametrize("name,overrides", list(_scenarios().items()))
def test_stage1_draft_has_no_hard_validator_blockers(name: str, overrides: dict) -> None:
    """Stage 1's own output never trips errors or hard blockers (gating gate)."""
    result = _run_stage1(overrides)
    breakdown = stage1_parity_breakdown(result)

    assert breakdown["error_count"] == 0, (
        f"{name}: Stage 1 draft produced validator errors {breakdown['error_codes']}"
    )
    assert breakdown["blocking_count"] == 0, (
        f"{name}: Stage 1 draft produced blocking warnings {breakdown['blocking_codes']}"
    )
    # Publishable == the LLM-bypass precondition holds.
    assert breakdown["is_publishable"] is True
    assert stage1_can_bypass_llm(result) is True


@pytest.mark.parametrize("name,overrides", list(_scenarios().items()))
def test_stage1_soft_review_flags_stay_within_baseline(name: str, overrides: dict) -> None:
    """Remaining soft gap is bounded by the documented baseline set."""
    result = _run_stage1(overrides)
    breakdown = stage1_parity_breakdown(result)
    observed = set(breakdown["review_flag_codes"])
    unexpected = observed - BASELINE_REVIEW_FLAG_CODES
    assert not unexpected, (
        f"{name}: Stage 1 draft emitted NEW review-flag codes {sorted(unexpected)}; "
        "the draft drifted further from live. Fix the renderer or update the baseline."
    )


@pytest.mark.parametrize("name,overrides", list(_scenarios().items()))
def test_every_rendered_session_role_has_athlete_facing_label(
    name: str, overrides: dict
) -> None:
    """Track 2: Stage 1 owns the session title for every rendered role."""
    result = _run_stage1(overrides)
    weekly_role_map = (result["planning_brief"].get("weekly_role_map") or {})
    missing: list[str] = []
    for week in weekly_role_map.get("weeks", []) or []:
        for role in week.get("session_roles", []) or []:
            label = str(role.get("athlete_facing_label") or "").strip()
            if not label:
                missing.append(str(role.get("role_key")))
    assert not missing, f"{name}: session roles missing athlete_facing_label: {missing}"


def test_review_stage1_self_output_rejects_non_success_result() -> None:
    with pytest.raises(ValueError):
        review_stage1_self_output({"status": "invalid_input", "plan_text": ""})


def test_parity_breakdown_shape() -> None:
    review = review_stage1_self_output(_run_stage1(_scenarios()["standard_amateur_boxing"]))
    breakdown = parity_breakdown(review)
    assert set(breakdown) >= {
        "status",
        "is_publishable",
        "error_codes",
        "blocking_codes",
        "review_flag_codes",
        "all_codes",
    }
    # all_codes is the union of the three buckets.
    union = {
        **breakdown["error_codes"],
        **breakdown["blocking_codes"],
        **breakdown["review_flag_codes"],
    }
    assert set(breakdown["all_codes"]) == set(union)


# --- role_labels unit coverage -------------------------------------------------


def test_humanize_role_key_strips_suffix_and_titlecases() -> None:
    assert humanize_role_key("double_stress_day") == "Double Stress"
    assert humanize_role_key("mini_taper_protocol") == "Mini Taper"
    assert humanize_role_key("") == ""


def test_athlete_facing_label_resolution_order() -> None:
    # Explicit mapping wins.
    assert athlete_facing_label_for("primary_strength_day") == "Strength"
    # Unknown key falls back to caller fallback, then humanised key.
    assert athlete_facing_label_for("totally_unknown_day", fallback="Custom") == "Custom"
    assert athlete_facing_label_for("totally_unknown_day") == "Totally Unknown"


def test_stamp_weekly_role_map_preserves_existing_and_skips_plan_markers() -> None:
    weekly_role_map = {
        "weeks": [
            {
                "session_roles": [
                    {"role_key": "primary_strength_day", "category": "strength"},
                    {
                        "role_key": "converted_mobility_support_day",
                        "category": "conditioning",
                        "athlete_facing_label": "Low-load mobility support",
                    },
                ],
                "suppressed_roles": [
                    {"role_key": "fight_week_override", "category": "plan"},
                ],
            }
        ]
    }
    stamp_weekly_role_map_labels(weekly_role_map)
    roles = weekly_role_map["weeks"][0]["session_roles"]
    assert roles[0]["athlete_facing_label"] == "Strength"
    # Existing bespoke label is preserved, not overwritten.
    assert roles[1]["athlete_facing_label"] == "Low-load mobility support"
    # Plan markers never get a session title.
    assert "athlete_facing_label" not in weekly_role_map["weeks"][0]["suppressed_roles"][0]
