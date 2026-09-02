from __future__ import annotations

import copy

import fightcamp.stage2_pipeline as stage2_pipeline
from fightcamp.stage2_validator import validate_stage2_output
from fightcamp.stage2_validator_postprocess import postprocess_stage2_validator_report


PRODUCTION_LIKE_PLAN = """Lead notes.
- No active weight cut. Keep recovery and fuel around sessions to protect freshness.

GPP — Week 1 (D-23 to D-16) — Build aerobic base and general force capacity.
D-22 (Friday): Hard sparring - controlled hard contact.
- Your declared hard-sparring/contact session. No extra S&C. Keep freshness priority.

D-18 (Tuesday): Hard sparring - controlled hard contact.
- Your declared hard-sparring/contact session. No extra S&C. Keep freshness priority.

D-17 (Wednesday) — Fight Tactical Watch.
Why: Establish the ranges where you can score without staying available for the return.
- Range Map: 10 minutes, tactical review only. No physical load.
  Intent: Control the space before increasing output.
  Focus: Notice where each fighter can land without overreaching.
  Reset: Return to the last range where you could see and react clearly.
  Anchor: Make them cross your range before they can attack.
  Purpose: Early-camp range study for a distance striker.

D-17 (Wednesday): Aerobic support.
- Assault Bike steady state: 20-25 minutes easy tempo, RPE 4-5.

D-16 (Thursday): Strength.
- Romanian Deadlift (RDL): 3 x 3 @ RPE 6-7.

SPP — Week 2 (D-15 to D-8) — Increase fight-specific repeatability and power transfer.
D-12 (Monday) — Neural speed touch.
- Speed Box Squat: 2 x 3 explosive intent, RPE 6-7.

D-11 (Tuesday): Technical-only combat.
- Technical-only contact today.

D-11 (Tuesday) — Fight Tactical Watch.
- Intercept the Entry: 10 minutes, tactical review only. No physical load.
  Anchor: Make the entry pay before it gets close.

D-10 (Wednesday): Rhythm flush.
- Technical rhythm rounds: 6 x 45 sec light technical sequences on the heavy bag or shadowboxing, RPE 4-5.

D-10 (Wednesday): Light Combat / Technical.
- Your declared light-combat / technical session.

D-8 (Friday): Technical-only combat.
- Technical-only contact today.

D-8 (Friday) — Tactical Cue Card.
- Write one fight cue only.

TAPER — Week 3 (D-7 to D-0) — Maintain sharpness and freshness.
D-5 (Monday): Fight Tactical Watch.
- First-Round Range Script: 8 minutes, tactical review only. No physical load.
  Anchor: Simple first, sharp second.

D-5 (Monday): Freshness primer.
- Explosive shadow bursts: 2-3 x 5-6 sec.

D-4 (Tuesday): Technical-only combat.
- Technical-only contact today.

D-4 (Tuesday) — Neural Visualization.
- Quiet visualization only.

D-3 (Wednesday): Light Combat / Technical.
- Your declared light-combat / technical session.

D-2 (Thursday): Fight-week freshness.
- Mobility/reset circuit: 8-10 minutes total.

D-1 (Friday): Technical-only combat.
- Technical-only contact today.

D-1 (Friday) — Breathing Reset.
- Nasal breathing if comfortable.

D-0 (Saturday): Fight day protocol.
- Follow coach warm-up and fight protocol; no additional S&C.
"""


def _role(
    role_key: str,
    *,
    category: str = "",
    preferred_system: str = "",
    label: str = "",
) -> dict:
    out = {"role_key": role_key}
    if category:
        out["category"] = category
    if preferred_system:
        out["preferred_system"] = preferred_system
    if label:
        out["athlete_facing_label"] = label
    return out


def _planning_brief() -> dict:
    return {
        "athlete_model": {"sport": "boxing", "equipment": ["barbell", "bike"]},
        "restrictions": [],
        "phase_strategy": {
            "GPP": {"must_keep": ["primary_strength"]},
            "SPP": {"must_keep": ["glycolytic"]},
            "TAPER": {"must_keep": ["primary_strength"]},
        },
        "candidate_pools": {
            "GPP": {
                "strength_slots": [
                    {
                        "role": "hinge",
                        "session_index": 1,
                        "selected": {
                            "name": "Romanian Deadlift (RDL)",
                            "anchor_capable": True,
                            "support_only": False,
                        },
                        "alternates": [],
                    }
                ],
                "conditioning_slots": [],
                "rehab_slots": [],
            },
            "SPP": {
                "strength_slots": [],
                "conditioning_slots": [
                    {
                        "role": "glycolytic",
                        "session_index": 1,
                        "selected": {"name": "Punch-Slide Repeatability"},
                        "alternates": [{"name": "Pad EMOM"}],
                    }
                ],
                "rehab_slots": [],
            },
            "TAPER": {
                "strength_slots": [
                    {
                        "role": "core",
                        "session_index": 1,
                        "selected": {
                            "name": "Wall ISO Deadbug",
                            "anchor_capable": True,
                            "support_only": False,
                        },
                        "alternates": [],
                    }
                ],
                "conditioning_slots": [],
                "rehab_slots": [],
            },
        },
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "GPP",
                    "session_roles": [
                        _role("aerobic_base_day", category="conditioning", preferred_system="aerobic"),
                        _role("primary_strength_day", category="strength"),
                        _role("hard_sparring_day", category="sparring"),
                        _role("hard_sparring_day", category="sparring"),
                        _role("tactical_watch"),
                    ],
                },
                {
                    "week_index": 2,
                    "phase": "SPP",
                    "session_roles": [
                        _role("strength_touch_day", category="strength"),
                        _role("hard_sparring_day", category="sparring"),
                        _role("tactical_watch"),
                        _role(
                            "light_fight_pace_touch_day",
                            category="conditioning",
                            preferred_system="glycolytic",
                        ),
                        _role("light_combat_day"),
                        _role("hard_sparring_day", category="sparring"),
                        _role("tactical_cue_card"),
                    ],
                },
                {
                    "week_index": 3,
                    "phase": "TAPER",
                    "session_roles": [
                        _role("alactic_sharpness_day", category="conditioning", preferred_system="alactic"),
                        _role("tactical_watch"),
                        _role("hard_sparring_day", category="sparring"),
                        _role("neural_visualization"),
                        _role("light_combat_day"),
                        _role("fight_week_freshness_day"),
                        _role("hard_sparring_day", category="sparring"),
                        _role("breathing_reset"),
                    ],
                },
            ]
        },
    }


def _production_false_positive_report() -> dict:
    return {
        "errors": [],
        "is_valid": True,
        "warnings": [
            {"code": "missing_required_element", "phase": "SPP", "requirement": "glycolytic"},
            {"code": "missing_required_element", "phase": "TAPER", "requirement": "primary_strength"},
            {
                "code": "missing_week_session_role",
                "phase": "GPP",
                "week_index": 1,
                "expected_session_count": 5,
                "actual_session_count": 0,
            },
            {
                "code": "late_camp_session_incomplete",
                "phase": "SPP",
                "week_index": 2,
                "expected_session_count": 7,
                "actual_session_count": 0,
            },
            {
                "code": "late_camp_session_incomplete",
                "phase": "TAPER",
                "week_index": 3,
                "expected_session_count": 8,
                "actual_session_count": 0,
            },
            {
                "code": "internal_render_contract_leak",
                "label": "anchor_label",
                "line": "Anchor: Make them cross your range before they can attack.",
                "blocking": True,
            },
            {"code": "conditional_conditioning_choice", "line": "Technical rhythm rounds"},
        ],
        "missing_required_elements": [
            {"phase": "SPP", "requirement": "glycolytic"},
            {"phase": "TAPER", "requirement": "primary_strength"},
        ],
    }


def test_production_like_false_blockers_are_removed_from_final_authority():
    report = postprocess_stage2_validator_report(
        planning_brief=_planning_brief(),
        final_plan_text=PRODUCTION_LIKE_PLAN,
        validator_report=_production_false_positive_report(),
    )
    assert [item["code"] for item in report["warnings"]] == ["conditional_conditioning_choice"]
    assert report["week_completeness_warnings"] == []
    assert report["internal_render_contract_leak_warnings"] == []
    assert report["missing_required_elements"] == []


def test_real_validator_then_pipeline_clears_the_production_false_blockers():
    brief = _planning_brief()
    raw = validate_stage2_output(
        planning_brief=brief,
        final_plan_text=PRODUCTION_LIKE_PLAN,
    )
    raw_codes = {item.get("code") for item in raw.get("warnings") or []}
    assert "missing_required_element" in raw_codes
    assert "internal_render_contract_leak" in raw_codes
    assert raw_codes & {"missing_week_session_role", "late_camp_session_incomplete"}

    review = stage2_pipeline.review_stage2_output(
        planning_brief=brief,
        final_plan_text=PRODUCTION_LIKE_PLAN,
    )
    final_warnings = review["validator_report"].get("warnings") or []
    final_codes = {item.get("code") for item in final_warnings}
    assert "missing_required_element" not in final_codes
    assert "missing_week_session_role" not in final_codes
    assert "late_camp_session_incomplete" not in final_codes
    assert not any(
        item.get("code") == "internal_render_contract_leak"
        and item.get("label") == "anchor_label"
        for item in final_warnings
    )


def test_d0_protocol_is_not_counted_as_an_extra_taper_training_session():
    report = postprocess_stage2_validator_report(
        planning_brief=_planning_brief(),
        final_plan_text=PRODUCTION_LIKE_PLAN,
        validator_report={
            "warnings": [
                {
                    "code": "weekly_session_overage",
                    "phase": "TAPER",
                    "week_index": 3,
                    "expected_session_count": 8,
                    "actual_session_count": 9,
                }
            ]
        },
    )
    assert report["warnings"] == []


def test_only_exact_morphed_fight_pace_role_suppresses_glycolytic_requirement():
    warning = {
        "code": "missing_required_element",
        "phase": "SPP",
        "requirement": "glycolytic",
    }

    morphed = _planning_brief()
    report = postprocess_stage2_validator_report(
        planning_brief=morphed,
        final_plan_text=PRODUCTION_LIKE_PLAN,
        validator_report={"warnings": [warning]},
    )
    assert report["warnings"] == []

    genuine_rhythm = _planning_brief()
    genuine_rhythm["weekly_role_map"]["weeks"][1]["session_roles"][3] = _role(
        "glycolytic_rhythm_repeats_day",
        category="conditioning",
        preferred_system="glycolytic",
        label="Fight Rhythm Conditioning",
    )
    report = postprocess_stage2_validator_report(
        planning_brief=genuine_rhythm,
        final_plan_text=PRODUCTION_LIKE_PLAN,
        validator_report={"warnings": [warning]},
    )
    assert report["warnings"] == [warning]


def test_duplicate_anchor_outside_tactical_context_is_not_whitelisted():
    warning = {
        "code": "internal_render_contract_leak",
        "label": "anchor_label",
        "line": "Anchor: Make them cross your range before they can attack.",
        "blocking": True,
    }
    text = PRODUCTION_LIKE_PLAN.replace(
        "- Romanian Deadlift (RDL): 3 x 3 @ RPE 6-7.",
        "Anchor: Make them cross your range before they can attack.\n"
        "- Romanian Deadlift (RDL): 3 x 3 @ RPE 6-7.",
    )
    report = postprocess_stage2_validator_report(
        planning_brief=_planning_brief(),
        final_plan_text=text,
        validator_report={"warnings": [warning]},
    )
    assert report["warnings"] == [warning]


def test_pipeline_applies_postprocess_before_warning_buckets(monkeypatch):
    raw = _production_false_positive_report()
    monkeypatch.setattr(
        stage2_pipeline,
        "validate_stage2_output",
        lambda **_kwargs: copy.deepcopy(raw),
    )
    report = stage2_pipeline._validator_report_with_required_countdown_sessions(
        planning_brief=_planning_brief(),
        final_plan_text=PRODUCTION_LIKE_PLAN,
    )
    assert [item["code"] for item in report["warnings"]] == ["conditional_conditioning_choice"]
