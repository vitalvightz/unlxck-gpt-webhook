"""Pure, dated evidence for hard-sparring eligibility (scheduling defaults)."""
from __future__ import annotations

from datetime import date
from typing import Any

from .completed_workload import completion_origin_of


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


def sparring_readiness_flags(context: dict[str, Any], *, evidence: list[dict] | None = None) -> list[str]:
    """Count distinct days/sessions; future dates and stale evidence never count."""
    from .injury_triage import current_report_medical_hold_reasons
    from .injury_awareness import has_independent_medical_override, is_awareness_only

    as_of = context.get("as_of", "")
    # More than one plan may have a check-in on the same day. Latest update wins.
    checkins = {}
    for row in sorted(context.get("checkins", []), key=lambda r: str(r.get("updated_at") or r.get("created_at") or "")):
        checkins[row.get("training_day")] = row
    checkins = recent_rows(list(checkins.values()), as_of)
    completed = [row for row in recent_rows(context.get("sessions", []), as_of)
                 if row.get("status") in {"done", "modified"} and row.get("source") != "external"]
    sessions = {
        (row.get("plan_id"), row.get("session_id"), row.get("training_day")): row
        for row in completed if completion_origin_of(row) == "reported"
    }
    flags = set()
    if any(completion_origin_of(row) not in {"reported", "day_credit"} for row in completed):
        flags.add("sparring_history_unavailable")
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
    def injury_signal(row: dict, *, source: str, global_capacity: bool, reason: str) -> None:
        flags.add("moderate_injury")
        if evidence is not None:
            evidence.append({
                "flag": "moderate_injury", "source": source,
                "scope": "training_capacity" if global_capacity else "contact",
                "reason_code": reason, "as_of": as_of,
                **{key: row[key] for key in ("id", "training_day", "severity", "severity_source") if key in row},
            })

    latest = max(checkins, key=lambda row: row["training_day"], default={})
    if latest.get("pain") in {"manageable", "high"} or latest.get("active_injury") == "worse":
        # Manageable pain is contact-readiness evidence, not a diagnosis or an
        # automatic loss of a weekly training appointment. High pain/worsening
        # is current functional evidence and remains a capacity restriction.
        injury_signal(latest, source="today_checkins",
                      global_capacity=latest.get("pain") == "high" or latest.get("active_injury") == "worse",
                      reason="worsening_checkin" if latest.get("active_injury") == "worse" else "pain_checkin")
    if any(row.get("neurological_symptoms") is True for row in checkins):
        flags.add("neurological_symptoms")
    for row in context.get("active_injuries", []):
        severity = row.get("manual_severity") or row.get("severity")
        if row.get("surface_class") == "stable_surface" or is_awareness_only({**row, "severity": severity}):
            continue
        medical = has_independent_medical_override(row)
        if severity not in {"moderate", "high", "severe"} and not medical:
            continue
        # Legacy intake tracking defaults every free-text symptom to moderate.
        # That compatibility value has no severity provenance and cannot trump
        # current parsed intake. Keep its conservative contact signal only.
        confirmed = bool(row.get("manual_severity")) or bool(
            row.get("severity_source") and row["severity_source"] != "fallback_default"
        ) or row.get("source") in {"manual", "clinician", "checkin"}
        injury_signal(row, source="injury_flags",
                      global_capacity=medical or severity in {"high", "severe"} or confirmed,
                      reason="medical_override" if medical else "injury_severity" if confirmed or severity in {"high", "severe"}
                      else "unverified_tracker_severity")
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
        if current_report_medical_hold_reasons(row):
            flags.add("medical_contact_restriction")
        category = str(row.get("triage_category") or row.get("injury_type") or "").strip().lower()
        row_flags = {str(value).strip().lower() for value in (row.get("flags") or []) if str(value).strip()}
        blocked_tags = {str(value).strip().lower() for value in (row.get("blocked_training_tags") or []) if str(value).strip()}
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
