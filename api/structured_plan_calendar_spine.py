"""Guarantee a dated fight camp's structured calendar is continuous and gap-free.

The athlete-facing ``structured_plan`` is a *second* LLM conversion of the Stage 2
``final_plan_text``. That text is a **sparse** document: it lists the days that
carry a prescribed session and silently omits uneventful rest / no-session days.
The converter faithfully mirrors that sparseness, so ``structured_plan.weeks[*].days``
ends up containing only session-bearing days. The faithfulness gate
(:mod:`api.structured_plan_faithfulness`) then makes this *impossible for the
converter to fix on its own* — any D-day it invents that is not in the source
text is rejected as unverifiable — so the missing days can only be restored
deterministically, server-side, after the gate has run.

Why the sparse calendar is a bug, not a display choice
------------------------------------------------------
The web renderer derives a week's boundaries, its date/countdown range, its
app/coach session counts, its phase context and current-day resolution from the
days that survive in ``weeks[*].days`` (see ``web/lib/structured-plan.ts`` and
``web/lib/camp-map.ts``). When the days are sparse:

* a week that kept a single session day collapses to a one-day window
  ("D-21 -> D-21", "Thu 27 -> Thu 27 Aug"),
* the frontend's Mon-Sun ``splitWeekByCalendarWeek`` cuts a converter mega-week
  into single-day tabs that all inherit one phase (every tab reads "Taper"),
* counters and countdown ranges are computed from whatever days survived, and
* D-days disappear entirely instead of existing as no-session calendar days.

A **calendar day** and a **session** are different entities. A no-session day
must mean "this D-day exists and has no prescribed app session", never "this
D-day does not exist".

The authoritative spine
-----------------------
The deterministic ``weekly_role_map`` already carries the continuous calendar
spine — a ``calendar_days`` block (normal camps) or a ``countdown_span`` /
``countdown_range`` window (late-fight camps) per week, anchored on the fight
date. This module rebuilds ``structured_plan.weeks`` from that spine, overlaying
the converter's real session content onto it:

    fight date -> authoritative continuous calendar spine
               -> universal planner weeks (phase + D-day set)
               -> overlay the converter's session days (content preserved)
               -> fill every remaining D-day as a no-session calendar day
               -> recompute each week's date / countdown boundaries from its days.

The rebuild is:

* **content-preserving** — every converter day (its sessions, today_card,
  day_type, coach-led contact) is kept; a day the spine does not cover (e.g. a
  camp-start edge day one further out than the role map computed) is attached to
  the nearest week rather than dropped;
* **conservative** — it is a no-op unless a day is actually missing, so a dense
  camp that already satisfies the invariant is returned untouched;
* **scoped to dated camps** — open / renewable plans (no fight date, no
  countdown) and briefs without a usable role-map spine are left alone;
* **never raising** — a malformed plan or brief is a silent no-op so the
  structured-card pipeline degrades to whatever the converter produced.

It MUST run *after* the faithfulness gate (it introduces D-days the source text
never spelled out), mirroring where
:func:`api.structured_plan_sparring_reconcile.reconcile_coach_led_sparring_days`
runs.
"""
from __future__ import annotations

import copy
import re
from datetime import date, timedelta
from typing import Any

from fightcamp.fight_date_utils import parse_fight_date

_PHASE_VALUES = {"GPP", "SPP", "TAPER", "FIGHT_WEEK", "REINTEGRATION"}
_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DDAY_RE = re.compile(r"D-\s*(\d+)", re.I)


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


def _valid_phase(value: Any, fallback: str = "") -> str:
    phase = str(value or "").strip().upper()
    return phase if phase in _PHASE_VALUES else fallback


def _empty_mindset() -> dict[str, str]:
    return {"intent": "", "focus_cue": "", "reset_cue": ""}


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


def _authoritative_week_days(week: dict[str, Any], fight_date: date) -> list[dict[str, Any]]:
    """Exact calendar days a role-map week covers (furthest -> closest).

    Prefers the normal-camp ``calendar_days`` block (each entry carries its own
    D-day and after-fight flag); falls back to computing the days straight from
    the late-fight ``countdown_span`` / list ``countdown_range`` window. No
    Mon-Sun extrapolation and no post-fight days: a pre-fight camp calendar never
    runs past D-0, and the spine must contain only days the week genuinely covers.
    """
    out: list[dict[str, Any]] = []
    seen: set[int] = set()

    def _add(d_day: int) -> None:
        if d_day < 0 or d_day in seen:
            return
        seen.add(d_day)
        current = fight_date - timedelta(days=d_day)
        out.append(
            {
                "d_day": d_day,
                "date": current.isoformat(),
                "weekday": _WEEKDAY_SHORT[current.weekday()],
                "is_fight_day": d_day == 0,
            }
        )

    calendar_days = week.get("calendar_days")
    if isinstance(calendar_days, list) and calendar_days:
        for entry in calendar_days:
            if not isinstance(entry, dict) or entry.get("is_after_fight_day"):
                continue
            try:
                _add(int(entry.get("d_day")))
            except (TypeError, ValueError):
                continue
    else:
        span = _resolve_week_span(week)
        if span is None:
            return []
        start_d, end_d = span
        if start_d < end_d:
            start_d, end_d = end_d, start_d
        for d_day in range(start_d, end_d - 1, -1):
            _add(d_day)

    out.sort(key=lambda item: item["d_day"], reverse=True)
    return out


def _build_authoritative_spine(
    role_map: dict[str, Any], fight_date: date
) -> list[dict[str, Any]]:
    """Per-week ``{"phase", "days"}`` spine buckets; a D-day is kept in one week.

    A day claimed by two role-map weeks (a boundary overlap) stays with the
    furthest-out week so the buckets tile the countdown without duplicating a
    calendar-day identity.
    """
    weeks = role_map.get("weeks")
    if not isinstance(weeks, list):
        return []
    spine: list[dict[str, Any]] = []
    seen_ddays: set[int] = set()
    for week in weeks:
        if not isinstance(week, dict):
            continue
        days = _authoritative_week_days(week, fight_date)
        unique_days = [day for day in days if day["d_day"] not in seen_ddays]
        for day in unique_days:
            seen_ddays.add(day["d_day"])
        spine.append({"phase": _valid_phase(week.get("phase")), "days": unique_days})
    return spine


def _rest_day(spine_day: dict[str, Any], phase: str) -> dict[str, Any]:
    """A schema-valid no-session calendar day for a D-day the converter dropped."""
    d_day = spine_day["d_day"]
    is_fight = d_day == 0
    return {
        "date": spine_day["date"],
        "weekday": spine_day["weekday"],
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
    existing: dict[str, Any],
    *,
    d_day: int,
    iso_date: str,
    weekday: str,
    phase: str,
) -> dict[str, Any]:
    """Keep a converter day's content, forcing its calendar identity authoritative.

    Sessions, today_card, day_type and coach-led contact are preserved verbatim.
    The date / countdown_label / weekday the converter emitted already passed the
    faithfulness gate, so they are kept when present and only backfilled when
    blank. The phase is normalised to the authoritative week phase so a converter
    that stamped one phase across the whole camp cannot leave a week mislabelled.
    """
    day = copy.deepcopy(existing)
    if not str(day.get("date") or "").strip():
        day["date"] = iso_date
    if not str(day.get("countdown_label") or "").strip():
        day["countdown_label"] = f"D-{d_day}"
    if not str(day.get("weekday") or "").strip():
        day["weekday"] = weekday
    if phase:
        day["phase_label"] = phase
    elif _valid_phase(day.get("phase_label")) == "":
        day["phase_label"] = "TAPER"
    return day


def _nearest_bucket_index(spine: list[dict[str, Any]], d_day: int) -> int | None:
    """Index of the spine bucket whose covered D-days are closest to ``d_day``."""
    best_index: int | None = None
    best_distance: int | None = None
    for index, bucket in enumerate(spine):
        for day in bucket["days"]:
            distance = abs(day["d_day"] - d_day)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_index = index
    return best_index


def _best_match_week_index(
    bucket_ddays: set[int], llm_week_ddays: list[set[int]]
) -> int | None:
    """Converter week sharing the most D-days with an authoritative bucket."""
    best_index: int | None = None
    best_overlap = 0
    for index, ddays in enumerate(llm_week_ddays):
        overlap = len(bucket_ddays & ddays)
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = index
    return best_index


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
    phase: str,
    source_week: dict[str, Any],
    week_index: int,
) -> dict[str, Any]:
    """A schema-valid week from a complete day list, boundaries recomputed.

    ``start_date`` / ``end_date`` / ``countdown_start`` / ``countdown_end`` are
    derived from the days themselves so they can never disagree with the calendar
    the athlete sees. Presentation metadata (goal, load focus, progression) is
    inherited from the best-matching converter week; the week goal is only kept
    when that week's phase matches, so a mega-week's single goal cannot bleed a
    wrong label onto a week the spine assigns a different phase.
    """
    days_out.sort(
        key=lambda day: _parse_dday(day.get("countdown_label")) if _parse_dday(day.get("countdown_label")) is not None else -1,
        reverse=True,
    )
    ddays = [
        parsed
        for parsed in (_parse_dday(day.get("countdown_label")) for day in days_out)
        if parsed is not None
    ]
    dates = [str(day.get("date") or "").strip() for day in days_out if str(day.get("date") or "").strip()]

    resolved_phase = phase or _valid_phase(source_week.get("phase_label"), "TAPER")
    source_phase = _valid_phase(source_week.get("phase_label"))
    week_goal = ""
    if source_phase == resolved_phase:
        week_goal = str(source_week.get("week_goal") or "").strip()

    load_focus = source_week.get("load_focus")
    if not isinstance(load_focus, dict) or not load_focus:
        load_focus = dict(_DEFAULT_LOAD_FOCUS)
    progression = source_week.get("progression")
    if not isinstance(progression, dict) or not progression:
        progression = dict(_DEFAULT_PROGRESSION)

    return {
        "week_id": f"wk-{week_index}",
        "week_index": week_index,
        "phase_label": resolved_phase,
        "week_goal": week_goal,
        "start_date": min(dates) if dates else str(source_week.get("start_date") or ""),
        "end_date": max(dates) if dates else str(source_week.get("end_date") or ""),
        "countdown_start": f"D-{max(ddays)}" if ddays else "",
        "countdown_end": f"D-{min(ddays)}" if ddays else "",
        "load_focus": load_focus,
        "progression": progression,
        "days": days_out,
    }


def reconcile_calendar_spine(structured_plan: Any, planning_brief: Any) -> Any:
    """Rebuild a dated camp's structured calendar from the authoritative spine.

    Returns a new plan dict when the calendar was incomplete, otherwise the input
    unchanged. Never raises: any unusable plan or brief is a silent no-op so the
    structured-card pipeline degrades to whatever the converter produced.
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

    spine = _build_authoritative_spine(role_map, fight_date)
    if not any(bucket["days"] for bucket in spine):
        return structured_plan

    # Index every day the converter produced by its athlete-facing D-day (its
    # label, or its date as a fallback), and record each converter week's D-day set
    # for metadata matching.
    llm_days_by_dday: dict[int, dict[str, Any]] = {}
    llm_week_ddays: list[set[int]] = []
    present_ddays: set[int] = set()
    for week in plan_weeks:
        week_ddays: set[int] = set()
        if isinstance(week, dict):
            for day in week.get("days") or []:
                if not isinstance(day, dict):
                    continue
                d_day = _effective_dday(day, fight_date)
                if d_day is None:
                    continue
                present_ddays.add(d_day)
                week_ddays.add(d_day)
                # First occurrence wins; a converter that duplicated a D-day keeps
                # its earliest (furthest-out) card.
                llm_days_by_dday.setdefault(d_day, day)
        llm_week_ddays.append(week_ddays)

    # A dated camp with content but no resolvable calendar identity on any day
    # cannot be safely mapped onto the spine — leave it exactly as the converter
    # produced it rather than risk replacing sessions with rest days.
    if not llm_days_by_dday:
        return structured_plan

    auth_ddays = {day["d_day"] for bucket in spine for day in bucket["days"]}
    # Fast path: the calendar is already continuous (every authoritative day is
    # present). A dense camp that satisfies the invariant is returned untouched so
    # the reconcile can never regress a plan that was already correct.
    if auth_ddays.issubset(present_ddays):
        return structured_plan

    # --- rebuild each week from the spine, overlaying converter content --------
    buckets_days: list[list[Any]] = []
    consumed_ddays: set[int] = set()
    for bucket in spine:
        phase = bucket["phase"]
        days_out: list[dict[str, Any]] = []
        for spine_day in bucket["days"]:
            d_day = spine_day["d_day"]
            consumed_ddays.add(d_day)
            existing = llm_days_by_dday.get(d_day)
            if isinstance(existing, dict):
                days_out.append(
                    _overlay_day(
                        existing,
                        d_day=d_day,
                        iso_date=spine_day["date"],
                        weekday=spine_day["weekday"],
                        phase=phase,
                    )
                )
            else:
                days_out.append(_rest_day(spine_day, phase))
        buckets_days.append([phase, days_out])

    # A converter day whose D-day the spine never covered (e.g. a camp-start edge
    # day one further out than the role map's computed spine) is attached to the
    # nearest week so its content is preserved rather than dropped.
    edge_days = sorted(
        ((d_day, day) for d_day, day in llm_days_by_dday.items() if d_day not in consumed_ddays),
        key=lambda item: item[0],
        reverse=True,
    )
    for d_day, day in edge_days:
        bucket_index = _nearest_bucket_index(spine, d_day)
        if bucket_index is None:
            continue
        phase = buckets_days[bucket_index][0]
        current = fight_date - timedelta(days=d_day)
        buckets_days[bucket_index][1].append(
            _overlay_day(
                day,
                d_day=d_day,
                iso_date=current.isoformat(),
                weekday=_WEEKDAY_SHORT[current.weekday()],
                phase=phase,
            )
        )
        consumed_ddays.add(d_day)

    # Assemble the final weeks, renumbering so the strip reads Week 1, 2, 3…
    new_weeks: list[dict[str, Any]] = []
    for index, (phase, days_out) in enumerate(buckets_days):
        if not days_out:
            continue
        bucket_ddays = {day["d_day"] for day in spine[index]["days"]}
        match_index = _best_match_week_index(bucket_ddays, llm_week_ddays)
        source_week = (
            plan_weeks[match_index]
            if match_index is not None and isinstance(plan_weeks[match_index], dict)
            else {}
        )
        new_weeks.append(
            _assemble_week(
                days_out=days_out,
                phase=phase,
                source_week=source_week,
                week_index=len(new_weeks) + 1,
            )
        )

    if not new_weeks:
        return structured_plan

    # Content-preservation invariant: the rebuild only ever ADDS no-session days,
    # so it can never carry fewer sessions than the converter produced. If it
    # somehow would, discard the rebuild rather than lose an athlete's session.
    if _count_sessions(new_weeks) < _count_sessions(plan_weeks):
        return structured_plan

    rebuilt = copy.deepcopy(structured_plan)
    rebuilt["weeks"] = new_weeks
    return rebuilt
