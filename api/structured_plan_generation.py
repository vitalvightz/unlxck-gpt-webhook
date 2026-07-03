"""Stage 2 → ``StructuredTrainingPlan`` bridge.

This module connects the existing Stage 2 plan generation to the new structured
plan schema (see ``api/structured_plan_models.py``). It is deliberately additive:
structured generation runs *beside* the legacy raw-text flow and never replaces
it. If structured generation is skipped, fails, or produces invalid JSON, the
raw ``plan_text`` remains the fallback and plan generation is never blocked.

Two concerns live here:

* :func:`build_structured_plan_outcome` — the pure, network-free validation flow
  (validate → one repair retry → raw-markdown fallback) that turns a candidate
  structured payload into a persistable outcome plus an admin/debug status. It
  reuses :func:`safe_parse_structured_plan` and :func:`repair_structured_plan_once`.
* :func:`build_structured_plan_prompt` — the instruction text that tells the
  model what a schema-compatible ``StructuredTrainingPlan`` JSON object must look
  like. The actual model call lives in ``api/stage2_automation.py``.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, get_args

from .state_machine import is_athlete_displayable_plan_status
from .structured_plan_faithfulness import check_structured_faithfulness
from .structured_plan_safety import athlete_safe_support, audit_structured_plan
from .structured_plan_models import (
    SCHEMA_VERSION,
    BlockType,
    CompletionStatus,
    DailyCheckIn,
    DayType,
    EventType,
    LoadFocusValue,
    PhaseLabel,
    PlanNoteCategory,
    PlanStatus,
    PlanType,
    EffortMethod,
    ReadinessStatus,
    RedFlagWhen,
    RiskLevel,
    SessionType,
    Severity,
    UnitsSystem,
    WeekType,
    repair_structured_plan_once,
    safe_parse_structured_plan,
)

# Admin/debug status describing what happened to the structured-plan attempt.
StructuredPlanStatus = Literal[
    "not_attempted",
    "valid",
    "repair_attempted_valid",
    "invalid_fallback_used",
]

# Biometric / wearable-style keys the structured plan must never carry. Readiness
# is self-report only (no HRV/CNS/WHOOP-style scores — see the schema module). If
# a model hallucinates one of these, it is stripped before validation so it can
# never be persisted.
BANNED_BIOMETRIC_KEYS: frozenset[str] = frozenset(
    {
        "hrv",
        "hrv_score",
        "hrv_ms",
        "cns",
        "cns_recovery",
        "cns_recovery_percent",
        "cns_percent",
        "whoop_recovery",
        "whoop_recovery_score",
        "whoop_score",
        "recovery_score",
        "readiness_score",
        "strain",
        "strain_score",
        "resting_heart_rate",
    }
)


@dataclass
class StructuredPlanOutcome:
    """Result of attempting to produce a validated structured plan.

    ``structured_plan`` is a JSON-ready dict (only on a valid/repaired outcome);
    it is ``None`` whenever the raw ``plan_text`` fallback must be used so an
    invalid payload is never persisted. ``errors``/``status`` feed admin debug.
    """

    status: StructuredPlanStatus
    structured_plan: dict[str, Any] | None = None
    schema_version: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_debug(self) -> dict[str, Any]:
        """Compact admin/debug view persisted alongside the validator report."""
        return {
            "status": self.status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "schema_version": self.schema_version,
        }


def _plan_has_structured_plan(plan: dict[str, Any]) -> bool:
    value = plan.get("structured_plan")
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value)
    return True


def _approved_plan_text(plan: dict[str, Any]) -> str:
    """The athlete-facing/final plan text that is the source of truth."""
    return str(plan.get("final_plan_text") or plan.get("plan_text") or "").strip()


def should_attempt_structured_plan(plan: Any, env_enabled: bool) -> bool:
    """Whether to build a ``structured_plan`` for this plan-like object.

    Centralizes the trigger so it is driven by the canonical state machine
    (:func:`api.state_machine.is_athlete_displayable_plan_status`), never by
    hardcoded Stage 2 statuses such as ``stage2_pass``/``admin_review_approved``.
    Returns ``True`` only when ALL of the following hold:

    1. ``env_enabled`` is set (``UNLXCK_STAGE2_STRUCTURED_PLAN=1``).
    2. No ``structured_plan`` is stored yet (idempotent — never overwrites).
    3. An approved/final ``plan_text`` exists to convert (source of truth).
    4. The plan status is athlete-displayable/publishable (``ready`` /
       ``publishable_with_flags``). Blocked, held, medical-gated, review-required,
       and archived states are excluded so nothing is published merely to derive
       structured output.

    Accepts either a Stage 2 result dict or a persisted plan row.
    """

    if not env_enabled:
        return False
    if not isinstance(plan, dict):
        return False
    if _plan_has_structured_plan(plan):
        return False
    if not _approved_plan_text(plan):
        return False
    return is_athlete_displayable_plan_status(plan.get("status"))


# Structured-plan attempt statuses that count as a successfully validated card.
# ``invalid_fallback_used`` / ``not_attempted`` are excluded: they mean the raw
# plan_text fallback is in play, so there is no schema-valid card to trust.
_CLEAN_STRUCTURED_PLAN_STATUSES: frozenset[StructuredPlanStatus] = frozenset(
    {"valid", "repair_attempted_valid"}
)


def has_clean_structured_card(plan: Any) -> bool:
    """True when ``plan`` carries a schema-valid structured card.

    A clean card is a non-empty ``structured_plan`` dict whose recorded attempt
    status validated (``valid`` or ``repair_attempted_valid``). It is used as a
    trust signal: a plan that produced a schema-valid card is treated as
    publishable rather than held for non-safety findings. Accepts either a
    Stage 2 result dict or a persisted plan row (the attempt status lives under
    ``stage2_validator_report.structured_plan.status`` in both).
    """

    if not isinstance(plan, dict):
        return False
    card = plan.get("structured_plan")
    if not isinstance(card, dict) or not card:
        return False
    report = plan.get("stage2_validator_report")
    debug = report.get("structured_plan") if isinstance(report, dict) else None
    status = debug.get("status") if isinstance(debug, dict) else None
    return status in _CLEAN_STRUCTURED_PLAN_STATUSES


def strip_biometric_fields(data: Any) -> tuple[Any, list[str]]:
    """Recursively drop banned biometric keys.

    Returns ``(cleaned, removed_paths)``. The input is not mutated.
    """

    removed: list[str] = []

    def _walk(node: Any, path: str) -> Any:
        if isinstance(node, dict):
            cleaned: dict[Any, Any] = {}
            for key, value in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                if isinstance(key, str) and key.strip().lower() in BANNED_BIOMETRIC_KEYS:
                    removed.append(child_path)
                    continue
                cleaned[key] = _walk(value, child_path)
            return cleaned
        if isinstance(node, list):
            return [_walk(item, f"{path}[{index}]") for index, item in enumerate(node)]
        return node

    return _walk(data, ""), removed


# ---------------------------------------------------------------------------
# Conservative normalization
#
# The structured conversion model occasionally returns the right plan in a
# slightly-wrong shape (enum aliases, loads/rests as strings, countdown labels as
# strings, a non-list daily_check_ins, a missing required meta field). These are
# *formatting* mistakes, not content mistakes. The normalizer below fixes only
# those, using neutral structural defaults. It NEVER invents training content —
# no exercises, sessions, blocks, loads, dates, biometrics, or weight-cut
# instructions — and it never touches raw_markdown_fallback content. If a value
# cannot be coerced safely it is dropped (e.g. an unparseable load → null), and
# the strict Pydantic schema still decides validity afterwards.
# ---------------------------------------------------------------------------

# Allowed enum value sets are derived from the schema's Literal aliases so they
# can never drift from api/structured_plan_models.py.
_PLAN_TYPE_VALUES = frozenset(get_args(PlanType))
_PLAN_STATUS_VALUES = frozenset(get_args(PlanStatus))
_UNITS_VALUES = frozenset(get_args(UnitsSystem))
_EVENT_TYPE_VALUES = frozenset(get_args(EventType))
_SEVERITY_VALUES = frozenset(get_args(Severity))
_RED_FLAG_WHEN_VALUES = frozenset(get_args(RedFlagWhen))
_PHASE_VALUES = frozenset(get_args(PhaseLabel))
_LOAD_FOCUS_VALUES = frozenset(get_args(LoadFocusValue))
_WEEK_TYPE_VALUES = frozenset(get_args(WeekType))
_DAY_TYPE_VALUES = frozenset(get_args(DayType))
_READINESS_VALUES = frozenset(get_args(ReadinessStatus))
_SESSION_TYPE_VALUES = frozenset(get_args(SessionType))
_COMPLETION_VALUES = frozenset(get_args(CompletionStatus))
_BLOCK_TYPE_VALUES = frozenset(get_args(BlockType))
_RISK_LEVEL_VALUES = frozenset(get_args(RiskLevel))
_PLAN_NOTE_CATEGORY_VALUES = frozenset(get_args(PlanNoteCategory))
_EFFORT_METHOD_VALUES = frozenset(get_args(EffortMethod))

# Conservative enum aliases for the most common loose values.
_SESSION_TYPE_ALIASES = {
    "strength": "strength_power",
    "power": "strength_power",
    "strength_and_conditioning": "strength_power",
    "s&c": "strength_power",
    "cardio": "conditioning",
    "technical": "skill",
    "spar": "sparring",
    "fight": "fight_or_match",
    "match": "fight_or_match",
    "rest": "recovery",
    "warmup": "primer",
    "warm-up": "primer",
}
_EFFORT_METHOD_ALIASES = {
    "rpe": "RPE",
    "rir": "RIR",
    "hr_zone": "heart_rate_zone",
    "heart_rate": "heart_rate_zone",
}
_BLOCK_TYPE_ALIASES = {
    "warmup": "preparation",
    "warm-up": "preparation",
    "warm_up": "preparation",
    "prep": "preparation",
    "mobility": "mobility_activation",
    "activation": "mobility_activation",
    "plyo": "plyometric_power",
    "plyometrics": "plyometric_power",
    "power": "plyometric_power",
    "cooldown": "cooldown_recovery",
    "cool-down": "cooldown_recovery",
    "cool_down": "cooldown_recovery",
    "recovery": "cooldown_recovery",
}

# --- day_type (intensity badge) classification -----------------------------
#
# day_type is the athlete-facing intensity badge (high / moderate / low / ...).
# The conversion model guesses it from prose and lands on the wrong bucket often;
# worse, the old normalizer silently defaulted *every* unrecognized value (e.g.
# "primer", "light", "easy") to "moderate", which reads as risky one day before a
# fight even when the session is a light primer. Instead we derive the badge
# deterministically from the day's actual content — session types and per-block
# effort (RPE), load (%1RM), and intensity tags — and a day is rated as hard as
# its hardest *real* work block. Categorical days (competition, rest, recovery,
# travel, reintegration) are detected first and never collapsed into an intensity
# bucket. The model's value is only consulted as a last-resort fallback, and even
# then an unreadable day falls to "low" rather than silently "moderate".

# Block intensity tags that read as hard / easy regardless of the numbers.
# "explosive" is deliberately excluded: taper/primer work is often "explosive"
# but low-volume, high-intent and light, so it must not auto-flag a hard day —
# the block's RPE/load decides.
_HIGH_INTENSITY_WORDS = frozenset(
    {"max", "maximal", "near_max", "very_high", "high"}
)
_LOW_INTENSITY_WORDS = frozenset(
    {"none", "very_low", "low", "easy", "light", "primer", "recovery"}
)
# Max-output block types: when a block carries no readable effort/load number,
# their presence still implies a high-CNS day (true power/speed work).
_HIGH_OUTPUT_BLOCK_TYPES = frozenset({"plyometric_power", "speed", "strength_speed"})
# Session types that are intrinsically light when they carry no measurable block.
_LOW_SESSION_TYPES = frozenset({"primer", "recovery", "rehab"})
_INTENSITY_RANK = {"low": 1, "moderate": 2, "high": 3}

_DURATION_UNIT_ALIASES = {
    "s": "seconds",
    "sec": "seconds",
    "secs": "seconds",
    "second": "seconds",
    "seconds": "seconds",
    "m": "minutes",
    "min": "minutes",
    "mins": "minutes",
    "minute": "minutes",
    "minutes": "minutes",
    "h": "hours",
    "hr": "hours",
    "hrs": "hours",
    "hour": "hours",
    "hours": "hours",
}

_COUNTDOWN_RE = re.compile(r"^[Dd]\s*([+-]?\d+)$")
_MEASURED_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)\s*$")
# First number or numeric range in a string. group(2) is the upper bound of a
# range ("7-8" → 8) and is ``None`` for a lone number ("7" → group(1) = 7).
_NUMBER_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)(?:\s*[-–—]\s*(\d+(?:\.\d+)?))?")
# Capture a percentage anywhere in the string plus an optional trailing reference
# such as "1RM" or "of 1RM" (bank prescriptions read like "3x5 @ 75-85% 1RM").
# group(2) is optional and may be ``None`` — callers must guard it.
_LOAD_PERCENT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:of\s+)?([A-Za-z0-9]+)?")

# Distance units are mapped separately from duration units because a bare "m"
# means metres for a distance field but minutes for a duration field; the field's
# default_unit selects which alias table applies.
_DISTANCE_UNIT_ALIASES = {
    "m": "meters",
    "meter": "meters",
    "metre": "meters",
    "meters": "meters",
    "metres": "meters",
    "km": "kilometers",
    "mi": "miles",
    "mile": "miles",
    "miles": "miles",
    "yd": "yards",
    "yard": "yards",
    "yards": "yards",
}
_TIME_UNITS = frozenset({"seconds", "minutes", "hours"})


def _coerce_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_coerce_str(item) for item in value).strip()
    if isinstance(value, dict):
        return ""
    return str(value)


def _coerce_nonempty_str(value: Any, default: str) -> str:
    text = _coerce_str(value).strip()
    return text or default


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return default
    return default


def _coerce_optional_int(value: Any) -> int | None:
    """Coerce to ``int`` without inventing a value: return ``None`` when not safe.

    Unlike :func:`_coerce_int` this has no default — a missing, non-numeric, or
    fractional value yields ``None`` so callers can drop the surrounding entry
    rather than substituting a fabricated score.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else None
    return None


def _coerce_float(value: Any) -> float | None:
    """Best-effort float, reading the *upper* bound of the first range in a string.

    "RPE 7-8" → 8, "3-4" → 4, "85% 1RM" → 85. Ranges resolve to their upper bound
    because an athlete given a 7-8 block may actually work at 8, so the intensity
    badge should reflect the harder end. Returns ``None`` when no number is
    present so callers can tell "no signal" from a real zero.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _NUMBER_RANGE_RE.search(value)
        if match:
            try:
                return float(match.group(2) or match.group(1))
            except ValueError:
                return None
    return None


def _enum(value: Any, allowed: frozenset[str], default: str, aliases: dict[str, str] | None = None) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate in allowed:
            return candidate
        lowered = candidate.lower()
        if lowered in allowed:
            return lowered
        if aliases and lowered in aliases:
            return aliases[lowered]
    return default


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _normalize_countdown_label(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        out = dict(item)
        label = _coerce_str(out.get("label"))
        out["label"] = label
        out["date"] = _coerce_str(out.get("date"))
        out["anchor"] = _coerce_nonempty_str(out.get("anchor"), "event_countdown")
        if not isinstance(out.get("days_to_event"), int) or isinstance(out.get("days_to_event"), bool):
            out["days_to_event"] = _days_from_label(label)
        return out
    if isinstance(item, str):
        label = item.strip()
        return {
            "date": "",
            "days_to_event": _days_from_label(label),
            "label": label,
            "anchor": "event_countdown",
        }
    return None


def _days_from_label(label: str) -> int:
    match = _COUNTDOWN_RE.match(label.strip())
    if not match:
        return 0
    # "D-28" → 28 days remaining; "D0" → 0; "D+1" → -1 (after the event).
    return -int(match.group(1))


def _normalize_load(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"method": "absolute", "value": float(value), "unit": "kg", "display": str(value)}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        percent = _LOAD_PERCENT_RE.search(text)
        if percent:
            load = {
                "method": "percentage",
                "value": float(percent.group(1)),
                "unit": "percent",
                "display": text,
            }
            # group(2) is optional, so guard it before use; carry a bank-style
            # reference (e.g. "1RM") through when present.
            ref = (percent.group(2) or "").strip()
            if ref:
                load["ref"] = ref
            return load
        if text.lower() in {"bodyweight", "bw", "body weight", "bodyweight only"}:
            return {"method": "bodyweight", "value": 0, "unit": "bodyweight", "display": "bodyweight"}
    return None


def _normalize_measured(value: Any, default_unit: str = "seconds") -> dict[str, Any] | None:
    """Coerce a measured value into ``{"value", "unit"}``.

    ``default_unit`` is used for bare numbers and plain numeric strings so a
    bank-style ``work_sec``/``rest_sec`` int maps to seconds, ``total_minutes``
    to minutes, and a distance to meters. A string carrying its own unit is
    parsed and the unit aliased within the field's dimension (time vs distance).
    Unparseable values return ``None``.
    """

    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"value": float(value), "unit": default_unit}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:  # plain numeric string ("90", "2.5") → default unit for the field
            return {"value": float(text), "unit": default_unit}
        except ValueError:
            pass
        match = _MEASURED_RE.match(text)
        if match:
            raw_unit = match.group(2).strip().lower()
            if default_unit in _TIME_UNITS:
                unit = _DURATION_UNIT_ALIASES.get(raw_unit, raw_unit)
            elif default_unit == "meters":
                unit = _DISTANCE_UNIT_ALIASES.get(raw_unit, raw_unit)
            else:
                unit = raw_unit
            return {"value": float(match.group(1)), "unit": unit}
    return None


def _normalize_phase(value: Any) -> str:
    if isinstance(value, str):
        upper = value.strip().upper()
        if upper in _PHASE_VALUES:
            return upper
    return "GPP"


def _coerce_str_list(value: Any) -> list[str]:
    """Clean list of non-empty strings; a lone string is wrapped into a list."""
    if isinstance(value, list):
        return [text for text in (_coerce_str(entry).strip() for entry in value) if text]
    text = _coerce_str(value).strip()
    return [text] if text else []


def _normalize_mindset(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["intent"] = _coerce_str(out.get("intent"))
    out["focus_cue"] = _coerce_str(out.get("focus_cue"))
    out["reset_cue"] = _coerce_str(out.get("reset_cue"))
    # Optional anchors: keep when the source provides them, else leave unset (None).
    for optional_key in ("confidence_anchor", "context"):
        if out.get(optional_key) is not None:
            out[optional_key] = _coerce_str(out.get(optional_key))
    return out


def _normalize_effort(value: Any) -> dict[str, Any] | None:
    """Effort as an ``EffortPrescription`` dict; tolerate a bare "RPE 7-8" string.

    A dict keeps its value (the schema allows float or str) and only has its
    method aliased onto the enum. A bare string or number becomes an RPE/RIR
    prescription when a number can be read from it; anything unreadable becomes
    None (the field is optional) instead of failing the card.
    """
    if isinstance(value, dict):
        out = dict(value)
        out["method"] = _enum(out.get("method"), _EFFORT_METHOD_VALUES, "RPE", _EFFORT_METHOD_ALIASES)
        if not isinstance(out.get("value"), (int, float, str)) or isinstance(out.get("value"), bool):
            number = _coerce_float(out.get("value"))
            if number is None:
                return None
            out["value"] = number
        if out.get("scale") is not None:
            out["scale"] = _coerce_str(out.get("scale")).strip() or None
        return out
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return {"method": "RPE", "value": float(value), "scale": "1-10"}
    if isinstance(value, str):
        number = _coerce_float(value)
        if number is None:
            return None
        method = "RIR" if re.search(r"\brir\b", value, re.I) else "RPE"
        return {"method": method, "value": number, "scale": "1-10" if method == "RPE" else None}
    return None


def _normalize_block(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["block_id"] = _coerce_nonempty_str(out.get("block_id"), "block")
    out["block_type"] = _enum(out.get("block_type"), _BLOCK_TYPE_VALUES, "accessory", _BLOCK_TYPE_ALIASES)
    out["display_name"] = _coerce_str(out.get("display_name"))
    if "load" in out:
        out["load"] = _normalize_load(out.get("load"))
    # Per-field default units follow the bank conventions: work/rest in seconds
    # (work_sec/rest_sec), duration in minutes (total_minutes), distance in meters.
    for measured_key, default_unit in (
        ("rest", "seconds"),
        ("work", "seconds"),
        ("distance", "meters"),
        ("duration", "minutes"),
    ):
        if measured_key in out:
            out[measured_key] = _normalize_measured(out.get(measured_key), default_unit)
    # Carry coaching detail through, tolerating a single string instead of a
    # list. An explicit null must also become [] — the schema fields are
    # non-optional lists, so a passed-through None rejects the whole card.
    for list_key in ("coaching_cues", "regression_options", "substitutions"):
        if list_key in out:
            out[list_key] = _coerce_str_list(out.get(list_key))
    if "red_flags" in out:
        out["red_flags"] = [_normalize_red_flag(rule) for rule in _as_dict_list(out.get("red_flags"))]
    if "effort" in out:
        out["effort"] = _normalize_effort(out.get("effort"))
    if out.get("progression_rule") is not None:
        out["progression_rule"] = _coerce_str(out.get("progression_rule"))
    return out


def _normalize_session(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["session_id"] = _coerce_nonempty_str(out.get("session_id"), "session")
    out["session_type"] = _enum(out.get("session_type"), _SESSION_TYPE_VALUES, "mixed", _SESSION_TYPE_ALIASES)
    out["title"] = _coerce_str(out.get("title"))
    out["objective"] = _coerce_str(out.get("objective"))
    out["mindset_anchor"] = _normalize_mindset(out.get("mindset_anchor"))
    if "completion_status" in out:
        out["completion_status"] = _enum(out.get("completion_status"), _COMPLETION_VALUES, "not_started")
    if out.get("planned_duration") is not None:
        out["planned_duration"] = _normalize_measured(out.get("planned_duration"), "minutes")
    out["blocks"] = [_normalize_block(block) for block in _as_dict_list(out.get("blocks"))]
    return out


def _normalize_today_card(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["headline"] = _coerce_str(out.get("headline"))
    out["readiness_status"] = _enum(out.get("readiness_status"), _READINESS_VALUES, "train_as_planned")
    out["mindset_anchor"] = _normalize_mindset(out.get("mindset_anchor"))
    # Coach-owned contact that coexists with the day's app sessions — keep only a
    # non-empty string so the renderer never shows a blank contact block.
    contact = _coerce_str(out.get("coach_led_contact")).strip()
    if contact:
        out["coach_led_contact"] = contact
    else:
        out.pop("coach_led_contact", None)
    return out


_COACH_LED_CONTACT_RE = re.compile(
    r"\b(coach|spar|technical\s+only|no\s+hard\s+sparring|boxing|pad\s?work|pads|mitts?)\b",
    re.I,
)


def _coach_led_contact_label(session: dict[str, Any]) -> str | None:
    """A contact-only session label, or None when this is real app work."""
    if _as_list(session.get("blocks")):
        return None
    text = " ".join(
        part
        for part in (
            _coerce_str(session.get("title")).strip(),
            _coerce_str(session.get("objective")).strip(),
            _coerce_str(session.get("session_type")).strip(),
        )
        if part
    )
    if not text or not _COACH_LED_CONTACT_RE.search(text):
        return None
    return _coerce_str(session.get("title")).strip() or _coerce_str(session.get("objective")).strip() or text


def _fold_coach_led_sessions_into_today_card(day: dict[str, Any]) -> None:
    """Normalize same-day contact + app work into the renderer's canonical shape."""
    sessions = [session for session in _as_list(day.get("sessions")) if isinstance(session, dict)]
    if len(sessions) < 2:
        return
    app_sessions: list[dict[str, Any]] = []
    contact_labels: list[str] = []
    for session in sessions:
        label = _coach_led_contact_label(session)
        if label:
            contact_labels.append(label)
        else:
            app_sessions.append(session)
    if not contact_labels or not app_sessions:
        return
    card = day.get("today_card")
    if not isinstance(card, dict):
        card = _normalize_today_card(card)
        day["today_card"] = card
    if not _coerce_str(card.get("coach_led_contact")).strip():
        card["coach_led_contact"] = contact_labels[0]
    day["sessions"] = app_sessions


def _coach_led_contact_intensity(day: dict[str, Any]) -> str | None:
    card = day.get("today_card")
    if not isinstance(card, dict):
        return None
    text = _coerce_str(card.get("coach_led_contact")).strip().lower()
    if not text:
        return None
    if "technical" in text or "no hard" in text:
        return "moderate"
    if "reduced" in text or "deload" in text:
        return "low"
    if re.search(r"\bspar", text):
        return "high"
    if re.search(r"\b(coach|boxing|pad\s?work|pads|mitts?)\b", text):
        return "moderate"
    return None


def _block_intensity(block: Any) -> str | None:
    """Rate a single block "high" / "moderate" / "low", or ``None`` when silent.

    Reads, in priority order, the explicit intensity tag, the RPE effort, the
    %1RM load, and finally the block type. Explicit effort/load always wins over
    block type, so a light primer plyo (RPE 3–4) reads "low" rather than being
    flagged "high" just for being plyometric.
    """
    if not isinstance(block, dict):
        return None
    tag = _coerce_str(block.get("intensity")).strip().lower()
    effort = block.get("effort")
    rpe = None
    if isinstance(effort, dict) and str(effort.get("method") or "").upper() == "RPE":
        rpe = _coerce_float(effort.get("value"))
    if rpe is None and "rpe" in tag:  # an RPE buried in the tag ("rpe 3-4")
        rpe = _coerce_float(tag)
    pct = None
    load = block.get("load")
    if isinstance(load, dict) and str(load.get("method") or "") == "percentage":
        pct = _coerce_float(load.get("value"))

    # Explicit hard signals.
    if tag in _HIGH_INTENSITY_WORDS:
        return "high"
    if rpe is not None and rpe >= 8:
        return "high"
    if pct is not None and pct >= 85:
        return "high"

    # Explicit easy/moderate signals in priority order.
    if tag in _LOW_INTENSITY_WORDS:
        return "low"
    if rpe is not None:
        return "low" if rpe <= 5 else "moderate"
    if pct is not None:
        return "low" if pct < 70 else "moderate"
    if tag in {"moderate", "medium"}:
        return "moderate"
    # No effort/load number at all: a true power/speed block implies a hard day.
    if str(block.get("block_type") or "") in _HIGH_OUTPUT_BLOCK_TYPES:
        return "high"
    return None


def _session_intensity(session: Any) -> str | None:
    """Rate a session by its hardest block, falling back to the session type."""
    if not isinstance(session, dict):
        return None
    levels = [lvl for lvl in (_block_intensity(b) for b in _as_list(session.get("blocks"))) if lvl]
    if levels:
        return max(levels, key=_INTENSITY_RANK.__getitem__)
    stype = str(session.get("session_type") or "")
    if stype in _LOW_SESSION_TYPES:
        return "low"
    if stype == "sparring":
        return "high"
    return None


def _classify_day_type(day: dict[str, Any], fallback: str) -> str:
    """Derive the day's intensity badge from its content (overrides the model).

    ``fallback`` is the model's own value already coerced onto a valid enum (or
    ``""`` when it was missing/unrecognized). It is consulted only when the day
    carries no readable intensity signal at all.
    """
    sessions = [s for s in _as_list(day.get("sessions")) if isinstance(s, dict)]
    session_types = {str(s.get("session_type") or "") for s in sessions}

    # Competition / fight day is categorical, anchored on the countdown or a
    # fight session — never an intensity bucket.
    if _countdown_distance(day.get("countdown_label")) == 0 or "fight_or_match" in session_types:
        return "competition"
    # travel / reintegration are model-only states content cannot contradict.
    if fallback in {"travel", "reintegration"}:
        return fallback
    # A purely recovery day stays "recovery" even when its mobility/breathing/
    # cooldown work is broken into blocks — it is categorical, not an intensity.
    if session_types and session_types <= {"recovery"}:
        return "recovery"

    # The day is as hard as its hardest session. _session_intensity reads each
    # session by its hardest block and, for a session with no readable block,
    # falls back to its type (e.g. an empty coach-led sparring day is still
    # "high", never "rest").
    levels = [lvl for lvl in (_session_intensity(s) for s in sessions) if lvl]
    contact_level = _coach_led_contact_intensity(day)
    if contact_level:
        levels.append(contact_level)
    if levels:
        return max(levels, key=_INTENSITY_RANK.__getitem__)

    # No sessions / no readable signal at all: an empty day is "rest", otherwise
    # keep a valid model intensity guess, else default low (never silently
    # "moderate").
    if not sessions:
        return fallback if fallback in {"rest", "recovery"} else "rest"
    if fallback in {"high", "moderate", "low", "recovery", "rest"}:
        return fallback
    return "low"


def _countdown_distance(label: Any) -> int | None:
    """Parse the days-to-event from a countdown label (``D-1`` → 1, ``D0`` → 0)."""
    match = _COUNTDOWN_RE.match(_coerce_str(label).strip())
    if not match:
        return None
    try:
        return abs(int(match.group(1)))
    except ValueError:
        return None


def _normalize_day(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["date"] = _coerce_str(out.get("date"))
    out["countdown_label"] = _coerce_str(out.get("countdown_label"))
    out["phase_label"] = _normalize_phase(out.get("phase_label"))
    out["today_card"] = _normalize_today_card(out.get("today_card"))
    out["sessions"] = [_normalize_session(session) for session in _as_dict_list(out.get("sessions"))]
    _fold_coach_led_sessions_into_today_card(out)
    # Derive the intensity badge from the now-normalized content; the model's own
    # value is only a last-resort fallback (see _classify_day_type).
    out["day_type"] = _classify_day_type(out, _enum(out.get("day_type"), _DAY_TYPE_VALUES, ""))
    return out


def _normalize_load_focus(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    for key in ("volume", "intensity", "specificity", "fatigue_target"):
        out[key] = _enum(out.get(key), _LOAD_FOCUS_VALUES, "moderate")
    return out


def _normalize_progression(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["week_type"] = _enum(out.get("week_type"), _WEEK_TYPE_VALUES, "build")
    out["planned_change_from_previous"] = _coerce_str(out.get("planned_change_from_previous"))
    return out


def _normalize_week(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["week_id"] = _coerce_nonempty_str(out.get("week_id"), "week")
    out["week_index"] = _coerce_int(out.get("week_index"), 0)
    out["phase_label"] = _normalize_phase(out.get("phase_label"))
    out["week_goal"] = _coerce_str(out.get("week_goal"))
    out["start_date"] = _coerce_str(out.get("start_date"))
    out["end_date"] = _coerce_str(out.get("end_date"))
    out["load_focus"] = _normalize_load_focus(out.get("load_focus"))
    out["progression"] = _normalize_progression(out.get("progression"))
    out["days"] = [_normalize_day(day) for day in _as_dict_list(out.get("days"))]
    return out


def _normalize_plan_note(value: Any) -> dict[str, Any] | None:
    """Coerce a plan-level note, or ``None`` when it carries no text.

    Keeps only formatting fixes: the category is aliased onto a valid enum value
    (defaulting to ``general``), and label/text are coerced to strings. A note
    with no usable text is dropped rather than fabricated.
    """
    if isinstance(value, str):
        text = value.strip()
        return {"category": "general", "text": text} if text else None
    if not isinstance(value, dict):
        return None
    text = _coerce_str(value.get("text")).strip()
    if not text:
        return None
    out: dict[str, Any] = {
        "category": _enum(value.get("category"), _PLAN_NOTE_CATEGORY_VALUES, "general", {"weight cut": "weight_cut", "weight-cut": "weight_cut"}),
        "text": text,
    }
    label = _coerce_str(value.get("label")).strip()
    if label:
        out["label"] = label
    return out


def _normalize_plan_notes(value: Any) -> list[dict[str, Any]]:
    return [
        note
        for note in (_normalize_plan_note(item) for item in _as_list(value))
        if note is not None
    ]


def _normalize_red_flag(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["rule_id"] = _coerce_nonempty_str(out.get("rule_id"), "red_flag")
    out["when"] = _enum(out.get("when"), _RED_FLAG_WHEN_VALUES, "morning_check_in")
    out["severity"] = _enum(out.get("severity"), _SEVERITY_VALUES, "amber")
    out["display_text"] = _coerce_str(out.get("display_text"))
    out["action"] = _coerce_str(out.get("action"))
    # Machine fields arrive as prose fragments more often than schema shapes
    # ("threshold": ">20%", "applies_to": "all sessions"); the display_text is the
    # athlete-facing rule, so a threshold that can't be read becomes None rather
    # than failing the whole card.
    if "threshold" in out:
        out["threshold"] = _coerce_float(out.get("threshold"))
    for optional_key in ("metric", "metric_group", "operator", "logic"):
        if out.get(optional_key) is not None:
            out[optional_key] = _coerce_str(out.get(optional_key)).strip() or None
    if "applies_to" in out:
        out["applies_to"] = _coerce_str_list(out.get("applies_to"))
    if out.get("replacement_session_type") is not None:
        replacement = _enum(
            out.get("replacement_session_type"), _SESSION_TYPE_VALUES, "", _SESSION_TYPE_ALIASES
        )
        out["replacement_session_type"] = replacement or None
    return out


def _normalize_plan_metadata(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["title"] = _coerce_nonempty_str(out.get("title"), "Training Plan")
    out["sport"] = _coerce_str(out.get("sport"))
    out["plan_type"] = _enum(out.get("plan_type"), _PLAN_TYPE_VALUES, "general_performance")
    out["timezone"] = _coerce_nonempty_str(out.get("timezone"), "UTC")
    out["status"] = _enum(out.get("status"), _PLAN_STATUS_VALUES, "active")
    out["units"] = _enum(out.get("units"), _UNITS_VALUES, "metric")
    return out


def _normalize_athlete_context(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    out["sport_profile"] = _coerce_str(out.get("sport_profile"))
    for list_key in ("known_issues", "equipment_access"):
        if list_key in out:
            out[list_key] = _coerce_str_list(out.get(list_key))
    return out


def _normalize_event_context(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    out = dict(value)
    if out.get("event_type") is not None:
        out["event_type"] = _enum(out.get("event_type"), _EVENT_TYPE_VALUES, "none")
    return out


def _normalize_nutrition(value: Any) -> dict[str, Any]:
    out = dict(value) if isinstance(value, dict) else {}
    for key in ("summary", "daily_focus", "training_day_guidance", "fight_week_guidance"):
        out[key] = _coerce_str(out.get(key))
    warning = out.get("weight_cut_warning")
    if isinstance(warning, dict):
        warning = dict(warning)
        warning["risk_level"] = _enum(warning.get("risk_level"), _RISK_LEVEL_VALUES, "none")
        warning["display_text"] = _coerce_str(warning.get("display_text"))
        out["weight_cut_warning"] = warning
    elif isinstance(warning, str):
        # Some conversions return the warning as a plain sentence. Wrap it in the
        # schema object with a neutral risk level; the text is preserved verbatim.
        text = warning.strip()
        out["weight_cut_warning"] = (
            {"risk_level": "none", "display_text": text, "requires_professional_support": False}
            if text
            else None
        )
    return out


# Decision aliases: only obvious, unambiguous synonyms map onto an established
# ReadinessStatus value. A readiness decision is self-report, so anything not
# matched here is dropped — never coerced into a fabricated default.
_DECISION_ALIASES = {
    "train": "train_as_planned",
    "as_planned": "train_as_planned",
    "train_as_plan": "train_as_planned",
    "train_normally": "train_as_planned",
    "modified": "modify",
    "modify_session": "modify",
    "pullback": "pull_back",
    "pull-back": "pull_back",
    "pull back": "pull_back",
    "unavailable": "unavailable",
}


def _normalize_checkin_decision(value: Any) -> str | None:
    """Resolve a check-in decision to a valid ``ReadinessStatus``, or ``None``.

    Accepts an exact enum value, a case-only variant, or one of a few obvious
    aliases. An unrecognized decision returns ``None`` so the caller drops the
    whole check-in — a readiness call is never invented.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate in _READINESS_VALUES:
        return candidate
    lowered = candidate.lower()
    if lowered in _READINESS_VALUES:
        return lowered
    return _DECISION_ALIASES.get(lowered)


def _normalize_checkin_morning(value: Any) -> dict[str, Any] | None:
    """Coerce a morning self-report, or ``None`` when it cannot be trusted.

    ``sleep_quality``/``overall_readiness``/``pain`` are required self-report
    scores with NO neutral default in the schema. A missing or out-of-range score
    drops the whole check-in rather than fabricating a biometric/readiness value.
    Numeric strings ("4") are coerced because that is a formatting fix, not
    invention. Optional self-report context is carried through verbatim.
    """
    if not isinstance(value, dict):
        return None
    out: dict[str, Any] = {}
    for key, low, high in (
        ("sleep_quality", 1, 5),
        ("overall_readiness", 1, 5),
        ("pain", 0, 10),
    ):
        score = _coerce_optional_int(value.get(key))
        if score is None or not (low <= score <= high):
            return None
        out[key] = score
    if value.get("location") is not None:
        out["location"] = _coerce_str(value.get("location"))
    if isinstance(value.get("injury_specific"), dict):
        out["injury_specific"] = value.get("injury_specific")
    return out


def _normalize_checkin_date(item: dict[str, Any], weeks: list[dict[str, Any]]) -> str | None:
    """Resolve a check-in's date, inferring from indices only when unambiguous.

    A present non-empty ``date`` string is used as-is. Otherwise, when the
    check-in carries integer ``week_index``/``day_index`` that resolve to exactly
    one dated day in the (already-normalized) ``weeks``, that date is used.
    Anything ambiguous or unresolved returns ``None`` and the caller drops the
    check-in — a date is never invented.
    """
    date = _coerce_str(item.get("date")).strip()
    if date:
        return date
    week_index = _coerce_optional_int(item.get("week_index"))
    day_index = _coerce_optional_int(item.get("day_index"))
    if week_index is None or day_index is None:
        return None
    resolved: list[str] = []
    for week in weeks:
        if not isinstance(week, dict):
            continue
        if _coerce_optional_int(week.get("week_index")) != week_index:
            continue
        days = week.get("days")
        if not isinstance(days, list) or not (0 <= day_index < len(days)):
            continue
        day = days[day_index]
        if isinstance(day, dict):
            day_date = _coerce_str(day.get("date")).strip()
            if day_date:
                resolved.append(day_date)
    # Unambiguous only: exactly one matching dated day.
    if len(resolved) == 1:
        return resolved[0]
    return None


def _normalize_daily_check_ins(
    value: Any, weeks: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Drop malformed daily check-ins so they cannot fail the whole plan (PR-7).

    A partial or garbled daily check-in must never sink an otherwise-valid
    structured plan. Each entry is conservatively repaired — numeric-string scores
    coerced, obvious decision aliases mapped, date inferred only when unambiguous —
    then validated against :class:`DailyCheckIn`. Anything that cannot be made
    trustworthy WITHOUT inventing self-report content (sleep, pain, readiness,
    decision, or date) is dropped. A non-list input, or a list with no salvageable
    entries, becomes an empty list (the model's own default).
    """
    if not isinstance(value, list):
        return []
    weeks = weeks if isinstance(weeks, list) else []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        date = _normalize_checkin_date(item, weeks)
        morning = _normalize_checkin_morning(item.get("morning"))
        decision = _normalize_checkin_decision(item.get("decision"))
        if date is None or morning is None or decision is None:
            continue
        candidate = {
            "date": date,
            "morning": morning,
            "decision": decision,
            "rules_triggered": _coerce_str_list(item.get("rules_triggered")),
        }
        try:  # final guarantee: only schema-valid entries survive
            DailyCheckIn.model_validate(candidate)
        except Exception:
            continue
        out.append(candidate)
    return out


# Intensity-label typo fix. Coaches read effort as ``RPE`` (rate of perceived
# exertion); models occasionally emit ``PRE`` instead. Only an all-caps ``PRE``
# immediately preceding a value on the RPE scale (1-10, optionally a range like
# ``7–8``) is corrected, so ordinary words (``pre-fight``, ``PRE-FIGHT WEEK``)
# and unrelated numbers (``PRE 2024``) are never touched.
_RPE_LABEL_TYPO_RE = re.compile(r"\bPRE\b(?=\s*(?:10|[1-9])\b)")

# Keys whose verbatim text must never be rewritten by cosmetic label fixes.
_LABEL_FIX_SKIP_KEYS = frozenset({"raw_markdown_fallback"})


def _fix_label_typos(node: Any) -> Any:
    """Recursively correct intensity-label typos (``PRE`` → ``RPE``) in text.

    A pure formatting fix applied to every string leaf except the verbatim
    ``raw_markdown_fallback``. The regex is deliberately narrow so it only
    rewrites the effort label, never coaching content.
    """
    if isinstance(node, dict):
        return {
            key: value if key in _LABEL_FIX_SKIP_KEYS else _fix_label_typos(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_fix_label_typos(item) for item in node]
    if isinstance(node, str):
        return _RPE_LABEL_TYPO_RE.sub("RPE", node)
    return node


def _normalize_safety_text(text: Any) -> str:
    """Lowercase, collapse whitespace, drop trailing punctuation — for dedup."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    return cleaned.rstrip(".!;: ").strip()


def _dedupe_plan_safety_text(plan: dict[str, Any]) -> dict[str, Any]:
    """Drop repeated athlete-facing warning/constraint text (PR-QC).

    Stop/warning language tends to echo across active notes, red flags, and
    final notes. The authoritative place for a stop rule is the red-flag rule,
    so this keeps the strongest copy there and removes only exact duplicates:

    * collapses red-flag rules that are byte-for-byte identical (same text,
      action, severity, and trigger) — never distinct or session-specific rules;
    * drops a plan note whose text repeats an earlier plan note or an existing
      red-flag ``display_text``.

    Mutates and returns ``plan``. No safety rule is ever removed outright — the
    warning always survives in at least one place.
    """
    rules = plan.get("red_flag_rules")
    if isinstance(rules, list):
        seen_rules: set[tuple] = set()
        deduped_rules: list[Any] = []
        for rule in rules:
            if not isinstance(rule, dict):
                deduped_rules.append(rule)
                continue
            display = _normalize_safety_text(rule.get("display_text"))
            key = (
                display,
                _normalize_safety_text(rule.get("action")),
                rule.get("severity"),
                rule.get("when"),
            )
            if display and key in seen_rules:
                continue
            seen_rules.add(key)
            deduped_rules.append(rule)
        plan["red_flag_rules"] = deduped_rules
        rules = deduped_rules

    red_flag_texts = {
        _normalize_safety_text(rule.get("display_text"))
        for rule in (rules or [])
        if isinstance(rule, dict) and _normalize_safety_text(rule.get("display_text"))
    }

    notes = plan.get("plan_notes")
    if isinstance(notes, list):
        seen_notes: set[str] = set()
        deduped_notes: list[Any] = []
        for note in notes:
            if not isinstance(note, dict):
                deduped_notes.append(note)
                continue
            norm = _normalize_safety_text(note.get("text"))
            if norm and (norm in seen_notes or norm in red_flag_texts):
                continue
            if norm:
                seen_notes.add(norm)
            deduped_notes.append(note)
        plan["plan_notes"] = deduped_notes

    return plan


def normalize_structured_plan_candidate(data: Any) -> Any:
    """Conservatively coerce a model's near-miss structured JSON into schema shape.

    Only fixes obvious *formatting* mistakes (enum aliases, string loads/rests,
    string countdown labels, non-list ``daily_check_ins``, non-string
    ``progression_notes``, missing required meta fields filled with neutral
    structural defaults, intensity-label typos, and duplicated warning text). It
    never invents training content and never alters ``raw_markdown_fallback``
    text. Non-dict input is returned unchanged so the strict schema can reject
    it. Never raises.
    """

    if not isinstance(data, dict):
        return data

    plan = copy.deepcopy(data)

    if not isinstance(plan.get("schema_version"), str) or not plan.get("schema_version"):
        plan["schema_version"] = SCHEMA_VERSION
    plan["plan_metadata"] = _normalize_plan_metadata(plan.get("plan_metadata"))
    plan["athlete_context"] = _normalize_athlete_context(plan.get("athlete_context"))
    if plan.get("event_context") is not None:
        plan["event_context"] = _normalize_event_context(plan.get("event_context"))
    plan["countdown_labels"] = [
        label
        for label in (_normalize_countdown_label(item) for item in _as_list(plan.get("countdown_labels")))
        if label is not None
    ]
    plan["red_flag_rules"] = [_normalize_red_flag(rule) for rule in _as_dict_list(plan.get("red_flag_rules"))]
    plan["plan_notes"] = _normalize_plan_notes(plan.get("plan_notes"))
    plan["weeks"] = [_normalize_week(week) for week in _as_dict_list(plan.get("weeks"))]
    # daily_check_ins must be a list of fully-valid entries; a non-list, or a
    # partial/garbled entry, must never fail the whole plan. Malformed entries are
    # dropped conservatively (no fabricated scores/decisions/dates), leaving [] if
    # none survive — matching the model's empty-list default.
    plan["daily_check_ins"] = _normalize_daily_check_ins(
        plan.get("daily_check_ins"), plan.get("weeks")
    )
    plan["nutrition"] = _normalize_nutrition(plan.get("nutrition"))
    plan["progression_notes"] = _coerce_str(plan.get("progression_notes"))
    plan["raw_markdown_fallback"] = _coerce_str(plan.get("raw_markdown_fallback"))
    # Cosmetic label fix first (so dedup compares corrected text), then collapse
    # repeated athlete-facing warnings. Both are formatting-only and never touch
    # raw_markdown_fallback or drop a safety rule outright.
    plan = _fix_label_typos(plan)
    plan = _dedupe_plan_safety_text(plan)
    return plan


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _strip_and_normalize(data: Any) -> Any:
    """Strip banned biometric keys then conservatively normalize. Never raises."""
    stripped, _removed = strip_biometric_fields(data)
    try:
        return normalize_structured_plan_candidate(stripped)
    except Exception:  # normalization must never break the fallback flow
        return stripped


# ---------------------------------------------------------------------------
# Bank → StructuredTrainingPlan adapters
#
# These map the project's existing bank conventions (see fightcamp/bank_schema.py
# and data/*_bank.json) into StructuredTrainingPlan value objects, so the
# structured renderer can consume bank-derived training metadata without a new
# naming scheme. They are conservative readers, not generators: they only
# translate fields already present on a bank entry and never invent content.
#
# Bank conventions translated here:
#   * strength/exercise: ``prescription`` string like "3x5 @ 75-85% 1RM"
#     (sets x reps @ %load ref), ``method``, ``category``, ``equipment`` (str).
#   * conditioning: ``work_sec``/``rest_sec`` (int seconds), ``total_minutes``
#     (minutes), ``rounds`` (int), ``rpe`` (int), ``intensity`` (str),
#     ``system`` (energy system), ``equipment`` (list).
# ---------------------------------------------------------------------------

_PRESCRIPTION_SETS_REPS_RE = re.compile(r"([0-9]+)\s*[xX×]\s*([0-9]+(?:\s*[-–]\s*[0-9]+)?)")


def parse_bank_prescription(prescription: Any) -> dict[str, Any]:
    """Parse a bank ``prescription`` string into structured block fields.

    "3x5 @ 75-85% 1RM" → {"sets": 3, "reps": "5", "load": {percentage 85, ref 1RM}}.
    Returns only the fields it can read; an unparseable input yields ``{}``.
    """

    if not isinstance(prescription, str) or not prescription.strip():
        return {}
    text = prescription.strip()
    out: dict[str, Any] = {}
    sets_reps = _PRESCRIPTION_SETS_REPS_RE.search(text)
    if sets_reps:
        out["sets"] = int(sets_reps.group(1))
        out["reps"] = sets_reps.group(2).replace(" ", "")
    load = _normalize_load(text)
    if load is not None:
        out["load"] = load
    return out


def _slug(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return cleaned or fallback


def bank_strength_to_block(entry: dict[str, Any]) -> dict[str, Any]:
    """Adapter: an exercise/strength bank entry → a SessionBlock-shaped dict.

    Reads name/method/category/prescription/notes; the result is passed through
    :func:`_normalize_block` so it always satisfies the schema.
    """

    entry = entry if isinstance(entry, dict) else {}
    name = _coerce_str(entry.get("name"))
    block: dict[str, Any] = {
        "block_id": _slug(name, "block"),
        "block_type": _enum(entry.get("method"), _BLOCK_TYPE_VALUES, "strength", _BLOCK_TYPE_ALIASES),
        "display_name": name,
    }
    category = _coerce_str(entry.get("category"))
    if category:
        block["category"] = category
    notes = _coerce_str(entry.get("notes"))
    if notes:
        block["purpose"] = notes
    impact = _coerce_str(entry.get("impact_cost"))
    if impact:
        block["impact_level"] = impact
    block.update(parse_bank_prescription(entry.get("prescription")))
    return _normalize_block(block)


def bank_conditioning_to_block(entry: dict[str, Any]) -> dict[str, Any]:
    """Adapter: a conditioning bank entry → a SessionBlock-shaped dict.

    Maps work_sec/rest_sec → work/rest (seconds), total_minutes → duration
    (minutes), rounds, rpe → effort (RPE), system → energy_system, and intensity.
    The result is passed through :func:`_normalize_block`.
    """

    entry = entry if isinstance(entry, dict) else {}
    name = _coerce_str(entry.get("name"))
    block: dict[str, Any] = {
        "block_id": _slug(name, "conditioning"),
        "block_type": "conditioning",
        "display_name": name,
    }
    if entry.get("work_sec") is not None:
        block["work"] = entry.get("work_sec")
    if entry.get("rest_sec") is not None:
        block["rest"] = entry.get("rest_sec")
    if entry.get("total_minutes") is not None:
        block["duration"] = entry.get("total_minutes")
    if isinstance(entry.get("rounds"), int) and not isinstance(entry.get("rounds"), bool):
        block["rounds"] = entry.get("rounds")
    rpe = entry.get("rpe")
    if isinstance(rpe, (int, float)) and not isinstance(rpe, bool):
        block["effort"] = {"method": "RPE", "value": rpe, "scale": "1-10"}
    system = _coerce_str(entry.get("system"))
    if system:
        block["energy_system"] = system
    intensity = _coerce_str(entry.get("intensity"))
    if intensity:
        block["intensity"] = intensity
    notes = _coerce_str(entry.get("notes"))
    if notes:
        block["purpose"] = notes
    impact = _coerce_str(entry.get("impact_cost"))
    if impact:
        block["impact_level"] = impact
    return _normalize_block(block)


def _with_deterministic_support(
    plan_dict: dict[str, Any], computed_support: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge an athlete-safe projection of computed_support into the plan dict.

    Deterministic-first: Stage 1's computed nutrition/recovery numbers are placed
    onto ``structured_plan.deterministic_support`` so the athlete frontend can
    render them directly (the raw ``computed_support`` — with ``coach_gated`` —
    is never exposed). No-op when there is nothing usable to project.
    """
    projection = athlete_safe_support(computed_support)
    if projection:
        plan_dict["deterministic_support"] = projection
    return plan_dict


def build_structured_plan_outcome(
    raw_data: Any,
    *,
    raw_markdown: str = "",
    repair_fn: Callable[[Any, list[str]], Any] | None = None,
    computed_support: dict[str, Any] | None = None,
) -> StructuredPlanOutcome:
    """Validate a candidate structured payload into a persistable outcome.

    Flow (matching the task contract):

    1. ``raw_data is None`` → ``not_attempted`` (structured generation skipped).
    2. Strip banned biometric keys, then validate.
    3. Valid → ``valid``.
    4. Invalid and no ``repair_fn`` → ``invalid_fallback_used``.
    5. Invalid with ``repair_fn`` → run exactly one repair retry via
       :func:`repair_structured_plan_once`; success → ``repair_attempted_valid``,
       otherwise ``invalid_fallback_used``.

    Never raises: a malformed payload degrades to ``invalid_fallback_used`` so the
    raw ``plan_text`` flow keeps working.
    """

    if raw_data is None:
        return StructuredPlanOutcome(status="not_attempted")

    cleaned = _strip_and_normalize(raw_data)

    first = safe_parse_structured_plan(cleaned, raw_markdown=raw_markdown or None)
    if first.ok and first.plan is not None:
        plan_dict = _with_deterministic_support(first.plan.model_dump(mode="json"), computed_support)
        unfaithful = check_structured_faithfulness(plan_dict, raw_markdown)
        if unfaithful:
            return StructuredPlanOutcome(
                status="invalid_fallback_used",
                errors=[f"faithfulness: {issue}" for issue in unfaithful],
            )
        return StructuredPlanOutcome(
            status="valid",
            structured_plan=plan_dict,
            schema_version=first.plan.schema_version,
            warnings=audit_structured_plan(plan_dict, computed_support),
        )

    if repair_fn is None:
        return StructuredPlanOutcome(
            status="invalid_fallback_used",
            errors=list(first.errors),
        )

    # Strip biometric keys + conservatively normalize anything the repair attempt
    # introduces too, mirroring the first-pass treatment.
    def _clean_repair(data: Any, errors: list[str]) -> Any:
        return _strip_and_normalize(repair_fn(data, errors))

    repaired = repair_structured_plan_once(
        cleaned, repair_fn=_clean_repair, raw_markdown=raw_markdown or None
    )
    if repaired.ok and repaired.plan is not None:
        plan_dict = _with_deterministic_support(repaired.plan.model_dump(mode="json"), computed_support)
        unfaithful = check_structured_faithfulness(plan_dict, raw_markdown)
        if unfaithful:
            return StructuredPlanOutcome(
                status="invalid_fallback_used",
                errors=[f"faithfulness: {issue}" for issue in unfaithful],
            )
        return StructuredPlanOutcome(
            status="repair_attempted_valid",
            structured_plan=plan_dict,
            schema_version=repaired.plan.schema_version,
            warnings=audit_structured_plan(plan_dict, computed_support),
        )
    return StructuredPlanOutcome(
        status="invalid_fallback_used",
        errors=list(repaired.errors),
    )


def _extract_json_object(text: str) -> str | None:
    """Return the first balanced top-level ``{...}`` object in ``text``.

    Uses a brace-counting scan so trailing/leading prose — or stray braces in a
    commentary wrapper or a ```json fence — does not produce a truncated or
    over-wide span the way ``find``/``rfind`` would. String literals are honoured
    so braces inside JSON string values are not mistaken for structure. Returns
    ``None`` when no complete object is present.
    """

    depth = 0
    start: int | None = None
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                return text[start : index + 1]
    return None


def parse_structured_json(text: str) -> Any:
    """Parse model output into JSON, tolerating a leading/trailing prose wrapper.

    Returns ``None`` when no JSON object can be located, so callers treat it as a
    skipped attempt rather than crashing.
    """

    if not text:
        return None
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced ``{...}`` object if the model wrapped the
    # JSON in commentary or a code fence despite instructions.
    candidate = _extract_json_object(stripped)
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


# Matches a JSON string value for raw_markdown_fallback, honouring backslash
# escapes so a plan body full of quotes/newlines is captured as one value.
_RAW_FALLBACK_VALUE_RE = re.compile(
    r'("raw_markdown_fallback"\s*:\s*)"(?:[^"\\]|\\.)*"', re.DOTALL
)


def _strip_fallback_from_broken_json(broken_json: str) -> str:
    """Blank ``raw_markdown_fallback`` in a prior attempt before re-embedding it.

    The repair prompt echoes the previous (invalid) JSON back to the model. If
    that attempt copied the whole plan into ``raw_markdown_fallback`` we do not
    want to pay to send it again — and we never want the plan echo, only its
    structural shape, to guide the repair. Parses when possible and blanks the
    field; otherwise falls back to a targeted regex so a genuinely broken blob
    is still trimmed. Never raises.
    """

    if not broken_json:
        return broken_json
    parsed = parse_structured_json(broken_json)
    if isinstance(parsed, dict):
        if parsed.get("raw_markdown_fallback"):
            parsed["raw_markdown_fallback"] = ""
        try:
            return json.dumps(parsed, ensure_ascii=False)
        except (TypeError, ValueError):
            pass
    return _RAW_FALLBACK_VALUE_RE.sub(r'\1""', broken_json)


_STRUCTURED_PLAN_RULES = f"""\
You are converting an already-written fight-camp training plan into a strict,
machine-readable JSON object. Output ONLY a single JSON object — no markdown, no
code fences, no commentary.

The human-readable plan provided below is the SOURCE OF TRUTH. Convert it
faithfully into structured form. Do NOT invent new training content — no new
exercises, sessions, blocks, loads, dates, athletes, or biometrics. Only
restructure what the plan already says.

The root JSON object IS the StructuredTrainingPlan.
Do NOT wrap it inside a top-level "plan" key. Its top-level keys are exactly:

  schema_version, plan_metadata, athlete_context, event_context,
  countdown_labels, red_flag_rules, plan_notes, weeks, daily_check_ins,
  nutrition, progression_notes, raw_markdown_fallback.

The nested training hierarchy lives inside the root object as:
weeks[] -> days[] -> sessions[] -> blocks[].

The JSON object MUST conform to the StructuredTrainingPlan schema:

- It MUST set "schema_version" to "{SCHEMA_VERSION}".
- Set "raw_markdown_fallback" to an empty string "". Do NOT echo the plan text
  back into it — the system restores the verbatim original after you respond.
  Spend your output tokens on the structured fields, not on copying the plan.
- It MUST use countdown labels (countdown_labels[] and per-day countdown_label,
  e.g. "D-28", "D-7", "D-1", "D0", "D+1") whenever an event/fight/match date is
  known.
- Each week's phase_label MUST be one of: GPP, SPP, TAPER, FIGHT_WEEK,
  REINTEGRATION.
- Every block load MUST be a machine-readable object, NEVER a string. Use:
  {{"method": "percentage", "value": 85, "unit": "percent", "ref": "1RM",
  "display": "85% 1RM"}}. Do NOT output loads like "85%" as plain strings.
- Readiness is self-report ONLY. Do NOT output HRV, CNS recovery percentage,
  WHOOP-style recovery scores, strain scores, or any other biometric/wearable
  readiness field. Use the self-report today_card readiness_status and the 3-tap
  morning check-in only.
- Each session MUST include completion_status (default "not_started") and a
  session-level mindset_anchor.
- Coach-led, sparring, or technical days where NO programmed S&C work is
  prescribed (e.g. "Coach-led boxing — hard sparring / controlled hard contact",
  "Coach-led boxing — technical-only combat", "coach-owned combat session", or
  the legacy "Coach-led boxing session", "no extra S&C today", "no app S&C
  today", "technical only") MUST still be emitted as a day. Leave that day's
  "sessions" as [] and set a concise today_card.headline naming what it is (e.g.
  "Coach-led boxing", "Hard sparring", "Technical only") so the day renders as
  its own card. Do NOT invent S&C blocks for these days and do NOT drop the day.
- A coach-led / sparring / technical day can ALSO carry a low-load programmed
  session on the SAME day (e.g. the plan lists "Coach-led boxing — technical
  only" AND a short touch such as a tactical cue card, mobility reset, or
  freshness primer). When that happens the two COEXIST — never drop one for the
  other: emit the programmed S&C work as normal entries in "sessions" (with its
  blocks), AND set today_card.coach_led_contact to the coach-owned label (e.g.
  "Coach-led boxing — technical only"). Put the coach-owned label in
  coach_led_contact, NOT in headline (set headline to a generic title like
  "Training Day" or the programmed session's title instead, as headline is still
  required), so the programmed session keeps its own title; the renderer shows the
  coach-owned contact as a context line above it. The "coach-owned combat
  session" / legacy "no extra S&C today" wording only applies when there is
  genuinely no programmed work — if a session is listed for the day, keep it.
- Preserve compact plan-output formats reliably:
  * A day header like `D-18 (Wednesday) — Power Transfer Touch` starts a day.
    A following `Why:` line is the session/day objective, not a separate block.
  * Bulleted prescriptions such as `- Band-Resisted Jab-Cross Primer — 3 x
    4-6 reps...` are blocks. Carry labelled follow-up lines into that same block:
    `Purpose`, `Why today`, `Progression/regression/stop`, `Progression`,
    `Regression`, `Stop`, `Duration`, `Prescription`, `Output`, `Intensity`,
    and `Coach call`.
  * Short late-camp support days like `Fight Tactical Watch`, `Tactical Cue
    Card`, `Breathing Reset`, `Freshness Reset`, and `Final Neural Cue` are real
    sessions when the plan gives Duration/Prescription/Purpose lines. Do not
    collapse them into rest days just because they are low-load.
  * Tactical watch, cue-card, film-review, and visualization work is tactical /
    mindset support, NOT physical conditioning. Use session_type "skill" or
    "recovery" as appropriate and block_type "skill" or "mindset"; do not label
    these as conditioning/strength/plyometric blocks.
  * If a coach-only day says `Coach-owned combat session` (or the legacy
    `No extra S&C today` / `No app S&C today`), keep sessions as []. If it also
    lists any prescribed touch on the same D-day, keep that touch as a session
    and put the coach-owned contact in today_card.coach_led_contact.
- Optimize for a valid first-pass card: omit optional fields you cannot fill
  from the source rather than emitting partial objects that fail schema
  validation. Preserve every dated day and every listed prescription, but do not
  invent missing numbers.
- daily_check_ins are OPTIONAL and must be either fully valid or omitted. Emit a
  check-in entry ONLY when the plan actually states a dated self-report; each
  entry MUST then carry "date", a "morning" object with all of "sleep_quality"
  (1-5), "overall_readiness" (1-5) and "pain" (0-10), and a "decision" of
  "train_as_planned", "modify", "pull_back" or "unavailable". Never emit a
  partial check-in and never invent these self-report scores or a date — if you
  cannot fill every field from the plan, leave daily_check_ins as [].
- Provide red_flag_rules[] with machine fields (metric/operator/threshold/logic)
  kept separate from a human-readable display_text. "threshold" MUST be a bare
  number (e.g. 20, not ">20%" or "form breaks") — put the comparison in
  "operator" and the prose in display_text, and OMIT threshold entirely when the
  rule has no numeric trigger.
- List fields (coaching_cues, regression_options, substitutions, applies_to)
  MUST be JSON arrays — emit [] when empty, never null and never a bare string.
  A block's "effort" MUST be an object like
  {{"method": "RPE", "value": 7, "scale": "1-10"}}, never a bare string.
- Capture short plan-level reminders that live OUTSIDE any week — e.g. a header
  "Active notes" block and footer "End of plan notes" — in plan_notes[]. Each
  entry is {{"category": one of weight_cut|injury|nutrition|training|recovery|
  general, "label": optional short label, "text": the reminder}}. Use plan_notes
  for the active weight-cut summary, injury/wound handling, nutrition reminders,
  and general non-negotiables. Keep stop/modify/report SAFETY thresholds in
  red_flag_rules and full nutrition macros in nutrition — plan_notes is for the
  brief, always-on context. A weight_cut note is a brief, calm statement of the
  active cut and how it shapes recovery/fuelling; it must NEVER contain acute-cut
  directives (no sauna, dehydration, water-loading, or sodium manipulation). Omit
  plan_notes entirely if the plan states none.
- WEIGHT-CUT SEVERITY GATE. The deterministic layer grades every active cut into
  a risk band (see STAGE 1 COMPUTED SUPPORT weight_cut.risk_band: none / moderate
  / high / severe). Match the plan's alarm level to that band — do NOT shout
  medical warnings at a routine cut:
  * band "none" or "moderate": treat the cut as ordinary context. Give at most ONE
    short, calm plan_notes weight_cut summary about protecting recovery and
    fuelling. Do NOT add a weight-cut stop/report red_flag_rule, do NOT tell the
    athlete to "seek supervision" / "notify coach" / see a professional, and set
    the nutrition weight_cut_warning risk_level to "none" (or omit it) with
    requires_professional_support = false.
  * band "high": add a single measured precaution — one weight_cut_warning at
    risk_level "amber" and, only if warranted, one weight-cut red_flag_rule.
  * band "severe": full supervision framing is appropriate — weight_cut_warning
    at "red" with requires_professional_support = true and a weight-cut
    red_flag_rule.
  Never escalate ABOVE the computed band. When in doubt, under-warn.
- Provide nutrition with a summary and, where a weight cut applies, a
  weight_cut_warning whose risk_level matches the computed band per the gate
  above. Weight-cut guidance is NEVER direct acute-cut instructions (no sauna,
  dehydration, water-loading, or sodium-manipulation directives).
- When the plan states them, carry per-block detail into each block:
  "coaching_cues" (list), "regression_options"/"substitutions" (lists of safer or
  alternative exercises the plan offers), and "progression_rule" (how to advance).
- Carry mental/mindset coaching into mindset_anchor at BOTH the session level and
  the day level (today_card.mindset_anchor), including "confidence_anchor" and
  "context" when the plan provides them. When STAGE 1 COMPUTED SUPPORT includes a
  mindset.athlete_note (the athlete's own words about their mental/confidence
  issue), personalise the mindset_anchor to that note — reflect their specific
  concern in "intent"/"focus_cue"/"confidence_anchor"/"context" rather than
  emitting only the generic phase cue. Keep it athlete-safe and supportive; never
  quote the note verbatim if it is distressing, and never invent clinical or
  mental-health diagnoses or treatment.
- Omit any of the above the plan does not state — leave the field out rather than
  inventing content.

VOICE & CONCISENESS (athlete-facing text — week_goal, today_card.headline,
session title/objective, plan_notes, mindset_anchor, nutrition prose):
- week_goal MUST be a SHORT label of AT MOST 6 words — a phrase, not a sentence.
  No semicolons, no "while …" tails, no second clause. Compress the source goal
  to its single most important driver (e.g. "Build single-leg drive and balance",
  "Sharpen punch speed, stay fresh"). Do NOT add content — only shorten.
- Keep every athlete-facing string tight: prefer short phrases over full
  sentences, drop filler and hedging, and never repeat the same point across two
  fields.
- Do NOT refer to "the app", "this app", "the platform", or "app sessions" in any
  athlete-facing text. The athlete is reading their own plan, so name the work
  directly ("S&C and rehab inserts on the listed D-days", "your sessions") rather
  than attributing it to "the app".

DETERMINISTIC AUTHORITY (when a "STAGE 1 COMPUTED SUPPORT" section is provided):
- Treat STAGE 1 COMPUTED SUPPORT as AUTHORITATIVE for nutrition macros,
  hydration, fuel timing, and weight-cut risk; for recovery sleep/fatigue rules;
  and for mindset block classification and phase cues. It is the source of truth
  for those numbers/classifications — the plan text only supplies wording.
- Do NOT extract or output macro, hydration, or weight-cut values from the plan
  text that conflict with computed support when computed support is present; use
  the computed values and let the plan text contribute phrasing only.
- Keep today_card brief: a short headline, readiness, and the day's mindset
  anchor. Do NOT pack full nutrition detail into today_card — the NutritionCard
  (plan-level "nutrition") owns full nutrition details.
- red_flag_rules MUST contain only stop / modify / report safety rules. Do not
  put general training or nutrition content there.
- Do NOT duplicate identical mindset anchors at both the day and session level —
  if a session's anchor would be identical to the day's, vary phrasing while
  still keeping a valid session-level mindset_anchor.
- NEVER surface coach_gated content. The "coach_gated" sub-sections of computed
  support (acute weight-cut and supplement dosing) are coach/medical-only and
  MUST NOT appear in any athlete-facing field.
"""


# Compact, valid skeleton showing the exact root shape and every nested object
# the schema requires. "..." marks free text to fill from the source plan.
_ROOT_SKELETON = f"""\
EXACT ROOT SKELETON (match this shape; fill values from the plan, keep all keys):
{{
  "schema_version": "{SCHEMA_VERSION}",
  "plan_metadata": {{"title": "...", "sport": "...", "plan_type": "fight_camp", "timezone": "Europe/London", "status": "active", "units": "metric"}},
  "athlete_context": {{"sport_profile": "..."}},
  "event_context": {{"event_type": "fight", "fight_date": "YYYY-MM-DD"}},
  "countdown_labels": [{{"date": "YYYY-MM-DD", "days_to_event": 28, "label": "D-28", "anchor": "fight"}}],
  "red_flag_rules": [{{"rule_id": "...", "when": "morning_check_in", "severity": "amber", "display_text": "...", "action": "..."}}],
  "plan_notes": [{{"category": "weight_cut", "label": "Active weight cut", "text": "..."}}],
  "weeks": [
    {{
      "week_id": "wk-1", "week_index": 1, "phase_label": "SPP", "week_goal": "<short label, max 6 words>",
      "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD",
      "load_focus": {{"volume": "moderate", "intensity": "high", "specificity": "high", "fatigue_target": "reduced"}},
      "progression": {{"week_type": "build", "planned_change_from_previous": "..."}},
      "days": [
        {{
          "date": "YYYY-MM-DD", "day_type": "high", "countdown_label": "D-15", "phase_label": "SPP",
          "today_card": {{"headline": "...", "readiness_status": "train_as_planned", "coach_led_contact": "", "mindset_anchor": {{"intent": "...", "focus_cue": "...", "reset_cue": "...", "confidence_anchor": "...", "context": "..."}}}},
          "sessions": [
            {{
              "session_id": "ses-1", "session_type": "strength_power", "title": "...", "objective": "...",
              "completion_status": "not_started",
              "mindset_anchor": {{"intent": "...", "focus_cue": "...", "reset_cue": "...", "confidence_anchor": "...", "context": "..."}},
              "blocks": [
                {{
                  "block_id": "blk-1", "block_type": "strength", "display_name": "...", "sets": 4, "reps": "4-6",
                  "load": {{"method": "percentage", "value": 85, "unit": "percent", "ref": "1RM", "display": "85% 1RM"}},
                  "rest": {{"value": 180, "unit": "seconds"}}, "duration": {{"value": 45, "unit": "minutes"}},
                  "coaching_cues": ["..."], "regression_options": ["..."], "substitutions": ["..."], "progression_rule": "..."
                }}
              ]
            }}
          ]
        }}
      ]
    }}
  ],
  "daily_check_ins": [],
  "nutrition": {{"summary": "...", "daily_focus": "...", "training_day_guidance": "...", "fight_week_guidance": "...", "weight_cut_warning": {{"risk_level": "amber", "display_text": "...", "requires_professional_support": false}}}},
  "progression_notes": "...",
  "raw_markdown_fallback": ""
}}"""


def build_structured_plan_prompt(
    *,
    plan_markdown: str,
    planning_brief: dict[str, Any] | None = None,
    event_date: str = "",
    repair_errors: list[str] | None = None,
    broken_json: str | None = None,
) -> str:
    """Build the model prompt for turning a markdown plan into structured JSON.

    When ``repair_errors``/``broken_json`` are supplied the prompt asks the model
    to fix a previous invalid attempt (the single repair retry).
    """

    sections: list[str] = [_STRUCTURED_PLAN_RULES, _ROOT_SKELETON]

    if event_date:
        sections.append(f"EVENT/FIGHT DATE: {event_date}")

    if planning_brief:
        # Carry Stage 1's own computed nutrition/recovery/mindset numbers
        # through UNTRUNCATED so the conversion does not re-derive them from
        # compressed prose. The rest of the brief stays capped (it is broad
        # context, not source-of-truth numbers).
        computed_support = None
        brief_rest = planning_brief
        if isinstance(planning_brief, dict) and "computed_support" in planning_brief:
            computed_support = planning_brief.get("computed_support")
            brief_rest = {
                key: value
                for key, value in planning_brief.items()
                if key != "computed_support"
            }

        try:
            brief_json = json.dumps(brief_rest, ensure_ascii=False)[:6000]
        except (TypeError, ValueError):
            brief_json = ""
        if brief_json:
            sections.append(
                "PLANNING BRIEF (context for athlete/event/phases — do not copy "
                "verbatim):\n" + brief_json
            )

        if computed_support:
            try:
                support_json = json.dumps(computed_support, ensure_ascii=False)
            except (TypeError, ValueError):
                support_json = ""
            if support_json:
                sections.append(
                    "STAGE 1 COMPUTED SUPPORT (authoritative nutrition/recovery/"
                    "mindset numbers — use these exact values when the plan "
                    "covers nutrition, recovery, or mental coaching; do not "
                    "invent or round differently). The `coach_gated` sub-sections "
                    "hold acute weight-cut and supplement dosing: keep them for "
                    "coach/medical use only and NEVER surface them directly to "
                    "the athlete:\n" + support_json
                )

    sections.append(
        "ORIGINAL PLAN (this is the source to convert; do NOT copy it into "
        "raw_markdown_fallback — leave that field \"\"):\n"
        + plan_markdown
    )

    if repair_errors:
        sections.append(
            "Your previous JSON failed schema validation with these errors:\n"
            + "\n".join(f"- {err}" for err in repair_errors)
        )
    if broken_json:
        sections.append(
            "Previous invalid JSON to correct (return a fully valid object):\n"
            + _strip_fallback_from_broken_json(broken_json)[:12000]
        )

    if repair_errors:
        sections.append(
            "Fix ONLY the JSON structure/shape so it matches the root skeleton and "
            "passes the schema. Do NOT change the training content."
        )

    sections.append(
        "Return the corrected StructuredTrainingPlan JSON object now."
        if repair_errors
        else "Return the StructuredTrainingPlan JSON object now."
    )

    return "\n\n".join(sections)
