"""Deterministically render governed banked roles in structured cards.

Stage 1 owns a banked prescription once its role governance marks the selected
drill as locked. Structured conversion may enrich the surrounding card, but it
must not omit, rename, or paraphrase those bank-owned fields. The authoritative
countdown day must already exist; within that day this module repairs, moves, or
creates the governed session and block without another model call.

Two banked systems share this pathway (see ``_LOCKED_CONTENT_SPECS``): the
Tactical Watch and the Fight Visualisation countdown protocol. They differ only
in which role field carries the bank object, the fixed session title, and how the
bank record's own fields map onto the card's block -- so the repair, move and
create logic below is written once and driven by that spec.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .structured_plan_sparring_reconcile import reconcile_coach_led_sparring_days


@dataclass(frozen=True)
class LockedContentSpec:
    """How one banked system projects onto a structured card."""

    content_field: str
    session_title: str
    session_slug: str
    session_type: str
    block_type: str


# Order is precedence: a role carrying more than one bank object (never expected)
# resolves to the first match, deterministically.
_LOCKED_CONTENT_SPECS = (
    LockedContentSpec(
        content_field="tactical_watch",
        session_title="Tactical Focus",
        session_slug="tactical-watch",
        session_type="skill",
        block_type="mindset",
    ),
    LockedContentSpec(
        content_field="fight_visualization",
        session_title="Fight Visualisation",
        session_slug="fight-visualization",
        session_type="skill",
        block_type="mindset",
    ),
)


def _spec_for_role(role: Mapping[str, Any]) -> tuple[LockedContentSpec, Mapping[str, Any]] | None:
    for spec in _LOCKED_CONTENT_SPECS:
        content = role.get(spec.content_field)
        if isinstance(content, Mapping):
            return spec, content
    return None


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


def _duration(content: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise the bank's duration onto the card's single-value shape.

    The Tactical Watch bank stores one integer; the Fight Visualisation bank
    stores a ``[min, max]`` range. A card shows one number, so a range renders
    at its upper bound -- the dose the athlete plans the day around.
    """
    raw = content.get("duration_min")
    if isinstance(raw, (list, tuple)) and raw:
        value = raw[-1]
    else:
        value = raw
    return {"value": value if isinstance(value, int) else 1, "unit": "minutes"}


def _mindset_anchor(content: Mapping[str, Any]) -> dict[str, Any]:
    """The card's coaching lines, one distinct claim per slot.

    A Tactical Watch carries a real four-part mindset block. The Fight
    Visualisation bank carries a single trusted ``cue`` instead, and filling
    every slot with it printed that one sentence three times on the card
    ("Focus", "Reset" and "Coach cue" all reading "Take the space, do not chase
    it."). A single cue is a single cue: it fills the coach-cue slot and the
    others stay empty rather than repeating it or inventing generic filler.
    """
    mindset = content.get("mindset")
    mindset = mindset if isinstance(mindset, Mapping) else {}
    cue = str(content.get("cue") or "").strip()
    intent = str(mindset.get("intent") or "").strip()
    focus = str(mindset.get("focus") or "").strip()
    reset = str(mindset.get("reset") or "").strip()
    anchor = str(mindset.get("anchor") or "").strip()
    if not (intent or focus or reset or anchor):
        return {
            "intent": cue,
            "focus_cue": "",
            "reset_cue": "",
            "confidence_anchor": None,
        }
    return {
        "intent": intent or cue,
        "focus_cue": focus,
        "reset_cue": reset,
        "confidence_anchor": anchor or None,
    }


def _new_watch_block(
    *, day_label: str, name: str, watch: Mapping[str, Any], spec: LockedContentSpec
) -> dict[str, Any]:
    return {
        "block_id": f"locked-{_stable_id(day_label)}-{_stable_id(name)}",
        "block_type": spec.block_type,
        "display_name": name,
        "duration": _duration(watch),
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
    spec: LockedContentSpec,
) -> dict[str, Any]:
    return {
        "session_id": f"locked-{_stable_id(day_label)}-{spec.session_slug}",
        "session_type": spec.session_type,
        "title": title,
        "objective": str(watch.get("why") or "Review the tactical plan."),
        "completion_status": "not_started",
        "mindset_anchor": _mindset_anchor(watch),
        "blocks": [],
    }


def _is_safe_named_watch_shell(
    session: Mapping[str, Any], authoritative_names: set[str]
) -> bool:
    """Return whether a drill-titled session can safely become the Watch.

    The structured converter occasionally emits the locked drill name as its
    own otherwise-empty session. It is the same governed content, not a second
    athlete session. Only reuse or remove that shell when it has not been
    started and carries no independent blocks.
    """
    completion_status = _normalise(session.get("completion_status"))
    if completion_status not in {"", "not_started", "not started"}:
        return False

    blocks = session.get("blocks") or []
    return isinstance(blocks, list) and all(
        isinstance(block, Mapping)
        and _normalise(block.get("display_name")) in authoritative_names
        for block in blocks
    )


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
        resolved = _spec_for_role(role)
        spec, watch = resolved if resolved is not None else (None, None)
        name = str(
            governance.get("selected_drill_name")
            or (watch or {}).get("name")
            or "locked drill"
        )
        day_label = _role_day(role)
        if watch is None or spec is None:
            result.unresolved.append(
                LockedMergeIssue(day_label, name, "missing locked bank metadata")
            )
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
        # This is fixed product copy. The selected drill is the card's block,
        # never an alternate session title supplied by structured conversion.
        display_title = spec.session_title
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
                    f"{spec.session_title} session not uniquely resolved",
                )
            )
            continue

        named_watch_sessions = [
            session
            for session in sessions
            if _normalise(session.get("title")) in authoritative_names
            and _normalise(session.get("title")) != session_title
        ]
        if len(named_watch_sessions) > 1:
            result.unresolved.append(
                LockedMergeIssue(
                    day_label,
                    name,
                    f"named {spec.session_title} session not uniquely resolved",
                )
            )
            continue
        named_watch_session = named_watch_sessions[0] if named_watch_sessions else None
        reusable_named_watch = (
            named_watch_session
            if named_watch_session
            and _is_safe_named_watch_shell(named_watch_session, authoritative_names)
            else None
        )

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
        elif reusable_named_watch:
            # The converter used the locked drill name as the session title.
            # Reuse it as the canonical Watch instead of creating a twin card.
            session = reusable_named_watch
        elif targets:
            # Keep unrelated same-day work intact. Create the governed session,
            # then move only the authoritative block into it below.
            session = _new_watch_session(
                day_label=day_label,
                title=display_title,
                name=name,
                watch=watch,
                spec=spec,
            )
            matching_days[0].setdefault("sessions", []).append(session)
            sessions.append(session)
        else:
            session = _new_watch_session(
                day_label=day_label,
                title=display_title,
                name=name,
                watch=watch,
                spec=spec,
            )
            matching_days[0].setdefault("sessions", []).append(session)
            sessions.append(session)

        if targets:
            owner, block = targets[0]
            if owner is not session:
                owner["blocks"] = [item for item in owner.get("blocks") or [] if item is not block]
                session.setdefault("blocks", []).append(block)
        else:
            # A generic mindset block is not proof that it represents this
            # governed drill. Preserve ambiguous/unrelated content and append
            # the authoritative block instead of destructively repurposing it.
            block = _new_watch_block(
                day_label=day_label, name=name, watch=watch, spec=spec
            )
            session.setdefault("blocks", []).append(block)

        mindset = watch.get("mindset")
        mindset = mindset if isinstance(mindset, Mapping) else {}
        anchor = _mindset_anchor(watch)
        session["title"] = display_title
        session["objective"] = watch.get("why")
        session["mindset_anchor"] = anchor
        # ``coaching_cues`` carries the bank's instructions. The Fight
        # Visualisation bank's trusted ``cue`` (and its optional immediate
        # pre-bout version) are part of the prescription, so they ride along
        # rather than being dropped on the floor.
        coaching_cues = [str(value) for value in watch.get("instructions") or []]
        for extra_field, prefix in (("cue", "Cue"), ("pre_bout", "Pre-bout")):
            extra = str(watch.get(extra_field) or "").strip()
            if extra:
                coaching_cues.append(f"{prefix}: {extra}")
        block.update(
            {
                "display_name": watch.get("name") or governance.get("selected_drill_name"),
                "duration": _duration(watch),
                "coaching_cues": coaching_cues,
                "purpose": mindset.get("context") or watch.get("why"),
            }
        )
        # Only the Tactical Watch bank carries a progression rule. Writing a
        # null for a system that has no such concept would just blank a field.
        if watch.get("progress"):
            block["progression_rule"] = watch["progress"]

        if (
            watch_sessions
            and reusable_named_watch is not None
            and reusable_named_watch is not session
        ):
            # Remove the old converter shell only after its authoritative
            # content has been repaired on the canonical Watch. The safety
            # check above protects completed or independently populated work.
            matching_days[0]["sessions"] = [
                item
                for item in matching_days[0].get("sessions") or []
                if item is not reusable_named_watch
            ]
        result.applied.append(LockedMergeApplication(day_label, str(block["display_name"])))

    return result


def merge_planner_owned_structured_content(
    structured_plan: dict[str, Any], planning_brief: Any
) -> LockedMergeResult:
    """Carry all planner-owned session and contact truth into one final card.

    Contact reconciliation must run after locked sessions are present. Otherwise
    adding Tactical Focus can turn a contact-only day into a session day while
    leaving its contact truth stranded in the now-hidden day headline.
    """
    result = merge_locked_structured_content(structured_plan, planning_brief)

    reconcile_coach_led_sparring_days(result.plan, planning_brief)
    return result
