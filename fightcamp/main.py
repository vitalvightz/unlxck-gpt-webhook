import asyncio
import json
import logging
from pathlib import Path
from time import perf_counter

from .input_parsing import PlanInput
from .logging_utils import configure_logging
from .plan_pipeline import (
    _filter_mindset_blocks,
    build_runtime_context,
    build_stage2_outputs,
    export_plan_pdf,
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

_INPUT_ERROR_LABELS = {
    "missing_fighting_style_technical": "technical fighting style",
    "missing_next_fight_date": "fight date",
    "invalid_next_fight_date": "valid fight date",
    "missing_training_availability": "training availability",
    "invalid_training_frequency": "weekly training frequency",
}


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
    }


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


async def generate_plan(data: dict):
    configure_logging()
    logger = logging.getLogger(__name__)
    timings: dict[str, float] = {}

    def _record_timing(label: str, start: float) -> None:
        elapsed = perf_counter() - start
        timings[label] = elapsed
        logger.info("[timing] %s=%.2fs", label, elapsed)

    timer_start = perf_counter()
    try:
        plan_input = PlanInput.from_payload(data)
    except ValueError as exc:
        _record_timing("parse_input", timer_start)
        logger.warning("invalid payload: %s", exc)
        return _invalid_result(str(exc))
    _record_timing("parse_input", timer_start)

    generation_issues = plan_input.generation_issues()
    if generation_issues:
        missing_summary = ", ".join(
            _INPUT_ERROR_LABELS.get(issue, issue.replace("_", " "))
            for issue in generation_issues
        )
        logger.warning("invalid planning input: %s", generation_issues)
        return _invalid_result(
            f"missing required planning inputs: {missing_summary}",
            missing_fields=generation_issues,
        )

    prime_plan_banks()
    context = build_runtime_context(
        plan_input=plan_input,
        random_seed=data.get("random_seed"),
        logger=logger,
    )
    blocks = generate_plan_blocks(context=context, record_timing=_record_timing, logger=logger)
    rendered = render_plan_bundle(context=context, blocks=blocks, logger=logger)
    pdf_url = export_plan_pdf(
        full_name=plan_input.full_name,
        html=rendered.html,
        record_timing=_record_timing,
        logger=logger,
    )

    if timings:
        slowest_label = max(timings, key=timings.get)
        logger.info("[timing] slowest_stage=%s %.2fs", slowest_label, timings[slowest_label])

    stage2_payload, planning_brief, stage2_handoff_text = build_stage2_outputs(
        context=context,
        blocks=blocks,
        rendered=rendered,
    )

    return {
        "pdf_url": pdf_url,
        "why_log": rendered.reason_log,
        "coach_notes": rendered.coach_notes,
        "plan_text": rendered.fight_plan_text,
        "stage2_payload": stage2_payload,
        "planning_brief": planning_brief,
        "stage2_handoff_text": stage2_handoff_text,
    }


def main():
    data_file = Path("test_data.json").resolve()
    if not data_file.exists():
        raise FileNotFoundError(f"Test data file not found: {data_file}")
    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = asyncio.run(generate_plan(data))
    print(f"::notice title=Plan PDF::{result.get('pdf_url')}")


if __name__ == "__main__":
    main()