import asyncio
import json
import logging
import re
from pathlib import Path
from .build_block import (
    PhaseBlock,
    build_html_document,
    html_to_pdf,
    upload_to_supabase,
    _md_to_html,
)
from .bank_schema import validate_training_item
from .tagging import normalize_item_tags
from .tag_maps import GOAL_NORMALIZER, WEAKNESS_NORMALIZER

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Load exercise bank
exercise_bank = json.loads((DATA_DIR / "exercise_bank.json").read_text())
for item in exercise_bank:
    validate_training_item(item, source="exercise_bank.json", require_phases=True)
    normalize_item_tags(item)

# Modules
from .training_context import TrainingContext, allocate_sessions, normalize_equipment_list
from .camp_phases import calculate_phase_weeks
from .input_parsing import PlanInput
from .logging_utils import configure_logging
from .mindset_module import (
    classify_mental_block,
    get_phase_mindset_cues,
    get_mindset_by_phase,
)
from .strength import generate_strength_block
from .conditioning import (
    conditioning_bank,
    generate_conditioning_block,
    style_conditioning_bank,
)
from .coach_review import run_coach_review
from .recovery import generate_recovery_block
from .nutrition import generate_nutrition_block
from .rehab_protocols import (
    format_injury_guardrails,
    generate_rehab_protocols,
    generate_support_notes,
)


async def generate_plan(data: dict):
    configure_logging()
    logger = logging.getLogger(__name__)
    plan_input = PlanInput.from_payload(data)

    full_name = plan_input.full_name
    age = plan_input.age
    weight = plan_input.weight
    target_weight = plan_input.target_weight
    height = plan_input.height
    fighting_style_technical = plan_input.fighting_style_technical
    fighting_style_tactical = plan_input.fighting_style_tactical
    stance = plan_input.stance
    status = plan_input.status
    record = plan_input.record
    next_fight_date = plan_input.next_fight_date
    rounds_format = plan_input.rounds_format
    fatigue = plan_input.fatigue
    equipment_access = plan_input.equipment_access
    available_days = plan_input.available_days
    training_days = plan_input.training_days
    training_frequency = plan_input.training_frequency
    injuries = plan_input.injuries
    key_goals = plan_input.key_goals
    weak_areas = plan_input.weak_areas
    training_preference = plan_input.training_preference
    mental_block = plan_input.mental_block
    notes = plan_input.notes
    weeks_out = plan_input.weeks_out
    days_until_fight = plan_input.days_until_fight

    logger.info(
        "plan_input loaded",
        extra={"plan_id": f"{full_name or 'unknown'}-{next_fight_date or 'no-date'}"},
    )

    style_map = {
        "mma": "mma",
        "boxer": "boxing",
        "boxing": "boxing",
        "kickboxer": "kickboxing",
        "muay thai": "muay_thai",
        "bjj": "mma",
        "wrestler": "mma",
        "grappler": "mma",
        "karate": "kickboxing"
    }
    # First style in the list determines fight format
    tech_styles = plan_input.tech_styles
    primary_tech = tech_styles[0] if tech_styles else ""
    mapped_format = style_map.get(primary_tech, "mma")
    tactical_styles = plan_input.tactical_styles
    if stance.strip().lower() == "hybrid" and "hybrid" not in tactical_styles:
        tactical_styles.append("hybrid")

    weight_val = float(weight) if weight.replace('.', '', 1).isdigit() else 0.0
    target_val = float(target_weight) if target_weight.replace('.', '', 1).isdigit() else 0.0
    weight_cut_risk_flag = weight_val - target_val >= 0.05 * target_val if target_val else False
    weight_cut_pct_val = round((weight_val - target_val) / target_val * 100, 1) if target_val else 0.0
    mental_block_class = classify_mental_block(mental_block or "")

    camp_len = weeks_out if isinstance(weeks_out, int) else 8
    phase_weeks = calculate_phase_weeks(
        camp_len,
        mapped_format,
        tactical_styles,
        status,
        fatigue,
        weight_cut_risk_flag,
        mental_block_class,
        weight_cut_pct_val,
    )

    # Core context
    training_context = TrainingContext(
        fatigue=fatigue.lower(),
        training_frequency=training_frequency,
        days_available=len(training_days),
        training_days=training_days,
        injuries=[w.strip().lower() for w in injuries.split(",") if w.strip()] if injuries else [],
        style_technical=tech_styles,
        style_tactical=tactical_styles,
        weaknesses=[
            tag
            for item in [w.strip().lower() for w in weak_areas.split(",") if w.strip()]
            for tag in WEAKNESS_NORMALIZER.get(item.lower(), [item.lower()])
        ],
        equipment=normalize_equipment_list(equipment_access),
        weight_cut_risk=weight_cut_risk_flag,
        weight_cut_pct=weight_cut_pct_val,
        fight_format=mapped_format,
        status=status.strip().lower(),
        training_split=allocate_sessions(training_frequency),
        key_goals=[
            GOAL_NORMALIZER.get(g.strip(), g.strip()).lower()
            for g in key_goals.split(",")
            if g.strip()
        ],
        training_preference=training_preference.strip().lower() if training_preference else "",
        mental_block=mental_block_class,
        age=int(age) if age.isdigit() else 0,
        weight=float(weight) if weight.replace(".", "", 1).isdigit() else 0.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks=phase_weeks,
        days_until_fight=days_until_fight,
    )

    # Module generation
    phase_mindset_cues = get_phase_mindset_cues(training_context.mental_block)

    # === Strength blocks per phase with repeat filtering ===
    strength_blocks = []
    gpp_ex_names = []
    spp_ex_names = []
    taper_ex_names = []
    gpp_movements: set[str] = set()
    spp_movements: set[str] = set()
    gpp_block = None
    spp_block = None
    taper_block = None
    strength_reason_log: dict[str, list] = {}

    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        gpp_flags = {**training_context.to_flags(), "phase": "GPP"}
        gpp_block = generate_strength_block(
            flags=gpp_flags,
            weaknesses=training_context.weaknesses,
            mindset_cue=phase_mindset_cues.get("GPP"),
        )
        gpp_ex_names = [ex["name"] for ex in gpp_block["exercises"]]
        gpp_movements = {ex["movement"] for ex in gpp_block["exercises"]}
        strength_reason_log = {"GPP": gpp_block.get("why_log", [])}
        strength_blocks.append(gpp_block["block"])

    if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
        spp_flags = {
            **training_context.to_flags(),
            "phase": "SPP",
            "prev_exercises": gpp_ex_names,
            "recent_exercises": list(gpp_movements),
        }
        spp_block = generate_strength_block(
            flags=spp_flags,
            weaknesses=training_context.weaknesses,
            mindset_cue=phase_mindset_cues.get("SPP"),
        )
        spp_ex_names = [ex["name"] for ex in spp_block["exercises"]]
        spp_movements = {ex["movement"] for ex in spp_block["exercises"]}
        strength_blocks.append(spp_block["block"])
        strength_reason_log["SPP"] = spp_block.get("why_log", [])

    if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
        combined_prev = list({*gpp_ex_names, *spp_ex_names})
        combined_recent = list(gpp_movements | spp_movements)
        taper_flags = {
            **training_context.to_flags(),
            "phase": "TAPER",
            "prev_exercises": combined_prev,
            "recent_exercises": combined_recent,
        }
        taper_block = generate_strength_block(
            flags=taper_flags,
            weaknesses=training_context.weaknesses,
            mindset_cue=phase_mindset_cues.get("TAPER"),
        )
        taper_ex_names = [ex["name"] for ex in taper_block["exercises"]]
        strength_blocks.append(taper_block["block"])
        strength_reason_log["TAPER"] = taper_block.get("why_log", [])

    strength_block = "\n\n".join(strength_blocks)

    # Generate conditioning blocks per phase
    gpp_cond_block = ""
    spp_cond_block = ""
    taper_cond_block = ""

    conditioning_reason_log: dict[str, list] = {}
    gpp_cond_names: list[str] = []
    spp_cond_names: list[str] = []
    taper_cond_names: list[str] = []

    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        (
            gpp_cond_block,
            gpp_cond_names,
            gpp_cond_reasons,
            gpp_cond_grouped,
            gpp_cond_missing,
        ) = generate_conditioning_block({**training_context.to_flags(), "phase": "GPP"})
        conditioning_reason_log["GPP"] = gpp_cond_reasons

    if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
        (
            spp_cond_block,
            spp_cond_names,
            spp_cond_reasons,
            spp_cond_grouped,
            spp_cond_missing,
        ) = generate_conditioning_block({**training_context.to_flags(), "phase": "SPP"})
        conditioning_reason_log["SPP"] = spp_cond_reasons

    if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
        (
            taper_cond_block,
            taper_cond_names,
            taper_cond_reasons,
            taper_cond_grouped,
            taper_cond_missing,
        ) = generate_conditioning_block({**training_context.to_flags(), "phase": "TAPER"})
        conditioning_reason_log["TAPER"] = taper_cond_reasons

    gpp_rehab_block = ""
    spp_rehab_block = ""
    taper_rehab_block = ""
    seen_rehab_drills: set = set()
    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        gpp_rehab_block, seen_rehab_drills = generate_rehab_protocols(
            injury_string=injuries,
            exercise_data=exercise_bank,
            current_phase="GPP",
            seen_drills=seen_rehab_drills,
        )
        if gpp_rehab_block.strip().startswith("**Red Flag Detected**"):
            spp_rehab_block = gpp_rehab_block
            taper_rehab_block = gpp_rehab_block
    if not gpp_rehab_block.strip().startswith("**Red Flag Detected**"):
        if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
            spp_rehab_block, seen_rehab_drills = generate_rehab_protocols(
                injury_string=injuries,
                exercise_data=exercise_bank,
                current_phase="SPP",
                seen_drills=seen_rehab_drills,
            )
        if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
            taper_rehab_block, seen_rehab_drills = generate_rehab_protocols(
                injury_string=injuries,
                exercise_data=exercise_bank,
                current_phase="TAPER",
                seen_drills=seen_rehab_drills,
            )
    gpp_guardrails = format_injury_guardrails("GPP", injuries)
    spp_guardrails = format_injury_guardrails("SPP", injuries)
    taper_guardrails = format_injury_guardrails("TAPER", injuries)
    current_phase = next(
        (p for p in ["GPP", "SPP", "TAPER"] if phase_weeks[p] > 0 or phase_weeks["days"][p] >= 1),
        "GPP",
    )
    recovery_block = generate_recovery_block({**training_context.to_flags(), "phase": current_phase})
    nutrition_block = generate_nutrition_block(flags={**training_context.to_flags(), "phase": current_phase})

    phase_colors = {"GPP": "#4CAF50", "SPP": "#FF9800", "TAPER": "#F44336"}
    conditioning_blocks = {}
    if gpp_cond_block:
        conditioning_blocks["GPP"] = {
            "block": gpp_cond_block,
            "names": gpp_cond_names,
            "why_log": gpp_cond_reasons,
            "grouped_drills": gpp_cond_grouped,
            "missing_systems": gpp_cond_missing,
            "phase_color": phase_colors["GPP"],
        }
    if spp_cond_block:
        conditioning_blocks["SPP"] = {
            "block": spp_cond_block,
            "names": spp_cond_names,
            "why_log": spp_cond_reasons,
            "grouped_drills": spp_cond_grouped,
            "missing_systems": spp_cond_missing,
            "phase_color": phase_colors["SPP"],
        }
    if taper_cond_block:
        conditioning_blocks["TAPER"] = {
            "block": taper_cond_block,
            "names": taper_cond_names,
            "why_log": taper_cond_reasons,
            "grouped_drills": taper_cond_grouped,
            "missing_systems": taper_cond_missing,
            "phase_color": phase_colors["TAPER"],
        }

    coach_review_notes, strength_blocks, conditioning_blocks, substitutions = run_coach_review(
        injury_string=injuries,
        phase=current_phase,
        training_context=training_context.to_flags(),
        exercise_bank=exercise_bank,
        conditioning_banks=[conditioning_bank, style_conditioning_bank],
        strength_blocks={"GPP": gpp_block, "SPP": spp_block, "TAPER": taper_block},
        conditioning_blocks=conditioning_blocks,
    )

    gpp_block = strength_blocks.get("GPP")
    spp_block = strength_blocks.get("SPP")
    taper_block = strength_blocks.get("TAPER")
    if gpp_block:
        gpp_ex_names = [ex["name"] for ex in gpp_block["exercises"]]
    if spp_block:
        spp_ex_names = [ex["name"] for ex in spp_block["exercises"]]
    if taper_block:
        taper_ex_names = [ex["name"] for ex in taper_block["exercises"]]

    def _names_from_grouped(grouped: dict[str, list[dict]]) -> list[str]:
        return [
            d.get("name")
            for drills in grouped.values()
            for d in drills
            if d.get("name")
        ]

    if conditioning_blocks.get("GPP"):
        gpp_cond_block = conditioning_blocks["GPP"]["block"]
        gpp_cond_names = _names_from_grouped(conditioning_blocks["GPP"]["grouped_drills"])
    if conditioning_blocks.get("SPP"):
        spp_cond_block = conditioning_blocks["SPP"]["block"]
        spp_cond_names = _names_from_grouped(conditioning_blocks["SPP"]["grouped_drills"])
    if conditioning_blocks.get("TAPER"):
        taper_cond_block = conditioning_blocks["TAPER"]["block"]
        taper_cond_names = _names_from_grouped(conditioning_blocks["TAPER"]["grouped_drills"])

    def _apply_substitution_log(reason_log: dict[str, list], module: str) -> None:
        for sub in substitutions:
            if sub["module"] != module:
                continue
            phase_key = sub["phase"]
            logs = reason_log.get(phase_key, [])
            logs = [entry for entry in logs if entry.get("name") != sub["old"]]
            if sub.get("new"):
                logs.append(
                    {
                        "name": sub["new"],
                        "reasons": {},
                        "explanation": "coach safety substitution",
                    }
                )
            reason_log[phase_key] = logs

    _apply_substitution_log(strength_reason_log, "Strength")
    _apply_substitution_log(conditioning_reason_log, "Conditioning")


# Mental Block Strategy Injection Per Phase
    def build_mindset_prompt(phase_name: str):
        blocks = training_context.mental_block
        if isinstance(blocks, str):
            blocks = [blocks]

        if blocks[0].lower() != "generic":
            return get_mindset_by_phase(phase_name, training_context.to_flags())
        return get_mindset_by_phase(phase_name, {"mental_block": ["generic"]})

    gpp_mindset = build_mindset_prompt("GPP")
    spp_mindset = build_mindset_prompt("SPP")
    taper_mindset = build_mindset_prompt("TAPER")

    rehab_sections = ["## Rehab Protocols"]
    if gpp_rehab_block:
        rehab_sections += ["### GPP", gpp_rehab_block.strip(), ""]
    if spp_rehab_block:
        rehab_sections += ["### SPP", spp_rehab_block.strip(), ""]
    if taper_rehab_block:
        rehab_sections += ["### TAPER", taper_rehab_block.strip(), ""]
    support_notes = generate_support_notes(injuries)
    if support_notes:
        rehab_sections += ["", support_notes]

    def _week_str(weeks: int, days: int) -> str:
        """Return a display string for weeks, avoiding zero for short phases."""
        return "~1" if weeks == 0 and days > 0 else str(weeks)

    week_str = {
        phase: _week_str(phase_weeks[phase], phase_weeks["days"][phase])
        for phase in ("GPP", "SPP", "TAPER")
    }

    fight_plan_lines = ["# FIGHT CAMP PLAN"]
    phase_num = 1

    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        fight_plan_lines += [
            f"## PHASE {phase_num}: GENERAL PREPARATION PHASE (GPP) – {week_str['GPP']} WEEKS ({phase_weeks['days']['GPP']} DAYS)",
            "",
            "### Mindset Focus",
            gpp_mindset,
            "",
            "### Strength & Power",
            gpp_block["block"] if gpp_block else "",
            "",
            "### Conditioning",
            gpp_cond_block,
            "",
            "### Injury Guardrails",
            "Phase: GPP",
            gpp_guardrails,
            "",
        ]
        phase_num += 1

    if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
        fight_plan_lines += [
            f"## PHASE {phase_num}: SPECIFIC PREPARATION PHASE (SPP) – {week_str['SPP']} WEEKS ({phase_weeks['days']['SPP']} DAYS)",
            "",
            "### Mindset Focus",
            spp_mindset,
            "",
            "### Strength & Power",
            spp_block["block"] if spp_block else "",
            "",
            "### Conditioning",
            spp_cond_block,
            "",
            "### Injury Guardrails",
            "Phase: SPP",
            spp_guardrails,
            "",
        ]
        phase_num += 1

    if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
        fight_plan_lines += [
            f"## PHASE {phase_num}: TAPER – {week_str['TAPER']} WEEKS ({phase_weeks['days']['TAPER']} DAYS)",
            "",
            "### Mindset Focus",
            taper_mindset,
            "",
            "### Strength & Power",
            taper_block["block"] if taper_block else "",
            "",
            "### Conditioning",
            taper_cond_block,
            "",
            "### Injury Guardrails",
            "Phase: TAPER",
            taper_guardrails,
            "",
        ]

    fight_plan_lines += [
        "## Nutrition",
        nutrition_block,
        "",
        "## Recovery",
        recovery_block,
        "",
    ] + rehab_sections + [
        "",
        "## Mindset Overview",
        f"Primary Block(s): {', '.join(training_context.mental_block).title()}",
        "",
        "### Sparring & Conditioning Adjustments",
        "",
        "- **If technical sparring is today** \u2192 Keep S&C but **cut volume by 30%**",
        "- **If no sparring this week** \u2192 Add an **extra glycolytic conditioning session** (e.g., 5x3min bag rounds)",
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
        f"- **Name:** <b>{full_name}</b><br>",
        f"- Age: {age}",
        f"- Weight: {weight}kg",
        f"- Target Weight: {target_weight}kg",
        f"- Height: {height}cm",
        f"- Technical Style: {fighting_style_technical}",
        f"- Tactical Style: {fighting_style_tactical}",
        f"- Stance: {stance}",
        f"- Status: {status}",
        f"- Record: {record}",
        f"- Fight Format: {rounds_format}",
        f"- Fight Date: {next_fight_date}",
        f"- Weeks Out: {weeks_out}",
        f"- Phase Weeks: {week_str['GPP']} GPP / {week_str['SPP']} SPP / {week_str['TAPER']} Taper",
        f"- Phase Days: {phase_weeks['days']['GPP']} GPP / {phase_weeks['days']['SPP']} SPP / {phase_weeks['days']['TAPER']} Taper",
        f"- Fatigue Level: {fatigue}",
        f"- Injuries: {injuries}",
        f"- Training Availability: {available_days}",
        f"- Weaknesses: {weak_areas}",
        f"- Key Goals: {key_goals}",
        f"- Mindset Challenges: {', '.join(training_context.mental_block)}",
        f"- Notes: {notes}",
    ]
     
    phase_split = f"{week_str['GPP']} / {week_str['SPP']} / {week_str['TAPER']}"

    def build_phase(name, weeks, days, mindset, strength, cond, guardrails):
        return PhaseBlock(
            name=name,
            weeks=weeks,
            days=days,
            mindset=mindset,
            strength=strength,
            conditioning=cond,
            guardrails=guardrails,
        )

    gpp_phase = None
    spp_phase = None
    taper_phase = None
    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        gpp_phase = build_phase(
            f"PHASE 1: GENERAL PREPARATION PHASE (GPP) – {week_str['GPP']} WEEKS ({phase_weeks['days']['GPP']} DAYS)",
            phase_weeks["GPP"],
            phase_weeks["days"]["GPP"],
            gpp_mindset,
            gpp_block["block"] if gpp_block else "",
            gpp_cond_block,
            gpp_guardrails,
        )
    if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
        spp_phase = build_phase(
            f"PHASE 2: SPECIFIC PREPARATION PHASE (SPP) – {week_str['SPP']} WEEKS ({phase_weeks['days']['SPP']} DAYS)",
            phase_weeks["SPP"],
            phase_weeks["days"]["SPP"],
            spp_mindset,
            spp_block["block"] if spp_block else "",
            spp_cond_block,
            spp_guardrails,
        )
    if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
        taper_phase = build_phase(
            f"PHASE 3: TAPER – {week_str['TAPER']} WEEKS ({phase_weeks['days']['TAPER']} DAYS)",
            phase_weeks["TAPER"],
            phase_weeks["days"]["TAPER"],
            taper_mindset,
            taper_block["block"] if taper_block else "",
            taper_cond_block,
            taper_guardrails,
        )

    rehab_parts = []
    if gpp_rehab_block:
        rehab_parts.append("<h3>GPP</h3>")
        rehab_parts.append(_md_to_html(gpp_rehab_block.strip()))
    if spp_rehab_block:
        rehab_parts.append("<h3>SPP</h3>")
        rehab_parts.append(_md_to_html(spp_rehab_block.strip()))
    if taper_rehab_block:
        rehab_parts.append("<h3>TAPER</h3>")
        rehab_parts.append(_md_to_html(taper_rehab_block.strip()))
    if support_notes:
        rehab_parts.append(_md_to_html(support_notes))
    rehab_html = "\n".join(rehab_parts)

    profile_lines = [
        f"- **Name:** <b>{full_name}</b><br>",
        f"- Age: {age}",
        f"- Weight: {weight}kg",
        f"- Target Weight: {target_weight}kg",
        f"- Height: {height}cm",
        f"- Technical Style: {fighting_style_technical}",
        f"- Tactical Style: {fighting_style_tactical}",
        f"- Stance: {stance}",
        f"- Status: {status}",
        f"- Record: {record}",
        f"- Fight Format: {rounds_format}",
        f"- Fight Date: {next_fight_date}",
        f"- Weeks Out: {weeks_out}",
        f"- Phase Weeks: {week_str['GPP']} GPP / {week_str['SPP']} SPP / {week_str['TAPER']} Taper",
        f"- Phase Days: {phase_weeks['days']['GPP']} GPP / {phase_weeks['days']['SPP']} SPP / {phase_weeks['days']['TAPER']} Taper",
        f"- Fatigue Level: {fatigue}",
        f"- Injuries: {injuries}",
        f"- Training Availability: {available_days}",
        f"- Weaknesses: {weak_areas}",
        f"- Key Goals: {key_goals}",
        f"- Mindset Challenges: {', '.join(training_context.mental_block)}",
        f"- Notes: {notes}",
    ]
    athlete_profile_html = _md_to_html("\n".join(profile_lines))

    adjustments_table = _md_to_html("- If sparring today: reduce S&C by 30%\n- No sparring this week: add extra glycolytic conditioning")

    sparring_nutrition_html = _md_to_html(
        "- **On Expected Hard Sparring Days:**\n"
        "  - Increase intra-workout carbs (e.g., 30g HBCD during session).\n"
        "  - Post-session: 1.2g/kg carbs + 0.4g/kg protein within 30 mins.\n"
        "- **If Sparring Was Unexpectedly Hard:**\n"
        "  - Add 500mg sodium + 20oz electrolyte drink immediately."
    )

    # ----- Coach Notes & Why Log -----
    previous = set(training_context.prev_exercises)
    all_strength_names = gpp_ex_names + spp_ex_names + (taper_ex_names if taper_block else [])
    all_cond_names = gpp_cond_names + spp_cond_names + taper_cond_names
    novel_strength = [n for n in all_strength_names if n not in previous]
    novel_conditioning = [n for n in all_cond_names if n not in previous]
    coach_notes = (
        f"Novelty Summary: {len(novel_strength)} new strength moves, {len(novel_conditioning)} new conditioning drills."
    )
    if coach_review_notes:
        coach_notes = f"{coach_notes}\n\n{coach_review_notes}"
    reason_log = {
        "strength": strength_reason_log,
        "conditioning": conditioning_reason_log,
    }

    def _format_rationale_section(title: str, phases: dict[str, list]) -> list[str]:
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

    selection_rationale_lines = [
        "## Selection Rationale",
        "",
        *_format_rationale_section("Strength Selection", strength_reason_log),
        "",
        *_format_rationale_section("Conditioning Selection", conditioning_reason_log),
        "",
    ]
    selection_rationale_md = "\n".join(selection_rationale_lines)
    fight_plan_lines += selection_rationale_lines
    fight_plan_text = "\n".join(fight_plan_lines)
    fight_plan_text = re.sub(r"\n{3,}", "\n\n", fight_plan_text)

    logger.info("plan generated locally (first 500 chars): %s", fight_plan_text[:500])

    html = build_html_document(
        full_name=full_name,
        sport=mapped_format,
        phase_split=phase_split,
        status=status,
        record=record,
        gpp=gpp_phase,
        spp=spp_phase,
        taper=taper_phase,
        nutrition_block=nutrition_block,
        recovery_block=recovery_block,
        rehab_html=rehab_html,
        mindset_overview=f"Primary Block(s): {', '.join(training_context.mental_block).title()}",
        adjustments_table=adjustments_table,
        sparring_nutrition_html=sparring_nutrition_html,
        athlete_profile_html=athlete_profile_html,
        coach_notes=coach_notes,
        selection_rationale_html=_md_to_html(selection_rationale_md),
    )

    safe = full_name.replace(" ", "_") or "plan"
    pdf_path = html_to_pdf(html, f"{safe}_fight_plan.pdf")
    pdf_url = upload_to_supabase(pdf_path) if pdf_path else "PDF generation failed"

    return {"pdf_url": pdf_url, "why_log": reason_log, "coach_notes": coach_notes}


def main():
    data_file = Path("test_data.json").resolve()
    if not data_file.exists():
        raise FileNotFoundError(f"Test data file not found: {data_file}")
    with open(data_file, "r") as f:
        data = json.load(f)
    result = asyncio.run(generate_plan(data))
    print(f"::notice title=Plan PDF::{result.get('pdf_url')}")


if __name__ == "__main__":
    main()
