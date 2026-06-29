from __future__ import annotations

import json
from pathlib import Path

from fightcamp.tagging import normalize_tags

ROOT = Path(__file__).resolve().parents[1]
FOOTWORK_BANK = ROOT / "data" / "footwork_conditioning_bank.json"

REQUIRED_FOOTWORK_TAGS = {
    "footwork",
    "lateral",
    "lateral_movement",
    "ringcraft",
    "angles",
    "pivot",
    "stance",
    "stance_reset",
    "angle_exit",
    "movement_quality",
    "balance",
    "coordination",
}

KEY_TAG_MINIMUMS = {
    "footwork": 8,
    "ringcraft": 3,
    "pivot": 4,
    "stance_reset": 4,
    "angle_exit": 4,
    "lateral_movement": 4,
}

TACTICAL_STYLE_TAGS = {
    "brawler",
    "pressure_fighter",
    "clinch_fighter",
    "counter_striker",
    "distance_striker",
    "submission_hunter",
    "kicker",
    "scrambler",
    "grappler",
    "wrestler",
}

FORBIDDEN_FOOTWORK_DEFAULT_TAGS = {
    "speed",
    "reactive",
    "high_cns",
    "plyometric",
    "explosive",
    "mech_cns_high",
    "mech_systemic_fatigue",
}


_ITEMS = json.loads(FOOTWORK_BANK.read_text(encoding="utf-8"))


def _items() -> list[dict]:
    return _ITEMS


def _tags(item: dict) -> set[str]:
    return set(normalize_tags(item.get("tags", [])))


def test_footwork_bank_covers_every_routing_tag():
    items = _items()
    coverage = {
        tag: [item["name"] for item in items if tag in _tags(item)]
        for tag in REQUIRED_FOOTWORK_TAGS
    }

    missing = {tag: names for tag, names in coverage.items() if not names}

    assert not missing


def test_core_footwork_tags_have_multiple_named_drills():
    items = _items()

    for tag, minimum in KEY_TAG_MINIMUMS.items():
        names = [item["name"] for item in items if tag in _tags(item)]
        assert len(names) >= minimum, f"{tag} only covered by {names}"


def test_footwork_bank_covers_every_tactical_style():
    items = _items()
    coverage = {
        style: [item["name"] for item in items if style in _tags(item)]
        for style in TACTICAL_STYLE_TAGS
    }

    missing = {style: names for style, names in coverage.items() if not names}

    assert not missing


def test_footwork_drills_do_not_default_to_speed_or_reactive_work():
    for item in _items():
        tags = _tags(item)
        leaked = tags & FORBIDDEN_FOOTWORK_DEFAULT_TAGS

        assert not leaked, (
            f"{item['name']} has speed/reactive leakage: {sorted(leaked)}"
        )


def test_footwork_bank_is_low_noise_and_not_glycolytic_density():
    for item in _items():
        assert item.get("system") == "aerobic"
        assert item.get("impact_cost") == "low"
        assert item.get("lactate_load") == "low"
        assert item.get("movement_cost") == "low"
        assert item.get("rpe", 0) <= 6
        assert item.get("rounds", 0) <= 2


def test_footwork_bank_is_loaded_into_conditioning_runtime():
    from fightcamp.conditioning import get_conditioning_bank

    names = {item.get("name") for item in get_conditioning_bank()}

    assert {
        "Step-Back Pivot Reset",
        "Lateral Exit to Re-Enter",
        "Corner Escape L-Step",
    }.issubset(names)
