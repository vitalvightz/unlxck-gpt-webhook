"""Pure, dated evidence for hard-sparring eligibility (scheduling defaults)."""
from __future__ import annotations

from datetime import date
from typing import Any


def recent_rows(rows: list[dict[str, Any]], as_of: str, days: int = 7) -> list[dict[str, Any]]:
    try:
        today = date.fromisoformat(as_of)
    except (ValueError, TypeError):
        return []
    result = []
    for row in rows:
        try:
            age = (today - date.fromisoformat(str(row.get("training_day", "")))).days
        except (ValueError, TypeError):
            continue
        if 0 <= age < days:
            result.append(row)
    return result


def sparring_readiness_flags(context: dict[str, Any]) -> list[str]:
    """Count distinct days/sessions; future dates and stale evidence never count."""
    as_of = context.get("as_of", "")
    # More than one plan may have a check-in on the same day. Latest update wins.
    checkins = {}
    for row in sorted(context.get("checkins", []), key=lambda r: str(r.get("updated_at") or r.get("created_at") or "")):
        checkins[row.get("training_day")] = row
    checkins = recent_rows(list(checkins.values()), as_of)
    sessions = {
        (row.get("plan_id"), row.get("session_id"), row.get("training_day")): row
        for row in recent_rows(context.get("sessions", []), as_of)
        if row.get("status") in {"done", "modified"}
    }
    flags = set()
    if sum(row.get("sleep") == "poor" or row.get("body") == "flat" for row in checkins) >= 3:
        flags.add("poor_recovery")
    hard = [row for row in sessions.values() if row.get("contact_load") == "hard"]
    contact = [row for row in sessions.values() if row.get("contact_load") in {"hard", "reduced"}]
    if len(hard) >= 3 or len(recent_rows(hard, as_of, 3)) >= 2 or len(contact) >= 4:
        flags.add("high_contact_load")
    demanding = [row for row in sessions.values() if isinstance(row.get("session_rpe"), (int, float)) and row["session_rpe"] >= 8]
    hard_reports = [row for row in checkins if row.get("previous_session") == "very_hard"]
    if len(recent_rows(demanding, as_of, 3)) >= 2 or len(recent_rows(hard_reports, as_of, 3)) >= 2:
        flags.add("high_fatigue")
    latest = max(checkins, key=lambda row: row["training_day"], default={})
    if latest.get("pain") in {"manageable", "high"} or latest.get("active_injury") == "worse":
        flags.add("moderate_injury")
    if any(row.get("neurological_symptoms") is True for row in checkins):
        flags.add("neurological_symptoms")
    if any(
        row.get("severity") in {"moderate", "high", "severe"}
        and row.get("surface_class") != "stable_surface"
        for row in context.get("active_injuries", [])
    ):
        flags.add("moderate_injury")
    active_injuries = context.get("active_injuries", [])
    if any(row.get("surface_class") == "surface_no_contact" for row in active_injuries):
        flags.add("medical_contact_restriction")
    serious_categories = {"concussion", "suspected_concussion", "acute_nerve_issue", "nerve_involvement"}
    serious_flag_names = {
        "suspected_concussion", "concussion_symptoms", "neurological_symptoms",
        "recent_ko", "recent_head_injury", "medical_contact_restriction", "no_contact",
    }
    blocked_contact_tags = {"contact", "sparring", "hard_contact", "head_impact"}
    for row in active_injuries:
        category = str(row.get("triage_category") or row.get("injury_type") or "").strip().lower()
        row_flags = {str(value).strip().lower() for value in row.get("flags", []) if str(value).strip()}
        blocked_tags = {str(value).strip().lower() for value in row.get("blocked_training_tags", []) if str(value).strip()}
        description = str(row.get("description") or "").strip().lower()
        if (
            category in serious_categories
            or row_flags & serious_flag_names
            or any(token in description for token in ("concussion", "knocked out", "knockout", "neurological"))
        ):
            flags.add("suspected_concussion")
        if blocked_tags & blocked_contact_tags:
            flags.add("medical_contact_restriction")
    if context.get("reduced_contact_requested") is True:
        flags.add("reduced_contact_requested")
    if context.get("unavailable"):
        flags.add("sparring_history_unavailable")
    return sorted(flags)
