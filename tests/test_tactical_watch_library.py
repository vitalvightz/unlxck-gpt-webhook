"""Selector + content-uniqueness tests for the Tactical Watch library.

Prove that the deterministic selector is style-aware, phase-aware and never
repeats a watch within a camp, and that every watch is genuinely distinct
across all athlete-visible fields (not just its title, and never the forbidden
shared four-line entry/danger/reset/round-1 contract).
"""

from __future__ import annotations

import pytest

from fightcamp.tactical_watch_library import (
    PHASES,
    STYLE_FAMILIES,
    TacticalWatch,
    TacticalWatchBankExhausted,
    all_watches,
    canonical_watch_signature,
    extract_tactical_style,
    normalize_camp_phase,
    normalize_tactical_style,
    ordered_phase_bank,
    select_tactical_watch,
    select_watch_by_occurrence,
)

_STYLE_SPECIFIC = ("distance_striker", "brawler", "counter_striker")


# --- style normalisation ---------------------------------------------------


@pytest.mark.parametrize(
    "raw, family",
    [
        # distance striker aliases
        ("distance striker", "distance_striker"),
        ("outside fighter", "distance_striker"),
        ("out-boxer", "distance_striker"),
        ("Out Boxer", "distance_striker"),
        ("range fighter", "distance_striker"),
        ("long-range striker", "distance_striker"),
        # brawler aliases
        ("brawler", "brawler"),
        ("pressure fighter", "brawler"),
        ("inside fighter", "brawler"),
        ("swarmer", "brawler"),
        ("volume pressure", "brawler"),
        # counter striker aliases
        ("counter striker", "counter_striker"),
        ("counter puncher", "counter_striker"),
        ("reactive counter fighter", "counter_striker"),
        # unsupported / missing -> generic
        ("wrestler", "generic"),
        ("", "generic"),
        (None, "generic"),
    ],
)
def test_style_aliases_normalise_to_family(raw, family):
    assert normalize_tactical_style(raw) == family


def test_boxing_sport_does_not_imply_distance_striker():
    # Sport is never a style signal; a boxer with no declared style is generic.
    assert extract_tactical_style({"sport": "boxing"}) == "generic"
    assert normalize_tactical_style("boxing") == "generic"


def test_extract_style_reads_declared_style_fields():
    assert extract_tactical_style({"tactical_styles": ["out-boxer"]}) == "distance_striker"
    assert extract_tactical_style({"technical_styles": ["swarmer"]}) == "brawler"
    assert extract_tactical_style({"tactical_style": "counter puncher"}) == "counter_striker"
    assert extract_tactical_style({}) == "generic"


@pytest.mark.parametrize(
    "raw, phase",
    [
        ("GPP", "GPP"),
        ("general prep", "GPP"),
        ("early camp", "GPP"),
        ("SPP", "SPP"),
        ("specific preparation", "SPP"),
        ("TAPER", "TAPER"),
        ("fight week", "TAPER"),
        ("peaking", "TAPER"),
        ("nonsense", "GPP"),
        ("", "GPP"),
    ],
)
def test_phase_aliases_normalise(raw, phase):
    assert normalize_camp_phase(raw) == phase


# --- selection: coverage across every style x phase ------------------------


@pytest.mark.parametrize("style", STYLE_FAMILIES)
@pytest.mark.parametrize("phase", PHASES)
def test_every_style_and_phase_returns_a_matching_watch(style, phase):
    watch = select_tactical_watch(style, phase, used_keys=set())
    assert isinstance(watch, TacticalWatch)
    assert watch.phase == phase
    # A style-specific request returns a style-specific first watch; generic
    # requests return a generic watch.
    if style in _STYLE_SPECIFIC:
        assert watch.style == style
    else:
        assert watch.style == "generic"


@pytest.mark.parametrize("phase", PHASES)
def test_unsupported_and_missing_style_use_generic(phase):
    for style in ("wrestler", "", None):
        watch = select_tactical_watch(style, phase, used_keys=set())
        assert watch.style == "generic"
        assert watch.phase == phase


# --- determinism -----------------------------------------------------------


@pytest.mark.parametrize("style", STYLE_FAMILIES)
@pytest.mark.parametrize("phase", PHASES)
def test_same_input_is_deterministic(style, phase):
    a = select_tactical_watch(style, phase, used_keys=set())
    b = select_tactical_watch(style, phase, used_keys=set())
    assert a.key == b.key
    # The first watch in a phase is always the first item of the ordered bank.
    assert a.key == ordered_phase_bank(style, phase)[0].key


def test_no_random_selection_first_watch_is_stable():
    # Range Map is the authored first distance-striker GPP watch.
    watch = select_tactical_watch("out-boxer", "GPP", used_keys=set())
    assert watch.name == "Range Map"
    assert watch.key == "distance_striker.gpp.range_map"


# --- multiple occurrences + no repeats -------------------------------------


@pytest.mark.parametrize("style", _STYLE_SPECIFIC)
@pytest.mark.parametrize("phase", PHASES)
def test_multiple_occurrences_advance_and_never_repeat(style, phase):
    used: set[str] = set()
    seen: list[str] = []
    # Walk the whole ordered bank (style watches then generic fallback): every
    # occurrence up to the bank size must be a new key.
    bank_size = len(ordered_phase_bank(style, phase))
    assert bank_size >= 3
    for _ in range(bank_size):
        watch = select_tactical_watch(style, phase, used_keys=used)
        assert watch is not None
        assert watch.key not in used, "selector repeated a key within a camp"
        used.add(watch.key)
        seen.append(watch.key)
    assert len(seen) == len(set(seen))


@pytest.mark.parametrize("style", _STYLE_SPECIFIC)
@pytest.mark.parametrize("phase", PHASES)
def test_occurrence_matches_used_key_ledger(style, phase):
    used: set[str] = set()
    for occurrence in range(1, 4):
        by_occurrence = select_watch_by_occurrence(style, phase, occurrence)
        by_ledger = select_tactical_watch(style, phase, used_keys=used)
        assert by_occurrence.key == by_ledger.key
        used.add(by_ledger.key)


def test_selection_fails_loudly_when_the_bank_is_exhausted():
    # No silent repetition fallback: once every watch in the style+generic bank
    # is used, the selector raises instead of returning a duplicate.
    for style in STYLE_FAMILIES:
        for phase in PHASES:
            bank = ordered_phase_bank(style, phase)
            used = {watch.key for watch in bank}
            with pytest.raises(TacticalWatchBankExhausted):
                select_tactical_watch(style, phase, used_keys=used)


def test_occurrence_beyond_bank_size_fails_loudly():
    for style in STYLE_FAMILIES:
        for phase in PHASES:
            over = len(ordered_phase_bank(style, phase)) + 1
            with pytest.raises(TacticalWatchBankExhausted):
                select_watch_by_occurrence(style, phase, over)


def test_generic_fallback_after_style_bank_exhaustion():
    # Distance-striker GPP has three authored watches; the fourth occurrence
    # must fall back to the phase-matched generic bank, never repeat a style key.
    used: set[str] = set()
    styles_seen: list[str] = []
    for _ in range(4):
        watch = select_tactical_watch("distance_striker", "GPP", used_keys=used)
        used.add(watch.key)
        styles_seen.append(watch.style)
    assert styles_seen[:3] == ["distance_striker"] * 3
    assert styles_seen[3] == "generic"


def test_full_camp_never_repeats_a_watch():
    # A realistic camp: 3 GPP, 3 SPP, 1 TAPER week for each style family.
    for style in STYLE_FAMILIES:
        used: set[str] = set()
        for phase, count in (("GPP", 3), ("SPP", 3), ("TAPER", 1)):
            for _ in range(count):
                watch = select_tactical_watch(style, phase, used_keys=used)
                assert watch.key not in used
                used.add(watch.key)


# --- phase separation ------------------------------------------------------


def test_gpp_and_taper_banks_do_not_overlap():
    for style in STYLE_FAMILIES:
        gpp = {w.key for w in ordered_phase_bank(style, "GPP")}
        taper = {w.key for w in ordered_phase_bank(style, "TAPER")}
        assert gpp.isdisjoint(taper)
        # No GPP analytical task can be selected during TAPER and vice versa.
        for watch in ordered_phase_bank(style, "TAPER"):
            assert watch.phase == "TAPER"
        for watch in ordered_phase_bank(style, "GPP"):
            assert watch.phase == "GPP"


# --- content uniqueness ----------------------------------------------------


def test_all_watch_keys_are_unique():
    keys = [w.key for w in all_watches()]
    assert len(keys) == len(set(keys))


def test_no_two_watches_share_canonical_content():
    watches = all_watches()
    signatures = [canonical_watch_signature(w) for w in watches]
    assert len(signatures) == len(set(signatures)), "two watches render identically"


def test_no_two_watches_in_the_same_style_phase_bank_are_identical():
    for style in STYLE_FAMILIES:
        for phase in PHASES:
            bank = ordered_phase_bank(style, phase)
            sigs = [canonical_watch_signature(w) for w in bank]
            assert len(sigs) == len(set(sigs))


def test_a_title_only_difference_does_not_satisfy_uniqueness():
    # Force every watch to share one identical name. If uniqueness were only a
    # title difference the signatures would now collide; they must stay distinct
    # because the WHY/mindset/instructions/progress bodies genuinely differ.
    renamed = [
        TacticalWatch(**{**watch.__dict__, "name": "Same Name"})
        for watch in all_watches()
    ]
    signatures = [canonical_watch_signature(watch) for watch in renamed]
    assert len(signatures) == len(set(signatures))


def test_watches_are_not_all_the_same_four_line_structure():
    watches = all_watches()
    instruction_tuples = [tuple(w.instructions) for w in watches]
    # Every instruction set is distinct...
    assert len(instruction_tuples) == len(set(instruction_tuples))
    # ...and the arrays are not one rigid length (a single four-line contract).
    lengths = {len(w.instructions) for w in watches}
    assert len(lengths) > 1


def test_no_watch_uses_the_forbidden_entry_danger_reset_round_one_contract():
    forbidden_prefixes = ("entry cue", "danger cue", "reset cue", "round 1")
    for watch in all_watches():
        lowered = [item.lower() for item in watch.instructions]
        matches = sum(
            1
            for prefix in forbidden_prefixes
            if any(item.startswith(prefix) for item in lowered)
        )
        # A watch must not reproduce the retired four-line output contract.
        assert matches < 4, f"{watch.key} reuses the forbidden four-line contract"


def test_every_watch_populates_all_athlete_visible_fields():
    for watch in all_watches():
        assert watch.name and watch.why and watch.intent and watch.focus
        assert watch.reset and watch.anchor and watch.context and watch.progress
        assert watch.duration_minutes > 0
        assert len(watch.instructions) >= 3
        assert all(item.strip() for item in watch.instructions)


def test_library_covers_all_named_watches_from_spec():
    names = {w.name for w in all_watches()}
    expected = {
        # distance striker
        "Range Map", "Lead-Hand Battle", "Exit Discipline",
        "Intercept the Entry", "Exit Lane Audit", "Rope and Corner Escape",
        "First-Round Range Script",
        # brawler
        "Pressure Route Scan", "Safe Entry Builder", "Pressure Reset",
        "Pocket Exchange Map", "Body Attack Opportunity", "Smother and Reset",
        "First-Round Pressure Script",
        # counter striker
        "Trigger Library", "Draw the Lead", "Counter Activity Check",
        "First Beat or Second Beat", "Counter and Exit", "Counter the Counter",
        "First-Round Patience Script",
        # generic
        "Opponent Pattern Scan", "Threat Priority", "Defensive Habit Review",
        "Trigger-Response Builder", "Round Flow Map", "Scoring Map",
        "Momentum Shift Review", "Adversity Reset",
        "Corner Instruction Translation", "Final Tactical Cue Card",
    }
    assert expected <= names
