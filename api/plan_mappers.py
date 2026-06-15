"""Profile/plan response mappers extracted from api.app (PR2: pure helpers)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from fightcamp.stage2_policy import is_hard_stage2_blocker
from fightcamp.sparring_advisories import build_plan_advisories
from fightcamp.weekly_schedule_view import extract_weekly_schedule

from .models import (
    AdminAthleteRecord,
    AdminPlanOutputs,
    AdminPlanSummary,
    MeResponse,
    PlanDetail,
    PlanOutputs,
    PlanSafetyState,
    PlanSummary,
    ProfileRecord,
    USERNAME_CHANGE_WINDOW_DAYS,
    USERNAME_MAX_CHANGES_PER_WINDOW,
    UsernameRateLimitInfo,
    WeeklySchedule,
)
from .store import AppStore
from .structured_plan_models import StructuredTrainingPlan, safe_parse_structured_plan


def _build_me_response(profile: ProfileRecord, store: AppStore) -> MeResponse:
    latest_intake = store.get_latest_intake(profile.athlete_id)
    plans = _visible_plans_for_athlete(store.list_user_plans(profile.athlete_id))
    latest_plan = _map_plan_summary(plans[0]) if plans else None
    return MeResponse(
        profile=profile,
        latest_intake=latest_intake.get("intake") if latest_intake else None,
        latest_plan=latest_plan,
        plan_count=len(plans),
        username_rate_limit=_username_rate_limit_info(profile.username_change_history),
    )


def _decode_structured_text(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            return {"raw": stripped}
        return decoded if isinstance(decoded, dict) else {"raw": decoded}
    return {"raw": value}


def _map_profile_row(row: dict[str, Any]) -> ProfileRecord:
    raw_username = row.get("username")
    history_raw = row.get("username_change_history") or []
    username_history: list[str] = [str(entry) for entry in history_raw if entry]
    return ProfileRecord(
        athlete_id=str(row["id"]),
        email=str(row.get("email") or ""),
        username=str(raw_username) if raw_username else None,
        username_change_history=username_history,
        role=str(row.get("role") or "athlete"),
        full_name=str(row.get("full_name") or ""),
        technical_style=list(row.get("technical_style") or []),
        tactical_style=list(row.get("tactical_style") or []),
        stance=str(row.get("stance") or ""),
        professional_status=str(row.get("professional_status") or ""),
        record=str(row.get("record_summary") or ""),
        athlete_timezone=str(row.get("athlete_timezone") or ""),
        athlete_locale=str(row.get("athlete_locale") or ""),
        appearance_mode=str(row.get("appearance_mode") or "dark"),
        onboarding_draft=row.get("onboarding_draft"),
        avatar_url=row.get("avatar_url") or None,
        nutrition_profile=row.get("nutrition_profile") or {},
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _username_rate_limit_info(history: list[str]) -> UsernameRateLimitInfo:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=USERNAME_CHANGE_WINDOW_DAYS)
    recent: list[datetime] = []
    for entry in history:
        try:
            parsed = datetime.fromisoformat(str(entry).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed >= cutoff:
            recent.append(parsed)
    remaining = max(0, USERNAME_MAX_CHANGES_PER_WINDOW - len(recent))
    next_available_at: str | None = None
    if remaining == 0 and recent:
        next_available_at = (min(recent) + timedelta(days=USERNAME_CHANGE_WINDOW_DAYS)).isoformat()
    return UsernameRateLimitInfo(
        remaining=remaining,
        next_available_at=next_available_at,
    )


def _map_plan_summary(row: dict[str, Any]) -> PlanSummary:
    raw_status = str(row.get("status") or "generated")
    normalized_status = raw_status
    if raw_status == "review_required":
        report = row.get("stage2_validator_report") if isinstance(row.get("stage2_validator_report"), dict) else {}
        report_exists = bool(report)
        if not report_exists:
            normalized_status = "held_for_review"
        else:
            has_errors = bool(report.get("errors"))
            blocking_warnings = [
                warning
                for warning in (report.get("blocking_warnings") or [])
                if isinstance(warning, dict)
                and is_hard_stage2_blocker(str(warning.get("code") or ""))
            ]
            has_blocking = bool(blocking_warnings)
            if not has_blocking:
                warnings = list(report.get("warnings") or [])
                has_blocking = any(
                    is_hard_stage2_blocker(str(w.get("code") or ""))
                    for w in warnings
                    if isinstance(w, dict)
                )
            normalized_status = "held_for_review" if has_errors or has_blocking else "ready"
    return PlanSummary(
        plan_id=str(row["id"]),
        plan_name=(str(row["plan_name"]).strip() if row.get("plan_name") is not None else None) or None,
        athlete_id=str(row["athlete_id"]),
        full_name=str(row.get("full_name") or ""),
        fight_date=str(row.get("fight_date") or ""),
        technical_style=list(row.get("technical_style") or []),
        created_at=str(row.get("created_at") or ""),
        status=normalized_status,
        pdf_url=row.get("pdf_url"),
    )


def _is_archived_plan(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    return str(row.get("status") or "").strip().lower() == "archived"


def _is_triage_blocked_plan(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    return str(row.get("status") or "").strip().lower() == "triage_blocked"


def _visible_plans_for_athlete(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Triage-blocked outcomes are screening decisions, not plans — they must
    # not surface in the athlete's archive or "latest plan" snapshot. Admin
    # endpoints bypass this filter so the ops team can still review and
    # approve-and-resume blocked attempts.
    return [
        row
        for row in rows
        if not _is_archived_plan(row) and not _is_triage_blocked_plan(row)
    ]


def _admin_draft_text(row: dict[str, Any]) -> str:
    return str(row.get("draft_plan_text") or row.get("plan_text") or "")


def _admin_final_text(row: dict[str, Any]) -> str:
    return str(row.get("final_plan_text") or row.get("plan_text") or "")


def _map_plan_safety_state(row: dict[str, Any]) -> PlanSafetyState:
    triage = {}
    why_log = row.get("why_log")
    if isinstance(why_log, dict):
        triage = why_log.get("injury_triage") or {}
    if not isinstance(triage, dict):
        triage = {}

    mode = str(triage.get("mode") or "")
    triage_blocked = str(row.get("status") or "").strip().lower() == "triage_blocked"
    stage2_was_skipped = bool(triage.get("should_block_stage2")) or triage_blocked
    if mode == "medical_hold":
        return PlanSafetyState(
            state="medical_hold",
            status_chip="MEDICAL HOLD",
            header="Medical hold: no training plan generated",
            subtext=(
                "Urgent neurological or medical red-flag signals were detected. "
                "Planning was intentionally blocked before normal generation."
            ),
            stage2_skipped=stage2_was_skipped,
            clinician_clearance_required=bool(triage.get("clinician_clearance_required", True)),
            matched_high_risk_categories=list(triage.get("matched_high_risk_categories") or []),
            red_flags=list(triage.get("red_flags") or []),
            sparring_risk_band=triage.get("sparring_risk_band"),
            next_steps=[
                "Seek appropriate medical review before training guidance.",
                "Update the intake after clearance.",
                "Regenerate only when medically cleared.",
            ],
        )
    if mode == "restricted_rehab_only":
        return PlanSafetyState(
            state="restricted_rehab_only",
            status_chip="RESTRICTED REHAB ONLY",
            header="Planning paused: clinician clearance required",
            subtext=(
                "Serious structural injury signals were detected. "
                "Normal fight-camp generation is paused to avoid unsafe loading recommendations."
            ),
            stage2_skipped=stage2_was_skipped,
            clinician_clearance_required=bool(triage.get("clinician_clearance_required", True)),
            matched_high_risk_categories=list(triage.get("matched_high_risk_categories") or []),
            red_flags=list(triage.get("red_flags") or []),
            sparring_risk_band=triage.get("sparring_risk_band"),
            next_steps=[
                "Review injury details and current restrictions.",
                "Update the intake after clinician clearance.",
                "Regenerate normal planning only when safe.",
            ],
        )
    if mode == "needs_review":
        return PlanSafetyState(
            state="needs_review",
            status_chip="NEEDS REVIEW",
            header="Safety review required before planning",
            subtext=(
                "Guided injury severity/trend combinations triggered a conservative safety gate. "
                "Automatic planning is paused pending coach/admin review."
            ),
            stage2_skipped=stage2_was_skipped,
            clinician_clearance_required=bool(triage.get("clinician_clearance_required", False)),
            matched_high_risk_categories=list(triage.get("matched_high_risk_categories") or []),
            red_flags=list(triage.get("red_flags") or []),
            sparring_risk_band=triage.get("sparring_risk_band"),
            next_steps=[
                "Review guided injury severity/trend details.",
                "Clarify diagnosis progression and restrictions.",
                "Approve before rerunning full planning.",
            ],
        )

    return PlanSafetyState(
        state="plan_ready",
        status_chip="PLAN READY",
        header="Plan ready",
        subtext="Normal planning completed.",
        stage2_skipped=False,
        clinician_clearance_required=False,
        matched_high_risk_categories=[],
        red_flags=[],
        sparring_risk_band=None,
        next_steps=[],
    )


_ALLOWED_PLAN_SOURCES: frozenset[str] = frozenset({"quick_build", "self_serve"})


def _lookup_plan_source(store: AppStore, plan_id: str) -> str | None:
    job = store.get_generation_job_by_plan_id(plan_id)
    if not isinstance(job, dict):
        return None
    raw = job.get("source")
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if value in _ALLOWED_PLAN_SOURCES else None


def _map_plan_detail(
    row: dict[str, Any],
    *,
    include_admin: bool,
    plan_source: str | None = None,
) -> PlanDetail:
    summary = _map_plan_summary(row)
    planning_brief = _decode_structured_text(row.get("planning_brief"))
    raw_stage2_payload = row.get("stage2_payload")
    fallback_parsing_metadata = (
        raw_stage2_payload.get("input_parsing_metadata")
        if isinstance(raw_stage2_payload, dict)
        else {}
    )
    parsing_metadata = row.get("parsing_metadata") or fallback_parsing_metadata or {}
    display_plan_text = str(row.get("plan_text") or "")
    is_legacy_review_required = str(row.get("status") or "").strip().lower() == "review_required"
    if (
        not display_plan_text
        and is_legacy_review_required
        and summary.status in {"ready", "publishable_with_flags"}
    ):
        display_plan_text = str(row.get("final_plan_text") or "")
    structured_plan, structured_schema_version = _decode_structured_plan(
        row.get("structured_plan"),
        raw_markdown=display_plan_text,
    )
    report_dict = row.get("stage2_validator_report")
    report_dict = report_dict if isinstance(report_dict, dict) else {}
    structured_debug = report_dict.get("structured_plan")
    structured_debug = structured_debug if isinstance(structured_debug, dict) else {}
    return PlanDetail(
        **summary.model_dump(mode="json"),
        outputs=PlanOutputs(
            plan_text=display_plan_text,
            pdf_url=row.get("pdf_url"),
            structured_plan=structured_plan,
            schema_version=structured_schema_version,
        ),
        safety_state=_map_plan_safety_state(row),
        advisories=build_plan_advisories(planning_brief=planning_brief),
        plan_source=plan_source,
        admin_outputs=(
            AdminPlanOutputs(
                coach_notes=str(row.get("coach_notes") or ""),
                why_log=row.get("why_log") or {},
                planning_brief=planning_brief,
                stage2_payload=raw_stage2_payload,
                parsing_metadata=parsing_metadata if isinstance(parsing_metadata, dict) else {},
                stage2_handoff_text=str(row.get("stage2_handoff_text") or ""),
                draft_plan_text=_admin_draft_text(row),
                final_plan_text=_admin_final_text(row),
                stage2_retry_text=str(row.get("stage2_retry_text") or ""),
                stage2_validator_report=row.get("stage2_validator_report") or {},
                stage2_status=str(row.get("stage2_status") or "legacy"),
                stage2_attempt_count=int(row.get("stage2_attempt_count") or 0),
                structured_plan_status=str(structured_debug.get("status") or "not_attempted"),
                structured_plan_errors=[str(err) for err in (structured_debug.get("errors") or [])],
                structured_schema_version=(
                    structured_schema_version or structured_debug.get("schema_version")
                ),
            )
            if include_admin
            else None
        ),
    )


def _decode_structured_plan(
    value: Any,
    *,
    raw_markdown: str = "",
) -> tuple[StructuredTrainingPlan | None, str | None]:
    """Best-effort decode of a stored structured plan column.

    Legacy plans have no structured payload, so this returns ``(None, None)``
    for missing/blank values. Malformed structured data never breaks the
    response: it is dropped and the raw markdown fallback still flows through
    ``plan_text``.
    """

    decoded = _decode_structured_text(value)
    # `_decode_structured_text` wraps non-JSON strings as {"raw": ...}; that is
    # not a structured plan, so treat it (and empty values) as "no structured".
    if not decoded or (len(decoded) == 1 and "raw" in decoded):
        return None, None
    result = safe_parse_structured_plan(decoded, raw_markdown=raw_markdown or None)
    if not result.ok or result.plan is None:
        return None, None
    return result.plan, result.plan.schema_version


def _map_weekly_schedule(row: dict[str, Any], *, week_index: int) -> WeeklySchedule:
    planning_brief = _decode_structured_text(row.get("planning_brief"))
    schedule = extract_weekly_schedule(
        planning_brief,
        week_index=week_index,
        fight_date=row.get("fight_date"),
    )
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="weekly schedule not found")
    return WeeklySchedule(plan_id=str(row["id"]), **schedule)


def _map_admin_plan_summary(row: dict[str, Any]) -> AdminPlanSummary:
    profile = row.get("profiles") or {}
    summary = _map_plan_summary(row)
    return AdminPlanSummary(
        **summary.model_dump(mode="json"),
        athlete_email=str(profile.get("email") or ""),
        profile_unavailable=bool(row.get("profile_enrichment_failed")),
    )


def _map_admin_athlete(row: dict[str, Any], latest_intake: dict[str, Any] | None = None) -> AdminAthleteRecord:
    onboarding_draft = row.get("onboarding_draft")
    return AdminAthleteRecord(
        athlete_id=str(row["id"]),
        email=str(row.get("email") or ""),
        role=str(row.get("role") or "athlete"),
        full_name=str(row.get("full_name") or ""),
        technical_style=list(row.get("technical_style") or []),
        tactical_style=list(row.get("tactical_style") or []),
        stance=str(row.get("stance") or ""),
        professional_status=str(row.get("professional_status") or ""),
        record=str(row.get("record") or row.get("record_summary") or ""),
        athlete_timezone=str(row.get("athlete_timezone") or ""),
        athlete_locale=str(row.get("athlete_locale") or ""),
        appearance_mode=str(row.get("appearance_mode") or "dark"),
        onboarding_draft=onboarding_draft if isinstance(onboarding_draft, dict) else None,
        latest_intake=latest_intake.get("intake") if isinstance(latest_intake, dict) else None,
        nutrition_profile=row.get("nutrition_profile") or {},
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        plan_count=int(row.get("plan_count") or 0),
        latest_plan_created_at=row.get("latest_plan_created_at"),
    )
