from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from .injury_formatting import parse_injuries_and_restrictions
from .restriction_parsing import ParsedRestriction


def _normalize_list(field: str | None) -> list[str]:
    return [w.strip().lower() for w in field.split(",") if w.strip()] if field else []


_EMPTY_INJURY_MARKERS = {
    "none",
    "no",
    "no injury",
    "no injuries",
    "n/a",
    "na",
    "nil",
    "none reported",
    "none noted",
    "no issues",
}


def _normalize_injury_marker(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


_EMPTY_INJURY_MARKERS_NORMALIZED = {
    _normalize_injury_marker(marker) for marker in _EMPTY_INJURY_MARKERS
}


def normalize_injury_text(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    if not cleaned:
        return ""
    normalized_full = _normalize_injury_marker(cleaned)
    if normalized_full in _EMPTY_INJURY_MARKERS_NORMALIZED:
        return ""

    parts = [
        part.strip()
        for part in re.split(r"\s*(?:,|/|\+| and )\s*", cleaned, flags=re.IGNORECASE)
        if part.strip()
    ]
    remaining: list[str] = []
    for part in parts:
        normalized_part = _normalize_injury_marker(part)
        if not normalized_part:
            continue
        if normalized_part in _EMPTY_INJURY_MARKERS_NORMALIZED:
            continue
        remaining.append(part)
    if not remaining:
        return ""
    return ", ".join(remaining)


def get_value(label: str, fields: list[dict]) -> str:
    for field in fields:
        if field.get("label", "").strip() == label.strip():
            value = field.get("value")
            if isinstance(value, list):
                if "options" in field:
                    return ", ".join(
                        [opt["text"] for opt in field["options"] if opt.get("id") in value]
                    )
                return ", ".join(str(v) for v in value)
            return str(value).strip() if value is not None else ""
    return ""


def get_date_value(label: str, fields: list[dict]) -> str:
    for field in fields:
        if field.get("label", "").strip() == label.strip():
            value = field.get("value")
            if isinstance(value, dict):
                for key in ("date", "value", "text", "label"):
                    if key in value and value[key] is not None:
                        return str(value[key]).strip()
            if isinstance(value, list):
                return ", ".join(str(v) for v in value)
            return str(value).strip() if value is not None else ""
    return ""


def parse_fight_date(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


@dataclass(frozen=True)
class PlanInput:
    full_name: str
    age: str
    weight: str
    target_weight: str
    height: str
    fighting_style_technical: str
    fighting_style_tactical: str
    stance: str
    status: str
    record: str
    next_fight_date: str
    rounds_format: str
    frequency_raw: str
    fatigue: str
    equipment_access: str
    available_days: str
    injuries: str
    parsed_injuries: list[dict[str, str | None]]
    restrictions: list[ParsedRestriction]
    key_goals: str
    weak_areas: str
    training_preference: str
    mental_block: str
    notes: str
    training_days: list[str]
    training_frequency: int
    weeks_out: int | str
    days_until_fight: int | None

    @classmethod
    def from_payload(cls, data: dict) -> "PlanInput":
        fields = data["data"]["fields"]

        full_name = get_value("Full name", fields)
        age = get_value("Age", fields)
        weight = get_value("Weight (kg)", fields)
        target_weight = get_value("Target Weight (kg)", fields)
        height = get_value("Height (cm)", fields)
        fighting_style_technical = get_value("Fighting Style (Technical)", fields)
        fighting_style_tactical = get_value("Fighting Style (Tactical)", fields)
        stance = get_value("Stance", fields)
        status = get_value("Professional Status", fields)
        record = get_value("Current Record", fields)
        next_fight_date = get_date_value("When is your next fight?", fields)
        rounds_format = get_value("Rounds x Minutes", fields)
        frequency_raw = get_value("Weekly Training Frequency", fields)
        fatigue = get_value("Fatigue Level", fields)
        equipment_access = get_value("Equipment Access", fields)
        available_days = get_value("Training Availability", fields)
        injuries = normalize_injury_text(
            get_value("Any injuries or areas you need to work around?", fields)
        )
        parsed_injuries, parsed_restrictions = parse_injuries_and_restrictions(injuries or "")
        key_goals = get_value("What are your key performance goals?", fields)
        weak_areas = get_value("Where do you feel weakest right now?", fields)
        training_preference = get_value("Do you prefer certain training styles?", fields)
        mental_block = get_value(
            "Do you struggle with any mental blockers or mindset challenges?", fields
        )
        notes = get_value("Are there any parts of your previous plan you hated or loved?", fields)

        training_days = [d.strip() for d in available_days.split(",") if d.strip()]
        try:
            training_frequency = int(frequency_raw)
        except (TypeError, ValueError):
            training_frequency = len(training_days)

        weeks_out: int | str
        days_until_fight = None
        if next_fight_date:
            fight_date = parse_fight_date(next_fight_date)
            if fight_date:
                days_until_fight = (fight_date - datetime.now()).days
                weeks_out = max(1, days_until_fight // 7)
            else:
                weeks_out = "N/A"
        else:
            weeks_out = "N/A"

        return cls(
            full_name=full_name,
            age=age,
            weight=weight,
            target_weight=target_weight,
            height=height,
            fighting_style_technical=fighting_style_technical,
            fighting_style_tactical=fighting_style_tactical,
            stance=stance,
            status=status,
            record=record,
            next_fight_date=next_fight_date,
            rounds_format=rounds_format,
            frequency_raw=frequency_raw,
            fatigue=fatigue,
            equipment_access=equipment_access,
            available_days=available_days,
            injuries=injuries,
            parsed_injuries=parsed_injuries,
            restrictions=parsed_restrictions,
            key_goals=key_goals,
            weak_areas=weak_areas,
            training_preference=training_preference,
            mental_block=mental_block,
            notes=notes,
            training_days=training_days,
            training_frequency=training_frequency,
            weeks_out=weeks_out,
            days_until_fight=days_until_fight,
        )

    @property
    def tech_styles(self) -> list[str]:
        return _normalize_list(self.fighting_style_technical)

    @property
    def tactical_styles(self) -> list[str]:
        return _normalize_list(self.fighting_style_tactical)
