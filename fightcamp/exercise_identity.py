"""Canonical exercise identity, decided by the planner.

An exercise's identity is the normalized slug of its canonical bank name, the
same slug the exercise-media taxonomy keys videos on. It is stamped onto every
``selected_exercise_assignments`` entry when the planner creates it, so the
identity exists before any model renders the plan and cannot be lost when the
athlete-facing copy is rewritten. Dependency-free so both the planner and the
API can import it.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_exercise_key(name: Any) -> str:
    """Slug an exercise name without dropping any word of it.

    Only case, punctuation, accents and "&" are folded, so spelling drift still
    lands on one row ("Hollow-Body Hold" and "Hollow Body Hold"). Qualifiers are
    kept: "Box Jump (Max Height)" and "Box Jump (Stick Landing)" are different
    exercises and must never share a video. Two names that really are the same
    movement are joined by an explicit alias on the media row, not by the slug.

    "Romanian Deadlift (RDL)" -> "romanian-deadlift-rdl"
    "Clean & Press" -> "clean-and-press"
    """
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name).lower()).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ")
    return _NON_ALNUM_RE.sub("-", text).strip("-")


def stamp_exercise_key(assignment: dict[str, Any]) -> dict[str, Any]:
    """Set an assignment's ``exercise_key`` from its canonical bank name, in place."""
    key = normalize_exercise_key(assignment.get("name"))
    if key:
        assignment["exercise_key"] = key
    return assignment


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
