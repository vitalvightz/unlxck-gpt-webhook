"""Coverage for the mandatory bank-driven Fight Visualisation countdown protocol."""
from __future__ import annotations

import pytest

from api.structured_plan_faithfulness import (
    repair_locked_tactical_watch_source_text,
    strip_locked_sessions_for_conversion,
)
from api.structured_plan_generation import build_structured_plan_prompt
from api.structured_plan_locked_merge import merge_locked_structured_content
from fightcamp.fight_visualization_library import (
    FIGHT_VISUALIZATION_COUNTDOWN_DAYS,
    all_visualizations,
    build_visualization_display_text,
    select_fight_visualization,
    visualization_metadata,
)
from fightcamp.gap_fill_inserts import (
    ZERO_COST_INSERTS,
    apply_gap_fill_inserts,
    budgeted_insert_count,
    consumes_insert_budget,
)


def _athlete(**overrides):
    model = {
        "sport": "boxing",
        "style_tactical": ["pressure_fighter"],
        "days_until_fight": 14,
        "training_days": [
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
        ],
    }
    model.update(overrides)
    return model


def _role(offset, role_key, **extra):
    role = {
        "role_key": role_key,
        "category": extra.pop("category", "sparring"),
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }
    role.update(extra)
    return role


def _visualizations(sequence):
    return {
        role["countdown_offset"]: role
        for role in sequence
        if role.get("role_key") == "fight_visualization"
    }


# --------------------------------------------------------------------------
# Bank integrity
# --------------------------------------------------------------------------


def test_bank_loads_and_covers_every_mandatory_countdown_day():
    entries = all_visualizations()
    assert 40 <= len(entries) <= 60
    assert {entry.countdown_day for entry in entries} == set(
        FIGHT_VISUALIZATION_COUNTDOWN_DAYS
    )


def test_bank_records_stay_concise():
    for entry in all_visualizations():
        assert 3 <= len(entry.instructions) <= 6, entry.key
        words = len(" ".join((entry.why, *entry.instructions, entry.cue)).split())
        assert 30 <= words <= 120, (entry.key, words)


def test_bank_avoids_outcome_imagery_and_motivational_language():
    banned = (
        "unstoppable", "knocking them out", "knockout", "visualise victory",
        "inner warrior", "destiny", "champion mindset", "you will win",
    )
    for entry in all_visualizations():
        blob = " ".join((entry.why, *entry.instructions, entry.cue)).lower()
        for phrase in banned:
            assert phrase not in blob, (entry.key, phrase)


@pytest.mark.parametrize(
    "countdown_day,expected_name,duration",
    [
        (7, "Tactical Picture", (6, 8)),
        (5, "Read → React", (5, 7)),
        (3, "Pressure → Reset", (4, 6)),
        (1, "Familiar & Ready", (3, 5)),
        (0, "Trust → Compete", (1, 3)),
    ],
)
def test_countdown_day_identity_and_duration(countdown_day, expected_name, duration):
    entry = select_fight_visualization("boxing", "counter_striker", countdown_day)
    assert entry.name == expected_name
    assert entry.duration_min == duration


# --------------------------------------------------------------------------
# Selection intelligence
# --------------------------------------------------------------------------


def test_style_drives_distinct_d7_content_within_one_sport():
    pressure = select_fight_visualization("boxing", "pressure_fighter", 7)
    counter = select_fight_visualization("boxing", "counter_striker", 7)
    distance = select_fight_visualization("boxing", "distance_striker", 7)
    keys = {pressure.key, counter.key, distance.key}
    assert len(keys) == 3
    assert len({p.instructions for p in (pressure, counter, distance)}) == 3
    # Exact matches, so no fallback was needed.
    assert not any(entry.fallback_reason for entry in (pressure, counter, distance))


def test_same_style_differs_across_sports():
    boxing = select_fight_visualization("boxing", "distance_striker", 7)
    mma = select_fight_visualization("mma", "distance_striker", 7)
    assert boxing.key != mma.key
    assert boxing.instructions != mma.instructions
    # MMA content is genuinely MMA, not boxing copy with a word swapped.
    assert any("level change" in line for line in mma.instructions)


def test_boxing_pressure_family_resolves_through_existing_taxonomy():
    # Boxing keeps its historical `brawler` programming key for the pressure
    # family; the athlete's declared label must still land on it.
    assert select_fight_visualization("boxing", "pressure_fighter", 7).key.startswith(
        "boxing.brawler"
    )
    assert select_fight_visualization("mma", "pressure_fighter", 7).key.startswith(
        "mma.pressure_fighter"
    )


@pytest.mark.parametrize(
    "sport,expected_family",
    [("muay_thai", "kickboxing"), ("bjj", "mma"), ("wrestling", "mma"), ("karate", "kickboxing")],
)
def test_compatible_sport_fallback_is_reported(sport, expected_family):
    entry = select_fight_visualization(sport, "counter_striker", 7)
    assert entry.key.startswith(expected_family)
    assert entry.fallback_reason == "compatible_sport_fallback"


def test_impossible_combination_falls_to_sport_generic_not_another_style():
    entry = select_fight_visualization("boxing", "grappler", 7)
    assert entry.key == "boxing.generic.d7.tactical_picture"
    assert entry.fallback_reason == "sport_incompatible_tactical_style"
    # Never silently served another fighting style's prescription.
    assert entry.styles == ("generic",)


def test_unknown_sport_falls_back_cross_sport():
    entry = select_fight_visualization("underwater_fencing", "hybrid", 3)
    assert entry.key == "cross_sport.generic.d3.pressure_reset"
    assert entry.fallback_reason == "cross_sport_fallback"


def test_d1_and_d0_share_content_across_styles_but_selector_keeps_the_style():
    styles = ["pressure_fighter", "counter_striker", "distance_striker"]
    for countdown_day in (1, 0):
        entries = [
            select_fight_visualization("boxing", style, countdown_day) for style in styles
        ]
        assert len({entry.key for entry in entries}) == 1
        # The style is still resolved and reported, it just does not fork content.
        assert [entry.requested_style for entry in entries] == ["brawler"] + styles[1:]


def test_selection_is_deterministic():
    first = select_fight_visualization("mma", "grappler", 3)
    second = select_fight_visualization("mma", "grappler", 3)
    assert first == second


def test_non_countdown_day_returns_nothing():
    for day in (14, 8, 6, 4, 2):
        assert select_fight_visualization("boxing", "brawler", day) is None


# --------------------------------------------------------------------------
# Placement, coexistence and load
# --------------------------------------------------------------------------


def test_exact_countdown_placement():
    sequence = apply_gap_fill_inserts(
        [_role(12, "hard_sparring_day"), _role(9, "strength_day", category="strength")],
        _athlete(),
    )
    assert set(_visualizations(sequence)) == {7, 5, 3, 1, 0}


def test_persists_on_hard_sparring_and_technical_combat_days():
    sequence = apply_gap_fill_inserts(
        [
            _role(7, "hard_sparring_day"),
            _role(3, "technical_touch_day", category="technical"),
        ],
        _athlete(),
    )
    placed = _visualizations(sequence)
    assert set(placed) == {7, 5, 3, 1, 0}
    day_keys = {
        role["role_key"] for role in sequence if role["countdown_offset"] == 7
    }
    assert {"hard_sparring_day", "fight_visualization"} <= day_keys


def test_persists_with_zero_physical_load_and_no_training_days():
    sequence = apply_gap_fill_inserts(
        [_role(10, "technical_touch_day", category="technical")],
        _athlete(training_days=[]),
    )
    assert set(_visualizations(sequence)) == {7, 5, 3, 1, 0}


def test_persists_on_a_crowded_day_without_displacing_existing_work():
    crowded = [
        _role(3, "hard_sparring_day"),
        _role(3, "neural_primer_day", category="strength"),
    ]
    sequence = apply_gap_fill_inserts(crowded, _athlete())
    day3 = [role["role_key"] for role in sequence if role["countdown_offset"] == 3]
    assert "hard_sparring_day" in day3
    assert "neural_primer_day" in day3
    assert "fight_visualization" in day3


def test_carries_zero_physical_load():
    sequence = apply_gap_fill_inserts([_role(12, "hard_sparring_day")], _athlete())
    for role in _visualizations(sequence).values():
        assert role["rpe_max"] == 1
        assert role["stress_class"] == "support"
        assert role["support_insert_cost_category"] == "zero_cost"
        assert role["support_insert_category"] == "mental"
        assert role["governance"]["meaningful_stress"] is False
        assert role["mechanical_load_regions"] == []


def test_consumes_no_support_insert_budget():
    assert "fight_visualization" in ZERO_COST_INSERTS
    assert consumes_insert_budget("fight_visualization") is False
    sequence = apply_gap_fill_inserts([_role(12, "hard_sparring_day")], _athlete())
    inserts = [role for role in sequence if role.get("category") == "support_insert"]
    budgeted = [role for role in inserts if consumes_insert_budget(role["role_key"])]
    assert budgeted_insert_count(inserts) == len(budgeted)
    assert all(role["role_key"] != "fight_visualization" for role in budgeted)


def test_never_shares_a_day_with_neural_visualization():
    sequence = apply_gap_fill_inserts(
        [_role(12, "hard_sparring_day"), _role(9, "hard_sparring_day")],
        _athlete(days_until_fight=13, fatigue_level="high"),
    )
    by_day: dict[int, set[str]] = {}
    for role in sequence:
        by_day.setdefault(role["countdown_offset"], set()).add(role["role_key"])
    for offset, keys in by_day.items():
        assert not {"fight_visualization", "neural_visualization"} <= keys, offset


def test_d0_coexists_with_the_fight_day_protocol():
    sequence = apply_gap_fill_inserts(
        [_role(12, "hard_sparring_day"), _role(0, "fight_day_protocol", category="fight_day")],
        _athlete(),
    )
    day0 = [role["role_key"] for role in sequence if role["countdown_offset"] == 0]
    assert "fight_day_protocol" in day0
    assert "fight_visualization" in day0


def test_short_notice_camp_only_places_days_inside_the_window():
    sequence = apply_gap_fill_inserts(
        [_role(4, "technical_touch_day", category="technical")],
        _athlete(days_until_fight=4),
    )
    assert set(_visualizations(sequence)) == {3, 1, 0}


def test_never_selected_as_an_ordinary_gap_filler():
    sequence = apply_gap_fill_inserts(
        [_role(20, "hard_sparring_day"), _role(10, "hard_sparring_day")],
        _athlete(days_until_fight=21),
    )
    # Only the mandatory countdown days carry it; no D-15 gap-filler copy.
    assert set(_visualizations(sequence)) == {7, 5, 3, 1, 0}


# --------------------------------------------------------------------------
# Governance and persistence
# --------------------------------------------------------------------------


def test_stage1_owns_locked_governance():
    sequence = apply_gap_fill_inserts([_role(12, "hard_sparring_day")], _athlete())
    role = _visualizations(sequence)[7]
    assert role["role_key"] == "fight_visualization"
    assert role["athlete_facing_label"] == "Fight Visualisation"
    assert role["mandatory_fight_visualization"] is True
    governance = role["governance"]
    assert governance["authority"] == "fight_visualization_library"
    assert governance["mandatory"] is True
    assert governance["selected_drill_locked"] is True
    assert governance["render_selected_drill_exactly"] is True
    assert governance["do_not_reselect_or_generalize"] is True
    assert governance["selected_drill_name"] == role["fight_visualization"]["name"]


@pytest.mark.parametrize("fatigue,expected_duration", [("low", 8), ("high", 6)])
def test_visualization_uses_one_duration_from_source_through_card(fatigue, expected_duration):
    sequence = apply_gap_fill_inserts(
        [_role(12, "hard_sparring_day")], _athlete(fatigue=fatigue)
    )
    role = _visualizations(sequence)[7]
    entry = select_fight_visualization("boxing", "pressure_fighter", 7)
    assert role["prescribed_duration_min"] == expected_duration
    assert role["fight_visualization"]["prescribed_duration_min"] == expected_duration
    assert f"- {entry.name}: {expected_duration} minutes" in role["display_text"]
    assert "6-8 minutes" not in role["display_text"]

    brief = {"weeks": [{"session_roles": [role]}]}
    result = merge_locked_structured_content(_plan_with_day("D-7", []), brief)
    block = result.plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["duration"] == {"value": expected_duration, "unit": "minutes"}


def _locked_brief(entry, day_label="D-3"):
    metadata = visualization_metadata(entry)
    role = {
        "role_key": "fight_visualization",
        "category": "support_insert",
        "scheduled_countdown_label": day_label,
        "countdown_label": day_label,
        "display_text": build_visualization_display_text(entry),
        "mandatory_fight_visualization": True,
        **metadata,
    }
    return {"weeks": [{"session_roles": [role]}]}, role


def _plan_with_day(day_label, sessions):
    return {"weeks": [{"days": [{"countdown_label": day_label, "sessions": sessions}]}]}


def test_stage2_omission_is_repaired_into_the_card():
    entry = select_fight_visualization("mma", "grappler", 3)
    brief, role = _locked_brief(entry)
    plan = _plan_with_day(
        "D-3",
        [{"title": "Technical Combat", "blocks": [{"display_name": "Positional rounds"}]}],
    )
    result = merge_locked_structured_content(plan, brief)
    assert not result.unresolved
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    titles = [session["title"] for session in sessions]
    # Unrelated same-day work is preserved alongside the restored protocol.
    assert "Technical Combat" in titles
    assert "Fight Visualisation" in titles
    restored = next(s for s in sessions if s["title"] == "Fight Visualisation")
    block = restored["blocks"][0]
    assert block["display_name"] == entry.name
    assert block["coaching_cues"][: len(entry.instructions)] == list(entry.instructions)
    assert f"Cue: {entry.cue}" in block["coaching_cues"]
    assert block["duration"] == {"value": entry.duration_min[1], "unit": "minutes"}


def test_stage2_paraphrase_and_rename_are_repaired():
    entry = select_fight_visualization("boxing", "brawler", 3)
    brief, _role = _locked_brief(entry)
    plan = _plan_with_day(
        "D-3",
        [
            {
                "title": "Mental Prep",
                "objective": "Some quiet imagery work.",
                "blocks": [
                    {
                        "display_name": entry.name,
                        "duration": {"value": 20, "unit": "minutes"},
                        "coaching_cues": ["Imagine yourself becoming unstoppable."],
                    }
                ],
            }
        ],
    )
    result = merge_locked_structured_content(plan, brief)
    assert not result.unresolved
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    restored = next(s for s in sessions if s["title"] == "Fight Visualisation")
    block = next(b for b in restored["blocks"] if b["display_name"] == entry.name)
    assert block["coaching_cues"][: len(entry.instructions)] == list(entry.instructions)
    assert "Imagine yourself becoming unstoppable." not in block["coaching_cues"]
    assert restored["objective"] == entry.why


def test_stage2_move_to_another_session_is_repaired_back():
    entry = select_fight_visualization("mma", "clinch_fighter", 5)
    brief, _role = _locked_brief(entry, day_label="D-5")
    plan = _plan_with_day(
        "D-5",
        [
            {
                "title": "Strength",
                "blocks": [
                    {"display_name": "Trap bar deadlift"},
                    {"display_name": entry.name, "coaching_cues": []},
                ],
            }
        ],
    )
    result = merge_locked_structured_content(plan, brief)
    assert not result.unresolved
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    strength = next(s for s in sessions if s["title"] == "Strength")
    assert [b["display_name"] for b in strength["blocks"]] == ["Trap bar deadlift"]
    restored = next(s for s in sessions if s["title"] == "Fight Visualisation")
    assert restored["blocks"][0]["display_name"] == entry.name


def test_empty_shell_session_is_filled_not_duplicated():
    entry = select_fight_visualization("kickboxing", "clinch_fighter", 7)
    brief, _role = _locked_brief(entry, day_label="D-7")
    plan = _plan_with_day("D-7", [{"title": "Fight Visualisation", "blocks": []}])
    result = merge_locked_structured_content(plan, brief)
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["blocks"][0]["coaching_cues"][: len(entry.instructions)] == list(
        entry.instructions
    )


def test_mental_rehearsal_copy_does_not_duplicate_tactical_picture():
    entry = select_fight_visualization("kickboxing", "clinch_fighter", 7)
    brief, _role = _locked_brief(entry, day_label="D-7")
    plan = _plan_with_day("D-7", [{
        "title": "Fight Visualisation",
        "blocks": [
            {"display_name": f"{entry.name} mental rehearsal", "duration": {"value": 6, "unit": "minutes"}},
            {"display_name": entry.name, "duration": {"value": 8, "unit": "minutes"}},
        ],
    }])

    result = merge_locked_structured_content(plan, brief)
    blocks = result.plan["weeks"][0]["days"][0]["sessions"][0]["blocks"]
    assert [block["display_name"] for block in blocks] == [entry.name]
    assert blocks[0]["duration"] == {"value": entry.duration_min[1], "unit": "minutes"}


def test_mental_rehearsal_alias_only_session_is_removed_with_its_block():
    entry = select_fight_visualization("kickboxing", "clinch_fighter", 7)
    brief, _role = _locked_brief(entry, day_label="D-7")
    plan = _plan_with_day("D-7", [
        {"title": "Fight Visualisation", "blocks": [{"display_name": entry.name}]},
        {
            "title": "Mental Rehearsal",
            "completion_status": "not_started",
            "blocks": [{"display_name": f"{entry.name} mental rehearsal"}],
        },
    ])

    result = merge_locked_structured_content(plan, brief)
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    assert [session["title"] for session in sessions] == ["Fight Visualisation"]
    assert [block["display_name"] for block in sessions[0]["blocks"]] == [entry.name]
    assert merge_locked_structured_content(result.plan, brief).plan == result.plan


@pytest.mark.parametrize("day", [3, 5])
def test_named_visualisation_shell_is_reused_for_the_locked_drill(day):
    entry = select_fight_visualization("boxing", "pressure_fighter", day)
    brief, _role = _locked_brief(entry, day_label=f"D-{day}")
    plan = _plan_with_day(f"D-{day}", [{
        "title": entry.name,
        "completion_status": "not_started",
        "blocks": [{"display_name": f"{entry.name} Visualisation", "block_type": "mindset"}],
    }])

    result = merge_locked_structured_content(plan, brief)
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["title"] == "Fight Visualisation"
    assert [block["display_name"] for block in sessions[0]["blocks"]] == [entry.name]
    assert merge_locked_structured_content(result.plan, brief).plan == result.plan


def test_generic_visualisation_shells_do_not_survive_the_locked_d7_card():
    entry = select_fight_visualization("boxing", "pressure_fighter", 7)
    brief, _role = _locked_brief(entry, day_label="D-7")
    plan = _plan_with_day("D-7", [
        {"title": "Fight Visualisation - Range Rehearse", "completion_status": "not_started", "blocks": []},
        {"title": "Fight Visualisation - Mental Rehearse", "completion_status": "not_started", "blocks": [
            {"display_name": "Fight Visualisation", "block_type": "mindset"}
        ]},
        {"title": "Tactical Focus", "blocks": [{"display_name": "First-Round Range Script"}]},
    ])

    result = merge_locked_structured_content(plan, brief)
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    assert [session["title"] for session in sessions] == ["Tactical Focus", "Fight Visualisation"]
    assert sessions[1]["blocks"][0]["display_name"] == entry.name


def test_completed_visualisation_alias_is_preserved():
    entry = select_fight_visualization("boxing", "pressure_fighter", 5)
    brief, _role = _locked_brief(entry, day_label="D-5")
    plan = _plan_with_day("D-5", [{
        "title": entry.name,
        "completion_status": "completed",
        "blocks": [{"display_name": f"{entry.name} Visualisation", "block_type": "mindset"}],
    }])
    result = merge_locked_structured_content(plan, brief)
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    assert len(sessions) == 2
    assert sessions[0]["blocks"][0]["display_name"] == f"{entry.name} Visualisation"
    assert sessions[1]["blocks"][0]["display_name"] == entry.name


def test_completed_mental_rehearsal_session_is_kept():
    entry = select_fight_visualization("kickboxing", "clinch_fighter", 7)
    brief, _role = _locked_brief(entry, day_label="D-7")
    plan = _plan_with_day("D-7", [
        {"title": "Fight Visualisation", "blocks": [{"display_name": entry.name}]},
        {
            "title": "Mental Rehearsal",
            "completion_status": "completed",
            "blocks": [{"display_name": f"{entry.name} mental rehearsal"}],
        },
    ])

    result = merge_locked_structured_content(plan, brief)
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    assert [session["title"] for session in sessions] == ["Fight Visualisation", "Mental Rehearsal"]


def test_mental_rehearsal_session_with_unrelated_work_is_kept():
    entry = select_fight_visualization("kickboxing", "clinch_fighter", 7)
    brief, _role = _locked_brief(entry, day_label="D-7")
    plan = _plan_with_day("D-7", [
        {"title": "Fight Visualisation", "blocks": [{"display_name": entry.name}]},
        {
            "title": "Mental Rehearsal",
            "completion_status": "not_started",
            "blocks": [
                {"display_name": f"{entry.name} mental rehearsal"},
                {"display_name": "Breathing reset"},
            ],
        },
    ])

    result = merge_locked_structured_content(plan, brief)
    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    assert [session["title"] for session in sessions] == ["Fight Visualisation", "Mental Rehearsal"]
    assert [block["display_name"] for block in sessions[1]["blocks"]] == ["Breathing reset"]


def test_missing_day_is_fail_closed():
    entry = select_fight_visualization("boxing", "brawler", 3)
    brief, _role = _locked_brief(entry)
    result = merge_locked_structured_content(_plan_with_day("D-9", []), brief)
    assert not result.applied
    assert result.unresolved[0].reason == "structured day not uniquely resolved"


def test_stage2_source_text_omission_is_repaired():
    entry = select_fight_visualization("boxing", "counter_striker", 3)
    brief, _role = _locked_brief(entry)
    source = "D-3 (Wednesday): Technical Combat\n- Positional rounds: 4 x 3 min\n\nD-0: Fight Day\n"
    result = repair_locked_tactical_watch_source_text(source, brief)
    assert not result.unresolved
    assert result.applied == [f"D-3: {entry.name}"]
    assert "Fight Visualisation" in result.source_markdown
    for instruction in entry.instructions:
        assert instruction in result.source_markdown
    # Repair is scoped to the authoritative day only.
    assert result.source_markdown.index(entry.name) < result.source_markdown.index("D-0:")


def test_locked_visualisation_does_not_enter_structured_model_prompt():
    entry = select_fight_visualization("boxing", "pressure_fighter", 7)
    brief, _role = _locked_brief(entry, day_label="D-7")
    source = (
        "D-7 (Thursday) — Strength\n- Trap Bar Deadlift: 3 x 3\n\n"
        "D-7 (Thursday) — Fight Visualisation\n"
        + build_visualization_display_text(entry)
        + "\n\nD-7 (Thursday) — Fight Visualisation (mental)\n"
        "- Fight Visualisation: 8 minutes\n\nD-6 (Friday) — Recovery\n"
    )
    converted = strip_locked_sessions_for_conversion(source, brief)
    assert "Trap Bar Deadlift" in converted
    assert "D-6 (Friday) — Recovery" in converted
    assert "Fight Visualisation" not in converted
    assert entry.name not in build_structured_plan_prompt(plan_markdown=source, planning_brief=brief)


def test_missing_locked_only_day_is_inserted_by_server_into_source():
    entry = select_fight_visualization("boxing", "pressure_fighter", 5)
    brief, _role = _locked_brief(entry, day_label="D-5")
    result = repair_locked_tactical_watch_source_text(
        "D-6 (Friday) — Recovery\nRest.\n\nD-4 (Sunday) — Technical\nMove lightly.", brief
    )
    assert not result.unresolved
    assert result.source_markdown.index("D-6") < result.source_markdown.index("D-5")
    assert result.source_markdown.index("D-5") < result.source_markdown.index("D-4")
    assert entry.name in result.source_markdown


def test_generic_same_day_visualisation_source_copy_is_removed():
    entry = select_fight_visualization("boxing", "pressure_fighter", 7)
    brief, _role = _locked_brief(entry, day_label="D-7")
    source = (
        "D-7 (Thursday) — Fight Visualisation\n"
        + build_visualization_display_text(entry)
        + "\n\nD-7 (Thursday) — Tactical Focus\n- First-Round Range Script: 8 minutes\n\n"
        "D-7 (Thursday) — Fight Visualisation (mental)\n"
        "Why: Confirm the picture.\n- Fight Visualisation: 8 minutes.\n\n"
        "D-6 (Friday) — Recovery\nRest.\n"
    )
    result = repair_locked_tactical_watch_source_text(source, brief)
    assert result.source_markdown.count("D-7 (Thursday) — Fight Visualisation") == 1
    assert "First-Round Range Script" in result.source_markdown
    assert "D-6 (Friday) — Recovery" in result.source_markdown


def test_deterministic_fallback_defers_to_the_locked_merge():
    from api.structured_plan_deterministic_fallback import _ROLES_OWNED_ELSEWHERE

    assert "fight_visualization" in _ROLES_OWNED_ELSEWHERE


def test_display_text_uses_the_shared_single_activity_shape():
    entry = select_fight_visualization("mma", "hybrid", 7)
    lines = build_visualization_display_text(entry).splitlines()
    assert lines[0].startswith("Why: ")
    assert lines[1].startswith(f"- {entry.name}: ")
    assert "No physical load." in lines[1]
    assert all(line.startswith("  ") for line in lines[2:])
    assert lines[-1] == f"  Cue: {entry.cue}"


def test_d0_display_text_carries_the_optional_pre_bout_version():
    entry = select_fight_visualization("mma", "grappler", 0)
    assert entry.pre_bout
    assert f"  Pre-bout: {entry.pre_bout}" in build_visualization_display_text(entry)


# --------------------------------------------------------------------------
# Tactical Watch is untouched
# --------------------------------------------------------------------------


def test_tactical_watch_still_selected_alongside_fight_visualization():
    sequence = apply_gap_fill_inserts(
        [_role(12, "hard_sparring_day"), _role(7, "hard_sparring_day")], _athlete()
    )
    watches = [role for role in sequence if role["role_key"] == "tactical_watch"]
    assert watches
    for watch in watches:
        assert watch["tactical_watch_key"]
        assert watch["mandatory_tactical_watch"] is True
        assert watch["governance"]["selected_drill_locked"] is True


# --------------------------------------------------------------------------
# Control-flow invariants: the protocol outruns every gap-fill early return
# --------------------------------------------------------------------------


def test_d0_only_plan_still_gets_its_protocol():
    # The gap fill has nothing to do here (no positive countdown offset), which
    # is precisely where an early return used to drop the mandatory D-0 card.
    sequence = apply_gap_fill_inserts(
        [_role(0, "fight_day_protocol", category="fight_day")],
        _athlete(days_until_fight=0),
    )
    assert set(_visualizations(sequence)) == {0}
    assert _visualizations(sequence)[0]["fight_visualization_key"]


def test_empty_stage1_sequence_still_gets_the_protocol():
    sequence = apply_gap_fill_inserts([], _athlete(days_until_fight=7))
    assert set(_visualizations(sequence)) == {7, 5, 3, 1, 0}


def test_sequence_with_no_positive_offsets_still_gets_the_protocol():
    sequence = apply_gap_fill_inserts(
        [_role(0, "fight_day_protocol", category="fight_day")],
        _athlete(days_until_fight=5),
    )
    assert set(_visualizations(sequence)) == {5, 3, 1, 0}


def test_early_return_path_is_still_ordered_and_indexed():
    sequence = apply_gap_fill_inserts([], _athlete(days_until_fight=7))
    offsets = [role["countdown_offset"] for role in sequence]
    assert offsets == sorted(offsets, reverse=True)
    assert [role["session_index"] for role in sequence] == list(
        range(1, len(sequence) + 1)
    )


def test_unanchorable_plan_returns_untouched():
    # No days_until_fight and no countdown offsets: nothing anchors a D-day, so
    # there is no day to place the protocol on.
    sequence = apply_gap_fill_inserts(
        [{"role_key": "primary_strength_day", "category": "strength"}],
        {"sport": "boxing", "style_tactical": ["brawler"]},
    )
    assert not _visualizations(sequence)


# --------------------------------------------------------------------------
# Freshness: an existing role is restamped, never trusted
# --------------------------------------------------------------------------


def test_existing_visualization_is_restamped_from_the_current_athlete():
    stale = _role(3, "fight_visualization", category="support_insert")
    stale.update(
        {
            "fight_visualization_key": "boxing.brawler.d3.pressure_reset",
            "fight_visualization_name": "Pressure → Reset",
            "fight_visualization": {"key": "boxing.brawler.d3.pressure_reset"},
            "display_text": "stale boxing content",
        }
    )
    # The athlete has since become an MMA grappler.
    sequence = apply_gap_fill_inserts(
        [_role(9, "hard_sparring_day"), stale],
        _athlete(sport="mma", style_tactical=["grappler"]),
    )
    restamped = _visualizations(sequence)[3]
    assert restamped["fight_visualization_key"] == "mma.grappler.d3.pressure_reset"
    assert restamped["fight_visualization"]["key"] == "mma.grappler.d3.pressure_reset"
    assert "stale boxing content" not in restamped["display_text"]
    assert "takedown" in restamped["display_text"]


def test_restamp_does_not_duplicate_the_day():
    existing = _role(5, "fight_visualization", category="support_insert")
    sequence = apply_gap_fill_inserts(
        [_role(9, "hard_sparring_day"), existing], _athlete()
    )
    on_d5 = [
        role
        for role in sequence
        if role["countdown_offset"] == 5 and role["role_key"] == "fight_visualization"
    ]
    assert len(on_d5) == 1


# --------------------------------------------------------------------------
# Bank fallback integrity
# --------------------------------------------------------------------------


def test_every_countdown_day_has_exactly_one_universal_fallback():
    for countdown_day in FIGHT_VISUALIZATION_COUNTDOWN_DAYS:
        universal = [
            entry
            for entry in all_visualizations()
            if entry.countdown_day == countdown_day
            and "cross_sport" in entry.sports
            and "generic" in entry.styles
        ]
        assert len(universal) == 1, (countdown_day, [e.key for e in universal])


def test_bank_load_rejects_a_missing_universal_fallback(tmp_path, monkeypatch):
    import json

    from fightcamp import fight_visualization_library as lib

    bank = json.loads((lib.DATA_DIR / "fight_visualization_bank.json").read_text())
    trimmed = [
        entry
        for entry in bank
        if not (entry["countdown_day"] == 3 and entry["sports"] == ["cross_sport"])
    ]
    (tmp_path / "fight_visualization_bank.json").write_text(json.dumps(trimmed))
    monkeypatch.setattr(lib, "DATA_DIR", tmp_path)
    lib.all_visualizations.cache_clear()
    try:
        with pytest.raises(lib.FightVisualizationBankError, match="D-3 needs exactly one"):
            lib.all_visualizations()
    finally:
        lib.all_visualizations.cache_clear()


def test_bank_load_rejects_a_duplicate_universal_fallback(tmp_path, monkeypatch):
    import json

    from fightcamp import fight_visualization_library as lib

    bank = json.loads((lib.DATA_DIR / "fight_visualization_bank.json").read_text())
    twin = dict(
        next(e for e in bank if e["countdown_day"] == 0 and e["sports"] == ["cross_sport"])
    )
    twin["key"] = twin["key"] + ".twin"
    (tmp_path / "fight_visualization_bank.json").write_text(json.dumps(bank + [twin]))
    monkeypatch.setattr(lib, "DATA_DIR", tmp_path)
    lib.all_visualizations.cache_clear()
    try:
        with pytest.raises(lib.FightVisualizationBankError, match="D-0 needs exactly one"):
            lib.all_visualizations()
    finally:
        lib.all_visualizations.cache_clear()


def test_every_countdown_day_resolves_for_every_supported_sport_and_style():
    from fightcamp.fight_visualization_library import BANK_SPORTS
    from fightcamp.tactical_watch_library import STYLE_FAMILIES

    for sport in (*BANK_SPORTS, "muay_thai", "bjj", "wrestling", "karate", "", "nonsense"):
        for style in (*STYLE_FAMILIES, "", "nonsense"):
            for countdown_day in FIGHT_VISUALIZATION_COUNTDOWN_DAYS:
                entry = select_fight_visualization(sport, style, countdown_day)
                assert entry is not None, (sport, style, countdown_day)
                assert entry.countdown_day == countdown_day


def test_single_bank_cue_fills_one_mindset_slot_not_every_slot():
    """One cue is one claim.

    The Fight Visualisation bank carries a single trusted ``cue`` instead of a
    four-part mindset block. Copying it into intent, focus, reset and anchor
    printed the same sentence three times on the athlete's card, under "Focus",
    "Reset" and "Coach cue".
    """
    from api.structured_plan_locked_merge import _mindset_anchor

    anchor = _mindset_anchor({"cue": "Take the space, do not chase it."})

    assert anchor["intent"] == "Take the space, do not chase it."
    assert anchor["focus_cue"] == ""
    assert anchor["reset_cue"] == ""
    assert anchor["confidence_anchor"] is None


def test_a_full_mindset_block_keeps_all_of_its_distinct_parts():
    from api.structured_plan_locked_merge import _mindset_anchor

    anchor = _mindset_anchor(
        {
            "cue": "Know the next beat.",
            "mindset": {
                "intent": "Win the second decision.",
                "focus": "Watch the response after the first two punches.",
                "reset": "Smother or leave instead of trading blindly.",
                "anchor": "Know the next beat.",
            },
        }
    )

    assert anchor["intent"] == "Win the second decision."
    assert anchor["focus_cue"] == "Watch the response after the first two punches."
    assert anchor["reset_cue"] == "Smother or leave instead of trading blindly."
    assert anchor["confidence_anchor"] == "Know the next beat."
