from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .stage2_validator import week_incompleteness_code


_PHASE_WEEK_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(GPP|SPP|TAPER)\b.*?\bWeek\s+(\d+)\b",
    re.IGNORECASE,
)
_SESSION_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*)?"
    r"D-(\d{1,2})\s*\(\s*"
    r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:sday)?)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\s*\)\s*"
    r"(?:—|–|-|:)\s*(.+?)\s*(?:\*\*)?\s*$",
    re.IGNORECASE,
)
_WEEK_COMPLETENESS_CODES = {
    "missing_week_session_role",
    "late_camp_session_incomplete",
    "weekly_session_overage",
}
_NON_PHASE_TOP_LEVEL_HEADINGS = {
    "coach notes",
    "selection rationale",
    "nutrition",
    "recovery",
    "rehab protocols",
    "mindset overview",
    "sparring & conditioning adjustments",
    "sparring & conditioning adjustments table",
    "nutrition adjustments for unknown sparring load",
    "athlete profile",
}
_PRIMARY_STRENGTH_ROLE_KEYS = {
    "primary_strength_day",
    "structural_strength_day",
    "neural_plus_strength_day",
}
_GLYCOLYTIC_SUPPRESSED_ROLE_KEYS = {"light_fight_pace_touch_day"}


def _norm(value: Any) -> str:
    return re.sub(r"[*_`]+", "", str(value or "")).strip().lower()


_LEADING_BULLET_RE = re.compile(r"^\s*[-*•]\s+")


def _norm_anchor(value: Any) -> str:
    """Normalize an anchor line, dropping a leading -, *, or • bullet marker.

    The raw validator strips bullets before flagging the leak, but the rendered
    occurrence inside a session block may still carry its Markdown bullet, so
    both sides must be bullet-normalized before comparing anchor text.
    """
    return _norm(_LEADING_BULLET_RE.sub("", str(value or ""), count=1))


def _top_level_heading_key(line: str) -> str:
    stripped = str(line or "").strip()
    if stripped.startswith(("- ", "* ")):
        return ""
    stripped = re.sub(r"^#{1,6}\s*", "", stripped)
    stripped = re.sub(r"^\*\*(.*?)\*\*$", r"\1", stripped)
    return _norm(stripped).rstrip(":.")


def _session_blocks(final_plan_text: str) -> list[dict[str, Any]]:
    """Parse canonical athlete-facing D-X session blocks."""
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_phase = ""
    current_week: int | None = None

    for raw_line in str(final_plan_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        phase_week = _PHASE_WEEK_HEADER_RE.match(line)
        if phase_week:
            if current:
                blocks.append(current)
                current = None
            current_phase = phase_week.group(1).upper()
            current_week = int(phase_week.group(2))
            continue

        if current_week is not None and _top_level_heading_key(line) in _NON_PHASE_TOP_LEVEL_HEADINGS:
            if current:
                blocks.append(current)
                current = None
            current_phase = ""
            current_week = None
            continue

        header = _SESSION_HEADER_RE.match(line)
        if header:
            if current:
                blocks.append(current)
            current = {
                "d_day": int(header.group(1)),
                "title": header.group(2).strip(),
                "phase": current_phase,
                "week_index": current_week,
                "lines": [],
            }
            continue

        if current:
            current["lines"].append(line)

    if current:
        blocks.append(current)
    return blocks


def _active_session_counts_by_week(final_plan_text: str) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for block in _session_blocks(final_plan_text):
        week_index = block.get("week_index")
        d_day = block.get("d_day")
        if isinstance(week_index, int) and isinstance(d_day, int) and d_day > 0:
            counts[week_index] += 1
    return dict(counts)


def _active_week_count(planning_brief: dict[str, Any]) -> int:
    """Active-week span from the final role map, matching the raw validator.

    Mirrors ``len(weeks)`` in ``_week_completeness_warnings`` so the shared
    late-camp boundary is computed from identical inputs on both sides.
    """
    weeks = (planning_brief.get("weekly_role_map") or {}).get("weeks")
    return len(weeks) if isinstance(weeks, list) else 0


def _phase_roles(planning_brief: dict[str, Any], phase: str) -> list[dict[str, Any]] | None:
    weekly_role_map = planning_brief.get("weekly_role_map") or {}
    weeks = weekly_role_map.get("weeks") or []
    if not isinstance(weeks, list) or not weeks:
        return None

    phase_key = str(phase or "").strip().upper()
    matching_weeks = [
        week
        for week in weeks
        if isinstance(week, dict) and str(week.get("phase") or "").strip().upper() == phase_key
    ]
    if not matching_weeks:
        return None

    return [
        role
        for week in matching_weeks
        for role in (week.get("session_roles") or [])
        if isinstance(role, dict)
    ]


def _requirement_survives_final_role_map(
    planning_brief: dict[str, Any], *, phase: str, requirement: str
) -> bool | None:
    """Resolve only the two proven stale requirement classes from production."""
    roles = _phase_roles(planning_brief, phase)
    if roles is None:
        return None

    requirement_key = str(requirement or "").strip().lower()
    if requirement_key == "primary_strength":
        return any(
            str(role.get("role_key") or "").strip().lower() in _PRIMARY_STRENGTH_ROLE_KEYS
            for role in roles
        )

    if requirement_key == "glycolytic":
        for role in roles:
            role_key = str(role.get("role_key") or "").strip().lower()
            if role_key in _GLYCOLYTIC_SUPPRESSED_ROLE_KEYS:
                continue
            if str(role.get("preferred_system") or "").strip().lower() == "glycolytic":
                return True
            if "glycolytic" in role_key or "fight_pace" in role_key:
                return True
        return False

    return None


def _is_tactical_block(block: dict[str, Any]) -> bool:
    title = _norm(block.get("title"))
    body = [_norm(line) for line in block.get("lines") or []]
    return "tactical watch" in title or any("tactical review only" in line for line in body)


def _is_legitimate_tactical_anchor(final_plan_text: str, line: str) -> bool:
    """Whitelist an Anchor line only when every rendered occurrence is tactical.

    Classification is over the *complete* final text, not just parsed D-X
    session blocks: an occurrence outside any session (e.g. leaked into Coach
    Notes) or inside a non-tactical block is never captured by
    ``_session_blocks`` and would otherwise be invisible, letting a genuine
    internal-contract leak be silently suppressed. Every exact occurrence in
    the full text must fall inside a Tactical Watch block for the whitelist to
    apply.
    """
    target = _norm_anchor(line)
    if not target.startswith("anchor:"):
        return False

    total_occurrences = sum(
        1
        for raw_line in str(final_plan_text or "").splitlines()
        if _norm_anchor(raw_line) == target
    )
    if not total_occurrences:
        return False

    tactical_occurrences = 0
    for block in _session_blocks(final_plan_text):
        if not _is_tactical_block(block):
            continue
        tactical_occurrences += sum(
            1 for value in (block.get("lines") or []) if _norm_anchor(value) == target
        )

    return tactical_occurrences == total_occurrences


def _reconcile_week_warning(
    warning: dict[str, Any], *, counts_by_week: dict[int, int], active_week_count: int
) -> dict[str, Any] | None:
    code = str(warning.get("code") or "")
    if code not in _WEEK_COMPLETENESS_CODES:
        return warning

    try:
        week_index = int(warning.get("week_index"))
        expected = int(warning.get("expected_session_count"))
    except (TypeError, ValueError):
        return warning
    if week_index not in counts_by_week:
        return warning

    actual = counts_by_week[week_index]
    if code in {"missing_week_session_role", "late_camp_session_incomplete"}:
        if actual >= expected:
            return None
        return {**warning, "actual_session_count": actual}

    if code == "weekly_session_overage":
        if actual == expected:
            return None
        if actual < expected:
            # Reuse the validator's global late-camp boundary (position in the
            # active-week span) rather than inventing a phase-based rule, so an
            # early SPP week in a long camp is not mislabelled as late camp.
            return {
                **warning,
                "code": week_incompleteness_code(week_index, active_week_count),
                "actual_session_count": actual,
                "message": f"Week {week_index} is structurally incomplete compared with the weekly role map.",
            }

    return {**warning, "actual_session_count": actual}


def _filter_warning(
    warning: dict[str, Any],
    *,
    planning_brief: dict[str, Any],
    final_plan_text: str,
    counts_by_week: dict[int, int],
    active_week_count: int,
) -> dict[str, Any] | None:
    warning = _reconcile_week_warning(
        warning, counts_by_week=counts_by_week, active_week_count=active_week_count
    )
    if warning is None:
        return None

    code = str(warning.get("code") or "")
    if code == "missing_required_element":
        survives = _requirement_survives_final_role_map(
            planning_brief,
            phase=str(warning.get("phase") or ""),
            requirement=str(warning.get("requirement") or ""),
        )
        if survives is False:
            return None

    if (
        code == "internal_render_contract_leak"
        and str(warning.get("label") or "") == "anchor_label"
        and _is_legitimate_tactical_anchor(final_plan_text, str(warning.get("line") or ""))
    ):
        return None

    return warning


def postprocess_stage2_validator_report(
    *,
    planning_brief: dict[str, Any],
    final_plan_text: str,
    validator_report: dict[str, Any],
) -> dict[str, Any]:
    """Remove only proven representation false positives using final authority."""
    if not isinstance(validator_report, dict):
        return validator_report

    counts_by_week = _active_session_counts_by_week(final_plan_text)
    active_week_count = _active_week_count(planning_brief)
    filtered_warnings: list[dict[str, Any]] = []
    for raw in validator_report.get("warnings") or []:
        if not isinstance(raw, dict):
            continue
        item = _filter_warning(
            raw,
            planning_brief=planning_brief,
            final_plan_text=final_plan_text,
            counts_by_week=counts_by_week,
            active_week_count=active_week_count,
        )
        if item is not None:
            filtered_warnings.append(item)

    result = {**validator_report, "warnings": filtered_warnings}
    result["week_completeness_warnings"] = [
        item for item in filtered_warnings if str(item.get("code") or "") in _WEEK_COMPLETENESS_CODES
    ]
    result["internal_render_contract_leak_warnings"] = [
        item for item in filtered_warnings if item.get("code") == "internal_render_contract_leak"
    ]
    result["missing_required_elements"] = [
        item
        for item in (validator_report.get("missing_required_elements") or [])
        if not (
            isinstance(item, dict)
            and _requirement_survives_final_role_map(
                planning_brief,
                phase=str(item.get("phase") or ""),
                requirement=str(item.get("requirement") or ""),
            )
            is False
        )
    ]
    return result
