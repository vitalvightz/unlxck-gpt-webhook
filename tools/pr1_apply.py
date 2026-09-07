"""One-time pinned-source integration for PR1. Removed after CI passes."""
from __future__ import annotations

import ast
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path, before, after):
    p = ROOT / path
    text = p.read_text()
    if text.count(before) != 1:
        raise RuntimeError(f"{path}: expected exactly one source anchor, found {text.count(before)}")
    p.write_text(text.replace(before, after, 1))


def replace_function(path, name, replacement):
    p = ROOT / path
    text = p.read_text()
    nodes = [n for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(nodes) != 1:
        raise RuntimeError(f"{path}: expected one {name}")
    node = nodes[0]
    lines = text.splitlines(keepends=True)
    original = ''.join(lines[node.lineno-1:node.end_lineno])
    updated = textwrap.dedent(replacement).strip() + '\n'
    p.write_text(text.replace(original, updated, 1))

replace_function('fightcamp/stage2_pipeline.py', 'build_stage2_retry', '''
def build_stage2_retry(
    *, stage1_result: dict, final_plan_text: str,
    validator_report: dict | None = None,
) -> dict:
    """Keep rendering repair independent of deterministic planner repair."""
    from .conditioning_render_repair import (
        MISSING_CODE, PLANNER_CODES, RENDER_CODES, findings,
        selected_missing_assignments, build_conditioning_repair_prompt,
    )
    stage1_result = _require_dict(stage1_result, name="stage1_result")
    planning_brief = _require_dict(_require_stage1_field(stage1_result, "planning_brief"), name="planning_brief")
    if validator_report is None:
        validator_report = review_stage2_output(
            planning_brief=planning_brief, final_plan_text=final_plan_text,
        )["validator_report"]
    else:
        validator_report = apply_stage2_release_policy(
            _enrich_validator_report(_require_dict(validator_report, name="validator_report"))
        )
    status = _review_status(validator_report)
    summary, summary_lines = _build_review_summary(validator_report, status)
    planner_failures = findings(validator_report, PLANNER_CODES)
    requires_planner = bool(planner_failures or validator_report.get("planner_preflight_failed"))
    render_findings = findings(validator_report, RENDER_CODES)
    missing = [item for item in render_findings if item.get("code") == MISSING_CODE]
    assignments, unresolved = selected_missing_assignments(planning_brief, validator_report)
    repair_prompt = None
    if unresolved:
        requires_planner = True
        validator_report = dict(validator_report)
        validator_report["errors"] = [*(validator_report.get("errors") or []), {
            "code": "missing_selected_conditioning_authority",
            "message": "A missing conditioning assignment has no unique, complete effective source.",
            "details": unresolved,
        }]
    elif render_findings and not validator_report.get("planner_preflight_failed"):
        if missing:
            repair_prompt = build_conditioning_repair_prompt(
                planning_brief=planning_brief, failed_plan_text=final_plan_text,
                validator_report=validator_report, assignments=assignments,
            )
        else:
            repair_prompt = build_stage2_repair_prompt(
                planning_brief=planning_brief, failed_plan_text=final_plan_text,
                validator_report=prompt_safe_validator_report(validator_report),
            )
    elif not requires_planner and validator_report.get("release_decision") == "hold":
        repair_prompt = build_stage2_repair_prompt(
            planning_brief=planning_brief, failed_plan_text=final_plan_text,
            validator_report=prompt_safe_validator_report(validator_report),
        )
    return {
        "status": status,
        "validator_report": validator_report,
        "summary": summary,
        "summary_lines": summary_lines,
        "needs_retry": bool(repair_prompt),
        "requires_planner_regeneration": requires_planner,
        "repair_prompt": repair_prompt,
        "render_repair_findings": render_findings,
        "unresolved_render_authority": unresolved,
    }
''')

replace_once('fightcamp/stage2_policy.py',
    '    if not normalized or normalized in _REPAIR_PROMPT_EXCLUDED_CODES:\n',
    '    if normalized == "missing_selected_conditioning_assignment":\n        return True\n    if not normalized or normalized in _REPAIR_PROMPT_EXCLUDED_CODES:\n')
replace_once('fightcamp/stage2_repair.py',
    '11. Collapse menu-like session templates into one final prescription whenever the athlete context already resolves the choice.',
    '11. Collapse menu-like templates into one resolved prescription per selected exercise. Never collapse closed multi-exercise membership into one drill.')
replace_once('fightcamp/stage2_payload.py',
    'Cut novelty, reduce accessory volume, avoid density. Keep only sharpness, rhythm, confidence, and freshness. One final prescription per session — no option menus.',
    'Cut novelty, reduce accessory volume, avoid density. Keep only sharpness, rhythm, confidence, and freshness. One resolved prescription per selected exercise — no option menus. Never collapse closed multi-exercise membership into one drill.')

# Preserve the existing automation, persistence, cost, and structured-card flow.
p = ROOT / 'api/stage2_automation.py'
text = p.read_text()
needle = 'from fightcamp.goal_preservation import validate_goal_preservation\n'
assert text.count(needle) == 1
text = text.replace(needle, needle + '''from fightcamp.conditioning_render_repair import (
    MISSING_CODE, PLANNER_CODES, RENDER_CODES, findings,
    mandatory_release_report, selected_missing_assignments,
)
''', 1)
text = text.replace('        report = apply_stage2_release_policy({\n',
                    '        report = mandatory_release_report({\n', 1)
start = text.index('    async def finalize(\n', text.index('class OpenAIStage2Automator'))
end = text.index('\n    async def ', start + 10) if '\n    async def ' in text[start + 10:] else len(text)
source = text[start:end]
source = source.replace('return {**review, "validator_report": apply_stage2_release_policy(report)}',
                        'return {**review, "validator_report": mandatory_release_report(report)}')
a = source.index('        # Effective-dose violations are deterministic safety failures.')
b = source.index('        quality_findings = athlete_release_with_flags_findings', a)
source = source[:a] + '''        # Repair only selected, source-backed rendering omissions. Genuine
        # planner failures remain independent and cannot be cleared by prose.
        original_review_report = dict(first_review["validator_report"])
        original_text = first_pass_text
        original_cost = first_pass_cost
        repair_audit = {"status": "not_needed", "attempted_text": ""}
        render_findings = findings(original_review_report, RENDER_CODES)
        if render_findings and not first_pass_cost.get("stage2_incomplete_response"):
            retry = build_stage2_retry(
                stage1_result=stage1_result, final_plan_text=first_pass_text,
                validator_report=original_review_report,
            )
            retry_text = str(retry.get("repair_prompt") or "")
            if retry.get("needs_retry") and retry_text:
                try:
                    candidate, repair_cost = await self._generate_text(
                        retry_text, attempt_label="effective_dose_repair",
                        source=source, log_context=log_context,
                    )
                except Stage2AutomationError as exc:
                    attempt_count = 2
                    final_cost = exc.stage2_cost or {}
                    repair_audit["status"] = "model_request_failed"
                    repair_audit["error"] = str(exc)
                else:
                    attempt_count = 2
                    final_cost = repair_cost
                    repair_audit["attempted_text"] = candidate
                    if repair_cost.get("stage2_incomplete_response"):
                        repair_audit["status"] = "model_incomplete"
                    else:
                        candidate_review = reviewed_report(review_stage2_output(
                            planning_brief=package["planning_brief"], final_plan_text=candidate,
                        ))
                        candidate_report = candidate_review["validator_report"]
                        if findings(candidate_report, RENDER_CODES):
                            repair_audit["status"] = "render_findings_remain"
                        else:
                            final_text = candidate
                            first_review = candidate_review
                            repair_audit["status"] = "applied"
            else:
                repair_audit["status"] = "planner_or_authority_required"
                repair_audit["unresolved"] = retry.get("unresolved_render_authority") or []
                if retry.get("requires_planner_regeneration"):
                    report = dict(first_review["validator_report"])
                    report["errors"] = [*(report.get("errors") or []), {
                        "code": "missing_selected_conditioning_authority",
                        "message": "Selected conditioning rendering requires deterministic planner repair.",
                        "details": retry.get("unresolved_render_authority") or [],
                    }]
                    first_review = reviewed_report({**first_review, "validator_report": report})
        plan_text_cost = (
            _merge_stage2_costs(original_cost, final_cost)
            if attempt_count == 2 else original_cost
        )
        if attempt_count == 2:
            plan_text_cost["stage2_attempt_count"] = 2
            first_review["validator_report"]["repair_source_report"] = original_review_report
        if repair_audit["status"] in {"model_request_failed", "model_incomplete", "render_findings_remain"}:
            # A failed repair is not an authority to replace the original plan.
            final_text = original_text
            report = dict(original_review_report)
            report["render_repair_failure"] = repair_audit
            first_review = reviewed_report({**first_review, "status": "FAIL", "validator_report": report})
        if final_cost.get("stage2_incomplete_response") and attempt_count == 1:
            report = dict(first_review["validator_report"])
            report["errors"] = [*(report.get("errors") or []), {
                "code": "stage2_output_truncated",
                "message": "Provider marked the final Stage 2 response incomplete.",
            }]
            first_review = reviewed_report({**first_review, "validator_report": report})
        if repair_audit["status"] != "not_needed":
            report = dict(first_review["validator_report"])
            report["conditioning_render_repair"] = repair_audit
            report["repair_source_report"] = original_review_report
            first_review = {**first_review, "validator_report": mandatory_release_report(
                report, preserve_hold=repair_audit["status"] not in {"applied", "not_needed"},
            )}

''' + source[b:]
anchor = '''        _apply_structural_source_repair_and_hold(
            result,
            planning_brief=package["planning_brief"],
            source=source,
        )
'''
assert source.count(anchor) == 1
source = source.replace(anchor, anchor + '''
        # Structural repair cannot upgrade an unresolved independent planner hold.
        report = dict(result["stage2_validator_report"])
        retained = findings(original_review_report, PLANNER_CODES)
        errors = list(report.get("errors") or [])
        errors.extend(item for item in retained if item not in errors)
        report["errors"] = errors
        report = mandatory_release_report(report)
        result["stage2_validator_report"] = report
        if report.get("release_decision") == "hold":
            result["status"] = "review_required"
            result["stage2_status"] = _STAGE2_FAILED
            result["plan_text"] = ""
''', 1)
text = text[:start] + source + text[end:]
p.write_text(text)

for path in ['fightcamp/stage2_pipeline.py', 'fightcamp/stage2_policy.py',
             'fightcamp/stage2_repair.py', 'fightcamp/stage2_payload.py',
             'fightcamp/conditioning_render_repair.py', 'api/stage2_automation.py']:
    ast.parse((ROOT/path).read_text(), filename=path)
print('PR1 source integration syntax checked.')
