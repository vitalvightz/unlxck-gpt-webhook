from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from .build_block import (
    PhaseBlock,
    _md_to_html,
    build_html_document,
    html_to_pdf,
    upload_to_supabase,
)
from .camp_phases import calculate_phase_weeks
from .coach_review import run_coach_review
from .conditioning import (
    generate_conditioning_block,
    get_conditioning_bank,
    get_style_conditioning_bank,
    prime_conditioning_banks,
)
from .input_parsing import PlanInput, is_short_notice_days
from .mindset_module import classify_mental_block, get_mindset_by_phase, get_phase_mindset_cues
from .nutrition import generate_nutrition_block
from .plan_rendering_utils import sanitize_phase_text, sanitize_stage_output
from .recovery import generate_recovery_block
from .rehab_protocols import (
    format_injury_guardrails,
    generate_rehab_protocols,
    generate_support_notes,
    prime_rehab_bank,
)
from .stage2_payload import build_planning_brief, build_stage2_handoff_text, build_stage2_payload
from .strength import (
    generate_strength_block,
    get_exercise_bank as get_strength_exercise_bank,
    prime_strength_banks,
)
from .tag_maps import GOAL_NORMALIZER, WEAKNESS_NORMALIZER
from .training_context import TrainingContext, allocate_sessions, normalize_equipment_list

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


def prime_plan_banks() -> None:
    prime_strength_banks()
    prime_conditioning_banks()
    prime_rehab_bank()


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
        return not bool(self.plan_input.restrictions)


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


def build_runtime_context(*, plan_input: PlanInput, random_seed: Any, logger: logging.Logger) -> PlanRuntimeContext:
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
    weight_val = float(weight) if weight.replace(".", "", 1).isdigit() else 0.0
    target_val = float(target_weight) if target_weight.replace(".", "", 1).isdigit() else 0.0
    weight_cut_risk_flag = weight_val - target_val >= 0.05 * target_val if target_val else False
    weight_cut_pct_val = round((weight_val - target_val) / target_val * 100, 1) if target_val else 0.0
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

    training_context = TrainingContext(
        fatigue=plan_input.fatigue.lower(),
        training_frequency=plan_input.training_frequency,
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
        training_split=allocate_sessions(plan_input.training_frequency),
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
def _build_phase_mindsets(training_context: TrainingContext) -> tuple[dict[str, str], dict[str, str]]:
    phase_mindset_cues = get_phase_mindset_cues(training_context.mental_block)
    phase_mindsets: dict[str, str] = {}

    for phase in PHASES:
        blocks = training_context.mental_block
        if isinstance(blocks, str):
            blocks = [blocks]
        if blocks and blocks[0].lower() != "generic":
            phase_mindsets[phase] = get_mindset_by_phase(phase, training_context.to_flags())
        else:
            phase_mindsets[phase] = get_mindset_by_phase(phase, {"mental_block": ["generic"]})

    return phase_mindset_cues, phase_mindsets


def _generate_strength_blocks(context: PlanRuntimeContext, phase_mindset_cues: dict[str, str]) -> tuple[dict[str, dict | None], dict[str, list[dict]]]:
    strength_blocks: dict[str, dict | None] = {phase: None for phase in PHASES}
    strength_reason_log: dict[str, list[dict]] = {}
    previous_names: list[str] = []
    previous_movements: set[str] = set()

    for phase in PHASES:
        if not context.phase_active(phase):
            continue
        flags = {
            **context.training_context.to_flags(),
            "phase": phase,
            "random_seed": context.random_seed,
            "restrictions": context.plan_input.restrictions,
            "ignore_restrictions": context.selection_ignore_restrictions,
        }
        if previous_names:
            flags["prev_exercises"] = previous_names
            flags["recent_exercises"] = list(previous_movements)
        block = generate_strength_block(
            flags=flags,
            weaknesses=context.training_context.weaknesses,
            mindset_cue=phase_mindset_cues.get(phase),
        )
        strength_blocks[phase] = block
        strength_reason_log[phase] = block.get("why_log", [])
        phase_names = [exercise["name"] for exercise in block.get("exercises", []) if exercise.get("name")]
        phase_movements = {
            exercise["movement"]
            for exercise in block.get("exercises", [])
            if exercise.get("movement")
        }
        previous_names = list({*previous_names, *phase_names})
        previous_movements |= phase_movements

    return strength_blocks, strength_reason_log


def _generate_conditioning_blocks(context: PlanRuntimeContext) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    conditioning_blocks: dict[str, dict] = {}
    conditioning_reason_log: dict[str, list[dict]] = {}

    for phase in PHASES:
        if not context.phase_active(phase):
            continue
        (
            block_text,
            names,
            reasons,
            grouped_drills,
            missing_systems,
            candidate_reservoir,
        ) = generate_conditioning_block(
            {
                **context.training_context.to_flags(),
                "phase": phase,
                "random_seed": context.random_seed,
                "restrictions": context.plan_input.restrictions,
                "ignore_restrictions": context.selection_ignore_restrictions,
            }
        )
        conditioning_reason_log[phase] = reasons
        conditioning_blocks[phase] = {
            "block": block_text,
            "names": names,
            "why_log": reasons,
            "grouped_drills": grouped_drills,
            "missing_systems": missing_systems,
            "candidate_reservoir": candidate_reservoir,
            "phase_color": PHASE_COLORS[phase],
        }

    return conditioning_blocks, conditioning_reason_log


def _first_active_phase(phase_weeks: dict) -> str:
    return next((phase for phase in PHASES if phase_weeks.get(phase, 0) > 0 or phase_weeks.get("days", {}).get(phase, 0) >= 1), "GPP")


def _generate_rehab_support_bundle(context: PlanRuntimeContext) -> tuple[dict[str, str], dict[str, str], str, bool, str, str, str]:
    rehab_blocks = {phase: "" for phase in PHASES}
    seen_rehab_drills: set[str] = set()

    if context.phase_active("GPP"):
        rehab_blocks["GPP"], seen_rehab_drills = generate_rehab_protocols(
            injury_string=context.injuries_only_text,
            exercise_data=context.exercise_bank,
            current_phase="GPP",
            seen_drills=seen_rehab_drills,
        )
        if rehab_blocks["GPP"].strip().startswith("**Red Flag Detected**"):
            rehab_blocks["SPP"] = rehab_blocks["GPP"]
            rehab_blocks["TAPER"] = rehab_blocks["GPP"]

    if not rehab_blocks["GPP"].strip().startswith("**Red Flag Detected**"):
        for phase in ("SPP", "TAPER"):
            if context.phase_active(phase):
                rehab_blocks[phase], seen_rehab_drills = generate_rehab_protocols(
                    injury_string=context.injuries_only_text,
                    exercise_data=context.exercise_bank,
                    current_phase=phase,
                    seen_drills=seen_rehab_drills,
                )

    guardrails = {
        phase: format_injury_guardrails(phase, context.plan_input.injuries, context.plan_input.restrictions)
        for phase in PHASES
    }
    has_injuries = bool(context.injuries_only_text or context.plan_input.restrictions)
    current_phase = _first_active_phase(context.phase_weeks)
    recovery_block = generate_recovery_block({**context.training_context.to_flags(), "phase": current_phase})
    nutrition_block = generate_nutrition_block(flags={**context.training_context.to_flags(), "phase": current_phase})
    support_notes = generate_support_notes(context.injuries_only_text) if has_injuries else ""

    if context.apply_muay_thai_filters:
        rehab_blocks = {
            phase: _apply_muay_thai_filters(text, allow_grappling=False)
            for phase, text in rehab_blocks.items()
        }
        guardrails = {
            phase: _apply_muay_thai_filters(text, allow_grappling=False)
            for phase, text in guardrails.items()
        }
        support_notes = _apply_muay_thai_filters(support_notes, allow_grappling=False)

    rehab_blocks = {
        phase: sanitize_phase_text(text, context.sanitize_labels)
        for phase, text in rehab_blocks.items()
    }
    guardrails = {
        phase: sanitize_phase_text(text, context.sanitize_labels)
        for phase, text in guardrails.items()
    }
    support_notes = sanitize_phase_text(support_notes, context.sanitize_labels) if support_notes else ""

    return rehab_blocks, guardrails, support_notes, has_injuries, current_phase, recovery_block, nutrition_block


def _names_from_grouped(grouped: dict[str, list[dict]]) -> list[str]:
    return [
        drill.get("name")
        for drills in grouped.values()
        for drill in drills
        if drill.get("name")
    ]


def _apply_substitution_log(reason_log: dict[str, list[dict]], substitutions: list[dict], module: str) -> None:
    for substitution in substitutions:
        if substitution["module"] != module:
            continue
        phase_key = substitution["phase"]
        logs = reason_log.get(phase_key, [])
        logs = [entry for entry in logs if entry.get("name") != substitution["old"]]
        if substitution.get("new"):
            logs.append(
                {
                    "name": substitution["new"],
                    "reasons": {},
                    "explanation": "coach safety substitution",
                }
            )
        reason_log[phase_key] = logs


def generate_plan_blocks(
    *,
    context: PlanRuntimeContext,
    record_timing: TimingRecorder,
    logger: logging.Logger,
) -> PlanBlocksBundle:
    timer_start = perf_counter()
    phase_mindset_cues, phase_mindsets = _build_phase_mindsets(context.training_context)
    record_timing("mindset", timer_start)

    logger.info(
        "[stage] selection_ignore_restrictions=%s restrictions_present=%s restrictions_count=%d",
        context.selection_ignore_restrictions,
        bool(context.plan_input.restrictions),
        len(context.plan_input.restrictions or []),
    )

    timer_start = perf_counter()
    strength_blocks, strength_reason_log = _generate_strength_blocks(context, phase_mindset_cues)
    record_timing("strength", timer_start)

    timer_start = perf_counter()
    conditioning_blocks, conditioning_reason_log = _generate_conditioning_blocks(context)
    record_timing("conditioning", timer_start)

    (
        rehab_blocks,
        guardrails,
        support_notes,
        has_injuries,
        current_phase,
        recovery_block,
        nutrition_block,
    ) = _generate_rehab_support_bundle(context)

    coach_review_notes, strength_blocks, conditioning_blocks, substitutions = run_coach_review(
        injury_string=context.injuries_only_text,
        phase=current_phase,
        training_context=context.training_context.to_flags(),
        exercise_bank=context.exercise_bank,
        conditioning_banks=[context.conditioning_bank, context.style_conditioning_bank],
        strength_blocks=strength_blocks,
        conditioning_blocks=conditioning_blocks,
    )

    _apply_substitution_log(strength_reason_log, substitutions, "Strength")
    _apply_substitution_log(conditioning_reason_log, substitutions, "Conditioning")

    for phase in PHASES:
        if strength_blocks.get(phase):
            strength_blocks[phase]["why_log"] = strength_reason_log.get(phase, [])
        if conditioning_blocks.get(phase):
            conditioning_blocks[phase]["why_log"] = conditioning_reason_log.get(phase, [])

    strength_names = {
        phase: [exercise["name"] for exercise in strength_blocks[phase].get("exercises", []) if exercise.get("name")]
        if strength_blocks.get(phase)
        else []
        for phase in PHASES
    }
    conditioning_names = {
        phase: _names_from_grouped(conditioning_blocks[phase].get("grouped_drills", {}))
        if conditioning_blocks.get(phase)
        else []
        for phase in PHASES
    }

    return PlanBlocksBundle(
        phase_mindsets=phase_mindsets,
        strength_blocks=strength_blocks,
        conditioning_blocks=conditioning_blocks,
        rehab_blocks=rehab_blocks,
        guardrails=guardrails,
        nutrition_block=nutrition_block,
        recovery_block=recovery_block,
        has_injuries=has_injuries,
        support_notes=support_notes,
        strength_reason_log=strength_reason_log,
        conditioning_reason_log=conditioning_reason_log,
        strength_names=strength_names,
        conditioning_names=conditioning_names,
        coach_review_notes=coach_review_notes,
        current_phase=current_phase,
    )

def _week_str(weeks: int, days: int) -> str:
    return "~1" if weeks == 0 and days > 0 else str(weeks)


def _display_phase_text(context: PlanRuntimeContext, text: str) -> str:
    if context.apply_muay_thai_filters:
        return _apply_muay_thai_filters(text, allow_grappling=False)
    return text


def _build_phase_model(name: str, weeks: int, days: int, mindset: str, strength: str, conditioning: str, guardrails: str) -> PhaseBlock:
    mindset = sanitize_phase_text(mindset, SANITIZE_LABELS)
    strength = sanitize_phase_text(strength, SANITIZE_LABELS)
    conditioning = sanitize_phase_text(conditioning, SANITIZE_LABELS)
    guardrails = sanitize_phase_text(guardrails, SANITIZE_LABELS) if guardrails else guardrails
    mindset = sanitize_stage_output(mindset)
    strength = sanitize_stage_output(strength)
    conditioning = sanitize_stage_output(conditioning)
    guardrails = sanitize_stage_output(guardrails) if guardrails else guardrails
    return PhaseBlock(
        name=name,
        weeks=weeks,
        days=days,
        mindset=mindset,
        strength=strength,
        conditioning=conditioning,
        guardrails=guardrails,
    )


def _format_rationale_section(title: str, phases: dict[str, list[dict]]) -> list[str]:
    lines = [f"### {title}"]
    for phase, entries in phases.items():
        lines.append(f"#### {phase}")
        for entry in entries:
            name = entry.get("name", "Unnamed")
            explanation = entry.get("explanation", "")
            if explanation:
                lines.append(f"- {name}: {explanation}")
            else:
                lines.append(f"- {name}")
    return lines


def render_plan_bundle(*, context: PlanRuntimeContext, blocks: PlanBlocksBundle, logger: logging.Logger) -> RenderedPlanBundle:
    week_str = {
        phase: _week_str(context.phase_weeks[phase], context.phase_weeks["days"][phase])
        for phase in PHASES
    }
    phase_split = f"{week_str['GPP']} / {week_str['SPP']} / {week_str['TAPER']}"
    phase_week_summary = f"{week_str['GPP']} GPP / {week_str['SPP']} SPP / {week_str['TAPER']} Taper"
    phase_day_summary = (
        f"{context.phase_weeks['days']['GPP']} GPP / {context.phase_weeks['days']['SPP']} SPP / "
        f"{context.phase_weeks['days']['TAPER']} Taper"
    )
    days_out_line = (
        f"- Days Out: {context.plan_input.days_until_fight}"
        if isinstance(context.plan_input.days_until_fight, int)
        else f"- Weeks Out: {context.plan_input.weeks_out}"
    )

    phase_num = 1
    fight_plan_lines = ["# FIGHT CAMP PLAN"]
    phase_models: dict[str, PhaseBlock] = {}

    for phase in PHASES:
        if not context.phase_active(phase):
            continue
        phase_name = (
            f"PHASE {phase_num}: {PHASE_PLAN_TITLES[phase]} - {week_str[phase]} WEEKS "
            f"({context.phase_weeks['days'][phase]} DAYS)"
        )
        mindset = _display_phase_text(context, blocks.phase_mindsets.get(phase, ""))
        strength = _display_phase_text(
            context,
            blocks.strength_blocks[phase]["block"] if blocks.strength_blocks.get(phase) else "",
        )
        conditioning = _display_phase_text(
            context,
            blocks.conditioning_blocks.get(phase, {}).get("block", ""),
        )
        guardrails = blocks.guardrails.get(phase, "") if blocks.has_injuries else ""

        fight_plan_lines += [
            f"## {phase_name}",
            "",
            "### Mindset Focus",
            mindset,
            "",
            "### Strength & Power",
            strength,
            "",
            "### Conditioning",
            conditioning,
            "",
        ]
        if blocks.has_injuries:
            fight_plan_lines += ["### Injury Guardrails", f"Phase: {phase}", guardrails, ""]

        phase_models[phase] = _build_phase_model(
            phase_name,
            context.phase_weeks[phase],
            context.phase_weeks["days"][phase],
            mindset,
            strength,
            conditioning,
            guardrails,
        )
        phase_num += 1

    fight_plan_lines += [
        "## Nutrition",
        blocks.nutrition_block,
        "",
        "## Recovery",
        blocks.recovery_block,
        "",
    ]

    rehab_sections: list[str] = []
    if blocks.has_injuries:
        rehab_sections = ["## Rehab Protocols"]
        for phase in PHASES:
            rehab_block = blocks.rehab_blocks.get(phase, "")
            if rehab_block:
                rehab_sections += [f"### {phase}", rehab_block.strip(), ""]
        if blocks.support_notes:
            rehab_sections += ["", blocks.support_notes]
    if rehab_sections:
        fight_plan_lines += rehab_sections

    fight_plan_lines += [
        "",
        "## Mindset Overview",
        f"Primary Block(s): {', '.join(context.training_context.mental_block).title()}",
        "",
        "### Sparring & Conditioning Adjustments",
        "",
        "- **If technical sparring is today** -> Keep S&C but **cut volume by 30%**",
        "- **If no sparring this week** -> Add an **extra glycolytic conditioning session** (e.g., 5x3min bag rounds)",
        "",
        "---",
        "",
        "- **On Expected Hard Sparring Days:**",
        "  - Increase intra-workout carbs (e.g., 30g HBCD during session).",
        "  - Post-session: 1.2g/kg carbs + 0.4g/kg protein within 30 mins.",
        "- **If Sparring Was Unexpectedly Hard:**",
        "  - Add 500mg sodium + 20oz electrolyte drink immediately.",
        "",
        "## Athlete Profile",
        f"- **Name:** {context.plan_input.full_name}",
        f"- Age: {context.plan_input.age}",
        f"- Weight: {context.plan_input.weight}kg",
        f"- Target Weight: {context.plan_input.target_weight}kg",
        f"- Height: {context.plan_input.height}cm",
        f"- Technical Style: {context.plan_input.fighting_style_technical}",
        f"- Tactical Style: {context.plan_input.fighting_style_tactical}",
        f"- Stance: {context.plan_input.stance}",
        f"- Status: {context.plan_input.status}",
        f"- Record: {context.plan_input.record}",
        f"- Fight Format: {context.plan_input.rounds_format}",
        f"- Fight Date: {context.plan_input.next_fight_date}",
        days_out_line,
        f"- Phase Weeks: {phase_week_summary}",
        f"- Phase Days: {phase_day_summary}",
        f"- Fatigue Level: {context.plan_input.fatigue}",
        f"- Injuries: {context.injuries_display}",
        f"- Training Availability: {context.plan_input.available_days}",
        f"- Equipment Access: {context.equipment_access_display}",
        f"- Weaknesses: {context.plan_input.weak_areas}",
        f"- Key Goals: {context.plan_input.key_goals}",
        f"- Mindset Challenges: {', '.join(context.training_context.mental_block)}",
        f"- Notes: {context.plan_input.notes}",
    ]

    rehab_html = ""
    if blocks.has_injuries:
        rehab_parts: list[str] = []
        for phase in PHASES:
            rehab_block = blocks.rehab_blocks.get(phase, "")
            if rehab_block:
                rehab_parts.append(f"<h3>{phase}</h3>")
                rehab_parts.append(_md_to_html(rehab_block.strip()))
        if blocks.support_notes:
            rehab_parts.append(_md_to_html(blocks.support_notes))
        rehab_html = "\n".join(rehab_parts)

    profile_lines = [
        f"- **Name:** {context.plan_input.full_name}",
        f"- Age: {context.plan_input.age}",
        f"- Weight: {context.plan_input.weight}kg",
        f"- Target Weight: {context.plan_input.target_weight}kg",
        f"- Height: {context.plan_input.height}cm",
        f"- Technical Style: {context.plan_input.fighting_style_technical}",
        f"- Tactical Style: {context.plan_input.fighting_style_tactical}",
        f"- Stance: {context.plan_input.stance}",
        f"- Status: {context.plan_input.status}",
        f"- Record: {context.plan_input.record}",
        f"- Fight Format: {context.plan_input.rounds_format}",
        f"- Fight Date: {context.plan_input.next_fight_date}",
        days_out_line,
        f"- Phase Weeks: {phase_week_summary}",
        f"- Phase Days: {phase_day_summary}",
        f"- Fatigue Level: {context.plan_input.fatigue}",
        f"- Injuries: {context.injuries_display}",
        f"- Training Availability: {context.plan_input.available_days}",
        f"- Equipment Access: {context.equipment_access_display}",
        f"- Weaknesses: {context.plan_input.weak_areas}",
        f"- Key Goals: {context.plan_input.key_goals}",
        f"- Mindset Challenges: {', '.join(context.training_context.mental_block)}",
        f"- Notes: {context.plan_input.notes}",
    ]
    athlete_profile_html = _md_to_html("\n".join(profile_lines))
    adjustments_table = _md_to_html(
        "- If sparring today: reduce S&C by 30%\n"
        "- No sparring this week: add extra glycolytic conditioning"
    )
    sparring_nutrition_html = _md_to_html(
        "- **On Expected Hard Sparring Days:**\n"
        "  - Increase intra-workout carbs (e.g., 30g HBCD during session).\n"
        "  - Post-session: 1.2g/kg carbs + 0.4g/kg protein within 30 mins.\n"
        "- **If Sparring Was Unexpectedly Hard:**\n"
        "  - Add 500mg sodium + 20oz electrolyte drink immediately."
    )

    previous = set(context.training_context.prev_exercises)
    all_strength_names = [name for phase in PHASES for name in blocks.strength_names.get(phase, [])]
    all_conditioning_names = [name for phase in PHASES for name in blocks.conditioning_names.get(phase, [])]
    novel_strength = [name for name in all_strength_names if name not in previous]
    novel_conditioning = [name for name in all_conditioning_names if name not in previous]
    coach_notes = (
        f"Novelty Summary: {len(novel_strength)} new strength moves, {len(novel_conditioning)} new conditioning drills."
    )
    if blocks.coach_review_notes:
        coach_notes = f"{coach_notes}\n\n{blocks.coach_review_notes}"
    if context.apply_muay_thai_filters:
        coach_notes = _apply_muay_thai_filters(coach_notes, allow_grappling=False)
    coach_notes = sanitize_phase_text(coach_notes, context.sanitize_labels)

    selection_rationale_md = "\n\n".join(
        section
        for section in (
            "\n".join(_format_rationale_section("Strength Selection", blocks.strength_reason_log)),
            "\n".join(_format_rationale_section("Conditioning Selection", blocks.conditioning_reason_log)),
        )
        if section
    )
    if context.apply_muay_thai_filters:
        selection_rationale_md = _apply_muay_thai_filters(selection_rationale_md, allow_grappling=False)
    selection_rationale_md = sanitize_phase_text(selection_rationale_md, context.sanitize_labels)
    selection_rationale_md = sanitize_stage_output(selection_rationale_md)
    fight_plan_lines += ["## Selection Rationale", selection_rationale_md]

    fight_plan_text = "\n\n".join(fight_plan_lines)
    fight_plan_text = re.sub(r"\n{3,}", "\n\n", fight_plan_text)

    logger.info("plan generated locally (first 500 chars): %s", fight_plan_text[:500])

    html = build_html_document(
        full_name=context.plan_input.full_name,
        sport=context.mapped_format,
        phase_split=phase_split,
        status=context.plan_input.status,
        record=context.plan_input.record,
        gpp=phase_models.get("GPP"),
        spp=phase_models.get("SPP"),
        taper=phase_models.get("TAPER"),
        nutrition_block=blocks.nutrition_block,
        recovery_block=blocks.recovery_block,
        rehab_html=rehab_html,
        include_injury_sections=blocks.has_injuries,
        mindset_overview=f"Primary Block(s): {', '.join(context.training_context.mental_block).title()}",
        adjustments_table=adjustments_table,
        sparring_nutrition_html=sparring_nutrition_html,
        athlete_profile_html=athlete_profile_html,
        coach_notes=coach_notes,
        selection_rationale_html=_md_to_html(selection_rationale_md),
        short_notice=context.short_notice,
    )

    return RenderedPlanBundle(
        fight_plan_text=fight_plan_text,
        coach_notes=coach_notes,
        reason_log={
            "strength": blocks.strength_reason_log,
            "conditioning": blocks.conditioning_reason_log,
        },
        html=html,
    )


def export_plan_pdf(
    *,
    full_name: str,
    html: str,
    record_timing: TimingRecorder,
    logger: logging.Logger,
) -> str:
    timer_start = perf_counter()
    safe_name = full_name.replace(" ", "_") or "plan"
    pdf_path = html_to_pdf(html, f"{safe_name}_fight_plan.pdf")
    if pdf_path:
        try:
            pdf_url = upload_to_supabase(pdf_path)
        except Exception:
            logger.exception(
                "[export-error] code=pdf_upload_failed stage=upload file=%s",
                pdf_path,
            )
            pdf_url = "PDF upload failed"
    else:
        pdf_url = "PDF generation failed"
    record_timing("export_pdf", timer_start)
    return pdf_url


def build_stage2_outputs(
    *,
    context: PlanRuntimeContext,
    blocks: PlanBlocksBundle,
    rendered: RenderedPlanBundle,
) -> tuple[dict, dict, str]:
    stage2_payload = build_stage2_payload(
        training_context=context.training_context,
        mapped_format=context.mapped_format,
        record=context.plan_input.record,
        rounds_format=context.plan_input.rounds_format,
        camp_len=context.camp_len,
        short_notice=context.short_notice,
        restrictions=context.plan_input.restrictions,
        phase_weeks=context.phase_weeks,
        strength_blocks=blocks.strength_blocks,
        conditioning_blocks=blocks.conditioning_blocks,
        rehab_blocks=blocks.rehab_blocks,
    )
    planning_brief = build_planning_brief(
        athlete_model=stage2_payload["athlete_model"],
        restrictions=stage2_payload["restrictions"],
        phase_briefs=stage2_payload["phase_briefs"],
        candidate_pools=stage2_payload["candidate_pools"],
        omission_ledger=stage2_payload["omission_ledger"],
        rewrite_guidance=stage2_payload["rewrite_guidance"],
    )
    stage2_handoff_text = build_stage2_handoff_text(
        stage2_payload=stage2_payload,
        plan_text=rendered.fight_plan_text,
        coach_notes=rendered.coach_notes,
        planning_brief=planning_brief,
    )
    return stage2_payload, planning_brief, stage2_handoff_text
