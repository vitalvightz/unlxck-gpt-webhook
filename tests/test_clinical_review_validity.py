"""Exact scope, chronology, latest-record semantics and lifecycle replay."""
from dataclasses import replace
from datetime import timedelta

import pytest

from api.contracts.clinical_review_validity import ReviewReason, ReviewSafetyEvent
from tests.clinical_review_fixtures import (
    CUTOFF, NOW, RECORDED, REVIEWED, START, SyntheticAttestations, bundle, changed_review, evaluate, lifecycle_change,
)


@pytest.mark.parametrize("field,value,reason", [
    ("athlete_id", "other-athlete", ReviewReason.ATHLETE),
    ("injury_id", "other-injury", ReviewReason.INJURY),
    ("injury_episode_id", "other-episode", ReviewReason.EPISODE),
    ("side", "right", ReviewReason.SIDE),
    ("profile_id", "other-profile", ReviewReason.PROFILE),
    ("criterion_id", "other-criterion", ReviewReason.CRITERION),
    ("criterion_version", 2, ReviewReason.CRITERION_VERSION),
    ("schema_version", 2, ReviewReason.SCHEMA_VERSION),
    ("policy_version", 2, ReviewReason.POLICY),
    ("policy_hash", "f" * 64, ReviewReason.POLICY),
    ("transition", dict(from_stage="load", to_stage="dynamic"), ReviewReason.TRANSITION),
])
def test_exact_review_binding(field, value, reason):
    supplied = bundle()
    raw = supplied.reviews[0].model_dump(mode="json") | {field: value}
    result = evaluate(replace(supplied, reviews=(raw,)))
    assert result.validity == "invalid" and result.criterion_status != "pass"
    assert reason in result.reason_codes


@pytest.mark.parametrize("changes,reason", [
    (dict(history_complete=False), ReviewReason.HISTORY),
    (dict(episode_current=False), ReviewReason.EPISODE_CLOSED),
    (dict(side="unknown"), ReviewReason.SIDE),
    (dict(medical_hold=True), ReviewReason.MEDICAL_HOLD),
    (dict(restriction_hold=True), ReviewReason.RESTRICTION),
    (dict(policy_version=2), ReviewReason.POLICY),
    (dict(policy_hash="e" * 64), ReviewReason.POLICY),
])
def test_current_context_invalidates(changes, reason):
    supplied = bundle()
    assert reason in evaluate(replace(supplied, context=supplied.context.model_copy(update=changes))).reason_codes


@pytest.mark.parametrize("field,value", [("packet_revision", "d" * 64), ("safety_revision", "e" * 64),
    ("evidence_cutoff", CUTOFF + timedelta(minutes=1)), ("clearance_event_id", "new-clearance"), ("references", ())])
def test_exact_packet_binding(field, value):
    supplied = bundle()
    packet = supplied.context.current_packet.model_copy(update={field: value})
    result = evaluate(replace(supplied, context=supplied.context.model_copy(update={"current_packet": packet})))
    assert ReviewReason.PACKET in result.reason_codes and result.criterion_status != "pass"


@pytest.mark.parametrize("kind,reason", [("setback", ReviewReason.SETBACK), ("medical_hold", ReviewReason.MEDICAL_HOLD),
    ("restriction", ReviewReason.RESTRICTION), ("assessment", ReviewReason.ASSESSMENT),
    ("clearance_change", ReviewReason.CLEARANCE)])
def test_replay_before_and_after_safety_event(kind, reason):
    supplied = bundle()
    context = supplied.context
    event = ReviewSafetyEvent(event_id="test-safety", **{k: getattr(context, k) for k in (
        "athlete_id", "injury_id", "injury_episode_id", "side")}, kind=kind,
        occurred_at=NOW, recorded_at=NOW)
    supplied = replace(supplied, context=context.model_copy(update={"safety_history": (event,)}))
    assert evaluate(supplied, as_of=NOW - timedelta(seconds=1)).criterion_status == "pass"
    after = evaluate(supplied, as_of=NOW)
    assert after.validity == "invalid" and reason in after.reason_codes
    assert after == evaluate(supplied, as_of=NOW)


def test_later_transcription_does_not_freshen_old_clinical_judgment():
    supplied = bundle()
    context = supplied.context
    event = ReviewSafetyEvent(event_id="test-safety", **{k: getattr(context, k) for k in (
        "athlete_id", "injury_id", "injury_episode_id", "side")}, kind="setback",
        occurred_at=REVIEWED, recorded_at=RECORDED)
    supplied = replace(supplied, context=context.model_copy(update={"safety_history": (event,)}))
    assert ReviewReason.SETBACK in evaluate(supplied).reason_codes


@pytest.mark.parametrize("state,reason", [("revoked", ReviewReason.REVOKED), ("superseded", ReviewReason.SUPERSEDED)])
def test_replay_before_and_after_lifecycle_change(state, reason):
    supplied = bundle()
    change = lifecycle_change(supplied, state)
    supplied = replace(supplied, lifecycle=(change,), trust=SyntheticAttestations.attest(supplied.reviews, (change,)))
    assert evaluate(supplied, as_of=NOW - timedelta(seconds=1)).criterion_status == "pass"
    result = evaluate(supplied)
    assert reason in result.reason_codes and result.criterion_status != "pass"
    assert result == evaluate(supplied)


def test_untrusted_revocation_does_not_restore_approval():
    supplied = bundle()
    result = evaluate(replace(supplied, lifecycle=(lifecycle_change(supplied),)))
    assert ReviewReason.LIFECYCLE in result.reason_codes and ReviewReason.REVOKED in result.reason_codes
    assert result.criterion_status != "pass"


@pytest.mark.parametrize("tamper", ["athlete_recorder", "missing_confirmation", "future_effective", "duplicate", "unknown_target"])
def test_lifecycle_incomplete_or_conflicting_is_not_ignored(tamper):
    supplied = bundle()
    change = lifecycle_change(supplied)
    if tamper == "athlete_recorder":
        change = change.model_copy(update={"provenance": change.provenance.model_copy(update={
            "recorder": change.provenance.recorder.model_copy(update={"actor_id": "test-athlete", "role": "athlete"})})})
    elif tamper == "missing_confirmation":
        change = change.model_copy(update={"provenance": change.provenance.model_copy(update={"confirmed_at": None})})
    elif tamper == "future_effective":
        change = change.model_copy(update={"effective_at": NOW + timedelta(days=1)})
    elif tamper == "unknown_target":
        change = change.model_copy(update={"review_id": "unknown-review"})
    lifecycle = (change, change) if tamper == "duplicate" else (change,)
    result = evaluate(replace(supplied, lifecycle=lifecycle, trust=SyntheticAttestations.attest(supplied.reviews, lifecycle)))
    assert ReviewReason.LIFECYCLE in result.reason_codes and result.criterion_status != "pass"


@pytest.mark.parametrize("newest", ["deferred", "not_approved", "malformed", "wrong_version", "revoked", "superseded"])
def test_never_fall_back_to_older_approved_review(newest):
    supplied = bundle()
    replacement = changed_review(supplied, review_id="test-replacement", recorded_at=NOW,
        reviewed_at=NOW, provenance=supplied.reviews[0].provenance.model_dump() | {"confirmed_at": NOW},
        supersedes_review_id="test-review", decision=newest if newest in {"deferred", "not_approved"} else "approved").reviews[0]
    raw = replacement.model_dump(mode="json")
    if newest == "malformed":
        raw["interpretation"] = {"incomplete": True}
    elif newest == "wrong_version":
        raw["criterion_version"] = 99
    lifecycle = (lifecycle_change(replace(supplied, reviews=(replacement,)), newest),) if newest in {"revoked", "superseded"} else ()
    supplied = replace(supplied, reviews=(supplied.reviews[0], raw), lifecycle=lifecycle,
        trust=SyntheticAttestations.attest((supplied.reviews[0], replacement), lifecycle))
    assert evaluate(supplied, as_of=NOW - timedelta(seconds=1)).criterion_status == "pass"
    assert evaluate(supplied).criterion_status != "pass"


@pytest.mark.parametrize("conflict", ["identical_id", "changed_same_id", "fork", "same_timestamp", "missing_prior"])
def test_duplicate_and_conflicting_review_history(conflict):
    supplied = bundle()
    review = supplied.reviews[0]
    next_review = changed_review(supplied, review_id="replacement", recorded_at=NOW,
        supersedes_review_id=review.review_id).reviews[0]
    if conflict == "identical_id":
        records = (review, review)
    elif conflict == "changed_same_id":
        records = (review, next_review.model_copy(update={"review_id": review.review_id}))
    elif conflict == "fork":
        records = (review, next_review.model_copy(update={"supersedes_review_id": None}))
    elif conflict == "same_timestamp":
        records = (review, next_review.model_copy(update={"recorded_at": RECORDED}))
    else:
        records = (next_review,)
    result = evaluate(replace(supplied, reviews=records, trust=SyntheticAttestations.attest(records)))
    assert result.validity == "invalid" and result.criterion_status != "pass"
    assert set(result.reason_codes) & {ReviewReason.DUPLICATE, ReviewReason.CONFLICT}


def test_explicit_new_approval_after_revocation_uses_new_identity():
    supplied = bundle()
    change = lifecycle_change(supplied, stamp=NOW)
    replacement = changed_review(supplied, review_id="test-replacement", reviewed_at=NOW + timedelta(hours=1),
        recorded_at=NOW + timedelta(hours=2), supersedes_review_id="test-review",
        provenance=supplied.reviews[0].provenance.model_dump() | {"confirmed_at": NOW + timedelta(hours=1)}).reviews[0]
    supplied = replace(supplied, reviews=(*supplied.reviews, replacement), lifecycle=(change,),
        trust=SyntheticAttestations.attest((*supplied.reviews, replacement), (change,)))
    assert evaluate(supplied, as_of=NOW).criterion_status != "pass"
    assert evaluate(supplied, as_of=NOW + timedelta(hours=2)).criterion_status == "pass"


def test_conflicting_supersession_link_cannot_approve_another_replacement():
    supplied = bundle()
    replacement = changed_review(supplied, review_id="actual-replacement", recorded_at=NOW,
        supersedes_review_id="test-review").reviews[0]
    change = lifecycle_change(supplied, "superseded")
    records = (*supplied.reviews, replacement)
    result = evaluate(replace(supplied, reviews=records, lifecycle=(change,),
        trust=SyntheticAttestations.attest(records, (change,))))
    assert ReviewReason.CONFLICT in result.reason_codes and result.criterion_status != "pass"


def test_new_rule_version_cannot_reuse_approval_even_with_same_policy_hash():
    from api.contracts.clinical_progression_review import CriterionReviewRegistry
    from tests.clinical_review_fixtures import protocol
    supplied = bundle()
    old = protocol()
    option = old.options[0].model_copy(update={"criterion_version": 2})
    current = replace(old, version=2, options=(option,))
    registry = CriterionReviewRegistry((old, current))
    result = evaluate(replace(supplied, registry=registry,
        context=supplied.context.model_copy(update={"criterion_version": 2})))
    assert ReviewReason.CRITERION_VERSION in result.reason_codes and result.criterion_status != "pass"
    assert evaluate(replace(supplied, registry=registry), as_of=RECORDED).criterion_status == "pass"


def test_readiness_evidence_before_setback_cannot_be_freshened_by_later_review():
    supplied = bundle()
    context = supplied.context
    setback = ReviewSafetyEvent(event_id="older-setback", **{k: getattr(context, k) for k in (
        "athlete_id", "injury_id", "injury_episode_id", "side")}, kind="setback",
        occurred_at=CUTOFF, recorded_at=CUTOFF)
    assert ReviewReason.SETBACK in evaluate(replace(supplied,
        context=context.model_copy(update={"safety_history": (setback,)}))).reason_codes


@pytest.mark.parametrize("changes,reason", [
    (dict(reviewed_at=NOW + timedelta(days=1)), ReviewReason.FUTURE),
    (dict(reviewed_at=CUTOFF - timedelta(seconds=1)), ReviewReason.CHRONOLOGY),
    (dict(reviewed_at=START - timedelta(seconds=1)), ReviewReason.BEFORE_EPISODE),
    (dict(valid_until=NOW, expiry_reason="Test-only explicit expiry."), ReviewReason.EXPIRED),
])
def test_chronology_and_explicit_expiry(changes, reason):
    assert reason in evaluate(changed_review(bundle(), **changes)).reason_codes


def test_replay_before_recording_and_policy_change():
    supplied = bundle()
    assert evaluate(supplied, as_of=RECORDED - timedelta(seconds=1)).criterion_status != "pass"
    assert evaluate(supplied, as_of=RECORDED).criterion_status == "pass"
    changed = replace(supplied, context=supplied.context.model_copy(update={"policy_version": 2}))
    assert ReviewReason.POLICY in evaluate(changed).reason_codes
    assert evaluate(supplied, as_of=RECORDED).criterion_status == "pass"  # Versioned replay snapshot retained.
    with pytest.raises(ValueError, match="aware explicit as_of"):
        evaluate(supplied, as_of=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("raw", [{}, dict(recorded_at="not-a-time"), dict(recorded_at=RECORDED, review_id=[]),
                                  dict(recorded_at=RECORDED, review_id="test-review", criterion_version={})])
def test_malformed_raw_input_returns_structured_failure(raw):
    result = evaluate(replace(bundle(), reviews=(raw,)))
    assert result.validity == "invalid" and ReviewReason.MALFORMED in result.reason_codes


def test_missing_review_is_explicit():
    assert ReviewReason.MISSING in evaluate(replace(bundle(), reviews=())).reason_codes
