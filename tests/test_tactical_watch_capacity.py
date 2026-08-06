"""Bank-capacity + camp-uniqueness proof for the Tactical Watch library.

``calculate_phase_weeks`` decides how many GPP / SPP / TAPER weeks a camp has,
and the scheduler places exactly one Tactical Watch per phase week (drawing from
the athlete's style bank, then the generic bank). This test sweeps every
supported camp length, sport and style, and proves:

1. Each generic phase bank holds at least the maximum number of weeks that phase
   can ever carry — generic must work alone when the style is missing.
2. For every supported camp, selecting one watch per phase week (with the shared
   camp ledger, exactly as the scheduler does) yields all-unique keys *and*
   all-unique athlete-visible content, and never raises
   ``TacticalWatchBankExhausted``.
"""

from __future__ import annotations

import pytest

from fightcamp.camp_phases import calculate_phase_weeks
from fightcamp.tactical_watch_library import (
    PHASES,
    TacticalWatchBankExhausted,
    canonical_watch_signature,
    normalize_tactical_style,
    ordered_phase_bank,
    select_tactical_watch,
)

# The four sports calculate_phase_weeks has ratio tables for.
SPORTS = ("boxing", "muay_thai", "mma", "kickboxing")

# Raw intake styles covering: no style (generic must work alone), each tactical
# family, and the styles that shift week counts in calculate_phase_weeks
# (pressure fighter -> +SPP, counter striker -> +GPP, grappler/clinch -> +GPP/SPP).
STYLES = (
    None,
    "out-boxer",
    "distance striker",
    "brawler",
    "swarmer",
    "pressure fighter",
    "counter striker",
    "counter puncher",
    "grappler",
    "clinch fighter",
    "scrambler",
    "hybrid",
)

# Effective phase-block count is capped at 16, so camp lengths past that collapse
# onto the same ratios; 1..16 covers every distinct camp shape.
CAMP_LENGTHS = tuple(range(1, 17))
# Representative days_until_fight values: None (full camp) plus the thresholds
# that trigger the ultra-short / compressed / short-notice branches.
DAY_VALUES = (None, 6, 7, 10, 13, 14, 21)
# status=professional + low fatigue + no cut is the combination that pushes SPP
# to its maximum in the pro branch.
STATUSES = (None, "professional")
FATIGUES = (None, "low")


def _phase_weeks(sport, style, camp_length, days, status, fatigue):
    return calculate_phase_weeks(
        camp_length,
        sport,
        style=style,
        status=status,
        fatigue=fatigue,
        days_until_fight=days,
    )


def _iter_supported_camps():
    for sport in SPORTS:
        for style in STYLES:
            for days in DAY_VALUES:
                lengths = CAMP_LENGTHS if days is None else (max(1, (days + 6) // 7),)
                for camp_length in lengths:
                    for status in STATUSES:
                        for fatigue in FATIGUES:
                            weeks = _phase_weeks(
                                sport, style, camp_length, days, status, fatigue
                            )
                            yield sport, style, days, status, fatigue, weeks


def _select_camp_watches(family, weeks):
    """Mirror the scheduler: one watch per phase week, shared camp ledger."""
    used: set[str] = set()
    watches = []
    for phase in PHASES:  # GPP, SPP, TAPER in chronological order
        for _ in range(int(weeks.get(phase, 0))):
            watch = select_tactical_watch(family, phase, used)
            used.add(watch.key)
            watches.append(watch)
    return watches


def test_generic_banks_cover_the_maximum_phase_week_counts():
    max_weeks = {phase: 0 for phase in PHASES}
    for *_rest, weeks in _iter_supported_camps():
        for phase in PHASES:
            max_weeks[phase] = max(max_weeks[phase], int(weeks[phase]))

    # Sanity: the sweep really does exercise long camps (otherwise a trivial
    # sweep could pass without testing capacity).
    assert max_weeks["GPP"] >= 7
    assert max_weeks["SPP"] >= 9
    assert max_weeks["TAPER"] == 2  # hard-capped in calculate_phase_weeks

    # The binding invariant: generic must work alone when style is missing.
    for phase in PHASES:
        generic_capacity = len(ordered_phase_bank("generic", phase))
        assert generic_capacity >= max_weeks[phase], (
            f"generic {phase} bank has {generic_capacity} watches but a camp can "
            f"carry up to {max_weeks[phase]} {phase} weeks"
        )


def test_every_supported_camp_produces_unique_watches():
    checked = 0
    for sport, style, days, status, fatigue, weeks in _iter_supported_camps():
        family = normalize_tactical_style(style) if isinstance(style, str) else "generic"
        try:
            watches = _select_camp_watches(family, weeks)
        except TacticalWatchBankExhausted as exc:  # pragma: no cover - failure path
            pytest.fail(
                f"bank exhausted for sport={sport} style={style} days={days} "
                f"status={status} fatigue={fatigue} weeks={weeks}: {exc}"
            )
        keys = [w.key for w in watches]
        signatures = [canonical_watch_signature(w) for w in watches]
        context = (
            f"sport={sport} style={style} days={days} status={status} "
            f"fatigue={fatigue} weeks={weeks}"
        )
        assert len(keys) == len(set(keys)), f"duplicate watch key in camp: {context}"
        assert len(signatures) == len(set(signatures)), (
            f"duplicate visible content in camp: {context}"
        )
        checked += 1
    assert checked > 1000  # the sweep really ran a broad set of camps
