"""Post-generation plan contract / invariant validator.

The generation pipeline has two calendar payload shapes that mean the same
thing: normal-camp weeks ship ``countdown_range`` (``[start, end]``) while
late-fight (D-21 and below) weeks ship ``countdown_span``
(``{"start_day": ..., "end_day": ...}``). Renderers, allocators, and the
weekly-schedule view each have to understand both. The standing risk is not a
single broken module but *silent contract drift*: one stage changes the shape
it emits and another stage keeps rendering a blank calendar without anyone
noticing until an athlete sees an empty plan.

This module runs once, after Stage 2 finalization and before the plan is
persisted, and records those invariants for telemetry and QA. It is intentionally:

* **shape-agnostic** — it reuses ``extract_weekly_schedule`` (the same code the
  UI renders from) so it validates the *rendered* calendar, catching
  range/span drift regardless of which planner built the plan; and
* **observational** — findings never veto or downgrade an already-produced plan.
  Planner/runtime logic owns the prescription and releaseable plan; this module
  only reports disagreement so it can be fixed at the canonical source.

``severity == "error"`` remains useful diagnostic metadata. It no longer means
an athlete-facing plan should be held for admin review.
"""
from __future__ import annotations

from typing import Any

from .weekly_schedule_view import extract_weekly_schedule

ERROR = "error"
WARNING = "warning"


def _violation(code: str, severity: str, message: str, *, week_index: int | None = None) -> dict[str, Any]:
    finding: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if week_index is not None:
        finding["week_index"] = week_index
    return finding


def _weeks(planning_brief: Any) -> list[dict[str, Any]]:
    if not isinstance(planning_brief, dict):
        return []
    weekly_role_map = planning_brief.get("weekly_role_map")
    if not isinstance(weekly_role_map, dict):
        return []
    weeks = weekly_role_map.get("weeks")
    if not isinstance(weeks, list):
        return []
    return [week for week in weeks if isinstance(week, dict)]


def _week_is_blank(rendered: dict[str, Any] | None) -> bool:
    """True when a week rendered no countdown spine at all (every day is blank)."""
    if not isinstance(rendered, dict):
        return True
    days = rendered.get("days")
    if not isinstance(days, list) or not days:
        return True
    return all(not isinstance(day.get("d_day"), int) for day in days if isinstance(day, dict))


def _week_allows_blank(week: dict[str, Any]) -> bool:
    """A week may legitimately render blank only if it explicitly opts in.

    Defaults to False: a structured week that yields no calendar is treated as
    drift unless the planner marked it intentionally empty.
    """
    return bool(week.get("allow_blank_calendar") or week.get("intentional_blank"))


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_plan_contract(
    final_result: dict[str, Any],
    *,
    fight_date: Any = None,
) -> dict[str, Any]:
    """Validate finalized-plan invariants for observational QA.

    Returns a structured, JSON-serialisable report::

        {
            "ran": bool,
            "ok": bool,
            "has_errors": bool,
            "checks": {check_name: bool, ...},
            "violations": [{"code", "severity", "message", "week_index?"}, ...],
            "week_count": int,
        }

    Never raises. Findings are diagnostic only; callers must not use this report
    to withhold an already-produced usable plan.
    """
    checks: dict[str, bool] = {}
    violations: list[dict[str, Any]] = []

    if not isinstance(final_result, dict):
        return {
            "ran": False,
            "ok": True,
            "has_errors": False,
            "checks": {},
            "violations": [],
            "week_count": 0,
        }

    try:
        planning_brief = final_result.get("planning_brief")
        weeks = _weeks(planning_brief)
        # The fight-day (D-0) assertion is driven solely by the fight_date the
        # caller affirmatively passes. Open camps pass None even when a stale
        # fight_date lingers on the request/brief, so we must NOT fall back to
        # planning_brief here or the missing-D-0 invariant would falsely trip.
        # The brief value is only used to help the calendar render below.
        assert_fight_day = bool(str(fight_date or "").strip())
        render_fight_date = (
            fight_date
            or (planning_brief.get("fight_date") if isinstance(planning_brief, dict) else None)
            or None
        )

        # No structured weekly schedule to validate. This is a legacy/edge shape,
        # not drift, so record it as a warning only.
        if not weeks:
            checks["weekly_schedule_present"] = False
            violations.append(
                _violation(
                    "weekly_schedule_missing",
                    WARNING,
                    "Plan has no structured weekly_role_map.weeks; calendar contract not validated.",
                )
            )
            return _finalize(checks, violations, week_count=0)

        checks["weekly_schedule_present"] = True

        rendered_weeks: list[dict[str, Any] | None] = []
        renderable_count = 0
        all_d_days: list[int] = []

        for index, week in enumerate(weeks):
            rendered = None
            try:
                rendered = extract_weekly_schedule(
                    planning_brief, week_index=index, fight_date=render_fight_date
                )
            except Exception:  # pragma: no cover - defensive: renderer must not break validation
                rendered = None
            rendered_weeks.append(rendered)

            if _week_is_blank(rendered):
                if not _week_allows_blank(week):
                    violations.append(
                        _violation(
                            "weekly_schedule_blank",
                            ERROR,
                            f"Week {index + 1} rendered a blank calendar (no D-day spine). "
                            "Likely countdown_range/countdown_span drift.",
                            week_index=index,
                        )
                    )
            else:
                renderable_count += 1
                for day in rendered.get("days", []):
                    d_day = day.get("d_day") if isinstance(day, dict) else None
                    if isinstance(d_day, int):
                        all_d_days.append(d_day)

        checks["weekly_schedule_not_blank"] = not any(
            v["code"] == "weekly_schedule_blank" for v in violations
        )
        checks["calendar_renderable"] = renderable_count > 0
        if renderable_count == 0:
            violations.append(
                _violation(
                    "calendar_unrenderable",
                    ERROR,
                    "No week in the plan rendered a calendar; the entire countdown spine is missing.",
                )
            )

        # Fight day must be present when a fight date is scheduled. Only assert
        # this once we have at least one renderable week, so a wholesale render
        # failure surfaces as calendar_unrenderable rather than a misleading
        # missing-D-0 finding.
        if assert_fight_day and renderable_count > 0:
            has_fight_day = 0 in all_d_days
            checks["fight_day_present"] = has_fight_day
            if not has_fight_day:
                violations.append(
                    _violation(
                        "fight_day_missing",
                        ERROR,
                        "Fight date is set but no week renders D-0 (the fight day) in the calendar.",
                    )
                )

        # Late-fight payload integrity: if the plan declares the late-fight
        # variant it must carry a non-empty session sequence, otherwise the
        # late-fight calendar/allocator has nothing to render.
        stage2_payload = final_result.get("stage2_payload")
        if isinstance(stage2_payload, dict):
            variant = _normalize_status(stage2_payload.get("payload_variant"))
            if variant == "late_fight_stage2_payload":
                sequence = (
                    stage2_payload.get("late_fight_session_sequence")
                    or stage2_payload.get("session_sequence")
                )
                has_sequence = isinstance(sequence, list) and len(sequence) > 0
                checks["late_fight_session_sequence_present"] = has_sequence
                if not has_sequence:
                    violations.append(
                        _violation(
                            "late_fight_session_sequence_empty",
                            ERROR,
                            "Plan declares the late-fight payload variant but carries no "
                            "session sequence to render.",
                        )
                    )

        plan_text = (
            final_result.get("plan_text")
            or final_result.get("final_plan_text")
            or final_result.get("draft_plan_text")
            or ""
        )
        has_plan_text = bool(str(plan_text).strip())
        checks["plan_text_present"] = has_plan_text
        if not has_plan_text:
            violations.append(
                _violation(
                    "plan_text_empty",
                    ERROR,
                    "Finalized plan carries no athlete-facing plan text.",
                )
            )

        return _finalize(checks, violations, week_count=len(weeks))
    except Exception as exc:  # pragma: no cover - validator must never block delivery
        violations.append(
            _violation(
                "validator_error",
                WARNING,
                f"Plan contract validator failed internally and was skipped: {type(exc).__name__}.",
            )
        )
        return _finalize(checks, violations, week_count=0, force_ok=True)


def _finalize(
    checks: dict[str, bool],
    violations: list[dict[str, Any]],
    *,
    week_count: int,
    force_ok: bool = False,
) -> dict[str, Any]:
    has_errors = (not force_ok) and any(v.get("severity") == ERROR for v in violations)
    return {
        "ran": True,
        "ok": not has_errors,
        "has_errors": has_errors,
        "checks": checks,
        "violations": violations,
        "week_count": week_count,
    }


def contract_report_requires_review(report: Any) -> bool:
    """Compatibility shim: contract findings are observational and never gate release."""
    return False
