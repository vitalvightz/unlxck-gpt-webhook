"""Which planner role a structured-card session represents.

One identity rule, shared by every consumer that has to map a converted card
back onto Stage 1's roles:

* ``api/structured_plan_calendar_spine`` asks "is this scheduled role already on
  the day?" before restoring it;
* ``fightcamp/session_sequencing`` asks "which role is this session?" so the
  role's intent and any explicit ``sequence_override`` survive conversion.

Both must agree, otherwise one could treat a session as the role while the other
does not. The rule itself is unchanged from where it originated in the calendar
spine; it only lives here so both layers can import it.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def identity_tokens(value: Any) -> set[str]:
    return {token for token in _TOKEN_RE.split(str(value or "").lower()) if token}


def role_session_suffix(role: dict[str, Any]) -> str:
    """The ``session_index`` half of a deterministic session id, as it is built."""
    session_index = role.get("session_index")
    return str(session_index if isinstance(session_index, int) else 0)


def deterministic_session_id(role: dict[str, Any], d_day: int) -> str:
    role_key = str(role.get("role_key") or "").strip().lower()
    return f"deterministic-{d_day}-{role_key}-{role_session_suffix(role)}"


def representing_session_index(
    sessions: Sequence[Any], role: dict[str, Any], d_day: int, claimed: set[int]
) -> int | None:
    """Index of the session already representing ``role``, or ``None``.

    Identity is the role's own ``(d_day, role_key, session_index)`` — what the
    deterministic builder writes into ``session_id`` — falling back to the
    athlete-facing label for a converter session that was retitled but is still
    the same item.

    A session represents at most ONE role: ``claimed`` carries the indices
    already spoken for, so two roles that share a ``role_key`` on one day (two
    ``session_index`` values) do not collapse into one, with the second wrongly
    read as already present and dropped.

    Label matching is containment in either direction ("Joint Prep" vs "Joint
    Prep Flow"), never a count of shared words: "Technical Shadow Rhythm" and
    "Technical Shadow Boxing" overlap in two tokens and are different items.

    Returns ``-1`` when the role carries nothing to identify it by.
    """
    role_key = str(role.get("role_key") or "").strip().lower()
    label_tokens = identity_tokens(role.get("athlete_facing_label"))
    if not label_tokens and not role_key:
        return -1  # nothing to identify it by: never restore blind
    exact_id = deterministic_session_id(role, d_day)
    sessions = list(sessions or [])
    # The full deterministic identity wins over any looser signal, wherever it
    # sits in the day's list.
    for index, session in enumerate(sessions):
        if index in claimed or not isinstance(session, dict):
            continue
        if role_key and str(session.get("session_id") or "").lower() == exact_id:
            return index
    for index, session in enumerate(sessions):
        if index in claimed or not isinstance(session, dict):
            continue
        session_id = str(session.get("session_id") or "").lower()
        if role_key and role_key in session_id:
            return index
        title_tokens = identity_tokens(session.get("title"))
        if label_tokens and title_tokens and (
            label_tokens <= title_tokens or title_tokens <= label_tokens
        ):
            return index
    return None


def match_sessions_to_roles(
    sessions: Sequence[Any], roles: Sequence[dict[str, Any]], d_day: int
) -> dict[int, dict[str, Any]]:
    """Session index -> the one role it represents, for a whole day.

    Every role is first offered its strongest evidence across the whole day
    before any role falls back to looser evidence, so a broad label ("Strength")
    cannot claim a session that another role ("Neural speed touch") names
    exactly. Within each tier, ``representing_session_index``'s own rule and
    one-session-per-role claiming apply.
    """
    sessions = list(sessions or [])
    roles = [role for role in roles if isinstance(role, dict)]
    matched: dict[int, dict[str, Any]] = {}
    pending = list(roles)

    def claim(index: int | None, role: dict[str, Any]) -> bool:
        if index is None or index < 0 or index in matched:
            return False
        matched[index] = role
        return True

    # Tier 1: the exact deterministic id.
    remaining = []
    for role in pending:
        exact_id = deterministic_session_id(role, d_day)
        index = next(
            (
                i
                for i, session in enumerate(sessions)
                if i not in matched
                and isinstance(session, dict)
                and str(role.get("role_key") or "").strip()
                and str(session.get("session_id") or "").lower() == exact_id
            ),
            None,
        )
        if not claim(index, role):
            remaining.append(role)
    pending = remaining

    # Tier 2: the athlete-facing label is exactly the session title.
    remaining = []
    for role in pending:
        label = identity_tokens(role.get("athlete_facing_label"))
        index = next(
            (
                i
                for i, session in enumerate(sessions)
                if i not in matched
                and isinstance(session, dict)
                and label
                and identity_tokens(session.get("title")) == label
            ),
            None,
        )
        if not claim(index, role):
            remaining.append(role)
    pending = remaining

    # Tier 3: the shared representation rule (role key in id, label containment).
    for role in pending:
        claim(representing_session_index(sessions, role, d_day, set(matched)), role)
    return matched


__all__ = [
    "deterministic_session_id",
    "identity_tokens",
    "match_sessions_to_roles",
    "representing_session_index",
    "role_session_suffix",
]
