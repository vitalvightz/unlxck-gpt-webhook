"""Downstream regression coverage for closed deterministic composition."""

from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_validator import _late_camp_effective_prescription_warnings


def _assignment(name: str, slot_id: str = "slot-1", phase: str = "SPP") -> dict:
    return {"slot_id": slot_id, "name": name, "source_phase": phase, "slot_group": "strength_slots"}


def _role(names: list[str], *, day: int = 7) -> dict:
    return {
        "role_key": "neural_primer_day",
        "category": "strength",
        "scheduled_day_hint": "tuesday",
        "selected_exercise_assignments": [
            _assignment(name, f"slot-{index}") for index, name in enumerate(names, 1)
        ],
        "effective_strength_envelope": {
            "scheduled_d_day": day,
            "complete_exercise_allow_list": True,
            "allowed_exercise_names": names,
        },
    }


def _brief(role: dict, *, candidates: list[dict] | None = None) -> dict:
    return {
        "candidate_pools": {"SPP": {"strength_slots": candidates or []}},
        "weekly_role_map": {"weeks": [{"phase": "SPP", "session_roles": [role]}]},
    }


def _membership_findings(brief: dict, rendered: str) -> list[dict]:
    return [
        finding
        for finding in _late_camp_effective_prescription_warnings(brief, rendered)
        if "exercise_allow_list" in (finding.get("violation_dimensions") or [])
    ]


def test_unselected_candidate_with_legal_dose_is_blocked() -> None:
    names = ["Thruster", "Med-Ball Slam", "Banded Row", "High Pull", "Skater Hop"]
    role = _role(["Thruster"])
    candidates = [
        {"slot_id": f"slot-{index}", "selected": {"name": name}, "session_index": 1}
        for index, name in enumerate(names, 1)
    ]
    rendered = "D-7 (Tuesday) — Neural primer\n- Thruster: 2 x 3 @ RPE 6\n- High Pull: 1 x 3 @ RPE 5"

    findings = _membership_findings(_brief(role, candidates=candidates), rendered)

    assert len(findings) == 1
    assert findings[0]["rendered_exercise"] == "High Pull"
    assert findings[0]["severity"] == "blocker"


def test_selected_multi_exercise_session_is_accepted() -> None:
    names = ["Trap Bar Deadlift", "Landmine Press", "Pallof Press"]
    rendered = "\n".join(["D-7 (Tuesday) — Strength", *[f"- {name}: 2 x 3 @ RPE 6" for name in names]])

    assert _membership_findings(_brief(_role(names)), rendered) == []


def test_candidate_alternate_cannot_substitute_for_selected_exercise() -> None:
    candidate = {
        "slot_id": "slot-1",
        "session_index": 1,
        "selected": {"name": "Trap Bar Deadlift"},
        "alternates": [{"name": "Front Squat", "prescription": "2 x 3 @ RPE 6"}],
    }
    rendered = "D-7 (Tuesday) — Strength\n- Front Squat: 2 x 3 @ RPE 6"

    findings = _membership_findings(_brief(_role(["Trap Bar Deadlift"]), candidates=[candidate]), rendered)

    assert len(findings) == 1
    assert findings[0]["rendered_exercise"] == "Front Squat"


def test_selected_exercise_can_pass_membership_and_fail_dose_independently() -> None:
    role = _role(["Trap Bar Deadlift"])
    role["effective_strength_envelope"].update(
        loaded_allowed=True, max_sets=2, max_reps=3, rpe_cap_high=7,
        loaded_exercise_names=["Trap Bar Deadlift"],
    )
    role["effective_strength_prescriptions"] = [{
        "name": "Trap Bar Deadlift", "dose_role_kind": "anchor", "effective_loaded": True,
        "effective_max_sets": 2, "effective_max_reps": 3, "effective_rpe_cap": 7,
    }]

    findings = _late_camp_effective_prescription_warnings(
        _brief(role), "D-7 (Tuesday) — Strength\n- Trap Bar Deadlift: 3 x 3 @ RPE 6"
    )

    assert not any("exercise_allow_list" in (item.get("violation_dimensions") or []) for item in findings)
    assert len(findings) == 1
    assert findings[0]["violation_dimensions"] == ["sets"]


def test_resolver_stamps_complete_authority_from_assignments_not_alternates() -> None:
    slot = {
        "slot_id": "slot-1", "session_index": 1, "priority": 1, "quality_class": "anchor_loaded",
        "selected": {"name": "Trap Bar Deadlift", "prescription": "3 x 5 @ RPE 7"},
        "alternates": [{"name": "Front Squat", "prescription": "3 x 5 @ RPE 7"}],
    }
    role = _role(["Trap Bar Deadlift"], day=30)
    role_map = {"weeks": [{"phase": "SPP", "calendar_days": [{"weekday": "tuesday", "d_day": 30}],
                           "session_roles": [role]}]}

    apply_effective_strength_prescriptions(
        weekly_role_map=role_map, candidate_pools={"SPP": {"strength_slots": [slot]}},
    )

    assert role["effective_strength_envelope"]["complete_exercise_allow_list"] is True
    assert role["effective_strength_envelope"]["allowed_exercise_names"] == ["Trap Bar Deadlift"]
    assert role["effective_strength_envelope"]["scheduled_d_day"] == 30


def test_finalizer_packet_exposes_selected_identity_and_closed_rule() -> None:
    role = _role(["Trap Bar Deadlift"])
    packet = build_stage2_finalizer_packet(stage2_payload={}, planning_brief=_brief(role))
    compact_role = packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_roles"][0]

    assert compact_role["selected_exercise_assignments"] == role["selected_exercise_assignments"]
    assert compact_role["effective_strength_envelope"]["allowed_exercise_names"] == ["Trap Bar Deadlift"]
    assert any("complete session membership" in rule for rule in packet["hard_rules"])


def test_role_without_composition_authority_is_not_constrained() -> None:
    combat_role = {"role_key": "technical_tactical_day", "category": "technical"}
    rendered = "D-7 (Tuesday) — Tactical\n- Southpaw exit drill: 3 x 2 minutes"

    assert _late_camp_effective_prescription_warnings(_brief(combat_role), rendered) == []
