from __future__ import annotations

import logging
from time import perf_counter

from .coach_review import run_coach_review
from .conditioning import generate_conditioning_block
from .mindset_module import get_mindset_by_phase, get_phase_mindset_cues
from .nutrition import generate_nutrition_block
from .plan_pipeline_runtime import (
    PHASES,
    PHASE_COLORS,
    PlanBlocksBundle,
    PlanRuntimeContext,
    TimingRecorder,
    _apply_muay_thai_filters,
)
from .plan_rendering_utils import sanitize_phase_text
from .recovery import generate_recovery_block
from .rehab_protocols import (
    format_injury_guardrails,
    generate_rehab_protocols,
    generate_support_notes,
)
from .strength import generate_strength_block
from .training_context import TrainingContext, allocate_sessions

def _build_phase_mindsets(training_context: TrainingContext) -> tuple[dict[str, str], dict[str, str]]:
    phase_mindset_cues = get_phase_mindset_cues(training_context.mental_block)
    phase_mindsets: dict[str, str] = {}
    # Compute once; reused for every non-generic phase below.
    base_flags = training_context.to_flags()

    for phase in PHASES:
        blocks = training_context.mental_block
        if isinstance(blocks, str):
            blocks = [blocks]
        if blocks and blocks[0].lower() != "generic":
            phase_mindsets[phase] = get_mindset_by_phase(phase, base_flags)
        else:
            phase_mindsets[phase] = get_mindset_by_phase(phase, {"mental_block": ["generic"]})

    return phase_mindset_cues, phase_mindsets


def _generate_strength_blocks(context: PlanRuntimeContext, phase_mindset_cues: dict[str, str]) -> tuple[dict[str, dict | None], dict[str, list[dict]]]:
    strength_blocks: dict[str, dict | None] = {phase: None for phase in PHASES}
    strength_reason_log: dict[str, list[dict]] = {}
    previous_names: list[str] = []
    previous_movements: set[str] = set()
    # Compute once per request; spread into per-phase flags dict below.
    base_flags = context.training_context.to_flags()

    for phase in PHASES:
        if not context.phase_active(phase):
            continue
        flags = {
            **base_flags,
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
    # Compute once per request; spread into per-phase flags dict below.
    base_flags = context.training_context.to_flags()

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
                **base_flags,
                "phase": phase,
                "sport": context.mapped_format,
                "random_seed": context.random_seed,
                "time_to_fight_days": context.plan_input.days_until_fight,
                "weeks_out": context.plan_input.weeks_out,
                "restrictions": context.plan_input.restrictions,
                "ignore_restrictions": context.selection_ignore_restrictions,
            }
        )
        render_metadata = {
            "num_sessions": allocate_sessions(context.training_context.training_frequency, phase).get("conditioning", 1),
            "diagnostic_context": {
                "phase": phase,
                "sport": context.mapped_format,
                "time_to_fight_days": context.plan_input.days_until_fight,
                "days_until_fight": context.plan_input.days_until_fight,
                "weeks_out": context.plan_input.weeks_out,
                "fatigue_level": context.training_context.fatigue,
                "injuries": context.training_context.injuries,
                "fight_format": context.training_context.fight_format,
            },
            "sport": context.mapped_format,
        }
        grouped_drills = grouped_drills or {}
        conditioning_reason_log[phase] = reasons
        conditioning_blocks[phase] = {
            "block": block_text,
            "names": names,
            "why_log": reasons,
            "grouped_drills": grouped_drills,
            "missing_systems": missing_systems,
            "candidate_reservoir": candidate_reservoir,
            "phase_color": PHASE_COLORS[phase],
            "num_sessions": render_metadata.get("num_sessions", 1),
            "diagnostic_context": render_metadata.get("diagnostic_context", {}),
            "sport": render_metadata.get("sport"),
        }

    return conditioning_blocks, conditioning_reason_log


def _first_active_phase(phase_weeks: dict) -> str:
    return next((phase for phase in PHASES if phase_weeks.get(phase, 0) > 0 or phase_weeks.get("days", {}).get(phase, 0) >= 1), "GPP")


def _build_phase_support_block(context: PlanRuntimeContext, builder) -> str:
    active_phases = [phase for phase in PHASES if context.phase_active(phase)]
    sections: list[str] = []

    for phase in active_phases:
        block = builder(phase).strip()
        if not block:
            continue
        if len(active_phases) == 1:
            sections.append(block)
        else:
            sections.extend([f"### {phase}", block])

    return "\n\n".join(section for section in sections if section)


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
        phase: format_injury_guardrails(
            phase,
            context.plan_input.injuries,
            context.plan_input.restrictions,
            parsed_entries=context.plan_input.parsed_injuries,
        )
        for phase in PHASES
    }
    has_injuries = bool(context.injuries_only_text or context.plan_input.restrictions)
    current_phase = _first_active_phase(context.phase_weeks)
    # Compute once; captured as a default argument by each builder lambda so
    # the dict is not re-created for every active phase.
    base_flags = context.training_context.to_flags()
    recovery_block = _build_phase_support_block(
        context,
        lambda phase, bf=base_flags: generate_recovery_block({**bf, "phase": phase}),
    )
    nutrition_block = _build_phase_support_block(
        context,
        lambda phase, bf=base_flags: generate_nutrition_block(flags={**bf, "phase": phase}),
    )
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


def _names_from_grouped(grouped: dict[str, list[dict]] | None) -> list[str]:
    grouped = grouped or {}
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

    timer_start = perf_counter()
    (
        rehab_blocks,
        guardrails,
        support_notes,
        has_injuries,
        current_phase,
        recovery_block,
        nutrition_block,
    ) = _generate_rehab_support_bundle(context)
    record_timing("rehab_support_bundle", timer_start)

    timer_start = perf_counter()
    coach_review_notes, strength_blocks, conditioning_blocks, substitutions = run_coach_review(
        injury_string=context.injuries_only_text,
        phase=current_phase,
        training_context=context.training_context.to_flags(),
        parsed_injury_entries=context.plan_input.parsed_injuries,
        exercise_bank=context.exercise_bank,
        conditioning_banks=[context.conditioning_bank, context.style_conditioning_bank],
        strength_blocks=strength_blocks,
        conditioning_blocks=conditioning_blocks,
    )
    record_timing("coach_review", timer_start)

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


