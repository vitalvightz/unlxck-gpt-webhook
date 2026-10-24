"""Goal diagnostics stay inspectable without becoming athlete instructions."""
from copy import deepcopy
import json

from api.structured_plan_generation import _with_athlete_goal_notes
from fightcamp.goal_preservation import athlete_goal_explanation
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet


def _entries():
    return [
        {"goal": "strength", "priority": "primary", "state": "defer", "satisfied": False,
         "constraints": [{"reason_code": "calendar_capacity"}], "evidence": [],
         "contract_errors": [], "repair_attempts": [{"result": "authority_preserved"}]},
        {"goal": "footwork", "priority": "primary_weakness", "state": "build", "satisfied": False,
         "contract_errors": [{"message": "deterministic repair is required before claiming progress"}]}]


def test_finalizer_receives_plain_goal_context_without_mutating_admin_diagnostics():
    brief = {"payload_variant": "open_ongoing_stage2_payload", "open_plan_spec": {"goal_coverage": _entries()}}
    before = deepcopy(brief)
    packet = build_stage2_finalizer_packet(stage2_payload=brief, planning_brief=brief)
    entries = packet["selected_plan"]["open_plan_spec"]["goal_coverage"]
    assert all("contract_errors" not in e and "repair_attempts" not in e for e in entries)
    assert "deterministic repair" not in json.dumps(packet).lower()
    assert entries[0]["athlete_explanation"] == "Your current training schedule leaves no room for separate strength work this block."
    assert entries[1]["athlete_explanation"] == "This plan does not yet include work for your footwork goal."
    assert brief == before


def test_backend_replaces_screenshot_goal_notes_and_preserves_medical_safety():
    injury = {"category": "injury", "label": "Left knee pain", "text": "Your left knee gives low-level pain sometimes."}
    safety = {"display_text": "Stop and seek medical advice if symptoms worsen.", "severity": "red"}
    plan = {"plan_notes": [injury,
        {"category": "training", "label": "Strength deferred", "text": "Strength and power are held back for knee pain. This is deliberate, not an omission."},
        {"category": "training", "label": "Footwork gap", "text": "No qualified exercises. Deterministic repair is required before claiming progress."}],
        "red_flag_rules": [safety]}
    result = _with_athlete_goal_notes(plan, {"open_plan_spec": {"goal_coverage": _entries()}})
    text = json.dumps(result)
    assert "deterministic" not in text.lower() and "qualified exercises" not in text.lower()
    assert "deliberate" not in text.lower()
    assert result["plan_notes"][0] == injury and result["red_flag_rules"] == [safety]
    assert [n["text"] for n in result["plan_notes"]][1:] == [athlete_goal_explanation(e) for e in _entries()]


def test_final_open_coverage_wins_over_initial_classification_and_removes_stale_deferral_note():
    initial = {"goal": "strength", "state": "build", "priority": "primary"}
    final = {**initial, "satisfied": True, "evidence": [{"name": "Deadlift", "week": 1, "weekday": "Monday"}]}
    brief = {"compressed_priorities": {"goal_preservation": [initial]},
             "open_plan_spec": {"goal_coverage": [final]}}
    packet = build_stage2_finalizer_packet(stage2_payload=brief, planning_brief=brief)
    assert packet["selected_plan"]["goal_preservation"][0]["satisfied"] is True
    assert packet["selected_plan"]["goal_preservation"][0]["athlete_explanation"] == ""
    plan = {"plan_notes": [{"category": "training", "label": "Strength deferred", "text": "Old deferral"}]}
    assert _with_athlete_goal_notes(plan, brief)["plan_notes"] == []


def test_unexplained_missing_goal_is_never_described_as_deliberate_safety_reduction():
    entry = {"goal": "strength", "state": "build", "satisfied": False}
    assert athlete_goal_explanation(entry) == "This plan does not yet include work for your strength goal."
    entry.update(state="defer", constraints=[{"reason_code": "injury_constraint"}])
    assert "symptoms" in athlete_goal_explanation(entry)



def test_reduced_week_copy_uses_the_removal_authority_not_bare_injury_presence():
    from fightcamp.stage2_finalizer_packet_impl import _session_count_summary

    athlete = {"training_frequency": 4, "has_active_injury": True,
               "parsed_injuries": [{"severity": "low"}]}
    week = {"phase": "GPP", "session_roles": [], "suppressed_roles": [
        {"compression_reason_codes": ["coach_owned_appointment_capacity"]}]}
    summary = _session_count_summary(week, athlete)
    assert "injury_management" not in summary["reason_codes"]
    assert "coached sessions" in " ".join(summary["reduction_reasons"])
    week["suppressed_roles"][0]["compression_reason_codes"] = ["injury_management"]
    assert "injury_management" in _session_count_summary(week, athlete)["reason_codes"]
