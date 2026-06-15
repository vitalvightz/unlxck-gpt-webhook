"""Stage 1 self-parity harness.

The Stage 2 LLM finalizer is graded by ``fightcamp.stage2_validator`` against
the planning brief. The closer Stage 1's *own* rendered draft is to a plan that
already passes that validator, the less structural work the LLM has to do — and
the closer we get to being able to skip the LLM entirely for clean cases.

This module turns that idea into a measurable, reusable primitive: run the exact
same validator the finalizer is graded by against Stage 1's own ``plan_text``,
using Stage 1's own ``planning_brief``. The result tells us, deterministically:

* whether Stage 1's draft would already be *publishable* (no errors, no hard
  blocking warnings) — the precondition for bypassing the LLM, and
* exactly which validator codes still fire, so each Stage 1 rendering
  improvement can be measured by how many codes it removes.

``stage1_can_bypass_llm`` is the gating primitive the generation pipeline can
eventually consult to short-circuit (or shrink) the Stage 2 call.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .stage2_pipeline import review_stage2_output


def _validator_report(review: dict[str, Any]) -> dict[str, Any]:
    report = review.get("validator_report")
    return report if isinstance(report, dict) else {}


def _codes(entries: Any) -> Counter:
    counter: Counter = Counter()
    for entry in entries or []:
        if isinstance(entry, dict):
            code = str(entry.get("code") or "").strip()
            if code:
                counter[code] += 1
    return counter


def review_stage1_self_output(stage1_result: dict[str, Any]) -> dict[str, Any]:
    """Validate Stage 1's own draft with the Stage 2 validator.

    ``stage1_result`` is the dict returned by ``generate_plan_sync`` — it must
    carry both ``planning_brief`` and ``plan_text``. Raises ``ValueError`` when
    the result is not a successful Stage 1 output (those legitimately omit the
    planning brief and cannot be self-validated).
    """

    if not isinstance(stage1_result, dict):
        raise TypeError("stage1_result must be a dict")
    planning_brief = stage1_result.get("planning_brief")
    if not isinstance(planning_brief, dict) or not planning_brief:
        status = str(stage1_result.get("status") or "").strip() or "unknown"
        raise ValueError(
            f"stage1_result has no planning_brief to self-validate (status={status!r})"
        )
    plan_text = str(stage1_result.get("plan_text") or "")
    return review_stage2_output(planning_brief=planning_brief, final_plan_text=plan_text)


def parity_breakdown(review: dict[str, Any]) -> dict[str, Any]:
    """Compact, code-level summary of a ``review_stage2_output`` result."""

    report = _validator_report(review)
    error_codes = _codes(report.get("errors"))
    blocking_codes = _codes(report.get("blocking_warnings"))
    review_flag_codes = _codes(report.get("review_flags"))
    return {
        "status": review.get("status"),
        "is_publishable": bool(report.get("is_publishable")),
        "error_codes": dict(error_codes),
        "blocking_codes": dict(blocking_codes),
        "review_flag_codes": dict(review_flag_codes),
        "error_count": sum(error_codes.values()),
        "blocking_count": sum(blocking_codes.values()),
        "review_flag_count": sum(review_flag_codes.values()),
        "all_codes": dict(error_codes + blocking_codes + review_flag_codes),
    }


def stage1_parity_breakdown(stage1_result: dict[str, Any]) -> dict[str, Any]:
    """Convenience: ``review_stage1_self_output`` + :func:`parity_breakdown`."""

    return parity_breakdown(review_stage1_self_output(stage1_result))


def stage1_can_bypass_llm(
    stage1_result: dict[str, Any],
    *,
    require_clean: bool = False,
) -> bool:
    """Return ``True`` when Stage 1's own draft already clears validation.

    By default this mirrors the finalizer's publish gate: no validator errors
    and no hard blocking warnings. With ``require_clean=True`` it additionally
    requires zero soft review flags — the stronger bar for rendering the plan
    deterministically with no LLM pass at all.
    """

    breakdown = stage1_parity_breakdown(stage1_result)
    if breakdown["error_count"] or breakdown["blocking_count"]:
        return False
    if require_clean and breakdown["review_flag_count"]:
        return False
    return True
