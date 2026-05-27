import pytest

from api.state_machine import (
    GENERATION_JOB_STATUSES,
    PLAN_STATUSES,
    can_transition,
    is_generation_job_status,
    is_plan_status,
    job_status_for_plan_status,
    require_generation_job_transition,
    require_plan_transition,
)


def test_known_status_sets_include_review_and_triage_states() -> None:
    assert set(GENERATION_JOB_STATUSES) == {"queued", "running", "completed", "review_required", "failed"}
    assert {
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
    } == set(PLAN_STATUSES)


def test_generation_job_transition_examples_are_canonical() -> None:
    assert can_transition("generation_job", "queued", "running")
    assert not can_transition("generation_job", "queued", "completed")
    assert not can_transition("generation_job", "queued", "review_required")
    assert can_transition("generation_job", "running", "review_required")
    assert can_transition("generation_job", "running", "failed")
    assert can_transition("generation_job", "failed", "queued")
    assert not can_transition("job", "queued", "running")


def test_plan_transition_examples_are_canonical() -> None:
    assert can_transition("plan", "review_required", "ready")
    assert can_transition("plan", "triage_blocked", "ready")
    assert can_transition("plan", "triage_blocked", "held_for_review")
    assert can_transition("plan", "ready", "archived")
    assert not can_transition("plan", "archived", "ready")


def test_require_transition_rejects_unknown_or_invalid_states() -> None:
    with pytest.raises(ValueError, match="unknown generation job status"):
        require_generation_job_transition("running", "lost")
    with pytest.raises(ValueError, match="invalid generation job status transition"):
        require_generation_job_transition("completed", "failed")
    with pytest.raises(ValueError, match="unknown plan status"):
        require_plan_transition("ready", "lost")
    with pytest.raises(ValueError, match="invalid plan status transition"):
        require_plan_transition("archived", "ready")


def test_status_classification_does_not_mix_job_and_plan_lifecycles() -> None:
    assert is_generation_job_status("queued")
    assert not is_generation_job_status("medical_hold")
    assert is_plan_status("medical_hold")
    assert not is_plan_status("running")


@pytest.mark.parametrize(
    ("plan_status", "job_status"),
    [
        ("generated", "completed"),
        ("ready", "completed"),
        ("publishable_with_flags", "completed"),
        ("triage_blocked", "completed"),
        ("archived", "completed"),
        ("review_required", "review_required"),
        ("held_for_review", "review_required"),
        ("medical_hold", "review_required"),
        ("restricted_rehab_only", "review_required"),
        ("needs_review", "review_required"),
        ("unknown", "review_required"),
    ],
)
def test_job_status_for_plan_status(plan_status: str, job_status: str) -> None:
    assert job_status_for_plan_status(plan_status) == job_status
