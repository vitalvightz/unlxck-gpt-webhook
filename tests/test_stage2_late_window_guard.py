from fightcamp.stage2_pipeline import review_stage2_output


def _late_fight_brief(days_out: str) -> dict:
    return {
        "athlete_model": {
            "sport": "boxing",
            "days_until_fight": int(days_out.split("-")[-1]),
        },
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "late_fight_plan_spec": {
            "payload_mode": "late_fight_session_payload" if days_out in {"D-4", "D-3", "D-2"} else "pre_fight_day_payload",
            "days_out_bucket": days_out,
            "max_active_roles": 10,
            "max_meaningful_stress_exposures": 10,
            "max_blocks_per_session": 10,
            "forbidden_blocks": [],
        },
    }


def _blocking_warning_codes(review: dict) -> set[str]:
    return {
        warning["code"]
        for warning in review["validator_report"].get("warnings", [])
        if warning.get("blocking")
    }


def test_review_stage2_output_blocks_sandbag_shouldering_on_d3():
    review = review_stage2_output(
        planning_brief=_late_fight_brief("D-3"),
        final_plan_text="""
        D-3 (Wednesday) — Fight-week freshness
        - Sandbag Shouldering — 4 x 4–6 reps each side
        - Mobility reset — 4 min
        """,
    )

    assert "late_fight_window_forbidden_exercise" in _blocking_warning_codes(review)
    assert review["needs_retry"] is True


def test_review_stage2_output_blocks_staggered_med_ball_throw_on_d1():
    review = review_stage2_output(
        planning_brief=_late_fight_brief("D-1"),
        final_plan_text="""
        D-1 (Friday) — Final neural primer
        - Staggered-Stance Medicine-Ball Punch Throw — 2 x 3 throws per side
        - Light technical shadowboxing — 2 x 60 sec
        """,
    )

    assert "late_fight_window_forbidden_exercise" in _blocking_warning_codes(review)
    assert review["needs_retry"] is True


def test_review_stage2_output_allows_staggered_med_ball_throw_on_d3():
    review = review_stage2_output(
        planning_brief=_late_fight_brief("D-3"),
        final_plan_text="""
        D-3 (Wednesday) — Final power touch
        - Staggered-Stance Medicine-Ball Punch Throw — 2 x 3 throws per side
        - Mobility reset — 4 min
        """,
    )

    assert "late_fight_window_forbidden_exercise" not in _blocking_warning_codes(review)


def test_review_stage2_output_blocks_sandbag_shouldering_under_subheader_on_d3():
    review = review_stage2_output(
        planning_brief=_late_fight_brief("D-3"),
        final_plan_text="""
        D-3 (Wednesday) — Fight-week freshness
        ### Core Work
        - Sandbag Shouldering — 4 x 4–6 reps each side
        - Mobility reset — 4 min
        """,
    )

    assert "late_fight_window_forbidden_exercise" in _blocking_warning_codes(review)
    assert review["needs_retry"] is True
