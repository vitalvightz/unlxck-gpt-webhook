from __future__ import annotations

from fightcamp.stage2_late_fight_utils import late_fight_block_cap, resolve_late_fight_window


def late_fight_planning_brief(days_until_fight: int) -> dict:
    window = resolve_late_fight_window(payload={}, athlete={"days_until_fight": days_until_fight})
    return {
        "athlete_model": {
            "sport": "boxing",
            "equipment": ["bike", "bands", "bodyweight"],
            "days_until_fight": days_until_fight,
            "readiness_flags": ["fight_week"],
        },
        "phase_strategy": {},
        "candidate_pools": {},
        "days_out_payload": {"late_fight_window": window},
        "late_fight_plan_spec": {"block_cap": late_fight_block_cap(days_until_fight)},
    }
