from __future__ import annotations

import httpx

from api.services import plan_ready_email


class Store:
    def __init__(self, status: str = "ready") -> None:
        self.status = status

    def get_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict:
        return {"id": plan_id, "athlete_id": athlete_id, "status": self.status}

    def get_profile(self, athlete_id: str) -> dict:
        return {"email": "fighter@example.test"}


def test_sends_branded_plan_email_after_publication(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("PLAN_READY_FROM_EMAIL", "UNLXCK <notifications@unlxck.test>")
    captured = {}

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(plan_ready_email.httpx, "post", post)
    assert plan_ready_email.send_plan_ready_email(Store(), athlete_id="athlete-1", plan_id="plan-1", job_id="job-1")

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Idempotency-Key"] == "plan-ready-job-1"
    assert captured["json"]["to"] == ["fighter@example.test"]
    assert captured["json"]["subject"] == "Your UNLXCK training plan is ready"
    assert captured["json"]["html"].count("https://unlxck.com/plans/plan-1") == 2
    assert "View my plan" in captured["json"]["html"]
    assert "https://unlxck.com/plans/plan-1" in captured["json"]["text"]
    assert "injury" not in captured["json"]["html"].lower()


def test_never_emails_unreleased_plan(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("PLAN_READY_FROM_EMAIL", "UNLXCK <notifications@unlxck.test>")
    monkeypatch.setattr(plan_ready_email.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sent")))
    assert not plan_ready_email.send_plan_ready_email(Store("review_required"), athlete_id="a", plan_id="p", job_id="j")


def test_missing_sender_does_not_send(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.delenv("PLAN_READY_FROM_EMAIL", raising=False)
    monkeypatch.delenv("FEEDBACK_FROM_EMAIL", raising=False)
    monkeypatch.setattr(plan_ready_email.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sent")))
    assert not plan_ready_email.send_plan_ready_email(Store(), athlete_id="a", plan_id="p", job_id="j")


def test_transport_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("PLAN_READY_FROM_EMAIL", "UNLXCK <notifications@unlxck.test>")

    def fail(*args, **kwargs):
        raise httpx.ConnectError("temporary failure")

    monkeypatch.setattr(plan_ready_email.httpx, "post", fail)
    assert not plan_ready_email.send_plan_ready_email(Store(), athlete_id="a", plan_id="p", job_id="j")
