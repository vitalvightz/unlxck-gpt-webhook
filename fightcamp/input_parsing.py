from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .injury_formatting import looks_like_guided_injury_text, parse_injuries_and_restrictions
from .rounds_format import assess_rounds_format
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

    if looks_like_guided_injury_text(cleaned):
        parts = [part.strip() for part in cleaned.split(";") if part.strip()]
        remaining: list[str] = []
        for part in parts:
            normalized_part = _normalize_injury_marker(part)
            if not normalized_part or normalized_part in _EMPTY_INJURY_MARKERS_NORMALIZED:
                continue
            remaining.append(part)
        return "; ".join(remaining)

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
    _normalize_label("Hard Sparring Days"): {
        _normalize_label("Hard sparring"),
        _normalize_label("Hard sparring days"),
        _normalize_label("Live sparring days"),
    },
    _normalize_label("Technical Skill Days"): {
        _normalize_label("Technical days"),
        _normalize_label("Technical skill days"),
        _normalize_label("Lighter skill days"),
        _normalize_label("Technical / lighter skill days"),
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
    return _extract_value(field) if field else ""


def _extract_date_value(field: dict) -> str:
    value = field.get("value")
    if isinstance(value, dict):
        for key in ("date", "value", "text", "label"):
            if key in value and value[key] is not None:
                return str(value[key]).strip()
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value).strip() if value is not None else ""


def get_date_value(label: str, fields: list[dict]) -> str:
    field = _find_field(label, fields)
    return _extract_date_value(field) if field else ""


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


_PLAN_FIELD_LABELS = {
    "full_name": "Full name",
    "age": "Age",
    "weight": "Weight (kg)",
    "target_weight": "Target Weight (kg)",
    "height": "Height (cm)",
    "fighting_style_technical": "Fighting Style (Technical)",
    "fighting_style_tactical": "Fighting Style (Tactical)",
    "stance": "Stance",
    "status": "Professional Status",
    "record": "Current Record",
    "athlete_timezone": "Athlete Time Zone",
    "athlete_locale": "Athlete Locale",
    "rounds_format": "Rounds x Minutes",
    "frequency_raw": "Weekly Training Frequency",
    "fatigue": "Fatigue Level",
    "equipment_access": "Equipment Access",
    "available_days": "Training Availability",
    "hard_sparring_days_raw": "Hard Sparring Days",
    "technical_skill_days_raw": "Technical Skill Days",
    "key_goals": "What are your key performance goals?",
    "weak_areas": "Where do you feel weakest right now?",
    "training_preference": "Do you prefer certain training styles?",
    "mental_block": "Do you struggle with any mental blockers or mindset challenges?",
    "notes": "Are there any parts of your previous plan you hated or loved?",
}


def _extract_fields(data: dict) -> list[dict]:
    fields = data.get("data", {}).get("fields") if isinstance(data, dict) else None
    if not isinstance(fields, list):
        raise ValueError("payload missing required data.fields list")
    return fields


def _get_plan_field_values(fields: list[dict]) -> dict[str, str]:
    return {name: get_value(label, fields) for name, label in _PLAN_FIELD_LABELS.items()}


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
    hard_sparring_days_raw: str
    technical_skill_days_raw: str
    injuries: str
    parsed_injuries: list[dict[str, str | None]]
    restrictions: list[ParsedRestriction]
    key_goals: str
    weak_areas: str
    training_preference: str
    mental_block: str
    notes: str
    training_days: list[str]
    hard_sparring_days: list[str]
    technical_skill_days: list[str]
    training_frequency: int
    weeks_out: int | str
    days_until_fight: int | None
    rounds_format_raw: str = ""
    rounds_format_warning: str = ""

    @classmethod
    def from_payload(cls, data: dict) -> "PlanInput":
        fields = _extract_fields(data)
        values = _get_plan_field_values(fields)
        values = {**values}
        rounds_format_raw = values["rounds_format"]
        tech_styles = _normalize_list(values["fighting_style_technical"])
        rounds_assessment = assess_rounds_format(
            rounds_format_raw,
            sport=tech_styles[0] if tech_styles else "",
        )
        values["rounds_format"] = rounds_assessment.normalized or values["rounds_format"]
        next_fight_date = get_date_value("When is your next fight?", fields)
        injuries = normalize_injury_text(
            get_value("Any injuries or areas you need to work around?", fields)
        )
        parsed_injuries, parsed_restrictions = parse_injuries_and_restrictions(injuries or "")

        training_days = [d.strip() for d in values["available_days"].split(",") if d.strip()]
        hard_sparring_days = [
            d.strip() for d in values["hard_sparring_days_raw"].split(",") if d.strip()
        ]
        technical_skill_days = [
            d.strip() for d in values["technical_skill_days_raw"].split(",") if d.strip()
        ]
        try:
            training_frequency = int(values["frequency_raw"])
        except (TypeError, ValueError):
            training_frequency = len(training_days)

        weeks_out: int | str = "N/A"
        days_until_fight = None
        fight_date = parse_fight_date(next_fight_date) if next_fight_date else None
        if fight_date:
            days_until_fight = _compute_days_until_fight(
                next_fight_date,
                fight_date,
                athlete_timezone=values["athlete_timezone"],
            )
            weeks_out = max(1, days_until_fight // 7) if days_until_fight is not None else "N/A"

        return cls(
            **values,
            next_fight_date=next_fight_date,
            injuries=injuries,
            parsed_injuries=parsed_injuries,
            restrictions=parsed_restrictions,
            training_days=training_days,
            hard_sparring_days=hard_sparring_days,
            technical_skill_days=technical_skill_days,
            training_frequency=training_frequency,
            weeks_out=weeks_out,
            days_until_fight=days_until_fight,
            rounds_format_raw=rounds_format_raw,
            rounds_format_warning=rounds_assessment.warning or "",
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
