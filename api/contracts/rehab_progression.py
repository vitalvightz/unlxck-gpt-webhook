"""Baseline recovery only. No clinician report or camp phase advances a stage."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from fightcamp.rehab_clinical import ClinicalPolicy


def _instant(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def episode_setback_at(injury: Mapping[str, Any], exposures: Sequence[Mapping[str, Any]]):
    negatives = []
    for row in exposures:
        raw = row.get("event_json") or row
        if str(row.get("athlete_id")) != str(injury.get("athlete_id")):
            continue
        if str(raw.get("injury_id")) != str(injury.get("id")) or str(raw.get("injury_episode_id")) != str(injury.get("episode_id")):
            continue
        response, dose = raw.get("response") or {}, raw.get("dose_completed") or {}
        if (response.get("during_response") == "worse" or response.get("next_day_response") == "worse"
                or response.get("stopped_due_to_symptoms") or response.get("worsening_reported") or dose.get("stopped_early")):
            stamp = _instant(row.get("response_recorded_at") or row.get("created_at") or raw.get("occurred_at"))
            if stamp is None:
                return datetime.max.replace(tzinfo=timezone.utc)
            negatives.append(stamp)
    return max(negatives, default=None)


def resolve_reviewed_progression(injury: Mapping[str, Any], *, base_stage: str,
                                policy: ClinicalPolicy, exposures: Sequence[Mapping[str, Any]],
                                history_truncated: bool = False) -> dict[str, Any]:
    # Retain the callable name for generation/Today callers and old integrations.
    stage = base_stage if base_stage in {"calm", "restore"} else "calm"
    reasons = ["baseline_only_v1"]
    setback = episode_setback_at(injury, exposures)
    reported_at = _instant(injury.get("updated_at"))
    improving_after = injury.get("latest_reported_status") == "improving" and reported_at and setback and reported_at > setback
    if injury.get("latest_reported_status") == "worse" or (setback and not improving_after):
        stage, reasons = "calm", ["episode_setback_loading_held"]
    if history_truncated:
        reasons.append("older_history_truncated_no_advanced_progression")
    return {"stage": stage, "reason_codes": reasons, "evidence_ids": [], "engine_version": "2"}
