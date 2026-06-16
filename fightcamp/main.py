import json
import logging
import os
from time import perf_counter
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, model_validator

from .input_parsing import PlanInput
from .injury_triage import FULL_PLAN, blocked_mode_output, triage_injuries
from .logging_utils import configure_logging
from .plan_pipeline import (
    _filter_mindset_blocks,
    build_runtime_context,
    build_stage2_outputs,
    generate_plan_blocks,
    prime_plan_banks,
    render_plan_bundle,
)
from .plan_rendering_utils import (
    _normalize_time_labels,
    _sanitize_phase_text,
    _sanitize_stage_output,
)
from .strength import get_exercise_bank as get_strength_exercise_bank


# Keep historical imports from fightcamp.main stable for tests and scripts.
__all__ = [
    "_filter_mindset_blocks",
    "_normalize_time_labels",
    "_sanitize_phase_text",
    "_sanitize_stage_output",
    "Stage1Result",
]

ProgressCallback = Callable[[str, str, str, dict[str, Any]], None]


def _safe_emit(callback: ProgressCallback | None, code: str, label: str, detail: str = "", **meta: Any) -> None:
    """Best-effort milestone emit. Never raises into the planner pipeline."""
    if callback is None:
        return
    try:
        callback(code, label, detail, dict(meta))
    except Exception:
        # Progress reporting must not break generation.
        logging.getLogger(__name__).exception("[progress] callback_failed code=%s", code)


_INPUT_ERROR_LABELS = {
    "missing_fighting_style_technical": "technical fighting style",
    "missing_next_fight_date": "fight date",
    "invalid_next_fight_date": "valid fight date",
    "missing_training_availability": "training availability",
    "invalid_training_frequency": "weekly training frequency",
}
_TRIAGE_RESUME_OVERRIDE_KEY = "_triage_resume_override"
_NON_OVERRIDABLE_TRIAGE_MODES = {"medical_hold"}


def _triage_resume_override_allows_continuation(data: dict, *, triage_mode: str) -> bool:
    override = data.get(_TRIAGE_RESUME_OVERRIDE_KEY)
    if not isinstance(override, dict):
        return False
    if override.get("approved") is not True:
        return False
    mode = str(triage_mode or "").strip().lower()
    if not mode or mode in _NON_OVERRIDABLE_TRIAGE_MODES:
        return False
    allowed_modes = override.get("allowed_modes")
    if not isinstance(allowed_modes, list):
        return False
    normalized_modes = {str(item).strip().lower() for item in allowed_modes if str(item).strip()}
    return mode in normalized_modes


def _invalid_result(error: str, *, missing_fields: list[str] | None = None) -> dict:
    return {
        "status": "invalid_input",
        "ok": False,
        "error": error,
        "missing_fields": list(missing_fields or []),
        "pdf_url": None,
        "why_log": {},
        "plan_text": "",
        "coach_notes": "",
        "stage2_payload": None,
        "planning_brief": None,
        "stage2_handoff_text": "",
        "parsing_metadata": {},
    }


# Statuses that represent a non-successful Stage 1 outcome, where the Stage 2
# handoff structures (``stage2_payload``/``planning_brief``) are legitimately
# absent. Any other status (including the empty status used by the normal
# success path) must carry both structures.
_NON_SUCCESS_STAGE1_STATUSES = frozenset(
    {
        "invalid_input",
        "triage_blocked",
        "medical_hold",
        "restricted_rehab_only",
        "needs_review",
    }
)


class Stage1Result(BaseModel):
    """Variant-aware contract for a Stage 1 generation result.

    Blocked/invalid variants may omit the Stage 2 handoff structures, but a
    successful generation must carry both ``stage2_payload`` and
    ``planning_brief`` so the failure surfaces here instead of downstream.
    """

    model_config = ConfigDict(extra="allow")

    status: str = ""
    stage2_payload: dict[str, Any] | None = None
    planning_brief: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _require_stage2_outputs_for_success(self) -> "Stage1Result":
        status = str(self.status or "").strip().lower()
        if status in _NON_SUCCESS_STAGE1_STATUSES:
            return self
        if self.stage2_payload is None:
            raise ValueError("stage2_payload is required for a successful Stage 1 result")
        if self.planning_brief is None:
            raise ValueError("planning_brief is required for a successful Stage 1 result")
        return self


def _validate_stage1_result(result: dict) -> dict:
    """Validate ``result`` against :class:`Stage1Result` and return it unchanged.

    Validation fails fast on a malformed success result; the original dict is
    returned so downstream consumers keep their existing dict contract.
    """
    Stage1Result.model_validate(result)
    return result


class _LazyListProxy:
    def __init__(self, loader):
        self._loader = loader

    def _resolve(self):
        return self._loader()

    def __iter__(self):
        return iter(self._resolve())

    def __len__(self):
        return len(self._resolve())

    def __getitem__(self, index):
        return self._resolve()[index]

    def __repr__(self):
        return repr(self._resolve())


exercise_bank = _LazyListProxy(get_strength_exercise_bank)


def generate_plan_sync(
    data: dict,
    *,
    progress_callback: ProgressCallback | None = None,
):
    """Generate a fight-camp plan.

    Parameters
    ----------
    data:
        Raw planner bridge payload.
    progress_callback:
        Optional ``(code, label, detail, meta)`` callable invoked at each
        semantic milestone (intake parsed, banks primed, strength scored,
        injury substitutions applied, etc.). Failures are swallowed so they
        never break generation.
    """
    configure_logging()
    logger = logging.getLogger(__name__)
    timings: dict[str, float] = {}

    def _record_timing(label: str, start: float) -> None:
        elapsed = perf_counter() - start
        timings[label] = elapsed
        logger.info("[timing] %s=%.2fs", label, elapsed)

    _safe_emit(
        progress_callback,
        "stage1_parse_input_started",
        "Stage 1 parse input started",
        "Parsing planner payload into canonical Stage 1 input.",
    )
    _safe_emit(
        progress_callback,
        "intake_received",
        "Intake received",
        "Locking in your intake and preparing the planner.",
    )

    timer_start = perf_counter()
    try:
        plan_input = PlanInput.from_payload(data)
    except ValueError as exc:
        _record_timing("parse_input", timer_start)
        logger.warning("invalid payload: %s", exc)
        return _validate_stage1_result(_invalid_result(str(exc)))
    _record_timing("parse_input", timer_start)
    _safe_emit(
        progress_callback,
        "stage1_parse_input_finished",
        "Stage 1 parse input finished",
        "Planner payload parsed into canonical Stage 1 input.",
    )

    generation_issues = plan_input.generation_issues()
    if generation_issues:
        missing_summary = ", ".join(
            _INPUT_ERROR_LABELS.get(issue, issue.replace("_", " "))
            for issue in generation_issues
        )
        logger.warning("invalid planning input: %s", generation_issues)
        return _validate_stage1_result(
            _invalid_result(
                f"missing required planning inputs: {missing_summary}",
                missing_fields=generation_issues,
            )
        )

    _safe_emit(
        progress_callback,
        "intake_parsed",
        "Intake parsed",
        "Athlete profile, camp timeline, and restrictions loaded.",
        weeks_out=plan_input.weeks_out,
        days_until_fight=plan_input.days_until_fight,
    )

    timer_start = perf_counter()
    _safe_emit(
        progress_callback,
        "stage1_injury_triage_started",
        "Stage 1 injury triage started",
        "Evaluating injuries and triage mode.",
    )
    triage_result = triage_injuries(plan_input)
    _record_timing("injury_triage", timer_start)
    triage_mode_value = str(triage_result.mode or "").strip().lower() or "full_plan"
    parsed_injury_count = len(plan_input.parsed_injuries or [])
    if parsed_injury_count:
        triage_detail = (
            f"{parsed_injury_count} injury note(s) classified — mode: {triage_mode_value}."
        )
    else:
        triage_detail = "No injuries reported. Routing as full plan."
    _safe_emit(
        progress_callback,
        "stage1_injury_triage_finished",
        "Stage 1 injury triage finished",
        triage_detail,
        triage_mode=triage_mode_value,
        parsed_injury_count=parsed_injury_count,
    )
    _safe_emit(
        progress_callback,
        "injury_triage_done",
        "Injury triage complete",
        triage_detail,
        triage_mode=triage_mode_value,
        parsed_injury_count=parsed_injury_count,
    )
    triage_mode = str(triage_result.mode or "").strip().lower()
    triage_resume_override_applied = _triage_resume_override_allows_continuation(
        data,
        triage_mode=triage_mode,
    )
    if triage_result.mode != FULL_PLAN and not triage_resume_override_applied:
        blocked = blocked_mode_output(triage=triage_result, parsed_injuries=plan_input.parsed_injuries)
        blocked["parsing_metadata"] = plan_input.parsing_metadata
        return _validate_stage1_result(blocked)

    timer_start = perf_counter()
    prime_plan_banks(logger=logger)
    _record_timing("prime_banks", timer_start)
    _safe_emit(
        progress_callback,
        "banks_primed",
        "Exercise banks loaded",
        "Strength, conditioning, and rehab libraries are warm.",
    )

    timer_start = perf_counter()
    _safe_emit(
        progress_callback,
        "stage1_phase_mapping_started",
        "Stage 1 phase mapping started",
        "Mapping camp phases and timeline windows.",
    )
    context = build_runtime_context(
        plan_input=plan_input,
        random_seed=data.get("random_seed"),
        logger=logger,
        triage_summary=triage_result.to_dict(),
        is_approved_triage_resume=triage_resume_override_applied,
    )
    _record_timing("runtime_context", timer_start)
    _safe_emit(
        progress_callback,
        "stage1_phase_mapping_finished",
        "Stage 1 phase mapping finished",
        "Camp phase mapping completed.",
    )
    phase_weeks_value = getattr(context, "phase_weeks", None)
    if not isinstance(phase_weeks_value, dict):
        phase_weeks_value = {}
    camp_len_value = getattr(context, "camp_len", 0)
    if not isinstance(camp_len_value, int):
        camp_len_value = 0
    camp_phase_summary = ", ".join(
        f"{phase}:{phase_weeks_value.get(phase, 0)}w"
        for phase in ("GPP", "SPP", "TAPER")
    )
    _safe_emit(
        progress_callback,
        "camp_brief_built",
        "Camp brief built",
        f"Camp shaped to {camp_len_value} weeks ({camp_phase_summary})."
        if camp_len_value
        else "Camp brief assembled.",
        camp_len=camp_len_value,
        phase_weeks=dict(phase_weeks_value),
    )

    _safe_emit(
        progress_callback,
        "stage1_blocks_generation_started",
        "Stage 1 blocks generation started",
        "Building strength, conditioning, recovery, mobility, rehab, and weekly training blocks.",
    )
    blocks = generate_plan_blocks(
        context=context,
        record_timing=_record_timing,
        logger=logger,
        progress_callback=progress_callback,
    )
    _safe_emit(
        progress_callback,
        "stage1_blocks_generation_finished",
        "Stage 1 blocks generation finished",
        "Stage 1 training blocks generated.",
    )

    timer_start = perf_counter()
    rendered = render_plan_bundle(context=context, blocks=blocks, logger=logger)
    _record_timing("render_bundle", timer_start)
    _safe_emit(
        progress_callback,
        "plan_drafted",
        "Plan drafted",
        "Stage 1 planning draft rendered with coach notes.",
    )

    # Build Stage 2 outputs immediately after rendering so the structured
    # handoff remains available to the finalizer.
    timer_start = perf_counter()
    _safe_emit(
        progress_callback,
        "stage1_role_map_started",
        "Stage 1 role map started",
        "Preparing Stage 2 role map and handoff structures.",
    )
    stage2_payload, planning_brief, stage2_handoff_text = build_stage2_outputs(
        context=context,
        blocks=blocks,
        rendered=rendered,
    )
    _safe_emit(
        progress_callback,
        "stage1_role_map_finished",
        "Stage 1 role map finished",
        "Stage 2 role map and handoff structures are ready.",
    )
    _safe_emit(
        progress_callback,
        "stage1_payload_build_started",
        "Stage 1 payload build started",
        "Building Stage 1 output payload package.",
    )
    if isinstance(stage2_payload, dict):
        stage2_payload = {
            **stage2_payload,
            "input_parsing_metadata": plan_input.parsing_metadata,
        }
    _record_timing("stage2_outputs", timer_start)
    _safe_emit(
        progress_callback,
        "stage1_payload_build_finished",
        "Stage 1 payload build finished",
        "Stage 1 payload package built successfully.",
    )
    _safe_emit(
        progress_callback,
        "stage2_handoff_ready",
        "Stage 2 handoff ready",
        "Planning brief and candidate pools packaged for the AI finalizer.",
    )

    pdf_url: str | None = None

    if timings:
        slowest_label = max(timings, key=timings.get)
        logger.info("[timing] slowest_stage=%s %.2fs", slowest_label, timings[slowest_label])

    result = {
        "pdf_url": pdf_url,
        "why_log": rendered.reason_log,
        "coach_notes": rendered.coach_notes,
        "plan_text": rendered.fight_plan_text,
        "stage2_payload": stage2_payload,
        "planning_brief": planning_brief,
        "stage2_handoff_text": stage2_handoff_text,
        "parsing_metadata": plan_input.parsing_metadata,
    }
    if triage_resume_override_applied:
        why_log = result.get("why_log")
        if isinstance(why_log, dict):
            why_log["injury_triage_resume_override"] = {
                "bypassed_blocking": True,
                "triage_mode": triage_mode,
                "runtime_triage_mode": FULL_PLAN,
                "override_key": _TRIAGE_RESUME_OVERRIDE_KEY,
            }
            why_log["injury_triage_original"] = triage_result.to_dict()
    return _validate_stage1_result(result)


async def generate_plan(
    data: dict,
    *,
    progress_callback: ProgressCallback | None = None,
):
    import asyncio
    return await asyncio.to_thread(
        generate_plan_sync,
        data,
        progress_callback=progress_callback,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Developer CLI: generate a plan from a planner bridge payload JSON file.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to planner bridge payload JSON generated from app-native PlanRequest.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise FileNotFoundError(
            f"Input JSON not found: {args.input}. Provide an app-native plan request fixture or generated planner payload."
        )

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    generate_plan_sync(data)
    print("::notice title=Plan Generated::Plan generated in app")


if __name__ == "__main__":
    main()
