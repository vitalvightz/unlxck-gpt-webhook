"""Deterministically restore governed Tactical Watch fields in structured cards.

Stage 1 owns a banked Tactical Watch once its role governance marks the selected
drill as locked.  Structured conversion may enrich the surrounding card, but it
must not paraphrase those bank-owned fields.  This module only patches an exact
block on its authoritative countdown day; it never creates or moves structure.
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


def merge_locked_structured_content(
    structured_plan: dict[str, Any], planning_brief: Any
) -> LockedMergeResult:
    """Overwrite exact locked fields while preserving all AI-owned metadata.

    Resolution is deliberately narrow.  The authoritative day and an exact
    normalised block name must identify one existing target.  Missing, moved or
    renamed structure is reported and left untouched for faithfulness to reject.
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
        targets: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for session in matching_days[0].get("sessions") or []:
            if not isinstance(session, dict):
                continue
            for block in session.get("blocks") or []:
                if isinstance(block, dict) and _normalise(block.get("display_name")) in authoritative_names:
                    targets.append((session, block))
        if len(targets) != 1:
            result.unresolved.append(LockedMergeIssue(day_label, name, "locked block not uniquely resolved"))
            continue

        session, block = targets[0]
        mindset = watch.get("mindset")
        mindset = mindset if isinstance(mindset, Mapping) else {}
        anchor = session.get("mindset_anchor")
        anchor = dict(anchor) if isinstance(anchor, Mapping) else {}
        anchor.update(
            {
                "intent": mindset.get("intent"),
                "focus_cue": mindset.get("focus"),
                "reset_cue": mindset.get("reset"),
                "confidence_anchor": mindset.get("anchor"),
            }
        )
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
