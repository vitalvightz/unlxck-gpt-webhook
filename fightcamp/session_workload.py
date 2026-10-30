"""Dose-aware endurance evidence shared by calendar and final-output checks."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .bank_authority import original_bank_entries
from .config import conditioning_dose_minutes

UNSAFE_STACKING_CODE = "substantial_endurance_strength_conflict"

# Continuous sessions of this size are training appointments, even at easy
# effort. Distance thresholds avoid inventing completion times. Short recovery
# flushes and interval strength/power work do not satisfy this contract.
_DISTANCE_FLOORS = {"run": 3000, "swim": 1000, "cycle": 10000, "row": 5000}
_MODALITIES = {
    "run": r"\b(?:run|running|jog|jogging)\b",
    "swim": r"\b(?:swim|swimming)\b",
    "cycle": r"\b(?:cycle|cycling|bike|biking|ride|riding)\b",
    "row": r"\b(?:row|rowing|rower|erg)\b",
}


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def substantial_endurance(item: Mapping) -> bool:
    """Use authored classification and current dose, with bank lookup for renders."""
    name = str(item.get("name") or item.get("display_name") or "").strip().rstrip(".")
    rows = original_bank_entries({"name": name, "slot_group": "conditioning_slots"})
    metadata = dict(rows[0]) if rows else {}
    metadata.update({k: v for k, v in item.items() if v is not None})
    text = " ".join(
        str(metadata.get(k) or "")
        for k in ("modality", "name", "display_name", "context_modality")
    ).replace("_", " ")
    modality = next(
        (key for key, pattern in _MODALITIES.items() if re.search(pattern, text, re.I)),
        None,
    )
    if modality is None:
        return False
    dose = str(
        item.get("effective_prescription")
        or item.get("prescription")
        or item.get("base_prescription")
        or item.get("duration")
        or item.get("timing")
        or ""
    )
    # A rendered/realised shorter dose takes precedence over the bank dose.
    if dose or any(
        item.get(k) is not None
        for k in ("total_minutes", "duration_min", "distance_m", "work_sec")
    ):
        for key in (
            "total_minutes",
            "duration_min",
            "distance_m",
            "duration",
            "timing",
            "rounds",
            "effective_rounds",
            "work_sec",
            "rest_sec",
        ):
            if key not in item:
                metadata.pop(key, None)
        if dose:
            metadata["duration"] = dose
    duration = str(metadata.get("duration") or metadata.get("timing") or "")
    if re.search(
        r"\d\s*[x×]|\b(?:intervals?|rounds?|repeats?|emom|tabata|circuit)\b",
        duration,
        re.I,
    ):
        return False
    rounds = metadata.get("effective_rounds") or metadata.get("rounds") or 1
    if _number(rounds) > 1:
        return False
    minutes = conditioning_dose_minutes(metadata)
    if minutes is None and _number(metadata.get("work_sec")) > 0:
        minutes = _number(metadata["work_sec"]) / 60
    if minutes is None and (
        hours := re.search(r"\b(\d+(?:\.\d+)?)\s*(?:h|hours?)\b", duration, re.I)
    ):
        minutes = float(hours[1]) * 60
    distance = _number(metadata.get("distance_m"))
    if not distance and (
        match := re.search(
            r"\b(\d+(?:\.\d+)?)\s*(km|kilomet(?:er|re)s?|mi|miles?|m|met(?:er|re)s?)\b",
            duration,
            re.I,
        )
    ):
        distance = float(match[1]) * (
            1000
            if match[2].lower().startswith("k")
            else 1609.344
            if match[2].lower() in {"mi", "mile", "miles"}
            else 1
        )
    return bool(
        (minutes is not None and minutes >= 30)
        or distance >= _DISTANCE_FLOORS[modality]
    )


def role_has_substantial_endurance(role: Mapping) -> bool:
    return any(
        substantial_endurance(item)
        for item in role.get("selected_exercise_assignments") or []
        if isinstance(item, Mapping)
    )


def stacking_finding(profiles: list, *, day: str) -> list[dict]:
    """Ask the canonical same-day policy; adapters supply representation only."""
    from .combat_load_policy import evaluate_candidate_at_position, CalendarEvent

    for index, profile in enumerate(profiles):
        decision = evaluate_candidate_at_position(
            profile,
            candidate_position=0,
            events=[
                CalendarEvent(0, other)
                for i, other in enumerate(profiles)
                if i != index
            ],
        )
        if decision.reason_code == UNSAFE_STACKING_CODE:
            return [
                {
                    "code": UNSAFE_STACKING_CODE,
                    "severity": "blocker",
                    "confidence": "high",
                    "blocking": True,
                    "day": day,
                    "message": decision.reason,
                }
            ]
    return []


def _rendered_profiles(label: str, items: list[dict]) -> list:
    from .combat_load_policy import CalendarLoadProfile, LoadClass, DayOccupancy

    profiles = []
    strength = bool(re.search(r"\b(?:strength|s&c)\b", label, re.I)) or any(
        item.get("block_type") in {"strength", "strength_speed"} for item in items
    )
    if not strength:
        strength = (
            sum(
                bool(
                    original_bank_entries(
                        {
                            "name": str(item.get("name") or "").rstrip("."),
                            "slot_group": "strength_slots",
                        }
                    )
                )
                for item in items
            )
            >= 3
        )
    # As with an uncapped planner strength role, an unproven "touch" title
    # cannot waive meaningful strength ownership.
    if strength:
        profiles.append(
            CalendarLoadProfile(LoadClass.MEANINGFUL_STRENGTH, DayOccupancy.PHYSICAL)
        )
    if any(substantial_endurance(item) for item in items):
        profiles.append(
            CalendarLoadProfile(
                LoadClass.LOW_LOAD_AEROBIC,
                DayOccupancy.PHYSICAL,
                substantial_endurance=True,
            )
        )
    return profiles


def _measured(value, factors: dict[str, float]) -> float | None:
    if not isinstance(value, Mapping):
        return None
    factor = factors.get(str(value.get("unit") or "").strip().lower())
    return _number(value.get("value")) * factor if factor is not None else None


_TIME_MINUTES = {
    "s": 1 / 60,
    "sec": 1 / 60,
    "second": 1 / 60,
    "seconds": 1 / 60,
    "min": 1,
    "minute": 1,
    "minutes": 1,
    "h": 60,
    "hr": 60,
    "hour": 60,
    "hours": 60,
}
_DISTANCE_METRES = {
    "m": 1,
    "meter": 1,
    "meters": 1,
    "metre": 1,
    "metres": 1,
    "km": 1000,
    "kilometer": 1000,
    "kilometers": 1000,
    "kilometre": 1000,
    "kilometres": 1000,
    "mi": 1609.344,
    "mile": 1609.344,
    "miles": 1609.344,
}


def _structured_workload_item(block: Mapping, modality: str) -> dict:
    item = {
        key: block[key]
        for key in (
            "block_type",
            "rounds",
            "effective_rounds",
            "work_sec",
            "rest_sec",
            "duration_min",
            "total_minutes",
            "distance_m",
            "effective_prescription",
            "prescription",
            "base_prescription",
            "timing",
        )
        if block.get(key) is not None
    }
    item["name"] = block.get("display_name") or block.get("name") or ""
    if block.get("modality"):
        item["modality"] = block["modality"]
    item["context_modality"] = modality
    if block.get("prescription_text"):
        item["prescription"] = block["prescription_text"]
    for field, target, units in (
        ("duration", "duration_min", _TIME_MINUTES),
        ("work", "work_sec", {k: v * 60 for k, v in _TIME_MINUTES.items()}),
        ("distance", "distance_m", _DISTANCE_METRES),
        ("rest", "rest_sec", {k: v * 60 for k, v in _TIME_MINUTES.items()}),
    ):
        measured = _measured(block.get(field), units)
        if measured is not None:
            item[target] = measured
    return item


def _has_current_workload(item: Mapping) -> bool:
    return any(
        item.get(key) is not None
        for key in (
            "duration_min",
            "total_minutes",
            "distance_m",
            "work_sec",
            "rounds",
            "effective_rounds",
            "effective_prescription",
            "prescription",
            "base_prescription",
            "timing",
        )
    )


def structured_stacking_findings(plan: dict) -> list[dict]:
    findings = []
    for wi, week in enumerate(plan.get("weeks") or []):
        for di, day in enumerate(week.get("days") or []):
            profiles = []
            for session in day.get("sessions") or []:
                label = str(session.get("title") or "")
                conditioning = session.get("session_type") == "conditioning"
                modality = (
                    " ".join(
                        str(session.get(key) or "")
                        for key in (
                            "modality",
                            "title",
                            "objective",
                            "primary_stressor",
                        )
                    )
                    if conditioning
                    else ""
                )
                items = [
                    _structured_workload_item(block, modality)
                    for block in session.get("blocks") or []
                ]
                # Session duration is a fallback for an undosed endurance
                # appointment, never a replacement for current block doses or
                # the elapsed time of a strength/interval workout.
                relevant = [
                    item
                    for item in items
                    if item.get("block_type") in {None, "conditioning"}
                ]
                elapsed = _measured(session.get("planned_duration"), _TIME_MINUTES)
                if (
                    conditioning
                    and elapsed is not None
                    and not any(_has_current_workload(item) for item in relevant)
                ):
                    items.append(
                        {"name": label, "modality": modality, "duration_min": elapsed}
                    )
                if session.get("session_type") == "strength_power":
                    label += " strength"
                profiles.extend(_rendered_profiles(label, items))
            findings.extend(
                stacking_finding(
                    profiles,
                    day=str(
                        day.get("weekday") or day.get("countdown_label") or f"{wi}:{di}"
                    ),
                )
            )
    return findings


_WEEKDAYS = r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
_RAW_DAY = re.compile(
    rf"^\s*(?:#{{1,6}}\s*|[-*]\s*)?(?:D-(\d+)\s*\(({_WEEKDAYS})\)|({_WEEKDAYS}))\s*(?:[—–:-]|\(D-(\d+)\))\s*(.*)$",
    re.I,
)


def raw_stacking_findings(text: str) -> list[dict]:
    """Read actual day cards, independently of an optional weekly role map."""
    days: dict[tuple, list] = {}
    week = 0
    current = None
    for raw in str(text or "").splitlines():
        line = raw.replace("**", "")
        if re.match(
            r"^\s*(?:#{1,6}\s*)?(?:(?:GPP|SPP|TAPER).*\b)?Week\s+\d+", line, re.I
        ):
            week += 1
            current = None
        elif match := _RAW_DAY.match(line):
            key = (match[1] or match[4] or week, (match[2] or match[3]).lower())
            current = {"label": match[5], "items": []}
            days.setdefault(key, []).append(current)
        elif re.match(
            r"^\s*(?:#{1,6}\s*)?(?:4-Week|Progression Rules|Priority Hierarchy|Adjustment Rules|Rehab /|Session Cards|Weekly Rhythm)\b",
            line,
            re.I,
        ):
            current = None
        elif current is not None:
            if re.match(
                r"^\s*(?:How|Cue|Easier|Swap|Progress|Stop|Why|Coach note|Fallback)\s*:",
                line,
                re.I,
            ):
                continue
            if dose := re.match(r"^\s*Dose\s*:\s*(.*)", line, re.I):
                if current["items"]:
                    current["items"][-1]["prescription"] = dose[1]
            elif exercise := re.match(
                r"^\s*[-*•]\s+(.+?)(?:\s+[—–]\s+|:\s+|$)(.*)", line
            ):
                current["items"].append(
                    {"name": exercise[1].rstrip("."), "prescription": exercise[2]}
                )
    findings = []
    for key, sessions in days.items():
        profiles = [
            p for s in sessions for p in _rendered_profiles(s["label"], s["items"])
        ]
        findings.extend(stacking_finding(profiles, day=f"{key[0]}:{key[1]}"))
    return findings
