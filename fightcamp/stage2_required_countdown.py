from __future__ import annotations

import re
from typing import Any

_COUNTDOWN_HEADER = re.compile(r"^\s*(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*)?D-(\d+)\b", re.IGNORECASE)


def _normalise_label(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"D-(\d+)", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return f"D-{int(match.group(1))}"


def _rendered_countdown_labels(final_plan_text: str) -> set[str]:
    labels: set[str] = set()
    for raw_line in str(final_plan_text or "").splitlines():
        match = _COUNTDOWN_HEADER.match(raw_line.strip())
        if match:
            labels.add(f"D-{int(match.group(1))}")
    return labels


def _session_sequence_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("visible_session_sequence", "session_sequence", "countdown_sessions", "sessions"):
        value = spec.get(key)
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]
    return []


def _session_render_label(session: dict[str, Any], fallback_label: str) -> str:
    display = str(session.get("countdown_display_label") or "").strip()
    if display:
        return display
    weekday = str(session.get("real_weekday") or session.get("scheduled_day_hint") or "").strip()
    if weekday:
        return f"{fallback_label} ({weekday.title()})"
    return fallback_label


def _is_render_mandatory_session(session: dict[str, Any]) -> bool:
    role_key = str(session.get("role_key") or "").strip()
    if role_key in {"", "hard_sparring_day"}:
        return False
    category = str(session.get("category") or "").strip()
    if category == "sparring" or bool(session.get("coach_owned")):
        return False
    return bool(session.get("scheduled_countdown_label") or session.get("countdown_label"))


def required_countdown_session_warnings(planning_brief: dict[str, Any], final_plan_text: str) -> list[dict[str, Any]]:
    """Return hard warnings when selected late-fight sessions are not rendered.

    The late-fight allocator can correctly schedule a low-cost support/freshness
    card such as D-3 (Wednesday), while the final LLM render can still omit it
    because it is not a meaningful stressor. This check treats the selected
    countdown sequence as render-mandatory, independent of stress_class.
    """

    spec = planning_brief.get("late_fight_plan_spec") if isinstance(planning_brief, dict) else None
    if not isinstance(spec, dict) or not spec:
        return []

    rendered_labels = _rendered_countdown_labels(final_plan_text)
    if not rendered_labels:
        return []

    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for session in _session_sequence_from_spec(spec):
        if not _is_render_mandatory_session(session):
            continue
        label = _normalise_label(session.get("scheduled_countdown_label") or session.get("countdown_label"))
        if not label or label == "D-0" or label in rendered_labels or label in seen:
            continue
        seen.add(label)
        warnings.append(
            {
                "code": "late_fight_missing_required_countdown_session",
                "message": f"Final render omitted selected late-fight session {label}.",
                "days_out_bucket": label,
                "expected_display_label": _session_render_label(session, label),
                "role_key": session.get("role_key"),
                "category": session.get("category"),
                "stress_class": session.get("stress_class"),
                "blocking": True,
            }
        )
    return warnings
