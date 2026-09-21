"""Deterministically guarantee coach-led / sparring days render as cards.

The athlete-facing structured plan is a *second* LLM conversion of the Stage 2
text. A declared contact day can also carry app work. The final plan owns that
choice; this reconciliation layer only guarantees the contact context is
visible and must not make a second training decision. Technical-contact days
therefore retain every app session the converter supplied. The web renderer
classifies a sessionless contact card purely from its free-text headline
(``classifySessionlessDay`` in ``web/lib/structured-plan.ts``). That single
fragile signal is the only thing
standing between a declared sparring day and a "Rest day." card: if the LLM drops
the day, leaves the headline blank, or phrases it without a coach/spar/technical
token, the coach-led card silently disappears.

The deterministic ``weekly_role_map`` already knows every sparring day for the
camp (it is what the Overview "Next session" card reads, and it is reliable). So
rather than trust the LLM to carry that truth through faithfully, this module
reconciles the converted plan against the deterministic schedule:

* a sessionless day that the schedule marks as contact work but whose headline
  would *not* classify as coach-led is stamped with a canonical coach-led
  headline,
* a declared contact day the converter dropped entirely is inserted into the
  matching week as a sessionless coach-led card, and
* a contact day that *also* carries app work keeps that work and has the
  contact surfaced on a dedicated ``today_card.coach_led_contact`` field so it
  renders as a context block above the session cards.

Technical-contact session headlines and blocks are never overwritten or
filtered: the coach-owned contact is added alongside, never in place of, the
app work. The function mutates the plan dict in place and returns a list of
human-readable change notes for admin/debug telemetry. It never raises: a
malformed brief or plan is a no-op.
"""
from __future__ import annotations

import re
from typing import Any

from fightcamp.weekly_schedule_view import extract_weekly_schedule
from fightcamp.sparring_dose_planner import hard_sparring_cutoff, contact_safety_reasons
from fightcamp.declared_combat_ownership import is_declared_light_combat_role
from fightcamp.combat_render_authority import resolve_declared_contact_load

# effective_load values from the deterministic schedule that mean coach-owned
# contact work the athlete must see as its own card.
_CONTACT_EFFECTIVE_LOADS = {"hard", "technical", "reduced"}

_WEEKDAY_ALIASES = {
    "mon": "Mon", "monday": "Mon",
    "tue": "Tue", "tues": "Tue", "tuesday": "Tue",
    "wed": "Wed", "wednesday": "Wed",
    "thu": "Thu", "thur": "Thu", "thurs": "Thu", "thursday": "Thu",
    "fri": "Fri", "friday": "Fri",
    "sat": "Sat", "saturday": "Sat",
    "sun": "Sun", "sunday": "Sun",
}
_WEEKDAY_ORDER = tuple(dict.fromkeys(_WEEKDAY_ALIASES.values()))

# Contact ceilings come from the same risk-aware owner as the planner.

# Canonical headlines chosen so the web classifier reliably tags the day:
#   "spar"      -> SPARRING_RE  -> kind "sparring"  (athlete-owned contact note shows)
#   "technical" -> TECHNICAL_RE -> kind "technical" (athlete-owned contact note shows)
# The labels are coach-neutral: a declared hard-sparring day is the athlete's own
# contact work (run with or without a coach), so nothing here asserts a coach.
_HEADLINE_BY_LOAD = {
    "hard": "Hard sparring",
    "reduced": "Hard sparring — reduced dose",
    "technical": "Technical-only combat",
}

# Converted hard-sparring cards become progressively lighter as fight day
# approaches. This is presentation-only: the sparring dose planner remains the
# authority for whether the declared hard day was converted to technical work.
_TECHNICAL_CARD_HEADLINES = {
    "fight_intensity": "Controlled fight-speed technical rounds",
    "rhythm": "Technical rhythm only",
    "touch": "Technical touch — pads / shadow",
    "activation": "Technical activation — no contact",
}


def _headline_for_load(load: str, d_day: int | None) -> str:
    """Return the athlete-facing contact-card headline for ``load`` and D-day."""
    if load != "technical" or d_day is None:
        return _HEADLINE_BY_LOAD.get(load, _HEADLINE_BY_LOAD["technical"])
    if 8 <= d_day <= 17:
        return _TECHNICAL_CARD_HEADLINES["fight_intensity"]
    if 5 <= d_day <= 7:
        return _TECHNICAL_CARD_HEADLINES["rhythm"]
    if 2 <= d_day <= 4:
        return _TECHNICAL_CARD_HEADLINES["touch"]
    if 0 <= d_day <= 1:
        return _TECHNICAL_CARD_HEADLINES["activation"]
    return _HEADLINE_BY_LOAD["technical"]


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
_ALLOWED_HARD_DAY_FILLER_RE = re.compile(
    r"\b("
    r"tactical\s+(?:watch|focus)|tactical\s+cue\s+card|cue\s+card|"
    r"neural\s+visuali[sz]ation|visuali[sz]ation|breathing\s+reset"
    r")\b",
    re.I,
)
_BLOCKED_CONTACT_FILLER_RE = re.compile(
    r"\b("
    r"strength|power\s+transfer|med[-\s]?ball|medicine\s+ball|plyo|"
    r"hard\s+(?:bag|pad)|bag\s+interval|pad\s+interval|"
    r"fight[-\s]?pace|conditioning|glycolytic|alactic|primer"
    r")\b",
    re.I,
)
_HIGH_RPE_RE = re.compile(r"\brpe\s*(?:[6-9]|10|[2-9]\s*[-–]\s*(?:[6-9]|10)|[6-9]\s*\+|10\s*\+)", re.I)
_SESSION_TEXT_EXCLUDED_KEYS = {
    "coaching_cues",
    "notes",
    "coach_notes",
    "description",
}


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


def _string_values(value: Any, *, parent_key: str = "") -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if parent_key in {"rpe", "rpe_cap", "intensity_rpe", "prescribed_intensity_rpe"}:
            return [f"rpe {value}"]
        return [str(value)]
    if isinstance(value, dict):
        values: list[str] = []
        for key, nested in value.items():
            key_text = str(key).strip().lower()
            if key_text in _SESSION_TEXT_EXCLUDED_KEYS:
                continue
            values.extend(_string_values(nested, parent_key=key_text))
        return values
    if isinstance(value, (list, tuple)):
        values: list[str] = []
        for nested in value:
            values.extend(_string_values(nested, parent_key=parent_key))
        return values
    return []


def _session_text(session: Any) -> str:
    return " ".join(_string_values(session))


def _is_allowed_nontechnical_contact_filler(session: Any) -> bool:
    """Keep the existing guard only for hard/reduced contact days.

    Technical-contact cards are a display context, not a filter: all app work
    supplied by the final plan remains visible alongside them. A locked Tactical
    Focus session is already deterministically classified as zero-load, so its
    instructional wording must never be reinterpreted as physical work here.
    """
    if isinstance(session, dict):
        title = str(session.get("title") or "").strip().casefold()
        session_id = str(session.get("session_id") or "").strip().casefold()
        if (
            title == "tactical focus"
            and session_id.startswith("locked-")
            and session_id.endswith("-tactical-watch")
        ):
            return True

    text = _session_text(session)
    if _BLOCKED_CONTACT_FILLER_RE.search(text) or _HIGH_RPE_RE.search(text):
        return False
    return bool(_ALLOWED_HARD_DAY_FILLER_RE.search(text))


def _ban_clamped_load(load: str, d_day: int | None, athlete_snapshot: dict[str, Any] | None = None) -> str:
    """Apply the shared ceiling without upgrading already reduced contact."""
    if contact_safety_reasons(athlete_snapshot or {}):
        return "none"
    if load in {"hard", "reduced"} and d_day is not None and 0 <= d_day <= hard_sparring_cutoff(athlete_snapshot or {}):
        return "technical"
    return load


def _role_contact_load(role: dict[str, Any], d_day: int | None, athlete_snapshot: dict[str, Any] | None = None) -> str:
    """Effective contact load for a declared ``hard_sparring_day`` role.

    Thin delegation to the shared resolver in
    :mod:`fightcamp.combat_render_authority`, which is the single owner of
    "declared hard day -> resolved contact status" for the structured plan, the
    Stage 2 locked render projection and deterministic source repair alike.
    """
    return resolve_declared_contact_load(
        role, d_day=d_day, athlete_snapshot=athlete_snapshot
    )


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

    __slots__ = (
        "date",
        "d_day",
        "weekday",
        "load",
        "headline",
        "day_type",
        "phase",
        "week_index",
    )

    def __init__(
        self,
        *,
        date: str | None,
        d_day: int | None,
        weekday: str | None,
        load: str,
        headline: str,
        day_type: str,
        phase: str,
        week_index: int,
    ):
        self.date = date
        self.d_day = d_day
        self.weekday = weekday
        self.load = load
        self.headline = headline
        self.day_type = day_type
        self.phase = phase
        # 1-based week number, matching the structured plan's ``week_index``. This
        # is the authoritative home week for the day and is what insertion targets
        # first, so a dropped day at a week boundary still lands in the right week.
        self.week_index = week_index


def _normalize_weekday(value: Any) -> str | None:
    return _WEEKDAY_ALIASES.get(str(value or "").strip().lower())


def _open_plan_contact_days(planning_brief: dict[str, Any]) -> list[_ContactDay]:
    """Declared open-plan combat locks, keyed by reusable week + weekday."""
    spec = planning_brief.get("open_plan_spec")
    if not isinstance(spec, dict) or spec.get("plan_type") != "open_ongoing_system":
        return []
    template = spec.get("weekly_template")
    if not isinstance(template, dict):
        return []
    coach_owned = template.get("coach_owned_days")
    coach_owned = coach_owned if isinstance(coach_owned, dict) else {}

    def weekdays(values: Any) -> set[str]:
        if not isinstance(values, (list, tuple, set)):
            return set()
        return {day for value in values if (day := _normalize_weekday(value))}

    training = weekdays(template.get("training_days"))
    hard = weekdays(template.get("hard_sparring_days")) & training
    technical = weekdays(
        template.get("support_work_days")
        or coach_owned.get("support_work_days")
        or coach_owned.get("technical_skill_days")
    ) & training
    technical -= hard
    if not hard and not technical:
        return []

    development = spec.get("development_block")
    week_count = max(1, len(development) if isinstance(development, dict) else 4)
    contacts: list[_ContactDay] = []
    for week_index in range(1, week_count + 1):
        for weekday in _WEEKDAY_ORDER:
            load = "hard" if weekday in hard else "technical" if weekday in technical else None
            if load is None:
                continue
            contacts.append(
                _ContactDay(
                    date=None,
                    d_day=None,
                    weekday=weekday,
                    load=load,
                    headline=_HEADLINE_BY_LOAD[load],
                    day_type=_DAY_TYPE_BY_LOAD[load],
                    phase="GPP",
                    week_index=week_index,
                )
            )
    return contacts


def _deterministic_contact_days(planning_brief: dict[str, Any]) -> list[_ContactDay]:
    """Every coach-owned contact day across the camp, from the role map schedule."""
    open_contacts = _open_plan_contact_days(planning_brief)
    if open_contacts:
        return open_contacts
    role_map = planning_brief.get("weekly_role_map")
    if not isinstance(role_map, dict):
        return []
    weeks = role_map.get("weeks")
    if not isinstance(weeks, list):
        return []

    athlete_snapshot = planning_brief.get("athlete_model") or planning_brief.get("athlete_snapshot") or {}
    fight_date = _resolve_fight_date(planning_brief)
    contact_days: list[_ContactDay] = []
    seen_dates: set[str] = set()
    seen_ddays: set[int] = set()

    def append_contact(contact: _ContactDay) -> None:
        if contact.date and contact.date in seen_dates:
            return
        if contact.d_day is not None and contact.d_day in seen_ddays:
            return
        if contact.date:
            seen_dates.add(contact.date)
        if contact.d_day is not None:
            seen_ddays.add(contact.d_day)
        contact_days.append(contact)

    for week_index in range(len(weeks)):
        week = weeks[week_index]
        if not isinstance(week, dict):
            continue

        schedule = extract_weekly_schedule(planning_brief, week_index=week_index, fight_date=fight_date)
        resolved_loads = {
            day["d_day"]: day["effective_load"]
            for day in (schedule or {}).get("days", [])
            if day.get("status") and isinstance(day.get("d_day"), int)
        }
        load_rank = {"none": 0, "technical": 1, "reduced": 2, "hard": 3}
        role_phase = str(week.get("phase") or "").strip().upper()
        session_roles = week.get("session_roles")
        role_entries = session_roles if isinstance(session_roles, list) else []
        for role in role_entries:
            if not isinstance(role, dict):
                continue
            role_key = str(role.get("role_key") or "").strip()
            is_declared_light_combat = is_declared_light_combat_role(role)
            if role_key != "hard_sparring_day" and not is_declared_light_combat:
                continue

            raw_offset = role.get("countdown_offset")
            d_day = raw_offset if isinstance(raw_offset, int) and raw_offset >= 0 else None
            if d_day is None:
                d_day = _parse_dday(
                    role.get("scheduled_countdown_label") or role.get("countdown_label")
                )
            if d_day is None or d_day == 0:
                continue

            if is_declared_light_combat:
                # A declared light-combat / technical day is coach-owned calendar
                # context the athlete stated, exactly like a declared hard-sparring
                # day. It carries technical contact load and is never clamped down
                # by the hard-sparring bans: the deterministic owners express any
                # suppression by leaving the role out of session_roles entirely.
                load = "technical"
            else:
                load = _ban_clamped_load(_role_contact_load(role, d_day, athlete_snapshot), d_day, athlete_snapshot)
                resolved_load = resolved_loads.get(d_day)
                if resolved_load in load_rank and load_rank[resolved_load] < load_rank[load]:
                    load = resolved_load
            if load == "none":
                continue
            append_contact(
                _ContactDay(
                    date=str(role.get("calendar_date") or role.get("date") or "").strip() or None,
                    d_day=d_day,
                    weekday=None,
                    load=load,
                    headline=_headline_for_load(load, d_day),
                    day_type=_DAY_TYPE_BY_LOAD[load],
                    phase=role_phase,
                    week_index=week_index + 1,
                )
            )

        if not isinstance(schedule, dict):
            continue

        phase = str(schedule.get("phase") or "").strip().upper()
        days = schedule.get("days")
        if not isinstance(days, list):
            continue

        for day in days:
            if not isinstance(day, dict):
                continue

            load = str(day.get("effective_load") or "").strip().lower()
            sparring_class = str(day.get("sparring_day_class") or "").strip().lower()

            if load not in _CONTACT_EFFECTIVE_LOADS or sparring_class in {"", "none"}:
                continue

            cal = str(day.get("calendar_date") or "").strip() or None
            raw_dday = day.get("d_day")
            d_day = raw_dday if isinstance(raw_dday, int) and raw_dday >= 0 else None

            if d_day == 0:
                continue

            if cal is None and d_day is None:
                continue

            load = _ban_clamped_load(load, d_day, athlete_snapshot)
            if load == "none":
                continue
            append_contact(
                _ContactDay(
                    date=cal,
                    d_day=d_day,
                    weekday=None,
                    load=load,
                    headline=_headline_for_load(load, d_day),
                    day_type=_DAY_TYPE_BY_LOAD.get(load, "moderate"),
                    phase=phase,
                    week_index=week_index + 1,
                )
            )

    return contact_days


def _valid_phase_label(phase: str, fallback: str) -> str:
    allowed = {"GPP", "SPP", "TAPER", "FIGHT_WEEK", "REINTEGRATION"}
    return phase if phase in allowed else fallback


_REST_DAY_TYPES = {"rest", "off", "none", "travel"}


def _apply_contact_day_type(day: dict[str, Any], contact: _ContactDay) -> bool:
    """Lift a rest ``day_type`` to the contact's own load when stamping a day.

    An inserted contact day (``_build_coach_led_day``) carries the day_type its
    load implies, but a day the converter already emitted as rest keeps that
    rest day_type when we stamp the contact headline onto it — so a declared
    hard-sparring day reads "Hard sparring" while every day_type consumer still
    sees rest. That understated the athlete's hardest day as reduced load on
    Today/Overview and dropped it from week-progress and streak counts.

    Only a declared *hard* contact is lifted, and only off a rest-ish day_type.
    Reduced and technical contact genuinely belong on an easy day — light
    technical touches on a recovery day are a normal prescription, and calling
    that day "moderate" would inflate it — so those keep the day_type the
    converter chose.
    """
    if contact.load != "hard":
        return False
    if str(day.get("day_type") or "").strip().lower() not in _REST_DAY_TYPES:
        return False
    day["day_type"] = _DAY_TYPE_BY_LOAD["hard"]
    return True


def _contact_identity(contact: _ContactDay) -> str:
    if contact.date:
        return contact.date
    if contact.weekday:
        return contact.weekday
    return f"D-{contact.d_day}"


def _build_coach_led_day(contact: _ContactDay, *, phase_fallback: str) -> dict[str, Any]:
    """A schema-valid sessionless coach-led day for an absent contact day."""
    countdown = f"D-{contact.d_day}" if contact.d_day is not None else ""
    day = {
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
    if contact.weekday:
        day["weekday"] = contact.weekday
    return day


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

    Fallback for when ``week_index`` matching fails (e.g. the converter misnumbered
    a week). Uses the week's *full declared span* — date range and countdown
    (``countdown_start``/``countdown_end``) bounds — before falling back to the
    span of the days actually present. Anchoring on the declared span (not just the
    remaining days) is what keeps a dropped day at a week boundary in scope.
    """
    start = str(week.get("start_date") or "").strip()
    end = str(week.get("end_date") or "").strip()
    if contact.date and start and end and start <= contact.date <= end:
        return True
    if contact.d_day is not None:
        cd_start = _parse_dday(week.get("countdown_start"))
        cd_end = _parse_dday(week.get("countdown_end"))
        if cd_start is not None and cd_end is not None:
            lo, hi = min(cd_start, cd_end), max(cd_start, cd_end)
            if lo <= contact.d_day <= hi:
                return True
        # Last resort: the span of the days the converter actually emitted.
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
    new_weekday = _normalize_weekday(new_day.get("weekday"))
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
        elif new_weekday:
            existing_weekday = _normalize_weekday(day.get("weekday"))
            if (
                existing_weekday
                and _WEEKDAY_ORDER.index(existing_weekday) > _WEEKDAY_ORDER.index(new_weekday)
            ):
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
    contact_by_date = {c.date: c for c in contact_days if c.date}
    contact_by_dday = {c.d_day: c for c in contact_days if c.d_day is not None}
    contact_by_open_day = {
        (c.week_index, c.weekday): c for c in contact_days if c.weekday
    }
    present_open_days: set[tuple[int, str]] = set()

    # Pass 1 — record every day the converter produced and stamp the sessionless
    # contact days whose headline would not classify as coach-led.
    for week_position, week in enumerate(weeks, start=1):
        if not isinstance(week, dict):
            continue
        days = week.get("days")
        if not isinstance(days, list):
            continue
        week_index = week.get("week_index")
        if not isinstance(week_index, int):
            week_index = week_position
        for day in days:
            if not isinstance(day, dict):
                continue
            date = str(day.get("date") or "").strip()
            dday = _parse_dday(day.get("countdown_label"))
            if date:
                present_dates.add(date)
            if dday is not None:
                present_ddays.add(dday)
            weekday = _normalize_weekday(day.get("weekday"))
            if weekday:
                present_open_days.add((week_index, weekday))

            contact = None
            if date and date in contact_by_date:
                contact = contact_by_date[date]
            elif dday is not None and dday in contact_by_dday:
                contact = contact_by_dday[dday]
            elif weekday:
                contact = contact_by_open_day.get((week_index, weekday))
            if contact is None:
                continue
            identity = _contact_identity(contact)
            card = day.get("today_card")
            if not isinstance(card, dict):
                card = {
                    "readiness_status": "train_as_planned",
                    "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
                }
                day["today_card"] = card
            current = str(card.get("headline") or "").strip()
            # A day the converter gave real app work renders as session cards, but
            # the coach-owned contact (a declared / downgraded sparring day) must
            # still show on that day. Technical-contact context does not decide
            # whether app work is allowed; it preserves the final plan's sessions.
            # Rather than overwrite the app headline (which the
            # session card falls back to for its own title), surface the contact on a
            # dedicated field; the renderer shows it as a context block above the
            # session cards. The contact block is driven solely by coach_led_contact
            # (never the day headline, which session.title can shadow), so it must be
            # populated whenever it is absent — even if the headline already reads
            # coach-led — or the coexisting contact stays hidden.
            if day.get("sessions"):
                sessions = day.get("sessions")
                if contact.load != "technical" and isinstance(sessions, list):
                    compatible_sessions = [
                        session
                        for session in sessions
                        if _is_allowed_nontechnical_contact_filler(session)
                    ]
                    if len(compatible_sessions) != len(sessions):
                        day["sessions"] = compatible_sessions
                        notes.append(
                            f"removed incompatible same-day app work from "
                            f"{identity} ({contact.headline!r})"
                        )
                if not day.get("sessions"):
                    card["headline"] = contact.headline
                    if _apply_contact_day_type(day, contact):
                        notes.append(
                            f"lifted rest day_type to {day['day_type']!r} on "
                            f"{identity} ({contact.headline!r})"
                        )
                    notes.append(
                        f"stamped contact headline on {identity} "
                        f"({contact.headline!r})"
                    )
                    continue
                if _apply_contact_day_type(day, contact):
                    notes.append(
                        f"lifted rest day_type to {day['day_type']!r} on "
                        f"{identity} ({contact.headline!r})"
                    )
                if str(card.get("coach_led_contact") or "").strip():
                    continue
                card["coach_led_contact"] = contact.headline
                notes.append(
                    f"surfaced coach-led contact alongside sessions on "
                    f"{identity} ({contact.headline!r})"
                )
                continue
            if current and _already_coach_led(current):
                # The headline already classifies, but the day_type behind it can
                # still be the converter's rest stamp — fix that either way.
                if _apply_contact_day_type(day, contact):
                    notes.append(
                        f"lifted rest day_type to {day['day_type']!r} on "
                        f"{identity} ({current!r})"
                    )
                continue
            card["headline"] = contact.headline
            if _apply_contact_day_type(day, contact):
                notes.append(
                    f"lifted rest day_type to {day['day_type']!r} on "
                    f"{identity} ({contact.headline!r})"
                )
            notes.append(
                f"stamped contact headline on {identity} "
                f"({contact.headline!r})"
            )

    # Pass 2 — insert declared contact days the converter dropped entirely.
    default_phase = _valid_phase_label(
        str((weeks[0] or {}).get("phase_label") or "").strip().upper()
        if isinstance(weeks[0], dict)
        else "",
        "SPP",
    )
    for contact in contact_days:
        # Either identity matching the day already in the plan means "present" —
        # the converter commonly keys a day by D-day countdown_label only (no
        # date), so a contact day that carries a date must still defer to a D-day
        # match or it would be inserted as a duplicate of the existing card.
        if contact.date and contact.date in present_dates:
            continue
        if contact.d_day is not None and contact.d_day in present_ddays:
            continue
        if contact.weekday and (contact.week_index, contact.weekday) in present_open_days:
            continue
        # Primary: the authoritative home week from the role map (week_index). This
        # is exact and immune to the boundary case where a dropped day sits outside
        # the span of the days the converter happened to keep. Fall back to span
        # coverage only when no week carries the matching index (e.g. a misnumbered
        # converter week).
        target_week = next(
            (
                week
                for week in weeks
                if isinstance(week, dict) and week.get("week_index") == contact.week_index
            ),
            None,
        )
        if target_week is None:
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
        if contact.weekday:
            present_open_days.add((contact.week_index, contact.weekday))
        notes.append(
            f"inserted contact card for "
            f"{_contact_identity(contact)} ({contact.headline!r})"
        )

    return notes
