"""Deterministic goal contract at the resolved planner / renderer boundary.

PriorityProfile owns selection and emphasis. The short-camp buckets describe
session framing, not successful adaptations. Only scheduled, effective stimuli
can discharge this contract; neither role names nor LLM prose are evidence.
"""
from __future__ import annotations

from copy import deepcopy
from math import ceil
import re
from typing import Any

from .calendar_context import role_d_day, weekly_role_map_legality
from .conditioning import _conditioning_structured_profile
from .goal_repair_effective_contact_policy import (
    effective_goal_repair_compression_state,
    resolved_weekly_frequency_count,
)
from .prescription_resolver import (
    _role_kind,
    _slot_quality_class_effective,
    _strength_role_slot_groups,
    athlete_dose_state,
)
from .priority_profile import build_priority_profile, normalize_priority_values
from .role_labels import athlete_facing_label_for, stamp_role_label
from .tagging import normalize_tag


VERSION = "goal_preservation.v1"
INTENTS = {
    "strength": "meaningful_strength",
    "power": "ballistic_power",
    "speed": "speed_quality",
    "conditioning": "energy_system_training",
    "skill_refinement": "technical_practice",
    "footwork": "footwork_practice",
    "mobility": "mobility_dose",
    "recovery": "recovery_support",
    "weight_cut": "weight_cut_support",
}
_ALIASES = {"explosive_power": "power", "conditioning_endurance": "conditioning",
            "endurance": "conditioning", "speed_reaction": "speed"}
_COMPRESSION_REASONS = {
    "high_fatigue": "high_fatigue",
    "active_weight_cut": "weight_cut_pressure",
    "high_pressure_weight_cut": "weight_cut_pressure",
    "aggressive_weight_cut": "weight_cut_pressure",
    "injury_management": "injury_constraint",
    "fight_week_override": "fight_proximity",
}
_SPEED_TAGS = {"speed", "reactive", "reaction", "acceleration", "max_velocity", "speed_reaction"}
_TECHNICAL_TAGS = {"technical", "skill_refinement", "technical_footwork", "footwork", "coordination"}


def _goal(value: Any) -> str:
    token = normalize_tag(str(value or "")) or ""
    return _ALIASES.get(token, token)


def _athlete(brief: dict) -> dict:
    return brief.get("athlete_snapshot") or brief.get("athlete_model") or {}


def selected_goals(athlete: dict, focus: dict | None = None) -> list[tuple[str, str]]:
    """Retain every selection, including profiles supplied without PlanInput."""
    focus = focus or {}
    profile = build_priority_profile(athlete)
    primary = _goal(focus.get("primary_goal") or profile.primary_goal or athlete.get("primary_goal"))
    values = [primary, *profile.all_goals,
              *normalize_priority_values(athlete.get("secondary_goals")),
              *normalize_priority_values(focus.get("secondary_goals"))]
    goals = list(dict.fromkeys(_goal(value) for value in values if _goal(value)))
    return [(goal, "primary" if goal == primary else "secondary") for goal in goals]


def classify_goal_preservation(athlete: dict, focus: dict | None = None) -> list[dict]:
    """Initial obligations, never a claim that the schedule satisfied them."""
    days = athlete.get("days_until_fight")
    readiness = athlete_dose_state(athlete)
    limits = []
    if isinstance(days, int) and days <= 13:
        limits.append("fight_proximity")
    if readiness.get("high_fatigue"):
        limits.append("high_fatigue")
    if readiness.get("aggressive_weight_cut"):
        limits.append("weight_cut_pressure")
    return [
        {"goal": goal, "priority": priority,
         "state": "build" if priority == "primary" and not limits else "maintain",
         "reason_codes": [f"{priority}_goal", *limits],
         "required_intent": INTENTS.get(goal, f"selected_goal:{goal}"),
         "evidence": []}
        for goal, priority in selected_goals(athlete, focus)
    ]


def _late_fight_phase(brief: dict) -> str:
    """Recover the late-fight phase when the plan spec did not carry one.

    Prefer the earlier weekly allocation's phase when it is unambiguous; taper is
    the canonical late-fight phase otherwise. This deliberately never keys off
    ``candidate_pools`` ordering, which is not phase authority: with several
    active pools that would silently bind late-fight roles to the wrong pool.
    """
    phases = [
        week.get("phase")
        for week in (brief.get("weekly_role_map") or {}).get("weeks") or []
        if week.get("phase")
    ]
    unique = list(dict.fromkeys(phases))
    return unique[0] if len(unique) == 1 else "TAPER"


def _effective_map(brief: dict, *, phase: str | None = None) -> dict:
    # Direct countdown plans render the final visible sequence. Their weekly
    # map is a separate, earlier allocation and must not supply ghost evidence.
    # Still project the visible D-days into calendar_days so downstream
    # deferral checks can prove a real late-countdown/readiness constraint
    # instead of failing merely because the synthetic week had no calendar.
    if "late_fight_session_sequence" in brief:
        spec = brief.get("late_fight_plan_spec") or {}
        # The authoritative phase is the one that produced the late-fight
        # sequence, carried on late_fight_plan_spec.phase (or passed in by the
        # payload before prescription resolution). Never fall back to an
        # arbitrary candidate-pool key as phase authority.
        phase = phase or spec.get("phase") or _late_fight_phase(brief)
        roles = brief["late_fight_session_sequence"]
        suppressed = deepcopy(spec.get("suppressed_roles") or [])
        calendar_days = []
        seen_days: set[int] = set()
        # Project legal D-days from both the visible roles AND the relevant
        # suppressed roles, so _deferral_constraints() can associate a
        # suppression reason with its coverage window even when the only role on
        # a late D-day was the one that was removed.
        for role in [*roles, *suppressed]:
            day = role_d_day({}, role)
            if not isinstance(day, int) or day < 0 or day in seen_days:
                continue
            seen_days.add(day)
            calendar_days.append({
                "d_day": day,
                "is_fight_day": day == 0,
                "is_after_fight_day": False,
            })
        return {"weeks": [{
            "week_index": 1,
            "phase": phase,
            "session_roles": roles,
            "calendar_days": calendar_days,
            "suppressed_roles": suppressed,
        }]}
    return brief.get("weekly_role_map") or {}


def _tags(item: dict) -> set[str]:
    values = [*(item.get("movement_patterns") or []), *(item.get("tags") or []),
              item.get("primary_adaptation"), *(item.get("secondary_adaptations") or [])]
    return {_goal(value) for value in values if value}


def _number(value: Any) -> float:
    if isinstance(value, (list, tuple)):
        return min((_number(v) for v in value), default=0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _sets_reps(text: str) -> tuple[int, int]:
    # Bank dose syntax only. Never inspect rendered plan prose for semantics.
    match = re.search(r"(\d+)(?:\s*[-–]\s*\d+)?\s*(?:(?:sets?|holds?)\s*)?[x×]\s*(\d+)", text, re.I)
    return (int(match[1]), int(match[2])) if match else (0, 0)


def strength_intensity(text: str) -> dict:
    """Minimum declared working intensity, not an exercise-name inference."""
    rpe = re.search(r"(?:RPE\s*[:=]?\s*)(\d+(?:\.\d+)?)(?:\s*[-–]\s*\d+(?:\.\d+)?)?", text, re.I)
    effort = re.search(r"(\d+)(?:\s*[-–]\s*\d+)?/10\s*effort", text, re.I)
    percent = re.search(r"(\d+)(?:\s*[-–]\s*\d+)?\s*%", text)
    if rpe or effort:
        return {"minimum_rpe": float((rpe or effort)[1])}
    if percent:
        return {"minimum_load_percent": float(percent[1])}
    return {}


def _slot_allowed(slot: dict, role: dict, brief: dict) -> bool:
    selected = slot.get("selected") or {}
    if not selected or selected.get("restriction_hits", 0) or selected.get("blocked"):
        return False
    names = role.get("preferred_exercise_names") or []
    if names and selected.get("name") not in names:
        return False
    day = role_d_day({}, role)
    allowed_by_day = (brief.get("late_fight_plan_spec") or {}).get("allowed_exercises_by_day") or {}
    if f"D-{day}" in allowed_by_day and selected.get("name") not in allowed_by_day[f"D-{day}"]:
        return False
    if isinstance(day, int) and day <= 21 and selected.get("late_windows"):
        from .late_selector_windows import classify_late_selector_window
        if classify_late_selector_window(day) not in selected["late_windows"]:
            return False
    tags = _tags(selected) | set(selected.get("restriction_tags") or [])
    if tags & set(role.get("blocked_tags") or []):
        return False
    # Use canonical structured restriction keys, not an injury-name heuristic.
    restrictions = brief.get("restrictions") or []
    for restriction in restrictions:
        key = _goal(restriction.get("restriction") or restriction.get("key"))
        if key in {_goal(tag) for tag in selected.get("restriction_tags") or []}:
            return False
    return True


def _strength_stimuli(role: dict, slots: list[dict], brief: dict) -> list[dict]:
    stimuli = []
    capped = isinstance(role.get("strength_dose_cap"), dict)
    prescriptions = role.get("effective_strength_prescriptions") or []
    envelope = role.get("effective_strength_envelope") or {}
    cap = role.get("strength_dose_cap") or {}
    for slot in slots:
        if not _slot_allowed(slot, role, brief):
            continue
        selected = slot["selected"]
        resolved = next((p for p in prescriptions if p.get("slot_id") == slot.get("slot_id")
                         and p.get("name") == selected.get("name")), None)
        if capped and resolved is None:
            continue  # Missing effective authority cannot fall back to bank dose.
        dose = resolved or {"effective_prescription": selected.get("prescription", ""),
                            "dose_authority": "exercise_bank"}
        sets, reps = _sets_reps(str(dose.get("effective_prescription") or ""))
        sets = int(dose.get("effective_max_sets", sets))
        reps = int(dose.get("effective_max_reps", reps))
        if sets < 1 or reps < 1 or (capped and _number(cap.get("max_sets")) < 1):
            continue
        effective_slot = {**slot, **{key: selected[key] for key in ("quality_class", "anchor_capable", "support_only") if key in selected}}
        kind = _role_kind(effective_slot)
        quality = _slot_quality_class_effective(effective_slot)
        loaded = (kind in {"anchor", "secondary"} and quality == "anchor_loaded") or (
            quality == "anchor_force_isometric" and selected.get("real_strength_maintenance") is True)
        intensity = strength_intensity(str(dose.get("effective_prescription") or ""))
        meaningful_intensity = intensity.get("minimum_rpe", 0) >= 6 or intensity.get("minimum_load_percent", 0) >= 60
        intents = []
        if (loaded and sets >= 2 and meaningful_intensity and kind != "support" and cap.get("loaded_allowed") is not False
                and envelope.get("loaded_allowed") is not False
                and dose.get("effective_loaded") is not False):
            intents.append("meaningful_strength")
        if quality == "anchor_power" and kind == "power":
            intents.append("ballistic_power")
            if _tags(selected) & _SPEED_TAGS:
                intents.append("speed_quality")
        if not intents:
            continue
        stimuli.append({"slot_id": slot.get("slot_id"), "name": selected.get("name"),
                        "intents": intents, "quality_class": quality,
                        "effective_prescription": dose["effective_prescription"],
                        "dose_authority": dose["dose_authority"],
                        "sets": sets, "reps": reps,
                        "development_capable": sets >= 2,
                        **(intensity if "meaningful_strength" in intents else {})})
    return stimuli


def _other_stimuli(role: dict, pool: dict, brief: dict) -> list[dict]:
    stimuli = []
    category = role.get("category")
    system = role.get("preferred_system")
    for slot in pool.get("conditioning_slots") or []:
        if (category != "conditioning" or slot.get("role") != system
                or slot.get("session_index", 1) != role.get("session_index", 1)
                or not _slot_allowed(slot, role, brief)):
            continue
        selected = slot["selected"]
        # A recovery morph / support flush does not become energy-system work
        # through its old pool identity. Positive work metadata is required.
        if (role.get("late_camp_role_morph") or role.get("counts_toward_conditioning_cap") is False
                or system in (role.get("blocked_systems") or [])):
            continue
        minutes = _number(selected.get("total_minutes"))
        work = _number(selected.get("work_sec"))
        rounds = _number(selected.get("rounds"))
        if not (minutes > 0 or (work > 0 and rounds > 0)):
            continue
        if "duration_cap_minutes" in role:
            minutes = min(minutes, _number(role["duration_cap_minutes"]))
        if "round_cap" in role:
            rounds = min(rounds, _number(role["round_cap"]))
        intents = []
        if system in {"aerobic", "glycolytic"} and (minutes >= 6 or work * rounds >= 180):
            intents.append("energy_system_training")
        profile = _conditioning_structured_profile(selected, system=system)
        if system in {"alactic", "atp_pcr", "atp-pcr"} and work > 0 and rounds >= 2 and profile["alactic_structure"]:
            intents.append("speed_quality")
        if _tags(selected) & _TECHNICAL_TAGS:
            intents.append("technical_practice")
        if "footwork" in _tags(selected) or system == "technical_footwork":
            intents.append("footwork_practice")
        if intents:
            stimuli.append({"slot_id": slot.get("slot_id"), "name": selected.get("name"),
                            "intents": intents, "system": system,
                            "dose_authority": "structured_conditioning_dose",
                            "work_sec": work, "rounds": rounds, "total_minutes": minutes,
                            "rest_sec": _number(selected.get("rest_sec")),
                            "effective_prescription": selected.get("prescription") or ""})
    # Locked technical / mobility inserts have an actual deterministic duration.
    duration = _number(role.get("duration_min"))
    support = role.get("support_insert_category") or role.get("support_kind")
    if duration > 0:
        intents = []
        if category == "mobility" or support == "mobility":
            intents.append("mobility_dose")
        if category == "technical" or support in {"technical", "coordination", "technical_footwork"}:
            intents.append("technical_practice")
        if support == "technical_footwork":
            intents.append("footwork_practice")
        if category == "recovery" or support in {"recovery", "recovery_walk"}:
            intents.append("recovery_support")
        if support == "conditioning_maintenance" and duration >= 6:
            intents.append("energy_system_training")
        if intents:
            stimuli.append({"intents": intents, "duration_min": duration,
                            "name": (role.get("preferred_exercise_names") or [role.get("athlete_facing_label") or athlete_facing_label_for(role.get("role_key"))])[0],
                            "effective_prescription": f"{duration:g} minutes",
                            "development_capable": support != "conditioning_maintenance",
                            "dose_authority": "scheduled_support_dose"})
    return stimuli


def collect_goal_evidence(brief: dict) -> list[dict]:
    """Recompute from live schedule and effective prescriptions, ignoring caches."""
    role_map = _effective_map(brief)
    pools = brief.get("candidate_pools") or {}
    strength = {id(role): slots for _, role, slots in _strength_role_slot_groups(
        weekly_role_map=role_map, candidate_pools=pools)}
    evidence = []
    for week in role_map.get("weeks") or []:
        for index, role in enumerate(week.get("session_roles") or [], 1):
            day = role_d_day(week, role)
            if day is None or day <= 0 or role.get("render_mandatory") is False:
                continue
            if "late_fight_session_sequence" not in brief and not any(
                d.get("d_day") == day and not d.get("is_after_fight_day") and not d.get("is_fight_day")
                for d in week.get("calendar_days") or []
            ):
                continue
            if (role.get("governance") or {}).get("hard_suppression_reasons"):
                continue
            stimuli = _strength_stimuli(role, strength.get(id(role), []), brief)
            stimuli += _other_stimuli(role, pools.get(week.get("phase"), {}), brief)
            for stimulus in stimuli:
                # D-1 protocol can support readiness; never training adaptations.
                if day <= 1:
                    stimulus["intents"] = [v for v in stimulus["intents"] if v in {"recovery_support", "mobility_dose"}]
                if not stimulus["intents"]:
                    continue
                evidence.append({"week_index": week.get("week_index"), "phase": week.get("phase"),
                                 "session_index": role.get("session_index", index),
                                 "role_key": role.get("role_key"), "d_day": day,
                                 "development_quality": day > 13 and week.get("phase") != "TAPER" and stimulus.get("development_capable", True),
                                 **stimulus})
    # These selected goals are serviced by deterministic daily support, not S&C
    # slots. Do not count these records toward conditioning or strength.
    support = brief.get("computed_support") or {}
    for phase, recovery in (support.get("recovery", {}).get("by_phase") or {}).items():
        if _number(recovery.get("sleep_hours_target")) > 0 and recovery.get("core_strategies"):
            evidence.append({"phase": phase, "intents": ["recovery_support"],
                             "dose_authority": "computed_support.recovery", "development_quality": True,
                             "sleep_hours_target": recovery["sleep_hours_target"]})
    for phase, nutrition in (support.get("nutrition", {}).get("by_phase") or {}).items():
        if (nutrition.get("weight_cut") or {}).get("active") and nutrition.get("protein_g_per_day"):
            evidence.append({"phase": phase, "intents": ["weight_cut_support"],
                             "dose_authority": "computed_support.nutrition", "development_quality": True,
                             "risk_band": nutrition["weight_cut"].get("risk_band")})
    return evidence


def _requirements(entry: dict, brief: dict) -> list[dict]:
    """One build exposure per development week; maintenance every 14 days.

    Partial development windows share the same requirement. Final fight-week
    strength is excluded by its canonical loaded-work cutoff. Multiple lifts on
    one day cannot pay for multiple windows.
    """
    if entry["goal"] in {"recovery", "weight_cut"}:
        return [{"min_d_day": None, "max_d_day": None}]
    days = _athlete(brief).get("days_until_fight")
    if not isinstance(days, int):
        return [{"min_d_day": None, "max_d_day": None}]
    cutoff = 14 if entry["state"] == "build" else (8 if entry["goal"] == "strength" else 2)
    width = 7 if entry["state"] == "build" else 14
    span = max(1, days - cutoff + 1)
    return [{"min_d_day": cutoff + index * width, "max_d_day": min(days, cutoff + (index + 1) * width - 1)}
            for index in range(ceil(span / width))]


def _coverage(entry: dict, brief: dict, evidence: list[dict]) -> tuple[list[dict], list[dict]]:
    matching = [e for e in evidence if entry["required_intent"] in e["intents"]
                and (entry["state"] != "build" or e.get("development_quality"))]
    missing, witnesses = [], []
    for window in _requirements(entry, brief):
        witness = next((e for e in matching if window["min_d_day"] is None or
                       (e.get("d_day") is not None and window["min_d_day"] <= e["d_day"] <= window["max_d_day"])), None)
        if witness is None:
            missing.append(window)
        elif witness not in witnesses:
            witnesses.append(witness)
    return witnesses, missing


def _role_matches_goal(role: dict, goal: str) -> bool:
    category = role.get("category")
    if goal in {"strength", "power"}:
        return category == "strength"
    if goal == "speed":
        return category == "strength" or role.get("preferred_system") in {"alactic", "atp_pcr"}
    if goal == "conditioning":
        return category == "conditioning" and role.get("preferred_system") in {"aerobic", "glycolytic", "alactic"}
    if goal == "footwork":
        return category == "technical" or (category == "conditioning" and role.get("preferred_system") == "technical_footwork")
    return category == {"mobility": "mobility", "recovery": "recovery", "skill_refinement": "technical"}.get(goal)


def _restore_goal_roles(brief: dict, entry: dict) -> list[dict]:
    """Try retained planner candidates within their original week and budget.

    Intentional compression and finished tails are immutable. No new exercise,
    role family, dose, extra session capacity or contact rule is invented here.
    """
    from .late_camp_role_morph import apply_late_camp_role_morph
    from .prescription_resolver import apply_effective_strength_prescriptions

    audit = []
    if "late_fight_session_sequence" in brief:
        return audit
    role_map = brief.get("weekly_role_map") or {}
    for ordinal, week in enumerate(role_map.get("weeks") or []):
        candidates = week.get("goal_repair_candidates") or []
        existing = {(r.get("role_key"), r.get("strength_session_index")) for r in week.get("session_roles") or []}
        for candidate in candidates:
            identity = (candidate.get("role_key"), candidate.get("strength_session_index"))
            if identity in existing or not _role_matches_goal(candidate, entry["goal"]):
                continue
            suppressed = [r for r in week.get("suppressed_roles") or [] if r.get("role_key") == candidate.get("role_key")]
            compression, compression_codes = effective_goal_repair_compression_state(week, suppressed)
            if compression_codes or compression.get("active") or any((r.get("governance") or {}).get("hard_suppression_reasons") for r in suppressed):
                audit.append({"week_index": week.get("week_index"), "role_key": candidate.get("role_key"),
                              "result": "authority_preserved", "reason_codes": sorted(set(compression_codes))})
                continue
            # Original category budget (after phase/safety allocation), plus the
            # user's overall cap. Weekly-frequency occupancy comes from canonical
            # resolved load semantics, not raw role category/filler presence.
            roles = week.get("session_roles") or []
            original_cap = sum(r.get("category") == candidate.get("category") for r in candidates)
            current = sum(r.get("category") == candidate.get("category") for r in roles)
            total = resolved_weekly_frequency_count(roles)
            frequency = _number(_athlete(brief).get("training_frequency"))
            if current >= original_cap or (frequency and total >= frequency):
                audit.append({"week_index": week.get("week_index"), "result": "session_cap", "reason_codes": ["calendar_capacity"]})
                continue
            declared = {str(d).lower() for d in week.get("declared_training_days") or []}
            protected_days = {str(d.get("day") or "").lower() for d in week.get("intentionally_unused_days") or []}
            view = weekly_role_map_legality(role_map, week, ordinal)
            for day in week.get("calendar_days") or []:
                d_day = day.get("d_day")
                if (not isinstance(d_day, int) or d_day <= 13 or str(day.get("weekday")).lower() not in declared
                        or str(day.get("weekday")).lower() in protected_days):
                    continue
                decision = view.decision_for_role(candidate, d_day)
                if decision is None or not decision.allowed:
                    audit.append({"week_index": week.get("week_index"), "d_day": d_day,
                                  "result": "calendar_forbidden", "reason_codes": [decision.reason_code] if decision else []})
                    continue
                trial = deepcopy(brief)
                trial_week = trial["weekly_role_map"]["weeks"][ordinal]
                restored = deepcopy(candidate)
                restored.update(scheduled_day_hint=str(day["weekday"]).title(), scheduled_countdown_label=f"D-{d_day}",
                                session_index=max((r.get("session_index", 0) for r in roles), default=0) + 1)
                restored["goal_preservation_repair"] = {"goal": entry["goal"], "authority": VERSION}
                trial_week["session_roles"].append(restored)
                apply_late_camp_role_morph(trial["weekly_role_map"])
                apply_effective_strength_prescriptions(weekly_role_map=trial["weekly_role_map"],
                                                      candidate_pools=trial.get("candidate_pools") or {}, athlete_model=_athlete(trial))
                _, missing_before = _coverage(entry, brief, collect_goal_evidence(brief))
                _, missing_after = _coverage(entry, trial, collect_goal_evidence(trial))
                # A repair may not pay for this goal by erasing another stimulus.
                retained = {(e.get("d_day"), e.get("name"), tuple(e["intents"])) for e in collect_goal_evidence(trial)}
                if len(missing_after) >= len(missing_before) or any(
                    (e.get("d_day"), e.get("name"), tuple(e["intents"])) not in retained for e in collect_goal_evidence(brief)
                ):
                    continue
                trial_week["suppressed_roles"] = [r for r in trial_week.get("suppressed_roles") or [] if r.get("role_key") != candidate.get("role_key")]
                brief["weekly_role_map"] = trial["weekly_role_map"]
                # The goal_repair reservoir holds pre-finalization role copies, so
                # a restored role reaches the finalizer without the athlete-facing
                # label surviving roles get from stamp_weekly_role_map_labels. Give
                # it the same final decoration now (after the morph has run so any
                # morph-owned label wins), rather than appending a stale copy.
                stamp_role_label(restored)
                audit.append({"week_index": week.get("week_index"), "d_day": d_day, "result": "restored", "reason_codes": []})
                return audit + _restore_goal_roles(brief, entry) if missing_after else audit
    return audit


def _deferral_constraints(entry: dict, brief: dict, missing: list[dict]) -> list[dict]:
    """Every uncovered window needs a live, causal higher-authority reason."""
    if not missing:
        return []
    days = _athlete(brief).get("days_until_fight")
    if isinstance(days, int) and (days <= 1 or (entry["goal"] == "strength" and days <= 7)):
        return [{"reason_code": "fight_proximity", "authority": "late_fight_strength_dose_cap" if entry["goal"] == "strength" else "fight_day_protocol", "days_until_fight": days}]
    reasons = []
    for window in missing:
        window_reasons = []
        for week in _effective_map(brief).get("weeks") or []:
            calendar = [d.get("d_day") for d in week.get("calendar_days") or [] if isinstance(d.get("d_day"), int)]
            if window["min_d_day"] is not None and not any(window["min_d_day"] <= d <= window["max_d_day"] for d in calendar):
                continue
            for row in week.get("suppressed_roles") or []:
                if not _role_matches_goal(row, entry["goal"]):
                    continue
                for code in row.get("compression_reason_codes") or []:
                    if code in _COMPRESSION_REASONS:
                        window_reasons.append({"reason_code": _COMPRESSION_REASONS[code], "authority": "planner_compression",
                            "source_reason_code": code, "week_index": week.get("week_index"), "role_key": row.get("role_key"),
                            "coverage_window": window})
                if row.get("calendar_integrity") and row.get("reason_code"):
                    window_reasons.append({"reason_code": "calendar_capacity", "authority": "final_calendar_integrity",
                        "source_reason_code": row["reason_code"], "week_index": week.get("week_index"), "role_key": row.get("role_key"),
                        "coverage_window": window})
            if entry["goal"] == "strength":
                readiness = athlete_dose_state(_athlete(brief))
                for role in week.get("session_roles") or []:
                    cap = role.get("strength_dose_cap") or {}
                    if _number(cap.get("max_sets")) < 2:
                        continue
                    # A reduce-only readiness override can turn a legitimate
                    # two-set retention exposure into one set. That is causal
                    # evidence; merely having an injury flag is not.
                    if any(p.get("effective_loaded") and p.get("effective_max_sets") == 1
                           for p in role.get("effective_strength_prescriptions") or []):
                        for flag, code in (("high_fatigue", "high_fatigue"), ("aggressive_weight_cut", "weight_cut_pressure"), ("injury_restricted", "injury_constraint")):
                            if readiness.get(flag):
                                window_reasons.append({"reason_code": code, "authority": "effective_strength_prescriptions",
                                    "week_index": week.get("week_index"), "role_key": role.get("role_key"), "coverage_window": window})
        if not window_reasons:
            return []  # One explained gap must not conceal another unexplained gap.
        reasons.extend(window_reasons)
    return reasons


def reconcile_goal_preservation(brief: dict) -> dict:
    """Repair, then decide; unresolved obligations remain blocking obligations."""
    entries = classify_goal_preservation(_athlete(brief), brief.get("priority_focus"))
    for entry in entries:
        initial_state = entry["state"]
        matching, missing = _coverage(entry, brief, collect_goal_evidence(brief))
        audit = _restore_goal_roles(brief, entry) if missing else []
        matching, missing = _coverage(entry, brief, collect_goal_evidence(brief))
        constraints = _deferral_constraints(entry, brief, missing) if missing else []
        if missing and constraints:
            # Prefer retaining a maintenance promise over deferring a primary.
            maintained = {**entry, "state": "maintain"}
            maintenance_evidence, maintenance_missing = _coverage(maintained, brief, collect_goal_evidence(brief))
            if entry["state"] == "build" and not maintenance_missing:
                entry["state"] = "maintain"
                matching, missing = maintenance_evidence, []
            else:
                entry["state"] = "defer"
            entry["reason_codes"] += list(dict.fromkeys(c["reason_code"] for c in constraints))
        entry.update(initial_state=initial_state, evidence=matching, constraints=constraints, repair_attempts=audit,
                     coverage_requirements=_requirements({**entry, "state": initial_state} if entry["state"] == "defer" else entry, brief), missing_coverage=missing,
                     satisfied=not missing and entry["state"] != "defer")
    brief["goal_preservation_version"] = VERSION
    brief["goal_preservation"] = entries
    compressed = deepcopy(brief.get("compressed_priorities") or _athlete(brief).get("compressed_priorities") or {})
    compressed["goal_preservation"] = entries
    brief["compressed_priorities"] = compressed
    _athlete(brief)["compressed_priorities"] = compressed
    # Correct legacy per-role success claims AFTER effective dose resolution.
    evidence = collect_goal_evidence(brief)
    summary = {"checked": 0, "satisfied": 0, "unsatisfied": 0, "unsatisfied_roles": []}
    for week in _effective_map(brief).get("weeks") or []:
        for role in week.get("session_roles") or []:
            validation = role.get("intent_validation") or {}
            if validation.get("intent") == "meaningful_strength":
                survives = any(e.get("week_index") == week.get("week_index") and e.get("d_day") == role_d_day(week, role)
                               and e.get("role_key") == role.get("role_key") and "meaningful_strength" in e["intents"] for e in evidence)
                role["intent_validation"] = {**validation, "satisfied": survives, "authority": "post_prescription_goal_reconciliation"}
                if not survives:
                    role["intent_validation"]["reason_code"] = "effective_stimulus_lost"
                else:
                    role["intent_validation"].pop("reason_code", None)
                    role["intent_validation"].pop("reason", None)
            if role.get("intent_validation"):
                summary["checked"] += 1
                if role["intent_validation"].get("satisfied"):
                    summary["satisfied"] += 1
                else:
                    summary["unsatisfied"] += 1
                    summary["unsatisfied_roles"].append({"role_key": role.get("role_key"),
                        "intent": role["intent_validation"].get("intent"), "scheduled_d_day": role_d_day(week, role),
                        "reason_code": role["intent_validation"].get("reason_code")})
    if brief.get("weekly_role_map"):
        brief["weekly_role_map"]["post_morph_intent_validation"] = summary
    return brief


def validate_goal_preservation(brief: dict) -> list[dict]:
    """Fail closed on missing, forged or stale states. Never repair in validation."""
    goals = selected_goals(_athlete(brief), brief.get("priority_focus"))
    entries = brief.get("goal_preservation")
    # Legacy stored briefs stay readable; any dated planner with selected goals
    # is required to carry a contract when submitted for publication.
    if not goals:
        return []
    if brief.get("payload_variant") == "open_ongoing_stage2_payload" and not brief.get("goal_preservation_version"):
        return []
    # A resolved dated payload that carries goal-preservation entries must also
    # carry the current contract version before publication validation. Without
    # this, a brief with valid-looking states/evidence but a missing or stale
    # version would slip stale contract semantics through. A brief with no entries
    # at all is not "resolved": it falls through to the per-goal checks below,
    # which report the missing contract for each selected goal.
    if (brief.get("payload_variant") != "open_ongoing_stage2_payload"
            and isinstance(entries, list) and entries
            and brief.get("goal_preservation_version") != VERSION):
        return [{
            "code": "goal_preservation_contract_stale",
            "requirement": "goal_preservation_version",
            "message": "Resolved dated payload must carry the current goal-preservation contract version.",
            "expected_version": VERSION,
            "actual_version": brief.get("goal_preservation_version"),
            "severity": "blocker",
            "confidence": "high",
        }]
    errors = []
    evidence = collect_goal_evidence(brief)
    initial = {e["goal"]: e for e in classify_goal_preservation(_athlete(brief), brief.get("priority_focus"))}
    for goal, priority in goals:
        rows = [e for e in entries or [] if isinstance(e, dict) and e.get("goal") == goal] if isinstance(entries, list) else []
        message = ""
        if len(rows) != 1:
            message = "Selected goal must have exactly one deterministic final state."
        else:
            entry = rows[0]
            if entry.get("state") not in {"build", "maintain", "defer"} or entry.get("required_intent") != INTENTS.get(goal, f"selected_goal:{goal}") or entry.get("priority") != priority:
                message = "Goal state or semantic requirement is invalid."
            elif entry.get("state") == "defer":
                obligation = {**entry, "state": "maintain"}
                _, missing = _coverage(obligation, brief, evidence)
                _, original_missing = _coverage(initial[goal], brief, evidence)
                justified = _deferral_constraints(initial[goal], brief, original_missing)
                if not missing or not justified or entry.get("constraints") != justified or not all(c["reason_code"] in (entry.get("reason_codes") or []) for c in justified):
                    message = "Deferred goal lacks a current, causal higher-authority reason."
            else:
                current, missing = _coverage(entry, brief, evidence)
                if missing or not current:
                    message = "Selected goal has no qualifying effective coverage; deterministic repair or justified deferral is required."
                elif entry.get("evidence") != current:
                    message = "Goal evidence is stale relative to the final schedule/prescription."
                elif entry["state"] == "maintain" and initial[goal]["state"] == "build":
                    _, build_missing = _coverage(initial[goal], brief, evidence)
                    constraints = _deferral_constraints(initial[goal], brief, build_missing)
                    if not constraints or entry.get("constraints") != constraints:
                        message = "Primary goal was downgraded without a higher-authority constraint."
        if message:
            errors.append({"code": "goal_preservation_failed", "goal": goal, "requirement": goal,
                           "message": message, "severity": "blocker", "confidence": "high"})
    return errors
