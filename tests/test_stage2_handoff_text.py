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
    json_block = handoff.split("PLANNING BRIEF\n", 1)[1].split("\n\n---\n\n", 1)[0]
    json_body = json_block.removeprefix("```json\n").removesuffix("\n```")

    assert "PLANNING BRIEF" in handoff
    assert '"athlete_snapshot"' in handoff
    assert '"candidate_pools"' in handoff
    assert "COACH NOTES\nKeep this coach-facing note short." in handoff
    assert "STAGE 1 DRAFT PLAN\nWeek 1\n- Landmine Press - 4x5" in handoff
    assert json_block.startswith("```json\n")
    assert json_block.endswith("\n```")
    assert json_body.startswith('{"athlete_snapshot":{"sport":"boxing","status":"amateur"}')
    assert '\n  "' not in json_body
    assert "ATHLETE PROFILE" not in handoff
    assert "RESTRICTIONS\n[" not in handoff
    assert "PHASE BRIEFS" not in handoff
    assert "CANDIDATE POOLS\n{" not in handoff
    assert "OMISSION LEDGER\n{" not in handoff
    assert "REWRITE GUIDANCE" not in handoff


def test_build_stage2_handoff_text_carries_surgical_voice_rules():
    handoff = build_stage2_handoff_text(
        stage2_payload={},
        plan_text="Week 1\n- Landmine Press - 4x5",
        planning_brief={"athlete_snapshot": {"sport": "boxing"}},
    )

    assert "Coach voice should feel decisive, respectful, and gym-realistic." in handoff
    assert "make the call, give a short why" in handoff
    assert "at most two practical options" in handoff
    assert "Do not open corrective lines with 'focus on', 'ensure', 'make sure', or 'it's important to'." in handoff
    assert "Do not rely on generic motivation such as 'stay consistent', 'trust the process', 'push yourself', or 'you've got this'." in handoff
    assert "If fatigue is high or fight-week pressure is active, reduce optionality" in handoff
    assert "If injury management is active, lead with constraints, substitutions, or stop rules" in handoff
    assert "Do not write visible count summaries such as '4 active sessions', 'Conditioning count = ...', or similar week-summary math." in handoff
    assert "If a day is explicitly off, rest, optional, or mobility-only, label it that way rather than presenting it as an active session." in handoff
