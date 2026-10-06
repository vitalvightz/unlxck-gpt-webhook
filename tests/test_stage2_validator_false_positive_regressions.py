"""Regressions from a held plan whose blockers were mostly validator misreads.

Each test replays lines from that render. The faithful render must pass; a
genuinely over-dosed or out-of-list render must still be caught.
"""

from fightcamp.stage2_validator import (
    _conditioning_dose_within_bounds,
    _countdown_blocks,
    _late_camp_effective_prescription_warnings,
    _late_fight_line_is_exercise_like,
    validate_stage2_output,
)


def test_progress_annotation_is_not_an_exercise() -> None:
    for line in (
        "Progress: next session add one round (4 rounds).",
        "Progress: next time add 30 sec per round.",
        "Regress: 2 rounds only.",
    ):
        assert _late_fight_line_is_exercise_like(line) is False
    assert _late_fight_line_is_exercise_like("- Banded Row (Speed Focus): 4 sets x 2 reps; RPE 7.") is True


def test_equivalent_conditioning_dose_spellings_match() -> None:
    cases = [
        ("5 x 3 min round; RPE 9", "- Double-End Bag Circuit: 5 rounds x 3 min; rest 30 sec (transitions); RPE 9."),
        ("3min work, 1min rest x 3 rounds", "- Ring Escape Flow: 3 rounds x 3 min work; rest 60 sec between rounds; RPE 6."),
        ("2x5s with 120s rest", "- Explosive Straight Burst: 2 sets x 5 sec; rest 120 sec; RPE 6."),
    ]
    for expected, rendered in cases:
        ok, violations, _, _ = _conditioning_dose_within_bounds(expected, rendered)
        assert ok, (expected, rendered, violations)


def test_conditioning_overdose_is_still_caught() -> None:
    cases = [
        ("5 x 3 min round; RPE 9", "- Double-End Bag Circuit: 6 rounds x 3 min; RPE 9.", "rounds exceed effective cap"),
        ("3min work, 1min rest x 3 rounds", "- Ring Escape Flow: 3 rounds x 3 min; rest 30 sec.", "rest below effective floor"),
        ("2x5s with 120s rest", "- Explosive Straight Burst: 2 sets x 8 sec; rest 120 sec.", "work interval exceeds effective cap"),
    ]
    for expected, rendered, violation in cases:
        ok, violations, _, _ = _conditioning_dose_within_bounds(expected, rendered)
        assert not ok
        assert violation in violations


_D0_AND_TRAILER = "\n".join(
    [
        "TAPER — Week 5 (D-5 to D-0) — Fight-week survival rhythm.",
        "D-1 (Friday) — Neural speed touch.",
        "- Shuffle-Angle-Set Cue: 2 x 4 sec; rest 120 sec; RPE 3.",
        "",
        "D-0 (Saturday) — Fight day protocol: follow coach warm-up and fight protocol; no additional S&C.",
        "Fight day protocol: follow coach warm-up and fight protocol; no additional S&C.",
        "",
        "Stop rules and regression notes (applies where relevant).",
        "- Stop: any sharp joint pain or dizziness.",
        "",
        "Progress and safety summary.",
        "- If hard sparring feels harder than usual, swap the next day to extra recovery.",
        "",
        "End of plan.",
    ]
)


def test_plain_text_plan_sections_end_the_d0_block() -> None:
    blocks = _countdown_blocks(_D0_AND_TRAILER)
    d0 = [block for block in blocks if block["day"] == 0]
    assert len(d0) == 1
    assert all("hard sparring" not in line.lower() for line in d0[0]["lines"])


def test_plan_wide_sparring_note_is_not_d0_hard_sparring() -> None:
    report = validate_stage2_output(planning_brief={}, final_plan_text=_D0_AND_TRAILER)
    codes = {item.get("code") for item in report.get("errors") or []}
    assert "late_fight_hard_sparring_violation" not in codes


def test_real_hard_sparring_on_d0_is_still_blocked() -> None:
    text = _D0_AND_TRAILER.replace(
        "Fight day protocol: follow coach warm-up and fight protocol; no additional S&C.\n",
        "Fight day protocol: follow coach warm-up and fight protocol; no additional S&C.\n- Hard sparring 3 x 3 min.\n",
        1,
    )
    report = validate_stage2_output(planning_brief={}, final_plan_text=text)
    codes = {item.get("code") for item in report.get("errors") or []}
    assert "late_fight_hard_sparring_violation" in codes


def _shared_day_brief() -> dict:
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "session_roles": [
                        {
                            "category": "strength",
                            "role_key": "secondary_strength_day",
                            "scheduled_d_day": 26,
                            "effective_strength_envelope": {
                                "scheduled_d_day": 26,
                                "loaded_allowed": True,
                                "complete_exercise_allow_list": True,
                                "allowed_exercise_names": ["Heavy RDL → Broad Jump", "Reactive Start Burst"],
                            },
                        },
                        {
                            "category": "conditioning",
                            "role_key": "controlled_repeatability_day",
                            "scheduled_d_day": 26,
                            "selected_exercise_assignments": [
                                {"name": "Double-End Bag Circuit", "effective_prescription": "5 x 3 min round; RPE 9"}
                            ],
                        },
                    ],
                }
            ]
        }
    }


def test_same_day_conditioning_block_is_not_judged_by_strength_allow_list() -> None:
    rendered = "\n".join(
        [
            "D-26 (Monday) — Strength.",
            "- Heavy RDL → Broad Jump: 3 rounds; heavy movement 2 reps @ 85% 1RM → broad jump 2 reps; rest 180 sec.",
            "Progress: next session add one round (4 rounds).",
            "- Reactive Start Burst: 3 x 4 sec @ RPE 7, full rest.",
            "",
            "D-26 (Monday) — Fight-pace conditioning.",
            "- Double-End Bag Circuit: 5 rounds x 3 min; rest 30 sec (transitions); RPE 9.",
            "Progress: next time add one round.",
        ]
    )
    warnings = _late_camp_effective_prescription_warnings(_shared_day_brief(), rendered)
    assert [item for item in warnings if "exercise_allow_list" in (item.get("violation_dimensions") or [])] == []


def test_unassigned_exercise_on_strength_day_is_still_blocked() -> None:
    rendered = "\n".join(
        [
            "D-26 (Monday) — Strength.",
            "- Heavy RDL → Broad Jump: 3 rounds; heavy movement 2 reps → broad jump 2 reps; rest 180 sec.",
            "- Single-Leg Forward Hops: 3 x 5",
        ]
    )
    warnings = _late_camp_effective_prescription_warnings(_shared_day_brief(), rendered)
    labels = [item["rendered_exercise"] for item in warnings if "exercise_allow_list" in (item.get("violation_dimensions") or [])]
    assert labels == ["Single-Leg Forward Hops"]


def test_goal_witness_rep_dose_accepts_spelled_out_sets() -> None:
    from fightcamp.stage2_validator import _goal_witness_dose_matches

    witness = {
        "name": "Depth Drop (No Rebound)",
        "rounds": 6,
        "work_sec": 3,
        "rest_sec": 90,
        "effective_prescription": "6x3 reps, 90s rest",
    }
    assert _goal_witness_dose_matches(witness, "- Depth Drop (No Rebound): 6 sets x 3 reps; rest 90 sec; RPE 7.")
    assert not _goal_witness_dose_matches(witness, "- Depth Drop (No Rebound): 4 sets x 3 reps; rest 90 sec; RPE 7.")
