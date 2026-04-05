from __future__ import annotations

import json
from typing import Any

from .stage2_late_fight_utils import resolve_late_fight_window


REPAIR_PROMPT_TEMPLATE = """You are revising a Stage 2 final plan after validation.

GOAL:
Repair the previous final plan so it becomes restriction-compliant, phase-consistent, and coherent with the planning brief.

REPAIR RULES:
1. Treat restrictions as hard constraints. Remove or replace violating items; do not soften them into compliance.
2. Fix validator errors first, then warnings.
3. Preserve compliant parts of the previous final plan when they still fit the planning brief.
4. Use candidate pools and same-role alternates from the planning brief before inventing anything new.
5. If a phase-critical element is missing, reintroduce it with a conservative, compliant option that matches the phase strategy.
6. Remove any internal/admin scaffolding such as Athlete Profile, Selection Rationale, Coach Notes, planning-brief labels, or Stage-2-only notes.
7. Remove raw HTML, code fences, and any non-athlete formatting artifacts.
8. If an anchor session drifted into support work, restore the strongest compliant anchor option available before accessories.
9. In non-taper weeks, restore a true externally loaded high-transfer anchor when a compliant option exists; if none exists, label the week injury-limited and keep the safest force-preserving substitute.
10. Resolve conditioning choices into one primary prescription and at most one explicit fallback.
11. Collapse menu-like session templates into one final prescription whenever the athlete context already resolves the choice.
12. Keep all primary drills, support drills, and fallbacks equipment-valid for the athlete profile.
13. Keep every active week present and structurally complete, especially the late-camp weeks.
14. Preserve the default boxer weekly rhythm of support strength, low-damage conditioning, recovery, primary strength, then the main phase-specific conditioning stressor unless a higher-order planning rule forces a different order.
15. Do not create more active weekly sessions than the weekly_role_map allows. If the athlete has extra available days, leave them off or clearly optional rather than turning them into extra training days.
16. If weekly_role_map or week_by_week_progression marks intentional_compression.active, keep that smaller week on purpose and do not restore the suppressed standalone role.
17. If a week contains intentionally_unused_days entries, leave those days as light recovery or completely off. Do not add active training sessions to intentionally unused days.
18. Treat declared hard sparring days in weekly_role_map as immutable hard_sparring_day slots. If readiness is compromised, deload hard sparring on that day; do not replace it with strength, recovery, aerobic, or technical-only work.
19. In taper weeks, keep the work short, direct, and low-noise with minimal branching.
20. If days_until_fight is 7 or less, stay inside the exact late-fight band. Do not rebuild normal week completeness, extra session roles, anchor language, or conditioning-system build logic.
21. Keep the final output athlete-facing. Do not mention the validator, the repair process, or rejected items.
22. If active weight cut shaped the plan, acknowledge it plainly in the athlete-facing output.
23. For high-pressure cuts, include one short summary-level note and one short support-level note without turning the plan into a long weight-cut essay.
24. For any corrective or adjustment line, make one clear coaching call with a short why tied to performance, safety, readiness, or the week's main objective.
25. Prefer command then reason on corrective lines; do not lead with explanation and then soften it into a suggestion.
26. Do not open corrective lines with generic openers such as 'focus on', 'ensure', 'make sure', or 'it's important to'; start with the action.
27. Use autonomy-supportive phrasing only when a real safe choice exists; if so, offer at most two practical options, and only when both are safe and materially equivalent.
28. Replace generic motivation, scripted empathy, and empty safety language with concrete next-action coaching.
29. Do not use generic motivation such as 'stay consistent', 'trust the process', 'push yourself', or 'you've got this'.
30. Do not use empty safety language such as 'listen to your body', 'be careful', or 'avoid overtraining' unless it adds a concrete rule, symptom trigger, or plan change.
31. If fatigue is high or fight-week pressure is active, reduce optionality and make the safest performance-preserving call plainly.
32. If injury management is active, lead with constraints, substitutions, or stop rules rather than optional language.
33. If active weight cut is present, keep the language shorter, safety-first, and non-negotiable about recovery margin.
34. Aim critique at the plan, load, or execution issue, never at the athlete's character.
35. Reduce repeated openers, labels, and filler reminders so the repaired plan reads like a final coach prescription, not a template.

OUTPUT:
Return only the revised athlete-facing final plan."""


def _json_block(value: dict | list) -> str:
    return "```json\n" + json.dumps(value, indent=2) + "\n```"



def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    return [str(values).strip()]


def _late_fight_window(planning_brief: dict) -> str:
    return resolve_late_fight_window(
        payload=planning_brief.get("days_out_payload") or {},
        athlete=planning_brief.get("athlete_model") or planning_brief.get("athlete_snapshot") or {},
    )


def _late_fight_repair_notes(planning_brief: dict) -> str:
    window = _late_fight_window(planning_brief)
    if window == "camp":
        return ""
    band_label = {
        "d7_to_d5": "D-7 to D-5 compressed late-fight week",
        "d4_to_d2": "D-4 to D-2 session-by-session sharpness/freshness window",
        "d1": "D-1 fight-eve primer window",
        "d0": "D-0 fight-day protocol window",
    }[window]
    return (
        "LATE-FIGHT BAND GUARDRAILS\n"
        f"- Stay inside the {band_label}.\n"
        "- Do not restore suppressed week completeness, extra session roles, anchor wording, or conditioning-system build logic.\n"
        "- Keep the repaired output compressed and athlete-facing for this exact late-fight band."
    )



def _build_revision_priorities(planning_brief: dict, validator_report: dict) -> dict[str, list[dict]]:
    late_fight_window = _late_fight_window(planning_brief)
    restriction_fixes: list[dict] = []
    for hit in validator_report.get("restricted_hits", []) or []:
        restriction_fixes.append(
            {
                "restriction": hit.get("restriction"),
                "line": hit.get("line"),
                "action": "remove_or_replace",
                "reason": "restriction violation",
            }
        )

    missing_elements: list[dict] = []
    for item in validator_report.get("missing_required_elements", []) or []:
        missing_elements.append(
            {
                "phase": item.get("phase"),
                "requirement": item.get("requirement"),
                "candidate_names": _clean_list(item.get("candidate_names", [])),
                "action": "restore_phase_critical_element",
            }
            )

    formatting_fixes: list[dict] = []
    for error in validator_report.get("errors", []) or []:
        code = str(error.get("code") or "")
        if code == "internal_section_leak":
            formatting_fixes.append(
                {
                    "action": "remove_internal_scaffolding",
                    "section": error.get("section"),
                    "line": error.get("line"),
                }
            )
        elif code == "internal_phrase_leak":
            formatting_fixes.append(
                {
                    "action": "remove_internal_phrase",
                    "phrase": error.get("phrase"),
                    "line": error.get("line"),
                }
            )
        elif code in {"html_markup_present", "code_fence_present"}:
            formatting_fixes.append(
                {
                    "action": "remove_formatting_artifact",
                    "code": code,
                    "line": error.get("line"),
                }
            )

    quality_fixes: list[dict] = []
    for warning in validator_report.get("warnings", []) or []:
        code = str(warning.get("code") or "")
        if code == "weak_anchor_session":
            quality_fixes.append(
                {
                    "action": "restore_anchor_session_quality",
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                    "anchor_candidates": _clean_list(warning.get("anchor_candidates", [])),
                }
            )
        elif code == "support_takeover_before_anchor":
            quality_fixes.append(
                {
                    "action": "move_support_work_after_anchor",
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                    "anchor_candidates": _clean_list(warning.get("anchor_candidates", [])),
                }
            )
        elif code == "conditional_conditioning_choice":
            quality_fixes.append(
                {
                    "action": "resolve_conditioning_to_primary_plus_fallback",
                    "line": warning.get("line"),
                }
            )
        elif code == "too_many_fallbacks":
            quality_fixes.append(
                {
                    "action": "collapse_extra_fallbacks_to_final_choice",
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                }
            )
        elif code == "unresolved_access_fallback":
            quality_fixes.append(
                {
                    "action": "remove_unneeded_fallback_branch_or_make_contingency_explicit",
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                    "line": warning.get("line"),
                }
            )
        elif code == "template_like_session_render":
            quality_fixes.append(
                {
                    "action": "rewrite_session_as_final_prescription",
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                }
            )
        elif code == "taper_option_overload":
            quality_fixes.append(
                {
                    "action": "simplify_taper_session",
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                }
            )
        elif code == "equipment_incongruent_selection":
            quality_fixes.append(
                {
                    "action": "replace_with_equipment_valid_same_role_option",
                    "phase": warning.get("phase"),
                    "line": warning.get("line"),
                    "required_equipment": _clean_list(warning.get("required_equipment", [])),
                }
            )
        elif code == "missing_week_session_role":
            action = "preserve_late_fight_compression" if late_fight_window != "camp" else "restore_missing_week_structure"
            quality_fixes.append(
                {
                    "action": action,
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "expected_roles": _clean_list(warning.get("expected_roles", [])),
                    "expected_role_days": list(warning.get("expected_role_days") or []),
                }
            )
        elif code == "late_camp_session_incomplete":
            action = "preserve_late_fight_compression" if late_fight_window != "camp" else "complete_late_camp_week"
            quality_fixes.append(
                {
                    "action": action,
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "expected_roles": _clean_list(warning.get("expected_roles", [])),
                    "expected_role_days": list(warning.get("expected_role_days") or []),
                }
            )
        elif code == "weekly_session_overage":
            action = "trim_late_fight_stack" if late_fight_window != "camp" else "trim_extra_week_sessions_to_match_profile"
            quality_fixes.append(
                {
                    "action": action,
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "expected_session_count": warning.get("expected_session_count"),
                    "actual_session_count": warning.get("actual_session_count"),
                }
            )
        elif code == "weekly_rhythm_broken":
            action = "preserve_late_fight_compression" if late_fight_window != "camp" else "restore_default_boxer_weekly_rhythm"
            quality_fixes.append(
                {
                    "action": action,
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                }
            )
        elif code == "missing_weight_cut_acknowledgement":
            quality_fixes.append(
                {
                    "action": "add_weight_cut_acknowledgement",
                }
            )
        elif code == "high_pressure_weight_cut_underaddressed":
            quality_fixes.append(
                {
                    "action": "add_summary_and_support_weight_cut_notes",
                    "summary_lines": _clean_list(warning.get("summary_lines", [])),
                    "support_lines": _clean_list(warning.get("support_lines", [])),
                }
            )
        elif code in {"gimmick_name", "overstyled_drill_name"}:
            quality_fixes.append(
                {
                    "action": "replace_overstyled_name_with_plain_language",
                    "line": warning.get("line"),
                }
            )
        elif code == "sport_language_leak":
            quality_fixes.append(
                {
                    "action": "rewrite_sport_language_to_fit_athlete_context",
                    "line": warning.get("line"),
                    "sport": warning.get("sport"),
                }
            )
        elif code in {"generic_filler_phrase", "generic_motivation_cliche", "generic_instruction_opener"}:
            quality_fixes.append(
                {
                    "action": "replace_low_trust_filler_with_concrete_coaching",
                    "line": warning.get("line"),
                    "code": code,
                }
            )
        elif code == "option_overload":
            quality_fixes.append(
                {
                    "action": "collapse_options_to_safe_equivalent_choices_or_one_final_call",
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                    "line": warning.get("line"),
                    "risk_context": _clean_list(warning.get("risk_context", [])),
                }
            )
        elif code == "hedged_adjustment_without_decision":
            quality_fixes.append(
                {
                    "action": "rewrite_adjustment_as_clear_call_with_short_why",
                    "line": warning.get("line"),
                }
            )
        elif code == "empty_safety_language":
            quality_fixes.append(
                {
                    "action": "replace_empty_safety_line_with_operational_guardrails",
                    "line": warning.get("line"),
                    "risk_context": _clean_list(warning.get("risk_context", [])),
                }
            )
        elif code in {
            "late_fight_block_overage",
            "late_fight_strength_overage",
            "late_fight_conditioning_overage",
            "late_fight_week_leakage",
            "late_fight_session_leakage",
            "late_fight_session_overstack",
            "fight_eve_primer_leakage",
            "fight_eve_primer_overstack",
            "fight_day_protocol_leakage",
        }:
            quality_fixes.append(
                {
                    "action": "compress_late_fight_output",
                    "late_fight_window": warning.get("late_fight_window") or late_fight_window,
                    "issue_code": code,
                    "matched_lines": _clean_list(warning.get("matched_lines", [])),
                    "block_cap": warning.get("block_cap"),
                }
            )
    return {
        "fix_first": restriction_fixes,
        "strip_out": formatting_fixes,
        "then_restore": missing_elements,
        "quality_repairs": quality_fixes,
    }



def build_stage2_repair_prompt(*, planning_brief: dict, failed_plan_text: str, validator_report: dict) -> str:
    revision_priorities = _build_revision_priorities(planning_brief, validator_report)
    sections = [
        REPAIR_PROMPT_TEMPLATE.strip(),
        _late_fight_repair_notes(planning_brief),
        "REVISION PRIORITIES\n" + _json_block(revision_priorities),
        "VALIDATOR REPORT\n" + _json_block(validator_report),
        "PLANNING BRIEF\n" + _json_block(planning_brief),
        "PREVIOUS FINAL PLAN\n" + (failed_plan_text or "").strip(),
    ]
    return "\n\n---\n\n".join(section for section in sections if section.strip())
