"""Days-out policy loader.

Loads the shared ``data/days_out_policy.json`` and exposes deterministic
helpers that every other module should use for fight-proximity decisions.

No other module should hard-code fight-week thresholds.  All behavior
gates are driven by the JSON policy.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_POLICY_PATH = Path(__file__).resolve().parents[1] / "data" / "days_out_policy.json"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class InputRelevance(str, Enum):
    """How a field should influence planning at a given days-out window."""
    REQUIRED = "required"
    USED_IF_PRESENT = "used_if_present"
    ADVISORY_ONLY = "advisory_only"
    IGNORE_FOR_PLANNING = "ignore_for_planning"
    HIDE_OR_DISABLE = "hide_or_disable_in_ui"


class SparringDoseMode(str, Enum):
    FULL = "full"
    NARROW = "narrow"
    ADVISORY = "advisory"
    SUPPRESS = "suppress"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlannerPermissions:
    allow_full_strength_block: bool = True
    allow_strength_anchor: bool = True
    allow_strength_primer_only: bool = False
    max_strength_exercises: int | None = None
    allow_conditioning_build: bool = True
    allow_conditioning_reminder_only: bool = False
    allow_glycolytic: bool = True
    max_conditioning_stressors: int | None = None
    allow_hard_sparring: bool = True
    allow_sparring_to_drive_architecture: bool = True
    max_hard_sparring_collision_owners: int | None = None
    sparring_dose_mode: SparringDoseMode = SparringDoseMode.FULL
    allow_weekly_architecture: bool = True
    allow_weekly_frequency_to_influence_structure: bool = True
    allow_development_blocks: bool = True
    allow_multi_session_days: bool = True
    allow_accessory_volume: bool = True
    allow_novelty: bool = True
    freshness_priority: bool = False
    fight_day_protocol: bool = False


@dataclass(frozen=True)
class UIHints:
    fight_proximity_banner: str | None = None
    de_emphasize_fields: tuple[str, ...] = ()
    disable_fields: tuple[str, ...] = ()
    hide_fields: tuple[str, ...] = ()
    helper_texts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DaysOutContext:
    """Immutable snapshot of every days-out decision a consumer needs."""
    days_out: int | None
    bucket: str
    label: str
    input_relevance: dict[str, InputRelevance]
    planner_permissions: PlannerPermissions
    allowed_session_types: frozenset[str]
    forbidden_session_types: frozenset[str]
    ui_hints: UIHints
    notes: str

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def field_ignored(self, field_name: str) -> bool:
        rel = self.input_relevance.get(field_name)
        return rel in (InputRelevance.IGNORE_FOR_PLANNING, InputRelevance.HIDE_OR_DISABLE)

    def field_advisory(self, field_name: str) -> bool:
        return self.input_relevance.get(field_name) == InputRelevance.ADVISORY_ONLY

    def field_active(self, field_name: str) -> bool:
        """True when the field should still influence planning structure."""
        rel = self.input_relevance.get(field_name)
        return rel in (InputRelevance.REQUIRED, InputRelevance.USED_IF_PRESENT)

    def to_dict(self) -> dict[str, Any]:
        """Serialisable summary for stage-2 payloads / debug logs."""
        return {
            "days_out": self.days_out,
            "bucket": self.bucket,
            "label": self.label,
            "input_relevance": {k: v.value for k, v in self.input_relevance.items()},
            "planner_permissions": {
                "allow_full_strength_block": self.planner_permissions.allow_full_strength_block,
                "allow_strength_anchor": self.planner_permissions.allow_strength_anchor,
                "allow_strength_primer_only": self.planner_permissions.allow_strength_primer_only,
                "max_strength_exercises": self.planner_permissions.max_strength_exercises,
                "allow_conditioning_build": self.planner_permissions.allow_conditioning_build,
                "allow_conditioning_reminder_only": self.planner_permissions.allow_conditioning_reminder_only,
                "allow_glycolytic": self.planner_permissions.allow_glycolytic,
                "max_conditioning_stressors": self.planner_permissions.max_conditioning_stressors,
                "allow_hard_sparring": self.planner_permissions.allow_hard_sparring,
                "allow_sparring_to_drive_architecture": self.planner_permissions.allow_sparring_to_drive_architecture,
                "max_hard_sparring_collision_owners": self.planner_permissions.max_hard_sparring_collision_owners,
                "sparring_dose_mode": self.planner_permissions.sparring_dose_mode.value,
                "allow_weekly_architecture": self.planner_permissions.allow_weekly_architecture,
                "allow_weekly_frequency_to_influence_structure": self.planner_permissions.allow_weekly_frequency_to_influence_structure,
                "allow_development_blocks": self.planner_permissions.allow_development_blocks,
                "allow_multi_session_days": self.planner_permissions.allow_multi_session_days,
                "allow_accessory_volume": self.planner_permissions.allow_accessory_volume,
                "allow_novelty": self.planner_permissions.allow_novelty,
                "freshness_priority": self.planner_permissions.freshness_priority,
                "fight_day_protocol": self.planner_permissions.fight_day_protocol,
            },
            "allowed_session_types": sorted(self.allowed_session_types),
            "forbidden_session_types": sorted(self.forbidden_session_types),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# JSON loading (cached)
# ---------------------------------------------------------------------------

_policy_cache: dict[str, Any] | None = None


def _load_policy() -> dict[str, Any]:
    global _policy_cache
    if _policy_cache is None:
        with open(_POLICY_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        _policy_cache = raw["buckets"]
    return _policy_cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_days_out_bucket(days_until_fight: int | None) -> str:
    """Return the bucket name for *days_until_fight*.

    Returns ``"CAMP"`` for >7 or ``None``, otherwise ``"D-N"`` for 0-7.
    """
    if days_until_fight is None or days_until_fight > 7:
        return "CAMP"
    if days_until_fight < 0:
        return "CAMP"
    return f"D-{days_until_fight}"


def _parse_permissions(raw: dict[str, Any]) -> PlannerPermissions:
    return PlannerPermissions(
        allow_full_strength_block=raw.get("allow_full_strength_block", True),
        allow_strength_anchor=raw.get("allow_strength_anchor", True),
        allow_strength_primer_only=raw.get("allow_strength_primer_only", False),
        max_strength_exercises=raw.get("max_strength_exercises"),
        allow_conditioning_build=raw.get("allow_conditioning_build", True),
        allow_conditioning_reminder_only=raw.get("allow_conditioning_reminder_only", False),
        allow_glycolytic=raw.get("allow_glycolytic", True),
        max_conditioning_stressors=raw.get("max_conditioning_stressors"),
        allow_hard_sparring=raw.get("allow_hard_sparring", True),
        allow_sparring_to_drive_architecture=raw.get("allow_sparring_to_drive_architecture", True),
        max_hard_sparring_collision_owners=raw.get("max_hard_sparring_collision_owners"),
        sparring_dose_mode=SparringDoseMode(raw.get("sparring_dose_mode", "full")),
        allow_weekly_architecture=raw.get("allow_weekly_architecture", True),
        allow_weekly_frequency_to_influence_structure=raw.get("allow_weekly_frequency_to_influence_structure", True),
        allow_development_blocks=raw.get("allow_development_blocks", True),
        allow_multi_session_days=raw.get("allow_multi_session_days", True),
        allow_accessory_volume=raw.get("allow_accessory_volume", True),
        allow_novelty=raw.get("allow_novelty", True),
        freshness_priority=raw.get("freshness_priority", False),
        fight_day_protocol=raw.get("fight_day_protocol", False),
    )


def _parse_ui_hints(raw: dict[str, Any]) -> UIHints:
    return UIHints(
        fight_proximity_banner=raw.get("fight_proximity_banner"),
        de_emphasize_fields=tuple(raw.get("de_emphasize_fields", ())),
        disable_fields=tuple(raw.get("disable_fields", ())),
        hide_fields=tuple(raw.get("hide_fields", ())),
        helper_texts=dict(raw.get("helper_texts", {})),
    )


def _parse_input_relevance(raw: dict[str, str]) -> dict[str, InputRelevance]:
    out: dict[str, InputRelevance] = {}
    for key, val in raw.items():
        try:
            out[key] = InputRelevance(val)
        except ValueError:
            out[key] = InputRelevance.USED_IF_PRESENT
    return out


def build_days_out_context(days_until_fight: int | None) -> DaysOutContext:
    """Build the complete days-out context from the shared JSON policy."""
    bucket = get_days_out_bucket(days_until_fight)
    policy = _load_policy()
    entry = policy.get(bucket) or policy["CAMP"]

    return DaysOutContext(
        days_out=days_until_fight,
        bucket=bucket,
        label=entry.get("label", bucket),
        input_relevance=_parse_input_relevance(entry.get("input_relevance", {})),
        planner_permissions=_parse_permissions(entry.get("planner_permissions", {})),
        allowed_session_types=frozenset(entry.get("allowed_session_types", ())),
        forbidden_session_types=frozenset(entry.get("forbidden_session_types", ())),
        ui_hints=_parse_ui_hints(entry.get("ui_hints", {})),
        notes=entry.get("notes", ""),
    )


# ---------------------------------------------------------------------------
# Effective-input helpers
# ---------------------------------------------------------------------------

def get_effective_planning_inputs(
    raw_inputs: dict[str, Any],
    days_out_ctx: DaysOutContext,
) -> dict[str, Any]:
    """Return a copy of *raw_inputs* with ignored/advisory fields neutralised.

    * ``ignore_for_planning`` / ``hide_or_disable_in_ui`` → field set to its
      neutral value (empty list, empty string, ``None``, or ``0``).
    * ``advisory_only`` → kept as-is but the caller should treat it as
      wording/cueing input only.
    * ``required`` / ``used_if_present`` → untouched.

    The original *raw_inputs* dict is never mutated.
    """
    effective = dict(raw_inputs)
    for field_name, relevance in days_out_ctx.input_relevance.items():
        if relevance not in (InputRelevance.IGNORE_FOR_PLANNING, InputRelevance.HIDE_OR_DISABLE):
            continue
        if field_name not in effective:
            continue
        val = effective[field_name]
        if isinstance(val, list):
            effective[field_name] = []
        elif isinstance(val, (int, float)):
            effective[field_name] = 0
        else:
            effective[field_name] = ""
    return effective


# ---------------------------------------------------------------------------
# Fight-day protocol stub
# ---------------------------------------------------------------------------

def build_fight_day_protocol(
    *,
    full_name: str,
    technical_style: str,
    tactical_style: str,
    stance: str,
    fatigue_level: str,
    injuries: list[str],
    restrictions: list[Any],
    rounds_format: str,
    mindset_challenges: str,
    current_weight: str | float,
    target_weight: str | float,
) -> dict[str, Any]:
    """Generate a fight-day-only output that bypasses normal weekly planning.

    Returns a dict with the same top-level keys as a normal plan result so
    callers can use it as a drop-in replacement.
    """
    name = full_name or "Athlete"
    injury_note = ""
    if injuries:
        injury_note = (
            "\n\n**Injury awareness:** "
            + "; ".join(injuries)
            + ". Warm up gently around affected areas."
        )
    restriction_note = ""
    if restrictions:
        restriction_note = "\n\n**Movement restrictions remain active.** Do not test restricted ranges during warm-up."

    cue = ""
    if mindset_challenges:
        cue = f"\n\n**Fight cue:** {mindset_challenges.strip().split('.')[0].strip()}."

    plan_text = (
        f"# {name} — Fight Day Protocol\n\n"
        f"## Activation & Warm-Up\n"
        f"- 5–8 min general movement: light skipping, arm circles, hip circles\n"
        f"- 3–5 min shadow work at 50–60 % tempo ({stance} stance, rhythm only)\n"
        f"- 2 min breathing reset: 4-count inhale, 6-count exhale\n"
        f"- 1–2 min pad touch or partner mirror drill (optional)\n\n"
        f"## Tactical Reminder\n"
        f"- Style: {technical_style or 'general'} / {tactical_style or 'general'}\n"
        f"- Rounds: {rounds_format or 'as scheduled'}\n"
        f"- Focus on your game plan. Nothing new.{cue}\n\n"
        f"## Fueling & Logistics\n"
        f"- Light meal 3–4 hours before fight time\n"
        f"- Sip water/electrolytes — do not over-hydrate\n"
        f"- Arrive early, walk the venue, settle nerves\n\n"
        f"## Post-Fight Recovery\n"
        f"- Hydrate immediately\n"
        f"- Light meal within 60 min\n"
        f"- Ice any contact areas\n"
        f"- Full rest day tomorrow"
        f"{injury_note}{restriction_note}"
    )

    return {
        "fight_day_protocol": True,
        "plan_text": plan_text,
        "coach_notes": f"Fight day for {name}. No training plan generated.",
        "why_log": {"fight_day": [{"note": "D-0 short-circuit — fight-day protocol only"}]},
    }
