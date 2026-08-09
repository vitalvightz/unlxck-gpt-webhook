"""Deterministically render governed Tactical Watch roles in structured cards.

Stage 1 owns a banked Tactical Watch once its role governance marks the selected
drill as locked. Structured conversion may enrich the surrounding card, but it
must not omit, rename, or paraphrase those bank-owned fields. The authoritative
countdown day must already exist; within that day this module repairs, moves, or
creates the Tactical Watch session and block without another model call.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class LockedMergeApplication:
    countdown_label: str
    block_name: str


@dataclass(frozen=True)
class LockedMergeIssue:
    countdown_label: str | None
    block_name: str
    reason: str


@dataclass
class LockedMergeResult:
    plan: dict[str, Any]
    applied: list[LockedMergeApplication] = field(default_factory=list)
    unresolved: list[LockedMergeIssue] = field(default_factory=list)


def _locked_roles(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        governance = value.get("governance")
        if isinstance(governance, Mapping) and governance.get("selected_drill_locked") is True:
            yield value
        for child in value.values():
            yield from _locked_roles(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _locked_roles(child)


def _normalise(value: Any) -> str:
    return " ".join(
        str(value or "")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .lower()
        .split()
    )


def _countdown(value: Any) -> str | None:
    match = re.search(r"D-\s*(\d+)", str(value or ""), re.IGNORECASE)
    return f"D-{int(match.group(1))}" if match else None


def _role_day(role: Mapping[str, Any]) -> str | None:
    # This is the same precedence used by the existing locked faithfulness path.
    for key in ("scheduled_countdown_label", "countdown_label", "countdown_display_label"):
        label = _countdown(role.get(key))
        if label:
            return label
    return None


def _days(plan: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    for week in plan.get("weeks") or []:
        if not isinstance(week, Mapping):
            continue
        for day in week.get("days") or []:
            if isinstance(day, dict):
                yield day


def _stable_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "watch"


def _mindset_anchor(watch: Mapping[str, Any]) -> dict[str, Any]:
    mindset = watch.get("mindset")
    mindset = mindset if isinstance(mindset, Mapping) else {}
    return {
        "intent": str(mindset.get("intent") or "Review the tactical plan."),
        "focus_cue": str(mindset.get("focus") or "Stay with the planned sequence."),
        "reset_cue": str(mindset.get("reset") or "Reset and return to the plan."),
        "confidence_anchor": mindset.get("anchor"),
    }


def _new_watch_block(
    *, day_label: str, name: str, watch: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "block_id": f"locked-{_stable_id(day_label)}-{_stable_id(name)}",
        "block_type": "mindset",
        "display_name": name,
        "duration": {"value": watch.get("duration_min") or 1, "unit": "minutes"},
        "coaching_cues": [],
        "regression_options": [],
        "substitutions": [],
    }


def _new_watch_session(
    *,
    day_label: str,
    title: str,
    name: str,
    watch: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "session_id": f"locked-{_stable_id(day_label)}-tactical-watch",
        "session_type": "skill",
        "title": title,
        "objective": str(watch.get("why") or "Review the tactical plan."),
        "completion_status": "not_started",
        "mindset_anchor": _mindset_anchor(watch),
        "blocks": [_new_watch_block(day_label=day_label, name=name, watch=watch)],
    }


def merge_locked_structured_content(
    structured_plan: dict[str, Any], planning_brief: Any
) -> LockedMergeResult:
    """Apply locked fields on their authoritative day.

    Day placement stays fail-closed: a missing or ambiguous countdown day is
    unresolved. Inside that verified day, Stage 1 is authoritative, so harmless
    converter drift (renamed/moved/missing Tactical Watch structure) is repaired
    deterministically instead of rejecting the entire athlete card.
    """
    plan = copy.deepcopy(structured_plan)
    result = LockedMergeResult(plan=plan)
    if not isinstance(planning_brief, Mapping):
        return result

    for role in _locked_roles(planning_brief):
        governance = role.get("governance")
        governance = governance if isinstance(governance, Mapping) else {}
        watch = role.get("tactical_watch")
        watch = watch if isinstance(watch, Mapping) else None
        name = str(
            governance.get("selected_drill_name")
            or (watch or {}).get("name")
            or "locked drill"
        )
        day_label = _role_day(role)
        if watch is None:
            result.unresolved.append(LockedMergeIssue(day_label, name, "missing tactical_watch metadata"))
            continue
        if day_label is None:
            result.unresolved.append(LockedMergeIssue(None, name, "missing authoritative countdown label"))
            continue

        matching_days = [day for day in _days(plan) if _countdown(day.get("countdown_label")) == day_label]
        if len(matching_days) != 1:
            result.unresolved.append(LockedMergeIssue(day_label, name, "structured day not uniquely resolved"))
            continue

        authoritative_names = {
            _normalise(governance.get("selected_drill_name")),
            _normalise(watch.get("name")),
        } - {""}
        sessions = [
            session
            for session in matching_days[0].get("sessions") or []
            if isinstance(session, dict)
        ]
        display_title = str(role.get("athlete_facing_label") or "Fight Tactical Watch")
        session_title = _normalise(display_title)
        watch_sessions = [
            session
            for session in sessions
            if _normalise(session.get("title")) == session_title
        ]
        if len(watch_sessions) > 1:
            result.unresolved.append(
                LockedMergeIssue(
                    day_label,
                    name,
                    "Tactical Watch session not uniquely resolved",
                )
            )
            continue

        targets = [
            (session, block)
            for session in sessions
            for block in session.get("blocks") or []
            if isinstance(block, dict)
            and _normalise(block.get("display_name")) in authoritative_names
        ]
        if len(targets) > 1:
            result.unresolved.append(
                LockedMergeIssue(day_label, name, "locked block not uniquely resolved")
            )
            continue

        if watch_sessions:
            session = watch_sessions[0]
        elif targets:
            # Keep unrelated same-day work intact. Create the governed session,
            # then move only the authoritative block into it below.
            session = _new_watch_session(
                day_label=day_label,
                title=display_title,
                name=name,
                watch=watch,
            )
            session["blocks"] = []
            matching_days[0].setdefault("sessions", []).append(session)
            sessions.append(session)
        else:
            session = _new_watch_session(
                day_label=day_label,
                title=display_title,
                name=name,
                watch=watch,
            )
            matching_days[0].setdefault("sessions", []).append(session)
            sessions.append(session)

        if targets:
            owner, block = targets[0]
            if owner is not session:
                owner["blocks"] = [item for item in owner.get("blocks") or [] if item is not block]
                session.setdefault("blocks", []).append(block)
        else:
            candidates = [
                block
                for block in session.get("blocks") or []
                if isinstance(block, dict) and block.get("block_type") == "mindset"
            ]
            if len(candidates) == 1:
                block = candidates[0]
            else:
                block = _new_watch_block(day_label=day_label, name=name, watch=watch)
                session.setdefault("blocks", []).append(block)

        mindset = watch.get("mindset")
        mindset = mindset if isinstance(mindset, Mapping) else {}
        anchor = _mindset_anchor(watch)
        session["objective"] = watch.get("why")
        session["mindset_anchor"] = anchor
        block.update(
            {
                "display_name": watch.get("name") or governance.get("selected_drill_name"),
                "duration": {"value": watch.get("duration_min"), "unit": "minutes"},
                "coaching_cues": list(watch.get("instructions") or []),
                "purpose": mindset.get("context"),
                "progression_rule": watch.get("progress"),
            }
        )
        result.applied.append(LockedMergeApplication(day_label, str(block["display_name"])))

    return result
