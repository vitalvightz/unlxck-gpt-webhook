"""Deterministically guarantee coach-led / sparring days render as cards.

The athlete-facing structured plan is a *second* LLM conversion of the Stage 2
text. A declared hard-sparring (or technical / reduced) day legitimately carries
no app S&C work — the contact load is coach-owned — so the converter is supposed
to emit it as a day with empty ``sessions`` and a headline naming it (e.g.
"Coach-led sparring"). The web renderer then classifies the card *purely* from
that free-text headline (``classifySessionlessDay`` in
``web/lib/structured-plan.ts``). That single fragile signal is the only thing
standing between a declared sparring day and a "Rest day." card: if the LLM drops
the day, leaves the headline blank, or phrases it without a coach/spar/technical
token, the coach-led card silently disappears.

The deterministic ``weekly_role_map`` already knows every sparring day for the
camp (it is what the Overview "Next session" card reads, and it is reliable). So
rather than trust the LLM to carry that truth through faithfully, this module
reconciles the converted plan against the deterministic schedule:

* a sessionless day that the schedule marks as contact work but whose headline
  would *not* classify as coach-led is stamped with a canonical coach-led
  headline, and
* a declared contact day the converter dropped entirely is inserted into the
  matching week as a sessionless coach-led card.

Real app sessions are never overwritten — a day the converter gave actual S&C
work is left alone (it already renders as a session card). The function mutates
the plan dict in place and returns a list of human-readable change notes for
admin/debug telemetry. It never raises: a malformed brief or plan is a no-op.
"""
from __future__ import annotations

import re
from typing import Any

from fightcamp.weekly_schedule_view import extract_weekly_schedule

# effective_load values from the deterministic schedule that mean coach-owned
# contact work the athlete must see as its own card.
_CONTACT_EFFECTIVE_LOADS = {"hard", "technical", "reduced"}

# Canonical headlines chosen so the web classifier reliably tags the day:
#   "spar"      -> SPARRING_RE  -> kind "sparring"  (coachLed = true)
#   "technical" -> TECHNICAL_RE -> kind "technical" (coachLed = true)
# Each also reads as coach-owned so the "train with your coach" note shows.
_HEADLINE_BY_LOAD = {
    "hard": "Coach-led sparring",
    "reduced": "Coach-led sparring — reduced dose",
    "technical": "Coach-led boxing — technical only",
}
# day_type carries no sparring value (high/moderate/low/...), so pick the closest
# intensity bucket purely for the day's intensity tag. It does NOT drive the
# coach-led classification — the headline does.
_DAY_TYPE_BY_LOAD = {"hard": "high", "reduced": "low", "technical": "moderate"}

# Mirror the web classifier's regexes (web/lib/structured-plan.ts) so we never
# restamp a day the converter already labelled coach-led / sparring / technical.
_TECHNICAL_RE = re.compile(
    r"\b(technical|skill|drill|pad\s?work|pads|mitts?|footwork|shadow)", re.I
)
_SPARRING_RE = re.compile(r"\bspar(?:r(?:ing|ed)|s)?\b", re.I)
_COACH_LED_RE = re.compile(r"\bcoach", re.I)

_DDAY_RE = re.compile(r"D-\s*(\d+)", re.I)


def _already_coach_led(headline: str) -> bool:
    """True when a headline would already classify as coach-led/sparring/technical."""
    return bool(
        _TECHNICAL_RE.search(headline)
        or _SPARRING_RE.search(headline)
        or _COACH_LED_RE.search(headline)
    )


def _parse_dday(label: Any) -> int | None:
    match = _DDAY_RE.search(str(label or ""))
    return int(match.group(1)) if match else None


def _resolve_fight_date(planning_brief: dict[str, Any]) -> Any:
    """Best-effort fight date for the calendar fallback in extract_weekly_schedule."""
    for source in (
        planning_brief.get("fight_date"),
        (planning_brief.get("athlete_model") or {}).get("fight_date")
        if isinstance(planning_brief.get("athlete_model"), dict)
        else None,
        (planning_brief.get("athlete_snapshot") or {}).get("fight_date")
        if isinstance(planning_brief.get("athlete_snapshot"), dict)
        else None,
    ):
        if source:
            return source
    return None


class _ContactDay:
    """A deterministic coach-led/sparring day to guarantee in the structured plan."""

    __slots__ = ("date", "d_day", "headline", "day_type", "phase")

    def __init__(self, *, date: str | None, d_day: int | None, headline: str, day_type: str, phase: str):
        self.date = date
        self.d_day = d_day
        self.headline = headline
        self.day_type = day_type
        self.phase = phase


def _deterministic_contact_days(planning_brief: dict[str, Any]) -> list[_ContactDay]:
    """Every coach-owned contact day across the camp, from the role map schedule."""
    role_map = planning_brief.get("weekly_role_map")
    if not isinstance(role_map, dict):
        return []
    weeks = role_map.get("weeks")
    if not isinstance(weeks, list):
        return []

    fight_date = _resolve_fight_date(planning_brief)
    contact_days: list[_ContactDay] = []
    seen: set[tuple[str | None, int | None]] = set()
    for week_index in range(len(weeks)):
        schedule = extract_weekly_schedule(
            planning_brief, week_index=week_index, fight_date=fight_date
        )
        if not isinstance(schedule, dict):
            continue
        phase = str(schedule.get("phase") or "").strip().upper()
        for day in schedule.get("days") or []:
            if not isinstance(day, dict):
                continue
            load = str(day.get("effective_load") or "").strip().lower()
            sparring_class = str(day.get("sparring_day_class") or "").strip().lower()
            if load not in _CONTACT_EFFECTIVE_LOADS or sparring_class in {"", "none"}:
                continue
            cal = str(day.get("calendar_date") or "").strip() or None
            raw_dday = day.get("d_day")
            d_day = raw_dday if isinstance(raw_dday, int) and raw_dday >= 0 else None
            if cal is None and d_day is None:
                continue
            key = (cal, d_day)
            if key in seen:
                continue
            seen.add(key)
            contact_days.append(
                _ContactDay(
                    date=cal,
                    d_day=d_day,
                    headline=_HEADLINE_BY_LOAD.get(load, _HEADLINE_BY_LOAD["technical"]),
                    day_type=_DAY_TYPE_BY_LOAD.get(load, "moderate"),
                    phase=phase,
                )
            )
    return contact_days


def _valid_phase_label(phase: str, fallback: str) -> str:
    allowed = {"GPP", "SPP", "TAPER", "FIGHT_WEEK", "REINTEGRATION"}
    return phase if phase in allowed else fallback


def _build_coach_led_day(contact: _ContactDay, *, phase_fallback: str) -> dict[str, Any]:
    """A schema-valid sessionless coach-led day for an absent contact day."""
    countdown = f"D-{contact.d_day}" if contact.d_day is not None else ""
    return {
        "date": contact.date or "",
        "day_type": contact.day_type,
        "countdown_label": countdown,
        "phase_label": _valid_phase_label(contact.phase, phase_fallback),
        "today_card": {
            "headline": contact.headline,
            "readiness_status": "train_as_planned",
            "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
        },
        "sessions": [],
    }


def _week_day_keys(week: dict[str, Any]) -> tuple[set[str], set[int]]:
    dates: set[str] = set()
    ddays: set[int] = set()
    for day in week.get("days") or []:
        if not isinstance(day, dict):
            continue
        date = str(day.get("date") or "").strip()
        if date:
            dates.add(date)
        dday = _parse_dday(day.get("countdown_label"))
        if dday is not None:
            ddays.add(dday)
    return dates, ddays


def _week_covers(week: dict[str, Any], contact: _ContactDay) -> bool:
    """True when this structured week is the home for a contact day.

    Prefers the week's declared date span, then its countdown (D-day) span derived
    from the days it already carries — whichever can be resolved.
    """
    start = str(week.get("start_date") or "").strip()
    end = str(week.get("end_date") or "").strip()
    if contact.date and start and end:
        if start <= contact.date <= end:
            return True
        # A definite date that sits outside this week's span rules the week out.
        return False
    if contact.d_day is not None:
        _, ddays = _week_day_keys(week)
        if ddays and min(ddays) <= contact.d_day <= max(ddays):
            return True
    return False


def _insert_day_in_order(week: dict[str, Any], new_day: dict[str, Any]) -> None:
    """Insert keeping chronological order (descending D-day / ascending date)."""
    days = week.get("days")
    if not isinstance(days, list):
        week["days"] = [new_day]
        return
    new_dday = _parse_dday(new_day.get("countdown_label"))
    new_date = str(new_day.get("date") or "").strip()
    for index, day in enumerate(days):
        if not isinstance(day, dict):
            continue
        if new_dday is not None:
            existing = _parse_dday(day.get("countdown_label"))
            if existing is not None and existing < new_dday:
                days.insert(index, new_day)
                return
        elif new_date:
            existing_date = str(day.get("date") or "").strip()
            if existing_date and existing_date > new_date:
                days.insert(index, new_day)
                return
    days.append(new_day)


def reconcile_coach_led_sparring_days(
    structured_plan: Any, planning_brief: Any
) -> list[str]:
    """Guarantee declared coach-led/sparring days render as cards. Mutates in place.

    Returns a list of change notes (empty when nothing needed reconciling). Never
    raises — an unusable plan or brief is a silent no-op so the structured card
    pipeline degrades to whatever the converter produced.
    """
    try:
        return _reconcile(structured_plan, planning_brief)
    except Exception:  # never block the card pipeline on reconciliation
        return []


def _reconcile(structured_plan: Any, planning_brief: Any) -> list[str]:
    if not isinstance(structured_plan, dict) or not isinstance(planning_brief, dict):
        return []
    weeks = structured_plan.get("weeks")
    if not isinstance(weeks, list) or not weeks:
        return []
    contact_days = _deterministic_contact_days(planning_brief)
    if not contact_days:
        return []

    notes: list[str] = []
    present_dates: set[str] = set()
    present_ddays: set[int] = set()
    headline_by_date = {c.date: c.headline for c in contact_days if c.date}
    headline_by_dday = {c.d_day: c.headline for c in contact_days if c.d_day is not None}

    # Pass 1 — record every day the converter produced and stamp the sessionless
    # contact days whose headline would not classify as coach-led.
    for week in weeks:
        if not isinstance(week, dict):
            continue
        for day in week.get("days") or []:
            if not isinstance(day, dict):
                continue
            date = str(day.get("date") or "").strip()
            dday = _parse_dday(day.get("countdown_label"))
            if date:
                present_dates.add(date)
            if dday is not None:
                present_ddays.add(dday)

            headline_target = None
            if date and date in headline_by_date:
                headline_target = headline_by_date[date]
            elif dday is not None and dday in headline_by_dday:
                headline_target = headline_by_dday[dday]
            if headline_target is None:
                continue
            # A day the converter gave real app work already renders as a session
            # card — never hide that behind a coach-led note.
            if day.get("sessions"):
                continue
            card = day.get("today_card")
            if not isinstance(card, dict):
                card = {
                    "readiness_status": "train_as_planned",
                    "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
                }
                day["today_card"] = card
            current = str(card.get("headline") or "").strip()
            if current and _already_coach_led(current):
                continue
            card["headline"] = headline_target
            notes.append(
                f"stamped coach-led headline on {date or f'D-{dday}'} "
                f"({headline_target!r})"
            )

    # Pass 2 — insert declared contact days the converter dropped entirely.
    default_phase = _valid_phase_label(
        str((weeks[0] or {}).get("phase_label") or "").strip().upper()
        if isinstance(weeks[0], dict)
        else "",
        "SPP",
    )
    for contact in contact_days:
        if contact.date and contact.date in present_dates:
            continue
        if contact.date is None and contact.d_day is not None and contact.d_day in present_ddays:
            continue
        target_week = next(
            (week for week in weeks if isinstance(week, dict) and _week_covers(week, contact)),
            None,
        )
        if target_week is None:
            continue
        new_day = _build_coach_led_day(contact, phase_fallback=default_phase)
        _insert_day_in_order(target_week, new_day)
        if contact.date:
            present_dates.add(contact.date)
        if contact.d_day is not None:
            present_ddays.add(contact.d_day)
        notes.append(
            f"inserted coach-led card for "
            f"{contact.date or f'D-{contact.d_day}'} ({contact.headline!r})"
        )

    return notes
