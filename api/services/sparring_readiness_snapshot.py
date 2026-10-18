"""Athlete-scoped persisted history -> ephemeral deterministic planner input."""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from fightcamp.sparring_readiness import recent_rows
from api.contracts.readiness_message import classify_injury_surface

from .today_service import _structured_plan_weeks, resolve_training_day
from .training_history import training_history
from fightcamp.completed_workload import completed_workload, has_unverified_completions

logger = logging.getLogger(__name__)


def _contact_load(plan: dict, completion: dict) -> str:
    # Match the actual completed session, not another session on the same day.
    for week in _structured_plan_weeks(plan, training_day=completion["training_day"]):
        for day in week.get("days", []):
            if day.get("date") != completion["training_day"]:
                continue
            for session in day.get("sessions", []):
                if session.get("session_id") != completion.get("session_id"):
                    continue
                text = " ".join(str(session.get(key) or "") for key in ("title", "session_type", "objective")).lower()
                if re.search(r"\b(?:no|non|without)[ -]contact\b|\bno sparring\b", text):
                    return "none"
                if not re.search(r"\bspar(?:ring)?\b", text):
                    return "none"
                effective_load = str(session.get("effective_load") or "").strip().lower()
                if completion.get("status") == "done" and effective_load == "hard":
                    return "hard"
                if effective_load in {"technical", "reduced", "light", "none"}:
                    return "reduced" if effective_load != "none" else "none"
                if (
                    completion.get("status") == "done"
                    and re.search(r"\bhard spar(?:ring)?\b", text)
                    and not re.search(r"\b(?:no|avoid) hard\b|\b(?:light|technical|reduced|managed)\b", text)
                ):
                    return "hard"
                return "reduced"
    return "unknown"


def annotate_payload_with_sparring_readiness(
    payload: dict, *, store: Any, athlete_id: str,
    athlete_timezone: str = "", training_day: str | None = None,
) -> dict:
    """Read only existing store contracts. A failed read raises risk, not clearance.

    An empty history is normal for a new athlete. No caller-supplied history is
    trusted at this boundary. Rows and referenced plans are ownership checked.
    """
    as_of = training_day or resolve_training_day(athlete_timezone)
    context: dict[str, Any] = {"as_of": as_of, "checkins": [], "sessions": [], "active_injuries": [], "unavailable": []}

    def read(method: str, fetch: Callable[[], Any]) -> list[dict]:
        try:
            return [row for row in fetch() if row.get("athlete_id") == athlete_id]
        except Exception:
            logger.warning("[generation] sparring context unavailable: %s", method, exc_info=True)
            context["unavailable"].append(method)
            return []

    context["checkins"] = recent_rows(
        read("list_today_checkins", lambda: store.list_today_checkins(athlete_id, limit=100)), as_of
    )
    context["active_injuries"] = read(
        "list_injury_flags",
        lambda: store.list_injury_flags(athlete_id, statuses=["open", "monitoring"], limit=500),
    )
    context["active_injuries"] = [
        {**row, "surface_class": classify_injury_surface(row)}
        for row in context["active_injuries"]
    ]
    completions = recent_rows(
        read("list_session_completions", lambda: store.list_session_completions(athlete_id, limit=200)), as_of
    )
    if has_unverified_completions(completions, as_of, days=7):
        context["unavailable"].append("completion_provenance")
    # Keep contact permission evidence prescribed-only. Manual Sparring/Hard
    # describes effort, never head contact. Conditioning shares Today's engine.
    history_input = {"as_of": as_of, "sessions": [], "checkins": context["checkins"], "available": True}
    try:
        history_input["sessions"] = recent_rows(training_history(
            store, athlete_id, prescribed=completions), as_of)
    except Exception:
        logger.warning("[generation] completed training history unavailable", exc_info=True)
        history_input["available"] = False
    history_input["sessions"] = [{key: row[key] for key in (
        "id", "source", "plan_id", "session_id", "training_day", "status", "session_rpe",
        "pain_after", "duration_minutes", "effort", "activity", "completion_origin") if key in row}
        for row in history_input["sessions"]]
    if has_unverified_completions(history_input["sessions"], as_of):
        history_input["available"] = False
    history_input["workload"] = completed_workload(history_input["sessions"], as_of)
    plans = {}
    for row in completions:
        if row.get("status") not in {"done", "modified"}:
            continue
        if row.get("completion_origin") != "reported":
            continue
        plan_id = row.get("plan_id")
        try:
            if plan_id not in plans:
                plans[plan_id] = store.get_plan(plan_id)
            plan = plans[plan_id]
            if not plan or plan.get("athlete_id") != athlete_id:
                raise ValueError("completion plan is unavailable")
            load = _contact_load(plan, row)
            if load == "unknown":
                context["unavailable"].append("completed_session")
        except Exception:
            logger.warning("[generation] sparring completion context unavailable", exc_info=True)
            context["unavailable"].append("completion_plan")
            load = "unknown"
        context["sessions"].append({**row, "contact_load": load})
    # Carry only decision evidence, never completion notes or unrelated profile data.
    fields = {
        "checkins": ("training_day", "updated_at", "created_at", "sleep", "body", "pain", "active_injury", "previous_session", "neurological_symptoms"),
        "sessions": ("plan_id", "session_id", "training_day", "status", "session_rpe", "contact_load", "completion_origin"),
        "active_injuries": ("surface_class", "body_area", "label", "description", "severity", "status", "triage_category", "injury_type", "consequence", "flags", "blocked_training_tags"),
    }
    for key, allowed in fields.items():
        context[key] = [{field: row[field] for field in allowed if field in row} for row in context[key]]
    history_input["checkins"] = context["checkins"]
    context["training_history"] = history_input
    return {**payload, "_sparring_readiness": context}
