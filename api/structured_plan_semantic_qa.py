"""Final semantic QA for athlete-facing structured cards.

The critic may only PASS or reject a structured card. It never rewrites training
content; a rejected or unreadable review falls back to the validated Stage 2 text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredCardSemanticQa:
    passed: bool
    issues: tuple[str, ...] = ()


def build_structured_card_semantic_qa_prompt(structured_plan: dict[str, Any]) -> str:
    payload = json.dumps(structured_plan, ensure_ascii=False, separators=(",", ":"))
    return f"""You are the final QA critic for an athlete-facing training-plan card.

You are NOT a coach, planner, or editor. Do not rewrite the plan and do not
change exercises, sets, reps, load, effort, dates, classifications, injuries,
red flags, or safety decisions.

Review the complete structured card only for CLEAR athlete-facing semantic defects:
- garbled, incomplete, or nonsensical wording;
- an isolated noun/symptom presented as an instruction, such as a stop rule
  containing only "discharge", "pain", or "bleeding";
- a stop rule that is not a complete actionable trigger/condition;
- a stop rule that merely repeats plan-level Safety Priority/red-flag guidance
  and adds no exercise-specific reason to stop that block;
- an internal contradiction between visible card fields;
- duplicated visible copy that would clearly confuse the athlete.

Do NOT fail for concise coaching phrases, normal sports terminology, minor style
preferences, or a stop rule being longer than 10 words when it remains complete
and meaningful. Be conservative: if the card makes sense, PASS it.

Return exactly one JSON object and nothing else:
{{"verdict":"pass","issues":[]}}
or
{{"verdict":"fail","issues":[{{"path":"weeks.0.days.0.sessions.0.blocks.0.stop_rules.0","reason":"isolated symptom is not an actionable stop condition"}}]}}

STRUCTURED CARD JSON:
{payload}
"""


def parse_structured_card_semantic_qa(text: str) -> StructuredCardSemanticQa:
    """Parse critic JSON fail-closed; malformed QA can never approve a card."""
    try:
        raw = json.loads(str(text or "").strip())
    except (TypeError, ValueError, json.JSONDecodeError):
        return StructuredCardSemanticQa(False, ("semantic QA returned invalid JSON",))
    if not isinstance(raw, dict):
        return StructuredCardSemanticQa(False, ("semantic QA response was not an object",))

    verdict = str(raw.get("verdict") or "").strip().lower()
    raw_issues = raw.get("issues")
    issues: list[str] = []
    if isinstance(raw_issues, list):
        for item in raw_issues:
            if isinstance(item, str) and item.strip():
                issues.append(item.strip())
            elif isinstance(item, dict):
                path = str(item.get("path") or "").strip()
                reason = str(item.get("reason") or "").strip()
                if reason:
                    issues.append(f"{path}: {reason}" if path else reason)
    if verdict == "pass" and not issues:
        return StructuredCardSemanticQa(True)
    if not issues:
        issues.append("semantic QA did not return a clean pass")
    return StructuredCardSemanticQa(False, tuple(issues))
