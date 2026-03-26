import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import normalize_injury_regions
from fightcamp.injury_formatting import parse_injury_entry
from fightcamp.injury_synonyms import parse_injury_phrase, split_injury_text
from fightcamp.rehab_protocols import (
    build_coach_review_entries,
    generate_rehab_protocols,
)
from fightcamp.coach_review import build_coach_review_notes


def _rehab_text(injury: str, phase: str) -> str:
    text, _ = generate_rehab_protocols(
        injury_string=injury,
        exercise_data=[],
        current_phase=phase,
    )
    return text


def test_negation_strips_injury_phrases():
    samples = [
        "no shoulder pain",
        "not injured",
        "no shin splints",
        "never had knee issues",
    ]
    for sample in samples:
        assert parse_injury_entry(sample) is None
        assert normalize_injury_regions([sample]) == set()


def test_multi_injury_split_and_parse():
    sample = "Left ankle sprain / right wrist pain and shoulder tightness, knee soreness."
    phrases = split_injury_text(sample)
    assert len(phrases) == 4
    entries = [parse_injury_entry(phrase) for phrase in phrases]
    entries = [entry for entry in entries if entry]
    locations = {entry.get("canonical_location") for entry in entries}
    assert {"ankle", "wrist", "shoulder", "knee"} <= locations


def test_punctuation_and_hyphenated_phrases_parse():
    sample = "Shoulder. left-ankle sprain (mild); knee pain."
    phrases = split_injury_text(sample)
    entries = [parse_injury_phrase(phrase) for phrase in phrases]
    locations = {loc for _, loc in entries if loc}
    assert {"shoulder", "ankle", "knee"} <= locations


def test_canonical_injury_types_are_allowed():
    allowed = {
        "sprain",
        "strain",
        "tightness",
        "contusion",
        "swelling",
        "tendonitis",
        "impingement",
        "instability",
        "stiffness",
        "pain",
        "soreness",
        "hyperextension",
        "unspecified",
    }
    entry = parse_injury_entry("shin splints")
    assert entry is not None
    assert entry.get("injury_type") in allowed
    assert entry.get("injury_type") != "shin splints"


def test_rehab_lookup_fallbacks_for_location_aliases():
    text, _ = generate_rehab_protocols(
        injury_string="lower back pain, biceps strain",
        exercise_data=[],
        current_phase="GPP",
    )
    assert "No rehab options" not in text


def test_anterior_hip_aliases_parse_to_hip_flexor():
    for sample in ("hip flexor tightness", "front of hip strain", "psoas strain"):
        entry = parse_injury_entry(sample)
        assert entry is not None
        assert entry.get("canonical_location") == "hip flexor"


def test_hip_flexor_rehab_output_keeps_front_hip_identity():
    text, _ = generate_rehab_protocols(
        injury_string="hip flexor tightness",
        exercise_data=[],
        current_phase="GPP",
    )

    assert "- Hip Flexor (Tightness):" in text
    assert "Hamstring" not in text
    assert "Calf" not in text


def test_front_of_hip_strain_coach_review_avoids_lower_leg_fallback_language():
    notes = build_coach_review_notes(
        build_coach_review_entries("front of hip strain", "GPP"),
        [],
    )

    assert "Hip Flexor" in notes
    assert "Strain" in notes
    assert "Progressive calf/hamstring strength." not in notes
    assert "Balance/proprioception for ankle." not in notes


def test_hip_flexor_return_bridge_output_wins_across_phases():
    phase_markers = {
        "GPP": "Build pain-free isometric hip flexion without anterior pinch",
        "SPP": "Bridge into stronger knee-drive holds without losing pelvis position",
        "TAPER": "Keep crisp low-cost step-in timing only",
    }

    for phase, marker in phase_markers.items():
        text = _rehab_text("hip flexor strain", phase)
        assert marker in text
        assert "General Isometric Holds" not in text


def test_groin_return_bridge_output_wins_across_phases():
    phase_markers = {
        "GPP": "Control midline load without deep provocative range",
        "SPP": "Bridge adductor control into entry, recoil, and balance restack",
        "TAPER": "Keep one clean return-to-strike bridge set without fatigue",
    }

    for phase, marker in phase_markers.items():
        text = _rehab_text("groin strain", phase)
        assert marker in text
        assert "Side-Lying Hip Adduction" not in text


def test_trunk_rotation_return_bridge_output_wins_across_phases():
    phase_markers = {
        "GPP": "Rebuild low-load trunk reload with feet quiet and ribs stacked",
        "SPP": "Bridge trunk control into jab-cross transfer",
        "TAPER": "Keep one sharp transfer set without fatigue",
    }

    for phase, marker in phase_markers.items():
        text = _rehab_text("obliques pain", phase)
        assert marker in text
        assert "Pallof Press (Light Band)" not in text


def test_shoulder_return_bridge_output_wins_across_phases():
    phase_markers = {
        "GPP": "Prepare scap and cuff without shrug-driven compensation",
        "SPP": "Bridge press tolerance into jab-return mechanics",
        "TAPER": "Keep low-volume sharp reps only",
    }

    for phase, marker in phase_markers.items():
        text = _rehab_text("shoulder strain", phase)
        assert marker in text
        assert "Wall Slides with Foam Roller" not in text


def test_ankle_and_foot_return_bridge_output_wins_across_phases():
    ankle_markers = {
        "GPP": "Rebuild arch stiffness and stance-base awareness in boxing posture",
        "SPP": "Add glove reach or head movement without losing base",
        "TAPER": "Keep short reactive brace touches only",
    }
    foot_markers = {
        "GPP": "Rebuild controlled pivot and deceleration at small angles",
        "SPP": "Bridge foot control into exit-and-restack movement",
        "TAPER": "Keep one low-fatigue footwork bridge set only",
    }

    for phase, marker in ankle_markers.items():
        text = _rehab_text("ankle instability", phase)
        assert marker in text
        assert "Reactive Stability Drills" not in text

    for phase, marker in foot_markers.items():
        text = _rehab_text("foot pain", phase)
        assert marker in text
        assert "Short Foot Doming" not in text
