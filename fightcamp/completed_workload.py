"""Shared evidence for the existing readiness rules; never a contact assessment.

Reported Hard is qualitative demanding work, not an RPE measurement. Actual
minutes stay separate from session counts: there is no invented minutes-to-RPE
or minutes-to-fatigue conversion. The existing repeated-session rule owns its
threshold; durations are retained and aggregated as evidence, not estimated.
"""
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any


def completion_origin_of(row: Mapping[str, Any]) -> str | None:
    """Stored provenance, or ``reported`` when a legacy NULL row proves execution.

    Only evidence owned by one executed occurrence counts: its frozen
    prescription snapshot, rehab result or rehab response contexts. Legacy
    sibling credit copied RPE, pain and notes, so those prove nothing.
    """
    origin = row.get("completion_origin")
    if origin is not None:
        return origin
    if row.get("prescription_snapshot") or row.get("rehab_performance") or row.get("rehab_response_contexts"):
        return "reported"
    return None


def has_unverified_completions(rows: Sequence[Mapping[str, Any]], as_of: str, *, days: int = 5) -> bool:
    """Unverified legacy records are not proof of independent workouts.

    No guessed grouping: consumers use their existing incomplete-history floor.
    """
    today = date.fromisoformat(as_of)
    for row in rows:
        if (row.get("source", "unlxck") != "unlxck"
                or row.get("status") not in {"done", "modified"}
                or completion_origin_of(row) in {"reported", "day_credit"}):
            continue
        try:
            age = (today - date.fromisoformat(str(row.get("training_day", "")))).days
        except ValueError:
            continue
        if 0 <= age < days:
            return True
    return False


def completed_workload(rows: Sequence[Mapping[str, Any]], as_of: str, *, days: int = 5, limit: int | None = 3) -> dict:
    try:
        today = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        today = None
    unique = {}
    for index, row in enumerate(rows):
        # Only explicit reports prove prescribed workout identity, including
        # when raw completion rows reach this shared helper without a source.
        if row.get("source") != "external" and completion_origin_of(row) != "reported":
            continue
        # Missing status is retained for legacy readiness inputs. Explicit
        # planned/started/skipped rows never represent completed workload.
        if row.get("status", "done") not in {"done", "modified"} or row.get("deleted_at"):
            continue
        if today is not None:
            try:
                age = (today - date.fromisoformat(str(row.get("training_day", "")))).days
            except ValueError:
                continue
            if not 0 <= age < days:
                continue
        key = (row.get("source", "unlxck"), row.get("id") or row.get("session_id") or index,
               row.get("plan_id"), row.get("training_day"))
        unique[key] = row
    demanding = minutes = hard_minutes = 0
    recent = list(unique.values())[:limit] if limit is not None else list(unique.values())
    for row in recent:
        duration = row.get("duration_minutes")
        actual = duration if type(duration) is int and 1 <= duration <= 600 else 0
        minutes += actual
        if row.get("source") == "external":
            hard = row.get("effort") == "hard" and actual > 0
        else:
            rpe = row.get("session_rpe")
            if rpe is None:
                rpe = row.get("rpe")
            try:
                hard = int(rpe or 0) >= 8
            except (TypeError, ValueError):
                hard = False
            try:
                hard = hard or int(row.get("pain_after") or 0) >= 6
            except (TypeError, ValueError):
                pass
        demanding += int(hard)
        if hard:
            hard_minutes += actual
    return {"sessions": len(recent), "demanding_sessions": demanding,
            "actual_minutes": minutes, "hard_minutes": hard_minutes}
