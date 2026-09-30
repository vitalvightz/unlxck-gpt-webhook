"""Pin every clock the planner reads, not just one of them.

Stage 1 gets "now" through two bindings of the same function:
``input_parsing._utc_now`` (days-out) and ``stage2_planning_brief._utc_now``
(the athlete's plan-creation weekday, via ``athlete_model``). Patching only the
first leaves the plan-creation weekday on the real clock, so the calendar
shifts by a day depending on when the suite runs.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from fightcamp import input_parsing
from fightcamp import stage2_planning_brief


def pin_planner_clock(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    """Make the planner believe it is ``now`` (naive UTC) everywhere."""
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: now)
    monkeypatch.setattr(stage2_planning_brief, "_utc_now", lambda: now)
