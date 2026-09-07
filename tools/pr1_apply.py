"""Apply PR1 integration to the pinned repository source, then remove this tool."""
from __future__ import annotations
import ast
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path, before, after):
    p = ROOT / path
    text = p.read_text()
    if text.count(before) != 1:
        raise RuntimeError(f'{path}: expected one anchor, found {text.count(before)}')
    p.write_text(text.replace(before, after, 1))


def replace_function(path, name, replacement, cls=None):
    p = ROOT / path
    text = p.read_text()
    tree = ast.parse(text)
    nodes = tree.body
    if cls:
        nodes = next(n for n in nodes if isinstance(n, ast.ClassDef) and n.name == cls).body
    matches = [n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f'{path}: could not identify {cls}.{name}')
    node = matches[0]
    lines = text.splitlines(keepends=True)
    source = ''.join(lines[node.lineno-1:node.end_lineno])
    indent = ' ' * node.col_offset
    replacement = textwrap.indent(textwrap.dedent(replacement).strip() + '\n', indent)
    p.write_text(text.replace(source, replacement, 1))

replace_function('fightcamp/stage2_pipeline.py', 'build_stage2_retry', '''
def build_stage2_retry(
    *, stage1_result: dict, final_plan_text: str,
    validator_report: dict | None = None,
) -> dict:
    from .stage2_retry_contract import build_stage2_retry as _build
    return _build(stage1_result=stage1_result, final_plan_text=final_plan_text,
                  validator_report=validator_report)
''')

replace_once('fightcamp/stage2_policy.py',
    '    if not normalized or normalized in _REPAIR_PROMPT_EXCLUDED_CODES:\n',
    '    if normalized == "missing_selected_conditioning_assignment":\n        return True\n    if not normalized or normalized in _REPAIR_PROMPT_EXCLUDED_CODES:\n')

replace_once('fightcamp/stage2_repair.py',
    '11. Collapse menu-like session templates into one final prescription whenever the athlete context already resolves the choice.',
    '11. Collapse menu-like session templates into one resolved prescription per selected exercise whenever the athlete context already resolves the choice. Never collapse a closed multi-exercise session into one exercise.')

replace_once('fightcamp/stage2_payload.py',
    'Cut novelty, reduce accessory volume, avoid density. Keep only sharpness, rhythm, confidence, and freshness. One final prescription per session — no option menus.',
    'Cut novelty, reduce accessory volume, avoid density. Keep only sharpness, rhythm, confidence, and freshness. One resolved prescription per selected exercise — no option menus. Closed multi-exercise membership must never be collapsed into one drill.')

replace_once('api/stage2_automation.py',
    '        report = apply_stage2_release_policy({\n',
    '        report = apply_mandatory_render_guard({\n')
replace_once('api/stage2_automation.py',
    'from fightcamp.goal_preservation import validate_goal_preservation\n',
    'from fightcamp.goal_preservation import validate_goal_preservation\n'
    'from fightcamp.stage2_retry_contract import (\n'
    '    apply_mandatory_render_guard, PLANNER_FAILURE_CODES,\n'
    ')\n'
    'from fightcamp.closed_conditioning_render import findings_with_codes\n'
    'from .stage2_conditioning_repair import run_stage2_render_repair\n')

p = ROOT / 'api/stage2_automation.py'
text = p.read_text()
cls = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'OpenAIStage2Automator')
fn = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'finalize')
lines = text.splitlines(keepends=True)
source = ''.join(lines[fn.lineno-1:fn.end_lineno])
source = source.replace(
    'return {**review, "validator_report": apply_stage2_release_policy(report)}',
    'return {**review, "validator_report": apply_mandatory_render_guard(report)}')
start = source.index('        # Effective-dose violations are deterministic safety failures.')
end = source.index('        quality_findings = athlete_release_with_flags_findings', start)
source = source[:start] + '''        # Repair only source-backed omissions. Goal failures remain independent.
        repair = await run_stage2_render_repair(
            automator=self, stage1_result=stage1_result,
            planning_brief=package["planning_brief"], first_review=first_review,
            first_pass_text=first_pass_text, first_pass_cost=first_pass_cost,
            reviewed_report=reviewed_report, source=source, log_context=log_context,
        )
        final_text = repair["text"]
        final_cost = repair["cost"]
        attempt_count = repair["attempt_count"]
        retry_text = repair["retry_text"]
        first_review = repair["review"]
        plan_text_cost = final_cost
        original_review_report = repair["original_report"]
        render_repair_audit = repair["audit"]

        if final_cost.get("stage2_incomplete_response"):
            report = dict(first_review["validator_report"])
            if not any(item.get("code") == "stage2_output_truncated"
                       for item in report.get("errors", []) if isinstance(item, dict)):
                report["errors"] = [*(report.get("errors") or []), {
                    "code": "stage2_output_truncated",
                    "message": "Provider marked the final Stage 2 response incomplete.",
                }]
            first_review = reviewed_report({**first_review, "validator_report": report})

''' + source[end:]
anchor = '''        _apply_structural_source_repair_and_hold(
            result,
            planning_brief=package["planning_brief"],
            source=source,
        )
'''
if source.count(anchor) != 1:
    raise RuntimeError('structural source-repair integration anchor changed')
source = source.replace(anchor, '''        report = result["stage2_validator_report"]
        if render_repair_audit["status"] != "not_needed":
            source_repair = dict(report.get("source_repair") or {})
            source_repair["conditioning_render_repair"] = render_repair_audit
            report["source_repair"] = source_repair
            report["repair_source_report"] = original_review_report

''' + anchor + '''
        # Structural restoration must not upgrade an unrelated planner hold.
        report = dict(result["stage2_validator_report"])
        prior_planner = findings_with_codes(original_review_report, PLANNER_FAILURE_CODES)
        errors = list(report.get("errors") or [])
        errors.extend(item for item in prior_planner if item not in errors)
        report["errors"] = errors
        report = apply_mandatory_render_guard(report)
        result["stage2_validator_report"] = report
        if report.get("release_decision") == "hold":
            result["status"] = "review_required"
            result["stage2_status"] = _STAGE2_FAILED
            result["plan_text"] = ""
''', 1)
text = text.replace(''.join(lines[fn.lineno-1:fn.end_lineno]), source, 1)
p.write_text(text)

# Narrow fixes in the new repair helpers, applied together with integration.
replace_once('fightcamp/closed_conditioning_render.py',
    '    handled: set[tuple] = set()\n',
    '    resolved: set[tuple] = set()\n')
replace_once('fightcamp/closed_conditioning_render.py',
    '        handled.add(identity)\n',
    '')
replace_once('fightcamp/closed_conditioning_render.py',
    '        present = [any(_line_has_exercise(line, name) for line in body) for name in names]\n',
    '        present = [any(_line_has_exercise(line, name) for line in body) for name in names]\n'
    '        resolved.update((day, role.get("role_key"), name) for name, exists in zip(names, present) if exists)\n')
replace_once('fightcamp/closed_conditioning_render.py',
    '    for finding in missing:\n        if not any(entry.get("scheduled_d_day") == finding.get("scheduled_d_day")\n',
    '    for finding in missing:\n        if (finding.get("scheduled_d_day"), finding.get("role_key"), finding.get("exercise")) in resolved:\n            continue\n        if not any(entry.get("scheduled_d_day") == finding.get("scheduled_d_day")\n')
replace_once('fightcamp/stage2_retry_contract.py',
    '    if blocking or preserve_hold or original.get("release_decision") == "hold":\n',
    '    if (blocking or preserve_hold or original.get("release_decision") == "hold"\n'
    '            or original.get("planner_preflight_failed")):\n')
replace_once('api/stage2_conditioning_repair.py',
    '    if not text.strip() or "stage2_output_truncated" in codes:\n',
    '    if not text.strip() or any(item.get("code") == "stage2_output_truncated"\n'
    '                                  for item in original_report.get("errors", []) if isinstance(item, dict)):\n')
replace_once('api/stage2_conditioning_repair.py',
    '    retry = build_stage2_retry(\n',
    '    if any(item.get("reason") in {"canonical_week_missing", "missing_or_ambiguous_day",\n'
    '                                   "ambiguous_role_ownership"} for item in audit["unresolved"]):\n'
    '        audit["status"] = "structural_authority_required"\n'
    '        review = _held_review(review, original_report=original_report,\n'
    '                              reason="structural_authority_required")\n'
    '        return {"text": text, "cost": cost, "attempt_count": 1,\n'
    '                "retry_text": "", "review": review, "audit": audit,\n'
    '                "original_report": original_report}\n\n'
    '    retry = build_stage2_retry(\n')
replace_once('api/stage2_conditioning_repair.py',
    '            cost = _merge_stage2_costs(first_pass_cost, exc.stage2_cost)\n',
    '            cost = _merge_stage2_costs(first_pass_cost, exc.stage2_cost)\n'
    '            cost["stage2_attempt_count"] = 2\n')
replace_once('api/stage2_conditioning_repair.py',
    '            cost = _merge_stage2_costs(first_pass_cost, repair_cost)\n',
    '            cost = _merge_stage2_costs(first_pass_cost, repair_cost)\n'
    '            cost["stage2_attempt_count"] = 2\n')
replace_once('api/stage2_conditioning_repair.py',
    '                    review = _held_review(review, original_report=original_report,\n'
    '                                          reason="model_revalidation_failed",\n',
    '                    review = _held_review(candidate_review, original_report=original_report,\n'
    '                                          reason="model_revalidation_failed",\n')

for path in ['fightcamp/stage2_pipeline.py', 'fightcamp/stage2_policy.py',
             'fightcamp/stage2_repair.py', 'fightcamp/stage2_payload.py',
             'fightcamp/closed_conditioning_render.py', 'fightcamp/stage2_retry_contract.py',
             'api/stage2_automation.py', 'api/stage2_conditioning_repair.py']:
    ast.parse((ROOT/path).read_text(), filename=path)
print('PR1 integration applied; eight files syntax-checked.')
