"""Calendar projection for renewable open training plans.

Open plans do not have an event countdown. Their persisted structured card is a
weekly template (or four already-expanded weeks), and this module projects it
onto the current renewable block from one stable anchor: the Monday of the week
the athlete can start training in — the creation week for a plan generated
Mon-Thu, the coming Monday for one generated Fri-Sun (see
``open_plan_anchor_date``).

The projection is deliberately strict.  Legacy cards are only assigned
weekdays when their day count and coach-owned pattern agree with the saved
``open_plan_spec.weekly_template``; ambiguous cards remain undated rather than
silently attaching a session to the wrong day.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date, timedelta
from typing import Any, Mapping

from fightcamp.weekly_schedule_view import normalize_weekday


WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_COACH_LED_RE = re.compile(r"\b(coach|spar|boxing|pads?|mitts?|technical\s+only)\b", re.I)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except (ValueError, AttributeError):
        return None


def _ordered_weekdays(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized = {day for value in values if (day := normalize_weekday(value))}
    return [day for day in WEEKDAYS if day in normalized]


def open_plan_spec(plan_row: Mapping[str, Any]) -> dict[str, Any] | None:
    if _parse_date(plan_row.get("fight_date")) is not None:
        return None
    planning_brief = _mapping(plan_row.get("planning_brief"))
    spec = planning_brief.get("open_plan_spec")
    if not isinstance(spec, Mapping) or spec.get("plan_type") != "open_ongoing_system":
        return None
    return dict(spec)


def schedule_mode(plan_row: Mapping[str, Any]) -> str:
    if _parse_date(plan_row.get("fight_date")) is not None:
        return "event_countdown"
    if open_plan_spec(plan_row) is not None:
        return "open_recurring"
    return "static_undated"


# How far into the week a plan can be created and still join the week it was
# created in. Creating on Mon-Thu leaves at least three days of the block's first
# week to train, so the plan goes live immediately; a Fri/Sat/Sun plan would join
# a week that is effectively over, so it starts on the coming Monday instead.
_JOIN_CURRENT_WEEK_SHIFT = timedelta(days=3)


def _athlete_local_creation_date(plan_row: Mapping[str, Any]) -> date | None:
    """Creation date corrected to the athlete-local calendar day when known.

    ``plans.created_at`` is stored as a UTC timestamp. Around midnight UTC its
    date prefix can be one day ahead of, or behind, the athlete's local date. The
    Stage 2 planning brief already persists the creation weekday together with
    ``plan_creation_weekday_basis=athlete_local_weekday``. Since real timezone
    offsets can only move a timestamp onto the same, previous, or next calendar
    day, that persisted weekday is enough to correct the UTC date without adding
    timezone-dependent response plumbing or changing the database schema.

    Legacy briefs without the explicit athlete-local basis keep the historical
    UTC/date-only fallback.
    """

    created = _parse_date(plan_row.get("created_at"))
    if created is None:
        return None

    planning_brief = _mapping(plan_row.get("planning_brief"))
    athlete_model = planning_brief.get("athlete_model")
    if not isinstance(athlete_model, Mapping):
        return created
    if athlete_model.get("plan_creation_weekday_basis") != "athlete_local_weekday":
        return created

    local_weekday = normalize_weekday(athlete_model.get("plan_creation_weekday"))
    if local_weekday not in WEEKDAYS:
        return created

    utc_weekday_index = created.weekday()
    local_weekday_index = WEEKDAYS.index(local_weekday)
    if local_weekday_index == (utc_weekday_index - 1) % 7:
        return created - timedelta(days=1)
    if local_weekday_index == (utc_weekday_index + 1) % 7:
        return created + timedelta(days=1)
    return created


def open_plan_anchor_date(plan_row: Mapping[str, Any]) -> date | None:
    """The Monday the plan's renewable block starts on.

    A plan is generated mid-week far more often than on a Monday, so the anchor
    is the Monday of the week the athlete can actually start training in: the
    current week for a Mon-Thu plan, the coming Monday for a Fri-Sun one.
    Anchoring every plan forward to the *next* Monday left a plan created on
    Tuesday dormant for six days, and made the projected block sit a week ahead
    of the live calendar — so nothing on the plan matched the real training day.
    """

    created = _athlete_local_creation_date(plan_row)
    if created is None:
        return None
    shifted = created + _JOIN_CURRENT_WEEK_SHIFT
    return shifted - timedelta(days=shifted.weekday())


def _coach_owned_days(template: Mapping[str, Any]) -> list[str]:
    coach_owned = template.get("coach_owned_days")
    coach_owned = coach_owned if isinstance(coach_owned, Mapping) else {}
    values: list[Any] = []
    for key in ("technical_skill_days", "hard_sparring_days"):
        raw = coach_owned.get(key)
        if isinstance(raw, (list, tuple, set)):
            values.extend(raw)
    # Older open-plan briefs only exposed hard_sparring_days at template level.
    raw_hard = template.get("hard_sparring_days")
    if isinstance(raw_hard, (list, tuple, set)):
        values.extend(raw_hard)
    return _ordered_weekdays(values)


def _is_coach_led_day(day: Mapping[str, Any]) -> bool:
    today_card = day.get("today_card")
    today_card = today_card if isinstance(today_card, Mapping) else {}
    if str(today_card.get("coach_led_contact") or "").strip():
        return True

    sessions = [item for item in (day.get("sessions") or []) if isinstance(item, Mapping)]
    has_executable_blocks = any(
        isinstance(session.get("blocks"), list) and bool(session.get("blocks"))
        for session in sessions
    )
    text = " ".join(
        str(value or "")
        for value in (
            today_card.get("headline"),
            *(session.get("title") for session in sessions),
            *(session.get("session_type") for session in sessions),
        )
    )
    return not has_executable_blocks and _COACH_LED_RE.search(text) is not None


def _is_safe_legacy_off_day(day: Mapping[str, Any]) -> bool:
    """Whether a full-calendar legacy slot is provably not a training day."""

    sessions = [item for item in (day.get("sessions") or []) if isinstance(item, Mapping)]
    today_card = day.get("today_card")
    today_card = today_card if isinstance(today_card, Mapping) else {}
    return (
        not sessions
        and not str(today_card.get("coach_led_contact") or "").strip()
        and str(day.get("day_type") or "").strip().lower() in {"rest", "recovery"}
    )


def _resolve_template_days(
    days: Any, training_days: list[str]
) -> list[dict[str, Any]] | None:
    """Resolve one template week without guessing ambiguous session placement.

    Current cards contain only the configured training weekdays.  One historical
    converter emitted all seven calendar slots instead; that shape is safe to
    recover only when every omitted weekday is an empty rest/recovery day.
    """

    if not isinstance(days, list):
        return None

    if len(days) == len(training_days):
        pairs = list(zip(training_days, days, strict=True))
    elif len(days) == len(WEEKDAYS):
        calendar_pairs = list(zip(WEEKDAYS, days, strict=True))
        for weekday, day in calendar_pairs:
            if not isinstance(day, Mapping):
                return None
            explicit_weekday = normalize_weekday(day.get("weekday"))
            if explicit_weekday and explicit_weekday != weekday:
                return None
            if weekday not in training_days and not _is_safe_legacy_off_day(day):
                return None
        pairs = [(weekday, day) for weekday, day in calendar_pairs if weekday in training_days]
    else:
        return None

    resolved: list[dict[str, Any]] = []
    for weekday, day in pairs:
        if not isinstance(day, Mapping):
            return None
        explicit_weekday = normalize_weekday(day.get("weekday"))
        if explicit_weekday and explicit_weekday != weekday:
            return None
        normalized = copy.deepcopy(dict(day))
        normalized["weekday"] = weekday
        resolved.append(normalized)
    return resolved


_OPEN_TEMPLATE_WEEK_TYPES = ("stabilise", "build", "specific_peak", "deload")


def _expand_single_template_week(
    weeks: list[dict[str, Any]], spec: Mapping[str, Any]
) -> list[dict[str, Any]] | None:
    if len(weeks) == 4:
        return weeks
    if len(weeks) != 1:
        return None

    development = spec.get("development_block")
    development = development if isinstance(development, Mapping) else {}
    base = weeks[0]
    base_id = str(base.get("week_id") or "open-template").strip() or "open-template"
    expanded: list[dict[str, Any]] = []
    for position in range(1, 5):
        week = copy.deepcopy(base)
        goal = str(development.get(f"week_{position}") or week.get("week_goal") or "").strip()
        week["week_id"] = f"{base_id}-w{position}"
        week["week_index"] = position
        if goal:
            week["week_goal"] = goal
        progression = week.get("progression")
        if not isinstance(progression, Mapping):
            progression = {}

        progression["week_type"] = _OPEN_TEMPLATE_WEEK_TYPES[position - 1]
        if goal:
            progression["planned_change_from_previous"] = goal
        week["progression"] = progression
        expanded.append(week)
    return expanded


def _base_context(
    plan_row: Mapping[str, Any], *, current_training_day: date | None
) -> dict[str, Any]:
    mode = schedule_mode(plan_row)
    return {
        "schedule_mode": mode,
        "projection_status": "not_required" if mode == "event_countdown" else "unavailable",
        "anchor_date": None,
        "current_training_day": current_training_day.isoformat() if current_training_day else None,
        "block_number": None,
        "current_week_number": None,
    }


def project_open_structured_plan(
    plan_row: Mapping[str, Any],
    structured_plan: Mapping[str, Any] | None,
    *,
    current_training_day: date | str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(projected_plan, response_context)`` for an open plan.

    Dated camps and non-open legacy plans pass through unchanged.  A failed
    legacy reconciliation also passes through unchanged with
    ``projection_status=unavailable``.
    """

    source = dict(structured_plan or {})
    training_day = (
        current_training_day
        if isinstance(current_training_day, date)
        else _parse_date(current_training_day)
    )
    context = _base_context(plan_row, current_training_day=training_day)
    spec = open_plan_spec(plan_row)
    if spec is None:
        return source, context

    anchor = open_plan_anchor_date(plan_row)
    template = spec.get("weekly_template")
    template = template if isinstance(template, Mapping) else {}
    training_days = _ordered_weekdays(template.get("training_days"))
    coach_owned_days = set(_coach_owned_days(template))
    hard_sparring_days = set(_ordered_weekdays(template.get("hard_sparring_days")))
    weeks = source.get("weeks")
    if anchor is None or not training_days or not isinstance(weeks, list) or not weeks:
        return source, context

    if training_day is None or training_day < anchor:
        block_number = 1
        current_week_number = 1
    else:
        elapsed = (training_day - anchor).days
        block_number = elapsed // 28 + 1
        current_week_number = (elapsed % 28) // 7 + 1

    # Validate every week before applying any dates so projection is atomic.
    resolved_weeks: list[dict[str, Any]] = []
    for week in weeks:
        if not isinstance(week, Mapping):
            return source, context
        resolved_days = _resolve_template_days(week.get("days"), training_days)
        if resolved_days is None:
            return source, context
        for day, expected_weekday in zip(resolved_days, training_days, strict=True):
            is_coach_led = _is_coach_led_day(day)
            # A coach-led card may only land on a declared coach-owned day, and
            # a declared hard-sparring day must remain coach-led. Technical days
            # are allowed to carry executable app work as well, so they do not
            # have to be sessionless to reconcile safely.
            if is_coach_led and expected_weekday not in coach_owned_days:
                return source, context
            if expected_weekday in hard_sparring_days and not is_coach_led:
                return source, context
        normalized_week = copy.deepcopy(dict(week))
        normalized_week["days"] = resolved_days
        resolved_weeks.append(normalized_week)

    resolved_weeks = _expand_single_template_week(resolved_weeks, spec)
    if resolved_weeks is None:
        return source, context

    projected = copy.deepcopy(source)
    projected["weeks"] = resolved_weeks
    block_anchor = anchor + timedelta(days=(block_number - 1) * 28)
    for week_position, week in enumerate(projected["weeks"]):
        week_start = block_anchor + timedelta(days=week_position * 7)
        week["start_date"] = week_start.isoformat()
        week["end_date"] = (week_start + timedelta(days=6)).isoformat()
        week["countdown_start"] = None
        week["countdown_end"] = None
        for day, weekday in zip(week["days"], training_days, strict=True):
            projected_date = week_start + timedelta(days=WEEKDAYS.index(weekday))
            day["weekday"] = weekday
            day["date"] = projected_date.isoformat()
            day["countdown_label"] = ""

    context.update(
        {
            "projection_status": "projected",
            "anchor_date": anchor.isoformat(),
            "block_number": block_number,
            "current_week_number": current_week_number,
        }
    )
    return projected, context
