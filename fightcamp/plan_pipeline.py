from __future__ import annotations

import logging

from .build_block import html_to_pdf, upload_to_supabase
from . import plan_pipeline_rendering as _rendering
from .plan_pipeline_blocks import generate_plan_blocks
from .plan_pipeline_rendering import build_stage2_outputs, render_plan_bundle
from .plan_pipeline_runtime import (
    GRAPPLING_STYLES,
    MUAY_THAI_REPLACEMENTS,
    MUAY_THAI_TERM_REPLACEMENTS,
    PHASES,
    PHASE_COLORS,
    PHASE_PLAN_TITLES,
    SANITIZE_LABELS,
    STYLE_MAP,
    PlanBlocksBundle,
    PlanRuntimeContext,
    RenderedPlanBundle,
    TimingRecorder,
    _apply_muay_thai_filters,
    _filter_mindset_blocks,
    _is_pure_striker,
    _normalize_selection_format,
    build_runtime_context,
    prime_plan_banks,
)


def export_plan_pdf(
    *,
    full_name: str,
    html: str,
    record_timing: TimingRecorder,
    logger: logging.Logger,
) -> str:
    _rendering.html_to_pdf = html_to_pdf
    _rendering.upload_to_supabase = upload_to_supabase
    return _rendering.export_plan_pdf(
        full_name=full_name,
        html=html,
        record_timing=record_timing,
        logger=logger,
    )


__all__ = [
    'GRAPPLING_STYLES',
    'MUAY_THAI_REPLACEMENTS',
    'MUAY_THAI_TERM_REPLACEMENTS',
    'PHASES',
    'PHASE_COLORS',
    'PHASE_PLAN_TITLES',
    'SANITIZE_LABELS',
    'STYLE_MAP',
    'PlanBlocksBundle',
    'PlanRuntimeContext',
    'RenderedPlanBundle',
    'TimingRecorder',
    '_apply_muay_thai_filters',
    '_filter_mindset_blocks',
    '_is_pure_striker',
    '_normalize_selection_format',
    'build_runtime_context',
    'build_stage2_outputs',
    'export_plan_pdf',
    'generate_plan_blocks',
    'prime_plan_banks',
    'render_plan_bundle',
]
