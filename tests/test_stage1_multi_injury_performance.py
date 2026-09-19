"""Stage 1 must not degrade into a planner timeout on a multi-injury intake.

An approved `restricted_rehab_only` resume timed out in Stage 1 (job
03039e43-fda8-4773-9c2d-381472aa935e): the strength block's injury
finalizers ran for minutes and the terminal pass never returned.

Root cause: `injury_decision()` re-parsed the athlete's injury free text on
every single call — `_injury_context()` and `_surface_injury_assessment()`
derive from the injuries list alone, yet both ran per exercise, ahead of the
decision cache that keys on what they produce. Cost therefore scaled with
(exercises x candidates) x (injury count x injury text length), which is why
a four-injury free-text intake hit the wall and single-injury self-serve
generations did not.

These tests pin the fix: the parse happens once per injuries list, the
decisions are unchanged, and the safety invariants of the finalizer hold.
"""

from __future__ import annotations

import time

import pytest

import fightcamp.injury_guard as injury_guard
from fightcamp.injury_guard import (
    Decision,
    clear_injury_decision_cache,
    clear_injury_profile_cache,
    injury_decision,
    pick_safe_replacement,
)
from fightcamp.strength import generate_strength_block


MULTI_INJURY = [
    "left shoulder impingement that flares when i press overhead, had it about 8 months, still painful under load",
    "right knee acl reconstruction 14 months ago, aching after long rounds and deep squats, cleared by physio but unstable",
    "chronic lower back disc herniation l4 l5 with nerve pain down the leg, worse in the morning and when deadlifting",
    "rolled my right ankle sparring three weeks ago, still swollen and gives way on lateral footwork",
]

EXERCISES = [
    {"name": "Back Squat", "tags": ["lower_body", "squat", "strength"], "movement": "squat", "method": "barbell"},
    {"name": "Overhead Press", "tags": ["upper_body_push", "press"], "movement": "press", "method": "barbell"},
    {"name": "Trap Bar Deadlift", "tags": ["hinge", "lower_body"], "movement": "hinge", "method": "trap_bar"},
    {"name": "Pallof Press", "tags": ["core", "anti_rotation"], "movement": "core", "method": "cable"},
    {"name": "Sled Push", "tags": ["lower_body", "low_impact"], "movement": "push", "method": "sled"},
]


@pytest.fixture(autouse=True)
def _clean_caches():
    clear_injury_profile_cache()
    clear_injury_decision_cache()
    yield
    clear_injury_profile_cache()
    clear_injury_decision_cache()


def _base_flags(injuries: list, phase: str = "GPP") -> dict:
    return {
        "phase": phase,
        "fatigue": "high",
        "injuries": injuries,
        "training_frequency": 4,
        "days_available": 4,
        "training_days": ["Mon", "Tue", "Thu", "Fri"],
        "style_tactical": [],
        "style_technical": [],
        "key_goals": [],
        "weaknesses": [],
        "equipment": [],
        "fight_format": "mma",
    }


def _count_injury_text_parses(monkeypatch) -> dict:
    """Count the injury-text parses that used to run per exercise."""
    counts = {"context": 0, "surface": 0}
    real_context = injury_guard._injury_context
    real_surface = injury_guard._surface_injury_assessment

    def counting_context(injuries, debug_entries=None):
        counts["context"] += 1
        return real_context(injuries, debug_entries=debug_entries)

    def counting_surface(injuries):
        counts["surface"] += 1
        return real_surface(injuries)

    monkeypatch.setattr(injury_guard, "_injury_context", counting_context)
    monkeypatch.setattr(injury_guard, "_surface_injury_assessment", counting_surface)
    return counts


def test_injury_text_is_parsed_once_per_injury_set_not_once_per_exercise(monkeypatch):
    """The pathological path: parse cost scaled with the number of exercises.

    Before the fix this was one context parse and one surface assessment per
    decision — 40 for this loop. It is now one of each for the whole run,
    regardless of how many exercises are evaluated.
    """
    counts = _count_injury_text_parses(monkeypatch)

    for _ in range(4):
        for exercise in EXERCISES:
            injury_decision(exercise, MULTI_INJURY, "GPP", "low")

    assert counts["context"] == 1
    assert counts["surface"] == 1


def test_parse_memo_is_keyed_per_injury_set(monkeypatch):
    """Different injuries must not share a parse — the memo is not global state."""
    counts = _count_injury_text_parses(monkeypatch)

    injury_decision(EXERCISES[0], MULTI_INJURY, "GPP", "low")
    injury_decision(EXERCISES[0], ["shoulder pain"], "GPP", "low")
    injury_decision(EXERCISES[0], MULTI_INJURY, "GPP", "low")

    assert counts["context"] == 2
    assert counts["surface"] == 2


def test_cached_injury_decisions_match_uncached_decisions():
    """Deterministic caching must not change a single safety verdict."""
    injury_sets = [
        [],
        ["shoulder pain"],
        MULTI_INJURY,
        ["concussion last week, got rocked sparring"],
        ["infected cut above the eye, needs stitches"],
        [{"region": "knee", "severity": "high", "original_phrase": "acl tear, knee gave way"}],
    ]

    for injuries in injury_sets:
        for phase, fatigue in (("GPP", "low"), ("TAPER", "high")):
            for exercise in EXERCISES:
                clear_injury_profile_cache()
                clear_injury_decision_cache()
                cold = injury_decision(exercise, list(injuries), phase, fatigue)
                warm = injury_decision(exercise, list(injuries), phase, fatigue)

                assert warm.action == cold.action
                assert warm.risk_score == cold.risk_score
                assert sorted(warm.matched_tags or []) == sorted(cold.matched_tags or [])
                assert sorted(warm.mods or []) == sorted(cold.mods or [])
                assert warm.reason == cold.reason


def test_interleaved_athletes_do_not_read_each_others_parses():
    """The memo is process-global, so isolation between athletes is load-bearing.

    A worker serves many athletes in turn; a concussion athlete's parse must
    never be handed to the next athlete's decision.
    """
    concussion = ["concussion last week, got rocked sparring"]
    minor = ["mild left shoulder irritation"]
    sparring = {"name": "Live Sparring Rounds", "tags": ["contact", "live_rounds"], "method": "sparring"}

    for _ in range(3):
        blocked = injury_decision(sparring, list(concussion), "GPP", "low")
        allowed = injury_decision(sparring, list(minor), "GPP", "low")

        assert blocked.action == "exclude"
        assert blocked.reason.get("bucket") == "concussion"
        assert allowed.action != "exclude"


def test_memoized_reason_payload_cannot_be_mutated_through_the_cache():
    """A caller editing a decision's reason must not poison later decisions."""
    surface_injuries = ["infected cut above the eye, needs stitches"]
    first = injury_decision(EXERCISES[0], surface_injuries, "GPP", "low")
    flags = first.reason.get("surface_red_flags")
    if isinstance(flags, list):
        flags.append("tampered")

    second = injury_decision(EXERCISES[1], surface_injuries, "GPP", "low")
    assert "tampered" not in (second.reason.get("surface_red_flags") or [])


def test_multi_injury_stage1_strength_terminates_for_every_phase():
    """The whole camp's strength generation must complete, not hang.

    The production failure was the terminal injury pass never returning; a
    generous wall-clock bound catches a regression back into that class of
    runtime without being flaky on slow CI.
    """
    started = time.perf_counter()
    for phase in ("GPP", "SPP", "TAPER"):
        block = generate_strength_block(flags=_base_flags(MULTI_INJURY, phase), weaknesses=[])
        assert block.get("exercises")
    elapsed = time.perf_counter() - started

    assert elapsed < 60.0, f"multi-injury strength generation took {elapsed:.1f}s"


def test_multi_injury_generation_does_not_rescan_injury_text_per_candidate(monkeypatch):
    """Complexity guard: parses must not scale with the exercise/candidate pool.

    Stage 1 evaluates hundreds of exercise/candidate pairs for a multi-injury
    athlete. The parse count must stay at one per distinct injuries list,
    which is what keeps the runtime off the 600s planner timeout.
    """
    counts = _count_injury_text_parses(monkeypatch)

    for phase in ("GPP", "SPP", "TAPER"):
        generate_strength_block(flags=_base_flags(MULTI_INJURY, phase), weaknesses=[])

    assert counts["context"] <= 2
    assert counts["surface"] <= 2


def test_non_injury_generation_is_unchanged():
    """No-injury generation must keep its exact selection behaviour."""
    first = generate_strength_block(flags=_base_flags([]), weaknesses=[])
    second = generate_strength_block(flags=_base_flags([]), weaknesses=[])

    names = [ex.get("name") for ex in first.get("exercises", [])]
    assert names
    assert names == [ex.get("name") for ex in second.get("exercises", [])]


def _always_excluded(item: dict) -> Decision:
    return Decision(
        action="exclude",
        risk_score=1.0,
        threshold=0.5,
        matched_tags=["injury"],
        mods=[],
        reason={"region": "knee", "severity": "high", "bucket": "default", "matches": []},
    )


def test_terminal_pass_cannot_leave_an_excluded_exercise_in_the_block(monkeypatch):
    """Invariant: nothing the guard calls `exclude` survives into the block.

    Every exercise is excluded here, so no replacement exists anywhere in the
    pool: the block must degrade in quantity rather than keep an unsafe
    movement or spin looking for a replacement that cannot exist.
    """
    monkeypatch.setattr(injury_guard, "injury_guard", lambda item, injuries, **kwargs: _always_excluded(item))
    monkeypatch.setattr(
        injury_guard,
        "injury_decision",
        lambda exercise, injuries, phase, fatigue: _always_excluded(exercise),
    )

    started = time.perf_counter()
    block = generate_strength_block(flags=_base_flags(MULTI_INJURY), weaknesses=[])
    elapsed = time.perf_counter() - started

    assert block.get("exercises") == []
    assert elapsed < 60.0, f"degraded path took {elapsed:.1f}s"


def test_pick_safe_replacement_uses_the_callers_cached_decider():
    """The finalizer's decisions must flow through the caller's memo.

    Re-deriving verdicts inside pick_safe_replacement re-evaluated pairs the
    caller had already settled, and could hand back a candidate the caller's
    own terminal re-check would then exclude.
    """
    calls: list[str] = []

    def decider(candidate: dict) -> Decision:
        calls.append(candidate.get("name", ""))
        action = "allow" if candidate.get("name") == "Pallof Press" else "exclude"
        return Decision(
            action=action,
            risk_score=0.0 if action == "allow" else 1.0,
            threshold=0.5,
            matched_tags=[],
            mods=[],
            reason={"region": None, "severity": None, "bucket": "default", "matches": []},
        )

    replacement, decision = pick_safe_replacement(
        EXERCISES[0],
        [EXERCISES[1], EXERCISES[2], EXERCISES[3]],
        {"injuries": MULTI_INJURY, "phase": "GPP", "fatigue": "low"},
        decide=decider,
    )

    assert replacement is EXERCISES[3]
    assert decision is not None and decision.action == "allow"
    # Scanning stops at the first safe candidate.
    assert calls == ["Overhead Press", "Trap Bar Deadlift", "Pallof Press"]


def test_pick_safe_replacement_without_a_decider_still_uses_the_injury_guard():
    """Existing callers (no `decide`) keep their behaviour."""
    replacement, decision = pick_safe_replacement(
        EXERCISES[0],
        [EXERCISES[3]],
        {"injuries": [], "phase": "GPP", "fatigue": "low"},
    )

    assert replacement is EXERCISES[3]
    assert decision is not None and decision.action in {"allow", "modify"}


def test_pick_safe_replacement_returns_nothing_when_every_candidate_is_excluded():
    """No safe replacement must degrade quantity, never loop."""
    replacement, decision = pick_safe_replacement(
        EXERCISES[0],
        EXERCISES[1:],
        {"injuries": MULTI_INJURY, "phase": "GPP", "fatigue": "low"},
        decide=_always_excluded,
    )

    assert replacement is None
    assert decision is None
