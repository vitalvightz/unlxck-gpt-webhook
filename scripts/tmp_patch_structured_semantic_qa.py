from pathlib import Path
import re

SEMANTIC_MODULE = '''"""Final semantic QA for athlete-facing structured cards.

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
  containing only \"discharge\", \"pain\", or \"bleeding\";
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
'''

Path("api/structured_plan_semantic_qa.py").write_text(SEMANTIC_MODULE, encoding="utf-8")

p = Path("api/stage2_automation.py")
s = p.read_text(encoding="utf-8")
anchor = "from .structured_plan_sparring_reconcile import reconcile_coach_led_sparring_days\n"
assert anchor in s
s = s.replace(anchor, anchor + "from .structured_plan_semantic_qa import (\n    build_structured_card_semantic_qa_prompt,\n    parse_structured_card_semantic_qa,\n)\n", 1)

marker = "\n\n# Responses-API output-format object requesting a single JSON object."
start = s.index("def _structured_repair_enabled() -> bool:")
end = s.index(marker, start)
helper = '''\n\ndef _structured_semantic_qa_enabled() -> bool:\n    """Whether the final LLM critic must approve the athlete-facing card."""\n    raw = os.getenv("UNLXCK_STAGE2_STRUCTURED_SEMANTIC_QA")\n    if raw is None:\n        return True\n    return raw.strip().lower() in {"1", "true", "yes", "on"}\n'''
s = s[:end] + helper + s[end:]

method_anchor = "    async def _generate_structured_outcome(\n"
assert method_anchor in s
qa_method = '''    async def _semantic_qa_structured_outcome(\n        self,\n        outcome: StructuredPlanOutcome,\n        *,\n        source: str,\n        log_context: dict[str, str] | None,\n        costs: list[dict[str, Any]],\n    ) -> tuple[StructuredPlanOutcome, list[dict[str, Any]]]:\n        """Reject semantically broken cards without rewriting training content."""\n        if (\n            not _structured_semantic_qa_enabled()\n            or outcome.status not in {"valid", "repair_attempted_valid"}\n            or outcome.structured_plan is None\n        ):\n            return outcome, costs\n\n        prompt = build_structured_card_semantic_qa_prompt(outcome.structured_plan)\n        qa_text, qa_cost = await self._generate_text(\n            prompt,\n            attempt_label="structured_semantic_qa",\n            source=source,\n            log_context=log_context,\n            timeout=_stage2_structured_timeout_seconds(),\n            response_format=_STRUCTURED_JSON_FORMAT,\n        )\n        costs.append(qa_cost)\n        qa = parse_structured_card_semantic_qa(qa_text)\n        if qa.passed:\n            logger.info("[stage2] structured_semantic_qa pass")\n            return outcome, costs\n\n        logger.warning(\n            "[stage2] structured_semantic_qa fail issues=%s; using raw plan_text fallback",\n            len(qa.issues),\n        )\n        return (\n            StructuredPlanOutcome(\n                status="invalid_fallback_used",\n                errors=[f"semantic_qa: {issue}" for issue in qa.issues],\n                warnings=list(outcome.warnings),\n            ),\n            costs,\n        )\n\n'''
s = s.replace(method_anchor, qa_method + method_anchor, 1)
old = '''        if first_outcome.status in ("valid", "blocked_by_safety_audit"):\n            return self._reconcile_coach_led(first_outcome, planning_brief), costs\n'''
assert old in s
s = s.replace(old, '''        if first_outcome.status == "blocked_by_safety_audit":\n            return self._reconcile_coach_led(first_outcome, planning_brief), costs\n        if first_outcome.status == "valid":\n            candidate = self._reconcile_coach_led(first_outcome, planning_brief)\n            return await self._semantic_qa_structured_outcome(\n                candidate, source=source, log_context=log_context, costs=costs\n            )\n''', 1)
old = "        return self._reconcile_coach_led(repaired_outcome, planning_brief), costs\n"
assert old in s
s = s.replace(old, '''        candidate = self._reconcile_coach_led(repaired_outcome, planning_brief)\n        return await self._semantic_qa_structured_outcome(\n            candidate, source=source, log_context=log_context, costs=costs\n        )\n''', 1)
p.write_text(s, encoding="utf-8")

p = Path("api/structured_plan_safety.py")
s = p.read_text(encoding="utf-8")
old = '                    for key in ("coaching_cues", "regression_options", "substitutions"):\n'
assert old in s
p.write_text(s.replace(old, '                    for key in ("coaching_cues", "regression_options", "substitutions", "stop_rules"):\n', 1), encoding="utf-8")

p = Path("api/structured_plan_generation.py")
s = p.read_text(encoding="utf-8")
lines = s.splitlines()
matches = [i for i, line in enumerate(lines) if "10 words" in line and "stop" in line.lower()]
assert len(matches) == 1, matches
i = matches[0]
lines[i + 1:i + 1] = [
    '        "- Before output, silently review every athlete-facing field for complete, coherent wording. "',
    '        "A stop_rules entry must be a complete actionable trigger, never an isolated symptom/noun, "',
    '        "and must not merely repeat plan-level Safety Priority/red-flag guidance when it adds no "',
    '        "exercise-specific trigger.\\n"',
]
p.write_text("\n".join(lines) + "\n", encoding="utf-8")

p = Path("web/lib/block-display-guardrails.ts")
s = p.read_text(encoding="utf-8")
s, n = re.subn(r'\nfunction stripStopLabel\(value: string\): string \{.*?\n\}\n', '\n', s, count=1, flags=re.S)
assert n == 1
s, n = re.subn(r'\nfunction splitStopClauses\(value: string\): string\[\] \{.*?\n\}\n\n/\*\*\n \* One exercise owns at most one athlete-facing stop rule\..*?\nexport function selectCompactStopRule\(.*?\n\}\n', '\n', s, count=1, flags=re.S)
assert n == 1
p.write_text(s, encoding="utf-8")

p = Path("web/components/structured-plan-renderer.tsx")
s = p.read_text(encoding="utf-8")
assert "  selectCompactStopRule,\n" in s
s = s.replace("  selectCompactStopRule,\n", "", 1)
s, n = re.subn(r'selectCompactStopRule\(\s*stopRules,\s*planSafetyTexts\s*\)', 'stopRules.map((rule) => rule.trim().replace(/^stop(?:\\s+rule)?\\s*:\\s*/i, "").trim()).find(Boolean) || null', s, count=1)
assert n == 1
p.write_text(s, encoding="utf-8")

p = Path("web/lib/block-display-guardrails.test.ts")
s = p.read_text(encoding="utf-8").replace("  selectCompactStopRule,\n", "", 1)
s, n = re.subn(r'\ntest\("keeps one block-specific stop rule.*?(?=\ntest\("removes escalation from Active Notes)', '\n', s, count=1, flags=re.S)
assert n == 1
p.write_text(s, encoding="utf-8")

Path("tests/test_structured_plan_semantic_qa.py").write_text('''from api.structured_plan_semantic_qa import (\n    build_structured_card_semantic_qa_prompt,\n    parse_structured_card_semantic_qa,\n)\n\n\ndef test_semantic_qa_parser_accepts_clean_pass():\n    result = parse_structured_card_semantic_qa('{"verdict":"pass","issues":[]}')\n    assert result.passed is True\n    assert result.issues == ()\n\n\ndef test_semantic_qa_parser_fails_closed_on_invalid_json():\n    result = parse_structured_card_semantic_qa("not-json")\n    assert result.passed is False\n    assert result.issues\n\n\ndef test_semantic_qa_parser_keeps_path_and_reason():\n    result = parse_structured_card_semantic_qa('{"verdict":"fail","issues":[{"path":"weeks.0.days.0.sessions.0.blocks.0.stop_rules.0","reason":"isolated symptom"}]}')\n    assert result.passed is False\n    assert result.issues == ("weeks.0.days.0.sessions.0.blocks.0.stop_rules.0: isolated symptom",)\n\n\ndef test_semantic_qa_prompt_catches_orphan_stop_rule_without_rewriting():\n    prompt = build_structured_card_semantic_qa_prompt({"weeks": [{"days": [{"sessions": [{"blocks": [{"stop_rules": ["discharge"]}]}]}]}]})\n    assert 'only "discharge"' in prompt\n    assert "Do not rewrite the plan" in prompt\n    assert '"stop_rules":["discharge"]' in prompt\n''', encoding="utf-8")

p = Path("tests/test_structured_plan_safety.py")
s = p.read_text(encoding="utf-8")
if "test_athlete_facing_strings_includes_stop_rules" not in s:
    s += '''\n\ndef test_athlete_facing_strings_includes_stop_rules():\n    from api.structured_plan_safety import athlete_facing_strings\n\n    plan = {"weeks": [{"days": [{"sessions": [{"blocks": [{"stop_rules": ["Stop if punch speed collapses"]}]}]}]}]}\n    assert "Stop if punch speed collapses" in athlete_facing_strings(plan)\n'''
    p.write_text(s, encoding="utf-8")
