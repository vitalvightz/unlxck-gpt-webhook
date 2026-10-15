"""Offline Stage 1 comparison; run this same file from each checkout.

No database writes, providers, saved-plan regeneration or bank edits. Production
did not persist a seed: --seed controls a comparison, not a claimed historical
stochastic reproduction. The source fixture changes only the athlete's name.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

# Deliberately use the selected checkout, even when this script lives elsewhere.
sys.path.insert(0, str(Path.cwd()))

from api.models import PlanRequest
from fightcamp import input_parsing, stage2_payload, stage2_planning_brief
from fightcamp.calendar_context import contact_refs, role_d_day
from fightcamp.combat_load_policy import LoadClass
from fightcamp.goal_preservation import _effective_map, collect_goal_evidence
from fightcamp.main import generate_plan_sync
from fightcamp.physical_session_frequency import (
    PHYSICAL_SUPPORT_ROLE_KEYS, cadence_windows, is_physical_session_role,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/physical_stimulus/saved_intake.json"
CLOCK = datetime(2026, 10, 15, 12, 36, 40)


def cases(source: dict) -> dict[str, dict]:
    saved = source["intake"]
    scenarios = {"saved_plan": deepcopy(saved)}
    for days in (28, 56):
        intake = deepcopy(saved)
        intake["fight_date"] = (CLOCK + timedelta(days=days)).date().isoformat()
        scenarios[f"boxing_{days}_day"] = intake
    intake = deepcopy(saved)
    intake.update(fight_date=(CLOCK + timedelta(days=10)).date().isoformat(),
                  injuries="", guided_injury=None, guided_injuries=[],
                  hard_sparring_days=["Thursday"], reduced_contact_requested=False)
    intake["athlete"]["target_weight_kg"] = intake["athlete"]["weight_kg"]
    scenarios["low_risk_10_day"] = intake
    # An independent actual longer boxing intake already recorded in #2876.
    scenarios["recorded_boxing_52_day"] = json.loads(
        (ROOT / "tests/fixtures/programme_fidelity/affected_intake.json").read_text())
    return scenarios


def role_records(role_map: dict) -> list[dict]:
    records = []
    for week in role_map.get("weeks") or []:
        for role in week.get("session_roles") or []:
            doses = {p["name"]: p.get("effective_prescription")
                     for p in role.get("effective_strength_prescriptions") or []}
            records.append({
                "week": week.get("week_index"), "phase": week.get("phase"),
                "d_day": role_d_day(week, role), "role_key": role.get("role_key"),
                "category": role.get("category"), "physical": is_physical_session_role(role),
                "exercises": [{"name": m.get("name"), "slot_id": m.get("slot_id"),
                               "prescription": doses.get(m.get("name")) or m.get("effective_prescription")
                               or m.get("base_prescription"),
                               "slot_group": m.get("slot_group")}
                              for m in role.get("selected_exercise_assignments") or []],
                "composition": role.get("strength_composition_policy") or role.get("conditioning_composition_policy"),
            })
    return records


def appointments(records: list[dict]) -> list[dict]:
    """Independently count standalone appointments, not occupied weekdays."""
    full = [r for r in records if r["physical"] and isinstance(r["d_day"], int) and r["d_day"] > 0
            and r["role_key"] not in PHYSICAL_SUPPORT_ROLE_KEYS]
    occupied = {r["d_day"] for r in full}
    support = {}
    for r in records:
        if (r["physical"] and isinstance(r["d_day"], int) and r["d_day"] > 0
                and r["role_key"] in PHYSICAL_SUPPORT_ROLE_KEYS and r["d_day"] not in occupied):
            support.setdefault(r["d_day"], r)
    return full + list(support.values())


def replay(intake: dict, *, seed: int = 1, clock: datetime = CLOCK, include_generation_day: bool = False) -> tuple[dict, dict]:
    intake = deepcopy(intake)
    intake["random_seed"] = seed
    payload = PlanRequest(**intake).to_payload()
    payload["include_generation_day"] = include_generation_day
    trace = []
    original = getattr(stage2_payload, "enforce_total_session_budget", None)

    def budget_trace(role_map, *args, **kwargs):
        before = role_records(role_map)
        result = original(role_map, *args, **kwargs)
        after = role_records(role_map)
        trace.append({"filter": "enforce_total_session_budget", "removed": [r for r in before if r not in after]})
        return result

    with patch.object(input_parsing, "_utc_now", lambda: clock), patch.object(stage2_planning_brief, "_utc_now", lambda: clock):
        if original:
            with patch.object(stage2_payload, "enforce_total_session_budget", budget_trace):
                result = generate_plan_sync(payload)
        else:
            result = generate_plan_sync(payload)
    brief = result.get("planning_brief")
    if not brief:
        raise RuntimeError(f"Stage 1 did not produce a brief: {result.get('status')} {result.get('error')}")
    role_map = _effective_map(brief)
    records = role_records(role_map)
    standalone = appointments(records)
    slots = [(d["d_day"], d.get("weekday", ""))
             for w in role_map.get("weeks") or [] for d in w.get("calendar_days") or []]
    frequency = intake["weekly_training_frequency"]
    counts = [{"from_d_day": max(d for d, _ in days), "to_d_day": min(d for d, _ in days),
               "appointments": sum(r["d_day"] in {d for d, _ in days} for r in standalone),
               "requested": frequency} for days in cadence_windows(slots)]
    contacts = [{"d_day": ref.d_day, "effective_load": ref.profile.load_class.value,
                 "allows_compatible_sc": ref.profile.allows_light_combat_stack,
                 "reason_codes": ref.entry.get("reason_codes")}
                for ref in contact_refs(role_map)]
    if "late_fight_session_sequence" in brief:
        from fightcamp.stage2_payload_late_fight import resolve_late_fight_contacts
        from fightcamp.combat_load_policy import contact_load_profile
        contacts = [{"d_day": day, "effective_load": contact_load_profile({"effective_load": load}).load_class.value,
                     "allows_compatible_sc": contact_load_profile({"effective_load": load}).allows_light_combat_stack}
                    for day, load in resolve_late_fight_contacts(brief["athlete_snapshot"]["days_until_fight"], brief["athlete_snapshot"])]
    from fightcamp.sparring_dose_planner import hard_sparring_cutoff
    summary = {
        "requested_weekly_sessions": frequency, "physical_appointments": len(standalone),
        "sc_sessions": sum(bool(r["exercises"]) and r["category"] in {"strength", "conditioning"} for r in standalone),
        "cadence_counts": counts, "count_exceeded": any(c["appointments"] > frequency for c in counts),
        "hard_sparring_cutoff": hard_sparring_cutoff(brief["athlete_snapshot"]),
        "effective_hard_appointments": sum(c["effective_load"] == LoadClass.HARD_CONTACT.value for c in contacts),
        "contacts": contacts, "roles": records,
        "goals": brief.get("goal_preservation"), "evidence": collect_goal_evidence(brief),
        "suppressed": [{"week": w.get("week_index"), **r} for w in role_map.get("weeks") or []
                       for r in w.get("suppressed_roles") or []],
        "budget_trace": trace, "restrictions": brief.get("restrictions"),
        "realised_load_revalidation": role_map.get("realised_load_revalidation"),
    }
    return brief, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    source = json.loads(SOURCE.read_text())
    output = {"revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "seed": args.seed, "source_plan_id": source["source_plan_id"], "cases": {}}
    for name, intake in cases(source).items():
        if args.case and name not in args.case:
            continue
        clock = datetime(2026, 10, 14, 3, 40) if name == "recorded_boxing_52_day" else CLOCK
        _, summary = replay(intake, seed=args.seed, clock=clock,
                            include_generation_day=source["planner_context"]["include_generation_day"] if name == "saved_plan" else False)
        output["cases"][name] = summary
        print(name, summary["physical_appointments"], "physical;", summary["sc_sessions"], "S&C; cadence",
              [c["appointments"] for c in summary["cadence_counts"]], flush=True)
    args.output.write_text(json.dumps(output, indent=2, default=str) + "\n")


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    main()
