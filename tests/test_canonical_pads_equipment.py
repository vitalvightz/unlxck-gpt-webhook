"""Canonical combat pad/mitt equipment capability.

Thai pads, focus mitts and partner mitts are one athlete-facing capability:
handheld striking pads held by a partner. The banks spell it four different
ways while intake only ever stored one spelling, so eligibility
(``required_equipment <= athlete_equipment``) silently dropped valid drills.
These tests pin the canonical ``pads`` token, the legacy-profile and
legacy-bank compatibility that depends on it, and the fact that ``partner``
stays an independent capability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fightcamp import conditioning
from fightcamp.stage2_validator import _normalize_equipment_set
from fightcamp.training_context import (
    PADS,
    known_equipment,
    normalize_athlete_equipment_list,
    normalize_equipment_list,
)


TAPER_BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_taper_conditioning.json"
PRESSURE_PAD_DRILLS = ("Cut-Off-Step-Score", "Herd-Corner-Burst-Reset")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "thai_pads",
        "thai_pad",
        "thai pads",
        "thai pad",
        "focus_mitts",
        "focus mitts",
        "focus_mitt",
        "partner_mitts",
        "partner mitts",
        "boxing mitts",
        "boxing_mitts",
        "punch mitts",
        "punch_mitts",
        "mitts",
        "pads",
        "Thai Pads",
        "Focus Mitts",
    ],
)
def test_pad_variants_normalize_to_canonical_pads(raw):
    assert normalize_equipment_list([raw]) == [PADS]


def test_canonical_token_is_pads():
    assert PADS == "pads"
    assert PADS in known_equipment


@pytest.mark.parametrize(
    "raw",
    ["heavy_bag", "punching_bag", "double_end_bag", "foam_pad", "partner", "mat"],
)
def test_unrelated_equipment_is_not_aliased_to_pads(raw):
    assert PADS not in normalize_equipment_list([raw])


def test_mixed_legacy_pad_tokens_collapse_to_one_capability():
    assert normalize_equipment_list(["thai_pads", "focus_mitts"]) == [PADS]
    assert normalize_equipment_list(["thai_pads", "focus_mitts", "partner_mitts", "pads"]) == [PADS]


def test_normalization_dedupes_without_dropping_distinct_capabilities():
    assert normalize_equipment_list(["focus_mitts", "partner", "thai_pad", "partner"]) == [
        PADS,
        "partner",
    ]


def test_comma_and_slash_separated_strings_normalize():
    assert normalize_equipment_list("thai_pads, focus_mitts") == [PADS]
    assert normalize_equipment_list(["focus_mitts/partner"]) == [PADS, "partner"]


def test_legacy_athlete_profile_values_normalize_without_migration():
    """Saved profiles still carry the pre-canonical intake value."""
    normalized = normalize_athlete_equipment_list(["thai_pads", "partner"])
    assert PADS in normalized
    assert "partner" in normalized
    assert "bodyweight" in normalized
    assert "thai_pads" not in normalized


# ---------------------------------------------------------------------------
# Eligibility (required_equipment ⊆ athlete_equipment, after normalization)
# ---------------------------------------------------------------------------


def _eligible(athlete: list[str], required: list[str]) -> bool:
    return set(normalize_equipment_list(required)).issubset(
        set(normalize_athlete_equipment_list(athlete))
    )


def test_legacy_athlete_pads_satisfy_legacy_bank_mitts():
    assert _eligible(["thai_pads", "partner"], ["focus_mitts", "partner"])


def test_canonical_athlete_pads_satisfy_legacy_bank_mitts():
    assert _eligible(["pads", "partner"], ["focus_mitts", "partner"])
    assert _eligible(["pads", "partner"], ["thai_pad", "partner"])
    assert _eligible(["pads", "partner"], ["partner_mitts"])


def test_partner_remains_an_independent_capability():
    """Owning pads must never imply having someone to hold them."""
    assert not _eligible(["pads"], ["focus_mitts", "partner"])
    assert not _eligible(["thai_pads"], ["partner_mitts", "partner"])
    # ...and a partner alone does not conjure pads.
    assert not _eligible(["partner"], ["focus_mitts"])


def test_genuine_equipment_mismatch_is_still_blocked():
    assert not _eligible(["pads", "partner"], ["heavy_bag"])
    assert not _eligible(["pads", "partner"], ["sled", "partner"])


# ---------------------------------------------------------------------------
# Legacy bank compatibility - no bulk JSON rewrite required
# ---------------------------------------------------------------------------


def test_real_bank_still_contains_legacy_pad_tokens():
    """Guards the premise: runtime correctness must not depend on a data cleanup."""
    raw = TAPER_BANK_PATH.read_text(encoding="utf-8")
    assert "focus_mitts" in raw, "bank was canonicalised - this test's premise is stale"


def test_legacy_bank_entries_are_reachable_from_canonical_intake():
    bank = json.loads(TAPER_BANK_PATH.read_text(encoding="utf-8"))
    athlete = set(normalize_athlete_equipment_list(["pads", "partner"]))
    legacy_pad_drills = [
        entry
        for entry in bank
        if {"thai_pads", "thai_pad", "focus_mitts", "partner_mitts"}
        & {str(token).lower() for token in entry.get("equipment", [])}
    ]
    assert legacy_pad_drills, "expected legacy pad tokens in the style taper bank"
    for entry in legacy_pad_drills:
        required = set(normalize_equipment_list(entry.get("equipment", [])))
        assert required.issubset(athlete), f"{entry['name']} unreachable: requires {sorted(required)}"


# ---------------------------------------------------------------------------
# Stage 2 validator agrees with the selectors
# ---------------------------------------------------------------------------


def test_validator_uses_the_same_canonical_semantics():
    athlete = _normalize_equipment_set(["thai_pads", "partner"])
    required = _normalize_equipment_set(["focus_mitts", "partner"])
    assert required.issubset(athlete), "validator would raise equipment_incongruent_selection"


def test_validator_still_flags_genuinely_unavailable_equipment():
    athlete = _normalize_equipment_set(["thai_pads", "partner"])
    assert not _normalize_equipment_set(["sled"]).issubset(athlete)
    # pads without a partner is a real mismatch, not an alias miss.
    assert not _normalize_equipment_set(["focus_mitts", "partner"]).issubset(
        _normalize_equipment_set(["pads"])
    )


# ---------------------------------------------------------------------------
# Style Taper regression: pressure-fighter pad drills become reachable
# ---------------------------------------------------------------------------


def _pressure_fighter_flags(equipment: list[str]) -> dict:
    return {
        "phase": "TAPER",
        "fatigue": "low",
        "sport": "boxing",
        "fight_format": "boxing",
        "style_tactical": ["pressure_fighter"],
        "style_technical": ["boxing"],
        "key_goals": [],
        "weaknesses": [],
        "injuries": [],
        "restrictions": [],
        "equipment": equipment,
        "training_frequency": 1,
        "days_available": 1,
        # D-6: inside the d6_to_d5 window both drills declare.
        "days_until_fight": 6,
    }


def _isolate_style_taper(monkeypatch, only: tuple[str, ...]) -> None:
    """Empty every other bank and trim the real taper bank to ``only``.

    With no other candidates in play, a selection is proof the drill survived
    the equipment filter - which is what this PR is about. It deliberately does
    not assert which of the two wins; ranking/diversity is out of scope.
    """
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(
        conditioning,
        "allocate_sessions",
        lambda *_a, **_k: {"strength": 0, "conditioning": 1, "recovery": 0},
    )
    monkeypatch.setattr(
        conditioning,
        "calculate_exercise_numbers",
        lambda *_a, **_k: {"strength": 0, "conditioning": 1},
    )

    original_load_bank = conditioning._load_bank

    def _trimmed_load_bank(path, *args, **kwargs):
        entries = original_load_bank(path, *args, **kwargs)
        if Path(path).name == "style_taper_conditioning.json":
            return [entry for entry in entries if entry.get("name") in only]
        return entries

    monkeypatch.setattr(conditioning, "_load_bank", _trimmed_load_bank)


@pytest.mark.parametrize("drill_name", PRESSURE_PAD_DRILLS)
@pytest.mark.parametrize("equipment", [["thai_pads", "partner"], ["pads", "partner"]])
def test_pressure_fighter_pad_drills_are_reachable(monkeypatch, drill_name, equipment):
    _isolate_style_taper(monkeypatch, only=(drill_name,))

    _out, _names, _why, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _pressure_fighter_flags(equipment)
    )

    selected = {
        drill.get("name") for drills in grouped.values() for drill in drills if drill.get("name")
    }
    assert drill_name in selected, (
        f"{drill_name} was filtered out for equipment {equipment}; "
        "it requires focus_mitts + partner, which normalize to pads + partner"
    )


@pytest.mark.parametrize("drill_name", PRESSURE_PAD_DRILLS)
def test_pressure_fighter_pad_drills_stay_blocked_without_a_partner(monkeypatch, drill_name):
    """Pads alone are not enough - partner is still an independent requirement."""
    _isolate_style_taper(monkeypatch, only=(drill_name,))

    _out, _names, _why, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        _pressure_fighter_flags(["thai_pads"])
    )

    selected = {
        drill.get("name") for drills in grouped.values() for drill in drills if drill.get("name")
    }
    assert drill_name not in selected
