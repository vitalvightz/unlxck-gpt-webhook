from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def _normalize_label(label: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", str(label or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


_CRITICAL_LABEL_ALIASES = {
    _normalize_label("When is your next fight?"): {
        _normalize_label("Fight date"),
        _normalize_label("Next fight date"),
        _normalize_label("Date of next fight"),
        _normalize_label("When is the fight?"),
    },
    _normalize_label("Fighting Style (Technical)"): {
        _normalize_label("Technical style"),
        _normalize_label("Primary fighting style"),
        _normalize_label("Combat style (technical)"),
    },
    _normalize_label("Fighting Style (Tactical)"): {
        _normalize_label("Tactical style"),
        _normalize_label("Fight style (tactical)"),
        _normalize_label("Combat style (tactical)"),
    },
    _normalize_label("Weekly Training Frequency"): {
        _normalize_label("Training frequency"),
        _normalize_label("Sessions per week"),
        _normalize_label("How many times do you train per week"),
    },
    _normalize_label("Training Availability"): {
        _normalize_label("Availability"),
        _normalize_label("Available training days"),
        _normalize_label("Days available to train"),
    },
    _normalize_label("Any injuries or areas you need to work around?"): {
        _normalize_label("Injuries"),
        _normalize_label("Current injuries"),
        _normalize_label("Injuries or restrictions"),
        _normalize_label("Anything to work around"),
    },
    _normalize_label("Athlete Time Zone"): {
        _normalize_label("Athlete Timezone"),
        _normalize_label("Time Zone"),
        _normalize_label("Timezone"),
        _normalize_label("Athlete UTC Offset"),
        _normalize_label("UTC Offset"),
    },
    _normalize_label("Athlete Locale"): {
        _normalize_label("Locale"),
        _normalize_label("Athlete Region"),
        _normalize_label("Region"),
    },
}
_DATE_ONLY_PATTERN = re.compile(r"^(?:\d{4}[-/]\d{2}[-/]\d{2}|\d{2}/\d{2}/\d{4})$")
_UTC_OFFSET_PATTERN = re.compile(
    r"^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$",
    re.IGNORECASE,
)


def _field_matches_label(field_label: str, target_label: str) -> bool:
    normalized_target = _normalize_label(target_label)
    normalized_field = _normalize_label(field_label)
    if not normalized_target or not normalized_field:
        return False
    if normalized_field == normalized_target:
        return True
    return normalized_field in _CRITICAL_LABEL_ALIASES.get(normalized_target, set())


def _find_field(label: str, fields: list[dict]) -> dict | None:
    exact_target = label.strip()
    for field in fields:
        if str(field.get("label", "")).strip() == exact_target:
            return field
    for field in fields:
        if _field_matches_label(field.get("label", ""), label):
            return field
    return None


def _extract_value(field: dict) -> str:
    value = field.get("value")
    if isinstance(value, list):
        if "options" in field:
            selected_ids = {str(item) for item in value}
            return ", ".join(
                [
                    str(opt.get("text", "")).strip()
                    for opt in field["options"]
                    if str(opt.get("id")) in selected_ids and str(opt.get("text", "")).strip()
                ]
            )
        return ", ".join(str(v) for v in value)
    return str(value).strip() if value is not None else ""


def get_value(label: str, fields: list[dict]) -> str:
    field = _find_field(label, fields)
    if not field:
        return ""
    return _extract_value(field)


def get_date_value(label: str, fields: list[dict]) -> str:
    field = _find_field(label, fields)
    if not field:
        return ""
    value = field.get("value")
    if isinstance(value, dict):
        for key in ("date", "value", "text", "label"):
            if key in value and value[key] is not None:
                return str(value[key]).strip()
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value).strip() if value is not None else ""


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _calendar_now() -> datetime:
    return datetime.now().astimezone().replace(tzinfo=None)


def _resolve_timezone(value: str | None) -> timezone | ZoneInfo | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if normalized.upper() in {"UTC", "GMT", "Z"}:
        return timezone.utc

    try:
        return ZoneInfo(normalized)
    except ZoneInfoNotFoundError:
        pass

    offset_match = _UTC_OFFSET_PATTERN.match(normalized)
    if not offset_match:
        return None

    sign, hours_text, minutes_text = offset_match.groups()
    hours = int(hours_text)
    minutes = int(minutes_text or "0")
    if hours > 23 or minutes > 59:
        return None

    offset = timedelta(hours=hours, minutes=minutes)
    if sign == "-":
        offset = -offset
    return timezone(offset)


def _athlete_calendar_now(athlete_timezone: str | None = None) -> datetime:
    tzinfo = _resolve_timezone(athlete_timezone)
    if tzinfo is None:
        return _calendar_now()
    return _utc_now().replace(tzinfo=timezone.utc).astimezone(tzinfo).replace(tzinfo=None)


def normalize_days_until_fight(days_until_fight: int | None) -> int | None:
    if not isinstance(days_until_fight, int):
        return None
    return days_until_fight if days_until_fight >= 0 else None


def is_short_notice_days(days_until_fight: int | None) -> bool:
    return isinstance(days_until_fight, int) and 0 <= days_until_fight <= 14


def _extract_fields(data: dict) -> list[dict]:
    fields = data.get("data", {}).get("fields") if isinstance(data, dict) else None
    if not isinstance(fields, list):
        raise ValueError("payload missing required data.fields list")
    return fields


def _compute_days_until_fight(
    raw_value: str,
    fight_date: datetime,
    *,
    athlete_timezone: str | None = None,
    now: datetime | None = None,
) -> int | None:
    if _DATE_ONLY_PATTERN.match((raw_value or "").strip()):
        reference = now or _athlete_calendar_now(athlete_timezone)
        raw_days = (fight_date.date() - reference.date()).days
    else:
        reference = now or _utc_now()
        if reference.tzinfo:
            reference = reference.astimezone(timezone.utc).replace(tzinfo=None)
        raw_days = int((fight_date - reference).total_seconds() // 86400)
    return normalize_days_until_fight(raw_days)


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
    athlete_timezone: str
    athlete_locale: str
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
        fields = _extract_fields(data)

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
        athlete_timezone = get_value("Athlete Time Zone", fields)
        athlete_locale = get_value("Athlete Locale", fields)
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
                days_until_fight = _compute_days_until_fight(
                    next_fight_date,
                    fight_date,
                    athlete_timezone=athlete_timezone,
                )
                weeks_out = max(1, days_until_fight // 7) if days_until_fight is not None else "N/A"
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
            athlete_timezone=athlete_timezone,
            athlete_locale=athlete_locale,
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

    def generation_issues(self) -> list[str]:
        issues: list[str] = []
        if not self.fighting_style_technical.strip():
            issues.append("missing_fighting_style_technical")
        if not self.next_fight_date.strip():
            issues.append("missing_next_fight_date")
        elif parse_fight_date(self.next_fight_date) is None:
            issues.append("invalid_next_fight_date")
        if not self.training_days:
            issues.append("missing_training_availability")
        if self.training_frequency < 1:
            issues.append("invalid_training_frequency")
        return issues
