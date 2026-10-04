"""Deterministic exercise identity for gap-fill support inserts.

Dependency-free so the API's exercise-identity reconciler can import it without
pulling in the planner.
"""

from __future__ import annotations

from typing import Any


# Canonical exercise identity (exercise-media taxonomy slug) for support
# inserts that prescribe one known physical movement. Keyed on the role AND its
# athlete-facing label, because a role key alone is not a movement: the generic
# "Aerobic Movement Flow" is any sport-specific solo movement, while the boxing
# label "Shadowboxing Aerobic Flow" is exactly tempo shadowboxing. A role or
# label absent here (walk/jog/footwork flushes, mobility, breathing, tactical
# and visualisation content) has no deterministic video and stays unkeyed.
_SUPPORT_INSERT_EXERCISE_KEYS: dict[tuple[str, str], str] = {
    ("aerobic_shadow_flow", "Shadowboxing Aerobic Flow"): "tempo-shadowboxing",
    ("aerobic_skip_flush", "Light Skipping Flush"): "jump-rope-recovery-pace",
}


def support_insert_exercise_key(role_key: Any, label: Any) -> str | None:
    """The deterministic exercise identity of a support insert, or None."""
    return _SUPPORT_INSERT_EXERCISE_KEYS.get(
        (str(role_key or "").strip(), str(label or "").strip())
    )
