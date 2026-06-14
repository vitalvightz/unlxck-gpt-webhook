from __future__ import annotations

from typing import Literal

GenerationJobStatus = Literal["queued", "running", "completed", "review_required", "failed"]
PlanStatus = Literal[
    "generated",
    "ready",
    "review_required",
    "held_for_review",
    "publishable_with_flags",
    "triage_blocked",
    "medical_hold",
    "restricted_rehab_only",
    "needs_review",
    "archived",
]

GENERATION_JOB_STATUSES: tuple[GenerationJobStatus, ...] = (
    "queued",
    "running",
    "completed",
    "review_required",
    "failed",
)
PLAN_STATUSES: tuple[PlanStatus, ...] = (
    "generated",
    "ready",
    "review_required",
    "held_for_review",
    "publishable_with_flags",
    "triage_blocked",
    "medical_hold",
    "restricted_rehab_only",
    "needs_review",
    "archived",
)

# Plan statuses at which a plan is athlete-displayable / publishable: the athlete
# can see the finalized plan. These are the only states where downstream,
# display-oriented work (e.g. building the structured_plan rendering payload)
# should run. Blocked, held, medical-gated, review-required, and archived states
# are deliberately excluded so nothing is published just to derive structured
# output.
#
# ``restricted_rehab_only`` is intentionally NOT included: it is a safety-gated
# "planning paused, clinician clearance required" state (see
# api/plan_mappers._map_plan_safety_state), not a normal athlete-facing training
# plan. Add it here only if the product decides to render rehab-only plans.
ATHLETE_DISPLAYABLE_PLAN_STATUSES: tuple[PlanStatus, ...] = (
    "ready",
    "publishable_with_flags",
)

# Plan statuses that keep a plan in the admin review/resume surface: it is held,
# blocked, or otherwise awaiting an admin decision. These are the states the
# support dashboard must surface so a held/paused plan never disappears from the
# review queue. ``publishable_with_flags`` is included because a flagged plan can
# still be awaiting admin sign-off before the athlete is notified.
ADMIN_REVIEW_PLAN_STATUSES: tuple[PlanStatus, ...] = (
    "review_required",
    "held_for_review",
    "needs_review",
    "triage_blocked",
    "medical_hold",
    "restricted_rehab_only",
    "publishable_with_flags",
)


def is_admin_review_plan_status(value: object) -> bool:
    """True when a plan status keeps the plan in the admin review/resume queue."""
    return normalize_status(value) in ADMIN_REVIEW_PLAN_STATUSES

_GENERATION_JOB_TRANSITIONS: dict[GenerationJobStatus, frozenset[GenerationJobStatus]] = {
    "queued": frozenset({"queued", "running", "failed"}),
    "running": frozenset({"queued", "running", "completed", "review_required", "failed"}),
    "failed": frozenset({"queued", "failed"}),
    "completed": frozenset({"queued", "completed"}),
    "review_required": frozenset({"queued", "review_required", "completed", "failed"}),
}

_PLAN_TRANSITIONS: dict[PlanStatus, frozenset[PlanStatus]] = {
    "generated": frozenset(
        {
            "generated",
            "ready",
            "review_required",
            "held_for_review",
            "publishable_with_flags",
            "triage_blocked",
            "medical_hold",
            "restricted_rehab_only",
            "needs_review",
            "archived",
        }
    ),
    "ready": frozenset({"ready", "review_required", "held_for_review", "publishable_with_flags", "archived"}),
    "publishable_with_flags": frozenset({"ready", "publishable_with_flags", "review_required", "archived"}),
    "review_required": frozenset({"ready", "review_required", "held_for_review", "archived"}),
    "held_for_review": frozenset({"ready", "review_required", "held_for_review", "archived"}),
    "triage_blocked": frozenset(
        {
            "ready",
            "review_required",
            "held_for_review",
            "triage_blocked",
            "medical_hold",
            "restricted_rehab_only",
            "needs_review",
            "archived",
        }
    ),
    "medical_hold": frozenset({"medical_hold", "needs_review", "restricted_rehab_only", "archived"}),
    "restricted_rehab_only": frozenset({"ready", "held_for_review", "restricted_rehab_only", "needs_review", "archived"}),
    "needs_review": frozenset({"ready", "review_required", "held_for_review", "needs_review", "restricted_rehab_only", "medical_hold", "archived"}),
    "archived": frozenset({"archived"}),
}

_PLAN_STATUS_TO_JOB_STATUS: dict[str, GenerationJobStatus] = {
    "generated": "completed",
    "ready": "completed",
    "publishable_with_flags": "completed",
    "triage_blocked": "review_required",
    "archived": "completed",
    "review_required": "review_required",
    "held_for_review": "review_required",
    "needs_review": "review_required",
    "medical_hold": "review_required",
    "restricted_rehab_only": "review_required",
    "failed": "failed",
}


def normalize_status(value: object) -> str:
    return str(value or "").strip().lower()


def is_generation_job_status(value: object) -> bool:
    return normalize_status(value) in GENERATION_JOB_STATUSES


def is_plan_status(value: object) -> bool:
    return normalize_status(value) in PLAN_STATUSES


def is_athlete_displayable_plan_status(value: object) -> bool:
    """True when a plan status is athlete-displayable/publishable.

    Canonical replacement for scattered ``status == "ready"`` style checks. See
    :data:`ATHLETE_DISPLAYABLE_PLAN_STATUSES`.
    """
    return normalize_status(value) in ATHLETE_DISPLAYABLE_PLAN_STATUSES


def can_transition(kind: Literal["generation_job", "plan"], current: object, next_status: object) -> bool:
    normalized_current = normalize_status(current)
    normalized_next = normalize_status(next_status)
    if kind == "generation_job":
        if normalized_current not in GENERATION_JOB_STATUSES or normalized_next not in GENERATION_JOB_STATUSES:
            return False
        return normalized_next in _GENERATION_JOB_TRANSITIONS[normalized_current]  # type: ignore[index]
    if kind == "plan":
        if normalized_current not in PLAN_STATUSES or normalized_next not in PLAN_STATUSES:
            return False
        return normalized_next in _PLAN_TRANSITIONS[normalized_current]  # type: ignore[index]
    return False


def require_generation_job_transition(current: object, next_status: object) -> GenerationJobStatus:
    normalized_current = normalize_status(current)
    normalized_next = normalize_status(next_status)
    if not is_generation_job_status(normalized_next):
        raise ValueError(f"unknown generation job status: {next_status!r}")
    if not is_generation_job_status(normalized_current):
        raise ValueError(f"unknown current generation job status: {current!r}")
    if not can_transition("generation_job", normalized_current, normalized_next):
        raise ValueError(f"invalid generation job status transition: {normalized_current} -> {normalized_next}")
    return normalized_next  # type: ignore[return-value]


def require_plan_transition(current: object, next_status: object) -> PlanStatus:
    normalized_current = normalize_status(current)
    normalized_next = normalize_status(next_status)
    if not is_plan_status(normalized_next):
        raise ValueError(f"unknown plan status: {next_status!r}")
    if not is_plan_status(normalized_current):
        raise ValueError(f"unknown current plan status: {current!r}")
    if not can_transition("plan", normalized_current, normalized_next):
        raise ValueError(f"invalid plan status transition: {normalized_current} -> {normalized_next}")
    return normalized_next  # type: ignore[return-value]


def job_status_for_plan_status(plan_status: object) -> GenerationJobStatus:
    normalized = normalize_status(plan_status)
    return _PLAN_STATUS_TO_JOB_STATUS.get(normalized, "review_required")
