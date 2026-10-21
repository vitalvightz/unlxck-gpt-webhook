"""The one authoritative rehab stage progression path for policy-backed episodes.

1. Baseline: the report ladder (``rehab_stage``) supplies CALM or RESTORE. A
   negative exposure response holds the episode at CALM until a later explicit
   injury-specific improvement.
2. Higher stages: each composed family + profile transition is evaluated against
   this episode's own exposure history. A stage advances only when the
   transition is open, declares at least one source-backed clinical criterion,
   every requirement passes and the target stage is live in the policy.

Reported rehabilitation permission is an explicit ceiling for reviewed LOAD
options. Training scope, camp phase, elapsed time and
whole-athlete signals cannot supply that permission or injury tolerance.
Missing evidence or a missing captured input is reported, never assumed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from fightcamp.rehab_clinical import ClinicalPolicy
from fightcamp.rehab_pathways import PathwayTransition, TransitionRequirement

from .rehab_evidence import (
    FAIL_DURING_RESPONSE_WORSE, FAIL_NEXT_DAY_RESPONSE_WORSE, group_events, has_defined_prescribed_dose,
    has_measured_amount, read_exact_events, side_matches,
)

#: Functional checkpoints whose input the app actually captures. Data cannot
#: claim capture; a checkpoint becomes evaluable only when code reads its input.
from .rehab_assessment import AssessmentContext, input_definitions, read_assessment_input
from .achilles_restore_load import CRITERION_ID, review_achilles_restore_load
from .clinical_review_validity import ClinicalReviewInput, ReviewReason, evaluate_clinical_review
from .clinical_progression_review import CLINICAL_REVIEW_REGISTRY
from .clinician_clearance import LOAD_PERMISSION_CHECKPOINT, achilles_load_permission_reason, permits_rehabilitation_loading
from .lateral_elbow_progression import CRITERION as ELBOW_CRITERION, PERMISSION_CRITERION, evaluate_elbow_entry, evaluate_elbow_permission
from .ankle_restore_load import CRITERION as ANKLE_CRITERION, evaluate_ankle_permission

from .shoulder_restore_load import CRITERION as SHOULDER_CRITERION, evaluate_shoulder_permission

CAPTURED_FUNCTIONAL_CHECKPOINTS: frozenset[str] = frozenset(
    [*(key[0] for key in CLINICAL_REVIEW_REGISTRY._definitions), LOAD_PERMISSION_CHECKPOINT, ELBOW_CRITERION, PERMISSION_CRITERION, ANKLE_CRITERION, SHOULDER_CRITERION])

PASS, FAIL, UNKNOWN, MISSING_INPUT = "pass", "fail", "unknown", "missing_input"
NOT_APPLICABLE = "not_applicable"


def _instant(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def episode_setback_at(injury: Mapping[str, Any], exposures: Sequence[Mapping[str, Any]]):
    negatives = []
    for row in exposures:
        raw = row.get("event_json") or row
        if str(row.get("athlete_id")) != str(injury.get("athlete_id")):
            continue
        if str(raw.get("injury_id")) != str(injury.get("id")) or str(raw.get("injury_episode_id")) != str(injury.get("episode_id")):
            continue
        # Retain conservative handling of partial historical adverse records,
        # but a known different side/region cannot hold this episode's tissue.
        if raw.get("body_region") and injury.get("body_region") and raw["body_region"] != injury["body_region"]:
            continue
        if raw.get("side") and not side_matches(str(injury.get("side") or "unknown"), raw["side"]):
            continue
        response, dose = raw.get("response") or {}, raw.get("dose_completed") or {}
        stamps = []
        if (response.get("during_response") == "worse" or response.get("next_day_response") == "worse"
                or response.get("stopped_due_to_symptoms") or response.get("worsening_reported") or dose.get("stopped_early")):
            if (response.get("during_response") == "worse" or response.get("stopped_due_to_symptoms")
                    or response.get("worsening_reported") or dose.get("stopped_early")):
                stamps.append(row.get("during_response_recorded_at") or row.get("created_at") or raw.get("occurred_at"))
            if response.get("next_day_response") == "worse":
                stamps.append(row.get("response_recorded_at") or row.get("created_at") or raw.get("occurred_at"))
            for value in stamps:
                stamp = _instant(value)
                if stamp is None:
                    return datetime.max.replace(tzinfo=timezone.utc)
                negatives.append(stamp)
    return max(negatives, default=None)


def _improvement_at(injury):
    return (_instant(injury.get("rehab_improvement_at"))
            or (_instant(injury.get("latest_reported_at")) if injury.get("latest_reported_status") == "improving" else None))


def _latest_setback_at(injury, exposures):
    # Exact episode injury reports count even on days without a rehab exposure.
    return max(filter(None, [episode_setback_at(injury, exposures),
                             _instant(injury.get("assessment_setback_at"))]), default=None)


def _reported_starter(transition, injury, as_of):
    """A persisted, episode-owned advice report; never inferred from silence."""
    report = injury.get("clinician_clearance") or {}
    if transition.entry_mode != "reported_clinician_starter" or not isinstance(report, Mapping):
        return False
    stamp = _instant(report.get("reported_at"))
    return (permits_rehabilitation_loading(injury) and injury.get("side") in {"left", "right"}
            and report.get("source") == "athlete_reported" and bool(report.get("report_id"))
            and stamp is not None and stamp <= as_of)


def _resolved_setback(policy, transition, injury, exposures, latest, performed, as_of):
    """Bounded re-entry after a flare, using existing observations only.

    See docs/rehab-progression-investigation.md for source scope and chronology.
    This never clears clinical restrictions or supplies permission. Other
    profiles/transitions retain their unresolved-negative hold.
    """
    if (transition.setback_resolution != "improvement_then_reviewed_restore"
            or not latest or not latest.response_consistent or latest.negative_reasons):
        return False
    setback = _latest_setback_at(injury, exposures)
    improvements = [(stamp, report["id"]) for report in injury.get("rehab_improvement_reports", ())
                    if (stamp := _instant(report.get("reported_at"))) and setback and setback < stamp <= as_of]
    if not improvements:
        return False
    improvement, report_id = min(improvements)
    if not setback or not improvement or not setback < improvement <= as_of:
        return False
    for event in latest.events:
        # Current completion evidence records the frozen completed_at here.
        # created_at only dates ingestion: a retry/backfill cannot make older
        # work new. Legacy midnight markers remain conservative within a day.
        performed_at = _instant(event.provenance.recorded_at)
        if (event not in performed or not performed_at or not improvement < performed_at <= as_of
                or event.response.during_response not in {"better", "same"}
                or event.response.next_day_response not in {"better", "same"}):
            return False
    return {"recovery_report_id": report_id, "recovery_reported_at": improvement.isoformat(),
            "resolved_setback_at": setback.isoformat()}


def _result(requirement: TransitionRequirement, status: str, reason: str, events=()) -> dict[str, Any]:
    return {"requirement_id": requirement.requirement_id, "kind": requirement.kind, "basis": requirement.basis,
            "status": status, "reason_code": reason, "evidence_ids": [str(e.exposure_id) for e in events]}


def evaluate_transition(transition: PathwayTransition, *, policy: ClinicalPolicy, injury: Mapping[str, Any],
                        exposures: Sequence[Mapping[str, Any]], history_truncated: bool = False,
                        as_of: datetime | None = None,
                        clinical_review_input: ClinicalReviewInput | None = None) -> dict[str, Any]:
    """Evaluate one declared transition. Pure; never changes a stage itself."""
    if clinical_review_input is not None and as_of is None:
        raise ValueError("shared clinical review integration requires explicit as_of")
    as_of = as_of or datetime.now(timezone.utc)
    events, ignored = read_exact_events(athlete_id=str(injury.get("athlete_id") or ""), injury=injury,
                                        exposure_rows=exposures)
    groups = group_events(events)
    reviewed = {p.drill_id: p for p in policy.prescriptions if p.stage == transition.from_stage}
    # Exposure to this policy's reviewed work for the stage being left, against
    # the same reviewed bank content, with a stated demand. Unknown demand is a
    # valid observation but never progression evidence.
    stage_events = [e for e in events if e.provenance.policy_id == policy.policy_id
                    and e.provenance.rehab_stage == transition.from_stage and e.drill_id in reviewed
                    and e.provenance.bank_hash == reviewed[e.drill_id].bank_hash and not e.has_unknown_demand]
    performed = [e for e in stage_events if e.dose_completed.completion_state in {"quantified", "performed_amount_unknown"}
                 and not e.dose_completed.stopped_early]
    performed_groups = [g for g in groups if g.group_id and any(e in performed for e in g.events)]
    latest = performed_groups[-1] if performed_groups else None
    # Permission is an entry basis, not proof of tolerance. A known setback
    # always requires the declared recovery evidence, even after renewed advice.
    starter = (_reported_starter(transition, injury, as_of)
               and not _latest_setback_at(injury, exposures) and not any(g.negative_reasons for g in groups))
    response_latest = groups[-1] if starter and groups else latest
    event_ids = {str(e.exposure_id) for e in events}
    unreadable_owned_work = False
    if starter:
        for row in exposures:
            raw = row.get("event_json") or row
            if (str(row.get("athlete_id")) == str(injury.get("athlete_id"))
                    and str(raw.get("injury_id")) == str(injury.get("id"))
                    and str(raw.get("injury_episode_id")) == str(injury.get("episode_id"))
                    and (not raw.get("side") or side_matches(str(injury.get("side")), raw["side"]))
                    and (not raw.get("body_region") or not injury.get("body_region") or raw["body_region"] == injury["body_region"])
                    and str(raw.get("exposure_id")) not in event_ids):
                unreadable_owned_work = True
    results = []
    for requirement in transition.requirements:
        kind = requirement.kind
        if kind == "no_unresolved_setback":
            if injury.get("latest_reported_status") == "worse":
                results.append(_result(requirement, FAIL, "current_report_worse"))
            elif groups and groups[-1].negative_reasons:
                results.append(_result(requirement, FAIL, groups[-1].negative_reasons[0], groups[-1].events))
            elif any(g.negative_reasons for g in groups) or _latest_setback_at(injury, exposures):
                resolution = _resolved_setback(policy, transition, injury, exposures, latest, performed, as_of)
                if resolution:
                    results.append({**_result(requirement, PASS, "setback_resolved_by_improvement_and_reviewed_response", latest.events),
                                    **resolution})
                else:
                    reason = ("unresolved_historical_negative_response" if any(g.negative_reasons for g in groups)
                              else "unresolved_injury_checkin_setback")
                    results.append(_result(requirement, UNKNOWN, reason,
                                           [e for g in groups if g.negative_reasons for e in g.events]))
            else:
                results.append(_result(requirement, PASS, "no_negative_response"))
        elif kind == "complete_history":
            results.append(_result(requirement, UNKNOWN, "history_truncated") if history_truncated
                           else _result(requirement, PASS, "history_complete"))
        elif kind == "completed_reviewed_exposure":
            qualifying = [e for e in performed if e.dose_completed.completion_state == "quantified"
                          or not requirement.requires_defined_dose or has_defined_prescribed_dose(e)]
            if qualifying:
                results.append(_result(requirement, PASS, "reviewed_stage_work_performed", qualifying))
            elif starter and requirement.basis == "data_sufficiency":
                results.append(_result(requirement, NOT_APPLICABLE, "prior_restore_not_required_for_reported_permission"))
            elif performed:
                # "Done as shown" of self-paced work is not completion of a defined dose.
                results.append(_result(requirement, UNKNOWN, "no_defined_dose_completed", performed))
            else:
                results.append(_result(requirement, UNKNOWN, "no_reviewed_stage_exposure"))
        elif kind == "measured_dose":
            measured = [e for e in performed if has_measured_amount(e)]
            results.append(_result(requirement, PASS, "measured_dose_completed", measured) if measured
                           else _result(requirement, UNKNOWN, "no_measured_dose"))
        elif kind in {"during_session_response", "next_day_response"}:
            field = "during_response" if kind == "during_session_response" else "next_day_response"
            response_group = response_latest
            if starter and unreadable_owned_work:
                results.append(_result(requirement, UNKNOWN, "incomplete_prior_rehab_evidence"))
            elif starter and response_group is None and requirement.basis == "product_safety":
                results.append(_result(requirement, NOT_APPLICABLE, "no_prior_rehab_response_to_resolve"))
            elif response_group is None:
                results.append(_result(requirement, UNKNOWN, "no_reviewed_response_group"))
            elif not response_group.group_id or not response_group.response_consistent:
                results.append(_result(requirement, UNKNOWN, "inconsistent_response_group", response_group.events))
            else:
                answer = getattr(response_group.events[0].response, field)
                if answer in requirement.allowed_responses:
                    results.append(_result(requirement, PASS, f"{field}_{answer}", response_group.events))
                elif answer == "worse":
                    reason = FAIL_DURING_RESPONSE_WORSE if field == "during_response" else FAIL_NEXT_DAY_RESPONSE_WORSE
                    results.append(_result(requirement, FAIL, reason, response_group.events))
                else:
                    results.append(_result(requirement, UNKNOWN, f"{field}_{answer}", response_group.events))
        elif kind == "minimum_observations":
            count = len(performed_groups)
            results.append(_result(requirement, PASS if count >= requirement.minimum else UNKNOWN,
                                   f"observed_response_groups_{count}_of_{requirement.minimum}",
                                   [e for g in performed_groups for e in g.events if e in performed]))
        elif kind == "functional_checkpoint":
            if (requirement.checkpoint == SHOULDER_CRITERION and policy.policy_id == "shoulder_tendonitis"
                    and (transition.from_stage, transition.to_stage) == ("restore", "load")):
                context = AssessmentContext.from_injury(injury, as_of=as_of,
                    setback_at=episode_setback_at(injury, exposures), history_truncated=history_truncated)
                entry = evaluate_shoulder_permission(context)
                results.append(_result(requirement, entry["status"], entry["reason_code"]))
            elif (requirement.checkpoint == ANKLE_CRITERION and policy.policy_id == "ankle_sprain"
                    and (transition.from_stage, transition.to_stage) == ("restore", "load")):
                context = AssessmentContext.from_injury(injury, as_of=as_of,
                    setback_at=episode_setback_at(injury, exposures), history_truncated=history_truncated)
                entry = evaluate_ankle_permission(context)
                results.append(_result(requirement, entry["status"], entry["reason_code"]))
            elif (requirement.checkpoint == PERMISSION_CRITERION and policy.policy_id == "elbow_tendonitis"
                    and (transition.from_stage, transition.to_stage) == ("restore", "load")):
                context = AssessmentContext.from_injury(injury, as_of=as_of,
                    setback_at=episode_setback_at(injury, exposures), history_truncated=history_truncated)
                entry = evaluate_elbow_permission(context)
                results.append(_result(requirement, entry["status"], entry["reason_code"]))
            elif (requirement.checkpoint == ELBOW_CRITERION and policy.policy_id == "elbow_tendonitis"
                    and (transition.from_stage, transition.to_stage) == ("restore", "load")):
                context = AssessmentContext.from_injury(injury, as_of=as_of,
                    setback_at=episode_setback_at(injury, exposures), history_truncated=history_truncated)
                entry = evaluate_elbow_entry(context)
                results.append({**_result(requirement, entry["status"], entry["reason_code"]),
                                "assessment_observation_id": entry.get("observation_id")})
            elif (requirement.checkpoint == LOAD_PERMISSION_CHECKPOINT and policy.policy_id == "achilles_tendonitis"
                    and (transition.from_stage, transition.to_stage) == ("restore", "load")):
                reason = achilles_load_permission_reason(injury)
                results.append(_result(requirement, UNKNOWN if reason else PASS,
                                       reason or "reported_permission_and_option_applicable"))
            elif (requirement.checkpoint == CRITERION_ID and policy.policy_id == "achilles_tendonitis"
                    and (transition.from_stage, transition.to_stage) == ("restore", "load")):
                context = AssessmentContext.from_injury(injury, as_of=as_of,
                    setback_at=episode_setback_at(injury, exposures), history_truncated=history_truncated)
                review = review_achilles_restore_load(context)
                results.append({**_result(requirement, review["status"], review["reason_codes"][0]),
                                "clinical_review": review})
            elif clinical_review_input is not None and requirement.checkpoint == clinical_review_input.context.criterion_id:
                supplied = clinical_review_input
                context = supplied.context
                assessed = AssessmentContext.from_injury(injury, as_of=as_of,
                    setback_at=episode_setback_at(injury, exposures), history_truncated=history_truncated)
                # An explicit shadow input cannot substitute a different engine
                # subject, policy, transition or hide known safety/history gates.
                matches = (context.athlete_id, context.injury_id, context.injury_episode_id, context.side,
                           context.profile_id, context.policy_version, context.policy_hash,
                           context.transition.from_stage, context.transition.to_stage) == (
                           str(injury.get("athlete_id")), str(injury.get("id")), str(injury.get("episode_id")), injury.get("side"),
                           policy.policy_id, policy.version, policy.content_hash, transition.from_stage, transition.to_stage)
                setback = assessed.setback_at
                unsafe = (assessed.medical_hold or not assessed.history_complete
                          or injury.get("latest_reported_status") == "worse"
                          or (setback and context.current_packet.evidence_cutoff <= setback))
                if not matches or unsafe or injury.get("status") not in {"open", "monitoring"}:
                    results.append(_result(requirement, UNKNOWN, ReviewReason.ENGINE_CONTEXT.value))
                else:
                    review = evaluate_clinical_review(context, supplied.reviews, as_of=as_of,
                        lifecycle=supplied.lifecycle, registry=supplied.registry, trust=supplied.trust)
                    result = review.model_dump(mode="json")
                    results.append({**_result(requirement, review.criterion_status.value, result["reason_codes"][0]),
                                    "clinical_review": result})
            elif CLINICAL_REVIEW_REGISTRY.current(requirement.checkpoint) is not None:
                results.append(_result(requirement, UNKNOWN, ReviewReason.MISSING.value))
            else:
                # Availability declarations cannot satisfy clinical checkpoints.
                results.append(_result(requirement, MISSING_INPUT, f"functional_checkpoint_not_captured:{requirement.checkpoint}"))
        elif kind == "input_availability":
            if requirement.checkpoint not in input_definitions():
                results.append(_result(requirement, MISSING_INPUT, f"assessment_input_not_captured:{requirement.checkpoint}"))
            else:
                context = AssessmentContext.from_injury(injury, as_of=as_of,
                    setback_at=episode_setback_at(injury, exposures), history_truncated=history_truncated)
                observed = read_assessment_input(requirement.checkpoint, context)
                results.append({**_result(requirement, observed["status"], observed["reason_code"]),
                                "checkpoint_observation": observed})
    reasons = [r["reason_code"] for r in results if r["status"] not in {PASS, NOT_APPLICABLE}]
    if transition.closed_reason:
        status, reasons = "closed", ["transition_closed_by_profile", *reasons]
    elif reasons:
        status = "blocked"
    elif not transition.promotable:
        status, reasons = "blocked", ["no_clinical_criteria_declared"]
    else:
        status = "met"
    live = transition.to_stage in policy.live_stages
    if status == "met" and not live:
        reasons = ["target_stage_not_activated"]
    authority = ({"entry_basis": "reported_clinician_permission",
                  "authority_event_id": str(injury["clinician_clearance"]["report_id"])} if starter else {})
    return {**authority, "from_stage": transition.from_stage, "to_stage": transition.to_stage, "status": status,
            "reason_codes": reasons, "target_stage_live": live, "closed_reason": transition.closed_reason,
            "missing_inputs": [r["reason_code"].split(":", 1)[1] for r in results if r["status"] == MISSING_INPUT],
            "requirements": results, "ignored_evidence": dict(sorted(ignored.items()))}


def resolve_reviewed_progression(injury: Mapping[str, Any], *, base_stage: str,
                                policy: ClinicalPolicy, exposures: Sequence[Mapping[str, Any]],
                                history_truncated: bool = False, as_of: datetime | None = None,
                                clinical_review_inputs: Mapping[str, ClinicalReviewInput] | None = None,
                                target_content_available: Mapping[str, bool] | None = None) -> dict[str, Any]:
    # Baseline: unchanged from the CALM/RESTORE-only engine.
    stage = base_stage if base_stage in {"calm", "restore"} else "calm"
    reasons = ["baseline_only_v1"]
    setback = _latest_setback_at(injury, exposures)
    reported_at = _improvement_at(injury)
    improving_after = reported_at and setback and reported_at > setback
    if injury.get("latest_reported_status") == "worse" or (setback and not improving_after):
        stage, reasons = "calm", ["episode_setback_loading_held"]
    if history_truncated:
        reasons.append("older_history_truncated_no_advanced_progression")
    result: dict[str, Any] = {"stage": stage, "reason_codes": reasons, "evidence_ids": [], "engine_version": "2"}
    # Declared transitions: one rung at a time, each judged on its own stage's work.
    by_source = {t.from_stage: t for t in policy.transitions}
    entry = next((t for t in policy.transitions if _reported_starter(t, injury, as_of or datetime.now(timezone.utc))), None)
    while stage in by_source or (stage == "calm" and entry is not None):
        transition = entry if stage == "calm" else by_source[stage]
        evaluation = evaluate_transition(transition, policy=policy, injury=injury,
            exposures=exposures, history_truncated=history_truncated, as_of=as_of,
            clinical_review_input=next((clinical_review_inputs[r.checkpoint] for r in transition.requirements
                if r.checkpoint in (clinical_review_inputs or {})), None))
        if (evaluation["status"] == "met" and target_content_available is not None
                and not target_content_available.get(evaluation["to_stage"], False)):
            evaluation.update(status="blocked", reason_codes=["reviewed_target_content_unavailable"])
        if evaluation["status"] != "met" or not evaluation["target_stage_live"]:
            result["next_transition"] = evaluation
            break
        stage = evaluation["to_stage"]
        reason = (f"reported_clinician_starter_entry:{stage}" if evaluation.get("entry_basis")
                  else f"transition_met:{evaluation['from_stage']}->{stage}")
        result.update(stage=stage, reason_codes=[reason])
        if evaluation.get("entry_basis"):
            result.update(entry_basis=evaluation["entry_basis"], authority_event_id=evaluation["authority_event_id"],
                          entry_decision=evaluation)
        result["evidence_ids"] = list(dict.fromkeys(
            [*result["evidence_ids"], *(i for r in evaluation["requirements"] for i in r["evidence_ids"])]))
    return result
