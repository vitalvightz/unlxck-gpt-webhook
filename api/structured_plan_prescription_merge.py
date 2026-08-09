"""Restore exactly representable source prescriptions without repairing structure."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .structured_plan_truth import StructuredPlanTruth, TrainingTruthBlock


@dataclass(frozen=True)
class PrescriptionMergeApplication:
    countdown_label: str
    session_title: str
    block_name: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class PrescriptionMergeIssue:
    countdown_label: str
    session_title: str
    block_name: str | None
    reason: str
    fields: tuple[str, ...] = ()
    expected: str | None = None


@dataclass
class PrescriptionMergeResult:
    plan: dict[str, Any]
    applied: list[PrescriptionMergeApplication] = field(default_factory=list)
    unresolved: list[PrescriptionMergeIssue] = field(default_factory=list)


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _days(plan: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    for week in plan.get("weeks") or []:
        if isinstance(week, Mapping):
            for day in week.get("days") or []:
                if isinstance(day, dict):
                    yield day


def _range(value: str) -> bool:
    return bool(re.search(r"\d\s*[-–]\s*\d", value))


def _number(value: str) -> int | float:
    number = float(re.search(r"\d+(?:\.\d+)?", value).group())  # type: ignore[union-attr]
    return int(number) if number.is_integer() else number


def _measured(value: str) -> dict[str, Any]:
    unit_text = re.search(r"[A-Za-z]+", value).group().lower()  # type: ignore[union-attr]
    unit = {
        "s": "seconds",
        "sec": "seconds",
        "second": "seconds",
        "seconds": "seconds",
        "min": "minutes",
        "mins": "minutes",
        "minute": "minutes",
        "minutes": "minutes",
        "hr": "hours",
        "hrs": "hours",
        "hour": "hours",
        "hours": "hours",
    }.get(unit_text, unit_text)
    return {"value": _number(value), "unit": unit}


def _load(value: str) -> dict[str, Any] | None:
    if _range(value):
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(%|kg|lb|lbs)(?:\s*(.*?))?\s*", value)
    if not match:
        return None
    amount, raw_unit, ref = match.groups()
    unit = "percent" if raw_unit == "%" else ("lb" if raw_unit == "lbs" else raw_unit)
    return {
        "method": "percentage" if raw_unit == "%" else "absolute",
        "value": float(amount) if "." in amount else int(amount),
        "unit": unit,
        "ref": ref or None,
        "display": value,
    }


def _apply_fields(
    block: dict[str, Any], truth: TrainingTruthBlock
) -> tuple[list[str], list[tuple[str, str]]]:
    applied: list[str] = []
    unresolved: list[tuple[str, str]] = []
    block["display_name"] = truth.display_name
    applied.append("display_name")
    for name in ("sets", "rounds"):
        value = getattr(truth, name)
        if value is None:
            continue
        if _range(value):
            unresolved.append((name, value))
        else:
            block[name] = int(_number(value))
            applied.append(name)
    if truth.reps is not None:
        block["reps"] = (
            truth.reps.replace("–", "-")
            if _range(truth.reps)
            else int(_number(truth.reps))
        )
        applied.append("reps")
    for name in ("duration", "work", "rest"):
        value = getattr(truth, name)
        if value is None:
            continue
        if _range(value):
            unresolved.append((name, value))
        else:
            block[name] = _measured(value)
            applied.append(name)
    if truth.load is not None:
        load = _load(truth.load)
        if load is None:
            unresolved.append(("load", truth.load))
        else:
            block["load"] = load
            applied.append("load")
    if truth.effort is not None:
        value = re.sub(r"^RPE\s*", "", truth.effort, flags=re.I).replace("–", "-")
        block["effort"] = {
            "method": "RPE",
            "value": value if "-" in value else _number(value),
            "scale": "1-10",
        }
        applied.append("effort")
    for source, target in (("intensity", "intensity"), ("purpose", "purpose")):
        value = getattr(truth, source)
        if value is not None:
            block[target] = value
            applied.append(target)
    if truth.easier is not None:
        block["regression_options"] = [truth.easier]
        applied.append("regression_options")
    if truth.progress is not None or truth.stop is not None:
        parts = []
        if truth.progress is not None:
            parts.append(f"Progress: {truth.progress}")
        if truth.stop is not None:
            parts.append(f"Stop: {truth.stop}")
        block["progression_rule"] = "\n".join(parts)
        applied.extend(
            [
                name
                for name, value in (
                    ("progression_rule", truth.progress),
                    ("stop", truth.stop),
                )
                if value
            ]
        )
    return applied, unresolved


def merge_authoritative_prescription(
    structured_plan: dict[str, Any], truth: StructuredPlanTruth
) -> PrescriptionMergeResult:
    """Patch facts only after an exact day/session/block resolution."""
    plan = copy.deepcopy(structured_plan)
    result = PrescriptionMergeResult(plan)
    all_days = list(_days(plan))
    for truth_day in truth.days:
        day_matches = [
            d
            for d in all_days
            if str(d.get("countdown_label") or "").strip() == truth_day.countdown_label
        ]
        for truth_session in truth_day.sessions:
            context = (truth_day.countdown_label, truth_session.title)
            if len(day_matches) != 1:
                for block in truth_session.blocks:
                    if not block.locked:
                        result.unresolved.append(
                            PrescriptionMergeIssue(
                                *context, block.display_name, "wrong_day"
                            )
                        )
                continue
            sessions = [
                s
                for s in day_matches[0].get("sessions") or []
                if isinstance(s, dict)
                and _key(s.get("title")) == _key(truth_session.title)
            ]
            for truth_block in truth_session.blocks:
                if truth_block.locked:
                    continue
                if len(sessions) != 1:
                    result.unresolved.append(
                        PrescriptionMergeIssue(
                            *context, truth_block.display_name, "wrong_session"
                        )
                    )
                    continue
                matches = [
                    b
                    for b in sessions[0].get("blocks") or []
                    if isinstance(b, dict)
                    and _key(b.get("display_name")) == _key(truth_block.display_name)
                ]
                if len(matches) != 1:
                    result.unresolved.append(
                        PrescriptionMergeIssue(
                            *context,
                            truth_block.display_name,
                            "block_not_uniquely_resolved",
                        )
                    )
                    continue
                fields, ranges = _apply_fields(matches[0], truth_block)
                if fields:
                    result.applied.append(
                        PrescriptionMergeApplication(
                            *context, truth_block.display_name, tuple(fields)
                        )
                    )
                for name, expected in ranges:
                    result.unresolved.append(
                        PrescriptionMergeIssue(
                            *context,
                            truth_block.display_name,
                            "UNREPRESENTABLE_RANGE",
                            (name,),
                            expected,
                        )
                    )
    return result
