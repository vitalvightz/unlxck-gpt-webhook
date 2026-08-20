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
from typing import Any, Iterable, Mapping

from fastapi import HTTPException, status

from fightcamp.rehab_protocols import rehab_drill_by_id

from api.contracts.rehab_completion import (
    COMPLETED_STATUSES,
    DURING_ANSWERS,
    LIMIT_ANSWERS,
    RehabCompletionResolution,
    RehabResponsePrompt,
    build_rehab_exposure_event,
    build_rehab_response_prompts,
    resolve_rehab_completion,
)
from api.contracts.rehab_exposure import RehabExposureEvent

from .open_plan_timeline import project_open_structured_plan

__all__ = [
    "collect_rehab_response_prompts",
    "prompts_as_payload",
    "record_rehab_exposures",
    "resolve_completed_session_rehab",
    "session_rehab_items",
]


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


def record_rehab_exposures(
    store: Any,
    *,
    athlete_id: str,
    plan_row: Mapping[str, Any],
    training_day: str,
    session_id: str,
    completion: Mapping[str, Any] | None,
    answers: Mapping[str, Mapping[str, Any]],
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

    recorded: list[RehabExposureEvent] = []
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
