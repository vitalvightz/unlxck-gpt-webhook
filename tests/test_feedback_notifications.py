from __future__ import annotations

from types import SimpleNamespace

from api.services import feedback_notifications


class _Response:
    def raise_for_status(self) -> None:
        return None


def _record(**overrides):
    values = {
        "id": "feedback-1",
        "priority": "safety",
        "surface": "daily_recommendation",
        "category": "recommendation_safety",
        "response": "unsafe",
        "reason": None,
        "has_screenshot": False,
        "created_at": "2026-07-12T20:00:00+00:00",
        "updated_at": "2026-07-12T20:00:00+00:00",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_notification_uses_default_operator_email_and_excludes_sensitive_content(monkeypatch):
    captured: dict = {}
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("FEEDBACK_FROM_EMAIL", "Unlxck <feedback@unlxck.test>")
    monkeypatch.delenv("FEEDBACK_NOTIFICATION_EMAIL", raising=False)

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return _Response()

    monkeypatch.setattr(feedback_notifications.httpx, "post", fake_post)
    feedback_notifications.send_feedback_notification(
        _record(),
        SimpleNamespace(role="athlete", email="private@example.com"),
    )

    assert captured["json"]["to"] == ["unlxckedmind@gmail.com"]
    assert captured["json"]["subject"].startswith("[SAFETY]")
    body = captured["json"]["text"]
    assert "private@example.com" not in body
    assert "health snapshots" in body
    assert captured["headers"]["Idempotency-Key"].startswith("feedback-feedback-1-")


def test_notification_failure_is_isolated(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("FEEDBACK_FROM_EMAIL", "Unlxck <feedback@unlxck.test>")
    monkeypatch.setattr(
        feedback_notifications.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider down")),
    )

    feedback_notifications.send_feedback_notification(
        _record(priority="normal", category="bug_report"),
        SimpleNamespace(role="admin", email="admin@example.com"),
    )
