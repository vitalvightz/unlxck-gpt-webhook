"""Canonical bout-format demand model.

Single owner of the athlete's "<rounds> x <minutes>" intake string. Everything
that needs to know how long a round lasts, how many rounds the athlete is
scheduled to fight, or how much total fight work that adds up to, resolves it
here so there is exactly one parser in the codebase.

This module states facts only. It does not infer a format from amateur/pro
status, does not assume a 3 x 3 default, and does not convert the demand into
energy-system modifiers — an unresolved format is reported as ``None`` so
callers keep their existing behaviour instead of planning against a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "BASELINE_WORK_SECONDS",
    "BoutFormat",
    "bout_format_metadata",
    "parse_bout_format",
]

# The 3 x 3 bout the planner has always been tuned against, kept here purely as
# a neutral reference point for comparison. It is not a fallback.
BASELINE_WORK_SECONDS = 540.0

_BOUT_FORMAT_PATTERN = re.compile(r"^\s*(\d+)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class BoutFormat:
    """Deterministic facts about the athlete's scheduled bout."""

    rounds: int
    round_seconds: float
    total_work_seconds: float

    @property
    def round_minutes(self) -> float:
        return self.round_seconds / 60.0

    @property
    def total_work_minutes(self) -> float:
        return self.total_work_seconds / 60.0

    @property
    def total_work_ratio_vs_baseline(self) -> float:
        """Total fight work relative to a 3 x 3 bout (540 sec).

        A plain ratio of two measured durations. It is deliberately not turned
        into an aerobic/glycolytic/alactic modifier here.
        """
        return self.total_work_seconds / BASELINE_WORK_SECONDS

    def as_metadata(self) -> dict[str, float | int]:
        """Planner metadata/debug view of the demand facts."""
        return {
            "rounds": self.rounds,
            "round_seconds": self.round_seconds,
            "total_work_seconds": self.total_work_seconds,
            "total_work_minutes": round(self.total_work_minutes, 4),
            "total_work_ratio_vs_3x3": round(self.total_work_ratio_vs_baseline, 4),
        }


def parse_bout_format(rounds_format: str | None) -> BoutFormat | None:
    """Parse the canonical intake string into a :class:`BoutFormat`.

    Returns ``None`` for anything that is not an explicit "<rounds> x <minutes>"
    value with positive rounds and positive minutes. Absent or malformed input
    is an unresolved format, never an assumed 3 x 3.
    """
    match = _BOUT_FORMAT_PATTERN.match(str(rounds_format or ""))
    if not match:
        return None
    rounds = int(match.group(1))
    minutes = float(match.group(2))
    if rounds <= 0 or minutes <= 0:
        return None
    round_seconds = minutes * 60.0
    return BoutFormat(
        rounds=rounds,
        round_seconds=round_seconds,
        total_work_seconds=round_seconds * rounds,
    )


def bout_format_metadata(rounds_format: str | None) -> dict[str, float | int] | None:
    """Metadata view straight from the intake string, or ``None`` if unresolved."""
    bout = parse_bout_format(rounds_format)
    return bout.as_metadata() if bout else None
