"""Deterministic, read-only training truth for structured-card shadow checks.

This module intentionally has no model or persistence dependencies.  It parses
only facts stated in the approved plan text, then lets governed Stage 1 locked
role metadata replace the corresponding block where that metadata is stronger.
The resulting frozen objects are diagnostics, not an athlete-facing schema.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class TrainingTruthBlock:
    display_name: str
    order_index: int
    sets: str | None = None
    reps: str | None = None
    rounds: str | None = None
    duration: str | None = None
    work: str | None = None
    rest: str | None = None
    load: str | None = None
    effort: str | None = None
    intensity: str | None = None
    purpose: str | None = None
    progress: str | None = None
    easier: str | None = None
    stop: str | None = None
    coaching_cues: tuple[str, ...] = ()
    locked: bool = False
    steps: tuple[str, ...] = ()
    intent: str | None = None
    focus: str | None = None
    reset: str | None = None
    anchor: str | None = None


@dataclass(frozen=True)
class TrainingTruthSession:
    title: str
    blocks: tuple[TrainingTruthBlock, ...]


@dataclass(frozen=True)
class TrainingTruthDay:
    countdown_label: str
    weekday: str | None
    sessions: tuple[TrainingTruthSession, ...]


@dataclass(frozen=True)
class StructuredPlanTruth:
    days: tuple[TrainingTruthDay, ...]


@dataclass(frozen=True)
class StructuredTruthDifference:
    code: str
    countdown_label: str | None = None
    session_title: str | None = None
    block_name: str | None = None
    field: str | None = None
    expected: Any = None
    actual: Any = None


_HEADER_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:"
    r"D-(?P<day>\d+)(?:\s*\((?P<weekday>[^)]+)\))?"
    r"|(?P<weekday_first>Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
    r"[^()]*(?:\(\s*D-(?P<day_second>\d+)\s*\)))"
    r"\s*[—–\-:]\s*(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*[-*•‣▪◦·]\s+(.+?)\s*$")
_DETAIL_RE = re.compile(
    r"^\s*(?:Step\s+(?P<step>\d+)|(?P<label>Purpose|Why|Progress(?:ion)?|Regression|Regress|Easier|Stop(?: rule)?|Intent|Focus|Reset|Anchor|Intensity|Rest))\s*:\s*(?P<text>.+?)\s*$",
    re.IGNORECASE,
)
_INLINE_LABEL_RE = re.compile(
    r"\b(Purpose|Progress(?:ion)?|Regression|Regress|Easier|Stop(?: rule)?|Intensity|Rest)\s*:\s*",
    re.IGNORECASE,
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("**", "").split()).strip(" ;")


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).lower()).strip()


def _split_inline(text: str) -> tuple[str, dict[str, str]]:
    matches = list(_INLINE_LABEL_RE.finditer(text))
    if not matches:
        return _clean(text), {}
    lead = _clean(text[: matches[0].start()])
    details: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        details[match.group(1).lower()] = _clean(text[match.end() : end])
    return lead, details


def _name_and_dose(line: str) -> tuple[str, str]:
    # Mirrors the frontend contract: the first dash/colon separates an activity
    # heading from its dose, while labelled detail segments remain details.
    for separator in (" — ", " – ", ": "):
        if separator in line:
            name, dose = line.split(separator, 1)
            return _clean(name), _clean(dose)
    return _clean(line), ""


def _first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return _clean(match.group(1)) if match else None


def _prescription(dose: str) -> dict[str, str | None]:
    values = {
        "sets": _first(r"\b(\d+(?:\s*[-–]\s*\d+)?)\s*sets?\b", dose),
        "reps": _first(r"(?:\bx\s*|\b)(\d+(?:\s*[-–]\s*\d+)?)\s*reps?\b", dose),
        "rounds": _first(r"\b(\d+(?:\s*[-–]\s*\d+)?)\s*rounds?\b", dose),
        "duration": _first(r"\b(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*(?:min(?:ute)?s?|sec(?:ond)?s?|hours?|hrs?))\b", dose),
        "work": _first(r"\b(\d+(?:\.\d+)?\s*(?:s|sec(?:ond)?s?|min(?:ute)?s?))\s*(?:work|on)\b", dose),
        "rest": _first(r"\brest\s+(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*(?:s|sec(?:ond)?s?|min(?:ute)?s?))\b", dose),
        "effort": _first(r"\b(RPE\s*\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?)\b", dose),
        "load": _first(r"\b(\d+(?:\.\d+)?\s*(?:kg|lb|lbs|%)(?:\s*\w+)?)\b", dose),
    }
    if values["duration"] and _equivalent(values["duration"], values["rest"]):
        values["duration"] = None
    return values


def _make_block(line: str, order: int) -> TrainingTruthBlock:
    name, dose_and_details = _name_and_dose(line)
    dose, details = _split_inline(dose_and_details)
    values = _prescription(dose)
    parsed_rest = values.pop("rest")
    return TrainingTruthBlock(
        display_name=name,
        order_index=order,
        **values,
        purpose=details.get("purpose"),
        progress=details.get("progress") or details.get("progression"),
        easier=details.get("easier") or details.get("regression") or details.get("regress"),
        stop=details.get("stop") or details.get("stop rule"),
        intensity=details.get("intensity"),
        rest=details.get("rest") or parsed_rest,
    )


def _apply_detail(block: TrainingTruthBlock, label: str, text: str) -> TrainingTruthBlock:
    label = label.lower()
    if label == "step":
        return replace(block, steps=(*block.steps, text))
    field = {
        "progression": "progress", "regression": "easier", "regress": "easier",
        "stop rule": "stop", "why": "purpose",
    }.get(label, label)
    if field == "rest":
        return replace(block, rest=text)
    if hasattr(block, field):
        return replace(block, **{field: text})
    return block


def _iter_locked_roles(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        governance = value.get("governance")
        if isinstance(governance, Mapping) and governance.get("selected_drill_locked") is True:
            yield value
        for child in value.values():
            yield from _iter_locked_roles(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_locked_roles(child)


def _locked_block(block: TrainingTruthBlock, role: Mapping[str, Any]) -> TrainingTruthBlock:
    watch = role.get("tactical_watch")
    if not isinstance(watch, Mapping):
        return replace(block, locked=True)
    mindset = watch.get("mindset") if isinstance(watch.get("mindset"), Mapping) else {}
    duration = watch.get("duration_min")
    return replace(
        block,
        display_name=_clean(watch.get("name")) or block.display_name,
        duration=f"{duration} min" if duration is not None else block.duration,
        locked=True,
        steps=tuple(_clean(item) for item in watch.get("instructions", ()) if _clean(item)),
        intent=_clean(mindset.get("intent")) or None,
        focus=_clean(mindset.get("focus")) or None,
        reset=_clean(mindset.get("reset")) or None,
        anchor=_clean(mindset.get("anchor")) or None,
        purpose=_clean(watch.get("why")) or block.purpose,
        progress=_clean(watch.get("progress")) or block.progress,
    )


def extract_structured_plan_truth(
    final_plan_text: str, planning_brief: Any = None
) -> StructuredPlanTruth:
    """Extract only explicit plan facts, with governed locked roles authoritative."""
    sessions: list[tuple[str, str | None, str, list[TrainingTruthBlock]]] = []
    current: tuple[str, str | None, str, list[TrainingTruthBlock]] | None = None
    for raw_line in str(final_plan_text or "").replace("\r\n", "\n").splitlines():
        line = raw_line.replace("**", "").rstrip()
        header = _HEADER_RE.match(line.strip())
        if header:
            weekday = header.group("weekday") or header.group("weekday_first")
            current = (
                f"D-{header.group('day') or header.group('day_second')}",
                _clean(weekday) or None,
                _clean(header.group("title")),
                [],
            )
            sessions.append(current)
            continue
        if current is None:
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            current[3].append(_make_block(bullet.group(1), len(current[3])))
            continue
        detail = _DETAIL_RE.match(line)
        if detail and current[3]:
            label = "step" if detail.group("step") else str(detail.group("label"))
            current[3][-1] = _apply_detail(current[3][-1], label, _clean(detail.group("text")))

    # Stage 1 role/bank metadata is stronger only for the corresponding locked block.
    for role in _iter_locked_roles(planning_brief):
        governance = role.get("governance") if isinstance(role.get("governance"), Mapping) else {}
        name = _clean(governance.get("selected_drill_name"))
        if not name:
            names = role.get("preferred_exercise_names")
            name = _clean(names[0]) if isinstance(names, list) and names else ""
        role_day = _clean(role.get("countdown_label") or role.get("scheduled_countdown_label"))
        for session in sessions:
            for index, block in enumerate(session[3]):
                if name and _key(block.display_name) == _key(name) and (not role_day or session[0] == role_day):
                    session[3][index] = _locked_block(block, role)

    days: list[TrainingTruthDay] = []
    for countdown, weekday, title, blocks in sessions:
        session = TrainingTruthSession(title=title, blocks=tuple(blocks))
        if days and days[-1].countdown_label == countdown:
            days[-1] = replace(
                days[-1],
                weekday=days[-1].weekday or weekday,
                sessions=(*days[-1].sessions, session),
            )
        else:
            days.append(TrainingTruthDay(countdown, weekday, (session,)))
    return StructuredPlanTruth(tuple(days))


def _measured(value: Any) -> str | None:
    if isinstance(value, Mapping) and value.get("value") is not None:
        return _clean(f"{value.get('value')} {value.get('unit', '')}")
    return _clean(value) or None


def _equivalent(expected: Any, actual: Any) -> bool:
    def canonical(value: Any) -> str:
        text = _key(value).replace("minutes", "min").replace("minute", "min")
        return re.sub(r"(?<=\d) 0(?=\s|$)", "", text)
    return canonical(expected) == canonical(actual)


def compare_structured_plan_to_truth(
    truth: StructuredPlanTruth, structured_plan: Any
) -> list[StructuredTruthDifference]:
    """Return deterministic differences without mutating or judging the candidate."""
    if not isinstance(structured_plan, Mapping):
        return []
    card_blocks: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
    for week in structured_plan.get("weeks", ()):
        if not isinstance(week, Mapping):
            continue
        for day in week.get("days", ()):
            if not isinstance(day, Mapping):
                continue
            for session in day.get("sessions", ()):
                if isinstance(session, Mapping):
                    for block in session.get("blocks", ()):
                        if isinstance(block, Mapping):
                            card_blocks.append((_clean(day.get("countdown_label")), session, block))

    differences: list[StructuredTruthDifference] = []
    for day in truth.days:
        for session in day.sessions:
            for expected_index, expected in enumerate(session.blocks):
                matches = [item for item in card_blocks if _key(item[2].get("display_name")) == _key(expected.display_name)]
                on_day = [item for item in matches if item[0] == day.countdown_label]
                context = dict(countdown_label=day.countdown_label, session_title=session.title, block_name=expected.display_name)
                if not matches:
                    differences.append(StructuredTruthDifference("BLOCK_MISSING", **context))
                    continue
                if not on_day:
                    differences.append(StructuredTruthDifference("DAY_MISMATCH", field="countdown_label", expected=day.countdown_label, actual=matches[0][0], **context))
                    continue
                _, card_session, actual = on_day[0]
                actual_order = list(card_session.get("blocks", ())).index(actual)
                if actual_order != expected_index:
                    differences.append(StructuredTruthDifference("BLOCK_ORDER_MISMATCH", field="order_index", expected=expected_index, actual=actual_order, **context))
                for field, actual_value in (
                    ("sets", actual.get("sets")), ("reps", actual.get("reps")),
                    ("rounds", actual.get("rounds")), ("duration", _measured(actual.get("duration"))),
                    ("work", _measured(actual.get("work"))), ("rest", _measured(actual.get("rest"))),
                    ("intensity", actual.get("intensity")), ("purpose", actual.get("purpose")),
                    ("progress", actual.get("progression_rule")),
                ):
                    wanted = getattr(expected, field)
                    if wanted is not None and not _equivalent(wanted, actual_value):
                        code = "PROGRESS_MISSING" if field == "progress" and not actual_value else ("DURATION_MISMATCH" if field in {"duration", "work", "rest"} else "PRESCRIPTION_MISMATCH")
                        differences.append(StructuredTruthDifference(code, field=field, expected=wanted, actual=actual_value, **context))
                if expected.stop and not any(_key(expected.stop) in _key(text) for text in _strings(actual.get("red_flags"))):
                    differences.append(StructuredTruthDifference("STOP_RULE_MISSING", field="stop", expected=expected.stop, **context))
                if expected.locked:
                    strings = [_clean(item) for item in _strings(card_session)]
                    for label, wanted in [("step", item) for item in expected.steps] + [(name, getattr(expected, name)) for name in ("intent", "focus", "reset", "anchor")]:
                        if wanted and not any(_equivalent(wanted, item) for item in strings):
                            differences.append(StructuredTruthDifference("LOCKED_TEXT_MISMATCH", field=label, expected=wanted, **context))
    return differences


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _strings(child)]
    return []
