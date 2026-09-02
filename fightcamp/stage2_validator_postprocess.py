from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


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
# Exact final-role identities whose stale preferred_system metadata must not
# resurrect a pre-morph glycolytic requirement.
_GLYCOLYTIC_SUPPRESSED_ROLE_KEYS = {"light_fight_pace_touch_day"}


def _norm(value: Any) -> str:
    return re.sub(r"[*_`]+", "", str(value or "")).strip().lower()


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
            str(role.get("category") or "").strip().lower() == "strength"
            or "strength" in str(role.get("role_key") or "").strip().lower()
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

    # Do not infer suppression for any other requirement class in this PR.
    return None


def _is_tactical_block(block: dict[str, Any]) -> bool:
    title = _norm(block.get("title"))
    body = [_norm(line) for line in block.get("lines") or []]
    return "tactical watch" in title or any("tactical review only" in line for line in body)


def _is_legitimate_tactical_anchor(final_plan_text: str, line: str) -> bool:
    """Whitelist an Anchor line only when every rendered occurrence is tactical."""
    target = _norm(line)
    if not target.startswith("anchor:"):
        return False

    matches: list[bool] = []
    for block in _session_blocks(final_plan_text):
        occurrence_count = sum(1 for value in (block.get("lines") or []) if _norm(value) == target)
        matches.extend([_is_tactical_block(block)] * occurrence_count)

    return bool(matches) and all(matches)


def _reconcile_week_warning(
    warning: dict[str, Any], *, counts_by_week: dict[int, int]
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
    if code in {"missing_week_session_role", "late_camp_session_incomplete"} and actual >= expected:
        return None
    if code == "weekly_session_overage" and actual <= expected:
        return None
    return {**warning, "actual_session_count": actual}


def _filter_warning(
    warning: dict[str, Any],
    *,
    planning_brief: dict[str, Any],
    final_plan_text: str,
    counts_by_week: dict[int, int],
) -> dict[str, Any] | None:
    warning = _reconcile_week_warning(warning, counts_by_week=counts_by_week)
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
    filtered_warnings: list[dict[str, Any]] = []
    for raw in validator_report.get("warnings") or []:
        if not isinstance(raw, dict):
            continue
        item = _filter_warning(
            raw,
            planning_brief=planning_brief,
            final_plan_text=final_plan_text,
            counts_by_week=counts_by_week,
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
