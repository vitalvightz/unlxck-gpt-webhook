from __future__ import annotations

import json
from pathlib import Path

from fightcamp.tagging import normalize_tags

ROOT = Path(__file__).resolve().parents[1]
FOOTWORK_BANK = ROOT / "data" / "technical_footwork_bank.json"

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

# Structured taxonomy the runtime selector relies on (reactive_level, phase
# eligibility, tactical_function) or that documents per-drill cost.
REACTIVE_LEVELS = {"closed", "semi_reactive", "reactive"}
DEMAND_LEVELS = {"low", "moderate", "high"}


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
    # The bank is technical movement rehearsal, not a physiological conditioning
    # dose: it stays aerobic, low-impact, low-lactate and low-RPE. Movement cost
    # is now differentiated per drill (low vs moderate) but never "high", which
    # the bank validator treats as a high-intensity late-safety contradiction.
    for item in _items():
        assert item.get("system") == "aerobic"
        assert item.get("impact_cost") == "low"
        assert item.get("lactate_load") == "low"
        assert item.get("movement_cost") in {"low", "moderate"}
        assert item.get("rpe", 0) <= 6
        assert item.get("rounds", 0) <= 2


def test_every_drill_has_load_bearing_taxonomy():
    # reactive_level, technical_complexity and tactical_function are read by the
    # runtime selector (fightcamp.conditioning.select_technical_footwork_drill),
    # so every drill must carry valid values.
    for item in _items():
        assert item.get("reactive_level") in REACTIVE_LEVELS, item["name"]
        assert item.get("technical_complexity") in DEMAND_LEVELS, item["name"]
        assert item.get("braking_demand") in DEMAND_LEVELS, item["name"]
        assert item.get("elastic_demand") in DEMAND_LEVELS, item["name"]
        functions = item.get("tactical_function")
        assert isinstance(functions, list) and functions, item["name"]
        assert item.get("footwork_pattern"), item["name"]


def test_reactive_and_high_complexity_drills_are_not_taper_phased():
    # Consistency guard for the selector's taper gate: anything reactive or of
    # high technical complexity must not claim TAPER phase eligibility.
    for item in _items():
        phases = {str(p).upper() for p in item.get("phases", [])}
        if item.get("reactive_level") == "reactive" or item.get("technical_complexity") == "high":
            assert "TAPER" not in phases, item["name"]


def test_late_windows_absent_from_high_movement_cost_drills():
    # A drill flagged moderate/low movement cost may carry late_windows; the
    # validator forbids high movement cost alongside late_windows.
    for item in _items():
        if item.get("movement_cost") == "high":
            assert not item.get("late_windows"), item["name"]


def test_bank_is_not_loaded_into_the_conditioning_scoring_pool():
    # Core architectural guarantee: technical footwork is NOT merged into the
    # conditioning scoring pool, so it can never be selected as a primary
    # energy-system conditioning dose. It lives in its own bank instead.
    from fightcamp.conditioning import get_conditioning_bank, get_technical_footwork_bank

    pool_names = {item.get("name") for item in get_conditioning_bank()}
    footwork_names = {item.get("name") for item in get_technical_footwork_bank()}

    assert footwork_names, "technical footwork bank should load drills"
    assert footwork_names.isdisjoint(pool_names), (
        "technical footwork drills must not appear in the conditioning pool"
    )
    # Modality is preserved for downstream identification.
    assert all(
        item.get("modality") == "technical_footwork"
        for item in get_technical_footwork_bank()
    )
