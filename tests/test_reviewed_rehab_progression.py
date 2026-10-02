"""Baseline stages never use clearance, uncertainty or camp as recovery evidence."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.contracts.rehab_progression import resolve_reviewed_progression
from fightcamp.rehab_clinical import ClinicalPolicy, load_clinical_policies


def injury():
    return dict(id="injury", episode_id="episode", athlete_id="athlete", latest_reported_status="improving", updated_at="2026-09-28T12:00:00Z")


def exposure(row, response="worse", stamp="2026-09-29T12:00:00Z"):
    return dict(id=str(uuid4()), athlete_id=row["athlete_id"], created_at=stamp,
                event_json=dict(injury_id=row["id"], injury_episode_id=row["episode_id"],
                                response=dict(next_day_response=response), dose_completed={}))


def resolve(row, stage="restore", rows=(), **kwargs):
    return resolve_reviewed_progression(row, base_stage=stage, exposures=rows, policy=load_clinical_policies()[0], **kwargs)


@pytest.mark.parametrize("stage", ["load", "dynamic", "return"])
def test_advanced_activation_is_rejected_and_clearance_cannot_bypass(stage):
    policy = load_clinical_policies()[0]
    # A higher live stage needs an open transition with source-backed criteria.
    with pytest.raises(ValidationError, match="cannot be live without an open transition|every lower stage live"):
        ClinicalPolicy.model_validate({**policy.model_dump(), "live_stages": ["calm", "restore", stage]})
    row = {**injury(), "clinician_clearance": {"scopes": ["rehab", "training", "contact"]}}
    assert resolve(row, stage)["stage"] == "calm"


def test_setback_requires_a_later_explicit_injury_improvement():
    row = injury()
    rows = [exposure(row)]
    assert resolve(row, rows=rows)["stage"] == "calm"
    row.update(latest_reported_status="same", updated_at="2026-10-01T12:00:00Z")
    assert resolve(row, rows=rows)["stage"] == "calm"
    row["latest_reported_status"] = "improving"
    assert resolve(row, rows=rows)["stage"] == "calm"
    row["latest_reported_at"] = "2026-10-01T12:00:00Z"
    assert resolve(row, rows=rows)["stage"] == "restore"
    # A delayed setback is timestamped when reported, not when work occurred.
    rows[0]["response_recorded_at"] = "2026-10-02T12:00:00Z"
    assert resolve(row, rows=rows)["stage"] == "calm"


def test_other_episodes_and_other_athletes_do_not_change_baseline():
    row = injury()
    rows = [exposure({**row, "episode_id": "old"}), exposure({**row, "athlete_id": "someone-else"})]
    assert resolve(row, rows=rows)["stage"] == "restore"


def test_missing_feedback_does_not_advance_and_truncation_keeps_baseline_available():
    row = injury()
    assert resolve(row, "calm", [exposure(row, "not_sure")])["stage"] == "calm"
    assert resolve(row, "restore", history_truncated=True)["stage"] == "restore"
