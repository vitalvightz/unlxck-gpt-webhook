"""Regression coverage for the removal of ``universal_gpp_conditioning.json``.

The universal GPP conditioning bank (``data/universal_gpp_conditioning.json``)
and its Stage 1 ``universal_gpp_insertion`` post-step were removed. These tests
lock in that:

  1. The bank file is gone.
  2. A normal GPP conditioning block still generates candidates across the
     aerobic, glycolytic and alactic energy systems with the file absent
     (no ``FileNotFoundError`` / missing-bank fallback needed).
  3. Injury-bank aggregation never attempts to open the deleted file and still
     assembles every remaining bank.
"""
from collections import Counter
from pathlib import Path

from fightcamp import conditioning, injury_filtering
from fightcamp.config import DATA_DIR

DELETED_BANK = "universal_gpp_conditioning.json"


def _collect_drill_dicts(obj, sink):
    """Recursively gather drill-shaped dicts (have both ``system`` and ``name``)."""
    if isinstance(obj, dict):
        if "system" in obj and "name" in obj:
            sink.append(obj)
        else:
            for value in obj.values():
                _collect_drill_dicts(value, sink)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _collect_drill_dicts(value, sink)


def test_deleted_bank_file_is_absent():
    assert not (DATA_DIR / DELETED_BANK).exists()


def test_gpp_conditioning_generates_all_energy_systems_without_universal_bank():
    flags = {
        "sport": "boxing",
        "style_technical": ["boxing"],
        "style_tactical": ["Brawler"],
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "fatigue": "low",
        "equipment": [
            "heavy_bag",
            "focus_mitts",
            "partner",
            "barbell",
            "dumbbell",
            "kettlebell",
            "sled",
            "jump_rope",
            "rower",
            "bike",
        ],
        "training_frequency": 5,
        "days_available": 5,
        "days_until_fight": 35,
        "time_to_fight_days": 35,
        "injuries": [],
        "restrictions": [],
        "phase": "GPP",
    }

    # Must not raise FileNotFoundError now that the universal bank is gone.
    result = conditioning.generate_conditioning_block(flags)

    drills: list[dict] = []
    _collect_drill_dicts(result, drills)
    systems = Counter(str(drill.get("system")).lower() for drill in drills)

    for system in ("aerobic", "glycolytic", "alactic"):
        assert systems.get(system, 0) > 0, (
            f"expected {system} conditioning candidates in GPP, got {dict(systems)}"
        )


def test_injury_bank_aggregation_never_opens_deleted_bank(monkeypatch):
    opened: list[str] = []
    real_read_text = Path.read_text

    def tracking_read_text(self, *args, **kwargs):
        opened.append(self.name)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracking_read_text)

    banks = injury_filtering.collect_banks(mode="runtime")

    assert DELETED_BANK not in opened
    assert "universal_gpp_conditioning" not in banks

    # Aggregation still assembles the remaining conditioning + strength banks.
    assert banks["conditioning_bank"]
    assert banks["style_conditioning_bank"]
    assert banks["style_taper_conditioning"]
    assert banks["universal_gpp_strength"]
    # The deleted bank key must not resurface anywhere in the aggregate.
    assert not any("universal_gpp_conditioning" in key for key in banks)
