"""Owner decision: anyone can provide these, so they never gate eligibility."""
from types import SimpleNamespace

import pytest

from api.services.exercise_customisation import _equipment_available, _library_index
from fightcamp import conditioning, strength
from fightcamp.training_catalogue import build_catalogue
from fightcamp.training_context import normalize_athlete_equipment_list, normalize_equipment_list


@pytest.mark.parametrize("raw,expected", [
    ("towel/bar", ["towel"]), ("bodyweight,pad", ["bodyweight"]), ("line/tape", []),
    (["mat", "partner"], ["partner"]), (["mats"], []), (["table", "tape"], ["table"]),
    (["wall", "mat"], ["wall"]), ("pads", ["pads"]), (["foam_pad"], ["foam_pad"]),
])
def test_not_required_tokens_are_dropped(raw, expected):
    assert normalize_equipment_list(raw) == expected


def test_dumbbells_imply_a_single_dumbbell_but_not_the_reverse():
    assert "dumbbell" in normalize_athlete_equipment_list(["dumbbells"])
    assert "dumbbells" not in normalize_athlete_equipment_list(["dumbbell"])


def test_no_live_row_needs_a_dropped_token():
    dropped = {"mat", "mats", "line", "tape", "line_tape", "bar", "pad"}
    for entry in build_catalogue():
        raw = entry["raw"]
        assert not set(normalize_equipment_list(raw.get("required_equipment") or raw.get("equipment") or [])) & dropped


def _editor(name, equipment):
    record = next(r for r in _library_index().records if r["entry"]["name"] == name)
    return _equipment_available(record, SimpleNamespace(equipment=set(normalize_athlete_equipment_list(equipment))))


@pytest.mark.parametrize("name,needs", [
    ("Towel Hang", ["towel"]), ("Adductor Squeeze Isometric", []),
    ("Tandem Gait Walk (Heel-to-Toe)", []), ("Side Hop-to-Stabilize", []),
    ("Reactive Sprawl Jumps", []), ("Seated supported biceps curl", ["dumbbells"]),
    ("Tape-Assisted Plyo Taps", ["table"]),
])
def test_editor_offers_rows_with_only_their_remaining_equipment(name, needs):
    assert _editor(name, needs)
    if needs:
        assert not _editor(name, [])


def test_strength_generation_reaches_former_dead_rows():
    flags = dict(phase="TAPER", fatigue="low", style_technical=["kickboxing"], style_tactical=["clinch_fighter"],
                 key_goals=["conditioning"], primary_goal="conditioning", weaknesses=["balance"],
                 equipment=["barbell", "heavy_bag"], injuries=[], training_frequency=4, days_available=4,
                 training_days=["Monday", "Tuesday", "Thursday", "Saturday"], days_until_fight=9,
                 fight_format="kickboxing", random_seed=7)
    names = {ex["name"] for ex in strength.generate_strength_block(flags=flags).get("exercises", [])}
    assert "Adductor Squeeze Isometric" in names


def test_mat_style_rows_keep_only_their_other_equipment():
    rows = [r for r in conditioning.get_style_conditioning_bank() if "mat" in str(r.get("equipment"))]
    assert rows
    for row in rows:
        required = conditioning._conditioning_required_equipment(row)
        assert not {"mat", "mats"} & set(required)
        if set(row["equipment"]) <= {"mat", "mats"}:
            assert conditioning._conditioning_is_universally_available(row)
