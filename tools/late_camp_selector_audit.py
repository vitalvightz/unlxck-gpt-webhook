from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.conditioning import generate_conditioning_block  # noqa: E402
from fightcamp.late_selector_windows import LATE_SELECTOR_AUDIT_WINDOWS  # noqa: E402
from fightcamp.strength import generate_strength_block  # noqa: E402


WINDOW_DAY_MAP = {
    "control_d28": 28,
    "d21_to_d14": 21,
    "d13_to_d8": 13,
    "d7": 7,
    "d6_to_d5": 6,
    "d4_to_d2": 4,
    "d1": 1,
}

AUDIT_FLAGS = {
    "phase": "TAPER",
    "fatigue": "low",
    "fight_format": "boxing",
    "sport": "boxing",
    "style_tactical": ["counter_striker"],
    "style_technical": ["boxing"],
    "equipment": [
        "bodyweight",
        "bands",
        "medicine_ball",
        "heavy_bag",
        "pads",
        "assault_bike",
        "stationary_bike",
        "battle_ropes",
    ],
    "key_goals": ["conditioning", "power"],
    "weaknesses": [],
    "injuries": [],
    "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "training_frequency": 5,
    "days_available": 5,
    "random_seed": 7,
}

LATE_STRENGTH_AUDIT_OVERRIDES = {
    "style_tactical": ["counter_striker"],
    "style_technical": ["boxing"],
    "equipment": [
        "bodyweight",
        "bands",
        "medicine_ball",
        "heavy_bag",
        "pullup_bar",
        "towel",
        "trap_bar",
        "pins",
    ],
    "key_goals": ["power", "maximal_strength_maintenance", "skill_refinement"],
    "weaknesses": ["posterior_chain", "coordination", "balance"],
    "training_days": ["monday", "tuesday", "thursday", "saturday"],
    "training_frequency": 4,
    "days_available": 4,
}


def _reason_codes(entry: dict) -> list[str]:
    reasons = entry.get("reasons") or {}
    codes = reasons.get("reason_codes") or []
    return [str(code) for code in codes if str(code).strip()]


def _winner_summary(entry: dict) -> dict:
    reasons = entry.get("reasons") or {}
    return {
        "name": entry.get("name"),
        "score": round(float(reasons.get("final_score", 0.0) or 0.0), 4),
        "reason_codes": _reason_codes(entry),
    }


def _blocked_summary(entries: list[dict]) -> list[dict]:
    return [
        {
            "name": entry.get("name"),
            "score": round(float(entry.get("score", 0.0) or 0.0), 4),
            "reason_codes": [str(code) for code in entry.get("reason_codes", []) if str(code).strip()],
        }
        for entry in entries
    ]


def _unique_names(entries: list[dict]) -> list[str | None]:
    names: list[str | None] = []
    seen: set[str | None] = set()
    for entry in entries:
        name = entry.get("name")
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _combined_ambiguous_gaps(
    strength_diag: dict,
    conditioning_diag: dict,
) -> list[dict]:
    combined = []
    for selector, diag in (("strength", strength_diag), ("conditioning", conditioning_diag)):
        for entry in diag.get("ambiguous_tag_gaps", []) or []:
            combined.append(
                {
                    "selector": selector,
                    "name": entry.get("name"),
                    "issue": entry.get("issue"),
                    "signals": list(entry.get("signals", []) or []),
                }
            )
    combined.sort(key=lambda entry: (entry.get("selector", ""), entry.get("name", "")))
    return combined


def build_snapshot() -> dict:
    snapshot: dict[str, dict] = {}
    for window in LATE_SELECTOR_AUDIT_WINDOWS:
        days_until_fight = WINDOW_DAY_MAP[window]
        conditioning_flags = {**AUDIT_FLAGS, "days_until_fight": days_until_fight}
        strength_flags = dict(conditioning_flags)
        if window != "control_d28":
            strength_flags.update(LATE_STRENGTH_AUDIT_OVERRIDES)
            strength_flags["phase"] = "SPP" if days_until_fight >= 8 else "TAPER"

        strength_block = generate_strength_block(flags=strength_flags)
        (
            _conditioning_text,
            _conditioning_names,
            conditioning_why_log,
            _grouped_drills,
            _missing_systems,
            conditioning_reservoir,
        ) = generate_conditioning_block(conditioning_flags)

        strength_diag = (strength_block.get("candidate_reservoir") or {}).get("__late_window__", {})
        conditioning_diag = conditioning_reservoir.get("__late_window__", {})

        snapshot[window] = {
            "strength": {
                "winners": [_winner_summary(entry) for entry in strength_block.get("why_log", [])],
                "blocked": _blocked_summary(strength_diag.get("blocked", []) or []),
            },
            "conditioning": {
                "winners": [_winner_summary(entry) for entry in conditioning_why_log],
                "blocked": _blocked_summary(conditioning_diag.get("blocked", []) or []),
            },
            "ambiguous_tag_gaps": _combined_ambiguous_gaps(strength_diag, conditioning_diag),
        }
    return snapshot


def build_diff(before: dict, after: dict) -> dict:
    diff: dict[str, dict] = {}
    for window in LATE_SELECTOR_AUDIT_WINDOWS:
        before_window = before.get(window, {})
        after_window = after.get(window, {})
        diff[window] = {}
        for selector in ("strength", "conditioning"):
            before_selector = before_window.get(selector, {})
            after_selector = after_window.get(selector, {})
            before_winners = _unique_names(before_selector.get("winners", []))
            after_winners = _unique_names(after_selector.get("winners", []))
            before_blocked = _unique_names(before_selector.get("blocked", []))
            after_blocked = _unique_names(after_selector.get("blocked", []))
            diff[window][selector] = {
                "before_winners": before_winners,
                "after_winners": after_winners,
                "added_winners": [name for name in after_winners if name not in before_winners],
                "removed_winners": [name for name in before_winners if name not in after_winners],
                "newly_blocked": [name for name in after_blocked if name not in before_blocked],
                "no_longer_blocked": [name for name in before_blocked if name not in after_blocked],
            }
        before_gaps = before_window.get("ambiguous_tag_gaps", [])
        after_gaps = after_window.get("ambiguous_tag_gaps", [])
        before_gap_keys = [(entry.get("selector"), entry.get("name"), entry.get("issue")) for entry in before_gaps]
        after_gap_keys = [(entry.get("selector"), entry.get("name"), entry.get("issue")) for entry in after_gaps]
        diff[window]["ambiguous_tag_gaps_added"] = [
            entry for entry in after_gaps
            if (entry.get("selector"), entry.get("name"), entry.get("issue")) not in before_gap_keys
        ]
        diff[window]["ambiguous_tag_gaps_removed"] = [
            entry for entry in before_gaps
            if (entry.get("selector"), entry.get("name"), entry.get("issue")) not in after_gap_keys
        ]
    return diff


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build late-camp selector audit snapshots.")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the live snapshot JSON.")
    parser.add_argument("--before", type=Path, help="Optional baseline snapshot for diff generation.")
    parser.add_argument("--diff-output", type=Path, help="Optional diff output path.")
    args = parser.parse_args()

    snapshot = build_snapshot()
    _write_json(args.output, snapshot)

    if args.before and args.diff_output:
        before = json.loads(args.before.read_text(encoding="utf-8"))
        diff = build_diff(before, snapshot)
        _write_json(args.diff_output, diff)


if __name__ == "__main__":
    main()
