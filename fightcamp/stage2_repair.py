from __future__ import annotations

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
8. Keep the final output athlete-facing. Do not mention the validator, the repair process, or rejected items.

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

    return {
        "fix_first": restriction_fixes,
        "strip_out": formatting_fixes,
        "then_restore": missing_elements,
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
