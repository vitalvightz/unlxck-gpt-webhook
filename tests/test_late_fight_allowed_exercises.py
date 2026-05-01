from fightcamp.stage2_payload import build_planning_brief


def test_late_fight_planning_brief_exposes_selected_exercises_by_countdown_day():
    brief = build_planning_brief(
        athlete_model={
            "sport": "boxing",
            "days_until_fight": 13,
            "fatigue": "moderate",
            "readiness_flags": [],
        },
        restrictions=[],
        phase_briefs={
            "TAPER": {
                "objective": "fresh sharpness",
                "emphasize": ["speed"],
                "deprioritize": [],
                "risk_flags": [],
                "selection_guardrails": {},
            }
        },
        candidate_pools={
            "TAPER": {
                "strength_slots": [
                    {"role": "strength_touch", "selected": {"name": "Staggered-Stance Medicine-Ball Punch Throw"}}
                ],
                "conditioning_slots": [
                    {"role": "alactic", "selected": {"name": "Reactive Shuffle Repeats"}}
                ],
                "rehab_slots": [
                    {"role": "reset", "selected": {"name": "Breathing Reset"}}
                ],
            }
        },
        omission_ledger={},
        rewrite_guidance={},
    )

    allowed = brief["late_fight_plan_spec"]["allowed_exercises_by_day"]
    assert allowed["D-13"] == [
        "Staggered-Stance Medicine-Ball Punch Throw",
        "Reactive Shuffle Repeats",
        "Breathing Reset",
    ]
    assert "Band-Resisted Sprint Starts (ATP-PCr)" not in allowed["D-13"]
    assert "Band-Resisted Jab-Cross Primer" not in allowed["D-1"]
