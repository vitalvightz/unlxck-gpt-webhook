"""The intake injuries behind a plan, for an admin reviewing a triage-held plan.

The admin plan view summarizes why injury triage held a plan, and names the
injuries the athlete reported at intake. Only admins receive it (inside
``admin_outputs``), and it is only read for plans that carry an injury triage
record, so ordinary plan views pay nothing for it.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from api.models import AdminIntakeInjuries
from api.store import AppStore

from .today_service import _intake_payload_from_row, _intake_row_for_plan

logger = logging.getLogger(__name__)


def admin_intake_injuries(store: AppStore, plan_row: Mapping[str, Any]) -> AdminIntakeInjuries | None:
    why_log = plan_row.get("why_log")
    if not isinstance(why_log, Mapping) or not why_log.get("injury_triage"):
        return None
    athlete_id = str(plan_row.get("athlete_id") or "")
    try:
        payload = _intake_payload_from_row(
            _intake_row_for_plan(store, athlete_id=athlete_id, plan_row=plan_row)
        )
    except Exception:
        logger.exception("[admin] plan intake injuries read failed plan_id=%s", plan_row.get("id"))
        return None
    guided = [payload.get("guided_injury"), *(payload.get("guided_injuries") or [])]
    return AdminIntakeInjuries(
        injuries=str(payload.get("injuries") or ""),
        guided_injuries=[dict(injury) for injury in guided if isinstance(injury, Mapping)],
    )
