"""Deterministic episode/routine cadence using existing accepted occurrences."""
from datetime import date, timedelta
from collections.abc import Mapping


def _training_demand(block, session):
    """Normalize plan prescriptions with the planner's existing intensity rules."""
    from api.structured_plan_generation import _block_intensity, _coerce_float, _NUMBER_RANGE_RE

    levels = [_block_intensity(dict(block))]
    for value in (block.get("effective_load"), block.get("load"), block.get("effort"),
                  block.get("intensity"), session.get("effective_load")):
        if isinstance(value, str):
            token = value.strip().lower()
            levels.append("high" if token in {"high", "hard", "heavy"} else
                          "moderate" if token in {"moderate", "medium", "technical"} else
                          "low" if token in {"low", "light", "reduced", "none"} else None)
        elif isinstance(value, Mapping):
            method = str(value.get("method") or "").lower()
            if method in {"rpe", "rir"}:
                effort = dict(value)
                effort["method"] = "RPE"
                if method == "rir":
                    rir = _coerce_float(value.get("value"))
                    if rir is None:
                        continue
                    if isinstance(value.get("value"), str):
                        bounds = _NUMBER_RANGE_RE.search(value["value"])
                        if bounds and bounds.group(2):
                            # Fewer reps in reserve is the harder end of a range.
                            rir = min(float(bounds.group(1)), float(bounds.group(2)))
                    effort["value"] = 10 - rir
                levels.append(_block_intensity({"effort": effort}))
            else:
                levels.append(_block_intensity({"load": dict(value)}))
    # A low/unknown block field must not hide known hard same-region work.
    return max((level for level in levels if level),
               key={"low": 0, "moderate": 1, "high": 2}.__getitem__, default=None)


def schedule_rehab(injury, decision, *, training_day, completions=(), exposures=(),
                   readiness_decision=None, training_session=None):
    def result(state, reason, next_day=None):
        return {"state": state, "reason": reason, "next_due_day": next_day}
    prescription = decision.get("prescription")
    if not prescription:
        return result("held" if decision.get("outcome") == "medical_review" else "unsupported", decision["summary"])
    today = date.fromisoformat(training_day)
    injury_id, episode_id = str(injury["id"]), str(injury["episode_id"])
    performed = []
    for completion in completions:
        if str(completion.get("athlete_id")) != str(injury.get("athlete_id")) or completion.get("status") not in {"started", "done", "modified"}:
            continue
        snapshot = completion.get("prescription_snapshot") or {}
        for block in snapshot.get("session", {}).get("blocks", []):
            if str(block.get("injury_id")) != injury_id or str(block.get("injury_episode_id")) != episode_id:
                continue
            day = date.fromisoformat(str(completion["training_day"]))
            if day == today:
                return result("already_completed", "Today's rehab allocation is reserved by your started session." if completion.get("status") == "started" else "You have already logged rehab for this injury today.", (today + timedelta(days=max(prescription["minimum_gap_days"], block.get("minimum_gap_days", 1)))).isoformat())
            if completion.get("status") in {"done", "modified"} and block.get("rehab_drill_id") == prescription["drill_id"]:
                performed.append((day, max(prescription["minimum_gap_days"], block.get("minimum_gap_days", 1))))
    # Legacy recorded rehab also spaces work; ordinary training has no such event.
    for row in exposures:
        raw = row.get("event_json") or row
        if str(row.get("athlete_id")) != str(injury.get("athlete_id")) or str(raw.get("injury_id")) != injury_id or str(raw.get("injury_episode_id")) != episode_id:
            continue
        day_text = (raw.get("provenance") or {}).get("training_day") or str(raw.get("occurred_at") or "")[:10]
        try:
            day = date.fromisoformat(day_text)
        except (TypeError, ValueError):
            continue
        if day == today:
            return result("already_completed", "You have already logged rehab for this injury today.", (today + timedelta(days=prescription["minimum_gap_days"])).isoformat())
        if (raw.get("drill_id") or raw.get("rehab_drill_id")) == prescription["drill_id"]:
            performed.append((day, prescription["minimum_gap_days"]))
    next_due = max((day + timedelta(days=gap) for day, gap in performed), default=today)
    if next_due > today:
        return result("recovery_day", "Allow the configured recovery gap before repeating this routine.", next_due.isoformat())
    if readiness_decision in {"stop", "not_checked_in"}:
        return result("held", "Complete today's check-in and follow its training guidance.")
    if prescription.get("is_loading"):
        if readiness_decision == "pull_back":
            return result("held", "Loading rehab is held by today's reduced-training guidance.")
        # No unknown or missing next-day response is treated as tolerance.
        recent = [r for r in exposures if str((r.get("event_json") or r).get("injury_episode_id")) == episode_id]
        if recent:
            latest = max(recent, key=lambda r: str((r.get("event_json") or r).get("occurred_at") or ""))
            response = (latest.get("event_json") or latest).get("response") or {}
            from .rehab_progression import _instant
            improved = _instant(injury.get("latest_reported_at"))
            observed = _instant(latest.get("response_recorded_at") or latest.get("created_at") or (latest.get("event_json") or latest).get("occurred_at"))
            explicit_later_improvement = injury.get("latest_reported_status") == "improving" and improved and observed and improved > observed
            if not explicit_later_improvement and (response.get("during_response") not in {"better", "same"} or response.get("next_day_response") not in {"better", "same"}):
                return result("held", "Loading rehab needs an injury-specific response to the last rehab session.")
        for block in (training_session or {}).get("blocks", []):
            if block.get("block_type") == "rehab":
                continue
            regions = block.get("mechanical_load_regions") or []
            demand = _training_demand(block, training_session or {})
            if decision.get("region") in regions and (demand == "high" or block.get("contact_level") == "full"):
                return result("deferred", "Demanding training already loads this region today.", (today + timedelta(days=1)).isoformat())
    return result("due", "Your baseline rehab is due today; missed work adds no extra volume.", training_day)
