from __future__ import annotations

from typing import Any


_OPEN_PLAN_STRUCTURE = [
    "Immediate Coach Summary",
    "Current Training Rules",
    "Weekly Rhythm",
    "Session Cards",
    "4-Week Development Block",
    "Progression Rules",
    "Priority Hierarchy",
    "Adjustment Rules",
    "Rehab / Red Flags",
    "4-Week Reassessment Gate",
]

_FORBIDDEN_TERMS = [
    "GPP",
    "SPP",
    "TAPER",
    "D-",
    "fight week",
    "fight-day",
    "countdown",
    "taper week",
]


def _uses_open_ongoing_payload(athlete_model: dict[str, Any]) -> bool:
    if not isinstance(athlete_model, dict):
        return False

    days_until_fight = athlete_model.get("days_until_fight")
    fight_date = athlete_model.get("fight_date")
    next_fight_date = athlete_model.get("next_fight_date")

    if isinstance(days_until_fight, int):
        return False
    try:
        int(days_until_fight)
        return False
    except (TypeError, ValueError):
        pass

    if fight_date:
        return False
    if next_fight_date:
        return False

    no_scheduled_fight = athlete_model.get("no_scheduled_fight")
    if isinstance(no_scheduled_fight, bool):
        return no_scheduled_fight

    return True


def build_open_ongoing_payload(*, athlete_model: dict[str, Any]) -> dict[str, Any]:
    return {
        "payload_mode": "open_ongoing_payload",
        "render_mode": "open_ongoing_system",
        "open_plan_spec": {
            "plan_type": "open_ongoing_system",
            "structure": list(_OPEN_PLAN_STRUCTURE),
            "forbidden_terms": list(_FORBIDDEN_TERMS),
            "render_rules": [
                "Render a renewable open training system, not a fight camp.",
                "Use the exact section order from open_plan_spec.structure.",
                "Render one Weekly Rhythm section only.",
                "Render app-owned days as session cards using Objective/Main work/Fallback/Rehab / mobility/Coach note/Stop rule.",
                "Do not render GPP/SPP/TAPER headings, countdown labels, D-day labels, fight-week rules, or fight-day protocol.",
                "Use 4-Week Development Block + 4-Week Reassessment Gate instead of fixed phase blocks.",
                "Preserve safety, medical stop rules, weight-cut adjustments, and fatigue adjustments.",
                "Do not expose internal scoring, candidate pools, raw tags, or unused options.",
            ],
            "weekly_template": {
                "training_days": athlete_model.get("training_days") or [],
                "hard_sparring_days": athlete_model.get("hard_sparring_days") or [],
                "support_work_days": athlete_model.get("support_work_days") or [],
                "coach_owned_days": {
                    "technical_skill_days": athlete_model.get("technical_skill_days") or [],
                    "hard_sparring_days": athlete_model.get("hard_sparring_days") or [],
                    "support_work_days": athlete_model.get("support_work_days") or [],
                },
            },
            "development_block": {
                "week_1": "Baseline and technical consistency",
                "week_2": "Small progression",
                "week_3": "Highest controlled week",
                "week_4": "Deload and reassess",
            },
            "priority_hierarchy": [
                "Protect restrictions and injury constraints first",
                "Preserve declared hard sparring and contact schedule",
                "Keep one main adaptation focus + one limiter focus",
                "Use support work only after anchor quality is protected",
            ],
            "adjustment_rules": [
                "If symptoms or red flags rise, reduce optional conditioning first.",
                "If fatigue stays high, trim volume before trimming key anchor quality.",
                "If weight-cut pressure rises, preserve recovery margin and remove low-priority extras.",
            ],
        },
    }
