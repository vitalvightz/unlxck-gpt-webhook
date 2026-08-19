"""The new rehab metadata is a data contract, not yet an authority.

PR1 adds structured rehab/safety metadata to the bank. Nothing reads it when
choosing drills. These tests hold that line: hostile metadata (a stage that says
"return", high impact/load/velocity, a severity gate that excludes the athlete,
a zero pain ceiling, explicit stop rules) must leave the generated rehab block
byte-identical, and every legacy behaviour — phase progression, severity
filtering, surface-injury separation, red flags — must be untouched.
"""

from __future__ import annotations

import copy

import pytest

from fightcamp import rehab_protocols
from fightcamp.rehab_protocols import (
    SURFACE_WOUND_CARE_NOTE,
    classify_drill_function,
    generate_rehab_protocols,
    get_rehab_bank,
    match_drill_function,
)
from fightcamp.rehab_schema import MSK_DRILL_FIELDS, is_surface_injury_type

PHASES = ("GPP", "SPP", "TAPER")


@pytest.fixture
def restorable_bank():
    """Yield the live bank, restoring the original records afterwards."""
    original = copy.deepcopy(get_rehab_bank())
    yield get_rehab_bank()
    rehab_protocols._REHAB_BANK_CACHE = original


def _protocol(injury: str, phase: str, **kwargs) -> str:
    text, _ = generate_rehab_protocols(
        injury_string=injury, exercise_data=[], current_phase=phase, **kwargs
    )
    return text


def _structured(location: str, injury_type: str, severity: str | None = None) -> list[dict]:
    return [
        {
            "canonical_location": location,
            "location": location,
            "rehab_type": injury_type,
            "injury_type": injury_type,
            "severity": severity,
        }
    ]


def _hostile_metadata(bank: list[dict]) -> None:
    """Stamp every musculoskeletal drill with metadata that would forbid it."""
    for entry in bank:
        if is_surface_injury_type(entry.get("type")):
            continue
        for drill in entry.get("drills", []):
            drill.update(
                {
                    "rehab_stage": "return",
                    "function": "tendon_loading",
                    "equipment": ["barbell"],
                    "dose": {"sets": 99, "reps": 99, "duration_seconds": 999},
                    "impact": "high",
                    "load": "high",
                    "velocity": "high",
                    "pain_ceiling": 0,
                    "allowed_severities": ["high"],
                    "progress_when": ["never"],
                    "regress_when": ["always"],
                    "stop_when": ["any pain at all"],
                }
            )


# ---------------------------------------------------------------------------
# The new metadata does not drive selection
# ---------------------------------------------------------------------------


CASES = [
    ("ankle sprain", "ankle", "sprain", None),
    ("knee pain", "knee", "pain", "low"),
    ("shoulder impingement", "shoulder", "impingement", "moderate"),
    ("achilles tendonitis", "achilles", "tendonitis", "high"),
    ("lower back stiffness", "lower_back", "stiffness", None),
    ("hamstring strain", "hamstring", "strain", "moderate"),
]


@pytest.mark.parametrize("injury,location,injury_type,severity", CASES)
@pytest.mark.parametrize("phase", PHASES)
def test_hostile_metadata_does_not_change_the_rehab_block(
    restorable_bank, injury, location, injury_type, severity, phase
):
    parsed = _structured(location, injury_type, severity)
    before = _protocol(injury, phase, parsed_entries=parsed)

    _hostile_metadata(restorable_bank)
    after = _protocol(injury, phase, parsed_entries=parsed)

    assert after == before


@pytest.mark.parametrize("day_type", [None, "sparring", "strength", "aerobic", "recovery"])
def test_hostile_metadata_does_not_change_day_type_output(restorable_bank, day_type):
    parsed = _structured("knee", "tendonitis", "moderate")
    before = _protocol("knee tendonitis", "SPP", parsed_entries=parsed, day_type=day_type)

    _hostile_metadata(restorable_bank)

    assert _protocol("knee tendonitis", "SPP", parsed_entries=parsed, day_type=day_type) == before


def test_stripping_the_metadata_entirely_does_not_change_the_rehab_block(restorable_bank):
    """Legacy, unmigrated records still render exactly the same."""
    parsed = _structured("ankle", "sprain")
    before = _protocol("ankle sprain", "GPP", parsed_entries=parsed)

    for entry in restorable_bank:
        for drill in entry.get("drills", []):
            for field in (*MSK_DRILL_FIELDS, "id"):
                drill.pop(field, None)

    assert _protocol("ankle sprain", "GPP", parsed_entries=parsed) == before


def test_metadata_values_never_leak_into_the_rendered_block():
    text = _protocol("ankle sprain", "GPP", parsed_entries=_structured("ankle", "sprain"))

    assert text.strip()
    for marker in ("rehab_stage", "pain_ceiling", "allowed_severities", "duration_seconds", "ankle_sprain_"):
        assert marker not in text


# ---------------------------------------------------------------------------
# Legacy runtime behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phase", PHASES)
def test_legacy_selection_still_returns_drills(phase):
    text = _protocol("ankle sprain", phase, parsed_entries=_structured("ankle", "sprain"))

    assert "Ankle" in text
    assert "•" in text
    assert "[Function:" in text
    assert "Consult with a healthcare professional" not in text


def test_phase_progression_still_selects_phase_specific_notes():
    """A GPP→SPP drill renders its GPP half in GPP and its SPP half in SPP."""
    gpp = _protocol("ankle sprain", "GPP", parsed_entries=_structured("ankle", "sprain"))
    spp = _protocol("ankle sprain", "SPP", parsed_entries=_structured("ankle", "sprain"))

    assert "Rebuild proprioception" in gpp
    assert "Rebuild proprioception" not in spp
    assert "→" not in gpp.split("[Function:")[0]


@pytest.mark.parametrize("phase", PHASES)
def test_each_phase_yields_its_own_block(phase):
    text = _protocol("knee tendonitis", phase, parsed_entries=_structured("knee", "tendonitis"))
    assert "Knee" in text


def test_sparring_day_keeps_the_single_drill_ceiling():
    text = _protocol(
        "knee tendonitis", "SPP", parsed_entries=_structured("knee", "tendonitis"), day_type="sparring"
    )
    assert len([line for line in text.splitlines() if line.strip().startswith("•")]) == 1


def test_high_severity_still_filters_aggressive_drills():
    text = _protocol(
        "ankle instability", "SPP", parsed_entries=_structured("ankle", "instability", "high")
    )
    lowered = text.lower()
    for blocked in ("pogo", "depth jump", "hop-stick"):
        assert blocked not in lowered


def test_no_injury_still_short_circuits():
    assert "No rehab work required" in _protocol("", "GPP")


# ---------------------------------------------------------------------------
# Safety gates are untouched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("injury_type", ["cut", "laceration", "abrasion", "graze", "blister"])
def test_surface_injuries_stay_out_of_loading_rehab(injury_type):
    text = _protocol(
        f"knee {injury_type}", "GPP", parsed_entries=_structured("knee", injury_type)
    )

    assert "[Function:" not in text
    for loading in ("isometric", "eccentric", "balance", "calf raise"):
        assert loading not in text.lower()


def test_surface_wound_care_note_is_still_used_for_open_wounds():
    text = _protocol("knee cut", "GPP", parsed_entries=_structured("knee", "cut"))
    assert SURFACE_WOUND_CARE_NOTE in text


def test_minor_surface_injury_still_trains_through():
    from fightcamp.injury_registry import SURFACE_MINOR_TRAIN_THROUGH_NOTE

    text = _protocol("knee graze", "GPP", parsed_entries=_structured("knee", "graze"))
    assert SURFACE_MINOR_TRAIN_THROUGH_NOTE in text


def test_urgent_structured_injury_still_returns_the_red_flag_block():
    parsed = [
        {
            "canonical_location": "knee",
            "injury_type": "acl_tear",
            "rehab_type": "acl_tear",
            "flags": ["urgent", "structural_red_flag"],
            "triage_category": "suspected_ligament_tear",
        }
    ]
    text = _protocol("knee acl tear", "GPP", parsed_entries=parsed)

    assert "Red Flag Detected" in text
    assert "•" in text
    assert "[Function:" not in text


def test_red_flag_text_injury_still_blocks_rehab():
    text = _protocol("knee fracture", "GPP")

    assert "Red Flag Detected" in text
    assert "cleared by clinician" in text


# ---------------------------------------------------------------------------
# The keyword classifier remains the runtime fallback
# ---------------------------------------------------------------------------


def test_match_drill_function_reports_ambiguity_instead_of_defaulting():
    assert match_drill_function("Banded Clamshell") == "activation"
    assert match_drill_function("Heel Walks") is None


def test_classify_drill_function_still_defaults_to_control():
    assert classify_drill_function("Heel Walks") == rehab_protocols.AMBIGUOUS_DRILL_FUNCTION
    assert classify_drill_function("Heel Walks") == "control"


def test_stored_function_metadata_matches_the_keyword_match_where_migrated():
    """Migration derived `function` from the classifier; it invented nothing."""
    for entry in get_rehab_bank():
        if is_surface_injury_type(entry.get("type")):
            continue
        for drill in entry.get("drills", []):
            declared = drill.get("function")
            if declared is None:
                assert match_drill_function(drill["name"], drill.get("notes", "")) is None
            else:
                assert declared == match_drill_function(drill["name"], drill.get("notes", ""))
