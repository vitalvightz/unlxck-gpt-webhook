from __future__ import annotations

from typing import Any

from .normalization import clean_list

_STALE_BELOW_TWO = {"two_hard_spar_days"}
_STALE_AT_ZERO = {"spar_first_cap"}


def _resolved_effective_hard_count(week: dict[str, Any]) -> int | None:
    """Return authoritative effective hard-contact count when resolver state exists."""
    if "effective_hard_sparring_days" not in week:
        return None
    return len(clean_list(week.get("effective_hard_sparring_days")))


def _effective_hard_count_is_resolved_below_two(week: dict[str, Any]) -> bool:
    """Return True only when resolved effective contact is explicitly below two."""
    count = _resolved_effective_hard_count(week)
    return count is not None and count < 2


def effective_goal_repair_compression_state(
    week: dict[str, Any],
    suppressed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Return live compression authority for goal repair without mutating planner state.

    Contact-derived compression is only authoritative while the resolved contact
    state still supports it. ``two_hard_spar_days`` becomes stale below two
    effective hard contacts. ``spar_first_cap`` becomes stale when the resolver
    explicitly proves there are zero effective hard contacts. Other readiness,
    cut, injury, proximity, and calendar reasons remain authoritative.
    """
    compression = dict(week.get("intentional_compression") or {})
    compression_codes = [str(code) for code in clean_list(compression.get("reason_codes"))]
    for row in suppressed:
        compression_codes.extend(str(code) for code in clean_list(row.get("compression_reason_codes")))

    effective_hard_count = _resolved_effective_hard_count(week)
    stale_codes: set[str] = set()
    if effective_hard_count is not None and effective_hard_count < 2:
        stale_codes.update(_STALE_BELOW_TWO)
    if effective_hard_count == 0:
        stale_codes.update(_STALE_AT_ZERO)

    if stale_codes:
        compression_codes = [code for code in compression_codes if code not in stale_codes]
        own_codes = [
            str(code)
            for code in clean_list(compression.get("reason_codes"))
            if str(code) not in stale_codes
        ]
        compression["reason_codes"] = own_codes
        if compression.get("active") and not own_codes:
            compression["active"] = False

    return compression, compression_codes
