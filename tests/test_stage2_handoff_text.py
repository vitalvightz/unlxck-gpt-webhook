from fightcamp.stage2_payload import build_stage2_handoff_text


def test_build_stage2_handoff_text_uses_planning_brief_as_single_structured_context():
    planning_brief = {
        "athlete_snapshot": {"sport": "boxing", "status": "amateur"},
        "restrictions": [{"restriction": "heavy_overhead_pressing"}],
        "candidate_pools": {"SPP": {"strength_slots": [{"role": "primary_strength"}]}},
        "omission_ledger": {"SPP": {"removed": ["push press"]}},
        "decision_rules": {"selection_rules": ["Prefer strong compliant same-role options first."]},
    }
    handoff = build_stage2_handoff_text(
        stage2_payload={
            "athlete_model": {"sport": "boxing"},
            "restrictions": [{"restriction": "heavy_overhead_pressing"}],
            "phase_briefs": {"SPP": {"objective": "fight-specific power"}},
            "candidate_pools": {"SPP": {"strength_slots": [{"role": "primary_strength"}]}},
            "omission_ledger": {"SPP": {"removed": ["push press"]}},
            "rewrite_guidance": {"selection_rules": ["Prefer strong compliant same-role options first."]},
        },
        plan_text="Week 1\n- Landmine Press - 4x5",
        coach_notes="Keep this coach-facing note short.",
        planning_brief=planning_brief,
    )
    json_body = handoff.split("```json\n", 1)[1].split("\n```", 1)[0]

    assert "PLANNING BRIEF" in handoff
    assert '"athlete_snapshot"' in handoff
    assert '"candidate_pools"' in handoff
    assert "COACH NOTES\nKeep this coach-facing note short." in handoff
    assert "STAGE 1 DRAFT PLAN\nWeek 1\n- Landmine Press - 4x5" in handoff
    assert json_body.startswith('{"athlete_snapshot":{"sport":"boxing","status":"amateur"}')
    assert '\n  "' not in json_body
    assert "ATHLETE PROFILE" not in handoff
    assert "RESTRICTIONS\n```json" not in handoff
    assert "PHASE BRIEFS" not in handoff
    assert "CANDIDATE POOLS\n```json" not in handoff
    assert "OMISSION LEDGER\n```json" not in handoff
    assert "REWRITE GUIDANCE" not in handoff
