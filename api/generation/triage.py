"""Stage 1 triage-skip decision and triage final-result helpers."""
from __future__ import annotations

from typing import Any

from ..models import PROFILE_REFRESH_FAILED_WHY_LOG_KEY

_TRIAGE_FINAL_RESULT_STATUSES = frozenset(
    {"triage_blocked", "medical_hold", "restricted_rehab_only", "needs_review"}
)


def _is_triage_skipped_final_result(final_result: dict[str, Any] | None) -> bool:
    """A Stage-1-only outcome that should not be persisted as a plan row.

    Triage holds are not plans: they are review states that live on the
    generation job (`generation_jobs.final_result`). The athlete-facing
    `plans` table only stores real plans, so no `triage_blocked` row is
    created or updated for these outcomes.
    """
    if not isinstance(final_result, dict):
        return False
    return str(final_result.get("status") or "").strip().lower() in _TRIAGE_FINAL_RESULT_STATUSES


def _compact_generation_job_final_result(final_result: dict[str, Any]) -> dict[str, Any]:
    """Keep generation_jobs.final_result lean; canonical full text lives on plans.

    Triage-blocked outcomes have no plan row, so the job's final_result is
    the canonical record. Preserve the triage context (why_log, injury_triage)
    that the admin resume endpoint needs to gate approval.
    """
    compact: dict[str, Any] = {}
    for key in (
        "status",
        "stage2_status",
        "stage2_attempt_count",
        "stage2_validator_report",
        "stage2_retry_text",
        "error",
    ):
        if key in final_result:
            compact[key] = final_result.get(key)
    if _is_triage_skipped_final_result(final_result):
        for key in ("why_log", "injury_triage", "full_name"):
            if key in final_result:
                compact[key] = final_result.get(key)
    # Preserve the durable profile-refresh-failed marker on every path (not just
    # triage): the plan row keeps the full why_log, but the lean job final_result
    # must still carry this one key so job.warnings survives milestone eviction.
    why_log = final_result.get("why_log")
    if isinstance(why_log, dict) and PROFILE_REFRESH_FAILED_WHY_LOG_KEY in why_log:
        compact_why_log = compact.get("why_log")
        compact_why_log = dict(compact_why_log) if isinstance(compact_why_log, dict) else {}
        compact_why_log[PROFILE_REFRESH_FAILED_WHY_LOG_KEY] = why_log[PROFILE_REFRESH_FAILED_WHY_LOG_KEY]
        compact["why_log"] = compact_why_log
    return compact


def _is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "y", "on"}
    return False


def should_skip_stage2(stage1_result: dict[str, Any], *, allow_triage_resume_override: bool = False) -> bool:
    status_value = str(stage1_result.get("status") or "").strip().lower()
    if status_value == "triage_blocked":
        return not allow_triage_resume_override

    injury_triage = stage1_result.get("injury_triage")
    if isinstance(injury_triage, dict):
        if _is_truthy_flag(injury_triage.get("should_block_stage2")):
            return False if allow_triage_resume_override else True
        triage_mode = str(injury_triage.get("mode") or "").strip().lower()
        if triage_mode in {"medical_hold", "restricted_rehab_only", "needs_review"}:
            return False if allow_triage_resume_override else True

    why_log = stage1_result.get("why_log")
    if isinstance(why_log, dict):
        why_log_triage = why_log.get("injury_triage")
        if isinstance(why_log_triage, dict):
            if _is_truthy_flag(why_log_triage.get("should_block_stage2")):
                return False if allow_triage_resume_override else True
            triage_mode = str(why_log_triage.get("mode") or "").strip().lower()
            if triage_mode in {"medical_hold", "restricted_rehab_only", "needs_review"}:
                return False if allow_triage_resume_override else True

    return False
