"""Transactional plan-ready email, sent only after a releasable plan is saved."""

from __future__ import annotations

import logging
import os
from email.utils import parseaddr
from html import escape
from pathlib import Path
from urllib.parse import quote

import httpx

from api.store import AppStore

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_TEMPLATE = Path(__file__).with_suffix(".html")


def send_plan_ready_email(store: AppStore, *, athlete_id: str, plan_id: str, job_id: str) -> bool:
    """Best-effort delivery. A failed email never changes the generated plan."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    configured_sender = os.getenv("PLAN_READY_FROM_EMAIL", "").strip()
    fallback_address = parseaddr(os.getenv("FEEDBACK_FROM_EMAIL", ""))[1]
    sender = configured_sender or (f"UNLXCK <{fallback_address}>" if fallback_address else "")
    if not api_key or not sender:
        return False

    plan = store.get_plan_for_athlete(plan_id, athlete_id)
    if not plan or str(plan.get("status") or "").lower() not in {"ready", "publishable_with_flags"}:
        return False
    profile = store.get_profile(athlete_id) or {}
    recipient = str(profile.get("email") or "").strip()
    if not recipient:
        return False

    link = f"https://unlxck.com/plans/{quote(plan_id, safe='')}"
    body = _TEMPLATE.read_text(encoding="utf-8").replace("{{PLAN_URL}}", escape(link, quote=True))
    try:
        response = httpx.post(
            _RESEND_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Idempotency-Key": f"plan-ready-{job_id}",
            },
            json={
                "from": sender,
                "to": [recipient],
                "subject": "Your UNLXCK training plan is ready",
                "html": body,
                "text": f"Your training plan is ready. Open it here: {link}",
            },
            timeout=5.0,
        )
        response.raise_for_status()
        logger.info("[plan_ready_email] sent job_id=%s plan_id=%s", job_id, plan_id)
        return True
    except Exception as exc:  # noqa: BLE001 - email must not break generation
        logger.error("[plan_ready_email] failed job_id=%s error_type=%s", job_id, type(exc).__name__)
        return False
