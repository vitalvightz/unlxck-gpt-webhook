"""The athlete path from "session done" to stored injury-specific evidence.

``api/contracts/rehab_completion.py`` decides *whether* a completed rehab drill
may become evidence. This module is what actually walks that path for a real
athlete on a real day:

1. A session is marked ``done`` or ``modified``.
2. :func:`session_rehab_items` reads that session's rehab blocks out of the
   stored structured plan, by canonical bank id — never by display name.
3. :func:`resolve_completed_session_rehab` runs the gate against the athlete's
   open injuries.
4. When something is genuinely attributable, the completion response carries the
   injury-specific prompts, so the block appears only for a session that
   actually contained rehab for a known injury. A normal training session
   returns none and the athlete is asked nothing.
5. The athlete answers, and :func:`record_rehab_exposures` re-resolves the same
   candidates server-side and appends the evidence.

Step 5 re-resolves rather than trusting the client. The submission returns the
server-issued injury episode context with the athlete's answers. That episode
must still match the current server record before any write; drill, side and
demand are recomputed from the plan and injury record. A client cannot assert an
attribution it was not given, and cannot log evidence against an injury the plan
never targeted.

General session feedback (RPE, pain-after, notes) stays exactly where it was.
It is programming feedback about a session; this is an observation about one
injury and one exposure, and the two are not interchangeable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Iterable, Mapping

from fastapi import HTTPException, status
from pydantic import ValidationError

from fightcamp.rehab_protocols import rehab_drill_by_id

from api.contracts.rehab_completion import (
    COMPLETED_STATUSES,
    DURING_ANSWERS,
    LIMIT_ANSWERS,
    RehabCompletionResolution,
    RehabResponsePrompt,
    build_exposure_id,
    build_rehab_exposure_event,
    build_rehab_response_prompts,
    build_response_group_id,
    resolve_rehab_completion,
)
from api.contracts.rehab_exposure import RehabExposureEvent

from .open_plan_timeline import project_open_structured_plan

__all__ = [
    "build_rehab_response_contexts",
    "collect_rehab_response_prompts",
    "list_pending_rehab_response_sets",
    "prompts_as_payload",
    "rehab_response_contexts_by_injury",
    "record_rehab_exposures",
    "resolve_completed_session_rehab",
    "session_rehab_items",
]

logger = logging.getLogger(__name__)
REHAB_RESPONSE_CONTEXT_VERSION = 1


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _measured_seconds(value: Any) -> float | None:
    """Seconds from a ``MeasuredValue``-shaped block field, when it states any."""
    if not isinstance(value, Mapping):
        return None
    amount = value.get("value")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
        return None
    unit = _clean(value.get("unit")).lower()
    if unit in {"second", "seconds", "sec", "s"}:
        return float(amount)
    if unit in {"minute", "minutes", "min", "m"}:
        return float(amount) * 60
    return None


def _prescribed_dose_from_block(block: Mapping[str, Any]) -> dict[str, Any]:
    """What the plan asked for on this block — only fields it actually states.

    This is the *prescription*, carried so the record shows what was asked
    alongside what was done. It is never read as what the athlete completed;
    :func:`~api.contracts.rehab_completion.completed_dose_from_session` owns
    that, and deliberately refuses to echo a prescribed dose back as a completed
    one.
    """
    dose: dict[str, Any] = {}
    sets = block.get("sets")
    if isinstance(sets, int) and not isinstance(sets, bool) and sets >= 0:
        dose["sets"] = sets
    reps = block.get("reps")
    if isinstance(reps, int) and not isinstance(reps, bool) and reps >= 0:
        # A rep range ("8-12") is a string here and is deliberately dropped
        # rather than collapsed to one of its ends.
        dose["reps"] = reps
    duration = _measured_seconds(block.get("duration"))
    if duration is not None:
        dose["duration_seconds"] = duration
    return dose


def _legacy_occurrence_base(block: Mapping[str, Any], drill_id: str) -> str:
    """Stable identity for an older block that has no ``block_id``.

    Current structured plans require a block id. For legacy rows, hash the
    stored block content while excluding only presentation order. Exact legacy
    duplicates receive deterministic occurrence suffixes in
    :func:`session_rehab_items`; reordering therefore preserves the same set of
    identities instead of turning array position into evidence identity.
    """
    stable_block = {key: value for key, value in block.items() if key != "order_index"}
    encoded = json.dumps(
        stable_block,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:24]
    return f"legacy:{drill_id}:{digest}"


def _structured_weeks(
    plan_row: Mapping[str, Any], *, training_day: str
) -> list[Mapping[str, Any]]:
    structured_plan = plan_row.get("structured_plan")
    if not isinstance(structured_plan, Mapping):
        return []
    projected, _context = project_open_structured_plan(
        plan_row,
        structured_plan,
        current_training_day=training_day,
    )
    weeks = projected.get("weeks") if isinstance(projected, Mapping) else None
    return _mappings(weeks)


def _session_blocks(
    plan_row: Mapping[str, Any], *, training_day: str, session_id: str
) -> list[Mapping[str, Any]]:
    """The blocks of one scheduled session, located by day and session id.

    Both must match. A session id alone is not enough: an open plan repeats its
    session ids across days, and evidence stamped with the wrong day would be
    attributed to work done on a different one.
    """
    for week in _structured_weeks(plan_row, training_day=training_day):
        for day in _mappings(week.get("days")):
            if _clean(day.get("date"))[:10] != training_day:
                continue
            sessions = _mappings(day.get("sessions"))
            for session in sessions:
                if _clean(session.get("session_id")) == session_id:
                    return _mappings(session.get("blocks"))
            # A day with a single session may carry the day's date as its id.
            if len(sessions) == 1 and session_id == training_day:
                return _mappings(sessions[0].get("blocks"))
    return []


def session_rehab_items(
    plan_row: Mapping[str, Any],
    *,
    training_day: str,
    session_id: str,
) -> list[dict[str, Any]]:
    """The session's rehab work, resolved back to canonical bank drills.

    A block contributes an item only when it is a rehab block *and* carries a
    ``rehab_drill_id`` the bank recognises. An unstamped or unrecognised block
    produces nothing at all — not a nameless item that the gate would then have
    to refuse. Non-rehab blocks are never considered: a hard session is not
    rehab evidence however it felt.

    Each stored block occurrence yields one item. Repeated uses of the same
    drill remain distinct when their stable ``block_id`` values differ. A
    duplicated block id is treated as the same stored occurrence, while older
    blocks without ids use a content-derived key plus a deterministic duplicate
    suffix. Array position alone is never identity.
    """
    items: list[dict[str, Any]] = []
    seen_occurrences: set[str] = set()
    legacy_counts: dict[str, int] = {}
    for block in _session_blocks(plan_row, training_day=training_day, session_id=session_id):
        if _clean(block.get("block_type")) != "rehab":
            continue
        drill_id = _clean(block.get("rehab_drill_id"))
        if not drill_id:
            continue
        drill = rehab_drill_by_id(drill_id)
        if not isinstance(drill, Mapping):
            continue
        block_id = _clean(block.get("block_id"))
        if block_id:
            occurrence_key = f"block:{block_id}"
        else:
            base = _legacy_occurrence_base(block, drill_id)
            legacy_counts[base] = legacy_counts.get(base, 0) + 1
            occurrence_key = f"{base}:{legacy_counts[base]}"
        if occurrence_key in seen_occurrences:
            continue
        seen_occurrences.add(occurrence_key)
        item = dict(drill)
        item["rehab_occurrence_key"] = occurrence_key
        prescribed = _prescribed_dose_from_block(block)
        if prescribed:
            item["prescribed_dose"] = prescribed
        items.append(item)
    return items


def _open_injuries(store: Any, athlete_id: str) -> list[Mapping[str, Any]]:
    lister = getattr(store, "list_injury_flags", None)
    if not callable(lister):
        return []
    return _mappings(lister(athlete_id, statuses=("open", "monitoring")) or [])


def resolve_completed_session_rehab(
    store: Any,
    *,
    athlete_id: str,
    plan_row: Mapping[str, Any],
    training_day: str,
    session_id: str,
    completion: Mapping[str, Any] | None,
) -> tuple[RehabCompletionResolution, list[Mapping[str, Any]]]:
    """Run the completion gate for one session. Returns the resolution + injuries.

    The injuries are returned alongside because the caller needs the same list
    the gate used — re-reading it would risk asking about one set of injuries
    and recording against another.
    """
    plan_id = _clean(plan_row.get("id"))
    completion_plan_id = _clean((completion or {}).get("plan_id"))
    if not plan_id or completion_plan_id != plan_id:
        return RehabCompletionResolution(), []
    if _clean((completion or {}).get("status")).lower() not in COMPLETED_STATUSES:
        return RehabCompletionResolution(), []
    items = session_rehab_items(plan_row, training_day=training_day, session_id=session_id)
    if not items:
        return RehabCompletionResolution(), []
    injuries = _open_injuries(store, athlete_id)
    resolution = resolve_rehab_completion(items, injuries, completion=completion)
    return resolution, injuries


def collect_rehab_response_prompts(
    store: Any,
    *,
    athlete_id: str,
    plan_row: Mapping[str, Any],
    training_day: str,
    session_id: str,
    completion: Mapping[str, Any] | None,
) -> tuple[RehabResponsePrompt, ...]:
    """The injury-specific prompts this completion should raise, if any.

    Empty for every session that did not contain attributable rehab work, which
    is what keeps the block off a normal training session.
    """
    resolution, injuries = resolve_completed_session_rehab(
        store,
        athlete_id=athlete_id,
        plan_row=plan_row,
        training_day=training_day,
        session_id=session_id,
        completion=completion,
    )
    if not resolution.has_attributable_rehab:
        return ()
    return build_rehab_response_prompts(resolution, injuries)


def build_rehab_response_contexts(
    store: Any,
    *,
    athlete_id: str,
    plan_row: Mapping[str, Any],
    training_day: str,
    session_id: str,
    completion: Mapping[str, Any],
) -> tuple[tuple[RehabResponsePrompt, ...], list[dict[str, Any]]]:
    """Snapshot immutable response identity for one newly completed session.

    The snapshot deliberately excludes demand, region, side and interpretation.
    It remembers only which completion, injury episode and canonical rehab block
    occurrences created the unanswered opportunity. Fixed questions are rebuilt
    from code when the prompt is read again.
    """
    resolution, injuries = resolve_completed_session_rehab(
        store,
        athlete_id=athlete_id,
        plan_row=plan_row,
        training_day=training_day,
        session_id=session_id,
        completion=completion,
    )
    prompts = build_rehab_response_prompts(resolution, injuries)
    plan_id = _clean(plan_row.get("id"))
    completion_id = _clean(completion.get("id"))
    contexts: list[dict[str, Any]] = []
    for prompt in prompts:
        candidates = [
            candidate
            for candidate in resolution.eligible
            if _clean(candidate.injury_id) == prompt.injury_id
        ]
        response_group_id = str(
            build_response_group_id(
                athlete_id=athlete_id,
                plan_id=plan_id,
                injury_episode_id=prompt.injury_episode_id,
                session_id=session_id,
                training_day=training_day,
            )
        )
        expected_exposures = [
            {
                "exposure_id": str(
                    build_exposure_id(
                        athlete_id=athlete_id,
                        plan_id=plan_id,
                        injury_episode_id=prompt.injury_episode_id,
                        drill_id=candidate.drill_id,
                        session_id=session_id,
                        training_day=training_day,
                        rehab_occurrence_key=candidate.rehab_occurrence_key,
                    )
                ),
                "drill_id": candidate.drill_id,
                "rehab_occurrence_key": candidate.rehab_occurrence_key,
            }
            for candidate in candidates
        ]
        contexts.append(
            {
                "version": REHAB_RESPONSE_CONTEXT_VERSION,
                # The existing deterministic response-group identity is also
                # the opaque identity of this one injury-level opportunity.
                "response_context_id": response_group_id,
                "athlete_id": athlete_id,
                "plan_id": plan_id,
                "session_id": session_id,
                "training_day": training_day,
                "session_completion_id": completion_id,
                "injury_id": prompt.injury_id,
                "injury_episode_id": prompt.injury_episode_id,
                "response_group_id": response_group_id,
                "expected_exposures": expected_exposures,
            }
        )
    return prompts, contexts


def _saved_contexts(completion: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = completion.get("rehab_response_contexts")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def rehab_response_contexts_by_injury(
    completion: Mapping[str, Any], *, athlete_id: str | None = None
) -> dict[str, dict[str, Any]]:
    """Saved contexts keyed by injury id; malformed duplicates fail closed."""
    result: dict[str, dict[str, Any]] = {}
    for context in _saved_contexts(completion):
        if athlete_id is not None and not _context_matches_completion(
            context, athlete_id=athlete_id, completion=completion
        ):
            continue
        injury_id = _clean(context.get("injury_id"))
        if not injury_id or injury_id in result:
            continue
        result[injury_id] = context
    return result


def _context_matches_completion(
    context: Mapping[str, Any], *, athlete_id: str, completion: Mapping[str, Any]
) -> bool:
    return (
        context.get("version") == REHAB_RESPONSE_CONTEXT_VERSION
        and _clean(context.get("athlete_id")) == athlete_id
        and _clean(context.get("plan_id")) == _clean(completion.get("plan_id"))
        and _clean(context.get("session_id")) == _clean(completion.get("session_id"))
        and _clean(context.get("training_day")) == _clean(completion.get("training_day"))
        and _clean(context.get("session_completion_id")) == _clean(completion.get("id"))
        and bool(_clean(context.get("injury_id")))
        and bool(_clean(context.get("injury_episode_id")))
        and bool(_clean(context.get("response_group_id")))
    )


def _expected_exposure_ids(context: Mapping[str, Any]) -> list[str]:
    return [
        _clean(item.get("exposure_id"))
        for item in _mappings(context.get("expected_exposures"))
        if _clean(item.get("exposure_id"))
    ]


def _event_satisfies_context(row: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    event = row.get("event_json")
    if not isinstance(event, Mapping):
        return False
    return (
        _clean(row.get("id") or event.get("exposure_id"))
        in set(_expected_exposure_ids(context))
        and _clean(event.get("injury_id")) == _clean(context.get("injury_id"))
        and _clean(event.get("injury_episode_id"))
        == _clean(context.get("injury_episode_id"))
        and _clean(event.get("response_group_id"))
        == _clean(context.get("response_group_id"))
    )


def _canonical_stored_event(
    row: Mapping[str, Any], context: Mapping[str, Any]
) -> RehabExposureEvent:
    """Return one context-bound canonical event or reject corrupted identity."""
    event_payload = row.get("event_json")
    if not isinstance(event_payload, Mapping) or not _event_satisfies_context(row, context):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="stale_rehab_response_context",
        )
    try:
        return RehabExposureEvent.model_validate(event_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="invalid_persisted_rehab_exposure",
        ) from exc


def _response_semantics(event: RehabExposureEvent) -> str:
    """Stable injury-level answer semantics copied across one response group."""
    return json.dumps(
        {
            "response": event.response.model_dump(mode="json"),
            "completion_state": event.dose_completed.completion_state,
            "stopped_early": event.dose_completed.stopped_early,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _with_response_semantics(
    event: RehabExposureEvent, canonical: RehabExposureEvent
) -> RehabExposureEvent:
    """Use an already-persisted injury answer for a missing group exposure."""
    return event.model_copy(
        update={
            "response": canonical.response.model_copy(deep=True),
            "dose_completed": event.dose_completed.model_copy(
                update={
                    "completion_state": canonical.dose_completed.completion_state,
                    "stopped_early": canonical.dose_completed.stopped_early,
                }
            ),
        }
    )


def _prompt_from_context(
    context: Mapping[str, Any], injury: Mapping[str, Any]
) -> RehabResponsePrompt:
    side = _clean(injury.get("side")).lower()
    region = _clean(injury.get("body_region")).lower()
    label = _clean(injury.get("label")) or " ".join(
        part for part in (side if side in {"left", "right"} else "", region) if part
    ).strip()
    return RehabResponsePrompt(
        injury_id=_clean(context.get("injury_id")),
        injury_episode_id=_clean(context.get("injury_episode_id")),
        injury_label=label.upper(),
        body_region=region,
        side=side,
        drill_ids=tuple(
            _clean(item.get("drill_id"))
            for item in _mappings(context.get("expected_exposures"))
            if _clean(item.get("drill_id"))
        ),
    )


def list_pending_rehab_response_sets(
    store: Any,
    *,
    athlete_id: str,
    completions: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rehydrate unanswered valid prompts from immutable completion context."""
    completion_rows = [row for row in completions if isinstance(row, Mapping)]
    valid: list[tuple[Mapping[str, Any], dict[str, Any], Mapping[str, Any]]] = []
    for completion in completion_rows:
        if _clean(completion.get("status")).lower() not in COMPLETED_STATUSES:
            continue
        for context in _saved_contexts(completion):
            if not _context_matches_completion(context, athlete_id=athlete_id, completion=completion):
                logger.warning(
                    "[rehab] pending_context_invalid athlete_id=%s completion_id=%s",
                    athlete_id,
                    _clean(completion.get("id")),
                )
                continue
            injury_reader = getattr(store, "get_injury_flag_for_athlete", None)
            injury = (
                injury_reader(_clean(context.get("injury_id")), athlete_id)
                if callable(injury_reader)
                else None
            )
            current_episode = _clean((injury or {}).get("episode_id"))
            saved_episode = _clean(context.get("injury_episode_id"))
            current_status = _clean((injury or {}).get("status")).lower()
            if current_episode != saved_episode or current_status not in {"open", "monitoring"}:
                stale_reason = (
                    "injury_episode_mismatch"
                    if current_episode != saved_episode
                    else "injury_inactive"
                )
                logger.info(
                    "[rehab] stale_pending_suppressed reason=%s athlete_id=%s completion_id=%s injury_id=%s saved_episode_id=%s current_episode_id=%s current_status=%s",
                    stale_reason,
                    athlete_id,
                    _clean(completion.get("id")),
                    _clean(context.get("injury_id")),
                    saved_episode,
                    current_episode,
                    current_status,
                )
                continue
            expected_ids = _expected_exposure_ids(context)
            if not expected_ids:
                logger.warning(
                    "[rehab] pending_context_has_no_exposures athlete_id=%s completion_id=%s injury_id=%s",
                    athlete_id,
                    _clean(completion.get("id")),
                    _clean(context.get("injury_id")),
                )
                continue
            valid.append((completion, context, injury or {}))

    all_ids = list(
        dict.fromkeys(
            exposure_id
            for _completion, context, _injury in valid
            for exposure_id in _expected_exposure_ids(context)
        )
    )
    reader = getattr(store, "list_rehab_exposures_by_ids", None)
    stored_rows = reader(athlete_id, all_ids) if callable(reader) and all_ids else []
    stored_by_id = {
        _clean(row.get("id") or (row.get("event_json") or {}).get("exposure_id")): row
        for row in stored_rows or []
        if isinstance(row, Mapping)
    }

    grouped: dict[str, dict[str, Any]] = {}
    for completion, context, injury in valid:
        expected_ids = _expected_exposure_ids(context)
        satisfied = {
            exposure_id
            for exposure_id in expected_ids
            if exposure_id in stored_by_id
            and _event_satisfies_context(stored_by_id[exposure_id], context)
        }
        if len(satisfied) == len(expected_ids):
            continue
        completion_id = _clean(completion.get("id"))
        response_set = grouped.setdefault(
            completion_id,
            {
                "completion_id": completion_id,
                "plan_id": _clean(completion.get("plan_id")),
                "session_id": _clean(completion.get("session_id")),
                "training_day": _clean(completion.get("training_day")),
                "rehab_response_prompts": [],
            },
        )
        response_set["rehab_response_prompts"].append(
            prompts_as_payload([_prompt_from_context(context, injury)])[0]
        )
    return list(grouped.values())


def record_rehab_exposures(
    store: Any,
    *,
    athlete_id: str,
    plan_row: Mapping[str, Any],
    training_day: str,
    session_id: str,
    completion: Mapping[str, Any] | None,
    answers: Mapping[str, Mapping[str, Any]],
    expected_contexts: Mapping[str, Mapping[str, Any]] | None = None,
    source: str = "athlete_logged_rehab",
) -> list[RehabExposureEvent]:
    """Append one exposure per eligible candidate the athlete answered for.

    ``answers`` is keyed by injury id — the same grouping the athlete was asked
    in. Its server-issued episode id is checked against the current injury row
    before any write begins. Everything else about the event is recomputed here;
    an answer for an injury this session had no attributable rehab for is ignored
    rather than stored, because the client does not get to assert that the work
    happened.

    Exposure ids include the stored plan and rehab-block occurrence, so a retry
    of one block is idempotent while two real uses of the same drill remain two
    observations.
    """
    if expected_contexts is not None:
        unexpected = set(answers) - set(expected_contexts)
        if unexpected:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="rehab_response_not_pending",
            )

    resolution, injuries = resolve_completed_session_rehab(
        store,
        athlete_id=athlete_id,
        plan_row=plan_row,
        training_day=training_day,
        session_id=session_id,
        completion=completion,
    )
    injuries_by_id = {_clean(injury.get("id")): injury for injury in injuries}
    # Validate the whole batch first. A delayed prompt must never be silently
    # rebound after the same injury flag rotates to a new evidence episode, and
    # a stale answer in a multi-injury request must not leave partial writes.
    for injury_id, answer in answers.items():
        injury = injuries_by_id.get(_clean(injury_id))
        expected_episode_id = _clean(answer.get("injury_episode_id"))
        current_episode_id = _clean((injury or {}).get("episode_id"))
        if not current_episode_id or current_episode_id != expected_episode_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="stale_rehab_response",
            )

    pending_events: list[RehabExposureEvent] = []
    for candidate in resolution.eligible:
        answer = answers.get(_clean(candidate.injury_id))
        if not isinstance(answer, Mapping):
            continue
        event = build_rehab_exposure_event(
            candidate,
            athlete_id=athlete_id,
            plan_id=_clean(plan_row.get("id")),
            session_id=session_id,
            training_day=training_day,
            completion=completion,
            during=answer.get("during_response"),
            limit=answer.get("limit_response"),
            source=source,
        )
        injury = injuries_by_id.get(_clean(candidate.injury_id))
        if injury is None or not event.is_attributable_to(injury):
            # The same identity check `POST /api/rehab-exposures` applies, so
            # both write paths agree. Reaching it means this module's own
            # resolution disagrees with the injury row it came from, which is a
            # bug rather than a client error — refuse loudly instead of writing
            # an observation nobody can trust.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="exposure does not match the injury episode, region and side",
            )
        pending_events.append(event)

    if expected_contexts is not None:
        for injury_id in answers:
            context = expected_contexts[injury_id]
            expected_ids = set(_expected_exposure_ids(context))
            matching = [
                event for event in pending_events if str(event.injury_id) == injury_id
            ]
            actual_ids = {str(event.exposure_id) for event in matching}
            expected_group = _clean(context.get("response_group_id"))
            if actual_ids != expected_ids or any(
                str(event.response_group_id or "") != expected_group for event in matching
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="stale_rehab_response_context",
                )

    existing_by_id: dict[str, RehabExposureEvent] = {}
    canonical_by_injury: dict[str, RehabExposureEvent] = {}
    if expected_contexts is not None:
        contexts_by_exposure_id = {
            exposure_id: expected_contexts[injury_id]
            for injury_id in answers
            for exposure_id in _expected_exposure_ids(expected_contexts[injury_id])
        }
        reader = getattr(store, "list_rehab_exposures_by_ids", None)
        if not callable(reader):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="rehab exposure recovery unavailable",
            )
        stored_rows = reader(athlete_id, list(contexts_by_exposure_id))
        for row in stored_rows or []:
            if not isinstance(row, Mapping):
                continue
            stored_payload = row.get("event_json")
            payload_exposure_id = (
                stored_payload.get("exposure_id")
                if isinstance(stored_payload, Mapping)
                else None
            )
            exposure_id = _clean(row.get("id") or payload_exposure_id)
            context = contexts_by_exposure_id.get(exposure_id)
            if context is None or exposure_id in existing_by_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="stale_rehab_response_context",
                )
            existing_by_id[exposure_id] = _canonical_stored_event(row, context)

        for injury_id in answers:
            existing_group = [
                existing_by_id[exposure_id]
                for exposure_id in _expected_exposure_ids(expected_contexts[injury_id])
                if exposure_id in existing_by_id
            ]
            if not existing_group:
                continue
            if len({_response_semantics(event) for event in existing_group}) != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="rehab_response_group_conflict",
                )
            canonical_by_injury[injury_id] = existing_group[0]

    recorded: list[RehabExposureEvent] = []
    for proposed_event in pending_events:
        exposure_id = str(proposed_event.exposure_id)
        existing = existing_by_id.get(exposure_id)
        if existing is not None:
            recorded.append(existing)
            continue
        canonical = canonical_by_injury.get(str(proposed_event.injury_id))
        event = (
            _with_response_semantics(proposed_event, canonical)
            if canonical is not None
            else proposed_event
        )
        store.create_rehab_exposure(athlete_id, event.model_dump(mode="json"))
        recorded.append(event)
    return recorded


def prompts_as_payload(prompts: Iterable[RehabResponsePrompt]) -> list[dict[str, Any]]:
    """Render prompts for the API response, questions and vocabularies included."""
    return [
        {
            "injury_id": prompt.injury_id,
            "injury_episode_id": prompt.injury_episode_id,
            "injury_label": prompt.injury_label,
            "body_region": prompt.body_region,
            "side": prompt.side,
            "drill_ids": list(prompt.drill_ids),
            "during_question": prompt.during_question,
            "during_options": list(DURING_ANSWERS),
            "limit_question": prompt.limit_question,
            "limit_options": list(LIMIT_ANSWERS),
        }
        for prompt in prompts
    ]
