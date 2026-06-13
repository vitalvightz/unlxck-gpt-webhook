"""Stage 2 → ``StructuredTrainingPlan`` bridge.

This module connects the existing Stage 2 plan generation to the new structured
plan schema (see ``api/structured_plan_models.py``). It is deliberately additive:
structured generation runs *beside* the legacy raw-text flow and never replaces
it. If structured generation is skipped, fails, or produces invalid JSON, the
raw ``plan_text`` remains the fallback and plan generation is never blocked.

Two concerns live here:

* :func:`build_structured_plan_outcome` — the pure, network-free validation flow
  (validate → one repair retry → raw-markdown fallback) that turns a candidate
  structured payload into a persistable outcome plus an admin/debug status. It
  reuses :func:`safe_parse_structured_plan` and :func:`repair_structured_plan_once`.
* :func:`build_structured_plan_prompt` — the instruction text that tells the
  model what a schema-compatible ``StructuredTrainingPlan`` JSON object must look
  like. The actual model call lives in ``api/stage2_automation.py``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .structured_plan_models import (
    SCHEMA_VERSION,
    repair_structured_plan_once,
    safe_parse_structured_plan,
)

# Admin/debug status describing what happened to the structured-plan attempt.
StructuredPlanStatus = Literal[
    "not_attempted",
    "valid",
    "repair_attempted_valid",
    "invalid_fallback_used",
]

# Biometric / wearable-style keys the structured plan must never carry. Readiness
# is self-report only (no HRV/CNS/WHOOP-style scores — see the schema module). If
# a model hallucinates one of these, it is stripped before validation so it can
# never be persisted.
BANNED_BIOMETRIC_KEYS: frozenset[str] = frozenset(
    {
        "hrv",
        "hrv_score",
        "hrv_ms",
        "cns",
        "cns_recovery",
        "cns_recovery_percent",
        "cns_percent",
        "whoop_recovery",
        "whoop_recovery_score",
        "whoop_score",
        "recovery_score",
        "readiness_score",
        "strain",
        "strain_score",
        "resting_heart_rate",
    }
)


@dataclass
class StructuredPlanOutcome:
    """Result of attempting to produce a validated structured plan.

    ``structured_plan`` is a JSON-ready dict (only on a valid/repaired outcome);
    it is ``None`` whenever the raw ``plan_text`` fallback must be used so an
    invalid payload is never persisted. ``errors``/``status`` feed admin debug.
    """

    status: StructuredPlanStatus
    structured_plan: dict[str, Any] | None = None
    schema_version: str | None = None
    errors: list[str] = field(default_factory=list)

    def as_debug(self) -> dict[str, Any]:
        """Compact admin/debug view persisted alongside the validator report."""
        return {
            "status": self.status,
            "errors": list(self.errors),
            "schema_version": self.schema_version,
        }


def strip_biometric_fields(data: Any) -> tuple[Any, list[str]]:
    """Recursively drop banned biometric keys.

    Returns ``(cleaned, removed_paths)``. The input is not mutated.
    """

    removed: list[str] = []

    def _walk(node: Any, path: str) -> Any:
        if isinstance(node, dict):
            cleaned: dict[Any, Any] = {}
            for key, value in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                if isinstance(key, str) and key.strip().lower() in BANNED_BIOMETRIC_KEYS:
                    removed.append(child_path)
                    continue
                cleaned[key] = _walk(value, child_path)
            return cleaned
        if isinstance(node, list):
            return [_walk(item, f"{path}[{index}]") for index, item in enumerate(node)]
        return node

    return _walk(data, ""), removed


def build_structured_plan_outcome(
    raw_data: Any,
    *,
    raw_markdown: str = "",
    repair_fn: Callable[[Any, list[str]], Any] | None = None,
) -> StructuredPlanOutcome:
    """Validate a candidate structured payload into a persistable outcome.

    Flow (matching the task contract):

    1. ``raw_data is None`` → ``not_attempted`` (structured generation skipped).
    2. Strip banned biometric keys, then validate.
    3. Valid → ``valid``.
    4. Invalid and no ``repair_fn`` → ``invalid_fallback_used``.
    5. Invalid with ``repair_fn`` → run exactly one repair retry via
       :func:`repair_structured_plan_once`; success → ``repair_attempted_valid``,
       otherwise ``invalid_fallback_used``.

    Never raises: a malformed payload degrades to ``invalid_fallback_used`` so the
    raw ``plan_text`` flow keeps working.
    """

    if raw_data is None:
        return StructuredPlanOutcome(status="not_attempted")

    cleaned, _removed = strip_biometric_fields(raw_data)

    first = safe_parse_structured_plan(cleaned, raw_markdown=raw_markdown or None)
    if first.ok and first.plan is not None:
        return StructuredPlanOutcome(
            status="valid",
            structured_plan=first.plan.model_dump(mode="json"),
            schema_version=first.plan.schema_version,
        )

    if repair_fn is None:
        return StructuredPlanOutcome(
            status="invalid_fallback_used",
            errors=list(first.errors),
        )

    # Strip biometric keys from anything the repair attempt introduces too.
    def _clean_repair(data: Any, errors: list[str]) -> Any:
        repaired = repair_fn(data, errors)
        repaired_clean, _ = strip_biometric_fields(repaired)
        return repaired_clean

    repaired = repair_structured_plan_once(
        cleaned, repair_fn=_clean_repair, raw_markdown=raw_markdown or None
    )
    if repaired.ok and repaired.plan is not None:
        return StructuredPlanOutcome(
            status="repair_attempted_valid",
            structured_plan=repaired.plan.model_dump(mode="json"),
            schema_version=repaired.plan.schema_version,
        )
    return StructuredPlanOutcome(
        status="invalid_fallback_used",
        errors=list(repaired.errors),
    )


def _extract_json_object(text: str) -> str | None:
    """Return the first balanced top-level ``{...}`` object in ``text``.

    Uses a brace-counting scan so trailing/leading prose — or stray braces in a
    commentary wrapper or a ```json fence — does not produce a truncated or
    over-wide span the way ``find``/``rfind`` would. String literals are honoured
    so braces inside JSON string values are not mistaken for structure. Returns
    ``None`` when no complete object is present.
    """

    depth = 0
    start: int | None = None
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                return text[start : index + 1]
    return None


def parse_structured_json(text: str) -> Any:
    """Parse model output into JSON, tolerating a leading/trailing prose wrapper.

    Returns ``None`` when no JSON object can be located, so callers treat it as a
    skipped attempt rather than crashing.
    """

    if not text:
        return None
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced ``{...}`` object if the model wrapped the
    # JSON in commentary or a code fence despite instructions.
    candidate = _extract_json_object(stripped)
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


_STRUCTURED_PLAN_RULES = f"""\
You are converting an already-written fight-camp training plan into a strict,
machine-readable JSON object. Output ONLY a single JSON object — no markdown, no
code fences, no commentary.

The root JSON object IS the StructuredTrainingPlan.
Do NOT wrap it inside a top-level "plan" key. Its top-level keys are exactly:

  schema_version, plan_metadata, athlete_context, event_context,
  countdown_labels, red_flag_rules, weeks, daily_check_ins, nutrition,
  progression_notes, raw_markdown_fallback.

The nested training hierarchy lives inside the root object as:
weeks[] -> days[] -> sessions[] -> blocks[].

The JSON object MUST conform to the StructuredTrainingPlan schema:

- It MUST set "schema_version" to "{SCHEMA_VERSION}".
- It MUST preserve the original human-readable plan verbatim in
  "raw_markdown_fallback".
- It MUST use countdown labels (countdown_labels[] and per-day countdown_label,
  e.g. "D-28", "D-7", "D-1", "D0", "D+1") whenever an event/fight/match date is
  known.
- Each week's phase_label MUST be one of: GPP, SPP, TAPER, FIGHT_WEEK,
  REINTEGRATION.
- Every block load MUST be a machine-readable object, NEVER a string. Use:
  {{"method": "percentage", "value": 85, "unit": "percent", "ref": "1RM",
  "display": "85% 1RM"}}. Do NOT output loads like "85%" as plain strings.
- Readiness is self-report ONLY. Do NOT output HRV, CNS recovery percentage,
  WHOOP-style recovery scores, strain scores, or any other biometric/wearable
  readiness field. Use the self-report today_card readiness_status and the 3-tap
  morning check-in only.
- Each session MUST include completion_status (default "not_started") and a
  session-level mindset_anchor.
- Provide red_flag_rules[] with machine fields (metric/operator/threshold/logic)
  kept separate from a human-readable display_text.
- Provide nutrition with a summary and, where a weight cut applies, a
  weight_cut_warning. Weight-cut guidance MUST be expressed as a risk requiring
  qualified supervision — NEVER direct acute-cut instructions (no sauna,
  dehydration, water-loading, or sodium-manipulation directives).
"""


def build_structured_plan_prompt(
    *,
    plan_markdown: str,
    planning_brief: dict[str, Any] | None = None,
    event_date: str = "",
    repair_errors: list[str] | None = None,
    broken_json: str | None = None,
) -> str:
    """Build the model prompt for turning a markdown plan into structured JSON.

    When ``repair_errors``/``broken_json`` are supplied the prompt asks the model
    to fix a previous invalid attempt (the single repair retry).
    """

    sections: list[str] = [_STRUCTURED_PLAN_RULES]

    if event_date:
        sections.append(f"EVENT/FIGHT DATE: {event_date}")

    if planning_brief:
        try:
            brief_json = json.dumps(planning_brief, ensure_ascii=False)[:6000]
        except (TypeError, ValueError):
            brief_json = ""
        if brief_json:
            sections.append(
                "PLANNING BRIEF (context for athlete/event/phases — do not copy "
                "verbatim):\n" + brief_json
            )

    sections.append(
        "ORIGINAL PLAN (preserve this exactly in raw_markdown_fallback):\n"
        + plan_markdown
    )

    if repair_errors:
        sections.append(
            "Your previous JSON failed schema validation with these errors:\n"
            + "\n".join(f"- {err}" for err in repair_errors)
        )
    if broken_json:
        sections.append(
            "Previous invalid JSON to correct (return a fully valid object):\n"
            + broken_json[:12000]
        )

    sections.append(
        "Return the corrected StructuredTrainingPlan JSON object now."
        if repair_errors
        else "Return the StructuredTrainingPlan JSON object now."
    )

    return "\n\n".join(sections)
