from __future__ import annotations

import copy
import math
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from api.app import create_app
from api.auth import AuthenticatedUser
from api.errors import client_request_id_payload_mismatch_error
from api.generation.payloads import _stable_payload_hash
from api.models import (
    PlanRequest,
    ProfileUpdateRequest,
    USERNAME_CHANGE_WINDOW_DAYS,
    USERNAME_MAX_CHANGES_PER_WINDOW,
    validate_username,
)
from api.state_machine import (
    is_generation_job_status,
    is_plan_status,
    require_generation_job_transition,
    require_plan_transition,
)
from api.generation_config import generation_worker_id
from api.schema_requirements import GENERATION_JOB_STAGE2_COST_COLUMNS
from api.store import _generation_startup_max_attempts, is_job_loaded_stalled_generation_job, is_stage1_planner_stalled_generation_job, is_startup_stale_generation_job
from datetime import timedelta

os.environ.setdefault("APP_GENERATION_SCHEDULER", "fastapi")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _latest_job_activity_at(job: dict) -> datetime | None:
    latest: datetime | None = None
    for field_name in ("heartbeat_at", "updated_at", "started_at", "created_at"):
        parsed = _parse_iso(job.get(field_name))
        if parsed is not None and (latest is None or parsed > latest):
            latest = parsed
    for milestone in job.get("progress_milestones") or []:
        if not isinstance(milestone, dict):
            continue
        parsed = _parse_iso(milestone.get("at"))
        if parsed is not None and (latest is None or parsed > latest):
            latest = parsed
    return latest


def _status_transition_error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _filter_admin_rows(rows: list[dict], q: str | None, columns: tuple[str, ...]) -> list[dict]:
    """Mirror the server-side ``q`` search the real store performs in Postgres:
    a case-insensitive substring match across the given text columns."""
    term = " ".join((q or "").split()).lower()
    if not term:
        return rows
    return [
        row
        for row in rows
        if any(term in str(row.get(column) or "").lower() for column in columns)
    ]


@dataclass
class FakeAuthService:
    users_by_token: dict[str, AuthenticatedUser]

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        user = self.users_by_token.get(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            )
        return user


class FakeStore:
    def __init__(self, admin_emails: set[str] | None = None):
        self.profiles: dict[str, dict] = {}
        self.intakes: dict[str, list[dict]] = {}
        self.plans: dict[str, dict] = {}
        self.active_plan_ids: dict[str, str] = {}
        self.generation_jobs: dict[str, dict] = {}
        self.daily_checkins: dict[str, list[dict]] = {}
        self.session_logs: dict[str, list[dict]] = {}
        self.today_checkins: dict[str, list[dict]] = {}
        self.session_completions: dict[str, list[dict]] = {}
        self.injury_flags: dict[str, list[dict]] = {}
        self.adaptation_notes: dict[str, list[dict]] = {}
        self.admin_reviews: list[dict] = []
        self.get_admin_athlete_calls = 0
        self.list_admin_athletes_by_ids_calls = 0
        # When True, admin-queue profile enrichment degrades to id-only rows
        # tagged with ``profile_enrichment_failed`` (mirrors a profiles outage).
        self.fail_profile_enrichment = False
        self.admin_emails: set[str] = {
            email.strip().lower() for email in (admin_emails or set()) if email
        }
        self._plan_generation_limit_events: dict[str, list[datetime]] = {}
        self._generation_job_daily_limit_lock = threading.RLock()

    def validate_runtime_schema(self) -> None:
        return None

    def check_plan_generation_short_window_limit(
        self,
        athlete_id: str,
        max_requests: int,
        window_seconds: float,
    ) -> tuple[bool, int]:
        if max_requests <= 0:
            return True, 0
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=max(1.0, window_seconds))
        bucket = [
            ts for ts in self._plan_generation_limit_events.get(athlete_id, [])
            if ts > cutoff
        ]
        self._plan_generation_limit_events[athlete_id] = bucket
        if len(bucket) >= max_requests:
            retry_after = max(
                1,
                math.ceil(max(1.0, window_seconds) - (now - bucket[0]).total_seconds()),
            )
            return False, retry_after
        bucket.append(now)
        return True, 0

    def is_admin_email(self, email: str) -> bool:
        if not email:
            return False
        normalized = email.strip().lower()
        if normalized in self.admin_emails:
            return True
        # Mirror ensure_profile's @unlxck.test test pattern so existing fixtures
        # do not need to register every admin email explicitly.
        return normalized.endswith("@unlxck.test")

    def _is_admin_email(self, email: str) -> bool:
        return self.is_admin_email(email)

    def _classify_running_job_staleness(self, job: dict, *, stale_after_seconds: int) -> str:
        if str(job.get("status") or "") != "running":
            return "fresh"
        raw_stage1_timeout = os.getenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "240").strip()
        try:
            stage1_stale_after_seconds = max(1, int(float(raw_stage1_timeout)))
        except (TypeError, ValueError):
            stage1_stale_after_seconds = 240
        if raw_stage1_timeout in {"", "0", "none", "None", "NONE"}:
            stage1_stale_after_seconds = 240
        if is_job_loaded_stalled_generation_job(job, stale_after_seconds=stale_after_seconds):
            return "job_loaded_stalled"
        if is_startup_stale_generation_job(job, stale_after_seconds=stale_after_seconds):
            return "startup_stale"
        if is_stage1_planner_stalled_generation_job(job, stale_after_seconds=stage1_stale_after_seconds):
            return "stage1_planner_stalled"
        reference = _latest_job_activity_at(job)
        if reference is None:
            return "fresh"
        age = (datetime.now(timezone.utc) - reference).total_seconds()
        return "fresh" if age < max(1, stale_after_seconds) else "mid_pipeline_stale"

    def ensure_profile(self, user: AuthenticatedUser) -> dict:
        existing = self.profiles.get(user.user_id)
        if existing:
            existing["updated_at"] = _now()
            return existing
        role = "admin" if self._is_admin_email(user.email) else "athlete"
        profile = {
            "id": user.user_id,
            "email": user.email,
            "username": None,
            "username_change_history": [],
            "role": role,
            "full_name": user.full_name,
            "technical_style": [],
            "tactical_style": [],
            "stance": "",
            "professional_status": "",
            "record_summary": "",
            "athlete_timezone": "",
            "athlete_locale": "",
            "appearance_mode": "dark",
            "onboarding_draft": None,
            "nutrition_profile": {},
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.profiles[user.user_id] = profile
        return profile

    def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict:
        profile = self.profiles[athlete_id]
        data = update.model_dump(mode="json", exclude_none=True)
        if "record" in data:
            data["record_summary"] = data.pop("record")
        profile.update(data)
        profile["updated_at"] = _now()
        return profile

    def change_username(self, athlete_id: str, username: str) -> dict:
        profile = self.profiles[athlete_id]
        normalized = validate_username(username)
        current = (profile.get("username") or "").lower() or None
        if normalized == current:
            return profile
        for other_id, other_profile in self.profiles.items():
            if other_id == athlete_id:
                continue
            if (other_profile.get("username") or "").lower() == normalized:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="That username is already taken. Pick another.",
                )
        history_raw = profile.get("username_change_history") or []
        history: list[str] = [str(entry) for entry in history_raw if entry]
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=USERNAME_CHANGE_WINDOW_DAYS)
        recent: list[datetime] = []
        for entry in history:
            try:
                parsed = datetime.fromisoformat(entry.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed >= cutoff:
                recent.append(parsed)
        if len(recent) >= USERNAME_MAX_CHANGES_PER_WINDOW:
            earliest = min(recent)
            next_available = earliest + timedelta(days=USERNAME_CHANGE_WINDOW_DAYS)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"You can change your username up to {USERNAME_MAX_CHANGES_PER_WINDOW} times "
                    f"every {USERNAME_CHANGE_WINDOW_DAYS} days. "
                    f"Next change available {next_available.isoformat()}."
                ),
            )
        profile["username"] = normalized
        profile["username_change_history"] = [entry.isoformat() for entry in recent] + [now.isoformat()]
        profile["updated_at"] = _now()
        return profile

    def get_latest_intake(self, athlete_id: str) -> dict | None:
        items = self.intakes.get(athlete_id, [])
        return items[-1] if items else None

    def get_intake(self, intake_id: str) -> dict | None:
        for items in self.intakes.values():
            for intake in items:
                if intake["id"] == intake_id:
                    return intake
        return None

    def create_intake(self, athlete_id: str, request: PlanRequest) -> dict:
        intake = {
            "id": f"intake_{uuid4().hex[:10]}",
            "athlete_id": athlete_id,
            "fight_date": None if request.no_scheduled_fight else (request.fight_date.strip() or None),
            "technical_style": request.athlete.technical_style,
            "intake": request.model_dump(mode="json"),
            "created_at": _now(),
        }
        self.intakes.setdefault(athlete_id, []).append(intake)
        return intake

    def update_intake(
        self,
        intake_id: str,
        *,
        intake: dict,
        fight_date: str | None,
        technical_style: list[str],
    ) -> dict:
        for athlete_intakes in self.intakes.values():
            for row in athlete_intakes:
                if row["id"] != intake_id:
                    continue
                row["intake"] = intake
                row["fight_date"] = fight_date
                row["technical_style"] = technical_style
                row["updated_at"] = _now()
                return row
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="intake not found")

    def create_plan(self, *, athlete_id: str, intake_id: str, request: PlanRequest, result: dict) -> dict:
        profile = self.profiles[athlete_id]
        plan_id = str(uuid4())
        result_status = str(result.get("status") or "generated").strip().lower()
        if not is_plan_status(result_status):
            raise _status_transition_error(f"unknown plan status: {result_status!r}")
        row = {
            "id": plan_id,
            "athlete_id": athlete_id,
            "intake_id": intake_id,
            "fight_date": request.fight_date.strip() or None,
            "technical_style": request.athlete.technical_style,
            "plan_name": "",
            "status": result_status,
            "plan_text": result.get("plan_text", ""),
            "draft_plan_text": result.get("draft_plan_text", result.get("plan_text", "")),
            "final_plan_text": result.get("final_plan_text", result.get("plan_text", "")),
            "coach_notes": result.get("coach_notes", ""),
            "pdf_url": result.get("pdf_url"),
            "why_log": result.get("why_log", {}),
            "planning_brief": result.get("planning_brief"),
            "stage2_payload": result.get("stage2_payload"),
            "parsing_metadata": result.get("parsing_metadata", {}),
            "stage2_handoff_text": result.get("stage2_handoff_text", ""),
            "stage2_retry_text": result.get("stage2_retry_text", ""),
            "stage2_validator_report": result.get("stage2_validator_report", {}),
            "stage2_status": result.get("stage2_status", ""),
            "stage2_attempt_count": result.get("stage2_attempt_count", 0),
            "structured_plan": result.get("structured_plan"),
            "schema_version": result.get("schema_version"),
            "created_at": _now(),
            "full_name": profile["full_name"],
        }
        self.plans[plan_id] = row
        return row

    def list_user_plans(self, athlete_id: str) -> list[dict]:
        rows = [plan for plan in self.plans.values() if plan["athlete_id"] == athlete_id]
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def get_plan(self, plan_id: str) -> dict | None:
        return self.plans.get(plan_id)

    def get_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict | None:
        row = self.plans.get(plan_id)
        if not row or str(row.get("athlete_id")) != athlete_id:
            return None
        return row

    def get_latest_plan(self, athlete_id: str) -> dict | None:
        plans = self.list_user_plans(athlete_id)
        return plans[0] if plans else None

    def get_active_plan_id(self, athlete_id: str) -> str | None:
        return self.active_plan_ids.get(athlete_id)

    def set_active_plan_id(self, athlete_id: str, plan_id: str) -> None:
        self.active_plan_ids[athlete_id] = plan_id

    def rename_plan(self, plan_id: str, plan_name: str) -> dict:
        row = self.plans.get(plan_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        row["plan_name"] = plan_name
        return row

    def rename_plan_for_athlete(self, plan_id: str, athlete_id: str, plan_name: str) -> dict:
        row = self.get_plan_for_athlete(plan_id, athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        row["plan_name"] = plan_name
        return row

    def archive_plan(self, plan_id: str) -> dict:
        if plan_id not in self.plans:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        row = self.plans[plan_id]
        try:
            row["status"] = require_plan_transition(row.get("status") or "generated", "archived")
        except ValueError as exc:
            raise _status_transition_error(str(exc)) from exc
        return row

    def archive_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict:
        row = self.get_plan_for_athlete(plan_id, athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        try:
            row["status"] = require_plan_transition(row.get("status") or "generated", "archived")
        except ValueError as exc:
            raise _status_transition_error(str(exc)) from exc
        return row

    def delete_plan(self, plan_id: str) -> None:
        if plan_id not in self.plans:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        del self.plans[plan_id]

    def delete_plan_for_athlete(self, plan_id: str, athlete_id: str) -> None:
        row = self.get_plan_for_athlete(plan_id, athlete_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        del self.plans[plan_id]

    def create_or_get_generation_job(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict,
        plan_id: str | None = None,
        intake_id: str | None = None,
        stale_after_seconds: int = 90,
    ) -> dict:
        payload_hash = _stable_payload_hash(request_payload)
        self._fail_stale_active_generation_jobs_for_athlete(
            athlete_id,
            stale_after_seconds=stale_after_seconds,
        )
        for job in self.generation_jobs.values():
            if job["athlete_id"] == athlete_id and job["client_request_id"] == client_request_id:
                if is_startup_stale_generation_job(job, stale_after_seconds=stale_after_seconds):
                    now = _now()
                    reset_changes = {
                        "source": source,
                        "request_payload": request_payload,
                        "payload_hash": payload_hash,
                        "status": "queued",
                        "error": None,
                        "stage1_result": None,
                        "final_result": None,
                        "heartbeat_at": None,
                        "started_at": None,
                        "completed_at": None,
                        "progress_milestones": [],
                        "claimed_by": None,
                        "claimed_at": None,
                        "updated_at": now,
                    }

                    if plan_id is not None:
                        reset_changes["plan_id"] = plan_id
                    if intake_id is not None:
                        reset_changes["intake_id"] = intake_id

                    job.update(reset_changes)
                existing_hash = job.get("payload_hash")
                if existing_hash and str(existing_hash) != payload_hash:
                    raise client_request_id_payload_mismatch_error()
                return dict(job)
        active = self.reconcile_active_generation_job_for_athlete(athlete_id, stale_after_seconds=stale_after_seconds)
        # Mirror SupabaseAppStore.create_or_get_generation_job: only a job that is
        # still queued/running blocks a new request. reconcile_active_generation_job_for_athlete
        # recovers a stale running job to a terminal status (e.g. failed) and returns
        # it; such a job must not be treated as in-flight, otherwise a mid-pipeline
        # stale job would wrongly 409 a new request instead of being superseded.
        if active and str(active.get("status") or "") in {"queued", "running"}:
            if str(active.get("client_request_id") or "") == client_request_id:
                existing_hash = active.get("payload_hash")
                if existing_hash and str(existing_hash) != payload_hash:
                    raise client_request_id_payload_mismatch_error()
                return dict(active)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A generation job is already queued or running for this account.",
            )
        now = _now()
        job_id = f"job_{uuid4().hex[:10]}"
        job = {
            "id": job_id,
            "athlete_id": athlete_id,
            "client_request_id": client_request_id,
            "source": source,
            "request_payload": request_payload,
            "payload_hash": payload_hash,
            "status": "queued",
            "error": None,
            "intake_id": intake_id,
            "stage1_result": None,
            "final_result": None,
            "plan_id": plan_id,
            "attempt_count": 0,
            "heartbeat_at": None,
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "claimed_by": None,
            "claimed_at": None,
            "progress_milestones": [],
            "created_at": now,
            "updated_at": now,
        }
        self.generation_jobs[job_id] = job
        return dict(job)

    def _fail_stale_active_generation_jobs_for_athlete(
        self,
        athlete_id: str,
        *,
        stale_after_seconds: int,
        exclude_client_request_id: str | None = None,
    ) -> None:
        cutoff_seconds = max(1, stale_after_seconds)
        now_dt = datetime.now(timezone.utc)
        now = _now()
        for job in self.generation_jobs.values():
            if str(job.get("athlete_id") or "") != athlete_id:
                continue
            if exclude_client_request_id and str(job.get("client_request_id") or "") == exclude_client_request_id:
                continue
            if str(job.get("status") or "") not in {"queued", "running"}:
                continue
        cutoff_seconds = max(1, stale_after_seconds)
        now_dt = datetime.now(timezone.utc)
        now = _now()
        for job in self.generation_jobs.values():
            if str(job.get("athlete_id") or "") != athlete_id:
                continue
            if str(job.get("status") or "") not in {"queued", "running"}:
                continue
            latest = _latest_job_activity_at(job)
            if latest is None:
                continue
            latest = latest.astimezone(timezone.utc)
            if (now_dt - latest).total_seconds() < cutoff_seconds:
                continue
            milestones = list(job.get("progress_milestones") or [])
            if not any(isinstance(item, dict) and item.get("code") == "stale_job_reaped" for item in milestones):
                milestones.append(
                    {
                        "code": "stale_job_reaped",
                        "label": "Stale job reaped",
                        "detail": "Job activity timed out and was failed so a new generation can start.",
                        "meta": {},
                        "at": now,
                    }
                )
            job.update(
                {
                    "status": "failed",
                    "error": "Generation job stalled. Please try again.",
                    "completed_at": now,
                    "failed_at": now,
                    "heartbeat_at": now,
                    "progress_milestones": milestones,
                    "updated_at": now,
                }
            )

    def create_or_get_generation_job_with_daily_limit(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict,
        daily_limit: int,
        day_start_iso: str,
        limit_reached_detail: str,
        counted_sources: set[str],
        plan_id: str | None = None,
        intake_id: str | None = None,
        stale_after_seconds: int = 90,
    ) -> dict:
        with self._generation_job_daily_limit_lock:
            payload_hash = _stable_payload_hash(request_payload)
            for job in self.generation_jobs.values():
                if job["athlete_id"] == athlete_id and job["client_request_id"] == client_request_id:
                    existing_hash = job.get("payload_hash")
                    if existing_hash and str(existing_hash) != payload_hash:
                        raise client_request_id_payload_mismatch_error()
                    return dict(job)
            if daily_limit > 0:
                jobs_today = self.count_generation_jobs_for_athlete_since(
                    athlete_id,
                    day_start_iso,
                    sources=counted_sources,
                )
                if jobs_today >= daily_limit:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=limit_reached_detail,
                    )
            return self.create_or_get_generation_job(
                athlete_id=athlete_id,
                client_request_id=client_request_id,
                source=source,
                request_payload=request_payload,
                plan_id=plan_id,
                intake_id=intake_id,
                stale_after_seconds=stale_after_seconds,
            )

    def get_generation_job(self, job_id: str) -> dict | None:
        job = self.generation_jobs.get(job_id)
        return dict(job) if job else None

    def recover_generation_job_if_stale(self, job: dict | None) -> dict | None:
        if not job or str(job.get("status") or "") != "running":
            return dict(job) if job else None
        live = self.generation_jobs.get(str(job.get("id") or ""))
        if live is None:
            return dict(job)
        staleness = self._classify_running_job_staleness(live, stale_after_seconds=90)
        if staleness == "job_loaded_stalled":
            milestones = list(live.get("progress_milestones") or [])
            now = _now()
            if int(live.get("attempt_count") or 0) < 2:
                milestones.append({"code": "worker_claim_stalled_requeued", "label": "Worker claim stalled", "detail": "Worker loaded the generation job but did not reach request parsing; job was requeued for recovery.", "meta": {}, "at": now})
                live.update({"status": "queued", "error": None, "started_at": None, "heartbeat_at": None, "completed_at": None, "progress_milestones": milestones, "claimed_by": None, "claimed_at": None, "updated_at": now})
            else:
                milestones.append({"code": "worker_claim_stalled_failed", "label": "Worker stalled after loading job", "detail": "Worker loaded the generation job but did not reach request parsing after retry.", "meta": {}, "at": now})
                live.update({"status": "failed", "error": "Generation worker stalled after loading the job.", "completed_at": now, "heartbeat_at": now, "progress_milestones": milestones, "updated_at": now})
        if staleness == "stage1_planner_stalled":
            now = _now()
            milestones = list(live.get("progress_milestones") or [])
            milestones.append(
                {
                    "code": "stage1_planner_timeout",
                    "label": "Stage 1 planner timed out",
                    "detail": "Planner did not return after invocation and the job was failed for recovery.",
                    "meta": {},
                    "at": now,
                }
            )
            live.update(
                {
                    "status": "failed",
                    "error": "Stage 1 planner stalled after planner invocation.",
                    "completed_at": now,
                    "heartbeat_at": now,
                    "progress_milestones": milestones,
                    "updated_at": now,
                }
            )
        return dict(live)

    def get_generation_job_by_client_request_id(self, *, athlete_id: str, client_request_id: str) -> dict | None:
        for job in self.generation_jobs.values():
            if job["athlete_id"] == athlete_id and job["client_request_id"] == client_request_id:
                return dict(job)
        return None

    def get_visible_active_generation_job_for_athlete(self, athlete_id: str) -> dict | None:
        rows = [
            dict(job)
            for job in self.generation_jobs.values()
            if str(job.get("athlete_id") or "") == athlete_id
            and str(job.get("status") or "") in {"queued", "running"}
        ]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows[0] if rows else None

    def reconcile_active_generation_job_for_athlete(
        self,
        athlete_id: str,
        *,
        stale_after_seconds: int = 90,
    ) -> dict | None:
        rows = [
            job
            for job in self.generation_jobs.values()
            if str(job.get("athlete_id") or "") == athlete_id and str(job.get("status") or "") in {"queued", "running"}
        ]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        for row in rows[:10]:
            if str(row.get("status") or "") == "queued":
                return dict(row)
            staleness = self._classify_running_job_staleness(row, stale_after_seconds=stale_after_seconds)
            if staleness == "fresh":
                return dict(row)
            if staleness == "startup_stale":
                now = _now()
                row.update(
                    {
                        "status": "queued",
                        "error": None,
                        "heartbeat_at": None,
                        "started_at": None,
                        "completed_at": None,
                        "stage1_result": None,
                        "final_result": None,
                        "progress_milestones": [],
                        "claimed_by": None,
                        "claimed_at": None,
                        "updated_at": now,
                    }
                )
            elif staleness == "job_loaded_stalled":
                now = _now()
                milestones = list(row.get("progress_milestones") or [])
                if int(row.get("attempt_count") or 0) < 2:
                    milestones.append({"code": "worker_claim_stalled_requeued", "label": "Worker claim stalled", "detail": "Worker loaded the generation job but did not reach request parsing; job was requeued for recovery.", "meta": {}, "at": now})
                    row.update({"status": "queued", "error": None, "heartbeat_at": None, "started_at": None, "completed_at": None, "progress_milestones": milestones, "claimed_by": None, "claimed_at": None, "updated_at": now})
                else:
                    milestones.append({"code": "worker_claim_stalled_failed", "label": "Worker stalled after loading job", "detail": "Worker loaded the generation job but did not reach request parsing after retry.", "meta": {}, "at": now})
                    row.update({"status": "failed", "error": "Generation worker stalled after loading the job.", "completed_at": now, "heartbeat_at": now, "progress_milestones": milestones, "updated_at": now})
            elif staleness == "stage1_planner_stalled":
                now = _now()
                milestones = list(row.get("progress_milestones") or [])
                milestones.append(
                    {
                        "code": "stage1_planner_timeout",
                        "label": "Stage 1 planner timed out",
                        "detail": "Planner did not return after invocation and the job was failed for recovery.",
                        "meta": {},
                        "at": now,
                    }
                )
                row.update(
                    {
                        "status": "failed",
                        "error": "Stage 1 planner stalled after planner invocation.",
                        "completed_at": now,
                        "heartbeat_at": now,
                        "progress_milestones": milestones,
                        "updated_at": now,
                    }
                )
            else:
                now = _now()
                row.update(
                    {
                        "status": "failed",
                        "error": "Generation job stalled mid-pipeline and was failed for recovery.",
                        "completed_at": now,
                        "heartbeat_at": now,
                        "updated_at": now,
                    }
                )
            return dict(row)
        return None

    def count_generation_jobs_for_athlete_since(
        self,
        athlete_id: str,
        since_timestamp: str,
        *,
        sources: set[str] | None = None,
    ) -> int:
        since = datetime.fromisoformat(since_timestamp.replace("Z", "+00:00"))
        count = 0
        for job in self.generation_jobs.values():
            if job["athlete_id"] != athlete_id:
                continue
            created_at_raw = str(job.get("created_at") or "")
            if not created_at_raw:
                continue
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            if created_at < since:
                continue
            if sources and str(job.get("source") or "") not in sources:
                continue
            count += 1
        return count

    def get_generation_job_by_plan_id(self, plan_id: str) -> dict | None:
        matches = [job for job in self.generation_jobs.values() if str(job.get("plan_id") or "") == plan_id]
        if not matches:
            return None
        matches.sort(key=lambda job: job.get("completed_at") or job.get("updated_at") or "", reverse=True)
        return dict(matches[0])

    def get_latest_generation_job_for_athlete(self, athlete_id: str) -> dict | None:
        rows = [
            dict(job)
            for job in self.generation_jobs.values()
            if str(job.get("athlete_id") or "") == athlete_id
        ]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows[0] if rows else None

    def has_active_generation_job_for_plan(self, plan_id: str) -> bool:
        return any(
            str(job.get("plan_id") or "") == plan_id and str(job.get("status") or "") in {"queued", "running"}
            for job in self.generation_jobs.values()
        )

    def list_generation_jobs_for_athlete(self, athlete_id: str, *, limit: int = 10) -> list[dict]:
        rows = [
            dict(job)
            for job in self.generation_jobs.values()
            if str(job.get("athlete_id") or "") == athlete_id
        ]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows[:limit]

    def _attach_profile_contacts(self, rows: list[dict], *, id_key: str = "athlete_id") -> list[dict]:
        """Mirror AppStore._attach_profile_contacts for admin-queue enrichment.

        Honours ``fail_profile_enrichment`` so tests can exercise the degraded
        path where the queue still renders with id-only rows.
        """
        for row in rows:
            existing = row.get("profiles")
            if isinstance(existing, dict) and (existing.get("email") or existing.get("full_name")):
                continue
            if self.fail_profile_enrichment:
                row["profile_enrichment_failed"] = True
                row["profiles"] = {"email": "", "full_name": ""}
                continue
            profile = self.profiles.get(str(row.get(id_key) or ""), {})
            row["profiles"] = {
                "email": profile.get("email", ""),
                "full_name": profile.get("full_name", ""),
            }
        return rows

    def list_admin_triage_generation_jobs(self, *, limit: int = 50) -> list[dict]:
        protected_statuses = {"triage_blocked", "needs_review", "restricted_rehab_only", "medical_hold"}
        rows = []
        for job in self.generation_jobs.values():
            final_result = job.get("final_result") if isinstance(job.get("final_result"), dict) else {}
            status_value = str(job.get("status") or "").strip().lower()
            plan_id = str(job.get("plan_id") or "").strip()
            triage_status = str(final_result.get("status") or "").strip().lower()
            stage2_status = str(final_result.get("stage2_status") or "").strip().lower()
            if status_value != "review_required" or plan_id or triage_status not in protected_statuses:
                continue
            if stage2_status == "triage_resume_approved":
                continue
            rows.append(dict(job))
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return self._attach_profile_contacts(rows[:limit])

    def list_admin_active_generation_jobs(self, *, limit: int = 50) -> list[dict]:
        rows = []
        for job in self.generation_jobs.values():
            status_value = str(job.get("status") or "").strip().lower()
            if status_value not in {"queued", "running"}:
                continue
            rows.append(dict(job))
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return self._attach_profile_contacts(rows[:limit])

    def list_orphaned_terminal_generation_jobs(self, *, limit: int = 500) -> list[dict]:
        rows: list[dict] = []
        for job in self.generation_jobs.values():
            status_value = str(job.get("status") or "").strip().lower()
            if status_value not in {"completed", "review_required"}:
                continue
            plan_id = str(job.get("plan_id") or "").strip()
            if not plan_id or self.get_plan(plan_id) is None:
                rows.append(
                    {
                        "job_id": str(job.get("id") or ""),
                        "athlete_id": str(job.get("athlete_id") or ""),
                        "status": status_value,
                        "source": str(job.get("source") or ""),
                        "plan_id": plan_id,
                    }
                )
        rows.sort(key=lambda row: row["job_id"], reverse=True)
        return rows[:limit]

    def list_failed_triage_resume_jobs_with_approved_marker(self, *, limit: int = 500) -> list[dict]:
        rows: list[dict] = []
        for job in self.generation_jobs.values():
            status_value = str(job.get("status") or "").strip().lower()
            source_value = str(job.get("source") or "").strip().lower()
            if status_value != "failed" or source_value != "admin_triage_resume":
                continue
            plan_id = str(job.get("plan_id") or "").strip()
            plan_row = self.get_plan(plan_id) if plan_id else None
            if not plan_row:
                continue
            stage2_status = str(plan_row.get("stage2_status") or "").strip().lower()
            if stage2_status != "triage_resume_approved":
                continue
            rows.append(
                {
                    "job_id": str(job.get("id") or ""),
                    "plan_id": str(plan_row.get("id") or ""),
                    "athlete_id": str(job.get("athlete_id") or ""),
                }
            )
        rows.sort(key=lambda row: row["job_id"], reverse=True)
        return rows[:limit]

    def list_claimable_generation_jobs(self, *, limit: int = 20, stale_after_seconds: int = 90) -> list[dict]:
        rows = []
        for job in self.generation_jobs.values():
            status_value = str(job.get("status") or "")
            if status_value == "queued":
                rows.append(dict(job))
                continue
            if status_value != "running":
                continue
            if is_startup_stale_generation_job(job, stale_after_seconds=stale_after_seconds):
                rows.append(dict(job))
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
        return rows[:limit]

    def claim_generation_job_start(self, job_id: str, *, stale_after_seconds: int = 90, worker_id: str | None = None) -> dict | None:
        job = self.generation_jobs.get(job_id)
        if not job:
            return None
        current_status = str(job.get("status") or "").strip().lower() or "queued"
        if current_status not in {"queued", "running"}:
            return None
        if current_status == "running" and not is_startup_stale_generation_job(
            job,
            stale_after_seconds=stale_after_seconds,
        ):
            return None
        # Mirror SupabaseAppStore: the worker reclaim path enforces the same
        # job_loaded retry cap as the read-side recovery so a repeatedly-dying
        # worker cannot re-grab the job past its attempt budget.
        if (
            current_status == "running"
            and int(job.get("attempt_count") or 0) >= _generation_startup_max_attempts()
            and is_job_loaded_stalled_generation_job(job, stale_after_seconds=stale_after_seconds)
        ):
            now_iso = _now()
            milestones = list(job.get("progress_milestones") or [])
            milestones.append(
                {
                    "code": "worker_claim_stalled_failed",
                    "label": "Worker stalled after loading job",
                    "detail": "Worker loaded the generation job but did not reach request parsing after retry.",
                    "meta": {},
                    "at": now_iso,
                }
            )
            job.update(
                {
                    "status": "failed",
                    "error": "Generation worker stalled after loading the job.",
                    "completed_at": now_iso,
                    "heartbeat_at": now_iso,
                    "progress_milestones": milestones,
                    "updated_at": now_iso,
                }
            )
            return None
        now_iso = _now()
        job["status"] = "running"
        job["heartbeat_at"] = now_iso
        job["started_at"] = now_iso if job.get("started_at") is None else job["started_at"]
        job["attempt_count"] = int(job.get("attempt_count") or 0) + 1
        job["claimed_by"] = (worker_id or "").strip() or generation_worker_id()
        job["claimed_at"] = now_iso
        job["error"] = None
        job["completed_at"] = None
        job["progress_milestones"] = [
            {
                "code": "job_loaded",
                "label": "Generation job loaded",
                "detail": "Worker loaded the persisted generation job.",
                "meta": {},
                "at": now_iso,
            }
        ]
        job["updated_at"] = now_iso
        return dict(job)

    def claim_generation_job(self, job_id: str, *, stale_after_seconds: int = 90, worker_id: str | None = None) -> dict | None:
        return self.claim_generation_job_start(job_id, stale_after_seconds=stale_after_seconds, worker_id=worker_id)

    def count_active_generation_jobs(self, *, stale_after_seconds: int = 90) -> int:
        now = datetime.now(timezone.utc)
        count = 0
        for job in self.generation_jobs.values():
            if str(job.get("status") or "") != "running":
                continue
            heartbeat_raw = job.get("heartbeat_at")
            started_raw = job.get("started_at")
            heartbeat = (
                datetime.fromisoformat(str(heartbeat_raw).replace("Z", "+00:00"))
                if isinstance(heartbeat_raw, str) and heartbeat_raw
                else None
            )
            started_at = (
                datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
                if isinstance(started_raw, str) and started_raw
                else None
            )
            last_progress_at = heartbeat or started_at
            if last_progress_at and (now - last_progress_at).total_seconds() < stale_after_seconds:
                count += 1
        return count

    def update_generation_job(self, job_id: str, **changes: dict) -> dict:
        job = self.generation_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
        payload = dict(changes)
        if "status" in payload:
            next_status = str(payload.get("status") or "").strip().lower()
            if not is_generation_job_status(next_status):
                raise _status_transition_error(f"unknown generation job status: {next_status!r}")
            try:
                payload["status"] = require_generation_job_transition(job.get("status") or "queued", next_status)
            except ValueError as exc:
                raise _status_transition_error(str(exc)) from exc
        job.update(payload)
        job["updated_at"] = _now()
        return dict(job)

    def _assert_generation_job_terminal_owner(
        self,
        job_id: str,
        *,
        expected_status: str,
        expected_attempt_count: int,
        expected_worker_id: str | None = None,
        enforce_worker_ownership: bool = True,
    ) -> dict:
        job = self.generation_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
        current_status = str(job.get("status") or "")
        if current_status != expected_status:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"wrong_generation_job_status:{job_id} expected {expected_status}, got {current_status or '<null>'}",
            )
        current_attempt = int(job.get("attempt_count") or 0)
        if current_attempt != expected_attempt_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"stale_generation_job_attempt:{job_id} expected {expected_attempt_count}, got {current_attempt}",
            )
        # Mirror the SQL RPC ownership guard: enforce only when the job has a
        # recorded owner (rows claimed before the migration have none).
        if enforce_worker_ownership:
            checked_worker_id = (expected_worker_id or "").strip() or generation_worker_id()
            claimed_by = str(job.get("claimed_by") or "")
            if claimed_by and claimed_by != checked_worker_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"stale_generation_job_worker:{job_id} expected {checked_worker_id}, got {claimed_by}",
                )
        return job

    def complete_generation_job(
        self,
        job_id: str,
        *,
        expected_attempt_count: int,
        final_status: str,
        final_result: dict | None = None,
        plan_id: str | None = None,
        error: str | None = None,
        completed_at: str | None = None,
        heartbeat_at: str | None = None,
        expected_status: str = "running",
        expected_worker_id: str | None = None,
        enforce_worker_ownership: bool = True,
    ) -> dict:
        if final_status not in {"completed", "review_required"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"invalid_terminal_status:{final_status}",
            )
        job = self._assert_generation_job_terminal_owner(
            job_id,
            expected_status=expected_status,
            expected_attempt_count=expected_attempt_count,
            expected_worker_id=expected_worker_id,
            enforce_worker_ownership=enforce_worker_ownership,
        )
        now = completed_at or _now()
        job.update(
            {
                "status": final_status,
                "error": error,
                "completed_at": now,
                "failed_at": None,
                "heartbeat_at": heartbeat_at or now,
                "updated_at": _now(),
            }
        )
        if final_result is not None:
            job["final_result"] = final_result
        if plan_id is not None:
            job["plan_id"] = plan_id
        return dict(job)

    def fail_generation_job(
        self,
        job_id: str,
        *,
        expected_attempt_count: int,
        error: str,
        final_result: dict | None = None,
        plan_id: str | None = None,
        progress_milestones: list | None = None,
        failed_at: str | None = None,
        heartbeat_at: str | None = None,
        expected_status: str = "running",
        expected_worker_id: str | None = None,
        enforce_worker_ownership: bool = True,
    ) -> dict:
        job = self._assert_generation_job_terminal_owner(
            job_id,
            expected_status=expected_status,
            expected_attempt_count=expected_attempt_count,
            expected_worker_id=expected_worker_id,
            enforce_worker_ownership=enforce_worker_ownership,
        )
        now = failed_at or _now()
        job.update(
            {
                "status": "failed",
                "error": error or "Generation job failed.",
                "completed_at": now,
                "failed_at": now,
                "heartbeat_at": heartbeat_at or now,
                "updated_at": _now(),
            }
        )
        if final_result is not None:
            job["final_result"] = final_result
        if plan_id is not None:
            job["plan_id"] = plan_id
        if progress_milestones is not None:
            job["progress_milestones"] = progress_milestones
        return dict(job)

    def record_stage2_cost(self, job_id: str, metadata: dict) -> None:
        job = self.generation_jobs.get(job_id)
        if not job or not isinstance(metadata, dict):
            return
        job.update(
            {
                column: metadata[column]
                for column in GENERATION_JOB_STAGE2_COST_COLUMNS
                if column in metadata
            }
        )

    def update_plan_stage2(self, plan_id: str, result: dict) -> dict:
        row = self.plans.get(plan_id)
        if not row:
            return None
        try:
            current_status = row.get("status") or "generated"
            next_status_input = result.get("status") or current_status
            next_status = require_plan_transition(current_status, next_status_input)
        except ValueError as exc:
            raise _status_transition_error(str(exc)) from exc
        row.update(
            {
                "status": next_status,
                "plan_text": result.get("plan_text", row.get("plan_text", "")),
                "draft_plan_text": result.get("draft_plan_text", row.get("draft_plan_text", row.get("plan_text", ""))),
                "final_plan_text": result.get("final_plan_text", row.get("final_plan_text", row.get("plan_text", ""))),
                "pdf_url": result.get("pdf_url"),
                "stage2_retry_text": result.get("stage2_retry_text", ""),
                "stage2_validator_report": result.get("stage2_validator_report", {}),
                "stage2_status": result.get("stage2_status", ""),
                "stage2_attempt_count": result.get("stage2_attempt_count", row.get("stage2_attempt_count", 0)),
            }
        )
        for optional_field in (
            "coach_notes",
            "why_log",
            "planning_brief",
            "stage2_payload",
            "parsing_metadata",
            "stage2_handoff_text",
            "structured_plan",
            "schema_version",
        ):
            if optional_field in result:
                row[optional_field] = result.get(optional_field)
        return row

    def update_plan_stage2_if_unchanged(self, plan_id: str, result: dict, expected_snapshot: dict) -> dict:
        row = self.plans.get(plan_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        # Mirror the production guard: lightweight state markers only, never the
        # large text bodies (which PostgREST would push into the request URL).
        guarded_fields = (
            "status",
            "stage2_status",
            "stage2_attempt_count",
        )
        if any(row.get(field) != expected_snapshot.get(field) for field in guarded_fields):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Plan changed while Stage 2 structured processing was running; reload and try again.",
            )
        return self.update_plan_stage2(plan_id, result)

    def update_plan_structured_artifacts(
        self,
        plan_id: str,
        *,
        structured_plan,
        schema_version,
        stage2_validator_report: dict,
        expected_final_plan_text: str | None = None,
    ) -> dict:
        row = self.plans.get(plan_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        # Stale-write guard: when the conversion's source text is supplied, only
        # persist the card if the row's current text still matches. A concurrent
        # edit/reject mid-conversion makes the card stale, so the write is skipped.
        if expected_final_plan_text is not None:
            current_text = str(row.get("final_plan_text") or row.get("plan_text") or "")
            if current_text != str(expected_final_plan_text):
                return row
            if structured_plan is None and row.get("structured_plan") is not None:
                return row
        # Narrow write: only the structured-plan output fields. Status / plan_text
        # / stage2 fields are intentionally left untouched so a concurrent admin
        # action cannot be clobbered by a slow background conversion.
        if structured_plan is not None:
            row["structured_plan"] = structured_plan
            row["schema_version"] = schema_version
        row["stage2_validator_report"] = stage2_validator_report or {}
        return row

    def update_plan_triage_approval(self, plan_id: str, *, why_log: dict, stage2_status: str) -> dict:
        row = self.plans.get(plan_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        row["why_log"] = why_log
        row["stage2_status"] = stage2_status
        return row

    def list_admin_plans(self, *, limit: int = 50, offset: int = 0, q: str | None = None) -> list[dict]:
        rows = [dict(plan) for plan in self.plans.values()]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        rows = _filter_admin_rows(rows, q, ("plan_name", "full_name", "status"))
        return self._attach_profile_contacts(rows[offset:offset + limit])

    def list_admin_review_plans(self, *, limit: int = 100) -> list[dict]:
        review_statuses = {
            "review_required",
            "held_for_review",
            "needs_review",
            "triage_blocked",
            "medical_hold",
            "restricted_rehab_only",
            "publishable_with_flags",
        }
        rows = [
            dict(plan)
            for plan in self.plans.values()
            if str(plan.get("status") or "").strip().lower() in review_statuses
        ]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return self._attach_profile_contacts(rows[:limit])

    def list_plans_missing_structured_plan(self, *, limit: int = 50) -> list[dict]:
        displayable = {"ready", "publishable_with_flags"}
        rows = [
            dict(plan)
            for plan in self.plans.values()
            if str(plan.get("status") or "").strip().lower() in displayable
            and plan.get("structured_plan") is None
        ]
        rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return rows[:limit]

    def list_admin_athletes(self, *, limit: int = 50, offset: int = 0, q: str | None = None) -> list[dict]:
        rows = []
        for profile in self.profiles.values():
            plans = self.list_user_plans(profile["id"])
            rows.append({
                **profile,
                "plan_count": len(plans),
                "latest_plan_created_at": plans[-1]["created_at"] if plans else None,
            })
        rows.sort(key=lambda row: row["updated_at"], reverse=True)
        rows = _filter_admin_rows(
            rows, q, ("email", "full_name", "username", "professional_status", "record_summary")
        )
        return rows[offset:offset + limit]

    def get_admin_athlete(self, athlete_id: str) -> dict | None:
        self.get_admin_athlete_calls += 1
        profile = self.profiles.get(athlete_id)
        if not profile:
            return None
        plans = self.list_user_plans(athlete_id)
        return {
            **profile,
            "plan_count": len(plans),
            "latest_plan_created_at": plans[-1]["created_at"] if plans else None,
        }

    def list_admin_athletes_by_ids(self, athlete_ids: list[str]) -> list[dict]:
        self.list_admin_athletes_by_ids_calls += 1
        return [
            athlete
            for athlete_id in athlete_ids
            if (athlete := self.get_admin_athlete_without_counting(athlete_id)) is not None
        ]

    def get_admin_athlete_without_counting(self, athlete_id: str) -> dict | None:
        profile = self.profiles.get(athlete_id)
        if not profile:
            return None
        plans = self.list_user_plans(athlete_id)
        return {
            **profile,
            "plan_count": len(plans),
            "latest_plan_created_at": plans[-1]["created_at"] if plans else None,
        }

    def clear_onboarding_draft(self, athlete_id: str) -> None:
        self.profiles[athlete_id]["onboarding_draft"] = None

    # ------------------------------------------------------------------
    # Live athlete daily tracking (api/routes/daily.py)
    # ------------------------------------------------------------------

    def upsert_daily_checkin(self, athlete_id: str, fields: dict) -> dict:
        bucket = self.daily_checkins.setdefault(athlete_id, [])
        for row in bucket:
            if row["checkin_date"] == fields["checkin_date"]:
                row.update(fields)
                row["updated_at"] = _now()
                return dict(row)
        row = {
            "id": str(uuid4()),
            "athlete_id": athlete_id,
            "sleep_hours": None,
            "injury_note": "",
            "notes": "",
            "readiness_state": "ready",
            **fields,
            "created_at": _now(),
            "updated_at": _now(),
        }
        bucket.append(row)
        return dict(row)

    def get_daily_checkin(self, athlete_id: str, checkin_date: str) -> dict | None:
        for row in self.daily_checkins.get(athlete_id, []):
            if row["checkin_date"] == checkin_date:
                return dict(row)
        return None

    def list_daily_checkins(self, athlete_id: str, *, limit: int = 14) -> list[dict]:
        rows = sorted(
            self.daily_checkins.get(athlete_id, []),
            key=lambda row: row["checkin_date"],
            reverse=True,
        )
        return [dict(row) for row in rows[:limit]]

    def upsert_today_checkin(self, athlete_id: str, fields: dict) -> dict:
        bucket = self.today_checkins.setdefault(athlete_id, [])
        for row in bucket:
            if row["plan_id"] == fields["plan_id"] and row["training_day"] == fields["training_day"]:
                row.update(fields)
                row["updated_at"] = _now()
                return dict(row)
        row = {
            "id": str(uuid4()),
            "athlete_id": athlete_id,
            "athlete_timezone": "",
            "active_injury": "none",
            "previous_session": "none",
            "recommendation_reason": "",
            "recommendation_triggers": [],
            **fields,
            "created_at": _now(),
            "updated_at": _now(),
        }
        bucket.append(row)
        return dict(row)

    def get_today_checkin(self, athlete_id: str, plan_id: str, training_day: str) -> dict | None:
        for row in self.today_checkins.get(athlete_id, []):
            if row["plan_id"] == plan_id and row["training_day"] == training_day:
                return dict(row)
        return None

    def list_today_checkins_for_day(self, athlete_id: str, training_day: str) -> list[dict]:
        return [
            dict(row)
            for row in self.today_checkins.get(athlete_id, [])
            if row["training_day"] == training_day
        ]

    def upsert_session_completion(self, athlete_id: str, fields: dict) -> dict:
        bucket = self.session_completions.setdefault(athlete_id, [])
        for row in bucket:
            if row["session_id"] == fields["session_id"] and row["training_day"] == fields["training_day"]:
                row.update(fields)
                row["updated_at"] = _now()
                return dict(row)
        row = {
            "id": str(uuid4()),
            "athlete_id": athlete_id,
            "session_rpe": None,
            "pain_after": None,
            "modification_reason": "",
            "notes": "",
            "started_at": None,
            "completed_at": None,
            **fields,
            "created_at": _now(),
            "updated_at": _now(),
        }
        bucket.append(row)
        return dict(row)

    def get_session_completion(self, athlete_id: str, session_id: str, training_day: str) -> dict | None:
        for row in self.session_completions.get(athlete_id, []):
            if row["session_id"] == session_id and row["training_day"] == training_day:
                return dict(row)
        return None

    def list_session_completions(self, athlete_id: str, *, limit: int = 30) -> list[dict]:
        rows = sorted(
            self.session_completions.get(athlete_id, []),
            key=lambda row: row["training_day"],
            reverse=True,
        )
        return [dict(row) for row in rows[:limit]]

    def list_today_checkins(self, athlete_id: str, *, limit: int = 14) -> list[dict]:
        rows = sorted(
            self.today_checkins.get(athlete_id, []),
            key=lambda row: row["training_day"],
            reverse=True,
        )
        return [dict(row) for row in rows[:limit]]

    def create_session_log(self, athlete_id: str, fields: dict) -> dict:
        row = {
            "id": str(uuid4()),
            "athlete_id": athlete_id,
            "plan_id": None,
            "session_type": "training",
            "completed": True,
            "rpe": None,
            "duration_minutes": None,
            "notes": "",
            **fields,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.session_logs.setdefault(athlete_id, []).append(row)
        return dict(row)

    def list_session_logs(self, athlete_id: str, *, limit: int = 20) -> list[dict]:
        rows = sorted(
            self.session_logs.get(athlete_id, []),
            key=lambda row: (row["session_date"], row["created_at"]),
            reverse=True,
        )
        return [dict(row) for row in rows[:limit]]

    def create_injury_flag(self, athlete_id: str, fields: dict) -> dict:
        row = {
            "id": str(uuid4()),
            "athlete_id": athlete_id,
            "plan_id": None,
            "source": "checkin",
            "body_area": "",
            "severity": "moderate",
            "status": "open",
            "resolved_at": None,
            **fields,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.injury_flags.setdefault(athlete_id, []).append(row)
        return dict(row)

    def list_injury_flags(
        self, athlete_id: str, *, statuses: tuple = ("open", "monitoring"), limit: int = 20
    ) -> list[dict]:
        rows = [
            dict(row)
            for row in self.injury_flags.get(athlete_id, [])
            if not statuses or row["status"] in statuses
        ]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return rows[:limit]

    def update_injury_flag(self, flag_id: str, fields: dict) -> dict:
        for rows in self.injury_flags.values():
            for row in rows:
                if row["id"] == flag_id:
                    row.update(fields)
                    row["updated_at"] = _now()
                    return dict(row)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="injury flag not found")

    def create_adaptation_note(self, athlete_id: str, fields: dict) -> dict:
        row = {
            "id": str(uuid4()),
            "athlete_id": athlete_id,
            "plan_id": None,
            "checkin_id": None,
            "session_log_id": None,
            "details": {},
            **fields,
            "created_at": _now(),
        }
        self.adaptation_notes.setdefault(athlete_id, []).append(row)
        return dict(row)

    def list_adaptation_notes(self, athlete_id: str, *, limit: int = 10) -> list[dict]:
        rows = list(reversed(self.adaptation_notes.get(athlete_id, [])))
        return [dict(row) for row in rows[:limit]]

    def create_admin_review(self, athlete_id: str, fields: dict) -> dict:
        row = {
            "id": str(uuid4()),
            "athlete_id": athlete_id,
            "adaptation_note_id": None,
            "injury_flag_id": None,
            "status": "pending",
            "resolution_notes": "",
            "resolved_by": "",
            "resolved_at": None,
            **fields,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.admin_reviews.append(row)
        return dict(row)

    def list_admin_reviews(self, *, status_filter: str | None = "pending", limit: int = 50) -> list[dict]:
        rows = [
            dict(row)
            for row in self.admin_reviews
            if status_filter is None or row["status"] == status_filter
        ]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return rows[:limit]

    def count_pending_admin_reviews_for_athlete(self, athlete_id: str) -> int:
        return sum(
            1
            for row in self.admin_reviews
            if row["athlete_id"] == athlete_id and row["status"] == "pending"
        )

    def resolve_admin_review(self, review_id: str, fields: dict) -> dict:
        for row in self.admin_reviews:
            if row["id"] == review_id:
                row.update(fields)
                row["updated_at"] = _now()
                return dict(row)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")


class FakeOpenAIStream:
    """Minimal stand-in for the OpenAI SDK's AsyncResponseStreamManager: entering
    the context resolves (or raises) like ``responses.create`` would, and
    ``get_final_response`` returns the accumulated response object."""

    def __init__(self, response_coro) -> None:
        self._coro = response_coro
        self._response: object | None = None

    async def __aenter__(self) -> "FakeOpenAIStream":
        self._response = await self._coro
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def get_final_response(self) -> object:
        return self._response


class FakeOpenAIResponses:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    async def create(self, **request: object) -> object:
        self.calls.append(request)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    def stream(self, **request: object) -> FakeOpenAIStream:
        # Delegate through create() so tests that override .create keep working.
        return FakeOpenAIStream(self.create(**request))


class FakeOpenAIClient:
    def __init__(self, outputs: list[object]) -> None:
        self.responses = FakeOpenAIResponses(outputs)


@dataclass
class FakeStage2Automator:
    result: dict | None = None
    error: Exception | None = None
    calls: list[dict] = field(default_factory=list)
    # Tests pass a zero-arg callable when each invocation should produce a fresh
    # finalized payload (e.g. distinct ids per call). When set, it takes
    # precedence over the static ``result``.
    result_factory: Callable[[], dict] | None = None

    async def finalize(self, *, stage1_result: dict, log_context: dict | None = None) -> dict:
        self.calls.append(stage1_result)
        if self.error:
            raise self.error
        overlay = self.result_factory() if self.result_factory is not None else (self.result or {})
        return {**stage1_result, **overlay}


def _build_request(overrides: dict | None = None) -> PlanRequest:
    payload = {
        "athlete": {
            "full_name": "Ari Mensah",
            "age": 27,
            "weight_kg": 72.5,
            "target_weight_kg": 70.0,
            "height_cm": 178,
            "technical_style": ["boxing"],
            "tactical_style": ["pressure_fighter"],
            "professional_status": "amateur",
            "record": "5-1",
            "athlete_timezone": "Europe/London",
        },
        "fight_date": "2099-04-18",
        "weekly_training_frequency": 4,
        "training_availability": ["Monday", "Tuesday", "Thursday", "Saturday"],
        "hard_sparring_days": ["Tuesday", "Saturday"],
        "technical_skill_days": ["Monday"],
        "equipment_access": ["barbell", "heavy_bag"],
        "key_goals": ["power", "conditioning"],
        "weak_areas": ["gas_tank"],
        "injuries": "mild left shoulder irritation",
        "rounds_format": "3 x 3",
        "fatigue_level": "moderate",
    }
    if overrides:
        merged = copy.deepcopy(overrides)
        athlete_overrides = merged.pop("athlete", None)
        if athlete_overrides:
            payload["athlete"].update(athlete_overrides)
        payload.update(merged)
        availability_override = merged.get("training_availability")
        if isinstance(availability_override, list):
            normalized_days = {
                str(day).strip().lower()
                for day in availability_override
                if str(day).strip()
            }
            for key in ["hard_sparring_days", "technical_skill_days", "support_work_days"]:
                if key not in merged and key in payload:
                    payload[key] = [
                        day
                        for day in payload[key]
                        if str(day).strip().lower() in normalized_days
                    ]
    return PlanRequest.model_validate(payload)


def stage1_result() -> dict:
    return {
        "plan_text": "# Stage 1 Draft",
        "coach_notes": "### Coach Review",
        "pdf_url": "https://example.com/stage1.pdf",
        "why_log": {"strength": {}},
        "stage2_payload": {"ok": True},
        "planning_brief": {"schema_version": "planning_brief.v1", "main_limiter": "conditioning"},
        "stage2_handoff_text": "handoff",
    }


def finalized_result(**overrides: object) -> dict:
    base = {
        **stage1_result(),
        "status": "ready",
        "plan_text": "# Final Plan",
        "draft_plan_text": "# Stage 1 Draft",
        "final_plan_text": "# Final Plan",
        "pdf_url": None,
        "stage2_status": "stage2_pass",
        "stage2_validator_report": {"errors": [], "warnings": []},
        "stage2_retry_text": "",
        "stage2_attempt_count": 1,
    }
    return {**base, **overrides}


def advisory_planning_brief(
    *,
    phase: str = "TAPER",
    stage_key: str = "fight_week_survival_rhythm",
    days_until_fight: int = 6,
    fatigue: str = "low",
    readiness_flags: list[str] | None = None,
    injuries: list[str] | None = None,
    weight_cut_pct: float = 0.0,
    hard_sparring_days: list[str] | None = None,
) -> dict:
    hard_days = hard_sparring_days or ["Tuesday", "Thursday"]
    return {
        "schema_version": "planning_brief.v1",
        "athlete_snapshot": {
            "sport": "boxing",
            "days_until_fight": days_until_fight,
            "fatigue": fatigue,
            "short_notice": days_until_fight <= 14,
            "readiness_flags": readiness_flags or [],
            "injuries": injuries or [],
            "weight_cut_pct": weight_cut_pct,
            "hard_sparring_days": hard_days,
            "technical_skill_days": ["Monday"],
        },
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": phase,
                    "week_index": 1,
                    "phase_week_index": 1,
                    "phase_week_total": 1,
                    "stage_key": stage_key,
                    "declared_hard_sparring_days": hard_days,
                    "declared_technical_skill_days": ["Monday"],
                    "declared_training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
                    "session_roles": [],
                    "suppressed_roles": [],
                }
            ]
        },
    }


def _presentation_ready_plan(*, heading: str, support_note: str) -> str:
    return (
        f"## {heading}\n"
        "### Week 1\n"
        "#### Strength\n"
        "- Trap Bar Deadlift - 4x3\n"
        "#### Recovery\n"
        f"- {support_note}\n"
        "#### Fight-pace conditioning\n"
        "- Bag Rounds - 5 x 3 min\n"
    )


def _review_required_result(*, final_plan_text: str, warning_code: str) -> dict:
    warning = {"code": warning_code, "severity": "blocker"}
    return finalized_result(
        status="review_required",
        plan_text="",
        final_plan_text=final_plan_text,
        stage2_status="stage2_failed",
        stage2_retry_text="repair prompt",
        stage2_validator_report={"errors": [], "warnings": [warning], "blocking_warnings": [warning]},
        stage2_attempt_count=2,
    )


@dataclass(frozen=True)
class SystemScenario:
    key: str
    request_overrides: dict
    automator_result: dict
    expected_status: str
    expected_review_code: str | None
    expected_resolution: str | None
    support_marker: str


SYSTEM_SCENARIOS = [
    SystemScenario(
        key="high_fatigue",
        request_overrides={
            "fatigue_level": "high",
            "weekly_training_frequency": 5,
            "training_availability": ["Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"],
        },
        automator_result=finalized_result(
            plan_text=_presentation_ready_plan(
                heading="PHASE 2: SPP",
                support_note="High fatigue this week, so keep the recovery day obvious and trim optional density first.",
            ),
            final_plan_text=_presentation_ready_plan(
                heading="PHASE 2: SPP",
                support_note="High fatigue this week, so keep the recovery day obvious and trim optional density first.",
            ),
        ),
        expected_status="ready",
        expected_review_code=None,
        expected_resolution=None,
        support_marker="High fatigue this week",
    ),
    SystemScenario(
        key="messy_injury_input",
        request_overrides={
            "injuries": "none / right shoulder cranky after pads + left wrist sore on hooks",
            "equipment_access": ["bands", "heavy_bag", "bodyweight"],
        },
        automator_result=finalized_result(
            plan_text=_presentation_ready_plan(
                heading="PHASE 1: GPP",
                support_note="Shoulder and wrist management stay in the week, but the main session remains decisive.",
            ),
            final_plan_text=_presentation_ready_plan(
                heading="PHASE 1: GPP",
                support_note="Shoulder and wrist management stay in the week, but the main session remains decisive.",
            ),
        ),
        expected_status="ready",
        expected_review_code=None,
        expected_resolution=None,
        support_marker="Shoulder and wrist management",
    ),
    SystemScenario(
        key="severe_cut_pressure",
        request_overrides={
            "athlete": {"weight_kg": 72.0, "target_weight_kg": 66.0},
            "fatigue_level": "moderate",
            "fight_date": "2099-04-05",
        },
        automator_result=finalized_result(
            plan_text=(
                "## Camp Summary\n"
                "- Active weight-cut stress is part of this camp, so protect freshness and avoid optional fatigue.\n"
                "## Nutrition\n"
                "- Prioritize carbs, fluids, and sodium around key sessions to preserve strength expression and conditioning tolerance.\n"
            ),
            final_plan_text=(
                "## Camp Summary\n"
                "- Active weight-cut stress is part of this camp, so protect freshness and avoid optional fatigue.\n"
                "## Nutrition\n"
                "- Prioritize carbs, fluids, and sodium around key sessions to preserve strength expression and conditioning tolerance.\n"
            ),
        ),
        expected_status="ready",
        expected_review_code=None,
        expected_resolution=None,
        support_marker="Active weight-cut stress",
    ),
    SystemScenario(
        key="limited_equipment_hold",
        request_overrides={
            "equipment_access": ["bands", "bodyweight"],
            "weekly_training_frequency": 3,
            "training_availability": ["Tuesday", "Thursday", "Saturday"],
        },
        automator_result=_review_required_result(
            final_plan_text="## PHASE 2: SPP\n- Heavy Bag Sprint Rounds - 6 x 15 sec",
            warning_code="equipment_incongruent_selection",
        ),
        expected_status="review_required",
        expected_review_code="equipment_incongruent_selection",
        expected_resolution="approve",
        support_marker="Heavy Bag Sprint Rounds",
    ),
    SystemScenario(
        key="short_notice_contradictory",
        request_overrides={
            "fight_date": "2099-03-24",
            "weekly_training_frequency": 6,
            "training_availability": ["Monday", "Wednesday"],
            "equipment_access": ["assault_bike", "bands", "bodyweight"],
        },
        automator_result=_review_required_result(
            final_plan_text="## PHASE 3: TAPER\n### Week 5\n#### Strength\n- Dead Bug - 2x8",
            warning_code="late_camp_session_incomplete",
        ),
        expected_status="review_required",
        expected_review_code="late_camp_session_incomplete",
        expected_resolution="manual_stage2",
        support_marker="Dead Bug - 2x8",
    ),
]


def _planner(payload: dict) -> dict:
    return stage1_result()


def _empty_plan_planner(payload: dict, *, progress_callback=None) -> dict:
    """Module-level planner that returns an empty plan result.

    Tests that pipe a planner through the generation subprocess need a
    picklable callable; in-test ``lambda`` planners raise AttributeError when
    the subprocess tries to pickle them.
    """
    return {"plan_text": ""}


def _start_generation(client: TestClient, request: PlanRequest | None = None) -> tuple[dict, dict]:
    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=(request or _build_request()).model_dump(mode="json"),
    )
    assert response.status_code == 202
    job_body = response.json()
    job_response = client.get(
        f"/api/generation-jobs/{job_body['job_id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert job_response.status_code == 200
    return job_body, job_response.json()


DEFAULT_ATHLETE_USER = AuthenticatedUser(
    user_id="athlete-1",
    email="ari@example.com",
    full_name="Ari Mensah",
    metadata={},
)
DEFAULT_ADMIN_USER = AuthenticatedUser(
    user_id="admin-1",
    email="ops@unlxck.test",
    full_name="Ops Admin",
    metadata={},
)


def seed_default_profiles(store: "FakeStore") -> None:
    """Ensure the default athlete and admin profiles exist in ``store``.

    Mirrors production where ``require_profile`` calls ``ensure_profile`` on the
    first authenticated request. Tests that build a ``FakeStore`` directly and
    seed intakes/plans without going through ``_build_client`` should call this
    to satisfy the profile-row prerequisite of admin/plan endpoints.
    """
    store.ensure_profile(DEFAULT_ATHLETE_USER)
    store.ensure_profile(DEFAULT_ADMIN_USER)


def _build_client(
    automator: FakeStage2Automator | None = None,
    *,
    enable_in_process_generation: bool = True,
) -> tuple[TestClient, FakeStore, FakeStage2Automator]:
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    admin = AuthenticatedUser(
        user_id="admin-1",
        email="ops@unlxck.test",
        full_name="Ops Admin",
        metadata={},
    )
    store = FakeStore()
    # Mirror production: every authenticated request ensures the caller's profile
    # via require_profile -> ensure_profile. Seed both up front so tests that
    # don't make a request first (e.g. seeding store state directly) still see
    # the profiles their endpoints expect.
    seed_default_profiles(store)
    stage2 = automator or FakeStage2Automator(result=finalized_result())
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
            stage2_automator=stage2,
            enable_in_process_generation=enable_in_process_generation,
        )
    )
    return client, store, stage2
