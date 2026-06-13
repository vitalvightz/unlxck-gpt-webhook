import pytest

from api.state_machine import (
    ATHLETE_DISPLAYABLE_PLAN_STATUSES,
    GENERATION_JOB_STATUSES,
    PLAN_STATUSES,
    can_transition,
    is_athlete_displayable_plan_status,
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


@pytest.mark.parametrize(
    ("from_status", "allowed_targets"),
    [
        (
            "triage_blocked",
            {"ready", "review_required", "held_for_review", "triage_blocked", "medical_hold", "restricted_rehab_only", "needs_review", "archived"},
        ),
        (
            "needs_review",
            {"ready", "review_required", "held_for_review", "needs_review", "restricted_rehab_only", "medical_hold", "archived"},
        ),
        (
            "restricted_rehab_only",
            {"ready", "held_for_review", "restricted_rehab_only", "needs_review", "archived"},
        ),
        (
            "medical_hold",
            {"medical_hold", "needs_review", "restricted_rehab_only", "archived"},
        ),
    ],
)
def test_protected_state_transition_matrix_is_explicit(from_status: str, allowed_targets: set[str]) -> None:
    actual = {candidate for candidate in PLAN_STATUSES if can_transition("plan", from_status, candidate)}
    assert actual == allowed_targets


@pytest.mark.parametrize("from_status", ["triage_blocked", "needs_review", "restricted_rehab_only"])
@pytest.mark.parametrize("resume_output", ["ready", "review_required", "held_for_review", "publishable_with_flags"])
def test_resume_outputs_are_allowed_from_resumable_protected_states(from_status: str, resume_output: str) -> None:
    expected = resume_output in {"ready", "held_for_review"} or (
        from_status in {"triage_blocked", "needs_review"} and resume_output == "review_required"
    )
    assert can_transition("plan", from_status, resume_output) is expected


def test_medical_hold_cannot_resume_directly_to_ready_or_publishable_states() -> None:
    assert not can_transition("plan", "medical_hold", "ready")
    assert not can_transition("plan", "medical_hold", "publishable_with_flags")
    assert not can_transition("plan", "medical_hold", "held_for_review")


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
        ("triage_blocked", "review_required"),
        ("archived", "completed"),
        ("review_required", "review_required"),
        ("held_for_review", "review_required"),
        ("medical_hold", "review_required"),
        ("restricted_rehab_only", "review_required"),
        ("needs_review", "review_required"),
        ("failed", "failed"),
        ("unknown", "review_required"),
    ],
)
def test_job_status_for_plan_status(plan_status: str, job_status: str) -> None:
    assert job_status_for_plan_status(plan_status) == job_status


def test_athlete_displayable_statuses_are_only_ready_and_publishable() -> None:
    assert set(ATHLETE_DISPLAYABLE_PLAN_STATUSES) == {"ready", "publishable_with_flags"}
    # Every displayable status must be a known plan status.
    assert set(ATHLETE_DISPLAYABLE_PLAN_STATUSES).issubset(set(PLAN_STATUSES))


@pytest.mark.parametrize(
    "status, displayable",
    [
        ("ready", True),
        ("publishable_with_flags", True),
        ("generated", False),
        ("review_required", False),
        ("held_for_review", False),
        ("triage_blocked", False),
        ("medical_hold", False),
        ("restricted_rehab_only", False),
        ("needs_review", False),
        ("archived", False),
        ("READY", True),  # case-insensitive
        ("unknown", False),
    ],
)
def test_is_athlete_displayable_plan_status(status: str, displayable: bool) -> None:
    assert is_athlete_displayable_plan_status(status) is displayable
