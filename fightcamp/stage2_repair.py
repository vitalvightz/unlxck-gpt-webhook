from __future__ import annotations
from .normalization import clean_list
from .stage2_policy import prompt_safe_validator_report

import json
from difflib import SequenceMatcher
import re


REPAIR_PROMPT_TEMPLATE = """You are revising a Stage 2 final plan after validation.

GOAL:
Repair the previous final plan so it becomes restriction-compliant, phase-consistent, and coherent with the planning brief.

REPAIR RULES:
1. Treat restrictions as hard constraints. Remove violating items rather than softening them into compliance. For a role with selected_exercise_assignments, a violating selected exercise may be removed/held but must never be replaced downstream; for roles without selected_exercise_assignments, replacement with a compliant same-role option remains allowed.
2. Fix hard blocker findings first.
3. Preserve compliant parts of the previous final plan when they still fit the planning brief.
3A. CLOSED MEMBERSHIP PRECEDENCE: when a role carries selected_exercise_assignments, that list is the deterministic planner's closed session membership. It overrides every repair rule below that mentions candidate pools, alternates, restoration, replacement, stronger options, or substitutions. Repair may remove an illegal selected exercise or lower its dose, but it must not add, restore, replace, or substitute any S&C exercise outside the selected set. If removal leaves a gap, leave the gap; selection belongs upstream.
3B. MEMBERSHIP IS CLOSED, DOSING IS NOT: a selected exercise that carries no effective prescription still has to be rendered with a real dose. Prescribe one from the athlete profile and the scheduled day (phase, countdown day, fatigue, weight cut, injury context, status, equipment), staying inside any dose cap the planning brief supplies. Never leave a scheduled exercise dose-less, and never render a DOSE_UNRESOLVED marker into athlete-facing text. This licenses dosing only; rule 3A still forbids changing membership.
4. Only for roles without selected_exercise_assignments, use candidate pools and same-role alternates from the planning brief before inventing anything new.
5. If a phase-critical element is missing, restore an already-selected legal exercise when the role has selected_exercise_assignments. Only roles without selected_exercise_assignments may reintroduce the element with a conservative, compliant option that matches the phase strategy.
6. Remove any internal/admin scaffolding such as Athlete Profile, Selection Rationale, Coach Notes, planning-brief labels, or Stage-2-only notes.
7. Remove raw HTML, code fences, and any non-athlete formatting artifacts.
8. If an anchor session drifted into support work, restore a selected anchor when the role has selected_exercise_assignments. Only roles without selected_exercise_assignments may choose the strongest compliant anchor option available before accessories.
9. In non-taper weeks, preserve a selected externally loaded high-transfer anchor when legal. Only roles without selected_exercise_assignments may restore or substitute a different externally loaded anchor; if none exists, label the week injury-limited and keep the safest force-preserving option already authorised by the planning brief.
10. For a role with selected_exercise_assignments, render every selected conditioning exercise and its effective prescription. Do not collapse selected membership into one primary exercise or a fallback. Only roles without closed membership may resolve an open conditioning choice to one primary prescription and at most one explicit fallback.
11. Collapse menu-like session templates into one final prescription whenever the athlete context already resolves the choice.
12. Keep all primary drills, support drills, and fallbacks equipment-valid for the athlete profile. Equipment invalidity never authorises a substitute for a role with selected_exercise_assignments; remove/hold the invalid selected item instead.
13. Keep every active week present and structurally complete, especially the late-camp weeks.
14. Preserve the default boxer weekly rhythm of support strength, low-damage conditioning, recovery, primary strength, then the main phase-specific conditioning stressor unless a higher-order planning rule forces a different order.
15. Do not create more active weekly sessions than the weekly_role_map allows. If the athlete has extra available days, leave them off or clearly optional rather than turning them into extra training days.
16. If weekly_role_map or week_by_week_progression marks intentional_compression.active, keep that smaller week on purpose and do not restore the suppressed standalone role.
17. If a week contains intentionally_unused_days entries with role off_day or recovery_only_day, leave those days as light recovery or completely off unless weekly_role_map.session_roles already includes an explicit converted low-load support role on that same day (for example recovery_aerobic_gas_tank_day or converted_low_aerobic_gas_tank_day). Do not invent new active sessions on unused days.
18. Treat declared hard sparring days in weekly_role_map as immutable hard_sparring_day slots. Hard sparring days are the athlete's own combat locks (run in their gym, with or without a coach): the app does not prescribe or lead the sparring itself, and it must respect resolved safety, readiness, and calendar restrictions on every declared hard sparring day. The app never deloads, caps, or drops a declared hard sparring day merely to create S&C capacity; only the explicit safety conversion rules below may change contact status. Only for a resolved hard-as-planned day render the minimal label "Hard sparring — controlled hard contact" (or the equivalent sport-specific label such as "MMA — hard sparring / controlled hard contact") followed by exactly one short note: "Your declared hard-sparring/contact session — no extra S&C. Keep freshness priority." From D-14 normally, or D-17 with elevated risk, hard sparring is converted to technical work: render "Technical-only combat" (or sport-equivalent) — the same applies whenever the day carries reason code "d14_hard_sparring_ban" or "d17_hard_sparring_ban" — followed by exactly one short note: "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority." A technical-only day must never carry the hard-sparring note. A blocked/none contact status overrides all declarations and dates: no contact or sparring; surface medical evaluation/clearance guidance and do not restore contact. Do not output round counts, time-x-rounds formulas, intensity targets, dose, RPE, work:rest, or any sparring template wording (e.g. never "6-8 x 3-min rounds at set intensity", "X rounds technical sparring", "live rounds at moderate intensity"). Nothing else — no programmed S&C is scheduled on a declared hard-sparring/contact day. Never say "coach-led" or "coach-owned" in athlete-facing text. If the previous plan rendered rounds, intensity, dose, or template sparring detail, strip it down to this minimal form.
19. If weekly_role_map.intentional_compression.policy is boxing_crowded_week, keep hard sparring as the week owner, preserve at most one anchor and one low-load support day, and cut accessory, transfer, glycolytic, and optional alactic extras before touching the anchor.
20. In boxing crowded weeks, anchor days and recovery/support days cannot pick up a second meaningful stressor. Strip the extra stressor instead of redistributing it across the week.
21. In taper weeks, keep the work short, direct, and low-noise with minimal branching.
22. Keep the final output athlete-facing. Do not mention the validator, the repair process, or rejected items.
23. If a target-weight constraint shaped the plan, acknowledge it plainly in the athlete-facing output.
24. For high-pressure cuts, include one short summary-level note and one short support-level note without turning the plan into a long weight-cut essay.
25. For any corrective or adjustment line, make one clear coaching call with a short why tied to performance, safety, readiness, or the week's main objective.
26. Prefer command then reason on corrective lines; do not lead with explanation and then soften it into a suggestion.
27. Do not open corrective lines with generic openers such as 'focus on', 'ensure', 'make sure', or 'it's important to'; start with the action.
28. Use autonomy-supportive phrasing only when a real safe choice exists; if so, offer at most two practical options, and only when both are safe and materially equivalent.
29. Replace generic motivation, scripted empathy, and empty safety language with concrete next-action coaching.
30. Do not use generic motivation such as 'stay consistent', 'trust the process', 'push yourself', or 'you've got this'.
31. Do not use empty safety language such as 'listen to your body', 'be careful', or 'avoid overtraining' unless it adds a concrete rule, symptom trigger, or plan change.
32. If fatigue is high or fight-week pressure is active, reduce optionality and make the safest performance-preserving call plainly.
33. If injury management is active, lead with constraints, substitutions, or stop rules rather than optional language. Closed membership still controls S&C exercise identity.
34. Do not prescribe exercises the plan already marks as avoid/contraindicated for the athlete's injury status.
35. If a target-weight constraint is present, keep the language shorter, safety-first, and non-negotiable about recovery margin.
36. Aim critique at the plan, load, or execution issue, never at the athlete's character.
37. Reduce repeated openers, labels, and filler reminders so the repaired plan reads like a final coach prescription, not a template.
38. If late_fight_plan_spec is present, treat its session cap, meaningful-stress cap, max_blocks_per_session, and forbidden_blocks as hard constraints.
39. In late-fight windows, do not restore suppressed roles just to make the plan feel like a normal week; stripped-down D-6/D-5 structures are intentional.
40. In late-fight windows, remove forbidden content instead of downgrading it into a disguised build session.
41. For D-1 and D-0, keep the output minimal and execution-focused; do not re-expand into a layered session menu.
42. D-1 is equipment-free: never render band, med-ball, bag, mitt, weight, or any other equipment-based work on D-1 — breathing, mobility, and light technical shadowboxing only.

OUTPUT:
Return only the revised athlete-facing final plan."""


def _json_block_pretty(value: dict | list) -> str:
    """JSON block with indentation — used in repair prompts for human readability."""
    return "```json\n" + json.dumps(value, indent=2) + "\n```"


def reconcile_selected_conditioning_assignments(
    *,
    planning_brief: dict,
    failed_plan_text: str,
    validator_report: dict,
) -> dict:
    """Restore omitted closed-membership conditioning lines in place.

    The authoritative role assignment is the only source.  Reconciliation is
    deliberately refused when the target day is absent/duplicated, the source
    assignment is ambiguous or incomplete, or the selected line itself matches
    an athlete restriction.  No calendar structure or substitute is invented.
    """
    from .planner_authority_integrity import (
        PLANNER_AUTHORITY_BLOCKER_CODES,
        planner_authority_findings,
    )
    from .stage2_pipeline import structural_integrity_findings
    from .stage2_validator import (
        _COUNTDOWN_LABEL_LINE,
        _countdown_blocks,
        _find_restricted_hits,
        _is_countdown_block_boundary,
    )

    missing = [
        dict(item)
        for field in ("errors", "blocking_warnings")
        for item in validator_report.get(field, []) or []
        if isinstance(item, dict)
        and str(item.get("code") or "") in {
            "missing_selected_conditioning_assignment",
            "selected_conditioning_effective_prescription_mismatch",
        }
    ]
    if not missing:
        return {"text": failed_plan_text, "applied": [], "unresolved": []}

    if structural_integrity_findings(validator_report):
        return {
            "text": failed_plan_text,
            "applied": [],
            "unresolved": [
                {
                    "code": "conditioning_render_repair_structurally_unsafe",
                    "message": "Canonical week/day structure is unresolved; conditioning was not restored.",
                }
            ],
        }

    authority_blockers = [
        item
        for item in planner_authority_findings(planning_brief)
        if str(item.get("code") or "") in PLANNER_AUTHORITY_BLOCKER_CODES
    ]
    blocks_by_day: dict[int, list[dict]] = {}
    for block in _countdown_blocks(failed_plan_text):
        blocks_by_day.setdefault(int(block["day"]), []).append(block)

    roles_by_identity: dict[tuple[int, str], list[tuple[dict, dict]]] = {}
    from .stage2_validator import _scheduled_role_d_day

    for week in (planning_brief.get("weekly_role_map") or {}).get("weeks") or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict) or str(role.get("category") or "").lower() != "conditioning":
                continue
            d_day = _scheduled_role_d_day(week, role)
            if d_day is None:
                continue
            for assignment in role.get("selected_exercise_assignments") or []:
                if not isinstance(assignment, dict):
                    continue
                name = str(assignment.get("name") or "").strip()
                if name:
                    roles_by_identity.setdefault((d_day, name.casefold()), []).append((role, assignment))

    insertions: dict[str, list[str]] = {}
    replacements: dict[str, str] = {}
    applied: list[dict] = []
    unresolved: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for finding in missing:
        try:
            d_day = int(finding.get("scheduled_d_day"))
        except (TypeError, ValueError):
            d_day = -1
        name = str(finding.get("exercise") or "").strip()
        identity = (d_day, name.casefold())
        if identity in seen:
            continue
        seen.add(identity)
        sources = roles_by_identity.get(identity, [])
        blocks = blocks_by_day.get(d_day, [])
        if len(sources) != 1 or len(blocks) != 1:
            unresolved.append({**finding, "reason": "ambiguous_or_missing_authoritative_day"})
            continue
        role, assignment = sources[0]
        prescription = str(assignment.get("effective_prescription") or "").strip()
        if not prescription:
            unresolved.append({**finding, "reason": "missing_effective_prescription"})
            continue
        if any(
            str(item.get("exercise") or "").casefold() == name.casefold()
            and str(item.get("role_key") or "") == str(role.get("role_key") or "")
            for item in authority_blockers
        ):
            unresolved.append({**finding, "reason": "planner_authority_failure"})
            continue
        line = f"- {name}: {prescription}"
        if _find_restricted_hits(planning_brief, [line]):
            unresolved.append({**finding, "reason": "selected_assignment_restricted"})
            continue
        header = str(blocks[0].get("header") or "")
        if str(finding.get("code") or "") == "selected_conditioning_effective_prescription_mismatch":
            rendered_line = str(finding.get("rendered_line") or "").strip()
            if not rendered_line:
                unresolved.append({**finding, "reason": "missing_rendered_dose_line"})
                continue
            replacements[rendered_line] = line
        else:
            insertions.setdefault(header, []).append(line)
        applied.append(
            {
                "action": "render_selected_conditioning_assignment",
                "scheduled_d_day": d_day,
                "role_key": role.get("role_key"),
                "exercise": name,
                "effective_prescription": prescription,
            }
        )

    if not insertions and not replacements:
        return {"text": failed_plan_text, "applied": applied, "unresolved": unresolved}

    lines = str(failed_plan_text or "").splitlines()
    for rendered_line, replacement in replacements.items():
        indexes = [index for index, line in enumerate(lines) if line.strip() == rendered_line]
        if len(indexes) != 1:
            unresolved.append(
                {
                    "code": "selected_conditioning_effective_prescription_mismatch",
                    "rendered_line": rendered_line,
                    "reason": "ambiguous_rendered_dose_line",
                }
            )
            applied = [item for item in applied if item.get("exercise") not in replacement]
            continue
        lines[indexes[0]] = replacement
    pending: list[tuple[int, list[str]]] = []
    for header, new_lines in insertions.items():
        header_indexes = [index for index, line in enumerate(lines) if line.strip() == header]
        if len(header_indexes) != 1:
            unresolved.extend(
                {**item, "reason": "ambiguous_rendered_day_header"}
                for item in applied
                if item.get("scheduled_d_day") == int(re.search(r"D-(\d+)", header, re.I).group(1))
            )
            applied = [item for item in applied if item.get("scheduled_d_day") != int(re.search(r"D-(\d+)", header, re.I).group(1))]
            continue
        insert_at = header_indexes[0] + 1
        while insert_at < len(lines):
            stripped = lines[insert_at].strip()
            if stripped and (_COUNTDOWN_LABEL_LINE.match(stripped) or _is_countdown_block_boundary(stripped)):
                break
            insert_at += 1
        pending.append((insert_at, new_lines))

    for insert_at, new_lines in sorted(pending, reverse=True):
        lines[insert_at:insert_at] = new_lines
    return {"text": "\n".join(lines), "applied": applied, "unresolved": unresolved}


def conditioning_render_repair_integrity_findings(
    *, planning_brief: dict, before_text: str, after_text: str
) -> list[dict]:
    """Allow only inserts/corrections of source-authorised conditioning lines."""
    from .stage2_validator import (
        _countdown_blocks,
        _conditioning_dose_within_bounds,
        _is_countdown_block_boundary,
        _line_has_exercise,
        _scheduled_role_d_day,
        _COUNTDOWN_LABEL_LINE,
    )

    assignments_by_day: dict[int, list[dict]] = {}
    for week in (planning_brief.get("weekly_role_map") or {}).get("weeks") or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict) or str(role.get("category") or "").lower() != "conditioning":
                continue
            assignments = [
                item
                for item in role.get("selected_exercise_assignments") or []
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ]
            d_day = _scheduled_role_d_day(week, role)
            if d_day is None or not assignments:
                continue
            assignments_by_day.setdefault(d_day, []).extend(assignments)

    def day_context(lines: list[str]) -> dict[int, int | None]:
        current_day: int | None = None
        contexts: dict[int, int | None] = {}
        for index, line in enumerate(lines):
            stripped = line.strip()
            match = _COUNTDOWN_LABEL_LINE.match(stripped)
            if match:
                current_day = int(match.group(2))
            elif stripped and _is_countdown_block_boundary(stripped):
                current_day = None
            contexts[index] = current_day
        return contexts

    def authorised_assignment(line: str, d_day: int | None) -> dict | None:
        if d_day is None:
            return None
        matches = [
            assignment
            for assignment in assignments_by_day.get(d_day, [])
            if _line_has_exercise(line, str(assignment.get("name") or ""))
        ]
        return matches[0] if len(matches) == 1 else None

    def permitted_new_line(line: str, d_day: int | None) -> tuple[bool, dict | None]:
        assignment = authorised_assignment(line, d_day)
        if not assignment:
            return False, None
        dose_ok, _, _, _ = _conditioning_dose_within_bounds(
            str(assignment.get("effective_prescription") or ""), line
        )
        return dose_ok, assignment

    before_lines = str(before_text or "").splitlines()
    after_lines = str(after_text or "").splitlines()
    before_context = day_context(before_lines)
    after_context = day_context(after_lines)
    findings: list[dict] = []

    for tag, before_start, before_end, after_start, after_end in SequenceMatcher(
        a=before_lines, b=after_lines, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        before_chunk = before_lines[before_start:before_end]
        after_chunk = after_lines[after_start:after_end]

        if tag == "insert":
            for offset, line in enumerate(after_chunk):
                index = after_start + offset
                allowed, _ = permitted_new_line(line, after_context[index])
                if not allowed:
                    findings.append(
                        {
                            "code": "conditioning_render_repair_unapproved_edit",
                            "severity": "blocker",
                            "edit": "insert",
                            "scheduled_d_day": after_context[index],
                            "line": line,
                            "message": "Render repair inserted content outside authorised conditioning membership.",
                        }
                    )
            continue

        if tag == "delete":
            for offset, line in enumerate(before_chunk):
                index = before_start + offset
                findings.append(
                    {
                        "code": "conditioning_render_repair_unapproved_edit",
                        "severity": "blocker",
                        "edit": "delete",
                        "scheduled_d_day": before_context[index],
                        "line": line,
                        "message": "Render repair deleted existing plan content.",
                    }
                )
            continue

        # A correction must be one-for-one, stay on the same D-day, and retain
        # the exact selected exercise identity. Any other rewrite is rejected.
        if len(before_chunk) != len(after_chunk):
            findings.append(
                {
                    "code": "conditioning_render_repair_unapproved_edit",
                    "severity": "blocker",
                    "edit": "replace",
                    "before": before_chunk,
                    "after": after_chunk,
                    "message": "Render repair rewrote unrelated plan structure or content.",
                }
            )
            continue
        for offset, (old_line, new_line) in enumerate(zip(before_chunk, after_chunk)):
            old_index = before_start + offset
            new_index = after_start + offset
            old_assignment = authorised_assignment(old_line, before_context[old_index])
            allowed, new_assignment = permitted_new_line(new_line, after_context[new_index])
            if (
                not allowed
                or not old_assignment
                or before_context[old_index] != after_context[new_index]
                or str(old_assignment.get("name") or "").casefold()
                != str(new_assignment.get("name") or "").casefold()
            ):
                findings.append(
                    {
                        "code": "conditioning_render_repair_unapproved_edit",
                        "severity": "blocker",
                        "edit": "replace",
                        "scheduled_d_day": after_context[new_index],
                        "before": old_line,
                        "after": new_line,
                        "message": "Render repair changed content outside an authorised conditioning correction.",
                    }
                )

    # Keep the existing parser-backed guard for accidental duplicate selected
    # lines, including duplicates inserted outside a SequenceMatcher hunk.
    for block in _countdown_blocks(after_text):
        d_day = int(block["day"])
        for assignment in assignments_by_day.get(d_day, []):
            name = str(assignment.get("name") or "")
            if sum(_line_has_exercise(line, name) for line in block.get("lines") or []) > 1:
                findings.append(
                    {
                        "code": "duplicate_selected_conditioning_assignment",
                        "severity": "blocker",
                        "scheduled_d_day": d_day,
                        "exercise": name,
                        "message": "Render repair duplicated a selected conditioning assignment.",
                    }
                )
    return findings


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
        elif code == "crowded_week_non_spar_overage":
            quality_fixes.append(
                {
                    "action": "trim_crowded_week_to_anchor_plus_support_budget",
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "actual_non_spar_sessions": warning.get("actual_non_spar_sessions"),
                    "max_non_spar_roles": warning.get("max_non_spar_roles"),
                    "risk_signals": clean_list(warning.get("risk_signals", [])),
                }
            )
        elif code == "anchor_day_identity_overload":
            quality_fixes.append(
                {
                    "action": "strip_extra_stress_from_anchor_day",
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                    "line": warning.get("line"),
                    "matched_lines": clean_list(warning.get("matched_lines", [])),
                    "matched_tokens": clean_list(warning.get("matched_tokens", [])),
                }
            )
        elif code == "support_recovery_day_stress_leak":
            quality_fixes.append(
                {
                    "action": "restore_support_day_to_low_load_only",
                    "week_index": warning.get("week_index"),
                    "phase": warning.get("phase"),
                    "session_index": warning.get("session_index"),
                    "line": warning.get("line"),
                    "matched_lines": clean_list(warning.get("matched_lines", [])),
                    "matched_tokens": clean_list(warning.get("matched_tokens", [])),
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
    # Late-camp effective-prescription blockers arrive as hard-blocker errors (and
    # are promoted into blocking_warnings by the release policy). Membership and
    # dose are different repair classes: an unselected exercise is removed, while
    # an authorised exercise with excessive dose is reduced to its effective cap.
    seen_effective_findings: set[tuple[object, ...]] = set()
    for finding in [
        *(validator_report.get("errors", []) or []),
        *(validator_report.get("blocking_warnings", []) or []),
    ]:
        if not isinstance(finding, dict):
            continue
        if str(finding.get("code") or "") != "late_camp_effective_prescription_exceeded":
            continue
        line = str(finding.get("line") or "")
        dimensions = tuple(str(value) for value in (finding.get("violation_dimensions") or ()))
        identity = (
            finding.get("scheduled_d_day"),
            finding.get("rendered_exercise") or finding.get("exercise"),
            line,
            dimensions,
        )
        if identity in seen_effective_findings:
            continue
        seen_effective_findings.add(identity)

        if (
            "exercise_allow_list" in dimensions
            or finding.get("effective_prescription") == "no loaded lifting"
        ):
            quality_fixes.append(
                {
                    "action": "remove_unselected_exercise",
                    "line": finding.get("line"),
                    "scheduled_d_day": finding.get("scheduled_d_day"),
                    "rendered_exercise": finding.get("rendered_exercise") or finding.get("exercise"),
                    "allowed_exercises": clean_list(finding.get("allowed_exercises", [])),
                    "reason": "closed_session_membership",
                    "replacement_allowed": False,
                }
            )
            continue

        quality_fixes.append(
            {
                "action": "reduce_strength_dose_to_effective_prescription",
                "line": finding.get("line"),
                "scheduled_d_day": finding.get("scheduled_d_day"),
                "exercise": finding.get("exercise"),
                "effective_max_sets": finding.get("effective_max_sets"),
                "effective_max_reps": finding.get("effective_max_reps"),
                "effective_rpe_cap": finding.get("effective_rpe_cap"),
                "effective_prescription": finding.get("effective_prescription"),
            }
        )

    for finding in [
        *(validator_report.get("errors", []) or []),
        *(validator_report.get("blocking_warnings", []) or []),
    ]:
        if not isinstance(finding, dict) or str(finding.get("code") or "") not in {
            "missing_selected_conditioning_assignment",
            "selected_conditioning_effective_prescription_mismatch",
        }:
            continue
        quality_fixes.append(
            {
                "action": (
                    "render_selected_conditioning_assignment"
                    if str(finding.get("code") or "") == "missing_selected_conditioning_assignment"
                    else "restore_selected_conditioning_effective_prescription"
                ),
                "scheduled_d_day": finding.get("scheduled_d_day"),
                "exercise": finding.get("exercise"),
                "effective_prescription": finding.get("effective_prescription"),
                "replacement_allowed": False,
            }
        )

    return {
        "fix_first": restriction_fixes,
        "strip_out": formatting_fixes,
        "then_restore": missing_elements,
        "quality_repairs": quality_fixes,
    }



def build_stage2_repair_prompt(*, planning_brief: dict, failed_plan_text: str, validator_report: dict) -> str:
    validator_report = prompt_safe_validator_report(validator_report)
    revision_priorities = _build_revision_priorities(validator_report)
    sections = [
        REPAIR_PROMPT_TEMPLATE.strip(),
        "REVISION PRIORITIES\n" + _json_block_pretty(revision_priorities),
        "VALIDATOR REPORT\n" + _json_block_pretty(validator_report),
        "PLANNING BRIEF\n" + _json_block_pretty(planning_brief),
        "PREVIOUS FINAL PLAN\n" + (failed_plan_text or "").strip(),
    ]
    return "\n\n---\n\n".join(section for section in sections if section.strip())
