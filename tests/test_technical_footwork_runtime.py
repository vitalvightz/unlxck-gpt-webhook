"""Runtime regression proofs for the dedicated technical footwork path.

The technical footwork bank was reclassified out of the conditioning scoring
pool into its own bank, consumed through a relevance-gated selector/insert
(``select_technical_footwork_drill`` / ``_insert_technical_footwork_drill``)
mirroring the coordination-goal guarantee. These tests pin the contract:

1. technical footwork appears for footwork-relevant athletes;
2. it is never a primary energy-system conditioning dose;
3. injury exclusions still gate it;
4. taper / D-day (reactive, complexity, late_windows) gating is per-drill;
5. sport / style matching still works;
6. ordinary conditioning selection is unaffected.
"""
from __future__ import annotations

import types

from fightcamp import conditioning


FOOTWORK_NAMES = {d["name"] for d in conditioning.get_technical_footwork_bank()}


def _flags(**over) -> dict:
    base = dict(
        phase="GPP",
        fatigue="low",
        sport="boxing",
        fight_format="boxing",
        style_tactical=["counter_striker"],
        style_technical=["boxing"],
        equipment=["bodyweight", "bands", "assault_bike"],
        training_days=["Mon", "Wed", "Fri"],
        training_frequency=3,
        days_available=3,
        key_goals=["footwork"],
        weaknesses=[],
        injuries=[],
        days_until_fight=40,
        random_seed=7,
    )
    base.update(over)
    return base


# --- Proof 1: appears for footwork-relevant athletes -----------------------

def test_selector_returns_a_drill_for_footwork_relevant_athletes():
    for phase in ("GPP", "SPP", "TAPER"):
        drill = conditioning.select_technical_footwork_drill(_flags(phase=phase), set(), [])
        assert drill is not None, phase
        assert drill["name"] in FOOTWORK_NAMES


def test_selector_returns_none_without_footwork_relevance():
    assert conditioning.select_technical_footwork_drill(_flags(key_goals=["power"]), set(), []) is None
    # weakness-based relevance also opens the gate
    assert conditioning.select_technical_footwork_drill(
        _flags(key_goals=["power"], weaknesses=["ring movement"]), set(), []
    ) is not None


def test_insert_surfaces_footwork_in_taper_for_a_footwork_athlete():
    # In taper the conditioning block is heavily restricted, so the
    # relevance-gated technical footwork insert fills the gap — exactly the
    # "familiar low-fatigue movement near the fight" case the reclassification
    # is meant to support. Deterministic across hash seeds.
    _markdown, names, *_rest = conditioning.generate_conditioning_block(
        _flags(phase="TAPER", days_until_fight=18)
    )
    assert FOOTWORK_NAMES.intersection(names), names


# --- Proof 2: never a *scored* conditioning dose ----------------------------

def test_footwork_is_not_in_the_conditioning_scoring_pool():
    pool = {d.get("name") for d in conditioning.get_conditioning_bank()}
    assert FOOTWORK_NAMES.isdisjoint(pool)


def test_footwork_only_ever_enters_via_the_technical_guarantee():
    # Technical footwork is never scored against the energy-system pool. When it
    # appears at all it must carry the technical_footwork_guarantee reason code,
    # i.e. it entered as the relevance-gated technical insert, not as a
    # competitively-scored primary conditioning dose.
    for phase in ("GPP", "SPP", "TAPER"):
        days = 40 if phase != "TAPER" else 18
        _markdown, _names, entries, *_rest = conditioning.generate_conditioning_block(
            _flags(phase=phase, days_until_fight=days)
        )
        for entry in entries:
            if entry.get("name") in FOOTWORK_NAMES:
                codes = entry.get("reasons", {}).get("reason_codes", [])
                assert "technical_footwork_guarantee" in codes, (phase, entry.get("name"), codes)


# --- Proof 3: injury exclusions still gate it -------------------------------

def test_selector_applies_injury_exclusion(monkeypatch):
    excluded = types.SimpleNamespace(action="exclude", reasons=[], severity="high")
    monkeypatch.setattr(conditioning, "injury_decision", lambda *a, **k: excluded)
    assert conditioning.select_technical_footwork_drill(_flags(), set(), ["knee pain"]) is None


def test_selector_returns_drill_when_injury_allows():
    # A benign injury that does not exclude gentle technical footwork still
    # yields a drill (the gate is applied, not blanket-blocking).
    drill = conditioning.select_technical_footwork_drill(_flags(injuries=["mild wrist soreness"]), set(), ["mild wrist soreness"])
    assert drill is not None


# --- Proof 4: taper / D-day gating is per-drill -----------------------------

def test_taper_excludes_reactive_and_high_complexity_drills():
    drill = conditioning.select_technical_footwork_drill(_flags(phase="TAPER"), set(), [])
    assert drill is not None
    assert drill.get("reactive_level") != "reactive"
    assert drill.get("technical_complexity") != "high"


def test_late_window_gate_respects_per_drill_late_windows():
    bank = {d["name"]: d for d in conditioning.get_technical_footwork_bank()}
    # Stance Reset lists d4_to_d2; it must not be window-blocked there.
    stance = conditioning._evaluate_conditioning_late_window(
        bank["Stance Reset Line Drill"], system="aerobic", window="d4_to_d2", bridge_rules=None,
        source="technical_footwork_bank.json",
    )
    assert "late_conditioning_block_window_mismatch" not in stance["block_codes"]
    # Sprawl Exit stops at d13_to_d8; at d4_to_d2 it is outside its window.
    sprawl = conditioning._evaluate_conditioning_late_window(
        bank["Sprawl Exit to Ring Angle"], system="aerobic", window="d4_to_d2", bridge_rules=None,
        source="technical_footwork_bank.json",
    )
    assert sprawl["blocked"]


# --- Proof 5: sport / style matching ----------------------------------------

def test_sport_and_style_matching():
    boxer = conditioning.select_technical_footwork_drill(_flags(), set(), [])
    assert "boxing" in {t.lower() for t in boxer.get("tags", [])}

    kicker = conditioning.select_technical_footwork_drill(
        _flags(sport="muay_thai", fight_format="muay_thai", style_tactical=["kicker"], style_technical=["muay_thai"]),
        set(),
        [],
    )
    kicker_tags = {t.lower() for t in kicker.get("tags", [])}
    assert kicker_tags & {"muay_thai", "kickboxing", "kicker"}

    wrestler = conditioning.select_technical_footwork_drill(
        _flags(phase="SPP", sport="mma", fight_format="mma", style_tactical=["wrestler"], style_technical=["mma"]),
        set(),
        [],
    )
    assert "mma" in {t.lower() for t in wrestler.get("tags", [])}


# --- Proof 6: ordinary conditioning selection is unaffected -----------------

def test_non_footwork_athlete_gets_no_technical_footwork():
    for phase in ("GPP", "SPP", "TAPER"):
        days = 40 if phase != "TAPER" else 18
        flags = _flags(phase=phase, days_until_fight=days, key_goals=["conditioning", "power"])
        _markdown, names, drills, grouped, *_rest = conditioning.generate_conditioning_block(flags)
        assert FOOTWORK_NAMES.isdisjoint(names), (phase, names)
        grouped_names = {
            d.get("name")
            for entries in (grouped.values() if isinstance(grouped, dict) else [])
            for d in entries
        }
        assert FOOTWORK_NAMES.isdisjoint(grouped_names), (phase, grouped_names)


def test_conditioning_pool_has_no_technical_footwork_modality():
    assert not [d for d in conditioning.get_conditioning_bank() if d.get("modality") == "technical_footwork"]
