from api.generation_job_helpers import _job_response


def _job(**overrides):
    job = {
        "id": "job_1234567890",
        "athlete_id": "athlete-1",
        "client_request_id": "request-1",
        "status": "running",
        "created_at": "2026-01-01T00:00:00+00:00",
        "progress_milestones": [
            {"code": "request_payload_parsed", "label": "Request payload parsed", "detail": "internal", "at": "2026-01-01T00:01:00+00:00", "meta": {"secret": "value"}},
            {"code": "stage1_planner_invoked", "label": "Stage 1 planner invoked", "detail": "model detail", "at": "2026-01-01T00:02:00+00:00"},
            {"code": "stage2_model_call_started", "label": "Stage 2 model call", "detail": "provider detail", "at": "2026-01-01T00:03:00+00:00"},
        ],
    }
    job.update(overrides)
    return job


def test_athlete_response_groups_milestones_and_removes_diagnostics():
    response = _job_response(_job(), viewer_role="athlete")
    assert [item.code for item in response.progress_milestones] == [
        "profile_ready", "designing_camp", "final_checks"
    ]
    assert all(item.meta == {} for item in response.progress_milestones)
    assert all("Stage" not in item.label for item in response.progress_milestones)


def test_non_admin_response_sanitizes_error_and_warnings():
    response = _job_response(
        _job(status="failed", error="worker traceback and provider model name", progress_milestones=[{
            "code": "stage2_flagged", "label": "flagged", "detail": "internal warning", "meta": {"warning": True}
        }]),
        viewer_role="athlete",
    )
    assert response.error == "Plan generation didn't complete this time. Please try again in a few moments."
    assert response.warnings == []


def test_admin_response_preserves_diagnostics_exactly():
    response = _job_response(_job(error="internal detail"), viewer_role="admin")
    assert response.error == "internal detail"
    assert response.progress_milestones[1].code == "stage1_planner_invoked"
    assert response.progress_milestones[1].detail == "model detail"
