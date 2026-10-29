"""Seeded selection preserves exercise identity and useful training methods."""

from collections import Counter
from datetime import datetime
import json
from pathlib import Path

import pytest

from fightcamp import strength
from fightcamp.plan_pipeline_blocks import _is_rotational_power_anchor
from fightcamp.strength_session_quality import classify_strength_item, missing_base_categories, strength_adaptation_relevance
from tools.audit_strength_pool_depth import EQUIPMENT_TIERS


SEEDS = [2837615948, 0, 1, 2, 3, 4, 5, 41]
EQUIVALENTS = [
    {"Romanian Deadlift (RDL)", "Romanian Deadlift (DB)"},
    {"Lat Pulldown", "Lat Pulldown Machine"},
    {"Band-Resisted Clinch Knee Strike", "Clinch Knee Strike (Band-Resisted)"},
]


@pytest.mark.parametrize("tier", ["full", "home", "min"])
@pytest.mark.parametrize("goal", ["strength", "power"])
def test_real_camps_keep_balance_explosive_work_and_variety(tier, goal):
    signatures = set()
    for seed in SEEDS:
        flags = dict(
            phase="GPP", equipment=EQUIPMENT_TIERS[tier], key_goals=[goal],
            style_tactical=["pressure_fighter"], fatigue="low", fight_format="mma",
            training_frequency=3, training_days=["Mon", "Tue", "Wed"],
            days_until_fight=56, injuries=[], random_seed=seed,
            rotational_power_camp_gap=True,
        )
        camp = []
        for phase in ("GPP", "SPP"):
            flags["phase"] = phase
            result = strength.generate_strength_block(flags=flags)
            exercises = result["exercises"]
            names = {ex["name"] for ex in exercises}
            assert all(len(names & aliases) <= 1 for aliases in EQUIVALENTS)
            assert not missing_base_categories(exercises)
            assert max(Counter(ex["movement"] for ex in exercises if ex["movement"] != "unknown").values()) <= 2
            assert any(classify_strength_item(ex)["power_pattern"] for ex in exercises)
            assert goal in set().union(*(strength_adaptation_relevance(
                ex, prescription_type=strength._classify_prescription_type(ex)) for ex in exercises))
            if tier == "full" and goal == "strength" and phase == "SPP":
                # Each heavy/explosive pairing survives unilateral promotion.
                assert {"Heavy RDL → Broad Jump", "Back Squat → Box Jump", "DB Bench Press → Plyo Push-Up"} <= names
            flags.update(
                prev_exercises=[ex["name"] for ex in exercises],
                recent_exercises=sorted({ex["movement"] for ex in exercises}),
                rotational_power_camp_gap=not any(_is_rotational_power_anchor(ex) for ex in exercises),
            )
            camp.append(frozenset(names))
        signatures.add(tuple(camp))
    assert len(signatures) > 1


@pytest.mark.parametrize("left,right", [
    ("Romanian Deadlift (DB)", "Kettlebell Swing"),
    ("Romanian Deadlift (DB)", "Single-Leg Romanian Deadlift Hold"),
    ("Romanian Deadlift (DB)", "Heavy RDL → Broad Jump"),
    ("Back Squat", "Back Squat → Box Jump"),
])
def test_shared_movement_does_not_make_distinct_stimuli_redundant(monkeypatch, left, right):
    bank = {ex["name"]: ex for ex in strength.get_exercise_bank()}
    rows = [{**bank[name], "phases": ["GPP"]} for name in (left, right)]
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: rows)
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_a, **_k: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_a, **_k: {"strength": 2})
    monkeypatch.setattr(strength, "score_exercise", lambda **kw: (3, {"final_score": 3}))
    exercises = strength.generate_strength_block(flags=dict(
        phase="GPP", equipment=EQUIPMENT_TIERS["full"], fatigue="low", fight_format="mma",
        training_frequency=1, training_days=["Mon"], days_until_fight=56,
    ))["exercises"]
    assert {ex["name"] for ex in exercises} == {left, right}


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("excluded", [None, "Romanian Deadlift (DB)"])
def test_replacement_paths_do_not_reintroduce_the_other_rdl(monkeypatch, seed, excluded):
    bank = [
        dict(name=name, method="strength", movement=movement, phases=["GPP"],
             equipment=equipment, tags=[name, *tags])
        for name, movement, equipment, tags in [
            ("Romanian Deadlift (DB)", "hinge", "dumbbells", []),
            ("Romanian Deadlift (RDL)", "hinge", "barbell", []),
            ("Bench Press", "push", "dumbbells", []),
            ("Split Squat", "squat", "dumbbells", ["unilateral"]),
        ]
    ]
    scores = dict(zip([ex["name"] for ex in bank], [6, 5, 4, 3]))
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_a, **_k: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_a, **_k: {"strength": 3})
    monkeypatch.setattr(strength, "score_exercise", lambda **kw: (
        scores[kw["exercise_tags"][0]], {"final_score": scores[kw["exercise_tags"][0]]}))
    if excluded:
        # A safe equipment variant may replace the excluded RDL. Excluding its
        # whole identity while it is being removed would needlessly underfill.
        monkeypatch.setattr(strength, "make_guarded_decision_factory", lambda *_a, **_k: lambda ex: strength.Decision(
            action="exclude" if ex["name"] == excluded else "allow",
            risk_score=0, threshold=1, matched_tags=[], mods=[], reason={},
        ))
    exercises = strength.generate_strength_block(flags=dict(
        phase="GPP", equipment=["barbell", "dumbbells", "bodyweight"],
        fatigue="low", fight_format="mma", training_frequency=1,
        training_days=["Mon"], days_until_fight=56, random_seed=seed,
    ))["exercises"]
    expected_rdl = "Romanian Deadlift (RDL)" if excluded else "Romanian Deadlift (DB)"
    assert {ex["name"] for ex in exercises} == {expected_rdl, "Bench Press", "Split Squat"}


@pytest.mark.parametrize("seed", [2837615948, 0, 4])
def test_original_intake_through_scheduled_strength_sessions(monkeypatch, seed):
    from api.models import PlanRequest
    from fightcamp import input_parsing, stage2_planning_brief
    from fightcamp.main import generate_plan_sync

    # Original generation_jobs request, with only the display name anonymised.
    payload = json.loads((Path(__file__).parent / "fixtures" / "strength_selection_quality" / "intake.json").read_text(encoding="utf8"))
    payload["random_seed"] = seed
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 10, 29, 9, 18))
    monkeypatch.setattr(stage2_planning_brief, "_utc_now", lambda: datetime(2026, 10, 29, 9, 18))
    result = generate_plan_sync(PlanRequest(**payload).to_payload())
    brief = result["planning_brief"]
    roles = [r for w in brief["weekly_role_map"]["weeks"] for r in w["session_roles"] if r["category"] == "strength"]
    assert [r["scheduled_d_day"] for r in roles] == [30, 28, 21, 14, 13, 7]
    for role in roles:
        names = {ex["name"] for ex in role["selected_exercise_assignments"]}
        assert all(len(names & aliases) <= 1 for aliases in EQUIVALENTS)
        if role["scheduled_d_day"] in {21, 14}:
            assert {"Heavy RDL → Broad Jump", "DB Bench Press → Plyo Push-Up"} <= names
            doses = {ex["name"]: ex["effective_prescription"] for ex in role["effective_strength_prescriptions"]}
            for name in ("Heavy RDL → Broad Jump", "DB Bench Press → Plyo Push-Up"):
                assert "heavy movement" in doses[name] and "explosive movement" in doses[name]
    if seed == 2837615948:
        secondary = next(r for r in roles if r["scheduled_d_day"] == 30)
        names = {ex["name"] for ex in secondary["selected_exercise_assignments"]}
        assert {"Romanian Deadlift (DB)", "Back Squat"} <= names
    assert all(goal["satisfied"] for goal in brief["goal_preservation"])
    assert brief["primary_weakness_disposition"]["weakness"] == "balance"
    assert brief["primary_weakness_disposition"]["subsystem"] == "coordination_support_library"
    # An athlete asking for five days can combine compatible coach work and
    # strength; optional filler work must not create a sixth occupied day.
    from fightcamp.physical_session_frequency import appointment_budget_exceeded
    assert not appointment_budget_exceeded(brief["weekly_role_map"], 5)
