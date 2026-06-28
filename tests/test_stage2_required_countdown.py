from fightcamp.stage2_pipeline import build_stage2_retry, review_stage2_output


def _brief_with_required_d3() -> dict:
    return {
        "athlete_model": {"sport": "boxing", "days_until_fight": 5},
        "restrictions": [],
        "phase_strategy": {},
        "candidate_pools": {},
        "late_fight_plan_spec": {
            "days_out_bucket": "D-5",
            "payload_mode": "late_fight_transition_payload",
            "visible_session_sequence": [
                {
                    "session_index": 1,
                    "category": "recovery",
                    "role_key": "fight_week_freshness_day",
                    "scheduled_countdown_label": "D-3",
                    "countdown_display_label": "D-3 (Wednesday)",
                    "scheduled_day_hint": "wednesday",
                    "real_weekday": "wednesday",
                    "stress_class": "support",
                },
                {
                    "session_index": 2,
                    "category": "strength",
                    "role_key": "neural_primer_day",
                    "scheduled_countdown_label": "D-1",
                    "countdown_display_label": "D-1 (Friday)",
                    "scheduled_day_hint": "friday",
                    "real_weekday": "friday",
                    "stress_class": "meaningful_stress",
                },
            ],
            "allowed_exercises_by_day": {
                "D-3": ["Mobility Reset Flow", "Breathing Reset"],
                "D-1": ["Technical Shadowboxing Tempo", "Breathing Reset"],
            },
        },
    }


def _blocking_codes(review: dict) -> set[str]:
    return {
        warning["code"]
        for warning in review["validator_report"].get("blocking_warnings", [])
    }


def test_review_stage2_output_retries_when_required_d3_freshness_card_is_omitted():
    review = review_stage2_output(
        planning_brief=_brief_with_required_d3(),
        final_plan_text="""
        D-1 (Friday) — Final neural primer
        - Technical Shadowboxing Tempo — 2 light rounds
        - Breathing Reset — 3 min

        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    assert review["status"] == "WARN"
    assert review["needs_retry"] is True
    assert review["validator_report"]["is_publishable"] is False
    assert "late_fight_missing_required_countdown_session" in _blocking_codes(review)
    assert any("D-3 (Wednesday)" in line for line in review["summary_lines"])


def test_review_stage2_output_passes_when_required_d3_freshness_card_is_rendered():
    review = review_stage2_output(
        planning_brief=_brief_with_required_d3(),
        final_plan_text="""
        D-3 (Wednesday) — Freshness Reset
        - Mobility Reset Flow — 6 min
        - Breathing Reset — 3 min

        D-1 (Friday) — Final neural primer
        - Technical Shadowboxing Tempo — 2 light rounds
        - Breathing Reset — 3 min

        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    assert review["status"] == "PASS"
    assert review["needs_retry"] is False
    assert review["validator_report"]["is_publishable"] is True


def test_build_stage2_retry_prompts_when_required_countdown_card_is_missing():
    stage1_result = {
        "planning_brief": _brief_with_required_d3(),
        "stage2_payload": {"schema_version": "stage2_payload.v1"},
        "stage2_handoff_text": "handoff",
    }
    retry = build_stage2_retry(
        stage1_result=stage1_result,
        final_plan_text="""
        D-1 (Friday) — Final neural primer
        - Technical Shadowboxing Tempo — 2 light rounds

        D-0 (Saturday) — Fight day protocol
        - Fight day protocol only — follow coach warm-up and fight protocol.
        """,
    )

    assert retry["needs_retry"] is True
    assert retry["repair_prompt"] is not None
    assert "late_fight_missing_required_countdown_session" in retry["repair_prompt"]
    assert "D-3 (Wednesday)" in retry["repair_prompt"]
