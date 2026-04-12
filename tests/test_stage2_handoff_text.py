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
    athlete_profile_block = handoff.split("ATHLETE PROFILE\n", 1)[1].split("\n\n---\n\n", 1)[0]
    athlete_profile_body = athlete_profile_block.removeprefix("```json\n").removesuffix("\n```")

    assert "PLANNING BRIEF" in handoff
    assert "ATHLETE PROFILE" in handoff
    assert '"athlete_snapshot"' in handoff
    assert '"candidate_pools"' in handoff
    assert "COACH NOTES\nKeep this coach-facing note short." in handoff
    assert "STAGE 1 DRAFT PLAN\nWeek 1\n- Landmine Press - 4x5" in handoff
    assert json_block.startswith("```json\n")
    assert json_block.endswith("\n```")
    assert json_body.startswith('{"athlete_snapshot":{"sport":"boxing","status":"amateur"}')
    assert athlete_profile_block.startswith("```json\n")
    assert athlete_profile_block.endswith("\n```")
    assert athlete_profile_body == '{"sport":"boxing","status":"amateur"}'
    assert '\n  "' not in json_body
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

    # Voice style is present (exact wording may evolve — check concepts)
    assert "decisive" in handoff.lower() or "gym-realistic" in handoff.lower(), (
        "Handoff should convey a decisive, gym-realistic coach voice"
    )
    # Corrective call directive is present
    assert "make the call" in handoff or "corrective" in handoff.lower(), (
        "Handoff should instruct making a clear call on corrections"
    )
    # Option discipline is present
    assert "practical options" in handoff or "two options" in handoff.lower(), (
        "Handoff should limit optionality for the model"
    )
    # Anti-filler directives are present
    assert "focus on" in handoff or "ensure" in handoff or "motivation" in handoff.lower(), (
        "Handoff should contain anti-filler coaching voice directives"
    )
    # Fatigue handling is present
    assert "fatigue" in handoff.lower() and "optionality" in handoff.lower(), (
        "Handoff should address fatigue → reduce optionality"
    )
    # Injury management is present
    assert "injury" in handoff.lower() and ("constraints" in handoff.lower() or "stop rules" in handoff.lower()), (
        "Handoff should address injury → lead with constraints"
    )
