from fightcamp.stage2_payload import build_stage2_handoff_text


def test_build_stage2_handoff_text_restores_salience_sections_around_planning_brief():
    planning_brief = {
        "athlete_snapshot": {
            "sport": "boxing",
            "status": "amateur",
            "hard_sparring_days": ["Tuesday", "Saturday"],
        },
        "main_limiter": "Primary limiter is gas tank under late-round pace.",
        "limiter_profile": {"key": "aerobic_repeatability"},
        "archetype_summary": {"style_focus": "pressure_fighter"},
        "phase_strategy": {"SPP": {"objective": "fight-specific power"}},
        "weekly_role_map": {"weeks": [{"phase": "SPP", "session_roles": [{"role_key": "fight_pace_repeatability_day"}]}]},
        "restrictions": [{"restriction": "heavy_overhead_pressing"}],
        "main_risks": ["Hard sparring already owns the highest collision load."],
        "global_priorities": {"push": ["Keep the main neural day away from hard sparring."]},
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

    assert "ATHLETE SNAPSHOT" in handoff
    assert "LIMITER AND ARCHETYPE" in handoff
    assert "PHASE STRATEGY" in handoff
    assert "WEEKLY EXECUTION MAP" in handoff
    assert "CONSTRAINTS AND OMISSIONS" in handoff
    assert "REWRITE GUIDANCE" in handoff
    assert "PLANNING BRIEF" in handoff
    assert '"athlete_snapshot"' in handoff
    assert '"hard_sparring_days":["Tuesday","Saturday"]' in handoff
    assert '"main_limiter":"Primary limiter is gas tank under late-round pace."' in handoff
    assert '"archetype_summary":{"style_focus":"pressure_fighter"}' in handoff
    assert '"weekly_role_map":{"weeks":[{"phase":"SPP","session_roles":[{"role_key":"fight_pace_repeatability_day"}]}]}' in handoff
    assert '"candidate_pools"' in handoff
    assert "COACH NOTES\nKeep this coach-facing note short." in handoff
    assert "STAGE 1 DRAFT PLAN\nWeek 1\n- Landmine Press - 4x5" in handoff
    assert json_block.startswith("```json\n")
    assert json_block.endswith("\n```")
    assert json_body.startswith('{"athlete_snapshot":{"sport":"boxing","status":"amateur","hard_sparring_days":["Tuesday","Saturday"]}')
    assert '\n  "' not in json_body


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
    assert "If the main limiter is only indirectly trained on a given day, say that plainly" in handoff
    assert "Do not write visible count summaries such as '4 active sessions', 'Conditioning count = ...', or similar week-summary math." in handoff
    assert "If a day is explicitly off, rest, optional, or mobility-only, label it that way rather than presenting it as an active session." in handoff


def test_build_stage2_handoff_text_explicitly_preserves_mindset_blocks():
    handoff = build_stage2_handoff_text(
        stage2_payload={},
        plan_text="Week 1\n- Landmine Press - 4x5",
        planning_brief={"athlete_snapshot": {"sport": "boxing", "mental_blocks": ["confidence"]}},
    )

    assert "RULE 6A - MINDSET CARRY-THROUGH" in handoff
    assert "Do not drop athlete_snapshot.mental_blocks just because the main physical limiter is elsewhere." in handoff
    assert "Retain a short summary-level mindset acknowledgement when mental_blocks are present." in handoff
