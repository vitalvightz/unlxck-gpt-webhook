from __future__ import annotations

import logging
import re
from time import perf_counter

from .build_block import (
    PhaseBlock,
    _md_to_html,
    build_html_document,
    html_to_pdf,
    upload_to_supabase,
)
from .plan_pipeline_runtime import (
    PHASES,
    PHASE_PLAN_TITLES,
    SANITIZE_LABELS,
    PlanBlocksBundle,
    PlanRuntimeContext,
    RenderedPlanBundle,
    TimingRecorder,
    _apply_muay_thai_filters,
)
from .plan_rendering_utils import sanitize_phase_text, sanitize_stage_output
from .stage2_payload import build_planning_brief, build_stage2_handoff_text, build_stage2_payload


def _sparring_adjustment_lines(context: PlanRuntimeContext) -> list[str]:
    hard_days = [str(day).strip() for day in (context.plan_input.hard_sparring_days or []) if str(day).strip()]
    technical_days = [str(day).strip() for day in (context.plan_input.technical_skill_days or []) if str(day).strip()]

    lines = ["### Sparring & Conditioning Adjustments", ""]
    if hard_days:
        lines.append(
            f"- **Expected hard sparring days:** {', '.join(hard_days)} -> Let these days own the main collision-heavy combat load and cut same-day or next-day S&C volume by about 30%."
        )
    else:
        lines.append("- **If hard sparring lands today** -> Keep S&C but cut volume by about 30% and trim accessories first.")

    if technical_days:
        lines.append(
            f"- **Technical / lighter skill days:** {', '.join(technical_days)} -> Use these for cleaner aerobic support, recovery, or lower-noise strength support."
        )
    if not hard_days:
        lines.append("- **If no sparring is fixed this week** -> Add one clear fight-pace conditioning exposure before extra lifting.")
    lines.append("")
    return lines


def _sparring_nutrition_lines(context: PlanRuntimeContext) -> list[str]:
    hard_days = [str(day).strip() for day in (context.plan_input.hard_sparring_days or []) if str(day).strip()]
    header = "- **On Expected Hard Sparring Days:**"
    if hard_days:
        header = f"- **On Expected Hard Sparring Days ({', '.join(hard_days)}):**"
    return [
        header,
        "  - Increase intra-workout carbs (e.g., 30g HBCD during session).",
        "  - Post-session: 1.2g/kg carbs + 0.4g/kg protein within 30 mins.",
        "- **If Sparring Was Unexpectedly Hard:**",
        "  - Add 500mg sodium + 20oz electrolyte drink immediately.",
        "",
    ]

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


def _build_coach_notes(context: PlanRuntimeContext, blocks: PlanBlocksBundle) -> str:
    sections: list[str] = []
    previous = set(context.training_context.prev_exercises)
    if previous:
        all_strength_names = [name for phase in PHASES for name in blocks.strength_names.get(phase, [])]
        all_conditioning_names = [name for phase in PHASES for name in blocks.conditioning_names.get(phase, [])]
        novel_strength = [name for name in all_strength_names if name not in previous]
        novel_conditioning = [name for name in all_conditioning_names if name not in previous]
        sections.append(
            f"Novelty Summary: {len(novel_strength)} new strength moves, {len(novel_conditioning)} new conditioning drills."
        )
    if blocks.coach_review_notes:
        sections.append(blocks.coach_review_notes)

    coach_notes = "\n\n".join(section for section in sections if section).strip()
    if not coach_notes:
        return ""
    if context.apply_muay_thai_filters:
        coach_notes = _apply_muay_thai_filters(coach_notes, allow_grappling=False)
    return sanitize_phase_text(coach_notes, context.sanitize_labels)


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
        *_sparring_adjustment_lines(context),
        "---",
        "",
        *_sparring_nutrition_lines(context),
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
        f"- Hard Sparring Days: {', '.join(context.plan_input.hard_sparring_days) if context.plan_input.hard_sparring_days else 'Not specified'}",
        f"- Technical Skill Days: {', '.join(context.plan_input.technical_skill_days) if context.plan_input.technical_skill_days else 'Not specified'}",
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
        f"- Hard Sparring Days: {', '.join(context.plan_input.hard_sparring_days) if context.plan_input.hard_sparring_days else 'Not specified'}",
        f"- Technical Skill Days: {', '.join(context.plan_input.technical_skill_days) if context.plan_input.technical_skill_days else 'Not specified'}",
        f"- Equipment Access: {context.equipment_access_display}",
        f"- Weaknesses: {context.plan_input.weak_areas}",
        f"- Key Goals: {context.plan_input.key_goals}",
        f"- Mindset Challenges: {', '.join(context.training_context.mental_block)}",
        f"- Notes: {context.plan_input.notes}",
    ]
    athlete_profile_html = _md_to_html("\n".join(profile_lines))
    adjustments_table = _md_to_html("\n".join(line for line in _sparring_adjustment_lines(context) if line))
    sparring_nutrition_html = _md_to_html("\n".join(line for line in _sparring_nutrition_lines(context) if line))

    coach_notes = _build_coach_notes(context, blocks)

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

