from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dateutil.tz import gettz

from .injury_formatting import parse_injuries_and_restrictions, parse_injury_entry
from .normalization import normalize_injury_marker as _normalize_injury_marker
from .normalization import normalize_label as _normalize_label
from .restriction_parsing import ParsedRestriction, parse_restriction_entry


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
_EXPLICIT_TZ_SUFFIX_PATTERN = re.compile(r"(?:Z|[+-]\d{2}(?::?\d{2})?)$")
_PLATFORM_DEFAULT_TIMEZONE = timezone.utc

ProvenanceSource = Literal["user_supplied", "system_inferred", "defaulted_missing"]


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

    dateutil_tz = gettz(normalized)
    if dateutil_tz is not None:
        return dateutil_tz

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


def _business_timezone(athlete_timezone: str | None = None) -> timezone | ZoneInfo:
    resolved = _resolve_timezone(athlete_timezone)
    if resolved is not None:
        return resolved
    return _PLATFORM_DEFAULT_TIMEZONE


def _normalized_timezone_name(tzinfo: timezone | ZoneInfo) -> str:
    if tzinfo == timezone.utc:
        return "UTC"
    if isinstance(tzinfo, ZoneInfo):
        return tzinfo.key
    name = tzinfo.tzname(None)
    return name or "UTC"


def _platform_default_timezone_name() -> str:
    return _normalized_timezone_name(_PLATFORM_DEFAULT_TIMEZONE)


def _athlete_calendar_now(
    athlete_timezone: str | None = None, *, now_utc: datetime | None = None
) -> datetime:
    tzinfo = _business_timezone(athlete_timezone)
    reference_utc = now_utc or _utc_now()
    if reference_utc.tzinfo is None:
        reference_utc = reference_utc.replace(tzinfo=timezone.utc)
    else:
        reference_utc = reference_utc.astimezone(timezone.utc)
    return reference_utc.astimezone(tzinfo).replace(tzinfo=None)


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


@dataclass(frozen=True)
class GuidedInjury:
    area: str = ""
    severity: str = ""
    trend: str = ""
    avoid: str = ""
    notes: str = ""

    def has_content(self) -> bool:
        return any([self.area, self.severity, self.trend, self.avoid, self.notes])


_GUIDED_TRIGGER_PREFIX = re.compile(
    r"^(?:avoid|limit|reduce|no|dont|don't|do not|cannot|can't|cant|restricted|restriction)\b",
    re.IGNORECASE,
)
_GUIDED_LATERALITY_PREFIX = re.compile(r"^\s*(left|right)\s+", re.IGNORECASE)
_GUIDED_SEVERITY_MAP = {
    "low": "mild",
    "mild": "mild",
    "moderate": "moderate",
    "high": "severe",
    "severe": "severe",
}
_GUIDED_STRUCTURAL_NOTE_PATTERN = re.compile(
    r"\b(?:acl|tear|rupture|reconstruction|dislocation|fracture|concussion)\b",
    re.IGNORECASE,
)


def _extract_guided_injury(data: dict) -> GuidedInjury | None:
    if not isinstance(data, dict):
        return None

    raw_value = data.get("guided_injury")
    if not isinstance(raw_value, dict):
        nested_data = data.get("data")
        if isinstance(nested_data, dict):
            raw_value = nested_data.get("guided_injury")
    if not isinstance(raw_value, dict):
        return None

    guided = GuidedInjury(
        area=str(raw_value.get("area") or "").strip(),
        severity=str(raw_value.get("severity") or "").strip(),
        trend=str(raw_value.get("trend") or "").strip(),
        avoid=str(raw_value.get("avoid") or "").strip(),
        notes=str(raw_value.get("notes") or "").strip(),
    )
    return guided if guided.has_content() else None


def _extract_guided_injuries(data: dict) -> list[GuidedInjury]:
    if not isinstance(data, dict):
        return []

    raw_value = data.get("guided_injuries")
    if not isinstance(raw_value, list):
        nested_data = data.get("data")
        if isinstance(nested_data, dict):
            raw_value = nested_data.get("guided_injuries")
    if not isinstance(raw_value, list):
        return []

    injuries: list[GuidedInjury] = []
    for entry in raw_value:
        if not isinstance(entry, dict):
            continue
        guided = GuidedInjury(
            area=str(entry.get("area") or "").strip(),
            severity=str(entry.get("severity") or "").strip(),
            trend=str(entry.get("trend") or "").strip(),
            avoid=str(entry.get("avoid") or "").strip(),
            notes=str(entry.get("notes") or "").strip(),
        )
        if guided.has_content():
            injuries.append(guided)
    return injuries


def _strip_guided_laterality(area: str, laterality: str | None) -> str:
    cleaned = str(area or "").strip()
    if not cleaned or not laterality:
        return cleaned
    return _GUIDED_LATERALITY_PREFIX.sub("", cleaned, count=1).strip() or cleaned


def _parse_guided_injury(guided_injury: GuidedInjury) -> tuple[list[dict[str, str | None]], list[ParsedRestriction]]:
    injuries: list[dict[str, str | None]] = []
    restrictions: list[ParsedRestriction] = []

    if guided_injury.area:
        injury_entry = parse_injury_entry(guided_injury.area)
        if injury_entry is None:
            injury_entry = {
                "injury_type": "unspecified",
                "canonical_location": None,
                "side": None,
                "laterality": None,
                "original_phrase": guided_injury.area,
            }

        laterality = injury_entry.get("laterality") or injury_entry.get("side")
        display_location = _strip_guided_laterality(guided_injury.area, laterality)
        if display_location:
            injury_entry["display_location"] = display_location

        mapped_severity = _GUIDED_SEVERITY_MAP.get(guided_injury.severity.lower())
        if mapped_severity:
            injury_entry["severity"] = mapped_severity

        if guided_injury.notes:
            injury_entry["notes"] = guided_injury.notes
            if _GUIDED_STRUCTURAL_NOTE_PATTERN.search(guided_injury.notes):
                injury_entry["original_phrase"] = f"{guided_injury.area}. Notes: {guided_injury.notes}"
        injuries.append(injury_entry)

    if guided_injury.avoid:
        restriction_phrase = guided_injury.avoid
        if not _GUIDED_TRIGGER_PREFIX.match(restriction_phrase):
            restriction_phrase = f"avoid {restriction_phrase}"
        restriction = parse_restriction_entry(restriction_phrase)
        if restriction is not None:
            if restriction.get("region") is None and injuries:
                restriction["region"] = injuries[0].get("canonical_location")
            restrictions.append(restriction)

    return injuries, restrictions


def _parse_guided_injuries(
    guided_injuries: list[GuidedInjury],
) -> tuple[list[dict[str, str | None]], list[ParsedRestriction]]:
    parsed_injuries: list[dict[str, str | None]] = []
    parsed_restrictions: list[ParsedRestriction] = []
    for guided_injury in guided_injuries:
        injuries, restrictions = _parse_guided_injury(guided_injury)
        parsed_injuries.extend(injuries)
        parsed_restrictions.extend(restrictions)
    return parsed_injuries, parsed_restrictions


def _compute_days_until_fight(
    raw_value: str,
    fight_date: datetime,
    *,
    athlete_timezone: str | None = None,
    now_utc: datetime | None = None,
) -> int | None:
    business_tz = _business_timezone(athlete_timezone)
    reference = _athlete_calendar_now(athlete_timezone, now_utc=now_utc)
    fight_local_date = _fight_local_date(raw_value, fight_date, business_tz)
    raw_days = (fight_local_date - reference.date()).days
    return normalize_days_until_fight(raw_days)


def _has_explicit_timezone(raw_value: str) -> bool:
    return bool(_EXPLICIT_TZ_SUFFIX_PATTERN.search((raw_value or "").strip()))


def _fight_local_date(
    raw_value: str,
    fight_date: datetime,
    business_timezone: timezone | ZoneInfo,
) -> datetime.date:
    raw = (raw_value or "").strip()
    if _DATE_ONLY_PATTERN.match(raw):
        return fight_date.date()
    if _has_explicit_timezone(raw):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(business_timezone).date()
        except ValueError:
            pass
    return fight_date.date()


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
    guided_injury: GuidedInjury | None
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
    parsing_metadata: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, data: dict) -> "PlanInput":
        def _metadata(source: ProvenanceSource, reason: str | None = None) -> dict[str, str]:
            metadata = {"source": source}
            if reason:
                metadata["reason"] = reason
            return metadata

        fields = _extract_fields(data)
        values = _get_plan_field_values(fields)

        raw_available_days = values["available_days"]
        raw_frequency = values["frequency_raw"]
        raw_athlete_timezone = values["athlete_timezone"].strip()

        # Normalization step (safe, non-planning transforms only).
        next_fight_date = get_date_value("When is your next fight?", fields)
        injuries = normalize_injury_text(
            get_value("Any injuries or areas you need to work around?", fields)
        )
        guided_injuries = _extract_guided_injuries(data)
        if guided_injuries:
            guided_injury = guided_injuries[0]
            parsed_injuries, parsed_restrictions = _parse_guided_injuries(guided_injuries)
        else:
            guided_injury = _extract_guided_injury(data)
            if guided_injury is not None:
                parsed_injuries, parsed_restrictions = _parse_guided_injury(guided_injury)
            else:
                parsed_injuries, parsed_restrictions = parse_injuries_and_restrictions(injuries or "")
        if guided_injuries:
            guided_injury = guided_injuries[0]
            parsed_injuries, parsed_restrictions = _parse_guided_injuries(guided_injuries)
        elif guided_injury is not None:
            parsed_injuries, parsed_restrictions = _parse_guided_injury(guided_injury)
        else:
            parsed_injuries, parsed_restrictions = parse_injuries_and_restrictions(injuries or "")

        training_days = [d.strip() for d in raw_available_days.split(",") if d.strip()]
        hard_sparring_days = [
            d.strip() for d in values["hard_sparring_days_raw"].split(",") if d.strip()
        ]
        technical_skill_days = [
            d.strip() for d in values["technical_skill_days_raw"].split(",") if d.strip()
        ]

        # Validation step (planning-critical contract).
        if next_fight_date:
            fight_date = parse_fight_date(next_fight_date)
            if fight_date is None:
                raise ValueError(f"invalid fight date format: {next_fight_date}")
        else:
            fight_date = None

        if raw_frequency.strip():
            try:
                training_frequency = int(raw_frequency)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid Weekly Training Frequency: expected integer, got {raw_frequency!r}"
                ) from exc
            if training_frequency < 1:
                raise ValueError(
                    f"invalid Weekly Training Frequency: expected integer >= 1, got {training_frequency}"
                )
            training_frequency_metadata = _metadata("user_supplied")
        else:
            # Explicit inference step.
            training_frequency = len(training_days)
            training_frequency_metadata = _metadata(
                "system_inferred",
                "weekly_training_frequency_missing_inferred_from_training_availability",
            )

        available_days_metadata = (
            _metadata("user_supplied")
            if raw_available_days.strip()
            else _metadata("defaulted_missing", "training_availability_missing")
        )

        fallback_timezone_name = _platform_default_timezone_name()
        if not raw_athlete_timezone:
            effective_athlete_timezone = fallback_timezone_name
            athlete_timezone_metadata = _metadata("defaulted_missing", "athlete_timezone_missing")
        elif _resolve_timezone(raw_athlete_timezone) is None:
            effective_athlete_timezone = fallback_timezone_name
            athlete_timezone_metadata = _metadata(
                "defaulted_missing",
                "invalid_athlete_timezone_fallback_to_platform_default",
            )
        else:
            effective_athlete_timezone = raw_athlete_timezone
            athlete_timezone_metadata = _metadata("user_supplied")

        weeks_out: int | str = "N/A"
        days_until_fight = None
        if fight_date:
            days_until_fight = _compute_days_until_fight(
                next_fight_date,
                fight_date,
                athlete_timezone=effective_athlete_timezone,
            )
            weeks_out = max(1, days_until_fight // 7) if days_until_fight is not None else "N/A"

        normalized_values = {**values, "athlete_timezone": effective_athlete_timezone}

        return cls(
            **normalized_values,
            next_fight_date=next_fight_date,
            injuries=injuries,
            guided_injury=guided_injury,
            parsed_injuries=parsed_injuries,
            restrictions=parsed_restrictions,
            training_days=training_days,
            hard_sparring_days=hard_sparring_days,
            technical_skill_days=technical_skill_days,
            training_frequency=training_frequency,
            weeks_out=weeks_out,
            days_until_fight=days_until_fight,
            parsing_metadata={
                "training_frequency": training_frequency_metadata,
                "available_days": available_days_metadata,
                "athlete_timezone": athlete_timezone_metadata,
            },
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
        if not self.training_days:
            issues.append("missing_training_availability")
        if self.training_frequency < 1:
            issues.append("invalid_training_frequency")
        return issues
