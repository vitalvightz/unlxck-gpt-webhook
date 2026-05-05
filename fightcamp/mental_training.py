"""Stage 2 mental-training integrator.

Stage 1 produces a raw mental profile (mental_block classifications, athlete
flags, fatigue, fight format, weaknesses, goals). This module reads that
profile alongside Stage 2 phase briefs and the weekly role map, then produces
a phase-aware, athlete-specific mental-training plan that Stage 2 can attach
directly to the final weekly schedule.

The output is intentionally small and coach-friendly:
- one phase-level brief per active phase (objective, primary blocks, dose,
  attached session roles, drills, coach voice line)
- per-week per-session attachment hints so the LLM finalizer knows which
  existing session carries which mental cue (sparring → composure / breath,
  recovery → confidence / visualization, strength → attention, rehab →
  injury-fear graded exposure, etc.)

Mental work is NOT scheduled as a standalone session. It is layered onto the
existing strength / conditioning / sparring / recovery / rehab work the rest
of Stage 2 already produced.
"""
from __future__ import annotations

from typing import Any, Iterable

from .normalization import clean_list, dedupe_preserve_order


# Ordered priority — when an athlete has multiple blocks we keep the two most
# acute and pick attachments / drills against them in priority order.
_BLOCK_PRIORITY = (
    "pressure",
    "rushing",
    "composure",
    "breath control",
    "gas tank",
    "injury fear",
    "fear of takedowns",
    "confidence",
    "attention",
    "motivation",
    "generic",
)


# Which session role keys most naturally carry each block. Ordered by best fit
# first; the resolver keeps the best matches it can find in the actual weekly
# role map.
_BLOCK_SESSION_AFFINITY: dict[str, tuple[str, ...]] = {
    "pressure": (
        "hard_sparring_day",
        "sparring_day",
        "fight_pace_day",
        "alactic_sharpness_day",
        "glycolytic_repeatability_day",
        "primary_strength_day",
        "neural_primer_day",
    ),
    "rushing": (
        "hard_sparring_day",
        "sparring_day",
        "fight_pace_day",
        "alactic_sharpness_day",
        "technical_touch_day",
    ),
    "composure": (
        "hard_sparring_day",
        "sparring_day",
        "fight_pace_day",
        "fight_week_freshness_day",
        "primary_strength_day",
    ),
    "breath control": (
        "aerobic_repeatability_day",
        "glycolytic_repeatability_day",
        "fight_pace_day",
        "recovery_day",
        "primary_strength_day",
    ),
    "gas tank": (
        "glycolytic_repeatability_day",
        "aerobic_repeatability_day",
        "fight_pace_day",
        "primary_strength_day",
    ),
    "injury fear": (
        "rehab_day",
        "primary_strength_day",
        "recovery_day",
        "structural_strength_day",
    ),
    "fear of takedowns": (
        "hard_sparring_day",
        "sparring_day",
        "technical_touch_day",
    ),
    "confidence": (
        "fight_week_freshness_day",
        "recovery_day",
        "primary_strength_day",
        "neural_primer_day",
    ),
    "attention": (
        "primary_strength_day",
        "neural_primer_day",
        "alactic_sharpness_day",
        "technical_touch_day",
        "structural_strength_day",
    ),
    "motivation": (
        "recovery_day",
        "primary_strength_day",
        "aerobic_repeatability_day",
    ),
    "generic": (
        "primary_strength_day",
        "recovery_day",
    ),
}


# Plain coach-readable category an athlete sees, derived from category +
# preferred_system + role_key. Mental cues attach to these.
_FALLBACK_AFFINITY_BY_CATEGORY = {
    "strength": ("primary_strength_day", "structural_strength_day"),
    "conditioning": ("aerobic_repeatability_day", "glycolytic_repeatability_day", "alactic_sharpness_day"),
    "recovery": ("recovery_day",),
    "rehab": ("rehab_day",),
    "sparring": ("hard_sparring_day", "sparring_day"),
}


# Phase-level dose rules. Mental work does not become a session — it stays a
# small, integrated layer.
_PHASE_DOSE = {
    "GPP": {
        "load_bias": "build the habit",
        "weekly_pattern": "Daily breath/cue habit + one short standalone block (5-10 min) inside an easier session.",
        "per_session_minutes": "3-5 min layered into warm-up or cooldown.",
        "objective_template": "Build the mental skill base before fight stress climbs.",
    },
    "SPP": {
        "load_bias": "rehearse under stress",
        "weekly_pattern": "Attach to sparring and fight-pace days; one short visualization block on a recovery day.",
        "per_session_minutes": "3-5 min around hard sport work.",
        "objective_template": "Rehearse the mindset under fight-specific stress so it transfers.",
    },
    "TAPER": {
        "load_bias": "minimal sharp dose",
        "weekly_pattern": "Pre-session reset rituals only. No new drills. Rehearse calm openings.",
        "per_session_minutes": "1-3 min reset rehearsal only.",
        "objective_template": "Protect freshness and rehearse the calm version of fight night.",
    },
}


# Drill bank — each entry is intentionally small and attached to a session
# context so the LLM can render it in plain coach language.
_DRILL_BANK: dict[str, dict[str, list[dict[str, str]]]] = {
    "pressure": {
        "GPP": [
            {
                "name": "Pressure-as-prep journal",
                "dose": "1 line, daily",
                "attach": "warm-up",
                "purpose": "Reframe pressure as evidence of preparation, not threat.",
            },
            {
                "name": "Reset-and-engage drill",
                "dose": "3 rounds × 2 min",
                "attach": "shadow / pad day",
                "purpose": "Practise breathing out before re-engaging when intensity spikes.",
            },
        ],
        "SPP": [
            {
                "name": "Pre-round reset routine",
                "dose": "30 s before each round",
                "attach": "hard sparring day",
                "purpose": "Pair calm breathing with one technical cue so pressure does not steer choices.",
            },
            {
                "name": "Round-end recall",
                "dose": "20 s after each round",
                "attach": "fight-pace day",
                "purpose": "Note one composed action; reinforce the pattern under fatigue.",
            },
        ],
        "TAPER": [
            {
                "name": "Opening-exchange visualization",
                "dose": "2 min, once per session",
                "attach": "recovery / freshness day",
                "purpose": "Rehearse a calm, confident opening so fight night feels familiar.",
            },
        ],
    },
    "rushing": {
        "GPP": [
            {
                "name": "Reset-to-stance habit",
                "dose": "every combination in shadow",
                "attach": "warm-up / technical touch",
                "purpose": "Build the body cue: every combo finishes with stance + exhale, not chase.",
            },
        ],
        "SPP": [
            {
                "name": "After clean shot, breathe-reset",
                "dose": "3 rounds × 2 min",
                "attach": "hard sparring day",
                "purpose": "Practise resetting after success instead of chasing a finish.",
            },
            {
                "name": "Pace anchor cue",
                "dose": "1 cue per round",
                "attach": "fight-pace conditioning",
                "purpose": "Pick one pace word; use it when the urge to speed up rises.",
            },
        ],
        "TAPER": [
            {
                "name": "Calm-rep visualization",
                "dose": "2 min, once per session",
                "attach": "recovery day",
                "purpose": "Rehearse taking the clean shot then resetting, not chasing.",
            },
        ],
    },
    "composure": {
        "GPP": [
            {
                "name": "Reset ritual",
                "dose": "before every round",
                "attach": "any sparring day",
                "purpose": "Shoulders down, jaw loose, exhale. Make composure a body cue, not a feeling.",
            },
        ],
        "SPP": [
            {
                "name": "Post-exchange check-in",
                "dose": "between exchanges",
                "attach": "hard sparring day",
                "purpose": "Quick scan: jaw, shoulders, breath. Re-set before re-engaging.",
            },
        ],
        "TAPER": [
            {
                "name": "Pre-round reset rehearsal",
                "dose": "30 s, pre-session",
                "attach": "freshness / technical touch",
                "purpose": "Rehearse the calm opening; this is the version we want on fight night.",
            },
        ],
    },
    "breath control": {
        "GPP": [
            {
                "name": "Nasal warm-up",
                "dose": "5 min",
                "attach": "warm-up",
                "purpose": "Establish a nasal-breathing baseline before output rises.",
            },
            {
                "name": "Exhale-on-output cue",
                "dose": "every set",
                "attach": "primary strength day",
                "purpose": "Tie a hard exhale to power output; carry the pattern into striking.",
            },
        ],
        "SPP": [
            {
                "name": "Round-rhythm breathing",
                "dose": "every round",
                "attach": "fight-pace conditioning / sparring",
                "purpose": "Exhale on strikes, nasal recovery between exchanges.",
            },
        ],
        "TAPER": [
            {
                "name": "Calm exhale reset",
                "dose": "before each session",
                "attach": "any session",
                "purpose": "Keep the breath smooth and quiet; do not introduce new drills here.",
            },
        ],
    },
    "gas tank": {
        "GPP": [
            {
                "name": "Recovery-time log",
                "dose": "post-session",
                "attach": "aerobic / glycolytic conditioning",
                "purpose": "Track HR drop or breath recovery to make progress visible.",
            },
        ],
        "SPP": [
            {
                "name": "Round-rhythm breathing",
                "dose": "every round",
                "attach": "glycolytic / fight-pace day",
                "purpose": "Lock the breathing pattern that lets the gas tank survive sport pace.",
            },
        ],
        "TAPER": [
            {
                "name": "Trust-the-base cue",
                "dose": "1 line pre-session",
                "attach": "recovery / freshness day",
                "purpose": "Reinforce that the conditioning is already done; do not chase fitness.",
            },
        ],
    },
    "injury fear": {
        "GPP": [
            {
                "name": "Graded exposure log",
                "dose": "1 line post-session",
                "attach": "rehab / strength day",
                "purpose": "Note one pain-free quality rep; build the body of evidence.",
            },
        ],
        "SPP": [
            {
                "name": "Trust-cue under load",
                "dose": "before main lift",
                "attach": "primary strength day",
                "purpose": "Tie one cue to a clean rep so confidence and tissue load build together.",
            },
        ],
        "TAPER": [
            {
                "name": "Clean-movement recall",
                "dose": "1 min, pre-session",
                "attach": "recovery / freshness day",
                "purpose": "Rehearse the body moving cleanly; protect trust into fight week.",
            },
        ],
    },
    "fear of takedowns": {
        "GPP": [
            {
                "name": "Calm level-change reps",
                "dose": "5 min",
                "attach": "technical / warm-up",
                "purpose": "Stay relaxed on level changes; reset stance after each rep.",
            },
        ],
        "SPP": [
            {
                "name": "Sprawl-and-reset routine",
                "dose": "3 × 1 min",
                "attach": "sparring day",
                "purpose": "Pair calm defensive entries with stance resets — kill the panic loop.",
            },
        ],
        "TAPER": [
            {
                "name": "Clean defense visualization",
                "dose": "2 min, pre-session",
                "attach": "freshness / technical touch",
                "purpose": "Rehearse smooth defensive triggers; do not introduce new live drills.",
            },
        ],
    },
    "confidence": {
        "GPP": [
            {
                "name": "Daily win note",
                "dose": "1 line, daily",
                "attach": "warm-up",
                "purpose": "Build small evidence of progress before big claims.",
            },
        ],
        "SPP": [
            {
                "name": "Best-round recap",
                "dose": "1 min, post-session",
                "attach": "primary strength / sparring day",
                "purpose": "End the session by naming what worked; tie work to belief.",
            },
        ],
        "TAPER": [
            {
                "name": "Highlight visualization",
                "dose": "5 min",
                "attach": "freshness / recovery day",
                "purpose": "Replay best moments; rehearse the opening exchange calmly.",
            },
        ],
    },
    "attention": {
        "GPP": [
            {
                "name": "One-cue lock-in",
                "dose": "before each set",
                "attach": "primary strength day",
                "purpose": "Pick one technical cue per set; train attention as a skill.",
            },
        ],
        "SPP": [
            {
                "name": "One-cue per round",
                "dose": "before each round",
                "attach": "alactic / sparring day",
                "purpose": "Limit cues to one per round so attention does not fragment under load.",
            },
        ],
        "TAPER": [
            {
                "name": "Quiet-mind breath",
                "dose": "30 s, pre-session",
                "attach": "any session",
                "purpose": "Short exhale focus; arrive present, not flooded.",
            },
        ],
    },
    "motivation": {
        "GPP": [
            {
                "name": "Why-line",
                "dose": "1 line pre-session",
                "attach": "warm-up",
                "purpose": "Anchor today's work to the bigger reason; reduce drift.",
            },
        ],
        "SPP": [
            {
                "name": "Outcome-to-today link",
                "dose": "1 line, pre-session",
                "attach": "primary session",
                "purpose": "Connect today's session to a clear fight-specific outcome.",
            },
        ],
        "TAPER": [
            {
                "name": "Readiness recall",
                "dose": "1 line, pre-session",
                "attach": "recovery / freshness day",
                "purpose": "Reinforce readiness; this is execution week, not motivation week.",
            },
        ],
    },
    "generic": {
        "GPP": [
            {
                "name": "Daily intention",
                "dose": "1 line pre-session",
                "attach": "warm-up",
                "purpose": "One simple intention; review one win post-session.",
            },
        ],
        "SPP": [
            {
                "name": "Cue-of-the-day",
                "dose": "1 line pre-session",
                "attach": "primary session",
                "purpose": "One cue, one outcome to track. Keep it simple under stress.",
            },
        ],
        "TAPER": [
            {
                "name": "Calm-and-ready cue",
                "dose": "1 line pre-session",
                "attach": "recovery / freshness day",
                "purpose": "Stay calm, stay simple. Trust the work done.",
            },
        ],
    },
}


def _normalize_blocks(raw: Iterable[str] | str | None) -> list[str]:
    if not raw:
        return ["generic"]
    if isinstance(raw, str):
        raw = [raw]
    cleaned: list[str] = []
    for value in raw:
        token = str(value or "").strip().lower()
        if token:
            cleaned.append(token)
    if not cleaned:
        return ["generic"]
    ordered = sorted(
        dedupe_preserve_order(cleaned),
        key=lambda block: _BLOCK_PRIORITY.index(block) if block in _BLOCK_PRIORITY else len(_BLOCK_PRIORITY),
    )
    return ordered[:2] or ["generic"]


def _block_purpose_for_athlete(block: str, athlete_model: dict) -> str:
    """Return one short coach-friendly sentence on why this block matters now."""
    fatigue = str(athlete_model.get("fatigue") or "").strip().lower()
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
    weight_cut_active = bool(athlete_model.get("weight_cut_risk")) or "active_weight_cut" in readiness_flags

    base = {
        "pressure": "Pressure shows up as performance anxiety; train it like a skill before fight week.",
        "rushing": "When intensity climbs the athlete chases instead of resetting; coach the reset.",
        "composure": "Composure breaks under stress; build it as a body cue, not willpower.",
        "breath control": "Breath collapses first under sport load; lock the pattern early.",
        "gas tank": "Gas-tank confidence is part conditioning, part mindset; coach both.",
        "injury fear": "Injury fear narrows movement quality; rebuild trust through graded exposure.",
        "fear of takedowns": "Defensive panic costs offense; coach calm level-change reps.",
        "confidence": "Confidence is built from evidence; collect small wins.",
        "attention": "Attention drifts under fatigue; one cue per round is enough.",
        "motivation": "Motivation dips mid-camp; anchor it to a clear why and routine.",
        "generic": "Keep mental work simple, intentional, and tied to today's training.",
    }
    line = base.get(block, base["generic"])
    if weight_cut_active and block in {"composure", "rushing", "pressure"}:
        line += " Cut stress sharpens this — keep the dose small and protective."
    if fatigue == "high" and block in {"motivation", "attention"}:
        line += " High fatigue makes this fragile; integrate, do not stack."
    return line


def _is_pure_striker(athlete_model: dict) -> bool:
    grappling = {"mma", "bjj", "wrestler", "wrestling", "grappler", "grappling", "judo", "sambo"}
    styles = {
        str(value).strip().lower()
        for value in clean_list(athlete_model.get("technical_styles", []))
        + clean_list(athlete_model.get("tactical_styles", []))
    }
    return not bool(styles & grappling)


def _filter_blocks_for_style(blocks: list[str], athlete_model: dict) -> list[str]:
    if _is_pure_striker(athlete_model):
        filtered = [block for block in blocks if block != "fear of takedowns"]
        return filtered or ["generic"]
    return blocks


def _phase_attachment_keys(blocks: list[str]) -> list[str]:
    keys: list[str] = []
    for block in blocks:
        keys.extend(_BLOCK_SESSION_AFFINITY.get(block, ()))
    return dedupe_preserve_order(keys)


def _drills_for_block(block: str, phase: str) -> list[dict]:
    drills = _DRILL_BANK.get(block, _DRILL_BANK["generic"]).get(phase)
    if drills:
        return [dict(item) for item in drills]
    fallback = _DRILL_BANK["generic"].get(phase, [])
    return [dict(item) for item in fallback]


def _phase_brief_for_blocks(
    *,
    phase: str,
    blocks: list[str],
    athlete_model: dict,
    phase_brief: dict,
) -> dict:
    dose = _PHASE_DOSE.get(phase, _PHASE_DOSE["GPP"])

    primary_block = blocks[0] if blocks else "generic"
    objective = (
        f"{dose['objective_template']} Lead with {primary_block.title()} for this athlete."
    )

    block_briefs: list[dict] = []
    for block in blocks:
        block_briefs.append(
            {
                "block": block,
                "purpose": _block_purpose_for_athlete(block, athlete_model),
                "preferred_session_roles": list(_BLOCK_SESSION_AFFINITY.get(block, ())),
                "drills": _drills_for_block(block, phase),
            }
        )

    coach_voice = _coach_voice_line(phase=phase, blocks=blocks, athlete_model=athlete_model)

    return {
        "phase": phase,
        "objective": objective,
        "primary_blocks": list(blocks),
        "load_bias": dose["load_bias"],
        "weekly_pattern": dose["weekly_pattern"],
        "per_session_minutes": dose["per_session_minutes"],
        "preferred_session_roles": _phase_attachment_keys(blocks),
        "block_briefs": block_briefs,
        "integration_rules": _phase_integration_rules(phase=phase, athlete_model=athlete_model),
        "coach_voice": coach_voice,
        "do_not": _phase_donts(phase=phase, athlete_model=athlete_model),
        "ties_to_phase_objective": str(phase_brief.get("objective") or ""),
    }


def _coach_voice_line(*, phase: str, blocks: list[str], athlete_model: dict) -> str:
    primary = blocks[0] if blocks else "generic"
    fatigue = str(athlete_model.get("fatigue") or "").strip().lower()
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
    cut_active = bool(athlete_model.get("weight_cut_risk")) or "active_weight_cut" in readiness_flags

    if phase == "TAPER":
        line = f"Mental work this week is small and rehearsed: {primary} reset cues only — no new drills."
    elif phase == "SPP":
        line = f"Pin {primary} work to the hardest sport day so it transfers under real stress."
    else:
        line = f"Build the {primary} habit early; keep it short and integrated, not a separate session."

    if cut_active:
        line += " Keep the dose protective — cut stress is already pulling on attention."
    if fatigue == "high" and phase != "TAPER":
        line += " Layer it onto easier sessions; do not stack on hard days when fatigue is already high."
    return line


def _phase_integration_rules(*, phase: str, athlete_model: dict) -> list[str]:
    rules = [
        "Attach mental cues to existing sessions; never schedule mental work as a standalone session.",
        "Keep the language simple and coach-friendly; avoid generic motivation.",
        "State the purpose, not the slogan.",
    ]
    if phase == "GPP":
        rules.append("Use warm-ups and cooldowns to install habits before fight stress climbs.")
    elif phase == "SPP":
        rules.append("Pair the primary block with the week's hardest sport day so it rehearses under pressure.")
    elif phase == "TAPER":
        rules.append("Reset rituals only — do not introduce new drills, do not chase mindset gains.")

    if bool(athlete_model.get("weight_cut_risk")):
        rules.append("Active weight cut: keep mental cues short, calm, and protective; do not add cognitive load.")
    if str(athlete_model.get("fatigue") or "").lower() == "high":
        rules.append("High fatigue: integrate cues into easier sessions; remove anything that adds mental load on hard days.")
    return dedupe_preserve_order(rules)


def _phase_donts(*, phase: str, athlete_model: dict) -> list[str]:
    base = [
        "Do not write generic motivation ('stay consistent', 'trust the process', 'you got this').",
        "Do not add a Mindset section that floats free of the week's actual sessions.",
        "Do not stack new mental drills on hard sparring or peak conditioning days.",
    ]
    if phase == "TAPER":
        base.append("Do not introduce new mental drills in taper; only rehearse the calm version of what is already known.")
    if bool(athlete_model.get("weight_cut_risk")):
        base.append("Do not pile on visualization or journaling load while the athlete is mid-cut.")
    return base


def _resolve_session_attachment(
    role: dict,
    *,
    blocks: list[str],
    weekly_attachment_rules: dict[str, str],
) -> dict | None:
    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()
    preferred_system = str(role.get("preferred_system") or "").strip().lower()

    candidate_keys: list[str] = []
    if role_key:
        candidate_keys.append(role_key)
    if preferred_system and category == "conditioning":
        candidate_keys.append(f"{preferred_system}_repeatability_day")
        candidate_keys.append(f"{preferred_system}_day")
    if category == "strength":
        candidate_keys.extend(_FALLBACK_AFFINITY_BY_CATEGORY["strength"])
    if category == "conditioning":
        candidate_keys.extend(_FALLBACK_AFFINITY_BY_CATEGORY["conditioning"])
    if category == "recovery":
        candidate_keys.extend(_FALLBACK_AFFINITY_BY_CATEGORY["recovery"])
    if category == "rehab":
        candidate_keys.extend(_FALLBACK_AFFINITY_BY_CATEGORY["rehab"])
    if "spar" in role_key:
        candidate_keys.extend(_FALLBACK_AFFINITY_BY_CATEGORY["sparring"])

    chosen_block: str | None = None
    chosen_key: str | None = None
    for block in blocks:
        affinity = _BLOCK_SESSION_AFFINITY.get(block, ())
        for key in candidate_keys:
            if key in affinity:
                chosen_block = block
                chosen_key = key
                break
        if chosen_block:
            break

    if not chosen_block:
        return None

    cue = weekly_attachment_rules.get(chosen_block) or _DEFAULT_CUE_BY_BLOCK.get(chosen_block, "")
    return {
        "block": chosen_block,
        "matched_role_key": chosen_key,
        "cue": cue,
        "attachment_kind": _attachment_kind_for_category(category),
        "purpose": _BLOCK_AFFINITY_PURPOSE.get(chosen_block, "Layer mental cue onto this session."),
    }


_DEFAULT_CUE_BY_BLOCK = {
    "pressure": "Pre-round reset (30 s breath + one cue) before hard work; recall one composed action after.",
    "rushing": "After every clean exchange, deliberately reset to stance and breathe out before re-engaging.",
    "composure": "Pre-round reset ritual: shoulders down, jaw loose, exhale. Repeat between rounds.",
    "breath control": "Lock round-rhythm breathing — exhale on output, nasal recovery between exchanges.",
    "gas tank": "Track recovery time between rounds; trust the base, do not panic-pace.",
    "injury fear": "One pain-free quality rep noted post-session; build trust through evidence.",
    "fear of takedowns": "Calm level-change rep + reset stance; kill the panic loop.",
    "confidence": "End the session by naming one thing that worked; replay it before the next session.",
    "attention": "Pick one technical cue per round/set; say it out loud before starting.",
    "motivation": "One why-line pre-session; tie today's work to a fight-specific outcome.",
    "generic": "One simple intention pre-session; one win logged post-session.",
}


_BLOCK_AFFINITY_PURPOSE = {
    "pressure": "Pair pressure rehearsal with the day that already creates real pressure.",
    "rushing": "Drill the reset on the day the athlete most wants to chase.",
    "composure": "Practise the reset ritual on the day composure is most likely to break.",
    "breath control": "Lock the breath pattern on the day it has to survive sport pace.",
    "gas tank": "Build gas-tank confidence on the day the work directly trains it.",
    "injury fear": "Rebuild movement trust on rehab and strength days where exposure is graded.",
    "fear of takedowns": "Calm the defensive response on the day live grappling actually happens.",
    "confidence": "Anchor confidence to fresh, high-quality output, not to fatigue days.",
    "attention": "Train attention on days where one cue clearly improves output.",
    "motivation": "Use easier sessions to anchor the bigger why; do not load it onto hard days.",
    "generic": "Keep the cue tied to today's actual session.",
}


def _attachment_kind_for_category(category: str) -> str:
    if category == "strength":
        return "between-set / pre-lift cue"
    if category == "conditioning":
        return "between-round cue + post-session log"
    if category == "recovery":
        return "visualization or journal block"
    if category == "rehab":
        return "graded-exposure log"
    if category == "sparring":
        return "pre-round reset + post-round recall"
    return "warm-up / cooldown cue"


def _build_mental_slots_for_phase(blocks: list[str], phase: str) -> list[dict]:
    slots: list[dict] = []
    for idx, block in enumerate(blocks, start=1):
        drills = _drills_for_block(block, phase)
        if not drills:
            continue
        primary = drills[0]
        alternates = drills[1:]
        slots.append(
            {
                "slot_id": f"{phase.lower()}_mental_{block.replace(' ', '_')}",
                "role": f"mental_{block.replace(' ', '_')}",
                "purpose": _BLOCK_AFFINITY_PURPOSE.get(block, "Layer mental cue onto an existing session."),
                "selected": {
                    "name": primary["name"],
                    "source": "mental_training_bank",
                    "block": block,
                    "dose": primary.get("dose", ""),
                    "attach": primary.get("attach", ""),
                    "purpose": primary.get("purpose", ""),
                },
                "alternates": [
                    {
                        "name": alt["name"],
                        "source": "mental_training_bank",
                        "block": block,
                        "dose": alt.get("dose", ""),
                        "attach": alt.get("attach", ""),
                        "purpose": alt.get("purpose", ""),
                    }
                    for alt in alternates
                ],
                "replace_with_same_role": True,
                "priority": "high" if idx == 1 else "medium",
            }
        )
    return slots


def derive_phase_mental_briefs(
    *,
    athlete_model: dict,
    phase_briefs: dict[str, dict],
    training_context_blocks: list[str] | str | None = None,
) -> dict[str, dict]:
    """Return a per-phase mental brief keyed by phase name.

    `training_context_blocks` is the Stage 1 mental_block classification. When
    omitted the function falls back to `athlete_model['mental_blocks']`.
    """
    raw_blocks = training_context_blocks if training_context_blocks is not None else athlete_model.get("mental_blocks")
    blocks = _filter_blocks_for_style(_normalize_blocks(raw_blocks), athlete_model)

    briefs: dict[str, dict] = {}
    for phase, phase_brief in phase_briefs.items():
        briefs[phase] = _phase_brief_for_blocks(
            phase=phase,
            blocks=blocks,
            athlete_model=athlete_model,
            phase_brief=phase_brief,
        )
    return briefs


def build_mental_candidate_pools(
    *,
    athlete_model: dict,
    phase_briefs: dict[str, dict],
    training_context_blocks: list[str] | str | None = None,
) -> dict[str, list[dict]]:
    """Return a per-phase mental_slots map for candidate_pools."""
    raw_blocks = training_context_blocks if training_context_blocks is not None else athlete_model.get("mental_blocks")
    blocks = _filter_blocks_for_style(_normalize_blocks(raw_blocks), athlete_model)

    pools: dict[str, list[dict]] = {}
    for phase in phase_briefs:
        pools[phase] = _build_mental_slots_for_phase(blocks, phase)
    return pools


def attach_mental_to_weekly_role_map(
    *,
    weekly_role_map: dict,
    phase_mental_briefs: dict[str, dict],
) -> dict:
    """Return a new weekly_role_map with mental_attachments added per session.

    The original map is not mutated. Each week's session_roles get an extra
    `mental_attachment` field when a mental block has good affinity for the
    role; weeks gain a `mental_attachments_summary` listing the matched
    attachments. Weeks with no active mental brief or no matched roles are
    left untouched apart from a defensive copy.
    """
    if not isinstance(weekly_role_map, dict):
        return {}

    weeks_in = weekly_role_map.get("weeks") or []
    new_weeks: list[dict] = []

    for week in weeks_in:
        if not isinstance(week, dict):
            new_weeks.append(week)
            continue
        phase = str(week.get("phase") or "").upper()
        brief = phase_mental_briefs.get(phase) if phase else None
        if not brief:
            new_weeks.append(dict(week))
            continue

        blocks = list(brief.get("primary_blocks") or [])
        if not blocks:
            new_weeks.append(dict(week))
            continue

        weekly_attachment_rules = {
            block: _DEFAULT_CUE_BY_BLOCK.get(block, "") for block in blocks
        }

        new_session_roles: list[dict] = []
        used_blocks: list[str] = []
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                new_session_roles.append(role)
                continue
            new_role = dict(role)
            attachment = _resolve_session_attachment(
                new_role,
                blocks=blocks,
                weekly_attachment_rules=weekly_attachment_rules,
            )
            if attachment:
                new_role["mental_attachment"] = attachment
                used_blocks.append(attachment["block"])
            new_session_roles.append(new_role)

        unused_blocks = [block for block in blocks if block not in used_blocks]
        new_week = dict(week)
        new_week["session_roles"] = new_session_roles
        new_week["mental_attachments_summary"] = {
            "phase": phase,
            "primary_blocks": blocks,
            "covered_blocks": dedupe_preserve_order(used_blocks),
            "uncovered_blocks": unused_blocks,
            "weekly_pattern": brief.get("weekly_pattern", ""),
            "load_bias": brief.get("load_bias", ""),
            "coach_voice": brief.get("coach_voice", ""),
            "do_not": list(brief.get("do_not", [])),
        }
        new_weeks.append(new_week)

    new_map = dict(weekly_role_map)
    new_map["weeks"] = new_weeks
    return new_map


MENTAL_TRAINING_WRITING_RULES = [
    "Mental work is layered onto existing strength, conditioning, sparring, recovery, or rehab sessions — never scheduled as a separate session.",
    "Use the per-session mental_attachment to choose where the mental cue lives that day; if a role has no attachment, do not invent one.",
    "Match the mental cue to the day's actual stress: composure / rushing / pressure / breath cues belong on sparring or fight-pace days; attention cues belong on strength or alactic days; confidence and visualization belong on recovery or freshness days; injury-fear graded exposure belongs on rehab or strength days.",
    "Honor the phase dose: GPP builds the habit, SPP rehearses it under sport stress, TAPER only rehearses the calm version — never introduce new drills in taper.",
    "Write mental work in plain coach voice with a clear purpose. No generic motivation ('stay consistent', 'trust the process', 'push yourself', 'you got this').",
    "Keep the dose small (1-5 minutes per session); reduce or remove it on hard sparring or peak conditioning days when fatigue is already high.",
    "If active weight cut, keep mental work shorter and protective; do not add cognitive load on top of the cut.",
    "If the athlete has no real mental block, default to one short intention pre-session and one win logged post-session — do not invent challenges.",
]


MENTAL_TRAINING_FINALIZER_GUIDE = (
    "MENTAL TRAINING INTEGRATION\n"
    "Stage 1 produced the athlete's raw mental profile (mental_blocks). Stage 2 has already paired "
    "each phase brief with a phase-aware mental brief and attached cues to the specific session "
    "roles where they fit. Render mental work as a small layer inside an existing session "
    "(warm-up, between-set, between-round, post-session log, pre-session reset), not as a separate "
    "session and not as a free-floating Mindset section.\n"
    "Honor the phase dose: GPP builds the habit, SPP rehearses under sport stress, TAPER only "
    "rehearses calm reset rituals (no new drills). Match the cue to the actual stress of that day. "
    "Use plain coach voice with a clear purpose; never default to generic motivation. If a session "
    "role has no mental_attachment in selected_plan.weekly_role_map, do not invent one — leave the "
    "session purely physical."
)
