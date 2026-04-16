from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from .camp_phases import calculate_phase_weeks
from .conditioning import (
    get_conditioning_bank,
    get_style_conditioning_bank,
    prime_conditioning_banks,
)
from .input_parsing import PlanInput, is_short_notice_days
from .mindset_module import classify_mental_block
from .rehab_protocols import prime_rehab_bank
from .strength import (
    get_exercise_bank as get_strength_exercise_bank,
    prime_strength_banks,
)
from .tag_maps import GOAL_NORMALIZER, WEAKNESS_NORMALIZER
from .training_context import TrainingContext, normalize_equipment_list
from .weight_cut import compute_weight_cut_pct, parse_weight_value

PHASES = ("GPP", "SPP", "TAPER")
PHASE_COLORS = {"GPP": "#4CAF50", "SPP": "#FF9800", "TAPER": "#F44336"}
PHASE_PLAN_TITLES = {
    "GPP": "GENERAL PREPARATION PHASE (GPP)",
    "SPP": "SPECIFIC PREPARATION PHASE (SPP)",
    "TAPER": "TAPER",
}
SANITIZE_LABELS = (
    "Mindset Focus",
    "Strength & Power",
    "Conditioning",
    "Injury Guardrails",
    "Selection Rationale",
    "Nutrition",
    "Recovery",
    "Rehab Protocols",
    "Mindset Overview",
    "Coach Notes",
)
GRAPPLING_STYLES = {
    "mma",
    "bjj",
    "wrestler",
    "wrestling",
    "grappler",
    "grappling",
    "judo",
    "sambo",
}
MUAY_THAI_REPLACEMENTS = {
    "Philly Shell Torture": "High-Guard + Long-Guard Defense Rounds",
    "Band-Resisted Sprawl to Sprint": "Band-Resisted Check-to-Cross Burst",
    "Grapple Circuits (High Pace)": "Clinch Pummel + Knee Burst Circuits",
    "Judo Throw Simulation": "Clinch Off-balance + Knee Entry Patterning",
}
MUAY_THAI_TERM_REPLACEMENTS = {
    "Philly Shell": "High-Guard + Long-Guard Defense",
    "Sprawl": "Check-to-Cross Burst",
    "Judo Throw": "Clinch Off-balance + Knee Entry",
    "Grapple Circuit": "Clinch Pummel + Knee Burst Circuit",
    "cage": "ring",
}
STYLE_MAP = {
    "mma": "mma",
    "boxer": "boxing",
    "boxing": "boxing",
    "kickboxer": "kickboxing",
    "muay thai": "muay_thai",
    "bjj": "mma",
    "wrestler": "mma",
    "grappler": "mma",
    "karate": "kickboxing",
}
TimingRecorder = Callable[[str, float], None]

# Module-level flag that tracks whether plan banks have been fully loaded at
# least once in this Python process. Guards the fast warm path in
# prime_plan_banks() so subsequent requests skip the three prime-function calls.
#
# Concurrency/deployment note: this is intentionally process-local and
# unsynchronised. In multi-worker deployments (for example uvicorn --workers 2),
# each worker warms its own in-memory caches on first use. In a rare concurrent
# cold-start race, two threads in the same process could both run the cold path;
# this is acceptable because the bank loaders are idempotent.
_BANKS_WARM: bool = False


def prime_plan_banks(*, logger: logging.Logger | None = None) -> None:
    """Prime all plan banks, loading JSON data into memory the first time.

    On the first call (cold path) all three bank modules are primed and a
    module-level flag is set.  Subsequent calls (warm path) short-circuit
    immediately, logging a lightweight debug message rather than re-entering
    each bank's load function.

    Passing *logger* routes messages through the caller's logger; when omitted
    a module-level logger is used instead.
    """
    global _BANKS_WARM
    _log = logger or logging.getLogger(__name__)
    if _BANKS_WARM:
        _log.debug("[bank-prime] path=warm (all caches populated, skipping)")
        return
    _t = perf_counter()
    prime_strength_banks()
    prime_conditioning_banks()
    prime_rehab_bank()
    _BANKS_WARM = True
    _log.info("[bank-prime] path=cold elapsed=%.3fs", perf_counter() - _t)


@dataclass(frozen=True)
class PlanRuntimeContext:
    plan_input: PlanInput
    random_seed: Any
    parsed_injury_phrases: list[str]
    injuries_display: str
    normalized_equipment_access: list[str]
    equipment_access_display: str
    tech_styles: list[str]
    tactical_styles: list[str]
    mapped_format: str
    selection_format: str
    pure_striker: bool
    apply_muay_thai_filters: bool
    weight_cut_risk_flag: bool
    weight_cut_pct_val: float
    mental_block_class: list[str]
    camp_len: int
    phase_weeks: dict
    short_notice: bool
    exercise_bank: list[dict]
    conditioning_bank: list[dict]
    style_conditioning_bank: list[dict]
    injuries_only_text: str
    training_context: TrainingContext
    sanitize_labels: tuple[str, ...] = SANITIZE_LABELS

    def phase_active(self, phase: str) -> bool:
        return self.phase_weeks.get(phase, 0) > 0 or self.phase_weeks.get("days", {}).get(phase, 0) >= 1

    @property
    def selection_ignore_restrictions(self) -> bool:
        return not bool(self.training_context.injury_restrictions)


@dataclass
class PlanBlocksBundle:
    phase_mindsets: dict[str, str]
    strength_blocks: dict[str, dict | None]
    conditioning_blocks: dict[str, dict]
    rehab_blocks: dict[str, str]
    guardrails: dict[str, str]
    nutrition_block: str
    recovery_block: str
    has_injuries: bool
    support_notes: str
    strength_reason_log: dict[str, list[dict]]
    conditioning_reason_log: dict[str, list[dict]]
    strength_names: dict[str, list[str]]
    conditioning_names: dict[str, list[str]]
    coach_review_notes: str
    current_phase: str


@dataclass
class RenderedPlanBundle:
    fight_plan_text: str
    coach_notes: str
    reason_log: dict[str, dict[str, list[dict]]]
    html: str


def _normalize_selection_format(sport: str) -> str:
    if sport == "muay_thai":
        return "kickboxing"
    return sport


def _is_pure_striker(tech_styles: list[str], tactical_styles: list[str]) -> bool:
    all_styles = {style.strip().lower() for style in (tech_styles + tactical_styles) if style.strip()}
    return not any(style in GRAPPLING_STYLES for style in all_styles)


# Re-exported from main for existing tests.
def _filter_mindset_blocks(blocks: list[str], tech_styles: list[str], tactical_styles: list[str]) -> list[str]:
    if not blocks:
        return ["generic"]
    if not _is_pure_striker(tech_styles, tactical_styles):
        return blocks
    filtered = [block for block in blocks if block != "fear of takedowns"]
    return filtered or ["generic"]


def _apply_muay_thai_filters(text: str, *, allow_grappling: bool) -> str:
    if not text or allow_grappling:
        return text
    for source, replacement in MUAY_THAI_REPLACEMENTS.items():
        text = re.sub(re.escape(source), replacement, text, flags=re.IGNORECASE)
    for source, replacement in MUAY_THAI_TERM_REPLACEMENTS.items():
        pattern = re.compile(rf"\b{re.escape(source)}\b", re.IGNORECASE)
        text = pattern.sub(replacement, text)
    return text


def build_runtime_context(
    *,
    plan_input: PlanInput,
    random_seed: Any,
    logger: logging.Logger,
    triage_summary: dict[str, Any] | None = None,
    is_approved_triage_resume: bool = False,
) -> PlanRuntimeContext:
    parsed_injury_phrases = [
        entry.get("original_phrase")
        for entry in plan_input.parsed_injuries
        if entry.get("original_phrase")
    ]
    injuries_display = "; ".join(parsed_injury_phrases) if parsed_injury_phrases else "None"
    normalized_equipment_access = normalize_equipment_list(plan_input.equipment_access)
    equipment_access_display = (
        ", ".join(eq.replace("_", " ").title() for eq in normalized_equipment_access)
        if normalized_equipment_access
        else "None listed"
    )

    logger.info(
        "plan_input loaded",
        extra={"plan_id": f"{plan_input.full_name or 'unknown'}-{plan_input.next_fight_date or 'no-date'}"},
    )

    tech_styles = plan_input.tech_styles
    primary_tech = tech_styles[0] if tech_styles else ""
    mapped_format = STYLE_MAP.get(primary_tech, "mma")
    selection_format = _normalize_selection_format(mapped_format)
    tactical_styles = list(plan_input.tactical_styles)
    if plan_input.stance.strip().lower() == "hybrid" and "hybrid" not in tactical_styles:
        tactical_styles.append("hybrid")
    pure_striker = _is_pure_striker(tech_styles, tactical_styles)
    apply_muay_thai_filters = mapped_format == "muay_thai" and pure_striker

    weight = plan_input.weight
    target_weight = plan_input.target_weight
    weight_val = parse_weight_value(weight)
    target_val = parse_weight_value(target_weight)
    weight_cut_pct_val = compute_weight_cut_pct(weight_val, target_val)
    weight_cut_risk_flag = weight_cut_pct_val >= 3.0
    mental_block_class = classify_mental_block(plan_input.mental_block or "")
    mental_block_class = _filter_mindset_blocks(mental_block_class, tech_styles, tactical_styles)

    camp_len = plan_input.weeks_out if isinstance(plan_input.weeks_out, int) else 8
    phase_weeks = calculate_phase_weeks(
        camp_len,
        mapped_format,
        tactical_styles,
        plan_input.status,
        plan_input.fatigue,
        weight_cut_risk_flag,
        mental_block_class,
        weight_cut_pct_val,
        plan_input.days_until_fight,
    )
    camp_len = max(1, phase_weeks["GPP"] + phase_weeks["SPP"] + phase_weeks["TAPER"])
    short_notice = is_short_notice_days(plan_input.days_until_fight)

    injuries_only_text = "; ".join(parsed_injury_phrases)
    raw_injury_list = [phrase.strip().lower() for phrase in parsed_injury_phrases if phrase.strip()]
    guided_injury = None if is_approved_triage_resume else plan_input.guided_injury
    guided_injury_dict = (
        {
            "area": guided_injury.area,
            "severity": guided_injury.severity,
            "trend": guided_injury.trend,
            "avoid": guided_injury.avoid,
            "notes": guided_injury.notes,
        }
        if guided_injury is not None
        else None
    )

    training_context = TrainingContext(
        fatigue=plan_input.fatigue.lower(),
        training_frequency=plan_input.training_frequency,
        weekly_active_session_budget=plan_input.training_frequency,
        days_available=len(plan_input.training_days),
        training_days=plan_input.training_days,
        injuries=raw_injury_list,
        style_technical=tech_styles,
        style_tactical=tactical_styles,
        weaknesses=[
            tag
            for item in [value.strip().lower() for value in plan_input.weak_areas.split(",") if value.strip()]
            for tag in WEAKNESS_NORMALIZER.get(item.lower(), [item.lower()])
        ],
        equipment=normalize_equipment_list(plan_input.equipment_access),
        weight_cut_risk=weight_cut_risk_flag,
        weight_cut_pct=weight_cut_pct_val,
        fight_format=selection_format,
        status=plan_input.status.strip().lower(),
        key_goals=[
            GOAL_NORMALIZER.get(goal.strip(), goal.strip()).lower()
            for goal in plan_input.key_goals.split(",")
            if goal.strip()
        ],
        training_preference=plan_input.training_preference.strip().lower() if plan_input.training_preference else "",
        mental_block=mental_block_class,
        age=int(plan_input.age) if plan_input.age.isdigit() else 0,
        weight=float(weight) if weight.replace(".", "", 1).isdigit() else 0.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks=phase_weeks,
        days_until_fight=plan_input.days_until_fight,
        hard_sparring_days=plan_input.hard_sparring_days,
        technical_skill_days=plan_input.technical_skill_days,
        athlete_timezone=plan_input.athlete_timezone,
        injuries_raw_text=plan_input.injuries,
        parsed_injuries=[dict(entry) for entry in plan_input.parsed_injuries],
        guided_injury=guided_injury_dict,
        injury_restrictions=[] if is_approved_triage_resume else [dict(entry) for entry in plan_input.restrictions],
        triage_summary={} if is_approved_triage_resume else dict(triage_summary or {}),
    )

    return PlanRuntimeContext(
        plan_input=plan_input,
        random_seed=random_seed,
        parsed_injury_phrases=parsed_injury_phrases,
        injuries_display=injuries_display,
        normalized_equipment_access=normalized_equipment_access,
        equipment_access_display=equipment_access_display,
        tech_styles=tech_styles,
        tactical_styles=tactical_styles,
        mapped_format=mapped_format,
        selection_format=selection_format,
        pure_striker=pure_striker,
        apply_muay_thai_filters=apply_muay_thai_filters,
        weight_cut_risk_flag=weight_cut_risk_flag,
        weight_cut_pct_val=weight_cut_pct_val,
        mental_block_class=mental_block_class,
        camp_len=camp_len,
        phase_weeks=phase_weeks,
        short_notice=short_notice,
        exercise_bank=get_strength_exercise_bank(),
        conditioning_bank=get_conditioning_bank(),
        style_conditioning_bank=get_style_conditioning_bank(),
        injuries_only_text=injuries_only_text,
        training_context=training_context,
    )
