from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import api.worker as worker
from api.worker_recovery import classify_worker_recovery_category


def _old_iso(minutes: int = 30) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _milestone(code: str, *, minutes: int = 30) -> dict[str, Any]:
    return {
        "code": code,
        "label": code,
        "detail": code,
        "meta": {},
        "at": _old_iso(minutes),
    }


def _running_job(
    job_id: str,
    *,
    milestones: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": job_id,
        "status": "running",
        "attempt_count": 1,
        "created_at": _old_iso(35),
        "started_at": _old_iso(34),
        "heartbeat_at": _old_iso(30),
        "completed_at": None,
        "progress_milestones": milestones or [],
        "stage1_result": None,
        "final_result": None,
        "plan_id": None,
        **extra,
    }


def test_worker_recovery_classifier_distinguishes_every_stale_category() -> None:
    stale_after = 90
    jobs = {
        "startup_stale": _running_job("startup"),
        "worker_claim_stalled": _running_job(
            "worker-claim",
            milestones=[_milestone("job_loaded")],
        ),
        "stage1_stalled": _running_job(
            "stage1",
            milestones=[
                _milestone("job_loaded"),
                _milestone("request_payload_parsed"),
                _milestone("stage1_planner_invoked"),
            ],
        ),
        "mid_pipeline_stale": _running_job(
            "mid",
            milestones=[
                _milestone("job_loaded"),
                _milestone("request_payload_parsed"),
                _milestone("stage1_planner_finished"),
                _milestone("stage2_drafting"),
            ],
            stage1_result={},
        ),
        "persisted_output_recovery": _running_job(
            "persisted",
            milestones=[
                _milestone("job_loaded"),
                {
                    **_milestone("final_result_persisted"),
                    "meta": {"plan_id": "plan-1"},
                },
            ],
            stage1_result={},
            final_result={
                "status": "publishable_with_flags",
                "stage2_status": "stage2_failed",
            },
        ),
    }

    for expected, job in jobs.items():
        assert (
            classify_worker_recovery_category(
                job,
                stale_after_seconds=stale_after,
            )
            == expected
        )


class _RecoveryStore:
    def __init__(self, jobs: dict[str, dict[str, Any]]):
        self.jobs = jobs
        self.recover_calls: list[str] = []
        self.complete_calls: list[str] = []
        self.fail_calls: list[str] = []

    def list_admin_active_generation_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [
            {"id": job_id, "status": job["status"], "created_at": job["created_at"]}
            for job_id, job in list(self.jobs.items())[:limit]
            if job["status"] in {"queued", "running"}
        ]

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.jobs.get(job_id)
        return dict(job) if job else None

    def recover_generation_job_if_stale(
        self,
        job: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not job:
            return job
        job_id = str(job["id"])
        self.recover_calls.append(job_id)
        if job_id == "worker-claim":
            self.jobs[job_id]["status"] = "queued"
            return dict(self.jobs[job_id])
        if job_id == "stage1":
            self.jobs[job_id]["status"] = "failed"
            return dict(self.jobs[job_id])
        return dict(job)

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        if plan_id != "plan-1":
            return None
        return {
            "id": plan_id,
            "status": "publishable_with_flags",
            "stage2_status": "stage2_failed",
            "final_plan_text": "Persisted plan",
            "structured_plan": {"schema_version": "1.0"},
            "why_log": {},
        }

    def complete_generation_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]:
        self.complete_calls.append(job_id)
        self.jobs[job_id]["status"] = str(kwargs["final_status"])
        return dict(self.jobs[job_id])

    def fail_generation_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]:
        self.fail_calls.append(job_id)
        self.jobs[job_id]["status"] = "failed"
        return dict(self.jobs[job_id])


async def _exercise_tick(monkeypatch) -> tuple[list[str], _RecoveryStore]:
    queued = {
        "id": "queued",
        "status": "queued",
        "created_at": _old_iso(5),
        "progress_milestones": [],
    }
    startup = _running_job("startup")
    worker_claim = _running_job(
        "worker-claim",
        milestones=[_milestone("job_loaded")],
    )
    stale_worker_claim_snapshot = dict(worker_claim)
    stage1 = _running_job(
        "stage1",
        milestones=[
            _milestone("job_loaded"),
            _milestone("request_payload_parsed"),
            _milestone("stage1_planner_invoked"),
        ],
    )
    mid = _running_job(
        "mid",
        milestones=[
            _milestone("job_loaded"),
            _milestone("request_payload_parsed"),
            _milestone("stage1_planner_finished"),
            _milestone("stage2_drafting"),
        ],
        stage1_result={},
    )
    persisted = _running_job(
        "persisted",
        milestones=[
            _milestone("job_loaded"),
            {
                **_milestone("final_result_persisted"),
                "meta": {"plan_id": "plan-1"},
            },
        ],
        stage1_result={},
        final_result={
            "status": "publishable_with_flags",
            "stage2_status": "stage2_failed",
        },
    )
    store = _RecoveryStore(
        {
            job["id"]: job
            for job in (queued, startup, worker_claim, stage1, mid, persisted)
        }
    )

    # Deliberately return a stale RPC snapshot after the recovery sweep has
    # already requeued the durable row. The worker must still reject the old
    # later-stage snapshot from claim/start.
    monkeypatch.setattr(
        worker,
        "list_claimable_generation_jobs",
        lambda *_args, **_kwargs: [queued, startup, stale_worker_claim_snapshot],
    )
    claimed: list[str] = []

    async def _record_claim(
        *,
        job_id: str,
        store: Any,
        active_tasks: set[str],
    ) -> None:
        claimed.append(job_id)
        active_tasks.discard(job_id)

    monkeypatch.setattr(worker, "_run_claimed_job", _record_claim)

    active_tasks: set[str] = set()
    detached_tasks: set[asyncio.Task[None]] = set()
    await worker._tick(
        store=store,
        active_tasks=active_tasks,
        detached_tasks=detached_tasks,
        stale_after_seconds=90,
        max_concurrent_jobs=10,
        recovery_state={},
        recovery_interval_seconds=5,
    )
    if detached_tasks:
        await asyncio.gather(*detached_tasks)
    return claimed, store


def test_every_candidate_is_claimed_or_deliberately_recovered(monkeypatch) -> None:
    claimed, store = asyncio.run(_exercise_tick(monkeypatch))

    assert claimed == ["queued", "startup"]
    assert set(store.recover_calls) == {"worker-claim", "stage1", "mid", "persisted"}
    assert store.complete_calls == ["persisted"]
    assert store.fail_calls == ["mid"]
    assert store.jobs["worker-claim"]["status"] == "queued"
    assert store.jobs["stage1"]["status"] == "failed"
    assert store.jobs["mid"]["status"] == "failed"
    assert store.jobs["persisted"]["status"] == "completed"
