from __future__ import annotations

from api.services import notification_templates
from api.services.notification_templates import BUNDLED_TEMPLATES, select_notification_template


class EmptyTemplateStore:
    def list_notification_templates(self, intent: str, *, locale: str = "en-GB"):
        return []


def _template(intent: str, variant_id: str):
    return next(
        template
        for template in BUNDLED_TEMPLATES
        if template.intent == intent and template.variant_id == variant_id
    )


def test_planned_time_does_not_claim_session_happened(monkeypatch) -> None:
    monkeypatch.setattr(
        notification_templates,
        "list_recent_notification_deliveries",
        lambda *args, **kwargs: [],
    )
    title, body, variant_id, _version = select_notification_template(
        EmptyTemplateStore(),
        profile_id="athlete-1",
        intent="post_session_log",
        dedupe_key="post-session-log:session-1:2026-08-26:1",
        context={"_timing_confidence": "high", "_session_started": False},
    )

    assert variant_id.startswith("pl-low-")
    assert title == "TRAINED YET?"
    assert "if training" in body.lower() or "when you're done" in body.lower()


def test_started_session_can_use_definitive_post_session_copy(monkeypatch) -> None:
    monkeypatch.setattr(
        notification_templates,
        "list_recent_notification_deliveries",
        lambda *args, **kwargs: [],
    )
    _title, _body, variant_id, _version = select_notification_template(
        EmptyTemplateStore(),
        profile_id="athlete-1",
        intent="post_session_log",
        dedupe_key="post-session-log:session-1:2026-08-26:1",
        context={"_timing_confidence": "high", "_session_started": True},
    )

    assert not variant_id.startswith("pl-low-")


def test_high_pain_copy_does_not_invent_yesterday() -> None:
    variants = [
        template
        for template in BUNDLED_TEMPLATES
        if template.intent == "high_pain_followup"
    ]
    assert variants
    assert all("yesterday" not in f"{item.title_template} {item.body_template}".lower() for item in variants)


def test_recovery_copy_does_not_invent_specific_adjacent_sessions() -> None:
    rc01 = _template("recovery_checkin", "rc-01")
    rn05 = _template("recovery_nudge", "rn-05")
    rn06 = _template("recovery_nudge", "rn-06")

    copy = " ".join(
        (
            rc01.title_template,
            rc01.body_template,
            rn05.title_template,
            rn05.body_template,
            rn06.title_template,
            rn06.body_template,
        )
    ).lower()
    assert "yesterday" not in copy
    assert "last session" not in copy
    assert "tomorrow" not in copy


def test_generic_d1_copy_does_not_assume_weight_cut() -> None:
    d1 = _template("fight_countdown", "fc-d01")
    assert "make weight" not in d1.body_template.lower()
    assert d1.body_template == "No chasing fitness now. Stay calm and follow the plan."
