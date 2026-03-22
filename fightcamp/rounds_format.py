from __future__ import annotations

from dataclasses import dataclass
import re

_ROUNDS_FORMAT_PATTERN = re.compile(
    r"(?P<rounds>\d+)\s*(?:x|X|by|[-/])\s*(?P<minutes>\d+)",
    re.IGNORECASE,
)
_ROUND_MINUTE_PATTERN = re.compile(
    r"(?P<rounds>\d+)\s*(?:rounds?|rds?|r)\D+(?P<minutes>\d+)\s*(?:minutes?|mins?|min|m)\b",
    re.IGNORECASE,
)
_SPORT_ALIASES = {
    "boxer": "boxing",
    "boxing": "boxing",
    "mma": "mma",
    "muay thai": "muay_thai",
    "muay_thai": "muay_thai",
    "kickboxer": "kickboxing",
    "kickboxing": "kickboxing",
}
_SPORT_LIMITS = {
    "boxing": {"rounds": range(1, 13), "minutes": {2, 3}},
    "mma": {"rounds": range(1, 6), "minutes": {3, 5}},
    "muay_thai": {"rounds": range(1, 6), "minutes": {2, 3}},
    "kickboxing": {"rounds": range(1, 6), "minutes": {2, 3}},
}


@dataclass(frozen=True)
class RoundFormatAssessment:
    raw: str
    normalized: str
    rounds: int | None
    minutes: int | None
    warning: str | None = None


def canonicalize_rounds_format_sport(sport: str | None) -> str:
    normalized = str(sport or "").strip().lower()
    return _SPORT_ALIASES.get(normalized, normalized)


def parse_rounds_minutes(rounds_format: str | None) -> tuple[int | None, int | None]:
    normalized = str(rounds_format or "").strip()
    if not normalized:
        return None, None

    for pattern in (_ROUNDS_FORMAT_PATTERN, _ROUND_MINUTE_PATTERN):
        match = pattern.search(normalized)
        if match:
            return int(match.group("rounds")), int(match.group("minutes"))

    digits = [int(value) for value in re.findall(r"\d+", normalized)]
    if len(digits) >= 2:
        return digits[0], digits[1]
    return None, None


def _generic_bounds_ok(rounds: int, minutes: int) -> bool:
    return 1 <= rounds <= 12 and 1 <= minutes <= 10


def _sport_bounds_ok(*, sport: str, rounds: int, minutes: int) -> bool:
    limits = _SPORT_LIMITS.get(sport)
    if not limits:
        return True
    return rounds in limits["rounds"] and minutes in limits["minutes"]


def _sport_display_name(sport: str) -> str:
    return sport.replace("_", " ") if sport else "this sport"


def assess_rounds_format(
    rounds_format: str | None,
    *,
    sport: str | None = None,
) -> RoundFormatAssessment:
    raw = str(rounds_format or "").strip()
    rounds, minutes = parse_rounds_minutes(raw)
    normalized = f"{rounds}x{minutes}" if rounds is not None and minutes is not None else raw
    canonical_sport = canonicalize_rounds_format_sport(sport)

    if not raw:
        return RoundFormatAssessment(raw=raw, normalized=normalized, rounds=rounds, minutes=minutes)

    if rounds is None or minutes is None:
        return RoundFormatAssessment(
            raw=raw,
            normalized=normalized,
            rounds=rounds,
            minutes=minutes,
            warning=(
                f"Could not confidently interpret Rounds x Minutes value '{raw}'. "
                "Format-specific dose rules were skipped and the base planner was kept."
            ),
        )

    if not _generic_bounds_ok(rounds, minutes):
        return RoundFormatAssessment(
            raw=raw,
            normalized=normalized,
            rounds=rounds,
            minutes=minutes,
            warning=(
                f"Rounds x Minutes value '{raw}' was interpreted as '{normalized}', "
                "which is outside plausible fight-format bounds. "
                "Format-specific dose rules were skipped and the base planner was kept."
            ),
        )

    if canonical_sport and not _sport_bounds_ok(sport=canonical_sport, rounds=rounds, minutes=minutes):
        return RoundFormatAssessment(
            raw=raw,
            normalized=normalized,
            rounds=rounds,
            minutes=minutes,
            warning=(
                f"Rounds x Minutes value '{raw}' was interpreted as '{normalized}', "
                f"which is unusual for {_sport_display_name(canonical_sport)}. "
                "Format-specific dose rules were skipped and the base planner was kept."
            ),
        )

    return RoundFormatAssessment(raw=raw, normalized=normalized, rounds=rounds, minutes=minutes)
