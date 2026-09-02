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


def _norm(value: Any) -> str:
    return re.sub(r"[*_`]+", "", str(value or "")).strip().lower()


def _session_blocks(final_plan_text: str) -> list[dict[str, Any]]:
    """Return canonical D-X athlete-facing session blocks.

    Multiple sessions can share one D-day, so each rendered D-X heading starts a
    new block. D-0 is retained for context but excluded from active week counts.
    """

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
                "header": line,
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


def _roles_by_phase(planning_brief: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    weekly_role_map = planning_brief.get("weekly_role_map") or {}
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for week in weekly_role_map.get("weeks") or []:
        if not isinstance(week, dict):
            continue
        phase = str(week.get("phase") or "").strip().upper()
        if not phase:
            continue
        out[phase].extend(
            role
            for role in (week.get("session_roles") or [])
            if isinstance(role, dict)
        )
    return dict(out)


def _is_strength_role(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()
    return category == "strength" or "strength" in role_key


def _is_live_glycolytic_role(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip().lower()
    label = " ".join(
        str(role.get(key) or "").strip().lower()
        for key in ("athlete_facing_label", "label", "session_role_label")
    )
    # Countdown morphs intentionally replace hard fight-pace work with a
    # low-cost rhythm touch. Stale preferred_system metadata must not resurrect
    # the original glycolytic requirement after that morph.
    if any(token in role_key or token in label for token in ("light_fight_pace", "rhythm", "flush")):
        return False
    preferred_system = str(role.get("preferred_system") or "").strip().lower()
    if preferred_system == "glycolytic":
        return True
    return "glycolytic" in role_key or "fight_pace" in role_key


def _requirement_survives_final_role_map(
    planning_brief: dict[str, Any],
    *,
    phase: str,
    requirement: str,
) -> bool | None:
    roles_by_phase = _roles_by_phase(planning_brief)
    if not roles_by_phase:
        return None
    roles = roles_by_phase.get(str(phase or "").strip().upper())
    if roles is None:
        return None

    requirement = str(requirement or "").strip().lower()
    if requirement == "primary_strength":
        return any(_is_strength_role(role) for role in roles)
    if requirement == "extra_strength_accessory":
        return sum(1 for role in roles if _is_strength_role(role)) >= 2
    if requirement == "aerobic":
        return any(
            str(role.get("preferred_system") or "").strip().lower() == "aerobic"
            or "aerobic" in str(role.get("role_key") or "").lower()
            for role in roles
        )
    if requirement == "glycolytic":
        return any(_is_live_glycolytic_role(role) for role in roles)
    if requirement == "alactic":
        return any(
            str(role.get("preferred_system") or "").strip().lower() == "alactic"
            or any(
                token in str(role.get("role_key") or "").lower()
                for token in ("alactic", "sharpness", "neural_speed", "primer")
            )
            for role in roles
        )
    if requirement == "rehab":
        return any(
            str(role.get("category") or "").strip().lower() == "rehab"
            or "rehab" in str(role.get("role_key") or "").lower()
            for role in roles
        )
    return None


def _is_legitimate_tactical_anchor(final_plan_text: str, line: str) -> bool:
    target = _norm(line)
    if not target.startswith("anchor:"):
        return False

    for block in _session_blocks(final_plan_text):
        title = _norm(block.get("title"))
        body = [_norm(value) for value in block.get("lines") or []]
        tactical = "tactical watch" in title or any("tactical review only" in value for value in body)
        if tactical and target in body:
            return True
    return False


def _reconcile_week_warning(
    warning: dict[str, Any],
    *,
    counts_by_week: dict[int, int],
) -> dict[str, Any] | None:
    code = str(warning.get("code") or "")
    if code not in _WEEK_COMPLETENESS_CODES:
        return warning
    try:
        week_index = int(warning.get("week_index"))
    except (TypeError, ValueError):
        return warning
    if week_index not in counts_by_week:
        return warning

    actual = counts_by_week[week_index]
    try:
        expected = int(warning.get("expected_session_count"))
    except (TypeError, ValueError):
        expected = None

    if expected is not None:
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
    code = str(warning.get("code") or "")

    reconciled = _reconcile_week_warning(warning, counts_by_week=counts_by_week)
    if reconciled is None:
        return None
    warning = reconciled

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
    """Reconcile validator findings against final calendar/render authority.

    The validator intentionally contains broad lexical checks. This pass removes
    three known representation false positives using deterministic final state:

    * countdown session headings are counted from the athlete-facing D-X format;
    * original phase must-keep requirements are ignored once the final role map
      has legitimately morphed/suppressed them;
    * ``Anchor:`` is allowed only inside a canonical Tactical Watch block.

    Genuine missing sessions, surviving requirements and non-tactical internal
    labels remain untouched.
    """

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

    # Keep validator diagnostic buckets consistent with the authoritative
    # warning list. Stage2_pipeline will rebuild blocking/review buckets next.
    result["week_completeness_warnings"] = [
        item for item in filtered_warnings if str(item.get("code") or "") in _WEEK_COMPLETENESS_CODES
    ]
    result["internal_render_contract_leak_warnings"] = [
        item for item in filtered_warnings if item.get("code") == "internal_render_contract_leak"
    ]

    original_missing = validator_report.get("missing_required_elements") or []
    result["missing_required_elements"] = [
        item
        for item in original_missing
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
