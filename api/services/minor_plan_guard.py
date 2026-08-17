"""Read-time backstop: no blocked cut guidance reaches an under-18 athlete.

Generation already prevents this — :func:`api.minor_safety.minor_safe_stage1_payload`
strips the cut inputs before the planner runs, and the structured-plan audit
blocks a card whose Stage 2 wording slipped. This layer exists because neither
of those covers a plan that already exists: one generated before the guard
landed, or one generated while the profile still had no date of birth on record
and the athlete turned out to be 15.

Applied where the plan is served, alongside
:func:`api.services.plan_safety_copy.clarify_restricted_training_hold`, so it
runs on every athlete-facing read rather than only on the generation path.
"""
from __future__ import annotations

import logging

from api.minor_safety import (
    MINOR_WEIGHT_CUT_NOTE,
    contains_blocked_minor_guidance,
    scrub_minor_guidance,
    scrub_minor_guidance_tree,
)
from api.models import PlanDetail, PlanOutputs
from api.structured_plan_models import safe_parse_structured_plan

logger = logging.getLogger(__name__)


def apply_minor_plan_guard(plan: PlanDetail, *, is_minor: bool) -> PlanDetail:
    """Strip weight-cut/dehydration guidance from a plan served to a minor.

    Adults are returned untouched. For a minor, the markdown is scrubbed line by
    line and the structured card is scrubbed leaf by leaf; if the scrubbed card
    no longer parses, it is dropped rather than served, because an unparseable
    card is not evidence that the guidance is gone.
    """
    if not is_minor:
        return plan

    outputs = plan.outputs
    plan_text = outputs.plan_text or ""
    scrubbed_text = scrub_minor_guidance(plan_text)

    structured_plan = outputs.structured_plan
    scrubbed_structured = structured_plan
    if structured_plan is not None:
        payload = structured_plan.model_dump(mode="json")
        if contains_blocked_minor_guidance(_flatten(payload)):
            guarded_payload = scrub_minor_guidance_tree(payload)
            parsed = safe_parse_structured_plan(
                guarded_payload,
                raw_markdown=scrubbed_text or None,
            )
            if parsed.ok and parsed.plan is not None:
                scrubbed_structured = parsed.plan
            else:
                logger.warning(
                    "minor guard: structured card dropped after scrub (plan_id=%s)",
                    plan.plan_id,
                )
                scrubbed_structured = None

    if scrubbed_text == plan_text and scrubbed_structured is structured_plan:
        return plan

    return plan.model_copy(
        update={
            "outputs": PlanOutputs(
                plan_text=scrubbed_text,
                pdf_url=outputs.pdf_url,
                structured_plan=scrubbed_structured,
                schema_version=outputs.schema_version,
            )
        }
    )


def _flatten(node: object) -> str:
    """Every string leaf of a payload, joined — cheap pre-check before scrubbing."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return "\n".join(_flatten(value) for value in node.values())
    if isinstance(node, list):
        return "\n".join(_flatten(item) for item in node)
    return ""


__all__ = ["apply_minor_plan_guard", "MINOR_WEIGHT_CUT_NOTE"]
