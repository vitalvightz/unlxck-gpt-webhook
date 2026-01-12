from __future__ import annotations

from typing import Iterable

from .conditioning import SYSTEM_ALIASES, is_banned_drill, render_conditioning_block
from .injury_exclusion_rules import INJURY_RULES
from .injury_filtering import ensure_tags, match_forbidden
from .rehab_protocols import build_coach_review_entries
from .strength import format_strength_block, is_banned_exercise
from .training_context import normalize_equipment_list


def _region_violation(item: dict, region_rules: dict[str, dict], fields: Iterable[str]) -> str | None:
    tags = {t.lower() for t in ensure_tags(item)}
    text = " ".join(str(item.get(field, "") or "") for field in fields)
    for region_key, rules in region_rules.items():
        ban_keywords = rules.get("exclude_keywords", rules.get("ban_keywords", []))
        ban_tags = {t.lower() for t in rules.get("exclude_tags", rules.get("ban_tags", []))}
        if tags & ban_tags:
            return region_key
        if match_forbidden(text, ban_keywords):
            return region_key
    return None


def _safe_strength_candidate(
    *,
    used_names: set[str],
    region_rules: dict[str, dict],
    exercise_bank: list[dict],
    phase: str,
    equipment_access: list[str],
    fight_format: str,
) -> dict | None:
    eq_set = set(normalize_equipment_list(equipment_access))
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
        if _region_violation(cand, region_rules, ("name", "notes", "method", "movement")):
            continue
        return cand
    return None


def _safe_conditioning_candidate(
    *,
    used_names: set[str],
    region_rules: dict[str, dict],
    candidates: list[dict],
    phase: str,
    equipment_access: list[str],
    fight_format: str,
    tactical_styles: list[str],
    technical_styles: list[str],
    system: str,
) -> dict | None:
    eq_set = set(normalize_equipment_list(equipment_access))
    for cand in candidates:
        name = cand.get("name")
        if not name or name in used_names:
            continue
        if phase.upper() not in cand.get("phases", []):
            continue
        raw_system = cand.get("system", "").lower()
        cand_system = SYSTEM_ALIASES.get(raw_system, raw_system)
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
        if _region_violation(cand, region_rules, ("name", "notes", "purpose", "description", "modality")):
            continue
        return cand
    return None


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
        severity = entry["severity"]
        severity_color = {"severe": "🔴", "moderate": "🟠"}.get(severity, "🟠")
        locations = ", ".join(sorted(entry["locations"]))
        lines.append(
            f"- {entry['region_label']} ({locations}) — Severity: {severity_color} {severity}"
        )
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
                    f"- {sub['phase']} {sub['module']}: {sub['old']} → {sub['new']} ({sub['region_label']})"
                )
            else:
                lines.append(
                    f"- {sub['phase']} {sub['module']}: removed {sub['old']} ({sub['region_label']})"
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

    region_rules = {
        entry["region_key"]: INJURY_RULES.get(entry["region_key"], {})
        for entry in entries
    }
    region_labels = {entry["region_key"]: entry["region_label"] for entry in entries}
    substitutions: list[dict] = []

    equipment_access = training_context.get("equipment", [])
    fight_format = training_context.get("fight_format", "mma")
    tactical_styles = training_context.get("style_tactical", [])
    technical_styles = training_context.get("style_technical", [])

    updated_strength: dict[str, dict | None] = {}
    for phase_key, block in strength_blocks.items():
        if not block:
            updated_strength[phase_key] = block
            continue
        used_names = {ex.get("name") for ex in block.get("exercises", []) if ex.get("name")}
        updated_exercises: list[dict] = []
        for ex in block.get("exercises", []):
            region_key = _region_violation(
                ex, region_rules, ("name", "notes", "method", "movement")
            )
            if not region_key:
                updated_exercises.append(ex)
                continue
            replacement = _safe_strength_candidate(
                used_names=used_names,
                region_rules=region_rules,
                exercise_bank=exercise_bank,
                phase=phase_key,
                equipment_access=equipment_access,
                fight_format=fight_format,
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
                        "region_label": region_labels.get(region_key, "Injury"),
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
                        "region_label": region_labels.get(region_key, "Injury"),
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
                region_key = _region_violation(
                    drill,
                    region_rules,
                    ("name", "notes", "purpose", "description", "modality"),
                )
                if not region_key:
                    idx += 1
                    continue
                replacement = _safe_conditioning_candidate(
                    used_names=used_names,
                    region_rules=region_rules,
                    candidates=candidate_pool,
                    phase=phase_key,
                    equipment_access=equipment_access,
                    fight_format=fight_format,
                    tactical_styles=tactical_styles,
                    technical_styles=technical_styles,
                    system=system,
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
                            "region_label": region_labels.get(region_key, "Injury"),
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
                            "region_label": region_labels.get(region_key, "Injury"),
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
        )
        updated_conditioning[phase_key] = cond

    coach_notes = build_coach_review_notes(entries, substitutions)
    return coach_notes, updated_strength, updated_conditioning, substitutions
