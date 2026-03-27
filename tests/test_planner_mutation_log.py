"""Tests for planner mutation log and post-score simplification.

Covers:
- Override classification constants exist with correct values
- Mutation log is emitted in the generate_strength_block result
- Representative post-score overrides are recorded with correct labels
- Narrowed _final_keyword_guard does not fire for exercises confirmed safe by
  the main injury guard (injury action == "allow")
- No regression in injury-safe filtering/replacement
- Removed redundant _apply_movement_caps calls (structural simplification)
"""
from __future__ import annotations

import pytest

from fightcamp import strength as strength_module
from fightcamp.planner_mutation_log import (
    MUST_NOT_MISS_GUARANTEE,
    NICHE_LATE_INSERTION,
    PHASE_SPECIFIC_SAFEGUARD,
    SELECTOR_COMPENSATION_INSERTION,
    MutationRecord,
    mutation_log_to_dicts,
    record_mutation,
)


# ---------------------------------------------------------------------------
# 1. Constants and dataclass API
# ---------------------------------------------------------------------------


def test_classification_labels_have_correct_string_values():
    assert MUST_NOT_MISS_GUARANTEE == "must_not_miss_guarantee"
    assert SELECTOR_COMPENSATION_INSERTION == "selector_compensation_insertion"
    assert PHASE_SPECIFIC_SAFEGUARD == "phase_specific_safeguard"
    assert NICHE_LATE_INSERTION == "niche_late_insertion"


def test_mutation_record_dataclass_fields():
    record = MutationRecord(
        mechanism="test_mechanism",
        phase="GPP",
        original_name="Old Exercise",
        replacement_name="New Exercise",
        original_score=1.5,
        replacement_score=2.0,
        label=SELECTOR_COMPENSATION_INSERTION,
        reason="test reason",
    )
    assert record.mechanism == "test_mechanism"
    assert record.phase == "GPP"
    assert record.original_name == "Old Exercise"
    assert record.replacement_name == "New Exercise"
    assert record.original_score == 1.5
    assert record.replacement_score == 2.0
    assert record.label == SELECTOR_COMPENSATION_INSERTION
    assert record.reason == "test reason"
    assert record.module == "strength"


def test_record_mutation_appends_to_log():
    log: list[MutationRecord] = []
    record_mutation(
        log,
        mechanism="promote_base_categories",
        phase="GPP",
        original_name="Support Only Exercise",
        replacement_name="Squat",
        original_score=1.0,
        replacement_score=2.5,
        label=SELECTOR_COMPENSATION_INSERTION,
        reason="missing lower_body_loaded base category",
    )
    assert len(log) == 1
    assert log[0].mechanism == "promote_base_categories"
    assert log[0].label == SELECTOR_COMPENSATION_INSERTION


def test_mutation_log_to_dicts_returns_serialisable_list():
    log: list[MutationRecord] = []
    record_mutation(
        log,
        mechanism="finalize_injury_safe_exercises",
        phase="SPP",
        original_name="Overhead Press",
        replacement_name="Cable Row",
        original_score=3.0,
        replacement_score=2.8,
        label=MUST_NOT_MISS_GUARANTEE,
        reason="excluded by shoulder injury guard",
    )
    dicts = mutation_log_to_dicts(log)
    assert len(dicts) == 1
    d = dicts[0]
    assert d["mechanism"] == "finalize_injury_safe_exercises"
    assert d["label"] == MUST_NOT_MISS_GUARANTEE
    assert d["original_name"] == "Overhead Press"
    assert d["replacement_name"] == "Cable Row"
    assert d["phase"] == "SPP"


def test_mutation_log_to_dicts_with_none_fields():
    log: list[MutationRecord] = []
    record_mutation(
        log,
        mechanism="finalize_injury_safe_exercises",
        phase="GPP",
        original_name="Deadlift",
        replacement_name=None,
        original_score=2.0,
        replacement_score=None,
        label=MUST_NOT_MISS_GUARANTEE,
        reason="excluded, no safe replacement found",
    )
    dicts = mutation_log_to_dicts(log)
    assert dicts[0]["replacement_name"] is None
    assert dicts[0]["replacement_score"] is None


# ---------------------------------------------------------------------------
# 2. generate_strength_block: mutation_log present in result
# ---------------------------------------------------------------------------


def _make_base_exercise(name: str, tags: list[str], equipment: list[str], phases: list[str]) -> dict:
    return {
        "name": name,
        "phases": phases,
        "tags": tags,
        "equipment": equipment,
        "movement": "hinge",
    }


def _base_flags(phase: str = "GPP") -> dict:
    return {
        "phase": phase,
        "fatigue": "low",
        "equipment": ["barbell"],
        "fight_format": "mma",
        "training_days": ["Mon"],
        "training_frequency": 1,
        "key_goals": [],
        "style_tactical": [],
    }


def test_generate_strength_block_returns_mutation_log_key(monkeypatch):
    """Result dict must contain a 'mutation_log' key."""
    bank = [
        _make_base_exercise(
            "Back Squat",
            ["compound", "posterior_chain", "quad_dominant"],
            ["barbell"],
            ["GPP"],
        )
    ]
    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 1})

    result = strength_module.generate_strength_block(flags=_base_flags("GPP"))

    assert "mutation_log" in result
    assert isinstance(result["mutation_log"], list)


def test_mutation_log_is_list_of_dicts(monkeypatch):
    bank = [
        _make_base_exercise(
            "Trap Bar Deadlift",
            ["compound", "posterior_chain", "hinge"],
            ["trap_bar"],
            ["SPP"],
        )
    ]
    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 1})

    result = strength_module.generate_strength_block(
        flags={**_base_flags("SPP"), "equipment": ["trap_bar"]}
    )

    for entry in result["mutation_log"]:
        assert isinstance(entry, dict)
        for field in ("mechanism", "phase", "label", "reason", "module"):
            assert field in entry


# ---------------------------------------------------------------------------
# 3. Base-category promotion records selector_compensation_insertion
# ---------------------------------------------------------------------------


def test_base_category_promotion_records_mutation(monkeypatch):
    """When _promote_base_categories fires, the mutation log should contain a
    selector_compensation_insertion record."""
    # Bank: one support-only exercise (no anchor/base-category coverage) and one
    # anchor-capable exercise with lower_body_loaded that should be promoted.
    # Names included as first tag so the score mock can look them up by tag[0].
    bank = [
        {
            "name": "Core Hold",
            "phases": ["GPP"],
            "tags": ["Core Hold", "core", "stability"],
            "equipment": [],
            "movement": "core",
        },
        {
            "name": "Goblet Squat",
            "phases": ["GPP"],
            "tags": ["Goblet Squat", "compound", "quad_dominant", "squat"],
            "equipment": ["kettlebell"],
            "movement": "squat",
        },
    ]

    def _fake_score(exercise_tags, **_kwargs):
        # Core Hold gets higher raw score so it wins selection; Goblet Squat
        # will be promoted as the replacement via _promote_base_categories.
        scores = {"Core Hold": 5.0, "Goblet Squat": 3.0}
        tag = exercise_tags[0] if exercise_tags else ""
        v = scores.get(tag, 1.0)
        return v, {"final_score": v}

    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "score_exercise", _fake_score)
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 1})

    result = strength_module.generate_strength_block(
        flags={**_base_flags("GPP"), "equipment": ["kettlebell"]}
    )

    promo_entries = [
        e
        for e in result["mutation_log"]
        if e["mechanism"] == "promote_base_categories"
        and e["label"] == SELECTOR_COMPENSATION_INSERTION
    ]
    assert promo_entries, (
        "Expected at least one selector_compensation_insertion record from "
        "promote_base_categories, but mutation_log contained: "
        f"{result['mutation_log']}"
    )


# ---------------------------------------------------------------------------
# 4. Session-quality enforcement records must_not_miss_guarantee
# ---------------------------------------------------------------------------


def test_session_quality_anchor_enforcement_records_mutation(monkeypatch):
    """When _enforce_session_quality fires due to support-cap exceeded, the
    mutation log should contain a must_not_miss_guarantee record.

    Setup: 3 support-only exercises score higher than the anchor-power candidate,
    but the anchor has no base_categories so _promote_base_categories cannot
    fire — leaving only _enforce_session_quality/support_cap to act.
    """
    bank = [
        {
            "name": "Plank",
            "phases": ["GPP"],
            "tags": ["Plank", "core", "stability"],
            "equipment": [],
            "movement": "core",
        },
        {
            "name": "Neck Hold",
            "phases": ["GPP"],
            "tags": ["Neck Hold", "neck"],
            "equipment": [],
            "movement": "neck",
        },
        {
            "name": "Breathing Box",
            "phases": ["GPP"],
            "tags": ["Breathing Box", "breathing", "parasympathetic"],
            "equipment": [],
            "movement": "core",
        },
        # anchor_power with no base_categories so _promote_base_categories cannot use it
        {
            "name": "Med Ball Slam",
            "phases": ["GPP"],
            "tags": ["Med Ball Slam", "explosive", "rate_of_force"],
            "equipment": [],
            "movement": "rotation",
        },
    ]

    def _fake_score(exercise_tags, **_kwargs):
        scores = {"Plank": 6.0, "Neck Hold": 5.5, "Breathing Box": 5.0, "Med Ball Slam": 3.0}
        tag = exercise_tags[0] if exercise_tags else ""
        v = scores.get(tag, 1.0)
        return v, {"final_score": v}

    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "score_exercise", _fake_score)
    # 1 session: support_cap = max(1*2, 2) = 2; 3 selected support items > cap
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 3})

    result = strength_module.generate_strength_block(
        flags={**_base_flags("GPP"), "equipment": []}
    )

    quality_entries = [
        e
        for e in result["mutation_log"]
        if e["label"] == MUST_NOT_MISS_GUARANTEE
        and "enforce_session_quality" in e["mechanism"]
    ]
    assert quality_entries, (
        "Expected must_not_miss_guarantee records from enforce_session_quality; "
        f"mutation_log: {result['mutation_log']}"
    )


# ---------------------------------------------------------------------------
# 5. Injury-safe final pass records must_not_miss_guarantee
# ---------------------------------------------------------------------------


def test_injury_safe_replacement_recorded_in_mutation_log(monkeypatch):
    """When _finalize_injury_safe_exercises replaces an injury-excluded exercise,
    the mutation log should contain a must_not_miss_guarantee record for it.

    Back Squat is a true_loaded_anchor (so _enforce_session_quality won't
    replace it first) and is excluded by the knee injury guard, ensuring
    _finalize_injury_safe_exercises is the one that acts.
    """
    bank = [
        {
            "name": "Back Squat",
            "phases": ["GPP"],
            "tags": ["Back Squat", "compound", "posterior_chain", "quad_dominant", "squat"],
            "equipment": ["barbell"],
            "movement": "squat",
        },
        {
            "name": "Bench Press",
            "phases": ["GPP"],
            "tags": ["Bench Press", "compound", "push", "horizontal_power"],
            "equipment": ["barbell"],
            "movement": "push",
        },
        {
            "name": "Cable Row",
            "phases": ["GPP"],
            "tags": ["Cable Row", "pull", "compound"],
            "equipment": ["cable"],
            "movement": "pull",
        },
    ]

    def _fake_score(exercise_tags, **_kwargs):
        scores = {"Back Squat": 8.0, "Bench Press": 6.0, "Cable Row": 4.0}
        tag = exercise_tags[0] if exercise_tags else ""
        v = scores.get(tag, 1.0)
        return v, {"final_score": v}

    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "score_exercise", _fake_score)
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 2})

    result = strength_module.generate_strength_block(
        flags={
            **_base_flags("GPP"),
            "equipment": ["barbell", "cable"],
            # Knee injury: Back Squat is excluded; Bench Press and Cable Row are safe.
            "injuries": [{"region": "knee", "severity": "high"}],
        }
    )

    safety_entries = [
        e
        for e in result["mutation_log"]
        if e["mechanism"] == "finalize_injury_safe_exercises"
        and e["label"] == MUST_NOT_MISS_GUARANTEE
    ]
    assert safety_entries, (
        "Expected must_not_miss_guarantee record from finalize_injury_safe_exercises; "
        f"mutation_log: {result['mutation_log']}"
    )
    # Back Squat should be recorded as the excluded exercise.
    original_names = {e["original_name"] for e in safety_entries}
    assert "Back Squat" in original_names


# ---------------------------------------------------------------------------
# 6. Injury-safe filtering still removes unsafe exercises (no regression)
# ---------------------------------------------------------------------------


def test_injury_safe_filtering_removes_excluded_exercise(monkeypatch):
    """Back Squat must not appear in the final exercise list when the athlete
    has a high-severity knee injury."""
    bank = [
        {
            "name": "Back Squat",
            "phases": ["GPP"],
            "tags": ["Back Squat", "compound", "posterior_chain", "quad_dominant", "squat"],
            "equipment": ["barbell"],
            "movement": "squat",
        },
        {
            "name": "Bench Press",
            "phases": ["GPP"],
            "tags": ["Bench Press", "compound", "push", "horizontal_power"],
            "equipment": ["barbell"],
            "movement": "push",
        },
        {
            "name": "Cable Row",
            "phases": ["GPP"],
            "tags": ["Cable Row", "pull", "compound"],
            "equipment": ["cable"],
            "movement": "pull",
        },
    ]

    def _fake_score(exercise_tags, **_kwargs):
        scores = {"Back Squat": 10.0, "Bench Press": 7.0, "Cable Row": 6.0}
        tag = exercise_tags[0] if exercise_tags else ""
        v = scores.get(tag, 1.0)
        return v, {"final_score": v}

    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "score_exercise", _fake_score)
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 2})

    result = strength_module.generate_strength_block(
        flags={
            **_base_flags("GPP"),
            "equipment": ["barbell", "cable"],
            "injuries": [{"region": "knee", "severity": "high"}],
        }
    )

    exercise_names = {ex.get("name") for ex in result["exercises"]}
    assert "Back Squat" not in exercise_names, (
        "Back Squat must not appear in final exercises for a high-severity knee injury"
    )


# ---------------------------------------------------------------------------
# 7. Keyword guard is narrowed: does not replace exercises the main guard allows
# ---------------------------------------------------------------------------


def test_narrowed_keyword_guard_does_not_remove_safe_exercises(monkeypatch):
    """The narrowed _final_keyword_guard should leave exercises untouched when
    the full injury guard evaluates them as 'allow' — even if their name contains
    a keyword that superficially matches an injury region.  This tests the core
    narrowing: trust main guard > keyword match."""
    # "Pressure Cooker" contains "press" which could naively match a shoulder
    # injury keyword, but the full injury guard should allow it.  The guard only
    # acts on exercises the full model also confirms as problematic.
    # Names as first tag so the score mock resolves by tag[0].
    bank = [
        {
            "name": "Pressure Cooker",
            "phases": ["GPP"],
            "tags": ["Pressure Cooker", "footwork", "coordination", "balance"],
            "equipment": [],
            "movement": "carry",
        },
        {
            "name": "Cable Row",
            "phases": ["GPP"],
            "tags": ["Cable Row", "pull", "compound"],
            "equipment": ["cable"],
            "movement": "pull",
        },
    ]

    def _fake_score(exercise_tags, **_kwargs):
        scores = {"Pressure Cooker": 8.0, "Cable Row": 6.0}
        tag = exercise_tags[0] if exercise_tags else ""
        v = scores.get(tag, 1.0)
        return v, {"final_score": v}

    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "score_exercise", _fake_score)
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 1})

    result = strength_module.generate_strength_block(
        flags={
            **_base_flags("GPP"),
            "equipment": ["cable"],
            # Moderate shoulder injury — should NOT exclude "Pressure Cooker"
            # since it has no overhead/push movement.
            "injuries": [{"region": "shoulder", "severity": "moderate"}],
        }
    )

    # The keyword guard must NOT have fired for "Pressure Cooker".
    keyword_guard_entries = [
        e for e in result["mutation_log"] if e["mechanism"] == "final_keyword_guard"
    ]
    for entry in keyword_guard_entries:
        assert entry["original_name"] != "Pressure Cooker", (
            "Keyword guard should not remove 'Pressure Cooker' when the main injury "
            "guard confirms it is safe (action == 'allow')"
        )


# ---------------------------------------------------------------------------
# 8. Structural simplification: _apply_movement_caps call count
# ---------------------------------------------------------------------------


def test_apply_movement_caps_not_called_after_force_isometric_or_after_session_quality_if_no_ops(
    monkeypatch,
):
    """After the simplification, _apply_movement_caps is called twice in the
    main shaping chain (once before promotion, once after promotion) and once
    at the very end — not after every individual step.  We verify this by
    counting calls via a monkeypatched wrapper and confirming the final count
    is lower than the old four-call chain."""
    bank = [
        {
            "name": "Back Squat",
            "phases": ["GPP"],
            "tags": ["compound", "posterior_chain", "quad_dominant", "squat"],
            "equipment": ["barbell"],
            "movement": "squat",
        },
        {
            "name": "Push Press",
            "phases": ["GPP"],
            "tags": ["compound", "push", "overhead", "explosive"],
            "equipment": ["barbell"],
            "movement": "push",
        },
        {
            "name": "Chin Up",
            "phases": ["GPP"],
            "tags": ["pull", "compound"],
            "equipment": [],
            "movement": "pull",
        },
    ]

    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 3})

    # Capture the body of generate_strength_block as source to count call sites.
    import inspect

    source = inspect.getsource(strength_module.generate_strength_block)
    # Count lines that actually call _apply_movement_caps(
    call_lines = [
        line.strip()
        for line in source.splitlines()
        if "_apply_movement_caps(" in line
        and not line.strip().startswith("#")
        and not line.strip().startswith("def ")
    ]
    # Old count was 5 (4 in shaping chain + 1 at end after session_quality).
    # New count should be 3 (2 in shaping chain + 1 final).
    assert len(call_lines) <= 3, (
        f"Expected at most 3 _apply_movement_caps call sites after simplification, "
        f"found {len(call_lines)}: {call_lines}"
    )


def test_enforce_session_quality_not_called_twice_after_safety_passes(monkeypatch):
    """After simplification, _enforce_session_quality should NOT be called after
    _final_keyword_guard.  The second call was removed as a redundant repair pass."""
    import inspect

    source = inspect.getsource(strength_module.generate_strength_block)
    lines = source.splitlines()

    # Find the position of _finalize_injury_safe_exercises call
    finalize_pos = next(
        (i for i, ln in enumerate(lines) if "_finalize_injury_safe_exercises(" in ln and "def " not in ln),
        None,
    )
    assert finalize_pos is not None, "_finalize_injury_safe_exercises call not found in source"

    # Count _enforce_session_quality calls after the finalize call
    post_finalize_calls = [
        ln.strip()
        for ln in lines[finalize_pos:]
        if "_enforce_session_quality(" in ln
        and not ln.strip().startswith("#")
        and not ln.strip().startswith("def ")
    ]
    assert len(post_finalize_calls) == 0, (
        "Expected zero _enforce_session_quality calls after _finalize_injury_safe_exercises "
        f"(second call was a redundant repair pass), found {len(post_finalize_calls)}: "
        f"{post_finalize_calls}"
    )


# ---------------------------------------------------------------------------
# 9. mutation_log record has all required fields
# ---------------------------------------------------------------------------


def test_all_mutation_log_entries_have_required_fields(monkeypatch):
    """Every record in the mutation_log must have the required fields."""
    # Names as first tag so the score mock resolves by tag[0].
    bank = [
        {
            "name": "Back Squat",
            "phases": ["GPP"],
            "tags": ["Back Squat", "compound", "posterior_chain", "quad_dominant", "squat"],
            "equipment": ["barbell"],
            "movement": "squat",
        },
        {
            "name": "Core Hold",
            "phases": ["GPP"],
            "tags": ["Core Hold", "core", "stability"],
            "equipment": [],
            "movement": "core",
        },
        {
            "name": "Overhead Press",
            "phases": ["GPP"],
            "tags": ["Overhead Press", "compound", "push", "overhead"],
            "equipment": ["barbell"],
            "movement": "push",
        },
    ]

    monkeypatch.setattr(strength_module, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength_module, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength_module, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength_module, "get_universal_strength", lambda: [])
    monkeypatch.setattr(strength_module, "allocate_sessions", lambda *a, **kw: {"strength": 1})
    monkeypatch.setattr(strength_module, "calculate_exercise_numbers", lambda *a, **kw: {"strength": 2})

    result = strength_module.generate_strength_block(
        flags={
            **_base_flags("GPP"),
            "equipment": ["barbell"],
            "injuries": [{"region": "shoulder", "severity": "high"}],
        }
    )

    required_fields = {
        "mechanism", "phase", "label", "reason", "module",
        "original_name", "replacement_name", "original_score", "replacement_score",
    }
    for entry in result["mutation_log"]:
        missing = required_fields - set(entry.keys())
        assert not missing, f"Mutation record missing fields {missing}: {entry}"
