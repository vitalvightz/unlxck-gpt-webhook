"""Unit tests for the daily injury check-in reconciliation contract.

Pure/deterministic: no store, no clock — declared injuries + known open flag ids.
"""

import pytest
from pydantic import ValidationError

from api.contracts.injury_checkin import (
    DeclaredInjury,
    build_injury_label,
    open_injury_flag_risks,
    reconcile_injury_checkin,
)


def _declare(**kwargs) -> DeclaredInjury:
    return DeclaredInjury(**kwargs)


def test_new_injury_opens_a_flag():
    plan = reconcile_injury_checkin(
        declared=[_declare(body_area="left knee", status="ongoing")],
        open_flag_ids=[],
    )
    assert len(plan.creates) == 1
    assert plan.updates == []
    create = plan.creates[0]
    assert create["status"] == "open"
    assert create["severity"] == "moderate"
    assert create["body_area"] == "left knee"
    assert create["description"] == "left knee"  # falls back to body area
    assert create["source"] == "checkin"


def test_improving_new_injury_opens_in_monitoring():
    plan = reconcile_injury_checkin(
        declared=[_declare(description="tight calf", status="improving")],
        open_flag_ids=[],
    )
    assert plan.creates[0]["status"] == "monitoring"


def test_existing_flag_resolved_is_an_update_not_a_create():
    plan = reconcile_injury_checkin(
        declared=[_declare(flag_id="f1", status="resolved")],
        open_flag_ids=["f1"],
    )
    assert plan.creates == []
    assert len(plan.updates) == 1
    assert plan.updates[0].flag_id == "f1"
    assert plan.updates[0].fields["status"] == "resolved"


def test_existing_flag_worse_keeps_open_and_updates_severity():
    plan = reconcile_injury_checkin(
        declared=[_declare(flag_id="f1", severity="severe", status="worse")],
        open_flag_ids=["f1"],
    )
    assert plan.updates[0].fields == {"status": "open", "severity": "severe"}


def test_existing_flag_status_update_does_not_default_severity():
    plan = reconcile_injury_checkin(
        declared=[_declare(flag_id="f1", status="ongoing")],
        open_flag_ids=["f1"],
    )
    assert plan.updates[0].fields == {"status": "open"}


def test_unknown_flag_id_is_treated_as_new_not_a_foreign_update():
    # A stale/foreign flag_id must never mutate another row — it becomes a create.
    plan = reconcile_injury_checkin(
        declared=[_declare(flag_id="ghost", body_area="wrist", status="ongoing")],
        open_flag_ids=["f1"],
    )
    assert plan.updates == []
    assert len(plan.creates) == 1
    assert plan.creates[0]["body_area"] == "wrist"


def test_unknown_flag_id_without_identity_is_rejected_before_create():
    with pytest.raises(ValueError, match="body_area or description"):
        reconcile_injury_checkin(
            declared=[_declare(flag_id="ghost", status="ongoing")],
            open_flag_ids=["f1"],
        )


def test_new_injury_reported_already_resolved_is_a_noop():
    plan = reconcile_injury_checkin(
        declared=[_declare(body_area="ankle", status="resolved")],
        open_flag_ids=[],
    )
    assert plan.creates == []
    assert plan.updates == []


def test_new_injury_requires_identity():
    with pytest.raises(ValidationError):
        _declare(status="ongoing")  # no flag_id, no body_area, no description


def test_multiple_injuries_partition_into_creates_and_updates():
    plan = reconcile_injury_checkin(
        declared=[
            _declare(flag_id="f1", status="resolved"),
            _declare(body_area="shoulder", status="ongoing"),
            _declare(flag_id="f2", status="improving"),
        ],
        open_flag_ids=["f1", "f2"],
    )
    assert len(plan.creates) == 1
    assert {u.flag_id for u in plan.updates} == {"f1", "f2"}


def test_no_open_flags_no_risk():
    assert open_injury_flag_risks([]) == []
    assert open_injury_flag_risks([{"status": "resolved", "body_area": "knee"}]) == []


def test_severe_open_flag_is_a_stop_level_risk():
    risks = open_injury_flag_risks(
        [{"status": "open", "severity": "severe", "body_area": "left knee"}]
    )
    assert len(risks) == 1
    assert risks[0].category == "active_injury_worse"
    assert "Left knee" in risks[0].text


def test_non_severe_open_flags_are_a_tracking_reminder():
    risks = open_injury_flag_risks(
        [
            {"status": "open", "severity": "mild", "body_area": "wrist"},
            {"status": "monitoring", "severity": "moderate", "body_area": "calf"},
        ]
    )
    assert len(risks) == 1
    assert risks[0].category == "reminder"
    assert "2 open injuries" in risks[0].text
    assert "Wrist" in risks[0].text


def test_reminder_uses_injury_logic_for_intake_labels():
    # A "left wrist" flag with a "tightness" intake type (stored in the
    # description as "left wrist: tightness") must read as the normalized label,
    # not the raw body_area — and colourful synonyms resolve to the right noun.
    risks = open_injury_flag_risks(
        [
            {
                "status": "monitoring",
                "severity": "mild",
                "body_area": "left wrist",
                "description": "left wrist: tightness",
            },
            {
                "status": "open",
                "severity": "mild",
                "body_area": "thigh",
                "description": "dead leg",
            },
        ]
    )
    assert "Left wrist tightness" in risks[0].text
    assert "Thigh bruise" in risks[0].text


def test_flag_label_prefers_precomputed_label():
    risks = open_injury_flag_risks(
        [{"status": "open", "severity": "mild", "label": "Right ankle sprain"}]
    )
    assert "Right ankle sprain" in risks[0].text


def test_build_injury_label_normalizes_condition_and_location():
    assert build_injury_label("left wrist", "left wrist: tightness") == "Left wrist tightness"
    assert build_injury_label("upper back", "upper back: bruise") == "Upper back bruise"
    # Free-text notes never leak into the label — only the location + condition.
    assert (
        build_injury_label("left knee", "left knee: tightness. hurts when squatting")
        == "Left knee tightness"
    )
    # No recognized condition: the clean location passes through.
    assert build_injury_label("left wrist", "left wrist") == "Left wrist"
    # Nothing to label.
    assert build_injury_label("", "") == "injury"


def test_build_injury_label_never_doubles_the_condition_word():
    # Regression: the scorer recognises "cut", but the curated location strip
    # list once omitted it, so the surviving "cut" got the condition appended
    # again ("Cut neck cut"). The condition must appear exactly once, wherever it
    # sits in the athlete's phrasing.
    assert build_injury_label("cut neck", "cut neck") == "Neck cut"
    assert build_injury_label("cut on left eyebrow", "cut on left eyebrow") == "Left eyebrow cut"
    # Inflected surface-injury words are stripped from the location too, so the
    # canonical noun is never doubled by an inflection the strip list missed.
    assert build_injury_label("grazed knuckles", "grazed knuckles") == "Knuckles graze"
    # A condition word must never be the *only* thing left after stripping it out
    # of the location — the canonical noun still labels the injury.
    assert build_injury_label("cut", "cut") == "Cut"


def test_build_injury_label_recognizes_lay_fracture_words():
    # Regression: fracture words used to be recognised only in the exact phrase
    # "broken bone", so "broken collarbone" lost its type and read as a bare
    # "Collarbone". Lay fracture words are now detected with any body part, and a
    # structural injury still surfaces its display noun via the triage category.
    assert build_injury_label("broken collarbone", "broken collarbone") == "Collarbone fracture"
    assert build_injury_label("broke my collarbone", "broke my collarbone") == "Collarbone fracture"
    assert build_injury_label("broken nose", "broken nose") == "Nose fracture"
    assert build_injury_label("cracked rib", "cracked rib") == "Rib fracture"
    assert build_injury_label("shattered wrist", "shattered wrist") == "Wrist fracture"


def test_build_injury_label_never_leaks_free_text_notes():
    # With no structured body_area, the location must come from the scorer's
    # structured side + location — never from cleaning the free-text description,
    # so athlete notes ("hurts when squatting") can never leak into the label.
    assert (
        build_injury_label("", "left knee: tightness. hurts when squatting")
        == "Left knee tightness"
    )
    assert (
        build_injury_label("", "right shoulder impingement when pressing overhead")
        == "Right shoulder impingement"
    )
    # Free text the scorer can't resolve to a location yields no leaked words.
    assert build_injury_label("", "totally unparseable gibberish note") == "injury"
