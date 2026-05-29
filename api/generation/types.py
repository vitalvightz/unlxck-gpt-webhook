"""Shared type aliases for the generation runtime modules."""
from __future__ import annotations

from typing import Any, Callable

Planner = Callable[..., dict[str, Any]]
ProgressCallback = Callable[[str, str, str, dict[str, Any]], None]
