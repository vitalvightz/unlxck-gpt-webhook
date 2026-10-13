"""PR6: goal coverage is reconciled against the training actually delivered.

A goal counts only when a final member of a scheduled role trains it at an
effective dose on a plannable day, and the athlete-visible programme renders
that member at that dose (audit F07, F13, F15). Pipeline scenarios reuse the
pinned-clock, fixed-seed generator from the PR5 delivery tests.
"""
from __future__ import annotations

import pytest

from fightcamp.calendar_context import role_d_day
from fightcamp.goal_preservation import (
    collect_goal_evidence, dose_volume, reconcile_goal_preservation, validate_goal_preservation,
)
from fightcamp.session_composition import _role_days_until_fight
from fightcamp.stage2_validator import _goal_witness_dose_matches, validate_stage2_output
from selector_assignments import apply_with_selected_membership
from test_goal_weakness_delivery import _brief, _entry, _members, _roles


def _slot(name, prescription, quality="anchor_loaded", **selected):
    return {"slot_id": name, "session_index": 1, "role": "hinge", "quality_class": quality, "anchor_capable": True,
            "selected": {"name": name, "quality_class": quality, "prescription": prescription, "method": "strength",
                         "movement_patterns": ["hinge"], **selected}}


def _hand_brief(*slots):
    role = {"role_key": "strength_touch_day", "category": "strength", "strength_session_index": 1, "session_index": 1,
            "scheduled_day_hint": "Monday", "scheduled_countdown_label": "D-18"}
    brief = {
        "athlete_snapshot": {"key_goals": ["strength"], "primary_goal": "strength", "days_until_fight": 20,
                             "fatigue": "low", "training_frequency": 4},
        "priority_focus": {"primary_goal": "strength", "secondary_goals": []},
        "weekly_role_map": {"weeks": [{"week_index": 1, "phase": "SPP", "declared_training_days": ["Monday", "Thursday"],
                                       "calendar_days": [{"weekday": "monday", "d_day": 18},
                                                         {"weekday": "thursday", "d_day": 15}],
                                       "session_roles": [role], "suppressed_roles": []}]},
        "candidate_pools": {"SPP": {"strength_slots": list(slots)}},
        "restrictions": [],
    }
    apply_with_selected_membership(weekly_role_map=brief["weekly_role_map"], candidate_pools=brief["candidate_pools"],
                                   athlete_model=brief["athlete_snapshot"])
    return reconcile_goal_preservation(brief)


def _strength(brief):
    return _entry(brief, "strength")


# ---------------------------------------------------------------------------
# F07 - dose units decide what a member can evidence
# ---------------------------------------------------------------------------

def test_a_short_carry_never_certifies_strength():
    brief = _hand_brief(_slot("Farmer Carry", "2 x 20 m @ RPE 7"))
    assert dose_volume("2 x 20 m @ RPE 7") == {"sets": 2, "amount": 20, "unit": "m"}
    assert not any("meaningful_strength" in e["intents"] for e in collect_goal_evidence(brief))
    assert not _strength(brief)["satisfied"]


def test_a_timed_force_isometric_is_witnessed_in_seconds():
    brief = _hand_brief(_slot("Pin Pull", "3 x 6 sec max effort @ RPE 8", "anchor_force_isometric",
                              real_strength_maintenance=True))
    witness = _strength(brief)["evidence"][0]
    assert (witness["sets"], witness["reps"], witness["volume_unit"], witness["volume_amount"]) == (3, 0, "sec", 6)


@pytest.mark.parametrize(("dose", "matches"), [
    ("2 x 20 m", True),
    ("3 x 25 m", True),
    ("2 x 10 m", False),   # reduced distance
    ("1 x 20 m", False),   # reduced sets
    ("2 x 20 sec", False),  # seconds are not metres
    ("2 x 20", False),     # reps are not metres
])
def test_a_distance_witness_is_matched_in_its_own_unit(dose, matches):
    witness = {"sets": 2, "reps": 0, "volume_unit": "m", "volume_amount": 20}
    assert _goal_witness_dose_matches(witness, dose) is matches


@pytest.mark.parametrize(("dose", "matches"), [("3 x 6 sec", True), ("3 x 3 sec", False), ("3 x 6", False)])
def test_a_timed_witness_is_matched_in_seconds(dose, matches):
    witness = {"sets": 3, "reps": 0, "volume_unit": "sec", "volume_amount": 6}
    assert _goal_witness_dose_matches(witness, dose) is matches


# ---------------------------------------------------------------------------
# Stage 2 render fidelity: the visible programme must carry the witness
# ---------------------------------------------------------------------------

def _render_mismatches(brief, line):
    assert not validate_goal_preservation(brief)  # the render check runs only on a clean contract
    text = f"D-18 Monday\n{line}\nD-0\nFight day protocol."
    report = validate_stage2_output(planning_brief=brief, final_plan_text=text)
    return [e for e in report["errors"] if e["code"] == "goal_preservation_render_mismatch"]


@pytest.mark.parametrize(("line", "survives"), [
    ("- Deadlift: 3 x 3 @ RPE 7", True),
    ("- Deadlift: 4 x 5 @ RPE 8", True),
    ("- Romanian Deadlift: 3 x 3 @ RPE 7", False),  # substituted
    ("- Trap Bar Jump: 3 x 3 @ RPE 7", False),      # renamed away
    ("- Deadlift: 3 x 2 @ RPE 7", False),           # fewer reps
    ("- Deadlift: 2 x 3 @ RPE 7", False),           # fewer sets
    ("- Deadlift: 3 x 3 @ RPE 4", False),           # below working intensity
])
def test_a_rep_witness_must_survive_into_the_rendered_programme(line, survives):
    brief = _hand_brief(_slot("Deadlift", "3 x 3 @ RPE 7"))
    assert _strength(brief)["satisfied"]
    assert (not _render_mismatches(brief, line)) is survives


@pytest.mark.parametrize(("line", "survives"), [
    ("- Pin Pull: 3 x 6 sec max effort @ RPE 8", True),
    ("- Pin Pull: 3 x 3 sec max effort @ RPE 8", False),
    ("- Pin Pull: 3 x 6 @ RPE 8", False),
])
def test_a_timed_witness_must_survive_into_the_rendered_programme(line, survives):
    brief = _hand_brief(_slot("Pin Pull", "3 x 6 sec max effort @ RPE 8", "anchor_force_isometric",
                              real_strength_maintenance=True))
    assert (not _render_mismatches(brief, line)) is survives


# ---------------------------------------------------------------------------
# Truthful states on finished programmes
# ---------------------------------------------------------------------------

_EXPOSURE = ["vito_b", "king", "king_no_cut", "boxer28_pool_bike", "boxer28_trunk_fullgym",
             "boxer14_speed", "boxer10_speed", "boxer3_speed", "boxer10_trunk_short"]


@pytest.mark.parametrize("key", ["boxer28_trunk_fullgym", "boxer14_speed", "boxer10_speed", "boxer3_speed"])
def test_every_goal_witness_is_a_final_member_on_its_day(key):
    # The PR5 scenarios are swept by test_goal_weakness_delivery.
    brief = _brief(key)
    final = {(role_d_day(week, role), m["name"]) for week, role in _roles(brief) for m in _members(role)}
    for entry in brief["goal_preservation"]:
        for evidence in entry["evidence"]:
            if evidence.get("d_day") is not None and evidence.get("name"):
                assert (evidence["d_day"], evidence["name"]) in final, (entry["goal"], evidence["name"])


@pytest.mark.parametrize("key", _EXPOSURE)
def test_states_reasons_and_satisfaction_agree(key):
    for entry in _brief(key)["goal_preservation"]:
        days = [e["d_day"] for e in entry["evidence"]]
        assert len(days) == len(set(days)), entry["goal"]  # one witness per window, never double counted
        assert len(entry["reason_codes"]) == len(set(entry["reason_codes"])), entry["goal"]
        assert entry["satisfied"] is not bool(entry["missing_coverage"]), entry["goal"]
        if entry["state"] == "build" and entry["satisfied"]:
            # Maintenance-quality exposure never stands in for development.
            assert all(e["development_quality"] for e in entry["evidence"]), entry["goal"]
        if entry["state"] == "defer":
            assert not entry["satisfied"] and entry["constraints"], entry["goal"]
            assert {c["reason_code"] for c in entry["constraints"]} <= set(entry["reason_codes"])


@pytest.mark.parametrize("key", ["vito_b", "king"])
def test_a_swimming_day_cites_the_swim_never_an_unassigned_pool_drill(key):
    brief = _brief(key)
    witnesses = {(e["d_day"], e["name"]) for e in _entry(brief, "conditioning")["evidence"]}
    swim_days = {role_d_day(w, r) for w, r in _roles(brief) for m in _members(r) if "swim" in m["name"].lower()}
    for d_day, name in witnesses:
        if d_day in swim_days:
            assert "swim" in name.lower(), (d_day, name)


@pytest.mark.parametrize("key", ["vito_b", "king_no_cut", "boxer28_trunk_fullgym"])
def test_a_primary_speed_goal_is_built_beside_a_weakness(key):
    """A weakness may not silently displace the primary goal from its sessions."""
    brief = _brief(key)
    speed = _entry(brief, "speed")
    assert (speed["state"], speed["satisfied"]) == ("build", True)
    assert len(speed["evidence"]) >= 2 and all(e["development_quality"] for e in speed["evidence"])
    weakness = next(e for e in brief["goal_preservation"] if e["priority"] == "primary_weakness")
    assert weakness["satisfied"]


def test_king_cut_week_speed_gap_is_reported_unresolved_not_satisfied():
    """Known limitation: under King's cut the D-20..D-14 week holds no speed
    member at an evidencing dose (its Sled Push is a heavy carry) and repair is
    refused at the composed cap. It must stay a visible, unsatisfied build."""
    speed = _entry(_brief("king"), "speed")
    assert speed["state"] == "build"
    if any(w["min_d_day"] <= 20 and w["max_d_day"] >= 14 for w in speed["missing_coverage"]):
        assert not speed["satisfied"]
    assert not any("sled" in e["name"].lower() for e in speed["evidence"])


# ---------------------------------------------------------------------------
# F13 - windows end at the calendar; fight proximity is cited per window
# ---------------------------------------------------------------------------

def _constraint(entry, code):
    return [c for c in entry["constraints"] if c["reason_code"] == code]


def test_a_fourteen_day_camp_cannot_owe_its_creation_day():
    brief = _brief("boxer14_speed")
    power = _entry(brief, "power")
    assert power["state"] == "defer"
    assert any(c.get("authority") == "plan_calendar" for c in _constraint(power, "fight_proximity"))
    speed = _entry(brief, "speed")
    assert (speed["state"], speed["satisfied"]) == ("maintain", True)


@pytest.mark.parametrize("key", ["boxer10_speed", "boxer3_speed"])
def test_a_short_camp_maintains_from_members_or_defers_with_a_cited_cause(key):
    for entry in _brief(key)["goal_preservation"]:
        assert entry["state"] in {"maintain", "defer"}
        if entry["state"] == "defer":
            assert {c.get("authority") for c in _constraint(entry, "fight_proximity")} & {
                "plan_calendar", "late_fight_tail_ownership"}, entry["goal"]
        else:
            assert entry["satisfied"], entry["goal"]


# ---------------------------------------------------------------------------
# F15 - dead state and D-day resolution
# ---------------------------------------------------------------------------

def test_composition_reads_the_scheduled_d_day_before_the_weekday():
    role = {"scheduled_d_day": 9, "scheduled_day_hint": "Monday", "countdown_label": "D-20"}
    assert _role_days_until_fight(role) == 9


def test_no_payload_carries_the_unread_double_stress_flag():
    brief = _brief("boxer10_speed")
    assert "double_stress_day_allowed" not in repr(brief)
