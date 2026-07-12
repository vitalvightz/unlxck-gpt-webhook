"""Non-blocking, best-effort operator email for persisted beta feedback."""

from __future__ import annotations

import logging
import os

import httpx

from api.models import FeedbackRecord, ProfileRecord

logger = logging.getLogger(__name__)

DEFAULT_FEEDBACK_RECIPIENT = "unlxckedmind@gmail.com"
RESEND_EMAILS_URL = "https://api.resend.com/emails"


def feedback_notification_recipient() -> str:
    return os.getenv("FEEDBACK_NOTIFICATION_EMAIL", DEFAULT_FEEDBACK_RECIPIENT).strip() or DEFAULT_FEEDBACK_RECIPIENT


def send_feedback_notification(record: FeedbackRecord, profile: ProfileRecord) -> None:
    """Attempt one notification after persistence; failures are logged and discarded."""

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("FEEDBACK_FROM_EMAIL", "").strip()
    if not api_key or not sender:
        logger.warning(
            "[feedback_notification] skipped feedback_id=%s error_code=email_not_configured",
            record.id,
        )
        return

    recipient = feedback_notification_recipient()
    priority_label = "SAFETY" if record.priority == "safety" else "New"
    subject = f"[{priority_label}] Unlxck feedback: {record.category.replace('_', ' ')}"
    admin_url = os.getenv("FEEDBACK_ADMIN_URL", "").strip()
    lines = [
        "New beta feedback has been saved.",
        "",
        f"Priority: {record.priority}",
        f"Surface: {record.surface}",
        f"Category: {record.category}",
        f"Response: {record.response or 'not applicable'}",
        f"Reason: {record.reason or 'not provided'}",
        f"Screenshot attached in admin storage: {'yes' if record.has_screenshot else 'no'}",
        f"Submitted by authenticated role: {profile.role}",
        f"Feedback ID: {record.id}",
    ]
    if admin_url:
        lines.extend(["", f"Review securely: {admin_url}"])
    lines.extend(
        [
            "",
            "Comments, health snapshots, uploaded images, and private technical context are intentionally excluded from email. Review them only in the authenticated admin tools.",
        ]
    )

    try:
        response = httpx.post(
            RESEND_EMAILS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Idempotency-Key": f"feedback-{record.id}-{record.updated_at or record.created_at}"[:256],
            },
            json={
                "from": sender,
                "to": [recipient],
                "subject": subject,
                "text": "\n".join(lines),
            },
            timeout=5.0,
        )
        response.raise_for_status()
        logger.info(
            "[feedback_notification] sent feedback_id=%s surface=%s category=%s priority=%s",
            record.id,
            record.surface,
            record.category,
            record.priority,
        )
    except Exception as exc:  # Background delivery must remain failure-isolated.
        logger.error(
            "[feedback_notification] failed feedback_id=%s surface=%s category=%s priority=%s error_code=email_delivery_failed error_class=%s",
            record.id,
            record.surface,
            record.category,
            record.priority,
            type(exc).__name__,
        )
