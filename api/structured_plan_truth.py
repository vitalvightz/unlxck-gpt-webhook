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
    for separator in (" — ", " – ", " - ", ": "):
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
        "duration": _first(
            r"\b(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*(?:min(?:ute)?s?|sec(?:ond)?s?|hours?|hrs?))\b",
            dose,
        ),
        "work": _first(
            r"\b(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*"
            r"(?:s|sec(?:ond)?s?|min(?:ute)?s?))\s*(?:work|on|fast\b[^;,.]*bursts?)",
            dose,
        ),
        "rest": _first(
            r"\b(?:rest|full\s+recovery)\s+"
            r"(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*"
            r"(?:s|sec(?:ond)?s?|min(?:ute)?s?))\b",
            dose,
        ),
        "effort": _first(
            r"\b(RPE\s*\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?)\b", dose
        ),
        "load": _first(
            r"\b(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*"
            r"(?:kg|lb|lbs|%)(?:\s*\w+)?)\b",
            dose,
        ),
    }
    if values["duration"] and (
        _equivalent(values["duration"], values["rest"])
        or _equivalent(values["duration"], values["work"])
    ):
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
        easier=details.get("easier")
        or details.get("regression")
        or details.get("regress"),
        stop=details.get("stop") or details.get("stop rule"),
        intensity=details.get("intensity"),
        rest=details.get("rest") or parsed_rest,
    )


def _apply_detail(
    block: TrainingTruthBlock, label: str, text: str
) -> TrainingTruthBlock:
    label = label.lower()
    if label == "step":
        return replace(block, steps=(*block.steps, text))
    if label == "why":
        # Why is session objective text, not the block's Purpose. Session
        # objectives are not compared by this first shadow contract.
        return block
    field = {
        "progression": "progress",
        "regression": "easier",
        "regress": "easier",
        "stop rule": "stop",
    }.get(label, label)
    if field == "rest":
        return replace(block, rest=text)
    if hasattr(block, field):
        return replace(block, **{field: text})
    return block


def _iter_locked_roles(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        governance = value.get("governance")
        if (
            isinstance(governance, Mapping)
            and governance.get("selected_drill_locked") is True
        ):
            yield value
        for child in value.values():
            yield from _iter_locked_roles(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_locked_roles(child)


def _locked_block(
    block: TrainingTruthBlock, role: Mapping[str, Any]
) -> TrainingTruthBlock:
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
        steps=tuple(
            _clean(item) for item in watch.get("instructions", ()) if _clean(item)
        ),
        intent=_clean(mindset.get("intent")) or None,
        focus=_clean(mindset.get("focus")) or None,
        reset=_clean(mindset.get("reset")) or None,
        anchor=_clean(mindset.get("anchor")) or None,
        purpose=_clean(mindset.get("context")) or block.purpose,
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
            current[3][-1] = _apply_detail(
                current[3][-1], label, _clean(detail.group("text"))
            )

    # Stage 1 role/bank metadata is stronger only for the corresponding locked block.
    for role in _iter_locked_roles(planning_brief):
        governance = (
            role.get("governance")
            if isinstance(role.get("governance"), Mapping)
            else {}
        )
        name = _clean(governance.get("selected_drill_name"))
        if not name:
            names = role.get("preferred_exercise_names")
            name = _clean(names[0]) if isinstance(names, list) and names else ""
        role_day = _clean(
            role.get("countdown_label") or role.get("scheduled_countdown_label")
        )
        for session in sessions:
            for index, block in enumerate(session[3]):
                if (
                    name
                    and _key(block.display_name) == _key(name)
                    and (not role_day or session[0] == role_day)
                ):
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


def _load(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return _clean(value) or None
    if _clean(value.get("display")):
        return _clean(value.get("display"))
    amount = value.get("value")
    if amount is None:
        return None
    unit = _clean(value.get("unit"))
    if unit.lower() in {"percent", "percentage", "%"}:
        amount_text = f"{amount}%"
        unit = ""
    else:
        amount_text = str(amount)
    return _clean(
        " ".join(part for part in (amount_text, unit, value.get("ref")) if part)
    )


def _effort(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return _clean(value) or None
    if value.get("value") is None:
        return None
    return _clean(f"{value.get('method', '')} {value.get('value')}")


def _equivalent(expected: Any, actual: Any) -> bool:
    return _comparison_text(expected) == _comparison_text(actual)


def _comparison_text(value: Any) -> str:
    text = (
        _clean(value)
        .lower()
        .replace("–", "-")
        .replace("—", "-")
        .replace("percentage", "%")
        .replace("percent", "%")
        .replace("seconds", "sec")
        .replace("second", "sec")
        .replace("minutes", "min")
        .replace("minute", "min")
    )
    text = re.sub(r"(?<=\d)\s*%", "%", text)
    text = re.sub(r"[^a-z0-9%+-]+", " ", text).strip()
    return re.sub(r"(?<=\d) 0(?=\s|$)", "", text)


def compare_structured_plan_to_truth(
    truth: StructuredPlanTruth, structured_plan: Any
) -> list[StructuredTruthDifference]:
    """Return deterministic differences without mutating or judging the candidate."""
    if not isinstance(structured_plan, Mapping):
        return []
    card_days: list[Mapping[str, Any]] = []
    for week in structured_plan.get("weeks", ()):
        if not isinstance(week, Mapping):
            continue
        for day in week.get("days", ()):
            if not isinstance(day, Mapping):
                continue
            card_days.append(day)

    differences: list[StructuredTruthDifference] = []
    for day in truth.days:
        matching_days = [
            candidate
            for candidate in card_days
            if _clean(candidate.get("countdown_label")) == day.countdown_label
        ]
        for session in day.sessions:
            context = dict(
                countdown_label=day.countdown_label,
                session_title=session.title,
            )
            matching_sessions = [
                candidate
                for candidate_day in matching_days
                for candidate in candidate_day.get("sessions", ())
                if isinstance(candidate, Mapping)
                and _key(candidate.get("title")) == _key(session.title)
            ]
            if not matching_sessions:
                same_day_blocks = {
                    _key(block.get("display_name"))
                    for candidate_day in matching_days
                    for candidate in candidate_day.get("sessions", ())
                    if isinstance(candidate, Mapping)
                    for block in candidate.get("blocks", ())
                    if isinstance(block, Mapping)
                }
                for expected in session.blocks:
                    if _key(expected.display_name) in same_day_blocks:
                        differences.append(
                            StructuredTruthDifference(
                                "SESSION_MISMATCH",
                                block_name=expected.display_name,
                                **context,
                            )
                        )
                sessions_elsewhere = [
                    (candidate_day, candidate)
                    for candidate_day in card_days
                    for candidate in candidate_day.get("sessions", ())
                    if isinstance(candidate, Mapping)
                    and _key(candidate.get("title")) == _key(session.title)
                ]
                if not matching_days and sessions_elsewhere:
                    actual_day = _clean(sessions_elsewhere[0][0].get("countdown_label"))
                    for expected in session.blocks:
                        differences.append(
                            StructuredTruthDifference(
                                "DAY_MISMATCH",
                                countdown_label=day.countdown_label,
                                session_title=session.title,
                                block_name=expected.display_name,
                                field="countdown_label",
                                expected=day.countdown_label,
                                actual=actual_day,
                            )
                        )
                    if session.blocks:
                        continue
                # Session identity is part of truth, including an explicit session
                # with no blocks. Do not let a same-named block elsewhere satisfy it.
                differences.append(
                    StructuredTruthDifference("SESSION_MISSING", **context)
                )
                continue
            card_session = matching_sessions[0]
            card_blocks = [
                block
                for block in card_session.get("blocks", ())
                if isinstance(block, Mapping)
            ]
            for expected_index, expected in enumerate(session.blocks):
                block_context = {
                    **context,
                    "block_name": expected.display_name,
                }
                matches = [
                    block
                    for block in card_blocks
                    if _key(block.get("display_name")) == _key(expected.display_name)
                ]
                if not matches:
                    same_day_elsewhere = [
                        candidate_block
                        for candidate_day in matching_days
                        for candidate_session in candidate_day.get("sessions", ())
                        if isinstance(candidate_session, Mapping)
                        and candidate_session is not card_session
                        for candidate_block in candidate_session.get("blocks", ())
                        if isinstance(candidate_block, Mapping)
                        and _key(candidate_block.get("display_name"))
                        == _key(expected.display_name)
                    ]
                    if same_day_elsewhere:
                        differences.append(
                            StructuredTruthDifference(
                                "SESSION_MISMATCH", **block_context
                            )
                        )
                        continue
                    elsewhere = [
                        candidate_day
                        for candidate_day in card_days
                        for candidate_session in candidate_day.get("sessions", ())
                        if isinstance(candidate_session, Mapping)
                        and _key(candidate_session.get("title")) == _key(session.title)
                        for candidate_block in candidate_session.get("blocks", ())
                        if isinstance(candidate_block, Mapping)
                        and _key(candidate_block.get("display_name"))
                        == _key(expected.display_name)
                    ]
                    if elsewhere:
                        actual_day = _clean(elsewhere[0].get("countdown_label"))
                        differences.append(
                            StructuredTruthDifference(
                                "DAY_MISMATCH",
                                field="countdown_label",
                                expected=day.countdown_label,
                                actual=actual_day,
                                **block_context,
                            )
                        )
                    else:
                        differences.append(
                            StructuredTruthDifference("BLOCK_MISSING", **block_context)
                        )
                    continue
                actual = matches[0]
                actual_order = card_blocks.index(actual)
                if actual_order != expected_index:
                    differences.append(
                        StructuredTruthDifference(
                            "BLOCK_ORDER_MISMATCH",
                            field="order_index",
                            expected=expected_index,
                            actual=actual_order,
                            **block_context,
                        )
                    )
                for field, actual_value in (
                    ("sets", actual.get("sets")),
                    ("reps", actual.get("reps")),
                    ("rounds", actual.get("rounds")),
                    ("duration", _measured(actual.get("duration"))),
                    ("work", _measured(actual.get("work"))),
                    ("rest", _measured(actual.get("rest"))),
                    ("load", _load(actual.get("load"))),
                    ("effort", _effort(actual.get("effort"))),
                    ("intensity", actual.get("intensity")),
                    ("purpose", actual.get("purpose")),
                    ("progress", actual.get("progression_rule")),
                    ("easier", actual.get("regression_options")),
                ):
                    wanted = getattr(expected, field)
                    matches_value = _equivalent(wanted, actual_value)
                    if field in {"progress", "easier"} and wanted is not None:
                        candidates = _strings(actual_value)
                        matches_value = any(
                            _equivalent(wanted, candidate) for candidate in candidates
                        )
                    if field == "progress" and wanted is not None:
                        matches_value = _comparison_text(wanted) in _comparison_text(
                            actual_value
                        )
                    if wanted is not None and not matches_value:
                        code = (
                            "REGRESSION_MISMATCH"
                            if field == "easier"
                            else (
                                "PROGRESS_MISSING"
                                if field == "progress" and not actual_value
                                else (
                                    "DURATION_MISMATCH"
                                    if field in {"duration", "work", "rest"}
                                    else "PRESCRIPTION_MISMATCH"
                                )
                            )
                        )
                        differences.append(
                            StructuredTruthDifference(
                                code,
                                field=field,
                                expected=wanted,
                                actual=actual_value,
                                **block_context,
                            )
                        )
                stop_locations = [
                    actual.get("progression_rule"),
                    actual.get("red_flags"),
                ]
                if expected.stop and not any(
                    _key(expected.stop) in _key(text)
                    for text in _strings(stop_locations)
                ):
                    differences.append(
                        StructuredTruthDifference(
                            "STOP_RULE_MISSING",
                            field="stop",
                            expected=expected.stop,
                            **block_context,
                        )
                    )
                if expected.locked:
                    strings = [_clean(item) for item in _strings(card_session)]
                    for label, wanted in [("step", item) for item in expected.steps] + [
                        (name, getattr(expected, name))
                        for name in ("intent", "focus", "reset", "anchor")
                    ]:
                        if wanted and not any(
                            _equivalent(wanted, item) for item in strings
                        ):
                            differences.append(
                                StructuredTruthDifference(
                                    "LOCKED_TEXT_MISMATCH",
                                    field=label,
                                    expected=wanted,
                                    **block_context,
                                )
                            )
    return differences


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _strings(child)]
    return []
