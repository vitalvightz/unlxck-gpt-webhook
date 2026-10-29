"""Reproduce strength coverage/variety diagnostics without generating report files.

    python tools/audit_strength_pool_depth.py --selection --step 5 --seeds 0 1 2 3 4 5

The static pass counts eligible anchors. Selection uses PR #3101's 504-camp
sample, carrying GPP exposure into SPP. Missing labels are diagnostic, not
programme validity: bodyweight squats count as lower_body_loaded, and safety
or phase constraints may justify an unfilled role.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import itertools
import logging
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp import strength  # noqa: E402
from fightcamp.strength_session_quality import classify_strength_item  # noqa: E402
from fightcamp.training_context import normalize_athlete_equipment_list  # noqa: E402

PHASES = ("GPP", "SPP")
EQUIPMENT_TIERS = {
    "full": [
        "barbell", "dumbbells", "kettlebell", "bands", "medicine_ball", "sled", "cable",
        "pullup_bar", "trap_bar", "landmine", "bench", "machine", "sandbag", "bodyweight",
        "trx", "cable_machine",
    ],
    "home": ["dumbbells", "kettlebell", "bands", "pullup_bar", "bodyweight"],
    "min": ["bodyweight", "bands"],
}
REQUIRED_CATEGORIES = ("lower_body_loaded", "upper_body_push_pull", "unilateral")
GOALS = [["strength"], ["power"], ["explosive", "speed"], ["conditioning"], ["grappling"], ["striking", "power"], ["injury_prevention"]]
WEAKNESSES = [[], ["posterior_chain"], ["core"], ["upper_body"], ["grip"], ["hip_mobility"]]
STYLES = [["pressure_fighter"], ["counter_striker"], ["wrestler"], ["grappler"], ["kicker"]]
FATIGUE = ["low", "moderate"]
FREQUENCY = [3, 5]


def static_audit() -> dict:
    """Pool depth before athlete-specific scoring, injury and novelty filters."""
    cells = {}
    for phase, (tier, equipment) in itertools.product(PHASES, EQUIPMENT_TIERS.items()):
        access = set(normalize_athlete_equipment_list(equipment))
        anchors = []
        for exercise in strength.get_exercise_bank():
            details = " ".join(str(exercise.get(k) or "") for k in ("notes", "method", "movement"))
            if (phase not in exercise.get("phases", []) or strength._exercise_late_windows(exercise)
                    or not set(strength._required_strength_equipment(exercise)) <= access
                    or strength.is_banned_exercise(exercise.get("name", ""), exercise.get("tags", []), "mma", details)
                    or strength._is_supra_max_isometric(exercise)
                    or (phase == "SPP" and strength._is_over_100_percent_isometric(exercise))):
                continue
            profile = classify_strength_item(exercise)
            if profile["anchor_capable"]:
                anchors.append(profile)
        cells[f"{phase}/{tier}"] = {
            "anchors": len(anchors),
            **{category: sum(category in p["base_categories"] for p in anchors) for category in REQUIRED_CATEGORIES},
        }
    return cells


def _camp(goals, weaknesses, style, tier, fatigue, frequency, *, seed=None) -> dict[str, list[dict]]:
    from fightcamp.plan_pipeline_blocks import _is_rotational_power_anchor

    out = {}
    previous, movements, rotational_seen = [], set(), False
    for phase in PHASES:
        flags = {
            "phase": phase, "fatigue": fatigue, "equipment": EQUIPMENT_TIERS[tier], "fight_format": "mma",
            "style_tactical": style, "key_goals": goals, "training_frequency": frequency,
            "training_days": ["Mon", "Tue", "Wed", "Thu", "Fri"][:frequency], "days_until_fight": 56,
            "injuries": [], "random_seed": seed,
        }
        if previous:
            flags.update(prev_exercises=previous, recent_exercises=sorted(movements))
        if not rotational_seen:
            flags["rotational_power_camp_gap"] = True
        exercises = strength.generate_strength_block(flags=flags, weaknesses=weaknesses)["exercises"]
        out[phase] = exercises
        previous = list(dict.fromkeys(previous + [ex["name"] for ex in exercises]))
        movements |= {ex["movement"] for ex in exercises if ex.get("movement")}
        rotational_seen |= any(_is_rotational_power_anchor(ex) for ex in exercises)
    return out


def selection_audit(step: int, *, seeds=(None,)) -> dict:
    grid = list(itertools.product(GOALS, WEAKNESSES, STYLES, EQUIPMENT_TIERS, FATIGUE, FREQUENCY))[::step]
    report = {}
    for seed in seeds:
        for args in grid:
            for phase, exercises in _camp(*args, seed=seed).items():
                key = f"{seed}/{phase}/{args[3]}"
                cell = report.setdefault(key, {"camps": 0, "use": Counter(), "missing": Counter()})
                cell["camps"] += 1
                cell["use"].update(ex["name"] for ex in exercises)
                cell["missing"].update(strength.missing_base_categories(exercises))
    return {key: {"camps": cell["camps"], "distinct": len(cell["use"]), "missing": dict(cell["missing"])}
            for key, cell in report.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selection", action="store_true", help="also generate representative camps")
    parser.add_argument("--step", type=int, default=5, help="sample every Nth camp (default 5)")
    parser.add_argument("--seeds", type=int, nargs="*", default=[], help="extra seeded runs alongside unseeded")
    args = parser.parse_args()
    if args.step < 1:
        parser.error("--step must be a positive integer")
    logging.disable(logging.CRITICAL)
    # Generation normalizes rows in place; keep direct tooling calls isolated.
    original_loader = strength.get_exercise_bank
    bank = copy.deepcopy(original_loader())
    strength.get_exercise_bank = lambda: copy.deepcopy(bank)
    try:
        print("Eligible anchors (before athlete-specific filters):")
        for key, cell in static_audit().items():
            print(key, cell)
        if args.selection:
            print("Category labels only; missing labels do not establish programme deficiency.")
            for key, cell in selection_audit(args.step, seeds=(None, *args.seeds)).items():
                print(key, cell)
    finally:
        strength.get_exercise_bank = original_loader


if __name__ == "__main__":
    main()
