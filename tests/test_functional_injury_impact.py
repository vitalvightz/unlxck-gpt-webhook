"""The athlete's three injury-impact choices give one decision everywhere.

* not_limiting: normal training once triage has cleared it (awareness only).
* limiting: exercise-specific adaptation from movement demands and severity.
* cant_train: normal training restricted, rehab/recovery still permitted.

Medical evidence (red flags, serious-injury triage, holds, wounds, "worse"
reports) is independent and always wins over the athlete's impact choice.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from api.contracts.injury_policy import resolve_injury_policy
from api.contracts.readiness_message import (
    ReadinessCheckin, ReadinessContext, build_readiness_adjustment, restricts_training,
)
from fightcamp.conditioning import get_conditioning_bank
from fightcamp.injury_awareness import (
    injury_stop_phrase, is_awareness_only, is_functional_cant_train, reported_training_impact,
)
from fightcamp.injury_guard import injury_decision
from fightcamp.input_parsing import _build_guided_injury, _parse_guided_injury
from fightcamp.rehab_clinical import load_clinical_policies
from fightcamp.rehab_protocols import get_rehab_bank
from fightcamp.strength import get_exercise_bank

SEVERITY = {"not_limiting": "mild", "limiting": "moderate", "cant_train": "severe"}  # web flagSeverity


def _flag(impact=None, *, severity=None, area="Left knee", text="left knee pain", **extra):
    marker = f" [training_impact:{impact}]" if impact else ""
    return {"id": "f1", "status": "open", "body_area": area, "label": area.lower(),
            "description": text + marker, "severity": severity or SEVERITY.get(impact, "moderate"),
            "latest_reported_status": "ongoing", **extra}


# --- Impact provenance --------------------------------------------------------

@pytest.mark.parametrize("impact", ["not_limiting", "limiting", "cant_train"])
def test_impact_is_read_from_the_stored_marker_and_the_parsed_field(impact):
    assert reported_training_impact(_flag(impact)) == impact
    assert reported_training_impact({"training_impact": impact}) == impact


def test_missing_or_legacy_impact_is_unknown_and_stays_restrictive():
    legacy = _flag(None, severity="mild")
    assert reported_training_impact(legacy) == ""
    assert not is_awareness_only(legacy) and restricts_training(legacy)
    assert not is_functional_cant_train(_flag(None, severity="severe"))


# --- not_limiting -------------------------------------------------------------

def test_not_limiting_is_awareness_only():
    assert is_awareness_only(_flag("not_limiting"))
    assert not restricts_training(_flag("not_limiting"))


@pytest.mark.parametrize("override", [
    {"latest_reported_status": "worse"},
    {"medical_hold": True},
    {"restriction_hold": True},
    {"rehab_medical_gate": True},
    {"consequence": "neuro"},
    {"severity": "severe"},
    {"text": "left knee numbness and tingling down the leg"},
    {"injury_type": "cut", "area": "Left shin", "text": "cut on shin"},
])
def test_medical_evidence_overrides_a_not_limiting_choice(override):
    text = override.pop("text", "left knee pain")
    area = override.pop("area", "Left knee")
    flag = _flag("not_limiting", text=text, area=area, **override)
    assert restricts_training(flag)


def _readiness(injuries, title="Hard sparring"):
    session = {"title": title, "session_type": "conditioning", "effective_load": "hard"}
    return build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session,
                         open_injuries=tuple(i for i in injuries if restricts_training(i))),
    )


@pytest.mark.parametrize("title", ["Hard sparring", "Heavy lower body strength", "Easy mobility"])
def test_today_treats_not_limiting_like_no_injury(title):
    clear = _readiness([], title)
    noted = _readiness([_flag("not_limiting", consequence="load_sensitive")], title)
    assert (noted.decision, noted.title, noted.reason) == (clear.decision, clear.title, clear.reason)


def test_today_still_restricts_the_same_injury_when_limiting():
    clear = _readiness([])
    limited = _readiness([_flag("limiting", consequence="structural")])
    assert limited.decision != clear.decision or limited.reason != clear.reason


# --- cant_train ---------------------------------------------------------------

def test_cant_train_stops_normal_training_without_a_severe_medical_label():
    adjustment = _readiness([_flag("cant_train", consequence="load_sensitive")])
    assert adjustment.decision == "pull_back"
    assert "Can't train normally: left knee" in adjustment.reason
    assert "severe" not in adjustment.reason.lower()


def test_genuine_severe_injury_keeps_its_severe_label():
    adjustment = _readiness([_flag(None, severity="severe", consequence="load_sensitive")])
    assert adjustment.decision == "pull_back"
    assert "Active severe injury" in adjustment.reason
    assert injury_stop_phrase(_flag("cant_train", medical_hold=True), "x") == "Active severe injury: x"


def _ankle(impact, **extra):
    return {"id": "a1", "status": "open", "body_area": "Right ankle", "label": "right ankle sprain",
            "description": f"right ankle sprain [training_impact:{impact}]" if impact else "right ankle sprain",
            "severity": "severe", "rehab_type": "sprain", "injury_type": "sprain",
            "latest_reported_status": "ongoing", **extra}


def test_cant_train_keeps_clinically_permitted_rehab_instead_of_a_review_hold():
    policies, bank = load_clinical_policies(), get_rehab_bank()
    functional = resolve_injury_policy(_ankle("cant_train"), policies=policies, bank=bank)
    assert functional["outcome"] != "medical_review"


@pytest.mark.parametrize("injury", [
    _ankle(None),  # legacy severe without provenance stays conservative
    _ankle("cant_train", rehab_medical_gate=True),
    _ankle("cant_train", description="right ankle sprain, suspected fracture [training_impact:cant_train]"),
])
def test_medical_severity_still_holds_for_review(injury):
    decision = resolve_injury_policy(injury, policies=load_clinical_policies(), bank=get_rehab_bank())
    assert decision["outcome"] == "medical_review"


# --- Onboarding / generation --------------------------------------------------

@pytest.mark.parametrize("impact,dropped", [("not_limiting", True), ("limiting", False), ("cant_train", False)])
def test_onboarding_impact_reaches_generation(impact, dropped):
    guided = _build_guided_injury({"area": "Left knee", "severity": {"not_limiting": "low", "limiting": "moderate",
                                                                     "cant_train": "high"}[impact],
                                   "trend": "stable", "injury_type": "pain",
                                   "notes": f"sore [training_impact:{impact}]"})
    injuries, _ = _parse_guided_injury(guided)
    marked = injuries[0].get("training_impact") == "not_limiting"
    assert marked is dropped  # plan_pipeline_runtime removes only these after triage


# --- #2958 metadata: absolute prohibitions vs conditional warnings -------------

def _bank():
    return {row["name"]: row for row in get_exercise_bank() + get_conditioning_bank()}


def _actions(name, region):
    row = _bank()[name]
    return {severity: injury_decision(row, [{"region": region, "severity": severity, "original_phrase": region}],
                                      "SPP", "low").action for severity in ("low", "moderate", "high")}


@pytest.mark.parametrize("name,region", [
    ("Towel/Gi Row Isometric Hold", "elbow"),  # "skip if elbow tendons are already flared..."
    ("Adductor Squeeze Isometric", "groin"),  # "skip if ... increases groin pain beyond..."
])
def test_conditional_contraindication_adapts_with_severity_instead_of_excluding(name, region):
    assert _actions(name, region) == {"low": "allow", "moderate": "modify", "high": "exclude"}


@pytest.mark.parametrize("name,region", [
    ("Jump Rope (Recovery Pace)", "ankle"),  # authored avoid_if region list
    ("Split-Step Ankle Snap Pogo", "foot"),  # avoid_if
    ("Landmine Split-Stance Punch Press", "shoulder"),  # "avoid if shoulder symptoms are active"
    ("Heavy-Bag Single-Shot Clusters", "wrist"),  # "skip if ... symptoms are active"
])
def test_absolute_prohibitions_still_exclude_at_every_severity(name, region):
    assert set(_actions(name, region).values()) == {"exclude"}


# --- Editor: same rules, plus the authored fight cutoff ------------------------

class _Store:
    def __init__(self, flags):
        self.flags = flags

    def list_injury_flags(self, athlete_id, statuses=(), limit=500):
        return [dict(f) for f in self.flags]

    def __getattr__(self, name):  # every other read: nothing recorded
        return lambda *a, **k: []


def _safety(flags, *, fight_date="2026-12-01", day=date(2026, 11, 10)):
    from api.services.exercise_customisation import SafetyContext

    session = {"title": "Conditioning", "blocks": []}
    occurrence = SimpleNamespace(plan_row={"id": "p1", "fight_date": fight_date}, phase="SPP", date=day,
                                 session=session, day={}, week={})
    return SafetyContext(_Store(flags), athlete_id="a1", occurrence=occurrence, equipment=["kettlebell"])


def test_editor_ignores_not_limiting_and_keeps_limiting_restrictions():
    assert not _safety([_flag("not_limiting", area="Left shoulder", text="shoulder")]).has_injuries
    limited = _safety([_flag("limiting", area="Left shoulder", text="shoulder")])
    assert limited.has_injuries and limited.contraindicated(_bank()["Landmine Split-Stance Punch Press"])


@pytest.mark.parametrize("days_out,held", [(22, False), (21, True), (14, True)])
def test_editor_enforces_the_authored_21_day_cutoff(days_out, held):
    row = _bank()["5-10-15 Ladder (Box Jumps/Push-Ups/KB Swings)"]
    day = date(2026, 12, 1).toordinal() - days_out
    assert _safety([], day=date.fromordinal(day)).contraindicated(row) is held


@pytest.mark.parametrize("days_out,held", [(11, False), (10, True)])
def test_editor_enforces_the_authored_10_day_cutoff(days_out, held):
    row = _bank()["Pad EMOM (5x5 format)"]
    assert _safety([], day=date.fromordinal(date(2026, 12, 1).toordinal() - days_out)).contraindicated(row) is held


def test_editor_cutoff_needs_a_fight_and_fails_closed_on_a_bad_date():
    row = _bank()["5-10-15 Ladder (Box Jumps/Push-Ups/KB Swings)"]
    assert not _safety([], fight_date="").contraindicated(row)
    assert _safety([], fight_date="not-a-date").contraindicated(row)


@pytest.mark.parametrize("impact", ["not_limiting", "limiting", "cant_train"])
def test_stored_impact_marker_never_erases_the_injury_identity(impact):
    # "cant"/"not" in the marker used to read as negation: Today flags marked
    # cant_train/not_limiting lost their region and type in the rehab policy.
    from fightcamp.injury_formatting import parse_injury_entry

    parsed = parse_injury_entry(f"Right ankle right ankle sprain [training_impact:{impact}]")
    assert parsed and parsed["canonical_location"] == "ankle" and parsed["injury_type"] == "sprain"
    assert "training_impact" not in parsed["original_phrase"]


def test_cant_train_identity_reaches_rehab_selection():
    decision = resolve_injury_policy({**_ankle("cant_train"), "rehab_type": None, "injury_type": None},
                                     policies=load_clinical_policies(), bank=get_rehab_bank())
    assert decision["region"] == "ankle" and decision["injury_type"] == "sprain"
    assert decision["outcome"] not in {"medical_review", "missing_information"}
