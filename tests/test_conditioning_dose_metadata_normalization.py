"""Regression tests for the conditioning dose-metadata normalisation.

These guard the corrections applied to ``data/conditioning_bank.json`` and
``data/style_conditioning_bank.json``.

The dose contract under test:

    work_sec       seconds per work interval
    rest_sec       seconds of genuine recovery between intervals
    rounds         number of work intervals
    total_minutes  full elapsed block time = (rounds*work_sec + (rounds-1)*rest_sec)/60

Timed interval drills whose written prescription states an explicit discrete rest
must carry ``rest_sec`` and elapsed-convention ``total_minutes``. Rep-count /
distance ``work_sec`` entries cannot be resolved from the prescription alone and
must be left untouched. The classifier below mirrors that rule so the tests can
assert the contract straight from the bank data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

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


def _duration(entry: dict) -> str:
    return str(entry.get("duration", "")).lower().replace("–", "-").replace("—", "-")


def _parse_work(duration: str):
    """Return ``(work_sec, rounds)`` when the work portion is genuine time."""
    match = re.match(r"\s*(\d+)\s*x\s*(\d+)\s*(?:s|sec|secs|seconds)\b", duration)
    if match:
        return int(match.group(2)), int(match.group(1))
    match = re.match(r"\s*(\d+)\s*x\s*(\d+)\s*(?:min|minute|minutes)\b", duration)
    if match:
        return int(match.group(2)) * 60, int(match.group(1))
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
    match = re.search(r"(\d+):1\s*(?:rest|off)", duration)
    if match and work_sec:
        return int(match.group(1)) * work_sec
    match = re.search(r"1:(\d+)\s*(?:rest|off)", duration)
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
    """Return ``(action, reason)`` for one bank entry.

    action: ``fix`` (auto-correctable but not yet correct), ``ambiguous`` (manual
    review), ``ok`` (clean timed interval already consistent), ``skip`` (not a
    timed multi-round interval).
    """
    duration = _duration(entry)
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
            if (
                work == work_sec
                and rest == rest_sec
                and total is not None
                and abs(total - target) <= 0.01
            ):
                return "ok", None
            return "fix", None
        if _ACTIVE_RECOVERY.search(duration):
            return "ambiguous", "active-recovery interval; between-interval bout is work"
        return "ambiguous", "no explicit discrete rest in prescription"

    reasons = []
    if reps_or_distance and (has_rest_token or rest is not None):
        reasons.append("work portion encodes reps/distance")
    if one_round and rounds > 1:
        reasons.append("total_minutes counts a single round")
    if has_rest_token and rest is None and not reps_or_distance:
        reasons.append("prescription states a rest but rest_sec is unset")
    if reasons:
        return "ambiguous", "; ".join(dict.fromkeys(reasons))
    return "skip", None


def _load(name: str) -> dict:
    return {
        entry["name"]: entry
        for entry in json.loads(Path(f"data/{name}").read_text(encoding="utf-8"))
    }


_BANK = _load("conditioning_bank.json")
_STYLE_BANK = _load("style_conditioning_bank.json")

_CLEAN = [e for e in _BANK.values() if classify(e)[0] == "ok"]
_AMBIGUOUS = {e["name"]: classify(e)[1] for e in _BANK.values() if classify(e)[0] == "ambiguous"}
_STYLE_CLEAN = [e for e in _STYLE_BANK.values() if classify(e)[0] == "ok"]


def _elapsed(work_sec: float, rest_sec: float, rounds: float) -> float:
    return round((work_sec * rounds + (rounds - 1) * rest_sec) / 60, 2)


# --- Canonical example from the linked plan --------------------------------


def test_plyo_step_up_intervals_encodes_work_rest_and_elapsed_block():
    drill = _BANK["Plyo Step-Up Intervals"]
    # 6 x 30s work with 90s rest -> three minutes is WORK time, not elapsed.
    assert drill["work_sec"] == 30
    assert drill["rest_sec"] == 90
    assert drill["rounds"] == 6
    assert drill["total_minutes"] == 10.5
    assert drill["total_minutes"] == _elapsed(30, 90, 6)


def test_plyo_step_up_intervals_preserves_training_purpose():
    # The correction must not redose or reclassify the drill.
    drill = _BANK["Plyo Step-Up Intervals"]
    assert drill["system"] == "glycolytic"
    assert drill["intensity"] == "high"
    assert drill["lactate_load"] == "high"
    assert drill["rpe"] == 8
    assert drill["duration"] == "6x30s on/1:30 off"  # readable prescription preserved


# --- Contract holds for every clean timed-interval entry -------------------


def test_every_clean_timed_interval_satisfies_the_elapsed_contract():
    assert len(_CLEAN) >= 50
    for entry in _CLEAN:
        assert entry["total_minutes"] == elapsed_minutes(
            entry["work_sec"], entry["rest_sec"], entry["rounds"]
        )


@pytest.mark.parametrize("entry", _CLEAN, ids=[e["name"] for e in _CLEAN])
def test_clean_timed_interval_units_are_valid(entry):
    assert isinstance(entry["rest_sec"], int)
    assert entry["rest_sec"] > 0
    assert isinstance(entry["rounds"], int)
    assert entry["rounds"] >= 2
    work_only = (entry["work_sec"] * entry["rounds"]) / 60
    assert entry["total_minutes"] > work_only


def test_no_timed_interval_leaves_a_stated_rest_unencoded():
    # No auto-correctable entry should remain in either bank.
    remaining = [
        e["name"]
        for bank in (_BANK, _STYLE_BANK)
        for e in bank.values()
        if classify(e)[0] == "fix"
    ]
    assert remaining == []


# --- Purpose retained: sample across systems -------------------------------


def test_corrected_entries_retain_energy_system_labels():
    assert _BANK["Hill Sprint Repeats"]["system"] == "glycolytic"
    assert _BANK["Pad Round Triples"]["system"] == "glycolytic"
    assert _BANK["Sled Push Aerobic Intervals"]["system"] == "aerobic"


# --- Ambiguous entries must be left untouched (no auto-redose) --------------


def test_rep_encoded_plyo_entry_is_reported_not_modified():
    # "Depth Jump to Sprint" prescribes 5x3 reps: work_sec=3 is a rep count, not
    # seconds. The pass must leave it exactly as-is.
    drill = _BANK["Depth Jump to Sprint"]
    assert drill["work_sec"] == 3
    assert drill["rest_sec"] == 120
    assert drill["total_minutes"] == 0.25
    assert "Depth Jump to Sprint" in _AMBIGUOUS
    assert "reps/distance" in _AMBIGUOUS["Depth Jump to Sprint"]


def test_active_recovery_interval_is_reported_not_modified():
    # "Echo Bike Tempo Intervals" (4x3min hard, 2min easy) has no discrete rest.
    drill = _BANK["Echo Bike Tempo Intervals"]
    assert "rest_sec" not in drill or drill["rest_sec"] is None
    assert drill["total_minutes"] == 12
    assert "Echo Bike Tempo Intervals" in _AMBIGUOUS


def test_ambiguous_entries_are_never_clean_timed_intervals():
    clean_names = {entry["name"] for entry in _CLEAN}
    assert clean_names.isdisjoint(_AMBIGUOUS)


# --- style_conditioning_bank.json satisfies the same contract --------------


def test_style_bank_clean_timed_intervals_satisfy_the_elapsed_contract():
    assert len(_STYLE_CLEAN) >= 150
    for entry in _STYLE_CLEAN:
        assert entry["total_minutes"] == elapsed_minutes(
            entry["work_sec"], entry["rest_sec"], entry["rounds"]
        )


def test_style_bank_word_order_prescription_is_corrected():
    # "5sec work, 60sec rest x 8 rounds" -> elapsed (40 + 7*60)/60 = 7.67, not 7.
    drill = _STYLE_BANK["Entry-Exit Burst"]
    assert drill["work_sec"] == 5
    assert drill["rest_sec"] == 60
    assert drill["rounds"] == 8
    assert drill["total_minutes"] == 7.67
    assert drill["total_minutes"] == elapsed_minutes(5, 60, 8)


# --- Prior corrections remain intact ---------------------------------------


def test_previous_dose_corrections_are_preserved():
    treadmill = _BANK["Treadmill Hill Sprints"]
    assert treadmill["total_minutes"] == _elapsed(
        treadmill["work_sec"], treadmill["rest_sec"], treadmill["rounds"]
    )
