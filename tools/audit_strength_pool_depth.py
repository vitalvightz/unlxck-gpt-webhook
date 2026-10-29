"""Read-only audit of strength-bank pool depth for GPP/SPP selection variety.

Run from any directory:
    python tools/audit_strength_pool_depth.py                 # static pool audit
    python tools/audit_strength_pool_depth.py --selection     # + generated camps
    python tools/audit_strength_pool_depth.py --json out.json

Why: the strength selector is deterministic and picks the top of a scored
pool. When the pool an athlete is eligible for is barely larger than the slots
a phase needs, the same exercises are picked for nearly everyone, and the
required movement categories are met by luck. This audit measures that pool
with the selector's own eligibility rules (phase tag, late-window gating,
equipment, sport bans) and its own quality classifier, then lists existing
bank rows a coach could review for extra phase tags. It changes nothing; every
listed row is a review candidate, never an approved change.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import io
import itertools
import json
import logging
from pathlib import Path
import sys
from contextlib import redirect_stdout

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with redirect_stdout(io.StringIO()):  # silence degraded-parser notice
    from fightcamp import strength  # noqa: E402
from fightcamp.training_context import normalize_athlete_equipment_list  # noqa: E402
from fightcamp.strength_session_quality import classify_strength_item  # noqa: E402

PHASES = ("GPP", "SPP")
# Representative intake tiers. "min" is what a fighter with no gym reports.
EQUIPMENT_TIERS = {
    "full": [
        "barbell", "dumbbells", "kettlebell", "bands", "medicine_ball", "sled", "cable",
        "pullup_bar", "trap_bar", "landmine", "bench", "machine", "sandbag", "bodyweight",
        "trx", "cable_machine",
    ],
    "home": ["dumbbells", "kettlebell", "bands", "pullup_bar", "bodyweight"],
    "min": ["bodyweight", "bands"],
}
# Base categories the selector requires in every block (missing_base_categories).
REQUIRED_CATEGORIES = ("lower_body_loaded", "upper_body_push_pull", "unilateral")
# A cell this shallow cannot rotate: every eligible athlete gets the same rows.
THIN_CELL_MAX = 2
FIGHT_FORMAT = "mma"


def _equipment_ok(exercise: dict, tier: list[str]) -> bool:
    required = strength._required_strength_equipment(exercise)
    return set(required).issubset(set(normalize_athlete_equipment_list(tier)))


def _banned(exercise: dict) -> bool:
    details = " ".join(str(exercise.get(k, "") or "") for k in ("notes", "method", "movement"))
    return strength.is_banned_exercise(exercise.get("name", ""), exercise.get("tags", []), FIGHT_FORMAT, details)


def _steady_state_bank() -> list[dict]:
    """Private copy of the loaded (movement-normalized) bank, so the audit never touches the cache."""
    return copy.deepcopy(strength.get_exercise_bank())


def _raw_bank() -> list[dict]:
    """Bank rows as authored: tags normalized, ``movement`` as written in the JSON."""
    rows = json.loads((REPO_ROOT / "data" / "exercise_bank.json").read_text(encoding="utf-8"))
    for row in rows:
        strength.normalize_item_tags(row)
    return rows


def _profile(exercise: dict) -> dict:
    profile = classify_strength_item(exercise)
    return {
        "name": exercise.get("name", ""),
        "movement": exercise.get("movement"),
        "quality_class": profile["quality_class"],
        "anchor_capable": bool(profile["anchor_capable"]),
        "base_categories": sorted(profile["base_categories"]),
        "phases": list(exercise.get("phases", [])),
        "equipment": strength._required_strength_equipment(exercise) or ["bodyweight"],
        "cost_class": exercise.get("cost_class"),
        "late_window_only": bool(strength._exercise_late_windows(exercise)),
    }


def _classification_flips(steady: list[dict]) -> list[dict]:
    """Rows whose authored movement classifies differently from the planner's normalized one."""
    flips = []
    for raw, normalized in zip(_raw_bank(), steady):
        before, after = classify_strength_item(raw), classify_strength_item(normalized)
        if before["quality_class"] == after["quality_class"] and set(before["base_categories"]) == set(after["base_categories"]):
            continue
        flips.append({
            "name": raw.get("name", ""),
            "movement": [raw.get("movement"), normalized.get("movement")],
            "quality_class": [before["quality_class"], after["quality_class"]],
            "categories_gained": sorted(set(after["base_categories"]) - set(before["base_categories"])),
            "categories_lost": sorted(set(before["base_categories"]) - set(after["base_categories"])),
        })
    return sorted(flips, key=lambda row: row["name"])


def static_audit() -> dict:
    bank = _steady_state_bank()
    rows = [(exercise, _profile(exercise)) for exercise in bank]
    usable = [(ex, p) for ex, p in rows if not p["late_window_only"] and not _banned(ex)]

    phase_counts = Counter(phase for _, p in usable for phase in p["phases"])
    untagged = [p["name"] for _, p in usable if not set(p["phases"]) & set(PHASES)]

    cells: dict = {}
    for phase, (tier_name, tier) in itertools.product(PHASES, EQUIPMENT_TIERS.items()):
        eligible = [(ex, p) for ex, p in usable if phase in p["phases"] and _equipment_ok(ex, tier)]
        anchors = [p for _, p in eligible if p["anchor_capable"]]
        by_movement = defaultdict(list)
        for p in anchors:
            by_movement[p["movement"]].append(p["name"])
        by_category = {
            category: sorted(p["name"] for p in anchors if category in p["base_categories"])
            for category in REQUIRED_CATEGORIES
        }
        cells[f"{phase}/{tier_name}"] = {
            "eligible": len(eligible),
            "eligible_anchors": len(anchors),
            "anchors_by_movement": {m: sorted(n) for m, n in sorted(by_movement.items())},
            "required_category_anchors": by_category,
        }

    # Near-miss review list: rows that would fill a thin required-category cell
    # if a coach judged them appropriate for that phase. Equipment and sport
    # rules already pass for the tier; only the phase tag is missing.
    review: dict = {}
    for phase, (tier_name, tier) in itertools.product(PHASES, EQUIPMENT_TIERS.items()):
        cell = cells[f"{phase}/{tier_name}"]
        for category, names in cell["required_category_anchors"].items():
            if len(names) > THIN_CELL_MAX:
                continue
            candidates = [
                {k: p[k] for k in ("name", "phases", "movement", "quality_class", "equipment", "cost_class")}
                for ex, p in usable
                if phase not in p["phases"]
                and p["anchor_capable"]
                and category in p["base_categories"]
                and _equipment_ok(ex, tier)
            ]
            review[f"{phase}/{tier_name}/{category}"] = {
                "current": names,
                "phase_tag_candidates": sorted(candidates, key=lambda c: c["name"]),
            }

    # Rows whose load classification looks inconsistent with their equipment:
    # a bodyweight drill counted as "lower_body_loaded" can satisfy that
    # required category on paper without loading anything.
    load_anomalies = sorted(
        (
            {"name": p["name"], "equipment": p["equipment"], "phases": p["phases"], "movement": p["movement"]}
            for _, p in usable
            if "lower_body_loaded" in p["base_categories"] and set(p["equipment"]) <= {"bodyweight", "open_space"}
        ),
        key=lambda row: row["name"],
    )

    return {
        "bank_rows": len(rows),
        "late_window_only_rows": sum(1 for _, p in rows if p["late_window_only"]),
        "phase_tag_counts": dict(sorted(phase_counts.items())),
        "rows_without_gpp_or_spp": len(untagged),
        "cells": cells,
        "thin_required_category_review": review,
        "bodyweight_rows_classed_lower_body_loaded": load_anomalies,
        "movement_normalization_classification_flips": _classification_flips(bank),
    }


# Representative camps for the optional selection pass. Same grid used in the
# variety investigation: goals x weaknesses x styles x equipment x fatigue x frequency.
GOALS = [["strength"], ["power"], ["explosive", "speed"], ["conditioning"], ["grappling"], ["striking", "power"], ["injury_prevention"]]
WEAKNESSES = [[], ["posterior_chain"], ["core"], ["upper_body"], ["grip"], ["hip_mobility"]]
STYLES = [["pressure_fighter"], ["counter_striker"], ["wrestler"], ["grappler"], ["kicker"]]
FATIGUE = ["low", "moderate"]
FREQUENCY = [3, 5]


def _camp(goals, weaknesses, style, tier, fatigue, frequency) -> dict[str, list[dict]]:
    """GPP then SPP, carrying prior names like plan_pipeline_blocks does."""
    from fightcamp.plan_pipeline_blocks import _is_rotational_power_anchor

    out: dict[str, list[dict]] = {}
    previous: list[str] = []
    movements: set[str] = set()
    rotational_seen = False
    for phase in PHASES:
        flags = {
            "phase": phase, "fatigue": fatigue, "equipment": EQUIPMENT_TIERS[tier], "fight_format": FIGHT_FORMAT,
            "style_tactical": style, "key_goals": goals, "training_frequency": frequency,
            "training_days": ["Mon", "Tue", "Wed", "Thu", "Fri"][:frequency], "days_until_fight": 56, "injuries": [],
        }
        if previous:
            flags["prev_exercises"] = previous
            flags["recent_exercises"] = sorted(movements)
        if not rotational_seen:
            flags["rotational_power_camp_gap"] = True
        block = strength.generate_strength_block(flags=flags, weaknesses=weaknesses)
        out[phase] = block["exercises"]
        previous = list(dict.fromkeys(previous + [ex["name"] for ex in block["exercises"]]))
        movements |= {ex["movement"] for ex in block["exercises"] if ex.get("movement")}
        rotational_seen = rotational_seen or any(_is_rotational_power_anchor(ex) for ex in block["exercises"])
    return out


def selection_audit(step: int) -> dict:
    grid = list(itertools.product(GOALS, WEAKNESSES, STYLES, EQUIPMENT_TIERS, FATIGUE, FREQUENCY))[::step]
    # Every camp starts from the same steady-state bank, so one camp's
    # write-backs cannot change the next camp's candidates.
    steady = _steady_state_bank()
    original_loader = strength.get_exercise_bank
    strength.get_exercise_bank = lambda: copy.deepcopy(steady)
    try:
        return _selection_report(grid)
    finally:
        strength.get_exercise_bank = original_loader


def _selection_report(grid: list) -> dict:
    use: dict = defaultdict(Counter)
    camps: Counter = Counter()
    missing: dict = defaultdict(Counter)
    for goals, weaknesses, style, tier, fatigue, frequency in grid:
        camp = _camp(goals, weaknesses, style, tier, fatigue, frequency)
        for phase, exercises in camp.items():
            key = f"{phase}/{tier}"
            camps[key] += 1
            use[key].update(ex["name"] for ex in exercises)
            for category in strength.missing_base_categories(exercises):
                missing[key][category] += 1
    report = {}
    for key in sorted(camps):
        total = camps[key]
        report[key] = {
            "camps": total,
            "distinct_selected": len(use[key]),
            "selected_in_80pct_or_more": sorted(n for n, c in use[key].items() if c / total >= 0.8),
            "blocks_missing_required_category": dict(missing[key]),
            "top_share": [[n, round(c / total * 100)] for n, c in use[key].most_common(8)],
        }
    return report


def _markdown(static: dict, selection: dict | None) -> str:
    lines = ["# Strength pool depth audit", ""]
    lines.append(
        f"Bank rows: {static['bank_rows']} ({static['late_window_only_rows']} late-window-only). "
        f"Phase tags: {static['phase_tag_counts']}. Rows tagged for neither GPP nor SPP: "
        f"{static['rows_without_gpp_or_spp']}."
    )
    lines += ["", "## Eligible pool per phase and equipment tier", "",
              "| Cell | Eligible | Anchors | " + " | ".join(REQUIRED_CATEGORIES) + " |",
              "|---|---|---|" + "---|" * len(REQUIRED_CATEGORIES)]
    for key, cell in static["cells"].items():
        cats = " | ".join(str(len(cell["required_category_anchors"][c])) for c in REQUIRED_CATEGORIES)
        lines.append(f"| {key} | {cell['eligible']} | {cell['eligible_anchors']} | {cats} |")
    lines += ["", f"## Thin required-category cells (≤{THIN_CELL_MAX} eligible anchors)", ""]
    for key, entry in static["thin_required_category_review"].items():
        lines.append(f"### {key}")
        lines.append(f"- Currently eligible: {', '.join(entry['current']) or '**none**'}")
        if entry["phase_tag_candidates"]:
            lines.append("- Existing rows a coach could review for this phase tag:")
            for c in entry["phase_tag_candidates"]:
                lines.append(
                    f"  - {c['name']} — tagged {'/'.join(c['phases'])}, {c['movement']}, "
                    f"{c['quality_class']}, cost {c['cost_class']}, equipment {'/'.join(c['equipment'])}"
                )
        else:
            lines.append("- No existing row fits: this cell needs a new equipment-appropriate exercise.")
        lines.append("")
    lines += ["## Bodyweight rows counted as `lower_body_loaded`", ""]
    for row in static["bodyweight_rows_classed_lower_body_loaded"]:
        lines.append(f"- {row['name']} ({'/'.join(row['phases'])}, {row['movement']})")
    lines += ["", "## Rows reclassified by movement normalization", "",
              "The planner replaces each row's authored `movement` with a detected canonical",
              "pattern when the bank loads; these rows classify differently under the two.", "",
              "| Row | Movement (bank → normalized) | Class | Gains | Loses |", "|---|---|---|---|---|"]
    for row in static["movement_normalization_classification_flips"]:
        quality = row["quality_class"][0] if row["quality_class"][0] == row["quality_class"][1] else " → ".join(row["quality_class"])
        lines.append(
            f"| {row['name']} | {' → '.join(row['movement'])} | {quality} | "
            f"{', '.join(row['categories_gained']) or '—'} | {', '.join(row['categories_lost']) or '—'} |"
        )
    if selection:
        lines += ["", "## Generated camps", "",
                  "| Cell | Camps | Distinct selected | Picked in ≥80% | Blocks missing a category |",
                  "|---|---|---|---|---|"]
        for key, entry in selection.items():
            lines.append(
                f"| {key} | {entry['camps']} | {entry['distinct_selected']} | "
                f"{len(entry['selected_in_80pct_or_more'])} | {entry['blocks_missing_required_category'] or '—'} |"
            )
        lines.append("")
        for key, entry in selection.items():
            lines.append(f"- **{key}** top: " + ", ".join(f"{n} {s}%" for n, s in entry["top_share"]))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selection", action="store_true", help="also generate representative camps (slow)")
    parser.add_argument("--step", type=int, default=5, help="sample every Nth camp of the grid (default 5)")
    parser.add_argument("--json", type=Path, help="write the full report as JSON to this path")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)

    static = static_audit()
    selection = selection_audit(args.step) if args.selection else None
    if args.json:
        args.json.write_text(json.dumps({"static": static, "selection": selection}, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.write(_markdown(static, selection))


if __name__ == "__main__":
    main()
