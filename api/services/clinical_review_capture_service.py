"""Shared admin capture, server evidence packets and private history replay."""
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException

from api.compliance_guards import require_health_feature_access
from api.contracts.clinical_progression_review import (
    CLINICAL_REVIEW_REGISTRY, ReviewLifecycleChange, ReviewedEvidencePacket,
)
from api.contracts.clinical_review_capture import ClinicalReviewCaptureResult
from api.contracts.clinical_review_validity import (
    ClinicalReviewInput, ReviewValidityContext, evaluate_clinical_review,
)
from api.contracts.rehab_assessment import assessment_identity, instant
from api.contracts.rehab_stage import resolve_rehab_stage
from api.contracts.rehab_progression import episode_setback_at
from api.contracts.reviewed_prescription import ReviewedPrescriptionSelection, materialised_selection_hash
from api.services.injury_episode_service import apply_episode_observations
from api.services.clinical_review_trust import (
    CAPTURE_POLICY, LIFECYCLE_EVENT, REVIEW_EVENT, PersistedClinicalReviewTrust,
)
from api.store import is_effective_admin_profile
from fightcamp.rehab_clinical import content_hash, load_clinical_policies
from fightcamp.rehab_protocols import get_rehab_bank


def _authority(store, recorder):
    if not is_effective_admin_profile(recorder, store):
        raise HTTPException(403, "admin access required")
    return recorder.athlete_id


def _target(snapshot, athlete_id, injury_id, episode_id, *, active=True):
    profile, injury = snapshot.get("profile") or {}, snapshot.get("injury") or {}
    if profile.get("id") != str(athlete_id) or profile.get("role") != "athlete":
        raise HTTPException(404, "target athlete not found")
    if profile.get("access_status") != "approved":
        raise HTTPException(403, "target athlete access required")
    require_health_feature_access(SimpleNamespace(**profile))
    if (injury.get("athlete_id"), injury.get("id"), injury.get("episode_id")) != (
            str(athlete_id), str(injury_id), str(episode_id)):
        raise HTTPException(409, "injury episode changed")
    if active and injury.get("status") not in {"open", "monitoring"}:
        raise HTTPException(409, "injury episode is closed")
    if active and injury.get("side") not in {"left", "right", "bilateral"}:
        raise HTTPException(409, "clinical review requires a known injury side")
    return injury


def _binding(injury, criterion_id, version, registry, policies):
    definition = registry.get(criterion_id, version)
    if definition is None:
        raise HTTPException(422, "clinical criterion/version is not registered")
    if registry.current(criterion_id).version != version:
        raise HTTPException(409, "clinical criterion version changed")
    matches = [p for p in policies if (p.region, p.injury_type) == assessment_identity(injury)
               and p.status == "active"]
    if len(matches) != 1 or matches[0].policy_id not in definition.profile_ids:
        raise HTTPException(409, "clinical criterion does not match this injury profile")
    policy = matches[0]
    transition = next((t for t in policy.transitions if t.from_stage == definition.transition.from_stage
                       and t.to_stage == definition.transition.to_stage), None)
    # Compiled profile/transition bindings may capture a shadow review before a
    # live pathway declares the checkpoint. Both production protections must
    # remain: target disabled and transition non-promotable. Live capture still
    # requires the exact checkpoint declaration. No request can register a rule.
    declared = transition and any(r.checkpoint == criterion_id for r in transition.requirements)
    shadow = transition and not transition.promotable and transition.to_stage not in policy.live_stages
    if not declared and not shadow:
        raise HTTPException(409, "clinical criterion does not match this transition")
    return definition, policy


def build_review_context(snapshot, *, definition, policy, bank, as_of):
    """Complete exact episode state. Cutoff changes with evidence, never the clock."""
    injury = snapshot["injury"]
    scope = (injury["athlete_id"], injury["id"], injury["episode_id"])
    events = snapshot["events"]
    exposures = snapshot["exposures"]
    if any(tuple(e.get(k) for k in ("athlete_id", "injury_id", "injury_episode_id")) != scope
           for e in [*events, *exposures]):
        raise ValueError("incomplete or foreign episode history")
    evidence = sorted((e for e in events if e["event_type"] not in {REVIEW_EVENT, LIFECYCLE_EVENT}),
                      key=lambda e: (instant(e["created_at"]), e["id"]))
    exposures = sorted(exposures, key=lambda e: (instant(e["created_at"]), e["id"]))
    row = apply_episode_observations(injury, evidence, as_of=as_of)
    start = instant(row.get("assessment_episode_started_at"))
    dates = [start, instant(injury.get("updated_at")), *(instant(e["created_at"]) for e in [*evidence, *exposures])]
    if not start or any(d is None or d > as_of for d in dates):
        raise ValueError("episode evidence timestamps are incomplete or in the future")
    references, safety = [], []
    for event in evidence:
        payload, kind = event.get("payload") or {}, None
        assessment = payload.get("assessment") or {}
        references.append(dict(event_id=event["id"], protocol_id=assessment.get("assessment_kind") or event["event_type"],
            protocol_version=assessment.get("protocol_version") or 1, content_hash=content_hash(payload),
            observed_at=instant(assessment.get("assessed_at")) or instant(event["created_at"]),
            recorded_at=instant(event["created_at"])))
        if event["event_type"] == "rehab_progression_assessment":
            kind = "medical_hold" if payload.get("medical_concern") is True else "assessment"
        elif event["event_type"] == "clinician_clearance_report":
            kind = "clearance_change"
        elif payload.get("latest_reported_status") == "worse" or payload.get("response") == "worse":
            kind = "setback"
        if kind:
            safety.append(dict(event_id=event["id"], athlete_id=scope[0], injury_id=scope[1], injury_episode_id=scope[2],
                side=injury["side"], kind=kind, occurred_at=event["created_at"], recorded_at=event["created_at"]))
    for exposure in exposures:
        event = exposure.get("event_json") or {}
        references.append(dict(event_id=exposure["id"], protocol_id="rehab_exposure", protocol_version=1,
            content_hash=content_hash(event), observed_at=instant(event.get("occurred_at")) or instant(exposure["created_at"]),
            recorded_at=instant(exposure["created_at"])))
        if setback := episode_setback_at(injury, (exposure,)):
            safety.append(dict(event_id=exposure["id"], athlete_id=scope[0], injury_id=scope[1], injury_episode_id=scope[2],
                side=injury["side"], kind="setback", occurred_at=setback, recorded_at=exposure["created_at"]))
    # Keep the whole history in the packet digest/audit export, but stale
    # pre-setback observations cannot become readiness references for a new decision.
    setback = max((instant(e["occurred_at"]) for e in safety if e["kind"] == "setback"), default=None)
    if setback:
        references = [r for r in references if r["observed_at"] > setback]
    bank_by_id = {d["id"]: content_hash(d) for group in bank for d in group.get("drills", [])}
    reviewed_bank = {o.drill_id: bank_by_id.get(o.drill_id) for o in definition.options}
    safety_revision = content_hash({"injury": injury, "safety": safety})
    packet = ReviewedEvidencePacket(evidence_cutoff=max(dates), safety_revision=safety_revision,
        packet_revision=content_hash({"injury": injury, "events": evidence, "exposures": exposures,
            "policy_version": policy.version, "policy_hash": policy.content_hash,
            "criterion_id": definition.criterion_id, "criterion_version": definition.version,
            "interpretation_schema": definition.payload_type.model_json_schema(),
            "options": [o.option_hash for o in definition.options], "bank": reviewed_bank}),
        references=tuple(references), clearance_event_id=next((e["id"] for e in reversed(evidence)
            if e["event_type"] == "clinician_clearance_report"), None))
    return ReviewValidityContext(athlete_id=scope[0], injury_id=scope[1], injury_episode_id=scope[2], side=injury["side"],
        profile_id=policy.policy_id, policy_version=policy.version, policy_hash=policy.content_hash,
        criterion_id=definition.criterion_id, criterion_version=definition.version, transition=definition.transition,
        episode_started_at=start, episode_current=injury["status"] in {"open", "monitoring"}, history_complete=True,
        current_packet=packet, bank=tuple(dict(drill_id=key, bank_hash=bank_by_id[key])
            for key in sorted({o.drill_id for o in definition.options}) if key in bank_by_id), safety_history=tuple(safety),
        medical_hold=bool(row.get("rehab_medical_gate") or resolve_rehab_stage(row).medical_gate),
        restriction_hold=bool(row.get("restriction_hold")),
        assessment_events=tuple(e for e in evidence if e["event_type"] == "rehab_progression_assessment"))


def hydrate_review_input(snapshot, *, criterion_id, criterion_version, as_of, registry=CLINICAL_REVIEW_REGISTRY,
                         policies=None, bank=None):
    injury = snapshot["injury"]
    _target(snapshot, injury["athlete_id"], injury["id"], injury["episode_id"], active=False)
    definition, policy = _binding(snapshot["injury"], criterion_id, criterion_version, registry,
                                  policies if policies is not None else load_clinical_policies())
    rows = snapshot["events"]
    reviews = tuple(e["payload"] for e in rows if e["event_type"] == REVIEW_EVENT
                    and e["payload"].get("criterion_id") == criterion_id)
    identities = {r.get("review_id") for r in reviews}
    lifecycle = tuple(ReviewLifecycleChange.model_validate(e["payload"]) for e in rows
                      if e["event_type"] == LIFECYCLE_EVENT and e["payload"].get("review_id") in identities)
    context = build_review_context(snapshot, definition=definition, policy=policy,
                                   bank=bank if bank is not None else get_rehab_bank(), as_of=as_of)
    return ClinicalReviewInput(context, reviews, lifecycle, registry, PersistedClinicalReviewTrust.from_server_history(rows))


def prepare_review_packet(store, *, recorder, athlete_id, injury_id, injury_episode_id, criterion_id, criterion_version,
                          registry=CLINICAL_REVIEW_REGISTRY, policies=None, bank=None, as_of=None):
    _authority(store, recorder)
    snapshot = store.get_clinical_review_capture_context(str(athlete_id), str(injury_id), str(injury_episode_id))
    _target(snapshot, athlete_id, injury_id, injury_episode_id)
    supplied = hydrate_review_input(snapshot, criterion_id=criterion_id, criterion_version=criterion_version,
        registry=registry, policies=policies, bank=bank, as_of=as_of or datetime.now(timezone.utc))
    return {"context": supplied.context.model_dump(mode="json"),
            "injury": snapshot["injury"],
            "reviewed_options": [o.model_dump(mode="json") | {"option_hash": o.option_hash}
                                 for o in supplied.registry.current(criterion_id).options],
            "interpretation_schema": supplied.registry.current(criterion_id).payload_type.model_json_schema(),
            "observations": [e for e in snapshot["events"] if e["event_type"] not in {REVIEW_EVENT, LIFECYCLE_EVENT}],
            "exposures": snapshot["exposures"]}


def _event_id(request):
    # Global request identity: rebinding the same request to another valid
    # subject/episode must conflict, rather than manufacture a second approval.
    return str(uuid5(NAMESPACE_URL, f"clinical-capture:{request.request_id}"))


def _result(event):
    return ClinicalReviewCaptureResult(event_id=event["id"], review_id=event["payload"].get("review_id") or event["id"],
        recorded_at=event["payload"]["recorded_at"], event_type=event["event_type"])


def _retry(snapshot, request, recorder_id):
    existing = next((e for e in snapshot["events"] if e["id"] == _event_id(request)), None)
    if existing:
        capture = existing.get("clinical_capture") or {}
        if capture.get("request_hash") != content_hash(request.model_dump(mode="json")) or capture.get("recorder_id") != recorder_id:
            raise HTTPException(409, "clinical review request conflict")
        return _result(existing)


def _provenance(recorder_id, confirmed_at, reference, statement_hash):
    actor = dict(actor_id=recorder_id, role="operational_recorder")
    return dict(source="independently_confirmed_clinician_statement", recorder=actor, verifier=actor,
                confirmed_at=confirmed_at, confirmation_reference=reference, statement_hash=statement_hash)


def _event(request, payload, recorder_id, event_type, *, statement_reference=None, statement_text=None):
    raw = payload.model_dump(mode="json")
    return dict(id=_event_id(request), athlete_id=str(request.athlete_id), injury_id=str(request.injury_id),
        injury_episode_id=str(request.injury_episode_id), event_type=event_type, payload=raw,
        clinical_capture=dict(policy=CAPTURE_POLICY, recorder_id=recorder_id,
            request_hash=content_hash(request.model_dump(mode="json")), envelope_hash=content_hash(raw),
            statement_reference=statement_reference, statement_text=statement_text))


def record_clinical_review(store, *, recorder, request, registry=CLINICAL_REVIEW_REGISTRY,
                           policies=None, bank=None, as_of=None):
    recorder_id = _authority(store, recorder)
    now = as_of or datetime.now(timezone.utc)
    snapshot = store.get_clinical_review_capture_context(str(request.athlete_id), str(request.injury_id), str(request.injury_episode_id))
    injury = _target(snapshot, request.athlete_id, request.injury_id, request.injury_episode_id, active=False)
    if retry := _retry(snapshot, request, recorder_id):
        return retry
    _target(snapshot, request.athlete_id, request.injury_id, request.injury_episode_id)
    definition, policy = _binding(injury, request.criterion_id, request.criterion_version, registry,
                                  policies if policies is not None else load_clinical_policies())
    statement = request.statement
    author_reference = statement.author_reference
    try:
        author_reference = str(UUID(author_reference))
    except ValueError:
        pass  # External professional identifiers are not necessarily UUIDs.
    if (author_reference.casefold() in {recorder_id.casefold(), str(request.athlete_id).casefold()}
            or statement.clinical_scope != definition.clinical_scope):
        raise HTTPException(422, "independent qualified clinical author required")
    context = build_review_context(snapshot, definition=definition, policy=policy,
                                   bank=bank if bank is not None else get_rehab_bank(), as_of=now)
    if statement.reviewed_packet_revision != context.current_packet.packet_revision:
        raise HTTPException(409, "reviewed evidence packet changed; obtain a new clinician decision")
    selection = None
    if statement.selection:
        selected = statement.selection
        option = next((o for o in definition.options if (o.option_id, o.option_version) == (selected.option_id, selected.option_version)), None)
        if not option:
            raise HTTPException(422, "reviewed prescription option is not registered")
        raw = selected.model_dump(mode="python")
        raw.update(selection_version=1, option_hash=option.option_hash, drill_id=option.drill_id, bank_hash=option.bank_hash,
                   materialised_prescription_hash="0" * 64)
        selection = ReviewedPrescriptionSelection.model_validate(raw)
        selection = selection.model_copy(update={"materialised_prescription_hash": materialised_selection_hash(option, selection)})
    raw = {k: getattr(context, k) for k in ("athlete_id", "injury_id", "injury_episode_id", "side", "profile_id",
        "policy_version", "policy_hash", "criterion_id", "criterion_version", "transition")}
    raw.update(review_id=_event_id(request), evidence=context.current_packet, recorded_at=now,
        reviewed_at=statement.reviewed_at, clinical_author=dict(author_id=author_reference,
            display_name=statement.author_display_name, qualification_reference=statement.qualification_reference,
            clinical_scopes=(definition.clinical_scope,)),
        provenance=_provenance(recorder_id, statement.confirmed_at, statement.confirmation_reference,
                               sha256(statement.statement_text.encode("utf-8")).hexdigest()),
        decision=statement.decision, interpretation=statement.interpretation, selected_prescription=selection,
        rationale=statement.rationale, structured_reasons=statement.structured_reasons,
        valid_until=statement.valid_until, expiry_reason=statement.expiry_reason,
        supersedes_review_id=str(request.supersedes_review_id) if request.supersedes_review_id else None)
    try:
        review = registry.parse(raw)
        event = _event(request, review, recorder_id, REVIEW_EVENT,
                       statement_reference=statement.statement_reference, statement_text=statement.statement_text)
        supplied = hydrate_review_input(snapshot, criterion_id=request.criterion_id, criterion_version=request.criterion_version,
            registry=registry, policies=policies, bank=bank, as_of=now)
        lifecycle, replacement = list(supplied.lifecycle), None
        if request.supersedes_review_id:
            change = ReviewLifecycleChange(lifecycle_id=str(uuid5(NAMESPACE_URL, f"supersession:{review.review_id}")),
                review_id=str(request.supersedes_review_id), state="superseded", replacement_review_id=review.review_id,
                effective_at=now, recorded_at=now, provenance=_provenance(recorder_id, now,
                    statement.confirmation_reference, review.provenance.statement_hash), reason="Replacement clinician decision recorded")
            replacement = dict(event, id=change.lifecycle_id, event_type=LIFECYCLE_EVENT, payload=change.model_dump(mode="json"))
            replacement["clinical_capture"] = dict(event["clinical_capture"], envelope_hash=content_hash(replacement["payload"]))
            lifecycle.append(change)
        trust = PersistedClinicalReviewTrust.from_server_history([*snapshot["events"], event, *([replacement] if replacement else [])])
        evaluation = evaluate_clinical_review(context, (*supplied.reviews, review), as_of=now,
            lifecycle=tuple(lifecycle), registry=registry, trust=trust)
        if evaluation.validity != "valid":
            raise HTTPException(409, {"code": "clinical_review_not_valid", "reasons": list(evaluation.reason_codes)})
    except ValueError as exc:
        raise HTTPException(422, "invalid clinical review contract") from exc
    return _result(store.record_clinical_review_event(str(request.athlete_id), recorder_id, snapshot, event, replacement))


def record_review_lifecycle(store, *, recorder, request, as_of=None):
    recorder_id = _authority(store, recorder)
    now = as_of or datetime.now(timezone.utc)
    snapshot = store.get_clinical_review_capture_context(str(request.athlete_id), str(request.injury_id), str(request.injury_episode_id))
    _target(snapshot, request.athlete_id, request.injury_id, request.injury_episode_id, active=False)
    if retry := _retry(snapshot, request, recorder_id):
        return retry
    review = next((e["payload"] for e in snapshot["events"] if e["event_type"] == REVIEW_EVENT
                   and e["id"] == str(request.review_id)), None)
    if not review:
        raise HTTPException(404, "clinical review not found in this episode")
    if request.effective_at < instant(review["recorded_at"]) or request.effective_at > now:
        raise HTTPException(422, "invalid lifecycle chronology")
    change = ReviewLifecycleChange(lifecycle_id=_event_id(request), review_id=str(request.review_id),
        state="revoked" if request.action == "revoke" else "superseded",
        effective_at=request.effective_at, recorded_at=now, reason=request.reason,
        replacement_review_id=str(request.replacement_review_id) if request.replacement_review_id else None,
        provenance=_provenance(recorder_id, now, request.confirmation_reference, content_hash(request.model_dump(mode="json"))))
    event = _event(request, change, recorder_id, LIFECYCLE_EVENT)
    return _result(store.record_clinical_review_event(str(request.athlete_id), recorder_id, snapshot, event, None))
