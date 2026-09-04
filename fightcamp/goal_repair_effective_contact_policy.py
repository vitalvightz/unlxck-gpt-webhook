from __future__ import annotations

from typing import Any

from .combat_load_policy import LoadClass, role_load_profile
from .normalization import clean_list

_STALE_REASON = "two_hard_spar_days"
_FREQUENCY_CONSUMING_LOADS = frozenset(
    {
        LoadClass.REDUCED_CONTACT,
        LoadClass.HARD_CONTACT,
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
    }
)


def _effective_hard_count_is_resolved_below_two(week: dict[str, Any]) -> bool:
    """Return True only when the week explicitly resolves to <2 hard contacts.

    Absence of ``effective_hard_sparring_days`` means the sparring-dose resolver
    has not supplied authority yet, so declared hard days remain fail-safe.
    An explicitly present empty/one-day list is authoritative.
    """
    if "effective_hard_sparring_days" not in week:
        return False
    return len(clean_list(week.get("effective_hard_sparring_days"))) < 2


def counts_toward_weekly_frequency(role: dict[str, Any]) -> bool:
    """Return whether a resolved role consumes one planned weekly-session slot.

    Calendar/load semantics are owned by ``combat_load_policy``. Goal repair must
    not rebuild those semantics from role labels/categories. Genuine hard/reduced
    contact and meaningful strength/conditioning consume the athlete's planned
    weekly frequency. Technical-only contact, neural microdoses, recovery, low-load
    work and zero-load support do not consume a full slot.

    Unknown non-filler roles fail safe and count. A camp-week filler is free unless
    canonical load authority independently classifies it as a genuine consuming
    load.
    """
    profile = role_load_profile(role)
    if profile is None:
        return not bool(role.get("camp_week_filler")) and role.get("category") != "support_insert"

    if profile.load_class in _FREQUENCY_CONSUMING_LOADS:
        return True

    if role.get("camp_week_filler"):
        return False

    return False


def resolved_weekly_frequency_count(roles: list[dict[str, Any]]) -> int:
    """Count genuine planned sessions from final resolved role semantics."""
    return sum(1 for role in roles if counts_toward_weekly_frequency(role))


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
