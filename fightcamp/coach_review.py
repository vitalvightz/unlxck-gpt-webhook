from __future__ import annotations

import logging
from typing import Iterable

from .conditioning import is_banned_drill, normalize_system, render_conditioning_block
from .injury_filtering import injury_match_details
from .injury_guard import choose_injury_replacement, injury_decision
from .rehab_protocols import build_coach_review_entries
from .strength import format_strength_block, is_banned_exercise
from .training_context import normalize_equipment_list

logger = logging.getLogger(__name__)


def _format_log_list(values: Iterable[str]) -> str:
    items = [str(value) for value in values if value]
    if not items:
        return "[]"
    return f"[{', '.join(items)}]"


def _injury_log_details(
    item: dict,
    injuries: list[str],
    *,
    fields: Iterable[str],
    region: str | None,
) -> tuple[list[str], list[str], list[str]]:
    matches = injury_match_details(item, injuries, fields=fields, risk_levels=("exclude", "flag"))
    match = None
    if region:
        for detail in matches:
            if detail.get("region") == region:
                match = detail
                break
    if match is None and matches:
        match = matches[0]
    if not match:
        return [], [], []
    return (
        match.get("fields", []),
        match.get("patterns", []),
        match.get("tags", []),
    )


def _decision_for_item(
    item: dict,
    injuries: list[str],
    *,
    phase: str,
    fatigue: str,
    extra_fields: Iterable[str] | None = None,
) -> tuple[str | None, dict]:
    if extra_fields:
        notes = " ".join(str(item.get(field, "") or "") for field in extra_fields)
        combined = {**item, "notes": f"{item.get('notes', '')} {notes}".strip()}
    else:
        combined = item
    decision = injury_decision(combined, injuries, phase, fatigue)
    region = None
    if isinstance(decision.reason, dict):
        region = decision.reason.get("region")
    return region, decision


def _safe_strength_candidate(
    *,
    used_names: set[str],
    exercise_bank: list[dict],
    phase: str,
    fatigue: str,
    injuries: list[str],
    equipment_access: list[str],
    fight_format: str,
    excluded_item: dict,
) -> dict | None:
    eq_set = set(normalize_equipment_list(equipment_access))
    candidates: list[dict] = []
    for cand in exercise_bank:
        name = cand.get("name")
        if not name or name in used_names:
            continue
        if phase.upper() not in cand.get("phases", []):
            continue
        cand_eq = normalize_equipment_list(cand.get("equipment", []))
        if cand_eq and not set(cand_eq).issubset(eq_set):
            continue
        details = " ".join(
            [
                cand.get("notes", ""),
                cand.get("method", ""),
                cand.get("movement", ""),
            ]
        )
        if is_banned_exercise(name, cand.get("tags", []), fight_format, details):
            continue
        _, decision = _decision_for_item(
            cand,
            injuries,
            phase=phase,
            fatigue=fatigue,
            extra_fields=("method", "movement"),
        )
        if decision.action == "exclude":
            continue
        candidates.append(cand)
    return choose_injury_replacement(
        excluded_item=excluded_item,
        candidates=candidates,
        injuries=injuries,
        phase=phase,
        fatigue=fatigue,
        score_fn=None,
    )


def _safe_conditioning_candidate(
    *,
    used_names: set[str],
    candidates: list[dict],
    phase: str,
    fatigue: str,
    injuries: list[str],
    equipment_access: list[str],
    fight_format: str,
    tactical_styles: list[str],
    technical_styles: list[str],
    system: str,
    excluded_item: dict,
) -> dict | None:
    eq_set = set(normalize_equipment_list(equipment_access))
    pool: list[dict] = []
    for cand in candidates:
        name = cand.get("name")
        if not name or name in used_names:
            continue
        if phase.upper() not in cand.get("phases", []):
            continue
        cand_system = normalize_system(cand.get("system"), source="coach_review")
        if cand_system != system:
            continue
        cand_eq = normalize_equipment_list(cand.get("equipment", []))
        if cand_eq and not set(cand_eq).issubset(eq_set):
            continue
        tags = [t.lower() for t in cand.get("tags", [])]
        details = " ".join(
            [
                cand.get("duration", ""),
                cand.get("notes", ""),
                cand.get("modality", ""),
                cand.get("equipment_note", ""),
            ]
        )
        if is_banned_drill(name, tags, fight_format, details, tactical_styles, technical_styles):
            continue
        _, decision = _decision_for_item(
            cand,
            injuries,
            phase=phase,
            fatigue=fatigue,
            extra_fields=("purpose", "description", "modality"),
        )
        if decision.action == "exclude":
            continue
        pool.append(cand)
    return choose_injury_replacement(
        excluded_item=excluded_item,
        candidates=pool,
        injuries=injuries,
        phase=phase,
        fatigue=fatigue,
        score_fn=None,
    )


def _build_conditioning_pool(banks: Iterable[list[dict]]) -> list[dict]:
    drills: list[dict] = []
    for bank in banks:
        drills.extend(bank)
    return drills


def build_coach_review_notes(entries: list[dict], substitutions: list[dict]) -> str:
    if not entries:
        return ""
    lines = ["### Coach Review & Safety Pass"]
    for entry in entries:
        for summary in entry.get("injury_summaries", []):
            lines.append(f"- {summary}")
        allowed = entry["ruleset"].get("allowed", [])
        avoid = entry["ruleset"].get("avoid", [])
        rehab = entry["rehab_drills"]
        if allowed:
            lines.append(f"  - Do: {'; '.join(allowed[:2])}")
        if avoid:
            lines.append(f"  - Avoid: {'; '.join(avoid[:2])}")
        if rehab:
            lines.append(f"  - Rehab priority: {'; '.join(rehab[:2])}")

    if substitutions:
        lines += ["", "### Safety Substitutions"]
        for sub in substitutions:
            if sub.get("new"):
                lines.append(
                    f"- {sub['phase']} {sub['module']}: {sub['old']} → {sub['new']} ({sub['label']})"
                )
            else:
                lines.append(
                    f"- {sub['phase']} {sub['module']}: removed {sub['old']} ({sub['label']})"
                )

    return "\n".join(lines)


def run_coach_review(
    *,
    injury_string: str,
    phase: str,
    training_context: dict,
    exercise_bank: list[dict],
    conditioning_banks: Iterable[list[dict]],
    strength_blocks: dict[str, dict | None],
    conditioning_blocks: dict[str, dict | None],
) -> tuple[str, dict[str, dict | None], dict[str, dict | None], list[dict]]:
    entries = build_coach_review_entries(injury_string, phase)
    if not entries:
        return "", strength_blocks, conditioning_blocks, []

    region_labels = {entry["region_key"]: entry.get("label", "Injury safety") for entry in entries}
    substitutions: list[dict] = []

    equipment_access = training_context.get("equipment", [])
    fight_format = training_context.get("fight_format", "mma")
    tactical_styles = training_context.get("style_tactical", [])
    technical_styles = training_context.get("style_technical", [])
    fatigue = training_context.get("fatigue", "low")
    injuries = training_context.get("injuries", [])

    updated_strength: dict[str, dict | None] = {}
    for phase_key, block in strength_blocks.items():
        if not block:
            updated_strength[phase_key] = block
            continue
        used_names = {ex.get("name") for ex in block.get("exercises", []) if ex.get("name")}
        updated_exercises: list[dict] = []
        for ex in block.get("exercises", []):
            region_key, decision = _decision_for_item(
                ex,
                injuries,
                phase=phase_key,
                fatigue=fatigue,
                extra_fields=("method", "movement"),
            )
            if decision.action != "exclude":
                updated_exercises.append(ex)
                continue
            decision_reason = decision.reason if isinstance(decision.reason, dict) else {}
            region = decision_reason.get("region")
            fields, patterns, tags = _injury_log_details(
                ex,
                injuries,
                fields=("name", "method", "movement"),
                region=region,
            )
            logger.warning(
                "[injury-guard] coach_review strength excluded '%s' phase=%s action=%s region=%s fields=%s patterns=%s tags=%s",
                ex.get("name", "Unnamed"),
                phase_key,
                decision.action,
                region,
                _format_log_list(fields),
                _format_log_list(patterns),
                _format_log_list(tags),
            )
            replacement = _safe_strength_candidate(
                used_names=used_names,
                exercise_bank=exercise_bank,
                phase=phase_key,
                fatigue=fatigue,
                injuries=injuries,
                equipment_access=equipment_access,
                fight_format=fight_format,
                excluded_item=ex,
            )
            if replacement:
                used_names.add(replacement.get("name"))
                updated_exercises.append(replacement)
                substitutions.append(
                    {
                        "phase": phase_key,
                        "module": "Strength",
                        "old": ex.get("name", "Unnamed"),
                        "new": replacement.get("name", "Unnamed"),
                        "region_key": region_key,
                        "label": region_labels.get(region_key, "Injury safety"),
                    }
                )
            else:
                substitutions.append(
                    {
                        "phase": phase_key,
                        "module": "Strength",
                        "old": ex.get("name", "Unnamed"),
                        "new": "",
                        "region_key": region_key,
                        "label": region_labels.get(region_key, "Injury safety"),
                    }
                )
        block["exercises"] = updated_exercises
        block["block"] = format_strength_block(
            phase_key, training_context.get("fatigue", "low"), updated_exercises
        )
        updated_strength[phase_key] = block

    updated_conditioning: dict[str, dict | None] = {}
    candidate_pool = _build_conditioning_pool(conditioning_banks)
    for phase_key, cond in conditioning_blocks.items():
        if not cond:
            updated_conditioning[phase_key] = cond
            continue
        grouped_drills = cond.get("grouped_drills", {})
        used_names = {
            d.get("name")
            for drills in grouped_drills.values()
            for d in drills
            if d.get("name")
        }
        for system, drills in grouped_drills.items():
            idx = 0
            while idx < len(drills):
                drill = drills[idx]
                region_key, decision = _decision_for_item(
                    drill,
                    injuries,
                    phase=phase_key,
                    fatigue=fatigue,
                    extra_fields=("purpose", "description", "modality"),
                )
                if decision.action != "exclude":
                    idx += 1
                    continue
                decision_reason = decision.reason if isinstance(decision.reason, dict) else {}
                region = decision_reason.get("region")
                fields, patterns, tags = _injury_log_details(
                    drill,
                    injuries,
                    fields=("name", "purpose", "description", "modality"),
                    region=region,
                )
                logger.warning(
                    "[injury-guard] coach_review conditioning excluded '%s' phase=%s system=%s action=%s region=%s fields=%s patterns=%s tags=%s",
                    drill.get("name", "Unnamed"),
                    phase_key,
                    system,
                    decision.action,
                    region,
                    _format_log_list(fields),
                    _format_log_list(patterns),
                    _format_log_list(tags),
                )
                replacement = _safe_conditioning_candidate(
                    used_names=used_names,
                    candidates=candidate_pool,
                    phase=phase_key,
                    fatigue=fatigue,
                    injuries=injuries,
                    equipment_access=equipment_access,
                    fight_format=fight_format,
                    tactical_styles=tactical_styles,
                    technical_styles=technical_styles,
                    system=system,
                    excluded_item=drill,
                )
                if replacement:
                    used_names.add(replacement.get("name"))
                    drills[idx] = replacement
                    substitutions.append(
                        {
                            "phase": phase_key,
                            "module": "Conditioning",
                            "old": drill.get("name", "Unnamed"),
                            "new": replacement.get("name", "Unnamed"),
                            "region_key": region_key,
                            "label": region_labels.get(region_key, "Injury safety"),
                        }
                    )
                    idx += 1
                else:
                    substitutions.append(
                        {
                            "phase": phase_key,
                            "module": "Conditioning",
                            "old": drill.get("name", "Unnamed"),
                            "new": "",
                            "region_key": region_key,
                            "label": region_labels.get(region_key, "Injury safety"),
                        }
                    )
                    drills.pop(idx)
            grouped_drills[system] = drills

        cond["grouped_drills"] = grouped_drills
        cond["block"] = render_conditioning_block(
            grouped_drills,
            phase=phase_key,
            phase_color=cond.get("phase_color", "#000"),
            missing_systems=cond.get("missing_systems", []),
            diagnostic_context=cond.get("diagnostic_context", {}),
            sport=cond.get("sport"),
        )
        updated_conditioning[phase_key] = cond

    coach_notes = build_coach_review_notes(entries, substitutions)
    return coach_notes, updated_strength, updated_conditioning, substitutions
