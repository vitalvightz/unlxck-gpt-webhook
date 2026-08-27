"""Guarantee a dated fight camp's structured calendar is continuous and gap-free.

The athlete-facing ``structured_plan`` is a *second* LLM conversion of the Stage 2
``final_plan_text``. That text is a **sparse** document: it lists the days that
carry a prescribed session and silently omits uneventful rest / no-session days.
The converter mirrors that sparseness, so ``structured_plan.weeks[*].days`` ends
up containing only session-bearing days, and the faithfulness gate
(:mod:`api.structured_plan_faithfulness`) makes this *impossible for the converter
to fix on its own* — any D-day it invents that is not in the source text is
rejected as unverifiable. The missing days can therefore only be restored
deterministically, server-side, after the gate has run.

Why the sparse calendar is a bug, not a display choice
------------------------------------------------------
The web renderer derives a week's boundaries, its date/countdown range, its
app/coach session counts, its phase context and current-day resolution from the
days that survive in ``weeks[*].days`` (``web/lib/structured-plan.ts`` and
``web/lib/camp-map.ts``). When the days are sparse a week collapses to a single
day ("D-21 -> D-21"), a converter mega-week is cut by the frontend's Mon-Sun
``splitWeekByCalendarWeek`` into single-day tabs that all inherit one phase (every
tab reads "Taper"), counts / countdown ranges are computed from whatever survived,
and D-days disappear instead of existing as no-session calendar days.

A **calendar day** and a **session** are different entities. A no-session day
must mean "this D-day exists and has no prescribed app session", never "this
D-day does not exist".

The authoritative contract this module enforces
-----------------------------------------------
For a dated camp beginning on D-N there is exactly one calendar-day identity for
every integer countdown D-N, D-(N-1), … D-0, and for each day the ``date`` <->
countdown ``label`` <-> ``weekday`` triple is deterministic (``fight_date`` minus
the countdown), independent of session sparsity. The days are grouped into the
**Mon-Sun calendar weeks** the web view actually renders (``splitWeekByCalendarWeek``
refuses to re-split a block spanning seven days or fewer, so a planner training
week would otherwise survive as one un-split card), and each week's phase and
boundaries come from that authoritative calendar rather than from the surviving
sessions.

    fight date + days-until-fight -> continuous calendar spine (D-N … D-0)
                                  -> authoritative per-day phase (planner role map)
                                  -> overlay the converter's session content
                                  -> group into Mon-Sun weeks, phase = week's own
                                     authoritative days, boundaries recomputed.

The rebuild is:

* **content-preserving** — every converter session is kept (a day whose label
  went blank is placed by its date; two converter rows on one calendar day are
  merged into a single day identity; a rebuild that would carry fewer sessions
  than the converter is discarded);
* **structurally verified** — it is a no-op only when the plan already matches the
  authoritative calendar (continuity *and* Mon-Sun ownership *and* per-day phase
  *and* deterministic date/weekday identity), so continuity alone is not enough to
  leave a mega-week or a mislabelled phase in place;
* **scoped to dated camps** — open / renewable plans and briefs without a usable
  role-map spine are left alone;
* **never raising** — a malformed plan or brief is a silent no-op so the
  structured-card pipeline degrades to whatever the converter produced.

It MUST run *after* the faithfulness gate (it introduces D-days the source text
never spelled out) and after the coach-led reconcile (whose contact days it
preserves), mirroring
:func:`api.structured_plan_sparring_reconcile.reconcile_coach_led_sparring_days`.
"""
from __future__ import annotations

import copy
import re
from datetime import date, timedelta
from typing import Any

from fightcamp.fight_date_utils import parse_fight_date

_PHASE_VALUES = {"GPP", "SPP", "TAPER", "FIGHT_WEEK", "REINTEGRATION"}
# Countdown ordering toward (and past) the fight, used to break a phase tie inside
# a Mon-Sun week that straddles a planner phase boundary: the sharper, closer-to-
# fight phase wins so a transition week never reads as the phase already left.
_PHASE_RANK = {"GPP": 0, "SPP": 1, "TAPER": 2, "FIGHT_WEEK": 3, "REINTEGRATION": 4}
_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DDAY_RE = re.compile(r"D-\s*(\d+)", re.I)
# How far past the planner spine an extent signal may reach. A lead-in shorter
# than the first planner week is legitimate; anything further is treated as noise
# so a garbled date/label can never balloon the calendar.
_EXTENT_SLACK_DAYS = 14


def _parse_dday(label: Any) -> int | None:
    """Countdown distance from a label like ``D-15`` (-> ``15``), else ``None``."""
    match = _DDAY_RE.search(str(label or ""))
    return int(match.group(1)) if match else None


def _effective_dday(day: dict[str, Any], fight_date: date) -> int | None:
    """A day's countdown distance from its label, falling back to its date.

    The athlete-facing ``countdown_label`` is preferred (it is what the faithfulness
    gate verified). When it is blank/garbled but the day carries a real ISO date,
    the distance is recovered from the fight date so a dated day is never lost just
    because its label went missing. Post-fight dates yield ``None`` (a pre-fight
    countdown never runs past D-0).
    """
    parsed = _parse_dday(day.get("countdown_label"))
    if parsed is not None:
        return parsed
    parsed_date = parse_fight_date(str(day.get("date") or "").strip())
    if parsed_date is None:
        return None
    delta = (fight_date - parsed_date).days
    return delta if delta >= 0 else None


def _resolve_fight_date(planning_brief: dict[str, Any]) -> Any:
    """Best-effort fight date from the brief (mirrors the sparring reconcile)."""
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


def _resolve_days_until_fight(planning_brief: dict[str, Any]) -> int | None:
    """The camp-start countdown (D-N), so an empty first day never disappears.

    The planner role map anchors its final week on D-0 and sums week spans, which
    can leave the camp-start day one countdown short of where the plan actually
    begins (a Friday-made plan whose first day is D-21 while the spine computes
    D-20). ``days_until_fight`` is the athlete's real distance to the fight, so it
    is the authoritative camp start regardless of whether that day carries a
    session.
    """
    for source in (
        planning_brief.get("days_until_fight"),
        (planning_brief.get("athlete_snapshot") or {}).get("days_until_fight")
        if isinstance(planning_brief.get("athlete_snapshot"), dict)
        else None,
        (planning_brief.get("athlete_model") or {}).get("days_until_fight")
        if isinstance(planning_brief.get("athlete_model"), dict)
        else None,
    ):
        try:
            value = int(source)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _valid_phase(value: Any, fallback: str = "") -> str:
    phase = str(value or "").strip().upper()
    return phase if phase in _PHASE_VALUES else fallback


def _empty_mindset() -> dict[str, str]:
    return {"intent": "", "focus_cue": "", "reset_cue": ""}


def _monday_iso(iso_date: str) -> str | None:
    """ISO date of the Monday that opens ``iso_date``'s calendar week, or ``None``.

    This is the exact Mon-Sun bucketing ``web/lib/structured-plan.ts``
    ``splitWeekByCalendarWeek`` uses, so the backend weeks and the rendered weeks
    agree instead of the frontend re-cutting (or refusing to re-cut) them.
    """
    parsed = parse_fight_date(iso_date)
    if parsed is None:
        return None
    return (parsed - timedelta(days=parsed.weekday())).isoformat()


def _resolve_week_span(week: dict[str, Any]) -> tuple[int, int] | None:
    """A week's ``(start_d, end_d)`` (furthest -> closest) from either contract.

    Normal-camp weeks ship a list ``countdown_range`` ``[start, end]``; late-fight
    weeks ship a ``countdown_span`` dict ``{"start_day", "end_day"}``. Both name
    the same countdown window; recognising both keeps the spine the single source
    of truth whichever planner built the week.
    """
    countdown_range = week.get("countdown_range")
    if isinstance(countdown_range, list) and len(countdown_range) == 2:
        try:
            return int(countdown_range[0]), int(countdown_range[1])
        except (TypeError, ValueError):
            pass
    countdown_span = week.get("countdown_span")
    if isinstance(countdown_span, dict):
        try:
            return int(countdown_span.get("start_day")), int(countdown_span.get("end_day"))
        except (TypeError, ValueError):
            pass
    return None


def _authoritative_phase_map(
    role_map: dict[str, Any],
) -> tuple[dict[int, str], int | None, int | None]:
    """Map each countdown D-day the planner covers to its phase.

    Reads the normal-camp ``calendar_days`` block (each entry carries its own
    D-day and after-fight flag) and the late-fight ``countdown_span`` /
    ``countdown_range`` window. A D-day claimed by two weeks stays with the
    furthest-out (first) week so a boundary day has one owner. Returns the map plus
    the covered ``(max_d_day, min_d_day)``.
    """
    weeks = role_map.get("weeks")
    if not isinstance(weeks, list):
        return {}, None, None
    phase_by_dday: dict[int, str] = {}
    for week in weeks:
        if not isinstance(week, dict):
            continue
        phase = _valid_phase(week.get("phase"))
        ddays: list[int] = []
        calendar_days = week.get("calendar_days")
        if isinstance(calendar_days, list) and calendar_days:
            for entry in calendar_days:
                if not isinstance(entry, dict) or entry.get("is_after_fight_day"):
                    continue
                try:
                    d_day = int(entry.get("d_day"))
                except (TypeError, ValueError):
                    continue
                if d_day >= 0:
                    ddays.append(d_day)
        else:
            span = _resolve_week_span(week)
            if span is not None:
                start_d, end_d = span
                if start_d < end_d:
                    start_d, end_d = end_d, start_d
                ddays.extend(d for d in range(start_d, end_d - 1, -1) if d >= 0)
        for d_day in ddays:
            phase_by_dday.setdefault(d_day, phase)
    if not phase_by_dday:
        return {}, None, None
    return phase_by_dday, max(phase_by_dday), min(phase_by_dday)


def _phase_for_dday(
    d_day: int, phase_by_dday: dict[int, str], lo: int, hi: int
) -> str:
    """The authoritative phase for a D-day, clamping edge days to the nearest one."""
    exact = phase_by_dday.get(d_day)
    if exact:
        return exact
    clamped = min(max(d_day, lo), hi)
    clamped_phase = phase_by_dday.get(clamped)
    if clamped_phase:
        return clamped_phase
    if not phase_by_dday:
        return "TAPER"
    nearest = min(phase_by_dday, key=lambda key: abs(key - d_day))
    return phase_by_dday[nearest] or "TAPER"


def _rest_day(d_day: int, fight_date: date, phase: str) -> dict[str, Any]:
    """A schema-valid no-session calendar day for a D-day the converter dropped."""
    current = fight_date - timedelta(days=d_day)
    is_fight = d_day == 0
    return {
        "date": current.isoformat(),
        "weekday": _WEEKDAY_SHORT[current.weekday()],
        # A dropped day is either the fight itself (categorical) or genuine rest;
        # never invent a training intensity for a day the plan left blank.
        "day_type": "competition" if is_fight else "rest",
        "countdown_label": f"D-{d_day}",
        "phase_label": phase or "TAPER",
        "today_card": {
            # Empty headline -> the web classifier renders a compact rest row; a
            # dropped fight day is named so it never reads as ordinary rest.
            "headline": "Fight day" if is_fight else "",
            "readiness_status": "train_as_planned",
            "mindset_anchor": _empty_mindset(),
        },
        "sessions": [],
    }


def _overlay_day(
    existing: dict[str, Any], *, d_day: int, fight_date: date, phase: str
) -> dict[str, Any]:
    """A converter day's content under an authoritative calendar identity.

    Sessions, ``today_card``, ``day_type`` and coach-led contact are the converter's
    to keep; ``date`` / ``countdown_label`` / ``weekday`` / ``phase_label`` are
    the planner calendar's and are set here unconditionally. The faithfulness gate
    proves a D-day marker was not fabricated or misplaced against the source text,
    but it does not prove the converter's date and weekday agree with
    ``fight_date`` minus that countdown — so those are made deterministic rather
    than trusted.
    """
    day = existing if isinstance(existing, dict) else {}
    current = fight_date - timedelta(days=d_day)
    day["date"] = current.isoformat()
    day["countdown_label"] = f"D-{d_day}"
    day["weekday"] = _WEEKDAY_SHORT[current.weekday()]
    day["phase_label"] = phase or "TAPER"
    if not isinstance(day.get("sessions"), list):
        day["sessions"] = []
    return day


def _week_phase(days: list[dict[str, Any]]) -> str:
    """The phase a Mon-Sun week owns: its days' majority, ties to the sharper phase."""
    counts: dict[str, int] = {}
    for day in days:
        phase = _valid_phase(day.get("phase_label"), "TAPER")
        counts[phase] = counts.get(phase, 0) + 1
    if not counts:
        return "TAPER"
    top_count = max(counts.values())
    contenders = [phase for phase, count in counts.items() if count == top_count]
    return max(contenders, key=lambda phase: _PHASE_RANK.get(phase, 2))


def _best_match_week(
    week_ddays: set[int], llm_week_ddays: list[set[int]], plan_weeks: list[Any]
) -> dict[str, Any]:
    """The converter week sharing the most D-days with a rebuilt week (for metadata)."""
    best_index: int | None = None
    best_overlap = 0
    for index, ddays in enumerate(llm_week_ddays):
        overlap = len(week_ddays & ddays)
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = index
    if best_index is not None and isinstance(plan_weeks[best_index], dict):
        return plan_weeks[best_index]
    return {}


_DEFAULT_LOAD_FOCUS = {
    "volume": "moderate",
    "intensity": "moderate",
    "specificity": "moderate",
    "fatigue_target": "moderate",
}
_DEFAULT_PROGRESSION = {"week_type": "build", "planned_change_from_previous": ""}


def _assemble_week(
    *,
    days_out: list[dict[str, Any]],
    source_week: dict[str, Any],
    week_index: int,
) -> dict[str, Any]:
    """A schema-valid Mon-Sun week from a complete day list, boundaries recomputed.

    The week phase is its own days' authoritative majority; every day is stamped
    with it so the week reads one phase. ``start_date`` / ``end_date`` /
    ``countdown_start`` / ``countdown_end`` are derived from the days so they can
    never disagree with the calendar. Presentation metadata (goal, load focus,
    progression) is inherited from the best-matching converter week; the goal is
    only kept when that week's phase matches, so a mega-week's single goal cannot
    stamp a wrong label onto a week the spine assigns a different phase.
    """
    days_out.sort(
        key=lambda day: _parse_dday(day.get("countdown_label")) if _parse_dday(day.get("countdown_label")) is not None else -1,
        reverse=True,
    )
    phase = _week_phase(days_out)
    for day in days_out:
        day["phase_label"] = phase

    ddays = [
        parsed
        for parsed in (_parse_dday(day.get("countdown_label")) for day in days_out)
        if parsed is not None
    ]
    dates = [str(day.get("date") or "").strip() for day in days_out if str(day.get("date") or "").strip()]

    source_phase = _valid_phase(source_week.get("phase_label"))
    week_goal = str(source_week.get("week_goal") or "").strip() if source_phase == phase else ""

    load_focus = source_week.get("load_focus")
    if not isinstance(load_focus, dict) or not load_focus:
        load_focus = dict(_DEFAULT_LOAD_FOCUS)
    progression = source_week.get("progression")
    if not isinstance(progression, dict) or not progression:
        progression = dict(_DEFAULT_PROGRESSION)

    return {
        "week_id": f"wk-{week_index}",
        "week_index": week_index,
        "phase_label": phase,
        "week_goal": week_goal,
        "start_date": min(dates) if dates else "",
        "end_date": max(dates) if dates else "",
        "countdown_start": f"D-{max(ddays)}" if ddays else "",
        "countdown_end": f"D-{min(ddays)}" if ddays else "",
        "load_focus": load_focus,
        "progression": progression,
        "days": days_out,
    }


def _count_sessions(weeks: Any) -> int:
    """Total sessions across a plan's weeks — the content-preservation invariant."""
    total = 0
    for week in weeks if isinstance(weeks, list) else []:
        if not isinstance(week, dict):
            continue
        for day in week.get("days") or []:
            if isinstance(day, dict) and isinstance(day.get("sessions"), list):
                total += len(day["sessions"])
    return total


def _plan_signature(weeks: Any, fight_date: date) -> tuple:
    """A structural fingerprint for every calendar field the renderer consumes.

    Two plans share a signature only when they group the same days into the same
    weeks with the same authoritative week boundaries, date/countdown/weekday/
    phase identity and the same has-session shape. Cosmetic differences (a
    datetime suffix, ``D0`` vs ``D-0``, ``Monday`` vs ``Mon``, the week id) are
    normalised away so the reconcile is a true no-op on an already-correct plan —
    but a mega-week, stale week range, mislabelled phase, dropped day or wrong date
    all change the fingerprint and trigger a rebuild.
    """
    signature: list[Any] = []
    for week in weeks if isinstance(weeks, list) else []:
        if not isinstance(week, dict):
            continue
        day_sig = []
        for day in week.get("days") or []:
            if not isinstance(day, dict):
                continue
            d_day = _effective_dday(day, fight_date)
            iso = str(day.get("date") or "").strip()[:10]
            weekday = str(day.get("weekday") or "").strip()[:3].title()
            phase = _valid_phase(day.get("phase_label"))
            has_sessions = bool(day.get("sessions"))
            day_sig.append((d_day, iso, weekday, phase, has_sessions))
        signature.append(
            (
                _valid_phase(week.get("phase_label")),
                str(week.get("start_date") or "").strip()[:10],
                str(week.get("end_date") or "").strip()[:10],
                _parse_dday(week.get("countdown_start")),
                _parse_dday(week.get("countdown_end")),
                tuple(day_sig),
            )
        )
    return tuple(signature)


def reconcile_calendar_spine(structured_plan: Any, planning_brief: Any) -> Any:
    """Rebuild a dated camp's structured calendar from the authoritative spine.

    Returns a new plan dict when the calendar drifted from the authoritative
    contract, otherwise the input unchanged. Never raises: any unusable plan or
    brief is a silent no-op so the structured-card pipeline degrades to whatever
    the converter produced.
    """
    try:
        return _reconcile(structured_plan, planning_brief)
    except Exception:  # never block the card pipeline on reconciliation
        return structured_plan


def _reconcile(structured_plan: Any, planning_brief: Any) -> Any:
    if not isinstance(structured_plan, dict) or not isinstance(planning_brief, dict):
        return structured_plan
    # Open / renewable plans have no fight date or countdown calendar — the spine
    # concept does not apply, so never touch them.
    if isinstance(planning_brief.get("open_plan_spec"), dict):
        return structured_plan
    role_map = planning_brief.get("weekly_role_map")
    if not isinstance(role_map, dict):
        return structured_plan
    plan_weeks = structured_plan.get("weeks")
    if not isinstance(plan_weeks, list) or not plan_weeks:
        return structured_plan
    fight_date = parse_fight_date(_resolve_fight_date(planning_brief))
    if fight_date is None:
        return structured_plan

    phase_by_dday, role_map_max, role_map_min = _authoritative_phase_map(role_map)
    if role_map_max is None or role_map_min is None:
        return structured_plan

    # Index every converter day by its athlete-facing D-day (its label, or its date
    # as a fallback), merging two rows that land on one calendar day so no session
    # is lost. Record each converter week's D-day set for metadata matching.
    llm_days_by_dday: dict[int, dict[str, Any]] = {}
    llm_week_ddays: list[set[int]] = []
    for week in plan_weeks:
        week_ddays: set[int] = set()
        if isinstance(week, dict):
            for day in week.get("days") or []:
                if not isinstance(day, dict):
                    continue
                d_day = _effective_dday(day, fight_date)
                if d_day is None:
                    continue
                week_ddays.add(d_day)
                existing = llm_days_by_dday.get(d_day)
                if existing is None:
                    llm_days_by_dday[d_day] = copy.deepcopy(day)
                else:
                    extra = day.get("sessions")
                    if isinstance(extra, list) and extra:
                        base = existing.get("sessions")
                        existing["sessions"] = (
                            list(base) if isinstance(base, list) else []
                        ) + copy.deepcopy(extra)
        llm_week_ddays.append(week_ddays)

    # A dated camp with content but no resolvable calendar identity on any day
    # cannot be safely mapped onto the spine — leave it exactly as the converter
    # produced it rather than risk replacing sessions with rest days.
    if not llm_days_by_dday:
        return structured_plan

    # Camp start (D-N): the planner spine, extended to the athlete's real
    # days-until-fight and to any converter day within a lead-in of the spine.
    # Bounded so a garbled label/date can never balloon the calendar.
    bound = role_map_max + _EXTENT_SLACK_DAYS
    camp_start = role_map_max
    days_until = _resolve_days_until_fight(planning_brief)
    if days_until is not None and role_map_max <= days_until <= bound:
        camp_start = max(camp_start, days_until)
    present_ddays = set(llm_days_by_dday)
    in_range_llm_max = max((d for d in present_ddays if d <= bound), default=camp_start)
    camp_start = max(camp_start, in_range_llm_max)

    # Build the continuous spine D-camp_start .. D-0, overlaying converter content.
    spine_days: list[dict[str, Any]] = []
    for d_day in range(camp_start, -1, -1):
        phase = _phase_for_dday(d_day, phase_by_dday, role_map_min, role_map_max)
        existing = llm_days_by_dday.get(d_day)
        if isinstance(existing, dict):
            spine_days.append(_overlay_day(existing, d_day=d_day, fight_date=fight_date, phase=phase))
        else:
            spine_days.append(_rest_day(d_day, fight_date, phase))

    # Group into the Mon-Sun calendar weeks the web view renders.
    groups: dict[str, list[dict[str, Any]]] = {}
    for day in spine_days:
        monday = _monday_iso(str(day.get("date") or "")) or str(day.get("date") or "")
        groups.setdefault(monday, []).append(day)

    ordered_mondays = sorted(groups)
    if not ordered_mondays:
        return structured_plan

    # A converter day further out than the bounded spine (pathological — a real
    # session cannot precede plan creation) is attached to the earliest week rather
    # than dropped, so its content is never lost.
    leftover = sorted(
        (d for d in present_ddays if d > camp_start),
        reverse=True,
    )
    for d_day in leftover:
        phase = _phase_for_dday(d_day, phase_by_dday, role_map_min, role_map_max)
        groups[ordered_mondays[0]].insert(
            0, _overlay_day(llm_days_by_dday[d_day], d_day=d_day, fight_date=fight_date, phase=phase)
        )

    new_weeks: list[dict[str, Any]] = []
    for index, monday in enumerate(ordered_mondays):
        days_out = groups[monday]
        week_ddays = {
            parsed
            for parsed in (_parse_dday(day.get("countdown_label")) for day in days_out)
            if parsed is not None
        }
        source_week = _best_match_week(week_ddays, llm_week_ddays, plan_weeks)
        new_weeks.append(
            _assemble_week(days_out=days_out, source_week=source_week, week_index=index + 1)
        )

    # Already correct: identical Mon-Sun grouping, phases, week boundaries,
    # calendar identity and session shape. Return the input untouched so a right
    # plan is never churned — but continuity ALONE does not qualify.
    if _plan_signature(plan_weeks, fight_date) == _plan_signature(new_weeks, fight_date):
        return structured_plan

    # Content-preservation invariant: the rebuild only ever ADDS no-session days,
    # so it can never carry fewer sessions than the converter produced. If it
    # somehow would, discard the rebuild rather than lose an athlete's session.
    if _count_sessions(new_weeks) < _count_sessions(plan_weeks):
        return structured_plan

    rebuilt = copy.deepcopy(structured_plan)
    rebuilt["weeks"] = new_weeks
    return rebuilt