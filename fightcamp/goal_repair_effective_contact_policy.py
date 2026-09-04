from __future__ import annotations

from typing import Any

from .normalization import clean_list

_STALE_REASON = "two_hard_spar_days"


def _effective_hard_count_is_resolved_below_two(week: dict[str, Any]) -> bool:
    """Return True only when the week explicitly resolves to <2 hard contacts.

    Absence of ``effective_hard_sparring_days`` means the sparring-dose resolver
    has not supplied authority yet, so declared hard days remain fail-safe.
    An explicitly present empty/one-day list is authoritative.
    """
    if "effective_hard_sparring_days" not in week:
        return False
    return len(clean_list(week.get("effective_hard_sparring_days"))) < 2


def effective_goal_repair_compression_state(
    week: dict[str, Any],
    suppressed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Return live compression authority for goal repair without mutating planner state.

    ``two_hard_spar_days`` is ignored only when resolved effective-contact state
    explicitly proves that fewer than two hard contacts remain. Every other
    compression and governance reason stays authoritative.
    """
    compression = dict(week.get("intentional_compression") or {})
    compression_codes = [str(code) for code in clean_list(compression.get("reason_codes"))]
    for row in suppressed:
        compression_codes.extend(str(code) for code in clean_list(row.get("compression_reason_codes")))

    if _effective_hard_count_is_resolved_below_two(week):
        compression_codes = [code for code in compression_codes if code != _STALE_REASON]
        own_codes = [
            str(code)
            for code in clean_list(compression.get("reason_codes"))
            if str(code) != _STALE_REASON
        ]
        compression["reason_codes"] = own_codes
        if compression.get("active") and not own_codes:
            compression["active"] = False

    return compression, compression_codes
