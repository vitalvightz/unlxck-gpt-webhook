"""Audit and normalise conditioning dose metadata against the written prescription.

Dose contract (single source of truth for the timed-interval shape):

    work_sec       seconds per work interval
    rest_sec       seconds of genuine recovery between intervals
    rounds         number of work intervals
    total_minutes  full elapsed block time = (rounds*work_sec + (rounds-1)*rest_sec)/60

Reps and distance are deliberately kept out of the seconds fields, and the
readable ``duration`` string is always preserved verbatim.

The auditor only auto-corrects entries whose ``duration`` unambiguously encodes
TIME-based work (seconds or minutes -- never reps, never distance) together with
an explicit DISCRETE rest (``rest`` / ``recovery`` / ``off``). For those it fills
a missing ``rest_sec`` from the prescription and rewrites ``total_minutes`` to the
full elapsed block time. Every other multi-round entry with a dose discrepancy is
reported for manual review and left untouched -- in particular the rep-count and
distance ``work_sec`` overloads catalogued in ``reports/conditioning_bank_audit.md``.

It normalises both ``data/conditioning_bank.json`` and
``data/style_conditioning_bank.json``. Because several style-bank slices are
protected by byte-for-byte governance snapshots (see ``tests/test_clinch_fighter_*``
and ``tests/test_distance_striker_*``), applying this pass to the style bank also
requires re-freezing those snapshot hashes for the deliberate metadata change.

Usage::

    python tools/audit_conditioning_dose_metadata.py            # dry-run summary
    python tools/audit_conditioning_dose_metadata.py --apply    # write both banks
    python tools/audit_conditioning_dose_metadata.py --json     # full before/after JSON
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"

BANKS = [
    DATA_DIR / "conditioning_bank.json",
    DATA_DIR / "style_conditioning_bank.json",
]

CONTRACT = {
    "work_sec": "seconds per work interval",
    "rest_sec": "seconds of genuine recovery between intervals",
    "rounds": "number of work intervals",
    "total_minutes": (
        "full elapsed block time = (rounds*work_sec + (rounds-1)*rest_sec)/60"
    ),
    "notes": (
        "reps and distance are kept separate from seconds; the readable duration "
        "string is preserved verbatim"
    ),
}

# Canonical dose-field order used throughout the banks. A newly added key is
# inserted immediately after its predecessor so ordering stays consistent.
_INSERT_AFTER = {"rest_sec": "work_sec", "total_minutes": "rounds"}

_DISTANCE = re.compile(r"\b\d+\s*(?:yd|yds|yard|yards|m|meter|meters|ft|feet)\b")
_REPS = re.compile(r"\breps?\b|/side|per side")
_REST_TOKEN = re.compile(r"\b(?:rest|off|recovery|reset)\b")
_ACTIVE_RECOVERY = re.compile(r"\beasy\b|\btempo\b|\bgame-pace\b|\bpace\b|walk back")


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _norm_duration(entry: dict) -> str:
    return str(entry.get("duration", "")).lower().replace("–", "-").replace("—", "-")


def _parse_work(duration: str):
    """Return ``(work_sec, rounds)`` when the work portion is genuine time."""
    # "R x Ns" / "R x Nsec" — rounds first, e.g. "6x30s on/1:30 off".
    match = re.match(r"\s*(\d+)\s*x\s*(\d+)\s*(?:s|sec|secs|seconds)\b", duration)
    if match:
        return int(match.group(2)), int(match.group(1))
    # "R x Nmin" — rounds first, minute work, e.g. "8x3min ..., 1min rest".
    match = re.match(r"\s*(\d+)\s*x\s*(\d+)\s*(?:min|minute|minutes)\b", duration)
    if match:
        return int(match.group(2)) * 60, int(match.group(1))
    # "Nsec work, ... x R rounds" — work first, rounds last, e.g.
    # "5sec work, 60sec rest x 8 rounds".
    match = re.match(r"\s*(\d+)\s*(?:s|sec|secs|seconds)\s*work\b", duration)
    if match:
        rounds = re.search(r"x\s*(\d+)\s*rounds?\b", duration)
        if rounds:
            return int(match.group(1)), int(rounds.group(1))
    return None


def _parse_rest(duration: str, work_sec: int):
    """Return an explicit DISCRETE rest in seconds, or ``None``."""
    match = re.search(r"(\d+):(\d{2})\s*(?:off|rest)", duration)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = re.search(r"(\d+):1\s*(?:rest|off)", duration)  # N:1 work:rest ratio
    if match and work_sec:
        return int(match.group(1)) * work_sec
    match = re.search(r"1:(\d+)\s*(?:rest|off)", duration)  # 1:N work:rest ratio
    if match and work_sec:
        return int(match.group(1)) * work_sec
    match = re.search(r"(\d+)\s*(?:s|sec|secs|seconds)\s*(?:rest|off|recovery)\b", duration)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*(?:min|minute|minutes)\s*(?:rest|recovery)\b", duration)
    if match:
        return int(match.group(1)) * 60
    return None


def elapsed_minutes(work_sec: float, rest_sec: float, rounds: float) -> float:
    """Full elapsed block time for a timed interval drill, rounded to 2 dp."""
    return round((work_sec * rounds + (rounds - 1) * rest_sec) / 60, 2)


def classify(entry: dict):
    """Return ``(action, payload)`` for one bank entry.

    action is one of: ``fix`` (auto-correctable), ``ambiguous`` (manual review),
    ``ok`` (already consistent), ``skip`` (not a timed multi-round interval).
    """
    duration = _norm_duration(entry)
    work = _num(entry.get("work_sec"))
    rest = _num(entry.get("rest_sec"))
    rounds = _num(entry.get("rounds"))
    total = _num(entry.get("total_minutes"))

    if rounds is None or rounds <= 1:
        return "skip", None

    parsed_work = _parse_work(duration)
    reps_or_distance = bool(_DISTANCE.search(duration) or _REPS.search(duration))
    has_rest_token = bool(_REST_TOKEN.search(duration))
    one_round = work is not None and total is not None and abs(total - work / 60) < 0.02

    if parsed_work is not None and parsed_work[1] == rounds and not reps_or_distance:
        work_sec, round_count = parsed_work
        rest_sec = _parse_rest(duration, work_sec)
        if rest_sec is not None:
            target = elapsed_minutes(work_sec, rest_sec, round_count)
            changes = {}
            if work != work_sec:
                changes["work_sec"] = (entry.get("work_sec"), work_sec)
            if rest != rest_sec:
                changes["rest_sec"] = (entry.get("rest_sec"), rest_sec)
            if total is None or abs(total - target) > 0.01:
                changes["total_minutes"] = (entry.get("total_minutes"), target)
            if not changes:
                return "ok", None
            return "fix", {"changes": changes}
        if _ACTIVE_RECOVERY.search(duration):
            return "ambiguous", (
                "active-recovery interval (easy/tempo/pace); the between-interval "
                "bout is work, not genuine rest"
            )
        return "ambiguous", (
            "no explicit discrete rest in prescription; elapsed block time is "
            "indeterminate"
        )

    reasons = []
    if reps_or_distance and (has_rest_token or rest is not None):
        reasons.append(
            "work portion encodes reps/distance, so work_sec/total_minutes are not "
            "seconds-based; needs a manual dose audit"
        )
    if one_round and rounds > 1:
        reasons.append("total_minutes counts a single round rather than the full block")
    if has_rest_token and rest is None and not reps_or_distance:
        reasons.append("prescription states a rest but rest_sec is unset")
    if reasons:
        return "ambiguous", "; ".join(dict.fromkeys(reasons))
    return "skip", None


def _apply_change(entry: dict, changes: dict) -> None:
    """Apply field changes in place, inserting new keys in canonical order."""
    new_keys = {}
    for key, (_before, after) in changes.items():
        if key in entry:
            entry[key] = after
        else:
            new_keys[key] = after
    if not new_keys:
        return
    rebuilt = {}
    for key, value in list(entry.items()):
        rebuilt[key] = value
        for new_key, new_val in new_keys.items():
            if _INSERT_AFTER.get(new_key) == key:
                rebuilt[new_key] = new_val
    for new_key, new_val in new_keys.items():  # predecessor absent -> append
        if new_key not in rebuilt:
            rebuilt[new_key] = new_val
    entry.clear()
    entry.update(rebuilt)


def audit_bank(path: Path, *, apply: bool):
    data = json.loads(path.read_text(encoding="utf-8"))
    fixed, ambiguous, already_ok = [], [], 0
    for entry in data:
        action, payload = classify(entry)
        if action == "fix":
            row = {"name": entry["name"], "duration": entry.get("duration"),
                   "before": {}, "after": {}}
            for key, (before, after) in payload["changes"].items():
                row["before"][key] = before
                row["after"][key] = after
            if apply:
                _apply_change(entry, payload["changes"])
            fixed.append(row)
        elif action == "ambiguous":
            ambiguous.append({
                "name": entry["name"],
                "duration": entry.get("duration"),
                "reason": payload,
                "current": {k: entry.get(k) for k in
                            ("work_sec", "rest_sec", "rounds", "total_minutes")},
            })
        elif action == "ok":
            already_ok += 1
    if apply:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "fixed_count": len(fixed),
        "ambiguous_count": len(ambiguous),
        "already_consistent": already_ok,
        "fixed": fixed,
        "ambiguous": ambiguous,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="write corrections to the conditioning banks")
    parser.add_argument("--json", action="store_true",
                        help="print the full before/after audit as JSON")
    args = parser.parse_args(argv)

    report = {"contract": CONTRACT, "banks": {}}
    for path in BANKS:
        summary = audit_bank(path, apply=args.apply)
        report["banks"][path.name] = summary
        print(f"{path.name}: fixed={summary['fixed_count']} "
              f"ambiguous={summary['ambiguous_count']} "
              f"already_ok={summary['already_consistent']} "
              f"[{'applied' if args.apply else 'dry-run'}]")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
