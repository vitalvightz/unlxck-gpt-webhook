"""Canonical bout-format demand model.

Single owner of the athlete's "<rounds> x <minutes>" intake string. Everything
that needs to know how long a round lasts, how many rounds the athlete is
scheduled to fight, or how much total fight work that adds up to, resolves it
here so there is exactly one parser in the codebase.

This module does not infer a format from amateur/pro status or assume a 3 x 3
default. It owns both the parsed facts and the deliberately conservative
planning modifiers derived from those facts; an unresolved format is reported
as ``None`` so callers keep their existing behaviour instead of planning
against a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "BASELINE_WORK_SECONDS",
    "BoutFormat",
    "bout_energy_modifiers",
    "bout_format_metadata",
    "parse_bout_format",
]

# The 3 x 3 bout the planner has always been tuned against, kept here purely as
# a neutral reference point for comparison. It is not a fallback.
BASELINE_WORK_SECONDS = 540.0

_BOUT_FORMAT_PATTERN = re.compile(r"^\s*(\d+)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*$")

_NEUTRAL_ENERGY_MODIFIERS = {
    "aerobic": 1.0,
    "glycolytic": 1.0,
    "alactic": 1.0,
}

# Planning weights, not physiological percentages. The explicit map keeps the
# supported formats auditable while retaining every energy system. Values are
# intentionally narrow: format shapes demand depth; it never dictates a
# session or scales training volume in proportion to total bout duration.
_KNOWN_ENERGY_MODIFIERS = {
    (3, 120.0): {"aerobic": 0.94, "glycolytic": 1.03, "alactic": 1.06},
    (3, 180.0): _NEUTRAL_ENERGY_MODIFIERS,
    (5, 180.0): {"aerobic": 1.08, "glycolytic": 1.03, "alactic": 0.96},
    (3, 300.0): {"aerobic": 1.10, "glycolytic": 1.06, "alactic": 0.94},
    (5, 300.0): {"aerobic": 1.18, "glycolytic": 1.05, "alactic": 0.90},
}

_MIN_ENERGY_MODIFIER = 0.90
_MAX_ENERGY_MODIFIER = 1.18


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

        A plain ratio of two measured durations. The modifier model deliberately
        does not scale linearly from this value.
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


def bout_energy_modifiers(bout: BoutFormat) -> dict[str, float]:
    """Return bounded energy-system planning weights for ``bout``.

    Known competition formats use an explicit mapping. Other valid formats use
    a small saturating adjustment from round duration and total scheduled work;
    the result is bounded to the same conservative range and deliberately does
    not scale linearly with total work.
    """
    known = _KNOWN_ENERGY_MODIFIERS.get((bout.rounds, bout.round_seconds))
    if known is not None:
        return dict(known)

    round_signal = max(-1.0, min(1.0, (bout.round_minutes - 3.0) / 2.0))
    work_signal = max(-1.0, min(1.0, (bout.total_work_minutes - 9.0) / 16.0))
    derived = {
        "aerobic": 1.0 + (0.06 * round_signal) + (0.12 * work_signal),
        "glycolytic": 1.0 + (0.05 * round_signal) + (0.03 * work_signal),
        "alactic": 1.0 - (0.04 * round_signal) - (0.06 * work_signal),
    }
    return {
        system: round(
            max(_MIN_ENERGY_MODIFIER, min(_MAX_ENERGY_MODIFIER, value)), 4
        )
        for system, value in derived.items()
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


def bout_format_metadata(rounds_format: str | None) -> dict[str, float | int]:
    """Metadata view of the intake string; empty when the format is unresolved.

    The parser still returns ``None`` for unresolved input. Metadata uses an
    empty mapping so it remains safe inside diagnostic containers whose values
    are expected to support ``len()`` and other mapping operations.
    """
    bout = parse_bout_format(rounds_format)
    return bout.as_metadata() if bout else {}
