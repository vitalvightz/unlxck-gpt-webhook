from __future__ import annotations

import httpx
import logging
from unittest.mock import MagicMock

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


def test_delivery_failure_is_queued_for_retry(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("PLAN_READY_FROM_EMAIL", "UNLXCK <notifications@unlxck.test>")
    store = Store()
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [{
        "job_id": "job-1", "athlete_id": "athlete-1", "plan_id": "plan-1",
        "claim_token": "lease-1", "attempts": 1,
    }]
    store.client = client
    monkeypatch.setattr(plan_ready_email, "send_plan_ready_email", lambda *args, **kwargs: False)

    assert plan_ready_email.deliver_pending_plan_ready_emails(store) == 0
    values = client.table.return_value.update.call_args.args[0]
    assert values["status"] == "pending"
    assert "next_attempt_at" in values
    client.table.return_value.update.return_value.eq.assert_called_once_with("job_id", "job-1")


def test_delivery_stops_after_six_failed_attempts(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("PLAN_READY_FROM_EMAIL", "UNLXCK <notifications@unlxck.test>")
    store = Store()
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [{
        "job_id": "job-1", "athlete_id": "athlete-1", "plan_id": "plan-1",
        "claim_token": "lease-6", "attempts": 6,
    }]
    store.client = client
    monkeypatch.setattr(plan_ready_email, "send_plan_ready_email", lambda *args, **kwargs: False)

    assert plan_ready_email.deliver_pending_plan_ready_emails(store) == 0
    values = client.table.return_value.update.call_args.args[0]
    assert values["status"] == "failed"
    assert values["last_error_code"] == "retry_exhausted"


def test_delivery_success_records_sent_at(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("PLAN_READY_FROM_EMAIL", "UNLXCK <notifications@unlxck.test>")
    store = Store()
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [{
        "job_id": "job-1", "athlete_id": "athlete-1", "plan_id": "plan-1",
        "claim_token": "lease-1", "attempts": 2,
    }]
    store.client = client
    monkeypatch.setattr(plan_ready_email, "send_plan_ready_email", lambda *args, **kwargs: True)

    assert plan_ready_email.deliver_pending_plan_ready_emails(store) == 1
    values = client.table.return_value.update.call_args.args[0]
    assert values["status"] == "sent"
    assert "sent_at" in values


def test_missing_email_configuration_warns_once(monkeypatch, caplog):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("PLAN_READY_FROM_EMAIL", raising=False)
    monkeypatch.delenv("FEEDBACK_FROM_EMAIL", raising=False)
    plan_ready_email._warn_missing_config.cache_clear()
    store = Store()
    with caplog.at_level(logging.WARNING):
        assert not plan_ready_email.send_plan_ready_email(store, athlete_id="a", plan_id="p", job_id="j")
        assert plan_ready_email.deliver_pending_plan_ready_emails(store) == 0
    assert caplog.text.count("email_not_configured") == 1


def test_http_error_includes_status_code_without_response_body(monkeypatch, caplog):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("PLAN_READY_FROM_EMAIL", "UNLXCK <notifications@unlxck.test>")

    def rejected(url, **kwargs):
        return httpx.Response(422, text="private provider response", request=httpx.Request("POST", url))

    monkeypatch.setattr(plan_ready_email.httpx, "post", rejected)
    with caplog.at_level(logging.ERROR):
        assert not plan_ready_email.send_plan_ready_email(Store(), athlete_id="a", plan_id="p", job_id="j")
    assert "status_code=422" in caplog.text
    assert "private provider response" not in caplog.text
