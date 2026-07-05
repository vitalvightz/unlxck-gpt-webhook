from __future__ import annotations

import logging
import re
from typing import Any
from .build_block import (
    PhaseBlock,
    _md_to_html,
    build_html_document,
)
from .fight_date_utils import resolve_fight_weekday
from .fight_day_override import FIGHT_DAY_PROTOCOL_TEXT
from .late_selector_windows import classify_late_selector_window, is_active_late_selector_window
from .plan_pipeline_runtime import (
    PHASES,
    PHASE_PLAN_TITLES,
    SANITIZE_LABELS,
    PlanBlocksBundle,
    PlanRuntimeContext,
    RenderedPlanBundle,
    _apply_muay_thai_filters,
)
from .lead_summary import render_lead_summary
from .plan_rendering_utils import sanitize_phase_text, sanitize_stage_output
from .stage2_payload import (
    build_computed_support,
    build_planning_brief,
    build_stage2_handoff_text,
    build_stage2_payload,
)


def _insert_lead_summary(plan_text: str, lead_summary: str) -> str:
    """Insert the lead summary immediately after the plan title.

    The validator only scans the first plan lines for injury / weight-cut
    context, so the summary must sit at the very top (right after the title),
    before any training detail.
    """
    parts = plan_text.split("\n", 1)
    title = parts[0]
    rest = parts[1].lstrip("\n") if len(parts) > 1 else ""
    return f"{title}\n\n{lead_summary}\n\n{rest}".rstrip()


def _normalise_countdown_label(value: Any) -> str:
    match = re.search(r"\bD-(\d{1,2})\b", str(value or ""), re.IGNORECASE)
    if not match:
        return ""
    return f"D-{int(match.group(1))}"


def _late_fight_role_display(role: dict[str, Any]) -> str:
    label = str(role.get("athlete_facing_label") or role.get("display_label") or "").strip()
    if label:
        return label
    role_key = str(role.get("role_key") or "countdown session").replace("_", " ").strip()
    return role_key.capitalize()


def _late_fight_role_countdown_label(role: dict[str, Any]) -> str:
    return (
        _normalise_countdown_label(role.get("scheduled_countdown_label"))
        or _normalise_countdown_label(role.get("countdown_label"))
        or _normalise_countdown_label(role.get("countdown_display_label"))
    )


def _late_fight_role_display_label(role: dict[str, Any], countdown_label: str) -> str:
    display = str(role.get("countdown_display_label") or "").strip()
    if display:
        return display
    weekday = str(
        role.get("real_weekday")
        or role.get("countdown_weekday")
        or role.get("scheduled_day_hint")
        or ""
    ).strip()
    return f"{countdown_label} ({weekday.title()})" if weekday else countdown_label


def _late_fight_role_is_hidden_context(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()
    return bool(role_key == "hard_sparring_day" or (category == "sparring" and role.get("coach_owned")))


def _late_fight_sequence_from_brief(planning_brief: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("late_fight_session_sequence", "session_sequence", "countdown_sessions"):
        value = planning_brief.get(key)
        if isinstance(value, list) and value:
            return [entry for entry in value if isinstance(entry, dict)]
    spec = planning_brief.get("late_fight_plan_spec") or {}
    if isinstance(spec, dict):
        for key in ("visible_session_sequence", "session_sequence", "countdown_sessions", "sessions"):
            value = spec.get(key)
            if isinstance(value, list) and value:
                return [entry for entry in value if isinstance(entry, dict)]
    return []


def _late_fight_window_for_role(role: dict[str, Any]) -> str:
    stage_key = str(role.get("composite_segment_stage_key") or "").strip().lower()
    if stage_key:
        return stage_key
    offset = None
    label = _late_fight_role_countdown_label(role)
    if label.startswith("D-"):
        try:
            offset = int(label[2:])
        except ValueError:
            offset = None
    if offset is None:
        return ""
    if 8 <= offset <= 13:
        return "d13_to_d8"
    if offset == 7:
        return "d7"
    if 5 <= offset <= 6:
        return "d6_to_d5"
    if 2 <= offset <= 4:
        return "d4_to_d2"
    if offset == 1:
        return "d1"
    return ""


def _late_fight_preferred_cue(role: dict[str, Any]) -> str:
    return {
        "d13_to_d8": "Mobility Reset Flow",
        "d7": "Mobility Reset Flow",
        "d6_to_d5": "Reactive Shuffle Repeats",
        "d4_to_d2": "Breathing Reset",
        "d1": "Breathing Reset",
    }.get(_late_fight_window_for_role(role), "Mobility Reset Flow")


def _candidate_names_from_slot(slot: dict[str, Any]) -> list[str]:
    names: list[str] = []
    selected = slot.get("selected") or {}
    if isinstance(selected, dict):
        selected_name = str(selected.get("name") or "").strip()
        if selected_name:
            names.append(selected_name)
    for alternate in slot.get("alternates", []) or []:
        if not isinstance(alternate, dict):
            continue
        alternate_name = str(alternate.get("name") or "").strip()
        if alternate_name:
            names.append(alternate_name)
    return list(dict.fromkeys(names))


def _slots_for_phase_requirement(phase_pool: dict[str, Any], requirement: str) -> list[dict[str, Any]]:
    strength_slots = [slot for slot in phase_pool.get("strength_slots", []) or [] if isinstance(slot, dict)]
    conditioning_slots = [slot for slot in phase_pool.get("conditioning_slots", []) or [] if isinstance(slot, dict)]
    rehab_slots = [slot for slot in phase_pool.get("rehab_slots", []) or [] if isinstance(slot, dict)]
    if requirement == "rehab":
        return rehab_slots
    if requirement in {"aerobic", "glycolytic", "alactic"}:
        return [slot for slot in conditioning_slots if slot.get("role") == requirement]
    if requirement == "primary_strength":
        return strength_slots[:1]
    if requirement == "extra_strength_accessory":
        return strength_slots[1:]
    return [
        slot
        for slot in conditioning_slots + strength_slots + rehab_slots
        if slot.get("role") == requirement
    ]


def _render_late_fight_phase_notes(planning_brief: dict[str, Any]) -> list[str]:
    candidate_pools = planning_brief.get("candidate_pools") or {}
    phase_strategy = planning_brief.get("phase_strategy") or {}
    lines: list[str] = []
    for phase, strategy in phase_strategy.items():
        must_keep = [
            str(item).strip()
            for item in (strategy.get("must_keep") or [])
            if str(item).strip()
        ]
        if not must_keep:
            continue
        phase_pool = candidate_pools.get(phase) or {}
        phase_lines: list[str] = []
        for requirement in must_keep:
            names: list[str] = []
            for slot in _slots_for_phase_requirement(phase_pool, requirement):
                names.extend(_candidate_names_from_slot(slot))
            if not names:
                continue
            phase_lines.append(
                f"- {requirement.replace('_', ' ').title()}: {', '.join(list(dict.fromkeys(names))[:4])}"
            )
        if phase_lines:
            lines.extend(["", f"## {str(phase).upper()}", *phase_lines])
    return lines


def _late_fight_terminal_d0_header(context: PlanRuntimeContext, planning_brief: dict[str, Any]) -> str:
    spec = planning_brief.get("late_fight_plan_spec") or {}
    countdown_map = spec.get("countdown_weekday_map") if isinstance(spec, dict) else {}
    weekday = ""
    if isinstance(countdown_map, dict):
        weekday = str(countdown_map.get("D-0") or "").strip()
    if not weekday:
        weekday = _resolve_fight_weekday(context) or ""
    label = f"D-0 ({weekday.title()})" if weekday else "D-0"
    return f"### {label} - Fight day protocol"


def _render_late_fight_stage1_draft(
    *,
    context: PlanRuntimeContext,
    planning_brief: dict[str, Any],
) -> str | None:
    spec = planning_brief.get("late_fight_plan_spec") or {}
    if not isinstance(spec, dict) or not spec:
        return None

    sequence = _late_fight_sequence_from_brief(planning_brief)
    lines = ["# LATE-FIGHT COUNTDOWN"]
    phase_notes = _render_late_fight_phase_notes(planning_brief)
    if phase_notes:
        lines.extend(phase_notes)
    lines.extend(["", "## Countdown Sessions", ""])
    seen: set[tuple[str, str]] = set()
    for role in sequence:
        if _late_fight_role_is_hidden_context(role):
            continue
        if role.get("render_mandatory") is False:
            continue
        countdown_label = _late_fight_role_countdown_label(role)
        if not countdown_label or countdown_label == "D-0":
            continue
        identity = (countdown_label, str(role.get("role_key") or ""))
        if identity in seen:
            continue
        seen.add(identity)
        display_label = _late_fight_role_display_label(role, countdown_label)
        lines.extend(
            [
                f"### {display_label} - {_late_fight_role_display(role)}",
                f"Cue: {_late_fight_preferred_cue(role)}.",
                "Purpose: hold the assigned taper job, protect freshness, and stop if sharpness drops.",
                "",
            ]
        )

    lines.extend(
        [
            _late_fight_terminal_d0_header(context, planning_brief),
            FIGHT_DAY_PROTOCOL_TEXT,
        ]
    )
    return "\n".join(lines).strip()


def _resolve_fight_weekday(context: PlanRuntimeContext) -> str | None:
    """Prefer the actual fight_date over runtime-clock weekday arithmetic.

    The renderer must not derive the fight weekday from ``_utc_now()`` — that
    drifts every time the plan is re-rendered after the original creation day.
    ``plan_input.next_fight_date`` is the only stable input.
    """
    fight_date = getattr(context.plan_input, "next_fight_date", "") or ""
    if fight_date:
        weekday = resolve_fight_weekday(fight_date=fight_date)
        if weekday is not None:
            return weekday
    # Conservative fallback: only attempt offset arithmetic when days are known.
    # We deliberately do NOT call _utc_now(); without a stable plan-creation
    # weekday we return None rather than risk a drifted answer.
    return None


def _sparring_adjustment_lines(context: PlanRuntimeContext) -> list[str]:
    hard_days = [str(day).strip() for day in (context.plan_input.hard_sparring_days or []) if str(day).strip()]
    support_days = [str(day).strip() for day in (context.plan_input.support_work_days or []) if str(day).strip()]

    lines = ["### Sparring & Conditioning Adjustments", ""]
    if hard_days:
        lines.append(
            f"- **Expected hard sparring days:** {', '.join(hard_days)} -> Let these days own the main collision-heavy combat load and cut same-day or next-day S&C volume by about 30%."
        )
    else:
        lines.append("- **If hard sparring lands today** -> Keep S&C but cut volume by about 30% and trim accessories first.")

    if support_days:
        lines.append(
            f"- **S&C-compatible slots:** {', '.join(support_days)} -> Use these for cleaner aerobic support, recovery, primers, or lower-noise strength support."
        )
    if not hard_days:
        lines.append("- **If no sparring is fixed this week** -> Add one clear fight-pace conditioning exposure before extra lifting.")

    fight_weekday = _resolve_fight_weekday(context)
    if fight_weekday:
        lines.append(
            f"- **Fight day ({fight_weekday.title()}):** {FIGHT_DAY_PROTOCOL_TEXT} "
            "This overrides every weekday role, including any declared hard sparring day that lands on the fight date."
        )
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

    late_window = classify_late_selector_window(context.plan_input.days_until_fight)
    late_fight_active = is_active_late_selector_window(late_window)

    phase_num = 1
    fight_plan_lines = ["# LATE-FIGHT COUNTDOWN" if late_fight_active else "# FIGHT CAMP PLAN"]
    phase_models: dict[str, PhaseBlock] = {}

    if late_fight_active:
        fight_plan_lines += ["## Countdown Sessions", ""]

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

        if late_fight_active:
            for body in (mindset, strength, conditioning):
                if body:
                    fight_plan_lines += [body, ""]
            if blocks.has_injuries and guardrails:
                fight_plan_lines += [guardrails, ""]
        else:
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

    phase_breakdown_lines = (
        []
        if late_fight_active
        else [
            f"- Phase Weeks: {phase_week_summary}",
            f"- Phase Days: {phase_day_summary}",
        ]
    )
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
        *phase_breakdown_lines,
        f"- Fatigue Level: {context.plan_input.fatigue}",
        f"- Injuries: {context.injuries_display}",
        f"- Training Availability: {context.plan_input.available_days}",
        f"- Hard Sparring Days: {', '.join(context.plan_input.hard_sparring_days) if context.plan_input.hard_sparring_days else 'Not specified'}",
            f"- Support Work Days: {', '.join(context.plan_input.support_work_days) if context.plan_input.support_work_days else 'Not specified'}",
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
        *phase_breakdown_lines,
        f"- Fatigue Level: {context.plan_input.fatigue}",
        f"- Injuries: {context.injuries_display}",
        f"- Training Availability: {context.plan_input.available_days}",
        f"- Hard Sparring Days: {', '.join(context.plan_input.hard_sparring_days) if context.plan_input.hard_sparring_days else 'Not specified'}",
            f"- Support Work Days: {', '.join(context.plan_input.support_work_days) if context.plan_input.support_work_days else 'Not specified'}",
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


def build_stage2_outputs(
    *,
    context: PlanRuntimeContext,
    blocks: PlanBlocksBundle,
    rendered: RenderedPlanBundle,
) -> tuple[dict, dict, str]:
    stage1_selection_summary = {
        "strength_names": blocks.strength_names,
        "conditioning_names": blocks.conditioning_names,
        "strength_reason_log": blocks.strength_reason_log,
        "conditioning_reason_log": blocks.conditioning_reason_log,
        "current_phase": blocks.current_phase,
    }

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

    if isinstance(stage2_payload, dict):
        stage2_payload["stage1_selection_summary"] = stage1_selection_summary
    active_phases = [phase for phase in PHASES if context.phase_active(phase)]
    computed_support = build_computed_support(
        flags=context.training_context.to_flags(),
        phases=active_phases or None,
    )
    planning_brief = build_planning_brief(
        athlete_model=stage2_payload["athlete_model"],
        restrictions=stage2_payload["restrictions"],
        phase_briefs=stage2_payload["phase_briefs"],
        candidate_pools=stage2_payload["candidate_pools"],
        omission_ledger=stage2_payload["omission_ledger"],
        rewrite_guidance=stage2_payload["rewrite_guidance"],
        plan_input=context.plan_input,
        computed_support=computed_support,
    )

    if isinstance(planning_brief, dict):
        planning_brief["stage1_selection_summary"] = stage1_selection_summary
        late_fight_draft = _render_late_fight_stage1_draft(
            context=context,
            planning_brief=planning_brief,
        )
        if late_fight_draft:
            rendered.fight_plan_text = late_fight_draft
    # Deterministic injury / weight-cut lead summary. The validator scans the
    # first plan lines for this context, so render it right after the title.
    lead_summary = render_lead_summary(planning_brief)
    if lead_summary:
        rendered.fight_plan_text = _insert_lead_summary(
            rendered.fight_plan_text, lead_summary
        )
    stage2_handoff_text = build_stage2_handoff_text(
        stage2_payload=stage2_payload,
        plan_text=rendered.fight_plan_text,
        coach_notes=rendered.coach_notes,
        planning_brief=planning_brief,
    )
    return stage2_payload, planning_brief, stage2_handoff_text
