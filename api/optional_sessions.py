"""Which structured sessions the athlete may skip without missing anything.

The optional camp Fight Visualisation is offered, never required. A session is
optional only when the server says so: ``structured_plan_locked_merge`` sets
``optional: True`` on it and clears the field everywhere else, so the model
cannot make real training skippable.

Everything that decides what a day owes the athlete reads this one rule: the
Today day unit (its primary session, one log written across the day, "is the
day logged"), the training and adherence streaks, and week progress. An
optional session is therefore never written by another session's log, never
headlines Today, and never counts as planned work that was missed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def is_optional_session(session: Any) -> bool:
    return isinstance(session, Mapping) and session.get("optional") is True
