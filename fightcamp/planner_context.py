from __future__ import annotations

from contextvars import ContextVar
from typing import Any


planner_athlete_model_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "planner_athlete_model_context",
    default=None,
)


def get_planner_athlete_model() -> dict[str, Any] | None:
    value = planner_athlete_model_context.get()
    return value if isinstance(value, dict) else None
