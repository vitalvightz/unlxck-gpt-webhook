"""Goal-priority helpers for deterministic planning allocation.

Safety and phase guardrails remain authoritative. These helpers only break
otherwise-close capacity conflicts between performance intents so the athlete's
stated priorities decide which useful exposure survives when the calendar is
crowded.
"""

from __future__ import annotations

from typing import Any

from .normalization import clean_list


_STRENGTH_POWER_TOKENS = {
    "power",
    "explosive_power",
    "strength",
    "maximal_strength",
    "speed_strength",
    "strength_speed",
    "rate_of_force_development",
    "rfd",
}

_CONDITIONING_TOKENS = {
    "conditioning",
    "conditioning_endurance",
    "gas_tank",
    "endurance",
    "work_capacity",
    "aerobic",
    "repeatability",
    "late_fight",
    "late_round",
    "fight_pace",
}

_SPEED_TOKENS = {
    "speed",
    "explosiveness",
    "explosive",
    "alactic",
    "sharpness",
}


def _normalise_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _token_family(token: str) -> str | None:
    if token in _STRENGTH_POWER_TOKENS:
        return "strength"
    if token in _CONDITIONING_TOKENS:
        return "conditioning"
    if token in _SPEED_TOKENS:
        return "speed"
    return None


def goal_priority_scores(athlete_model: dict[str, Any]) -> dict[str, int]:
    """Return bounded intent scores derived from the athlete's stated priorities.

    Weighting is deliberately small and deterministic:
    primary goal > key goals > weaknesses. The result is intended as a tie-break
    signal only; it must never override safety suppression, must-keep rules, or
    phase survival constraints.
    """

    scores = {"strength": 0, "conditioning": 0, "speed": 0}

    primary = _normalise_token(athlete_model.get("primary_goal"))
    family = _token_family(primary)
    if family:
        scores[family] += 30

    for value in clean_list(
        athlete_model.get("key_goals")
        or athlete_model.get("goals")
        or athlete_model.get("performance_goals")
        or []
    ):
        family = _token_family(_normalise_token(value))
        if family:
            scores[family] += 10

    for value in clean_list(
        athlete_model.get("weaknesses")
        or athlete_model.get("weak_areas")
        or []
    ):
        family = _token_family(_normalise_token(value))
        if family:
            scores[family] += 4

    return scores


def role_goal_priority(role: dict[str, Any], athlete_model: dict[str, Any]) -> int:
    """Return the athlete-specific tie-break score for one performance role."""

    scores = goal_priority_scores(athlete_model)
    category = _normalise_token(role.get("category"))
    system = _normalise_token(role.get("preferred_system"))
    role_key = _normalise_token(role.get("role_key"))

    if category == "strength":
        return scores["strength"] + scores["speed"] // 3

    if category == "conditioning":
        # Conditioning goals should own scarce conditioning capacity. Speed is a
        # secondary signal only for genuinely alactic/sharpness work.
        score = scores["conditioning"]
        if system in {"alactic", "atp_pcr", "atp-pcr"} or "alactic" in role_key:
            score += scores["speed"] // 2
        return score

    return 0
