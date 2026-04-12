from __future__ import annotations
from .normalization import clean_list

import json
from typing import Any


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
20. Keep the final output athlete-facing. Do not mention the validator, the repair process, or rejected items.
21. If active weight cut shaped the plan, acknowledge it plainly in the athlete-facing output.
22. For high-pressure cuts, include one short summary-level note and one short support-level note without turning the plan into a long weight-cut essay.
23. For any corrective or adjustment line, make one clear coaching call with a short why tied to performance, safety, readiness, or the week's main objective.
24. Prefer command then reason on corrective lines; do not lead with explanation and then soften it into a suggestion.
25. Do not open corrective lines with generic openers such as 'focus on', 'ensure', 'make sure', or 'it's important to'; start with the action.
26. Use autonomy-supportive phrasing only when a real safe choice exists; if so, offer at most two practical options, and only when both are safe and materially equivalent.
27. Replace generic motivation, scripted empathy, and empty safety language with concrete next-action coaching.
28. Do not use generic motivation such as 'stay consistent', 'trust the process', 'push yourself', or 'you've got this'.
29. Do not use empty safety language such as 'listen to your body', 'be careful', or 'avoid overtraining' unless it adds a concrete rule, symptom trigger, or plan change.
30. If fatigue is high or fight-week pressure is active, reduce optionality and make the safest performance-preserving call plainly.
31. If injury management is active, lead with constraints, substitutions, or stop rules rather than optional language.
32. If active weight cut is present, keep the language shorter, safety-first, and non-negotiable about recovery margin.
33. Aim critique at the plan, load, or execution issue, never at the athlete's character.
34. Reduce repeated openers, labels, and filler reminders so the repaired plan reads like a final coach prescription, not a template.
35. If late_fight_plan_spec is present, treat its session cap, meaningful-stress cap, max_blocks_per_session, and forbidden_blocks as hard constraints.
36. In late-fight windows, do not restore suppressed roles just to make the plan feel like a normal week; stripped-down D-6/D-5 structures are intentional.
37. In late-fight windows, remove forbidden content instead of downgrading it into a disguised build session.
38. For D-1 and D-0, keep the output minimal and execution-focused; do not re-expand into a layered session menu.

OUTPUT:
Return only the revised athlete-facing final plan."""


def _json_block(value: dict | list) -> str:
    return "```json\n" + json.dumps(value, indent=2) + "\n```"



def _build_revision_priorities(validator_report: dict) -> dict[str, list[dict]]:
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
                "candidate_names": clean_list(item.get("candidate_names", [])),
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
                    "anchor_candidates": clean_list(warning.get("anchor_candidates", [])),
                }
            )
        elif code == "support_takeover_before_anchor":
            quality_fixes.append(
                {
                    "action": "move_support_work_after_anchor",
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                    "anchor_candidates": clean_list(warning.get("anchor_candidates", [])),
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
                    "required_equipment": clean_list(warning.get("required_equipment", [])),
                }
            )
        elif code == "missing_week_session_role":
            quality_fixes.append(
                {
                    "action": "restore_missing_week_structure",
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "expected_roles": clean_list(warning.get("expected_roles", [])),
                    "expected_role_days": list(warning.get("expected_role_days") or []),
                }
            )
        elif code == "late_camp_session_incomplete":
            quality_fixes.append(
                {
                    "action": "complete_late_camp_week",
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "expected_roles": clean_list(warning.get("expected_roles", [])),
                    "expected_role_days": list(warning.get("expected_role_days") or []),
                }
            )
        elif code == "weekly_session_overage":
            quality_fixes.append(
                {
                    "action": "trim_extra_week_sessions_to_match_profile",
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "expected_session_count": warning.get("expected_session_count"),
                    "actual_session_count": warning.get("actual_session_count"),
                }
            )
        elif code == "weekly_rhythm_broken":
            quality_fixes.append(
                {
                    "action": "restore_default_boxer_weekly_rhythm",
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
                    "summary_lines": clean_list(warning.get("summary_lines", [])),
                    "support_lines": clean_list(warning.get("support_lines", [])),
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
                    "risk_context": clean_list(warning.get("risk_context", [])),
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
                    "risk_context": clean_list(warning.get("risk_context", [])),
                }
            )
        elif code == "late_fight_forbidden_content":
            quality_fixes.append(
                {
                    "action": "remove_late_fight_forbidden_block",
                    "forbidden_block": warning.get("forbidden_block"),
                    "line": warning.get("line"),
                    "matched_lines": clean_list(warning.get("matched_lines", [])),
                }
            )
        elif code == "late_fight_block_overage":
            quality_fixes.append(
                {
                    "action": "trim_late_fight_session_to_block_ceiling",
                    "session_index": warning.get("session_index"),
                    "line": warning.get("line"),
                    "max_blocks_per_session": warning.get("max_blocks_per_session"),
                    "actual_block_count": warning.get("actual_block_count"),
                }
            )
        elif code == "late_fight_meaningful_stress_overage":
            quality_fixes.append(
                {
                    "action": "reduce_late_fight_meaningful_stress_exposures",
                    "actual_exposures": warning.get("actual_exposures"),
                    "max_meaningful_stress_exposures": warning.get("max_meaningful_stress_exposures"),
                    "exposures": list(warning.get("exposures") or []),
                }
            )
        elif code == "late_fight_active_role_overage":
            quality_fixes.append(
                {
                    "action": "trim_late_fight_sessions_to_cap",
                    "actual_sessions": warning.get("actual_sessions"),
                    "max_active_roles": warning.get("max_active_roles"),
                }
            )
        elif code == "late_fight_hard_sparring_overage":
            quality_fixes.append(
                {
                    "action": "remove_extra_late_fight_hard_sparring_exposures",
                    "days_out_bucket": warning.get("days_out_bucket"),
                    "hard_sparring_sessions": list(warning.get("hard_sparring_sessions") or []),
                }
            )
    return {
        "fix_first": restriction_fixes,
        "strip_out": formatting_fixes,
        "then_restore": missing_elements,
        "quality_repairs": quality_fixes,
    }



def build_stage2_repair_prompt(*, planning_brief: dict, failed_plan_text: str, validator_report: dict) -> str:
    revision_priorities = _build_revision_priorities(validator_report)
    sections = [
        REPAIR_PROMPT_TEMPLATE.strip(),
        "REVISION PRIORITIES\n" + _json_block(revision_priorities),
        "VALIDATOR REPORT\n" + _json_block(validator_report),
        "PLANNING BRIEF\n" + _json_block(planning_brief),
        "PREVIOUS FINAL PLAN\n" + (failed_plan_text or "").strip(),
    ]
    return "\n\n---\n\n".join(section for section in sections if section.strip())
