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


def test_footwork_uses_dedicated_channel_not_aerobic_dose_accounting():
    # Blocker 2: technical footwork must be grouped/resolved under its own
    # channel, never counted or titled as an aerobic energy-system dose.
    flags = _flags(phase="TAPER", days_until_fight=18)
    markdown, names, entries, grouped, *_rest = conditioning.generate_conditioning_block(flags)
    inserted = FOOTWORK_NAMES.intersection(names)
    assert inserted, "expected footwork to surface in taper"

    # It lives under the dedicated technical_footwork group, never under an
    # energy system (aerobic/glycolytic/alactic).
    tf_group = {d.get("name") for d in grouped.get("technical_footwork", [])}
    assert inserted.issubset(tf_group), (inserted, tf_group)
    for system in ("aerobic", "glycolytic", "alactic"):
        system_names = {d.get("name") for d in grouped.get(system, [])}
        assert FOOTWORK_NAMES.isdisjoint(system_names), (system, system_names)

    # why_log entries for footwork carry the technical_footwork system, not aerobic.
    for entry in entries:
        if entry.get("name") in FOOTWORK_NAMES:
            assert entry.get("system") == "technical_footwork", entry

    # Renders under its own label, never as "Aerobic support" for the footwork drill.
    assert "Technical Footwork" in markdown


# --- Proof 3: injury exclusions still gate it -------------------------------

def test_selector_omits_footwork_for_real_severe_lower_limb_injury():
    flags = _flags(injuries=["ruptured achilles"])
    assert conditioning.select_technical_footwork_drill(
        flags, set(), flags["injuries"]
    ) is None

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


# --- Proof 4b: window-blocked top pick must not strand the insert -----------
# Regression for the D-4 selection bug: the selector ranks candidates and the
# insert applies the per-drill late_windows gate. If the top-ranked candidate is
# out of its late window, the insert must fall through to the next eligible
# candidate instead of inserting nothing.

_FOOT_BANK = {d["name"]: d for d in conditioning.get_technical_footwork_bank()}


def _late_windows(name: str) -> set[str]:
    return {str(w).strip().lower() for w in _FOOT_BANK[name].get("late_windows", [])}


def test_d4_top_ranked_candidate_is_window_blocked_but_insert_still_fills():
    # The full ranked candidate list exists and its top pick is genuinely out of
    # the D-4 window, yet a window-eligible footwork drill is still inserted.
    flags = _flags(phase="TAPER", days_until_fight=4)
    ranked = conditioning.select_technical_footwork_candidates(flags, set(), [])
    assert ranked, "expected footwork candidates at D-4"
    assert "d4_to_d2" not in _late_windows(ranked[0]["name"]), ranked[0]["name"]

    _markdown, names, *_rest = conditioning.generate_conditioning_block(flags)
    inserted = FOOTWORK_NAMES.intersection(names)
    assert inserted, "footwork was stranded by a window-blocked top-ranked pick"
    # Whatever was inserted must actually be eligible in the D-4 window.
    for name in inserted:
        assert "d4_to_d2" in _late_windows(name), (name, sorted(_late_windows(name)))


def test_d4_severe_knee_injury_omits_technical_footwork():
    flags = _flags(phase="TAPER", days_until_fight=4, injuries=["torn acl in my knee"])
    _markdown, names, *_rest = conditioning.generate_conditioning_block(flags)
    assert FOOTWORK_NAMES.isdisjoint(names), names


def test_d4_full_generator_keeps_technical_footwork_sport_specific_and_dedicated():
    cases = {
        "boxing": {"boxing"},
        "muay_thai": {"muay_thai", "kickboxing"},
        "mma": {"mma"},
    }
    for sport, accepted_tags in cases.items():
        flags = _flags(
            phase="TAPER", days_until_fight=4, sport=sport, fight_format=sport,
            style_tactical=[], style_technical=[sport],
        )
        markdown, names, entries, grouped, *_rest = conditioning.generate_conditioning_block(flags)
        inserted = FOOTWORK_NAMES.intersection(names)
        assert inserted, (sport, names)
        assert "Technical Footwork" in markdown
        assert inserted == {d["name"] for d in grouped.get("technical_footwork", [])}
        for name in inserted:
            drill = _FOOT_BANK[name]
            assert accepted_tags & {str(t).lower() for t in drill.get("tags", [])}
            assert "d4_to_d2" in _late_windows(name)
        for system in ("aerobic", "glycolytic", "alactic"):
            assert inserted.isdisjoint({d["name"] for d in grouped.get(system, [])})
        for entry in entries:
            if entry.get("name") in inserted:
                assert entry.get("system") == "technical_footwork"
                assert "technical_footwork_guarantee" in entry["reasons"]["reason_codes"]


def test_d4_without_a_sport_appropriate_candidate_omits_technical_footwork():
    flags = _flags(
        phase="TAPER", days_until_fight=4, sport="karate", fight_format="karate",
        style_tactical=[], style_technical=["karate"],
    )
    _markdown, names, *_rest = conditioning.generate_conditioning_block(flags)
    assert FOOTWORK_NAMES.isdisjoint(names), names


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


# --- Proof 7: wrestling & BJJ are served without cross-sport leakage ---------
# The technical footwork bank is striking/MMA-oriented, but wrestling and BJJ are
# supported combat sports (coordination_support_library.SUPPORTED_SPORTS). They
# must not be silently made footwork-unavailable, nor broadly mapped onto every
# MMA drill: sport is resolved through the shared canonical ontology and each
# grappling sport is gated to the specific transition drills a per-drill movement
# audit found genuinely appropriate. Deliberate omission (rather than another
# sport's footwork) is correct where a sport has no eligible drill in a window.

def _drills_tagged(tag: str) -> set[str]:
    return {n for n, d in _FOOT_BANK.items() if tag in {str(t).lower() for t in d.get("tags", [])}}


_WRESTLING_DRILLS = _drills_tagged("wrestling")
_BJJ_DRILLS = _drills_tagged("bjj")
# Drills that belong to a pure striking sport and must never surface for a
# wrestling/BJJ athlete.
_PURE_STRIKING_DRILLS = _drills_tagged("boxing") | _drills_tagged("kickboxing") | _drills_tagged("muay_thai")


def _sport_flags(sport: str, **over) -> dict:
    return _flags(sport=sport, fight_format=sport, style_tactical=[], style_technical=[sport], **over)


def _selected_names(sport: str, phase: str) -> set[str]:
    return {
        c["name"]
        for c in conditioning.select_technical_footwork_candidates(
            _sport_flags(sport, phase=phase), set(), []
        )
    }


def test_wrestling_selector_surfaces_only_wrestling_appropriate_drills():
    # Served across the phases where genuine wrestling movements exist (sprawl,
    # level change, scramble recovery, technical stand-up).
    for phase in ("GPP", "SPP"):
        surfaced = _selected_names("wrestling", phase)
        assert surfaced, phase  # not silently unavailable
        assert surfaced <= _WRESTLING_DRILLS, (phase, surfaced)
        assert surfaced.isdisjoint(_PURE_STRIKING_DRILLS), (phase, surfaced)
        # Cage ring-craft is a striking/MMA spatial skill, deliberately left
        # MMA-only, so wrestling is never blanket-mapped onto every MMA drill.
        assert "Cage Circle and Cut-Off" not in surfaced, phase
    assert _selected_names("wrestling", "SPP") == {
        "Level-Change Feint to Angle",
        "Scramble-to-Strike Rebase",
        "Sprawl Exit to Ring Angle",
        "Submission Hunter Stand-Up Reset",
    }


def test_bjj_selector_surfaces_only_the_genuine_standup_drill():
    # BJJ's only genuinely-appropriate standing pattern here is the technical
    # stand-up to base; the strike-framed transitions are not BJJ footwork.
    assert _BJJ_DRILLS == {"Submission Hunter Stand-Up Reset"}
    for phase in ("GPP", "SPP"):
        surfaced = _selected_names("bjj", phase)
        assert surfaced, phase
        assert surfaced <= _BJJ_DRILLS, (phase, surfaced)
        assert surfaced.isdisjoint(_PURE_STRIKING_DRILLS), (phase, surfaced)


def test_mma_selector_keeps_full_grappling_transition_set():
    # MMA is unchanged by the wrestling/BJJ gating: it still gets every MMA drill
    # including the cage ring-craft drill wrestling deliberately omits.
    surfaced = _selected_names("mma", "SPP")
    assert surfaced, surfaced
    assert all("mma" in {t.lower() for t in _FOOT_BANK[n]["tags"]} for n in surfaced)
    assert "Cage Circle and Cut-Off" in surfaced
    assert surfaced.isdisjoint(_PURE_STRIKING_DRILLS)


def test_grapplers_deliberately_omit_footwork_in_deep_taper():
    # No wrestling/BJJ drill claims TAPER eligibility, so omission is the correct,
    # deliberate outcome there — never a fall-through to a striking drill.
    for sport in ("wrestling", "bjj"):
        assert _selected_names(sport, "TAPER") == set(), sport


def test_no_striking_footwork_ever_leaks_to_grapplers():
    for sport in ("wrestling", "bjj"):
        for phase in ("GPP", "SPP", "TAPER"):
            assert _selected_names(sport, phase).isdisjoint(_PURE_STRIKING_DRILLS), (sport, phase)


def test_canonical_sport_aliases_resolve_for_technical_footwork():
    # Reuse of the shared sport ontology means aliases resolve to the same
    # canonical sport rather than filtering to an unknown literal tag.
    def cands(sport):
        return sorted(_selected_names(sport, "SPP"))

    assert cands("wrestler") == cands("wrestling")
    assert cands("jiu_jitsu") == cands("bjj") == cands("brazilian_jiu_jitsu")
    assert cands("muaythai") == cands("muay_thai")


def test_generator_serves_wrestling_and_bjj_with_sport_appropriate_footwork():
    # Full-generator proof (dedicated channel, guarantee, accounting separation)
    # that wrestling/BJJ footwork-focused athletes are actually served.
    for sport, allowed in (("wrestling", _WRESTLING_DRILLS), ("bjj", _BJJ_DRILLS)):
        flags = _sport_flags(sport, phase="SPP", days_until_fight=40)
        markdown, names, entries, grouped, *_rest = conditioning.generate_conditioning_block(flags)
        inserted = FOOTWORK_NAMES.intersection(names)
        assert inserted, (sport, names)  # served, not silently omitted
        assert inserted <= allowed, (sport, inserted)
        assert inserted.isdisjoint(_PURE_STRIKING_DRILLS), (sport, inserted)
        assert "Technical Footwork" in markdown
        assert inserted == {d["name"] for d in grouped.get("technical_footwork", [])}
        for system in ("aerobic", "glycolytic", "alactic"):
            assert inserted.isdisjoint({d["name"] for d in grouped.get(system, [])})
        for entry in entries:
            if entry.get("name") in inserted:
                assert entry.get("system") == "technical_footwork"
                assert "technical_footwork_guarantee" in entry["reasons"]["reason_codes"]


def test_generator_omits_footwork_for_grapplers_in_deep_taper():
    for sport in ("wrestling", "bjj"):
        for days in (18, 4):
            flags = _sport_flags(sport, phase="TAPER", days_until_fight=days)
            _markdown, names, *_rest = conditioning.generate_conditioning_block(flags)
            assert FOOTWORK_NAMES.isdisjoint(names), (sport, days, names)
