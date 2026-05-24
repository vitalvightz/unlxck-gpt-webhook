from __future__ import annotations

import logging
import os

from .environment import is_production_environment

logger = logging.getLogger(__name__)


def _parse_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("[runtime-config] invalid_int_env name=%s value=%r default=%s", name, raw, default)
        return default


def get_runtime_generation_config() -> dict[str, int | str | bool]:
    return {
        "enable_in_process_generation": os.getenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", "0").strip() == "1",
        "app_generation_job_stale_after_seconds": _parse_int_env("APP_GENERATION_JOB_STALE_AFTER_SECONDS", 300, minimum=60),
        "worker_stale_after_seconds": _parse_int_env("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", 300, minimum=60),
        "app_stage2_finalize_timeout_seconds": _parse_int_env("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", 240, minimum=1),
        "openai_stage2_timeout_seconds": _parse_int_env("UNLXCK_STAGE2_TIMEOUT_SECONDS", 210, minimum=1),
        "app_generation_max_concurrent_jobs": _parse_int_env("APP_GENERATION_MAX_CONCURRENT_JOBS", 1, minimum=1),
        "worker_max_concurrent_jobs": _parse_int_env("UNLXCK_GENERATION_WORKER_MAX_CONCURRENT_JOBS", 1, minimum=1),
        "stage2_model": os.getenv("UNLXCK_STAGE2_MODEL", "gpt-5-mini").strip() or "gpt-5-mini",
    }


def validate_runtime_generation_config(*, startup_role: str) -> dict[str, int | str | bool]:
    cfg = get_runtime_generation_config()
    logger.info(
        "[runtime-config] resolved role=%s in_process=%s app_stale=%s worker_stale=%s stage2_finalize=%s openai_timeout=%s app_concurrency=%s worker_concurrency=%s stage2_model=%s",
        startup_role,
        cfg["enable_in_process_generation"],
        cfg["app_generation_job_stale_after_seconds"],
        cfg["worker_stale_after_seconds"],
        cfg["app_stage2_finalize_timeout_seconds"],
        cfg["openai_stage2_timeout_seconds"],
        cfg["app_generation_max_concurrent_jobs"],
        cfg["worker_max_concurrent_jobs"],
        cfg["stage2_model"],
    )

    if not is_production_environment():
        return cfg

    if startup_role == "api" and bool(cfg["enable_in_process_generation"]):
        raise RuntimeError("Invalid production config: API must set UNLXCK_ENABLE_IN_PROCESS_GENERATION=0")
    if int(cfg["openai_stage2_timeout_seconds"]) >= int(cfg["app_stage2_finalize_timeout_seconds"]):
        raise RuntimeError("Invalid production config: UNLXCK_STAGE2_TIMEOUT_SECONDS must be lower than APP_STAGE2_FINALIZE_TIMEOUT_SECONDS")
    if int(cfg["app_stage2_finalize_timeout_seconds"]) >= int(cfg["app_generation_job_stale_after_seconds"]):
        raise RuntimeError("Invalid production config: APP_STAGE2_FINALIZE_TIMEOUT_SECONDS must be lower than APP_GENERATION_JOB_STALE_AFTER_SECONDS")
    if startup_role == "worker" and int(cfg["worker_max_concurrent_jobs"]) > 1:
        raise RuntimeError("Invalid production config: worker concurrency above 1 is not allowed")
    return cfg
