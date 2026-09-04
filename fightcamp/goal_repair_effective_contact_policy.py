from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any

from .normalization import clean_list

_STALE_REASON = "two_hard_spar_days"
_INSTALLED_FLAG = "_EFFECTIVE_CONTACT_GOAL_REPAIR_POLICY_INSTALLED"


def _effective_hard_count_is_resolved_below_two(week: dict[str, Any]) -> bool:
    """Return True only when the week explicitly resolves to <2 hard contacts.

    Absence of ``effective_hard_sparring_days`` means the sparring-dose resolver
    has not supplied authority yet, so declared hard days must remain fail-safe.
    An explicitly present empty/one-day list is authoritative and must not be
    overwritten by stale declared-day compression metadata.
    """

    if "effective_hard_sparring_days" not in week:
        return False
    return len(clean_list(week.get("effective_hard_sparring_days"))) < 2


def clear_stale_two_hard_spar_authority(brief: dict[str, Any]) -> dict[str, Any]:
    """Remove only stale ``two_hard_spar_days`` goal-repair authority.

    The sparring-dose planner owns effective hard-contact semantics. Some weeks
    retain compression/suppression metadata that was calculated from the two
    originally declared hard-sparring days even after one or both sessions are
    downgraded to technical contact. Goal-preservation repair then sees the stale
    reason and exits before consulting the canonical calendar legality view.

    This function is deliberately narrow:
    - it acts only when an explicit effective-hard list exists and contains <2 days;
    - it removes only ``two_hard_spar_days``;
    - all other compression, governance, safety and calendar reasons survive;
    - an active compression flag is cleared only when the stale reason was the
      sole encoded compression authority for that week.
    """

    role_map = brief.get("weekly_role_map")
    if not isinstance(role_map, dict):
        return brief

    for week in role_map.get("weeks") or []:
        if not isinstance(week, dict) or not _effective_hard_count_is_resolved_below_two(week):
            continue

        compression = week.get("intentional_compression")
        if isinstance(compression, dict):
            original_codes = [str(code) for code in clean_list(compression.get("reason_codes"))]
            filtered_codes = [code for code in original_codes if code != _STALE_REASON]
            stale_removed = len(filtered_codes) != len(original_codes)
            if stale_removed:
                compression["reason_codes"] = filtered_codes
                if compression.get("active") and not filtered_codes:
                    compression["active"] = False
                    compression["reason"] = ""
                    compression["summary"] = ""

        for row in week.get("suppressed_roles") or []:
            if not isinstance(row, dict):
                continue
            original_codes = [str(code) for code in clean_list(row.get("compression_reason_codes"))]
            if _STALE_REASON in original_codes:
                row["compression_reason_codes"] = [
                    code for code in original_codes if code != _STALE_REASON
                ]

    return brief


def install() -> None:
    """Install effective-contact normalization at the goal-repair boundary."""

    from . import goal_preservation as goal_preservation_module

    if getattr(goal_preservation_module, _INSTALLED_FLAG, False):
        return

    original_restore = goal_preservation_module._restore_goal_roles

    @wraps(original_restore)
    def _restore_goal_roles(brief: dict, entry: dict) -> list[dict]:
        clear_stale_two_hard_spar_authority(brief)
        return original_restore(brief, entry)

    goal_preservation_module._restore_goal_roles = _restore_goal_roles
    setattr(goal_preservation_module, _INSTALLED_FLAG, True)
