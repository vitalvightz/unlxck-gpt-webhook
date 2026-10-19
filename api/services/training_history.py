"""One session-level history for Plan and adaptive consumers; no exercise rows."""
from datetime import datetime, timezone
import hashlib
import json

from fastapi import HTTPException

from api.contracts.external_training import ExternalTrainingCreate, ExternalTrainingFields, ExternalTrainingTakeaway
from api.contracts.training_day import resolve_training_day_str


def external_occurrence(row: dict) -> dict:
    return {**row, "source": "external", "status": "done", "plan_id": None,
            "session_id": f"external-{row['id']}", "title": row["activity"].title()}


def training_history(store, athlete_id: str, *, limit: int = 200, prescribed: list[dict] | None = None, external: list[dict] | None = None, include_skipped: bool = False) -> list[dict]:
    """Combine occurrences; callers supplying preloaded rows retain read health.

    An explicit empty list skips a source read; it does not prove availability.
    """
    if prescribed is None:
        prescribed = store.list_session_completions(athlete_id, limit=limit)
    if external is None:
        external = store.list_external_training_sessions(athlete_id, limit=limit)
    return _combine(athlete_id, prescribed, external, include_skipped)


def training_history_page(store, athlete_id: str, *, limit: int, before_day: str | None = None,
                          include_skipped: bool = False, manual_only: bool = False) -> tuple[list[dict], str | None]:
    """One History page of whole training days, newest first, and the cursor for the next.

    Each source reads ``limit`` rows before ``before_day``. When a source fills its
    read, its oldest day may be cut short, so that day moves to the next page.
    """
    prescribed = [] if manual_only else store.list_session_completions(athlete_id, limit=limit, before_day=before_day)
    external = store.list_external_training_sessions(athlete_id, limit=limit, before_day=before_day)
    rows = _combine(athlete_id, prescribed, external, include_skipped)
    full = [source for source in (prescribed, external) if len(source) >= limit]
    if not full:
        return rows, None
    # The newest day any full source reached may be missing rows, so it and
    # everything older is left to the next page, which reads before ``oldest``.
    cutoff = max(str(source[-1]["training_day"]) for source in full)
    kept = [row for row in rows if str(row["training_day"]) > cutoff]
    if not kept:
        # One day fills a whole read: keep it rather than stall the pager.
        return rows, cutoff
    return kept, min(str(row["training_day"]) for row in kept)


def _combine(athlete_id: str, prescribed: list[dict], external: list[dict], include_skipped: bool) -> list[dict]:
    rows = [
        {**row, "source": "unlxck", "completion_origin": row.get("completion_origin")} for row in prescribed
        if row.get("athlete_id") == athlete_id and row.get("status") in ({"done", "modified", "skipped"} if include_skipped else {"done", "modified"})
        and row.get("completion_origin") != "day_credit"
    ] + [external_occurrence(row) for row in external
         if row.get("athlete_id") == athlete_id and not row.get("deleted_at")]
    # IDs are scoped to their source. Name/date matches are distinct sessions.
    unique = {(row["source"], row.get("id") or row.get("session_id"), row.get("plan_id"), row["training_day"]): row for row in rows}
    return sorted(unique.values(), key=lambda row: (
        str(row["training_day"]), str(row.get("completed_at") or row.get("created_at") or ""),
        str(row.get("id") or "")), reverse=True)


def create_external_training(store, athlete_id: str, athlete_timezone: str | None,
                             body: ExternalTrainingCreate, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    current_day = resolve_training_day_str(now, athlete_timezone=athlete_timezone)
    training_day = body.training_day.isoformat() if body.training_day else current_day
    if training_day > current_day:
        raise HTTPException(422, "Training date cannot be after your current training day.")
    # Preserve existing request fingerprints when the optional date is omitted.
    fields = body.model_dump(mode="json", exclude={"client_request_id"}, exclude_none=True)
    fingerprint = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    row = store.create_external_training_session(athlete_id, {
        **fields, "client_request_id": str(body.client_request_id), "request_fingerprint": fingerprint,
        "training_day": training_day,
    })
    if row.get("deleted_at"):
        raise HTTPException(410, "This session was deleted. Log new work with a new request ID.")
    if row["request_fingerprint"] != fingerprint:
        raise HTTPException(409, "This request ID was already used for another session.")
    return external_occurrence(row)


def update_external_training(store, athlete_id: str, entry_id: str, body: ExternalTrainingFields) -> dict:
    row = store.update_external_training_session(athlete_id, entry_id, body.model_dump())
    if row is None:
        raise HTTPException(404, "Training session not found.")
    return external_occurrence(row)


def set_external_training_takeaway(store, athlete_id: str, entry_id: str, body: ExternalTrainingTakeaway) -> dict:
    row = store.set_external_training_takeaway(athlete_id, entry_id, body.takeaway)
    if row is None:
        raise HTTPException(404, "Training session not found.")
    return external_occurrence(row)


def delete_external_training(store, athlete_id: str, entry_id: str) -> None:
    # Keep a tombstone so a late retry of the initial POST cannot recreate it.
    if not store.delete_external_training_session(athlete_id, entry_id):
        raise HTTPException(404, "Training session not found.")
