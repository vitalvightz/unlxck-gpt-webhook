"""Which structured sessions the athlete may skip without missing anything.

Planner mental support inserts, camp Fight Visualisation and athlete-added custom recovery are offered,
never required. A session is
optional only when the server says so: ``structured_plan_locked_merge`` sets
``optional: True`` on these trusted sessions and clears the field elsewhere, so the model
cannot make real training skippable.

Everything that decides what a day owes the athlete reads this one rule: the
Today day unit (its primary session, one log written across the day, "is the
day logged"), the training and adherence streaks, and week progress. An
optional session is therefore never written by another session's log, never
headlines Today, and never counts as planned work that was missed.
"""

from __future__ import annotations

import re

from collections.abc import Mapping
from typing import Any


def is_optional_session(session: Any) -> bool:
    return isinstance(session, Mapping) and session.get("optional") is True


def mark_optional_support_inserts(plan: dict, planning_brief: Mapping) -> None:
    """Trusted mental support is offered, never owed, even when placement is locked.

    Match one standalone session on the role's authoritative day; never make a
    mixed physical session optional. Placement requirements govern scheduling,
    not athlete completion or adherence.
    """
    names = {
        "neural_visualization": {"neural visualisation", "neural visualization"},
        "fight_visualization": {"fight visualisation", "fight visualization"},
        "self_review": {"self-review cues", "self review cues"},
        "breathing_reset": {"breathing reset"},
        "tactical_watch": {"fight tactical watch", "tactical watch", "tactical focus"},
    }
    role_map = planning_brief.get("weekly_role_map") or {}
    weeks = [*(planning_brief.get("weeks") or []), *(role_map.get("weeks") or [])]
    for week in weeks:
        for role in week.get("session_roles") or []:
            key = role.get("role_key")
            governance = role.get("governance") or {}
            if (key not in names or role.get("category") != "support_insert"
                    or governance.get("authority") not in {"gap_fill_support_insert", "camp_week_support_insert", "fight_visualization_library", "late_fight_tail_allocator"}
                    or (key == "breathing_reset" and (role.get("optional") is False or governance.get("mandatory")))):
                continue
            label = role.get("scheduled_countdown_label") or role.get("countdown_label")
            role_day = re.match(r"D-\d+", str(label or ""))
            if not role_day:
                continue
            for plan_week in plan.get("weeks") or []:
                for day in plan_week.get("days") or []:
                    day_label = re.match(r"D-\d+", str(day.get("countdown_label") or ""))
                    if not day_label or day_label.group() != role_day.group():
                        continue
                    candidates = [session for session in day.get("sessions") or []
                                  if str(session.get("title") or "").strip().lower() in names[key]]
                    if len(candidates) != 1:
                        continue
                    session = candidates[0]
                    allowed_types = {"mindset", "skill", "recovery"} if key == "breathing_reset" else {"mindset", "skill"}
                    if session.get("session_type") not in allowed_types:
                        continue
                    allowed_blocks = {None, "mindset"}
                    if key == "breathing_reset":
                        allowed_blocks.add("recovery")
                    def support_block(block):
                        if block.get("exercise_key"):
                            return False
                        if block.get("block_type") in allowed_blocks:
                            return True
                        # Older converters use skill for a standalone mental task.
                        return (block.get("block_type") == "skill"
                                and str(block.get("display_name") or "").strip().lower() in names[key])

                    if not all(support_block(block) for block in session.get("blocks") or []):
                        continue
                    session["optional"] = True
