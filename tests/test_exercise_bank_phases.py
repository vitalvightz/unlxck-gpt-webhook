import json
from pathlib import Path


def test_exercise_bank_removed_taper_exercises_keep_non_empty_non_taper_phases():
    bank = json.loads(Path("data/exercise_bank.json").read_text())
    by_name = {entry["name"]: entry for entry in bank}

    expected_spp_only = {
        "Trap Bar Jump",
        "Cluster Set Trap Bar Deadlift",
        "Band-Resisted Sprawl to Sprint",
    }

    for name in expected_spp_only:
        assert name in by_name
        assert by_name[name]["phases"] == ["SPP"]
