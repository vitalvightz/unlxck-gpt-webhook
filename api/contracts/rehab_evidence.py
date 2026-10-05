"""Exact injury-episode exposure evidence for stage-transition evaluation.

Only immutable :class:`RehabExposureEvent` observations for one exact athlete,
injury, episode, region and side are read. Invalid, duplicate or mismatched rows
are counted as ignored diagnostics and can never become positive evidence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from .rehab_exposure import RehabExposureEvent, nonspecific_policy_type_matches

IGNORED_INVALID_EVENT = "ignored_invalid_event"
IGNORED_ATHLETE_MISMATCH = "ignored_athlete_mismatch"
IGNORED_INJURY_MISMATCH = "ignored_injury_mismatch"
IGNORED_EPISODE_MISMATCH = "ignored_episode_mismatch"
IGNORED_REGION_MISMATCH = "ignored_region_mismatch"
IGNORED_SIDE_MISMATCH = "ignored_side_mismatch"
IGNORED_TYPE_MISMATCH = "ignored_type_mismatch"
IGNORED_DUPLICATE_EXPOSURE = "ignored_duplicate_exposure"

FAIL_STOPPED_DUE_TO_SYMPTOMS = "fail_stopped_due_to_symptoms"
FAIL_DURING_RESPONSE_WORSE = "fail_during_response_worse"
FAIL_NEXT_DAY_RESPONSE_WORSE = "fail_next_day_response_worse"
FAIL_WORSENING_REPORTED = "fail_worsening_reported"


@dataclass(frozen=True)
class ResponseGroup:
    """One athlete answer, possibly copied onto several exposures."""
    group_id: str | None
    events: tuple[RehabExposureEvent, ...]
    negative_reasons: tuple[str, ...]
    response_consistent: bool


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _side(value: Any) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def side_matches(injury_side: str, event_side: str) -> bool:
    if injury_side in {"", "unknown"} or event_side == "unknown":
        return False
    return injury_side == event_side or "bilateral" in {injury_side, event_side}


def read_exact_events(*, athlete_id: str, injury: Mapping[str, Any],
                      exposure_rows: Sequence[Mapping[str, Any]]) -> tuple[list[RehabExposureEvent], Counter[str]]:
    ignored: Counter[str] = Counter()
    events: list[RehabExposureEvent] = []
    seen: set[str] = set()
    injury_id, episode_id = _clean(injury.get("id")), _clean(injury.get("episode_id"))
    body_region, injury_side = _clean(injury.get("body_region")), _side(injury.get("side"))
    for row in exposure_rows or ():
        if not isinstance(row, Mapping):
            ignored[IGNORED_INVALID_EVENT] += 1
            continue
        if _clean(row.get("athlete_id")) != athlete_id:
            ignored[IGNORED_ATHLETE_MISMATCH] += 1
            continue
        raw_event = row.get("event_json")
        if not isinstance(raw_event, Mapping):
            ignored[IGNORED_INVALID_EVENT] += 1
            continue
        try:
            event = RehabExposureEvent.model_validate(raw_event)
        except (ValidationError, TypeError, ValueError):
            ignored[IGNORED_INVALID_EVENT] += 1
            continue
        exposure_id = str(event.exposure_id)
        if exposure_id in seen:
            ignored[IGNORED_DUPLICATE_EXPOSURE] += 1
            continue
        seen.add(exposure_id)
        if str(event.injury_id) != injury_id:
            ignored[IGNORED_INJURY_MISMATCH] += 1
        elif str(event.injury_episode_id) != episode_id:
            ignored[IGNORED_EPISODE_MISMATCH] += 1
        elif event.body_region != body_region:
            ignored[IGNORED_REGION_MISMATCH] += 1
        elif not nonspecific_policy_type_matches(event.provenance.policy_id, injury):
            ignored[IGNORED_TYPE_MISMATCH] += 1
        elif not side_matches(injury_side, event.side):
            ignored[IGNORED_SIDE_MISMATCH] += 1
        else:
            events.append(event)
    events.sort(key=lambda event: (event.occurred_at, str(event.exposure_id)))
    return events, ignored


def negative_reasons(event: RehabExposureEvent) -> tuple[str, ...]:
    response = event.response
    reasons = []
    if response.stopped_due_to_symptoms is True or event.dose_completed.stopped_early is True:
        reasons.append(FAIL_STOPPED_DUE_TO_SYMPTOMS)
    if response.during_response == "worse":
        reasons.append(FAIL_DURING_RESPONSE_WORSE)
    if response.next_day_response == "worse":
        reasons.append(FAIL_NEXT_DAY_RESPONSE_WORSE)
    if response.worsening_reported is True:
        reasons.append(FAIL_WORSENING_REPORTED)
    return tuple(reasons)


def _signature(event: RehabExposureEvent) -> tuple[Any, ...]:
    r = event.response
    return (r.during_response, r.next_day_response, r.stopped_due_to_symptoms, r.worsening_reported)


def group_events(events: Sequence[RehabExposureEvent]) -> list[ResponseGroup]:
    """Group copied answers so one response is never counted as several."""
    grouped: dict[str, list[RehabExposureEvent]] = {}
    for event in events:
        # A missing group stays isolated and can never qualify positively.
        key = str(event.response_group_id) if event.response_group_id else f"missing:{event.exposure_id}"
        grouped.setdefault(key, []).append(event)
    groups = [ResponseGroup(
        group_id=None if key.startswith("missing:") else key, events=tuple(members),
        negative_reasons=tuple(dict.fromkeys(r for e in members for r in negative_reasons(e))),
        response_consistent=len({_signature(e) for e in members}) == 1,
    ) for key, members in grouped.items()]
    groups.sort(key=lambda group: (group.events[0].occurred_at, str(group.events[0].exposure_id)))
    return groups


def has_measured_amount(event: RehabExposureEvent) -> bool:
    dose = event.dose_completed
    measured = (dose.sets, dose.reps, dose.duration_seconds, dose.external_load_kg,
                dose.distance_metres, dose.hold_seconds, dose.completed_fraction)
    return dose.completion_state == "quantified" and any(isinstance(v, (int, float)) and v > 0 for v in measured)


def has_defined_prescribed_dose(event: RehabExposureEvent) -> bool:
    dose = event.prescribed_dose
    return dose is not None and any(
        isinstance(v, (int, float)) and v > 0
        for v in (dose.sets, dose.reps, dose.duration_seconds, dose.external_load_kg, dose.distance_metres, dose.hold_seconds))
