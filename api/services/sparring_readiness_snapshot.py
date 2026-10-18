"""Athlete-scoped persisted history -> ephemeral deterministic planner input."""
from __future__ import annotations

import logging
from datetime import date
import re
from typing import Any, Callable

from fightcamp.sparring_readiness import recent_rows
from api.contracts.readiness_message import classify_injury_surface
from api.contracts.completion import COMPLETION_STATUSES
from api.contracts.external_training import ExternalTrainingFields

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

    def unavailable(method: str, error: Exception) -> None:
        if method not in context["unavailable"]:
            context["unavailable"].append(method)
            # Source/type diagnostics only: database exception messages and
            # workout/medical values do not belong in generation logs.
            logger.warning("[generation] sparring context unavailable athlete_id=%s source=%s error_type=%s",
                           athlete_id, method, type(error).__name__)

    def read(method: str, fetch: Callable[[], Any]) -> list[dict]:
        try:
            rows = fetch()
            if not isinstance(rows, list):
                raise ValueError("history response is not a row list")
        except Exception as exc:
            unavailable(method, exc)
            return []
        valid = []
        for row in rows:
            try:
                if not isinstance(row, dict) or not row.get("athlete_id"):
                    raise ValueError("history row has no owner")
                if row["athlete_id"] != athlete_id:
                    raise ValueError("history source returned another owner")
                if method != "list_injury_flags":
                    date.fromisoformat(row["training_day"])
                if method == "list_session_completions":
                    if (not row.get("session_id") or not row.get("plan_id")
                            or row.get("status") not in COMPLETION_STATUSES):
                        raise ValueError("completion identity/status unavailable")
                if method == "list_external_training_sessions":
                    if not row.get("id"):
                        raise ValueError("manual occurrence identity unavailable")
                    ExternalTrainingFields.model_validate({key: row[key] for key in ExternalTrainingFields.model_fields})
                valid.append(row)
            except Exception as exc:
                # Keep other verified rows, but never call this source complete.
                unavailable(method, exc)
        return valid

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
    external = read("list_external_training_sessions", lambda: store.list_external_training_sessions(athlete_id, limit=200))
    # Preload each source independently so a fallback [] retains its failure
    # attribution and cannot discard records retrieved from the other source.
    history_input = {"as_of": as_of, "sessions": recent_rows(training_history(
        store, athlete_id, prescribed=completions, external=external), as_of),
        "checkins": context["checkins"]}
    history_input["sessions"] = [{key: row[key] for key in (
        "id", "source", "plan_id", "session_id", "training_day", "status", "session_rpe",
        "pain_after", "duration_minutes", "effort", "activity", "completion_origin") if key in row}
        for row in history_input["sessions"]]
    history_input["unavailable"] = [source for source in context["unavailable"] if source in {
        "list_session_completions", "list_external_training_sessions", "list_today_checkins",
    }]
    # Workload keeps its five-day window; the contact context above keeps seven.
    if has_unverified_completions(history_input["sessions"], as_of):
        history_input["unavailable"].append("completion_provenance")
    history_input["available"] = not history_input["unavailable"]
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
        except Exception as exc:
            unavailable("completion_plan", exc)
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
