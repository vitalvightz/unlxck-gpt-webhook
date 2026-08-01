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
    _TRIAGE_DISPLAY_NOUN,
)


# Action/verb words that must never survive in the LOCATION half of a label
# (they belong to the type noun at the end, e.g. "tear" in "ACL tear").
_LEAK_WORDS = {
    "torn", "tore", "snapped", "snap", "popped", "pop", "blown", "broke", "broken",
    "cracked", "shattered", "dislocated", "fractured", "ruptured", "sprained", "strained",
}

# Known punctuation edge: redundant with "ko'd" / "knocked out", which do fire.
_KNOWN_UNDETECTED = {"k.o.'d"}


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
    assert create["latest_reported_status"] == "ongoing"
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
    assert plan.creates[0]["latest_reported_status"] == "improving"


def test_existing_flag_resolved_is_an_update_not_a_create():
    plan = reconcile_injury_checkin(
        declared=[_declare(flag_id="f1", status="resolved")],
        open_flag_ids=["f1"],
    )
    assert plan.creates == []
    assert len(plan.updates) == 1
    assert plan.updates[0].flag_id == "f1"
    assert plan.updates[0].fields["status"] == "resolved"
    assert plan.updates[0].fields["latest_reported_status"] == "resolved"


def test_existing_flag_worse_keeps_open_and_updates_severity():
    plan = reconcile_injury_checkin(
        declared=[_declare(flag_id="f1", severity="severe", status="worse")],
        open_flag_ids=["f1"],
    )
    assert plan.updates[0].fields == {
        "status": "open",
        "severity": "severe",
        "latest_reported_status": "worse",
    }


def test_existing_flag_status_update_does_not_default_severity():
    plan = reconcile_injury_checkin(
        declared=[_declare(flag_id="f1", status="ongoing")],
        open_flag_ids=["f1"],
    )
    assert plan.updates[0].fields == {"status": "open", "latest_reported_status": "ongoing"}


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


def test_severe_easing_flag_stays_a_stop_level_risk():
    # Regression: a severe injury marked "easing" (monitoring) is still severe, so
    # it must stay a stop-level risk, not quietly drop to the soft "train around
    # it" reminder. This closes the "mark it easing to bypass the hold" gap and
    # keeps the risk consistent with the Today/Overview injury hold.
    risks = open_injury_flag_risks(
        [{"status": "monitoring", "severity": "severe", "body_area": "chest"}]
    )
    assert len(risks) == 1
    assert risks[0].category == "active_injury_worse"
    assert "Chest" in risks[0].text
    # Only resolving it clears the stop.
    assert open_injury_flag_risks(
        [{"status": "resolved", "severity": "severe", "body_area": "chest"}]
    ) == []


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


def test_build_injury_label_unrecognized_condition_falls_back_to_location():
    assert (
        build_injury_label(
            "left shoulder tngling i dont know why",
            "left shoulder tngling i dont know why",
        )
        == "Left shoulder"
    )
    # Correctly recognized symptom text still keeps the type noun.
    assert build_injury_label("left shoulder", "tingling i dont know why") == "Left shoulder nerve issue"
    # Clean manual/body-map locations must not be collapsed to coarser scorer regions.
    assert build_injury_label("hip flexor", "hip flexor") == "Hip flexor"
    assert build_injury_label("Head / Neck", "Head / Neck") == "Head / neck"


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


def test_build_injury_label_is_clean_for_every_injury_type():
    # One representative athlete phrase per canonical type: the label must be a
    # clean "<location> <type-noun>" with no leaked descriptor/synonym words and
    # no doubled condition. Locks in map-driven stripping across every type.
    cases = {
        # rehab types
        "sprained ankle": "Ankle sprain",
        "rolled ankle": "Ankle sprain",
        "pulled hamstring": "Hamstring strain",
        "calf cramp": "Calf strain",
        "tight hip": "Hip tightness",
        "scraped knee": "Knee abrasion",
        "mat burn on elbow": "Elbow abrasion",
        "cut lip": "Lip cut",
        "nick on eyebrow": "Eyebrow cut",
        "gash on shin": "Shin laceration",
        "grazed knuckles": "Knuckles graze",
        "scratch on cheek": "Cheek graze",
        "blister on heel": "Heel blister",
        "bruised thigh": "Thigh bruise",
        "corked calf": "Calf bruise",
        "swollen knee": "Knee swelling",
        "achilles tendonitis": "Achilles tendonitis",
        "jumpers knee": "Knee tendonitis",
        "shoulder impingement": "Shoulder impingement",
        "hip pinch": "Hip impingement",
        "unstable shoulder": "Shoulder instability",
        "stiff neck": "Neck stiffness",
        "frozen shoulder": "Shoulder stiffness",
        "knee pain": "Knee pain",
        "sore quads": "Quads soreness",
        "hyperextended elbow": "Elbow hyperextension",
        # structural / triage types
        "dislocated shoulder": "Shoulder dislocation",
        "subluxation shoulder": "Shoulder dislocation",
        "fractured collarbone": "Collarbone fracture",
        # a concussion carries no body location and never doubles its own word
        "concussed": "Concussion",
        "got rocked": "Concussion",
        "head knock": "Concussion",
        # A reported tear stays a "tear" — it is not escalated to "rupture" — while
        # explicit rupture evidence ("snapped", "rupture") keeps the louder noun.
        # Named ligaments show the type alone.
        "knee tendon tear": "Knee tendon tear",
        "torn tendon": "Tendon tear",
        "acl tear": "ACL tear",
        "torn acl": "ACL tear",
        "mcl tear": "MCL tear",
        "torn ligament": "Ligament tear",
        "muscle tear": "Muscle tear",
        "torn hamstring": "Hamstring tear",
        "bicep tear": "Bicep tear",
        "torn bicep": "Bicep tear",
        "snapped achilles": "Achilles rupture",
        "achilles rupture": "Achilles rupture",
        "ruptured tendon": "Tendon rupture",
    }
    for phrase, expected in cases.items():
        assert build_injury_label(phrase, phrase) == expected, phrase


def test_reported_tear_is_not_escalated_to_rupture():
    # A tear is not always a rupture. A reported tendon tear must keep the athlete's
    # own word instead of being relabelled a (complete) rupture — the screenshot
    # bug where "Left bicep tear" surfaced as "Left bicep rupture".
    assert build_injury_label("Left bicep", "Left bicep tear") == "Left bicep tear"
    assert build_injury_label("bicep tear", "bicep tear") == "Bicep tear"
    assert build_injury_label("torn tendon", "torn tendon") == "Tendon tear"
    assert build_injury_label("rotator cuff tear", "rotator cuff tear") == "Rotator cuff tear"

    # Explicit rupture evidence still earns the louder "rupture" noun.
    assert build_injury_label("achilles rupture", "achilles rupture") == "Achilles rupture"
    assert build_injury_label("snapped achilles", "snapped achilles") == "Achilles rupture"
    assert build_injury_label("ruptured bicep", "ruptured bicep") == "Bicep rupture"
    assert build_injury_label("achilles", "complete achilles tear") == "Achilles rupture"
    assert build_injury_label("achilles", "complete achilles tendon tear") == "Achilles rupture"
    assert build_injury_label("bicep", "full-thickness bicep tear") == "Bicep rupture"
    assert build_injury_label("achilles", "achilles tear with avulsion") == "Achilles rupture"
    assert build_injury_label("bicep", "bicep tear with detached tendon") == "Bicep rupture"


def test_negated_rupture_evidence_does_not_upgrade_a_tear():
    for description in [
        "Not ruptured, just a bicep tear",
        "nothing is ruptured, just a bicep tear",
        "bicep tear with no rupture",
        "bicep tear without evidence of rupture",
        "bicep tear, not detached",
        "the tendon was not detached, just a bicep tear",
        "avulsion not present, just a bicep tear",
        "rupture not seen, just a bicep tear",
        "not a complete tear, just a bicep tear",
        "confirmed bicep tear, not a full-thickness tear",
    ]:
        assert build_injury_label("bicep", description) == "Bicep tear", description
    assert build_injury_label("achilles", "ruled out rupture but achilles tear") == "Achilles tear"


def test_rupture_evidence_requires_an_actual_complete_tear_phrase():
    for description in [
        "complete recovery from a bicep tear",
        "complete healing of the tendon tear",
        "bicep tear; complete imaging confirms a tear",
        "bicep tear; full-thickness injury",
    ]:
        assert build_injury_label("bicep", description) == "Bicep tear", description

    assert build_injury_label("achilles", "multiple achilles ruptures") == "Achilles rupture"
    assert build_injury_label("achilles", "the tendon is rupturing") == "Achilles rupture"


def test_confirmed_tear_stays_a_tear():
    # A tear being clinically *confirmed* proves it exists, not that it is complete.
    # "confirmed" must not act as rupture evidence — only a confirmed *rupture* does
    # (and that already reads as a rupture via the word "rupture" itself).
    assert build_injury_label("bicep", "confirmed bicep tear") == "Bicep tear"
    assert build_injury_label("achilles", "confirmed achilles tear") == "Achilles tear"
    assert build_injury_label("achilles", "confirmed achilles rupture") == "Achilles rupture"
    # The clinical qualifier never leaks into the label location either.
    assert build_injury_label("confirmed bicep tear", "confirmed bicep tear") == "Bicep tear"
    assert build_injury_label("confirmed achilles tear", "confirmed achilles tear") == "Achilles tear"
    assert build_injury_label("confirmed achilles rupture", "confirmed achilles rupture") == "Achilles rupture"

    # The safety triage is unchanged: a plain tear still routes to the urgent
    # tendon-rupture category (clinical clearance), only the label is honest.
    from fightcamp.injury_scoring import score_injury_phrase

    scored = score_injury_phrase("left bicep tear")
    assert scored["triage_category"] == "tendon_rupture"
    assert "urgent" in scored["flags"]


def test_every_triage_category_has_a_display_noun():
    # Map-driven: any triage category the system can emit MUST have a display noun,
    # otherwise a detected tear/rupture/fracture would render with no type in the
    # label. Adding a new category to TRIAGE_CATEGORY_MAP without a noun fails here.
    from fightcamp.injury_synonyms import TRIAGE_CATEGORY_MAP

    missing = sorted(set(TRIAGE_CATEGORY_MAP.values()) - set(_TRIAGE_DISPLAY_NOUN))
    assert missing == [], f"triage categories with no display noun: {missing}"


def test_every_structural_phrase_is_urgent_and_cleanly_labelled():
    # Map-driven contract over the WHOLE structural/triage vocabulary: every phrase
    # the maps know must (1) flag urgent and (2) produce a clean label whose
    # location half carries no leftover action verb. Adding a new phrase to either
    # map without wiring it through the label builder fails here.
    from fightcamp.injury_scoring import score_injury_phrase
    from fightcamp.injury_synonyms import STRUCTURAL_RED_FLAG_MAP, TRIAGE_CATEGORY_MAP

    phrases = sorted(set(STRUCTURAL_RED_FLAG_MAP) | set(TRIAGE_CATEGORY_MAP))
    not_urgent, leaked = [], []
    for phrase in phrases:
        if phrase in _KNOWN_UNDETECTED:
            continue
        score = score_injury_phrase(f"{phrase} {phrase}")
        if "urgent" not in score["flags"]:
            not_urgent.append(phrase)
        label = build_injury_label(phrase, phrase)
        # The type noun is the final word(s); the location half is everything before
        # it and must not contain an action verb like "torn"/"snapped".
        location_tokens = set(label.lower().split()[:-1])
        if location_tokens & _LEAK_WORDS:
            leaked.append((phrase, label))
    assert not_urgent == [], f"structural phrases not flagged urgent: {not_urgent}"
    assert leaked == [], f"action verbs leaked into location: {leaked}"


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
