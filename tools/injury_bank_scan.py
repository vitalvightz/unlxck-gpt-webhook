import argparse
from collections import defaultdict
from pathlib import Path
import sys
from typing import Iterable

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_exclusion_rules import INJURY_RULES
from fightcamp.injury_filtering import collect_banks
from fightcamp.injury_guard import injury_decision


def _parse_regions(value: str | None) -> list[str]:
    if not value:
        return sorted(INJURY_RULES.keys())
    return [region.strip() for region in value.split(",") if region.strip()]


def _parse_severities(value: str | None) -> list[str]:
    if not value:
        return ["low", "moderate", "high"]
    return [severity.strip() for severity in value.split(",") if severity.strip()]


def _format_name(item: dict) -> str:
    return str(item.get("name") or item.get("drill") or item.get("title") or "<unnamed>")


def _iter_injury_inputs(regions: Iterable[str], severities: Iterable[str]) -> list[dict]:
    return [{"region": region, "severity": severity} for region in regions for severity in severities]


def scan_banks(
    *,
    regions: list[str],
    severities: list[str],
    phase: str,
    fatigue: str,
    limit: int,
    show_exclusions: bool,
) -> int:
    banks = collect_banks()
    injury_inputs = _iter_injury_inputs(regions, severities)
    exit_code = 0

    for injury_input in injury_inputs:
        region = injury_input["region"]
        severity = injury_input["severity"]
        print(f"\n=== Injury scan: region={region} severity={severity} phase={phase} fatigue={fatigue} ===")
        for bank_name, items in banks.items():
            counts = defaultdict(int)
            examples: list[str] = []
            for item in items:
                exercise = dict(item)
                decision = injury_decision(exercise, [injury_input], phase, fatigue)
                counts[decision.action] += 1
                if show_exclusions and decision.action in {"exclude", "flag"} and len(examples) < limit:
                    matched_tags = ", ".join(decision.matched_tags or [])
                    reason = decision.reason if isinstance(decision.reason, dict) else {}
                    patterns = set()
                    for detail in reason.get("matches", []) or []:
                        if isinstance(detail, dict):
                            patterns.update(detail.get("patterns", []) or [])
                    pattern_text = ", ".join(sorted(patterns))
                    examples.append(
                        f"- {decision.action}: {_format_name(exercise)} | tags=[{matched_tags}] | patterns=[{pattern_text}]"
                    )
            total = sum(counts.values())
            print(
                f"{bank_name}: total={total} allow={counts['allow']} modify={counts['modify']} "
                f"flag={counts['flag']} exclude={counts['exclude']}"
            )
            if show_exclusions and examples:
                print("\n".join(examples))
        if region not in INJURY_RULES:
            print(f"WARNING: Unknown injury region '{region}'")
            exit_code = 1
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan all exercise/conditioning banks for injury filtering coverage.")
    parser.add_argument(
        "--regions",
        help="Comma-separated injury regions to scan (default: all).",
    )
    parser.add_argument(
        "--severities",
        help="Comma-separated severities to scan (default: low,moderate,high).",
    )
    parser.add_argument("--phase", default="GPP", help="Training phase (default: GPP).")
    parser.add_argument("--fatigue", default="low", help="Fatigue level (default: low).")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit for listed examples when --show-exclusions is set.",
    )
    parser.add_argument(
        "--show-exclusions",
        action="store_true",
        help="Print example excluded/flagged items per bank.",
    )
    args = parser.parse_args()

    regions = _parse_regions(args.regions)
    severities = _parse_severities(args.severities)
    return scan_banks(
        regions=regions,
        severities=severities,
        phase=args.phase,
        fatigue=args.fatigue,
        limit=args.limit,
        show_exclusions=args.show_exclusions,
    )


if __name__ == "__main__":
    raise SystemExit(main())
