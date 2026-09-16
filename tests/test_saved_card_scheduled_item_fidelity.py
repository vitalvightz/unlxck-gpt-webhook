"""A SAVED structured card obeys the same scheduled-item fidelity invariant.

The production failure (structured_plan = null) is fixed by the deterministic
fallback. This is the other half of the contract: when the structured-card model
DOES produce a valid card but silently omits an authoritative scheduled support
insert, the saved card is returned as-is by the resolver — the fallback never
runs — so the restoration has to happen on the shared deterministic path
(`reconcile_calendar_spine`) that `_map_plan_detail` already applies to both.

Each omitted item must come back exactly once; an item the card already carries
must not be duplicated.
"""

from __future__ import annotations

import copy

from api.plan_mappers import _map_plan_detail
from test_structured_plan_models import SCHEMA_VERSION, _valid_plan

FIGHT_DATE = "2026-06-13"

#: D-10 / D-9 / D-3 support inserts, exactly as the production brief stores them:
#: an athlete-facing label, one banked instruction, zero exercise assignments.
SUPPORT_ROLES = [
    (10, "joint_prep", "Joint Prep", "Neck CARs, shoulder CARs, wrist circles, hip circles, and ankle rocks."),
    (9, "breathing_reset", "Breathing Reset", "Nasal breathing, 5 minutes. Finish calmer than you started."),
    (9, "footwork_walkthrough", "Pressure Step-Cut Reset", "Light in-out steps, pivots, and stance resets, RPE 3-4."),
    (3, "technical_shadow_rhythm", "Technical Shadow Rhythm", "Light shadow rhythm only. Smooth entries, exits, and reset cues."),
]


def _brief() -> dict:
    return {
        "fight_date": FIGHT_DATE,
        "days_until_fight": 12,
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "TAPER",
                    "calendar_days": [{"d_day": d_day} for d_day in range(12, -1, -1)],
                    "session_roles": [
                        {
                            "role_key": role_key,
                            "category": "support_insert",
                            "athlete_facing_label": label,
                            "display_text": text,
                            "stress_class": "support",
                            "countdown_offset": d_day,
                            "scheduled_countdown_label": f"D-{d_day}",
                            "selected_exercise_assignments": [],
                        }
                        for d_day, role_key, label, text in SUPPORT_ROLES
                    ],
                }
            ]
        },
    }


def _row(plan: dict) -> dict:
    return {
        "id": "plan-fidelity-1",
        "athlete_id": "athlete-fidelity-1",
        "full_name": "Fidelity Test",
        "status": "generated",
        "plan_text": "# Athlete plan",
        "fight_date": FIGHT_DATE,
        "structured_plan": plan,
        "planning_brief": _brief(),
        "stage2_validator_report": {
            "structured_plan": {"status": "valid", "schema_version": SCHEMA_VERSION}
        },
    }


def _card_omitting_supports() -> dict:
    """A schema-valid card whose D-10 / D-9 / D-3 support inserts are missing."""
    plan = copy.deepcopy(_valid_plan())
    week = plan["weeks"][0]
    template = copy.deepcopy(week["days"][0])
    days = []
    for d_day in (10, 9, 3):
        day = copy.deepcopy(template)
        day["countdown_label"] = f"D-{d_day}"
        day["today_card"]["headline"] = ""
        # D-9 keeps ONE real session; the model dropped the other two items.
        day["sessions"] = day["sessions"] if d_day == 9 else []
        days.append(day)
    week["days"] = days
    return plan


def _sessions_by_dday(detail) -> dict[int, list[str]]:
    found: dict[int, list[str]] = {}
    for week in detail.outputs.structured_plan.weeks:
        for day in week.days:
            label = str(day.countdown_label or "")
            if label.upper().startswith("D-"):
                found[int(label[2:])] = [session.title for session in day.sessions]
    return found


def test_saved_card_omitting_support_inserts_gets_them_back_exactly_once():
    detail = _map_plan_detail(_row(_card_omitting_supports()), include_admin=False)
    sessions = _sessions_by_dday(detail)

    assert "Joint Prep" in sessions[10]
    assert sessions[10].count("Joint Prep") == 1
    assert "Breathing Reset" in sessions[9]
    assert "Pressure Step-Cut Reset" in sessions[9]
    assert sessions[9].count("Pressure Step-Cut Reset") == 1
    assert "Technical Shadow Rhythm" in sessions[3]
    assert sessions[3].count("Technical Shadow Rhythm") == 1


def test_a_support_insert_the_card_already_carries_is_not_duplicated():
    plan = _card_omitting_supports()
    day = next(d for d in plan["weeks"][0]["days"] if d["countdown_label"] == "D-10")
    kept = copy.deepcopy(day["sessions"][0]) if day["sessions"] else None
    if kept is None:
        kept = copy.deepcopy(_valid_plan()["weeks"][0]["days"][0]["sessions"][0])
    kept["title"] = "Joint Prep"
    day["sessions"] = [kept]

    detail = _map_plan_detail(_row(plan), include_admin=False)
    sessions = _sessions_by_dday(detail)

    assert sessions[10].count("Joint Prep") == 1


def test_a_day_with_no_authoritative_role_stays_empty():
    detail = _map_plan_detail(_row(_card_omitting_supports()), include_admin=False)
    sessions = _sessions_by_dday(detail)

    # D-8 carries no scheduled role in the brief, so nothing is invented for it.
    assert sessions[8] == []


def test_two_roles_sharing_a_role_key_both_survive():
    """One card can never stand in for two distinct scheduled items.

    Session identity is ``(d_day, role_key, session_index)``. Matching a role to
    a session by ``role_key`` alone let the first restored session absorb the
    second role, which then looked "already represented" and was dropped.
    """
    plan = _card_omitting_supports()
    row = _row(plan)
    week = row["planning_brief"]["weekly_role_map"]["weeks"][0]
    week["session_roles"] = [
        {
            "role_key": "mobility_rehab",
            "category": "support_insert",
            "athlete_facing_label": "Shoulder Opener",
            "display_text": "Easy range and pain-free control. Stop well before fatigue.",
            "countdown_offset": 10,
            "scheduled_countdown_label": "D-10",
            "session_index": 0,
            "selected_exercise_assignments": [],
        },
        {
            "role_key": "mobility_rehab",
            "category": "support_insert",
            "athlete_facing_label": "Hip Opener",
            "display_text": "Low-amplitude hip range, slow and controlled.",
            "countdown_offset": 10,
            "scheduled_countdown_label": "D-10",
            "session_index": 1,
            "selected_exercise_assignments": [],
        },
    ]

    sessions = _sessions_by_dday(_map_plan_detail(row, include_admin=False))

    assert sessions[10] == ["Shoulder Opener", "Hip Opener"]


def test_a_similarly_titled_session_does_not_absorb_a_different_role():
    """Two shared words are not identity.

    "Technical Shadow Rhythm" and "Technical Shadow Boxing" overlap in two
    tokens and are different scheduled items, so the second must still render.
    """
    plan = _card_omitting_supports()
    day = next(d for d in plan["weeks"][0]["days"] if d["countdown_label"] == "D-9")
    kept = copy.deepcopy(day["sessions"][0])
    kept["session_id"] = "llm-d9-0"
    kept["title"] = "Technical Shadow Boxing"
    day["sessions"] = [kept]

    row = _row(plan)
    week = row["planning_brief"]["weekly_role_map"]["weeks"][0]
    week["session_roles"] = [
        {
            "role_key": "technical_shadow_rhythm",
            "category": "support_insert",
            "athlete_facing_label": "Technical Shadow Rhythm",
            "display_text": "Light shadow rhythm only. Smooth entries, exits, and reset cues.",
            "countdown_offset": 9,
            "scheduled_countdown_label": "D-9",
            "selected_exercise_assignments": [],
        }
    ]

    sessions = _sessions_by_dday(_map_plan_detail(row, include_admin=False))

    assert sessions[9] == ["Technical Shadow Boxing", "Technical Shadow Rhythm"]


def _support_role(d_day: int, role_key: str, label: str, category: str, text: str) -> dict:
    return {
        "role_key": role_key,
        "category": "support_insert",
        "support_insert_category": category,
        "athlete_facing_label": label,
        "display_text": text,
        "stress_class": "support",
        "countdown_offset": d_day,
        "scheduled_countdown_label": f"D-{d_day}",
        "selected_exercise_assignments": [],
    }


def test_same_day_support_sessions_all_survive_with_their_own_semantics():
    """D-9 carries breathing, a physical footwork drill and visualisation."""
    plan = _card_omitting_supports()
    for day in plan["weeks"][0]["days"]:
        day["sessions"] = []
    row = _row(plan)
    row["planning_brief"]["weekly_role_map"]["weeks"][0]["session_roles"] = [
        _support_role(9, "breathing_reset", "Breathing Reset", "recovery", "Nasal breathing if comfortable."),
        _support_role(
            9,
            "footwork_walkthrough",
            "Pressure Step-Cut Reset",
            "technical_footwork",
            "Why: Read the opponent's exit lane.\n- Pressure Step-Cut Reset: 2 sets x 4 reactions.",
        ),
        _support_role(9, "neural_visualization", "Neural Visualization", "mental", "Quiet visualization only."),
    ]

    detail = _map_plan_detail(row, include_admin=False)
    day = next(
        day
        for week in detail.outputs.structured_plan.weeks
        for day in week.days
        if day.countdown_label == "D-9"
    )

    assert [session.title for session in day.sessions] == [
        "Breathing Reset",
        "Pressure Step-Cut Reset",
        "Neural Visualization",
    ]
    types = {session.title: session.session_type for session in day.sessions}
    assert types["Breathing Reset"] == "recovery"
    assert types["Pressure Step-Cut Reset"] == "skill"
    assert types["Neural Visualization"] == "skill"


def test_a_day_with_no_authoritative_role_is_never_given_a_session():
    plan = _card_omitting_supports()
    for day in plan["weeks"][0]["days"]:
        day["sessions"] = []
    row = _row(plan)
    row["planning_brief"]["weekly_role_map"]["weeks"][0]["session_roles"] = [
        _support_role(9, "breathing_reset", "Breathing Reset", "recovery", "Nasal breathing if comfortable.")
    ]

    sessions = _sessions_by_dday(_map_plan_detail(row, include_admin=False))

    assert sessions[9] == ["Breathing Reset"]
    assert sessions[8] == []
    assert sessions[5] == []
