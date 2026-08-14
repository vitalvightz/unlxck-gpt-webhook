"""Regression tests for two-pass conditioning system-quota fairness.

All energy systems draw from the same shared style/general drill budget. The
previous single-pass fill walked ``preferred_order`` and filled one system's
entire quota before touching the next, so in over-subscribed SPP sessions the
earlier systems (glycolytic, alactic) could drain the budget before aerobic —
which had a non-zero quota, valid candidates and nothing blocking it — ever got
a pick. ``_fill_system_quotas`` now runs two passes: a minimum-representation
pass that gives every system with a positive quota one opportunity to place a
single drill, followed by a remaining-quota pass that uses the existing
preferred-order behaviour.

These tests assert the fairness guarantee without changing any ratio, score,
bank, injury, equipment, late-window or TAPER behaviour.
"""

from __future__ import annotations

from fightcamp import conditioning


def _base_flags(**overrides):
    flags = {
        "phase": "SPP",
        "fatigue": "low",
        "sport": "boxing",
        "fight_format": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "key_goals": ["conditioning"],
        "weaknesses": [],
        "injuries": [],
        "equipment": ["bodyweight"],
        "training_frequency": 3,
        "days_available": 3,
        "days_until_fight": 28,
    }
    flags.update(overrides)
    return flags


def _spp_bank():
    """Bodyweight-only SPP bank with >=2 valid candidates per system."""
    return [
        {
            "name": "Fight Pace Repeat A",
            "phases": ["SPP"],
            "system": "glycolytic",
            "tags": ["conditioning", "glycolytic"],
            "equipment": [],
            "duration": "4 x 2 min, 1 min rest",
            "rpe": 7,
        },
        {
            "name": "Fight Pace Repeat B",
            "phases": ["SPP"],
            "system": "glycolytic",
            "tags": ["conditioning", "glycolytic"],
            "equipment": [],
            "duration": "4 x 90 sec, 1 min rest",
            "rpe": 7,
        },
        {
            "name": "Reactive Shuffle Speed",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["speed", "footwork", "reactive", "low_impact"],
            "equipment": [],
            "duration": "4 x 6 sec, 90 sec rest",
            "notes": "Short full-rest footwork speed. Stop before fatigue.",
            "work_sec": 6,
            "rest_sec": 90,
            "rounds": 4,
            "rpe": 7,
            "lactate_load": "low",
            "impact_cost": "low",
            "movement_cost": "low",
        },
        {
            "name": "Split Step Footwork Pop",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["footwork", "acceleration", "low_impact"],
            "equipment": [],
            "duration": "4 x 5 sec, 90 sec rest",
            "notes": "Sharp technical footwork pop. Stop before fatigue.",
            "work_sec": 5,
            "rest_sec": 90,
            "rounds": 4,
            "rpe": 7,
            "lactate_load": "low",
            "impact_cost": "low",
            "movement_cost": "low",
        },
        {
            "name": "Easy Bike Flush",
            "phases": ["SPP"],
            "system": "aerobic",
            "tags": ["aerobic", "recovery"],
            "equipment": [],
            "duration": "20 min",
            "rpe": 5,
        },
        {
            "name": "Easy Row Flush",
            "phases": ["SPP"],
            "system": "aerobic",
            "tags": ["aerobic", "recovery"],
            "equipment": [],
            "duration": "18 min",
            "rpe": 5,
        },
    ]


def _patch_bank(monkeypatch, bank, *, total_drills):
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: bank)
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_a, **_k: {"conditioning": total_drills})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_a, **_k: {"conditioning": total_drills})
    monkeypatch.setattr(
        conditioning,
        "get_format_weights",
        lambda: {"boxing": {"SPP": {"glycolytic": 1.0, "alactic": 1.0, "aerobic": 1.0}}},
    )


def _generate(flags):
    return conditioning.generate_conditioning_block(flags)


def test_spp_represents_all_three_systems_before_a_second_drill(monkeypatch):
    """1. SPP with non-zero glyco/alactic/aerobic quotas and valid candidates
    can represent all three before any system takes its second drill.

    At total_drills=3 the SPP ratios give glycolytic quota 2, alactic 1 and
    aerobic 1 (demand 4) against a visible cap of 3. The old single-pass fill
    let glycolytic take 2 and alactic take 1, exhausting the budget before
    aerobic — so aerobic (a valid, unblocked system) was dropped. The two-pass
    fill guarantees one aerobic slot first.
    """
    _patch_bank(monkeypatch, _spp_bank(), total_drills=3)

    _output, names, _why, grouped, _missing, _res = _generate(_base_flags())

    # Every system with a positive quota and a valid candidate is represented.
    for system in ("aerobic", "glycolytic", "alactic"):
        assert grouped.get(system), f"expected {system} to be represented, got {sorted(grouped)}"

    # No system took a second drill before all three were represented: with a
    # visible cap of 3 and three represented systems, the raw selection is
    # exactly one per system.
    assert len(names) == 3
    assert len(grouped.get("aerobic", [])) == 1
    assert len(grouped.get("glycolytic", [])) == 1
    assert len(grouped.get("alactic", [])) == 1


def test_system_with_no_valid_candidate_does_not_waste_a_slot(monkeypatch):
    """2. A system with no valid candidate does not reserve/waste a slot.

    With no aerobic drill in the bank, aerobic has a positive quota but zero
    valid candidates. Pass 1 must skip it rather than reserving a slot, so the
    systems that *do* have candidates are still represented — aerobic's absence
    never blocks glycolytic or alactic.
    """
    bank = [d for d in _spp_bank() if d["system"] != "aerobic"]
    _patch_bank(monkeypatch, bank, total_drills=3)

    _output, _names, _why, grouped, _missing, _res = _generate(_base_flags())

    assert not grouped.get("aerobic"), "aerobic has no candidate and must not be represented"
    # The systems with valid candidates are still represented: aerobic's empty
    # quota did not consume or block their slots.
    assert grouped.get("glycolytic")
    assert grouped.get("alactic")


def test_total_selected_never_exceeds_visible_cap(monkeypatch):
    """3. Total selected drills never exceed the existing visible drill cap."""
    # No speed dose -> visible cap == total_drills.
    for total_drills in (2, 3, 4, 5):
        with monkeypatch.context() as m:
            _patch_bank(m, _spp_bank(), total_drills=total_drills)
            _output, names, _why, _grouped, _missing, _res = _generate(_base_flags())
            assert len(names) <= total_drills, (
                f"selected {len(names)} drills exceeds cap {total_drills}"
            )

    # Speed dose lifts the cap by exactly one; selection must still respect it.
    with monkeypatch.context() as m:
        _patch_bank(m, _spp_bank(), total_drills=4)
        _output, names, _why, _grouped, _missing, _res = _generate(
            _base_flags(key_goals=["speed"])
        )
        assert len(names) <= 5


def test_injury_exclusions_still_win_over_fairness(monkeypatch):
    """4. Existing injury exclusions still win: a system whose only candidates
    are injury-excluded is not represented, even though fairness would have
    given it a first slot."""
    bank = [
        {
            "name": "Hamstring Bound Sprint",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["speed", "acceleration"],
            "equipment": [],
            "duration": "4 x 8 sec, 120 sec rest",
            "notes": "Maximal hamstring-loaded sprint bounds.",
        },
        {
            "name": "Fight Pace Repeat A",
            "phases": ["SPP"],
            "system": "glycolytic",
            "tags": ["conditioning", "glycolytic"],
            "equipment": [],
            "duration": "4 x 2 min, 1 min rest",
            "rpe": 7,
        },
        {
            "name": "Easy Bike Flush",
            "phases": ["SPP"],
            "system": "aerobic",
            "tags": ["aerobic", "recovery"],
            "equipment": [],
            "duration": "20 min",
            "rpe": 5,
        },
    ]
    _patch_bank(monkeypatch, bank, total_drills=3)

    _output, names, _why, grouped, _missing, _res = _generate(
        _base_flags(injuries=["hamstring strain"])
    )

    assert "Hamstring Bound Sprint" not in names, "injury-excluded drill must not be selected"


def test_equipment_exclusions_still_win_over_fairness(monkeypatch):
    """4b. Existing equipment exclusions still win: an equipment-gated candidate
    is not selected when the athlete lacks the equipment, even under fairness."""
    bank = [
        {
            "name": "Barbell Complex Grinder",
            "phases": ["SPP"],
            "system": "glycolytic",
            "tags": ["conditioning", "glycolytic"],
            "equipment": ["barbell"],
            "required_equipment": ["barbell"],
            "duration": "4 x 2 min, 1 min rest",
            "rpe": 7,
        },
        {
            "name": "Reactive Shuffle Speed",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["speed", "footwork", "reactive", "low_impact"],
            "equipment": [],
            "duration": "4 x 6 sec, 90 sec rest",
            "work_sec": 6,
            "rest_sec": 90,
            "rounds": 4,
            "rpe": 7,
            "lactate_load": "low",
            "impact_cost": "low",
            "movement_cost": "low",
        },
        {
            "name": "Easy Bike Flush",
            "phases": ["SPP"],
            "system": "aerobic",
            "tags": ["aerobic", "recovery"],
            "equipment": [],
            "duration": "20 min",
            "rpe": 5,
        },
    ]
    _patch_bank(monkeypatch, bank, total_drills=3)

    _output, names, _why, _grouped, _missing, _res = _generate(
        _base_flags(equipment=["bodyweight"])
    )

    assert "Barbell Complex Grinder" not in names, "equipment-gated drill must not be selected"


def test_taper_selection_unchanged(monkeypatch):
    """5. TAPER selection remains unchanged: the two-pass fill lives in the
    non-TAPER branch, so TAPER continues to use its dedicated blended-pick path
    (alactic primary, optional aerobic when a conditioning goal is present)."""
    bank = [
        {
            "name": "Shadowboxing Technical Rhythm",
            "phases": ["TAPER"],
            "system": "alactic",
            "tags": ["sharpness", "skill_refinement", "low_impact", "cns_freshness"],
            "equipment": [],
            "duration": "4 x 30 sec, 90 sec rest",
            "work_sec": 10,
            "rest_sec": 90,
            "rounds": 4,
            "rpe": 5,
            "lactate_load": "low",
            "impact_cost": "low",
            "movement_cost": "low",
        },
        {
            "name": "Easy Bike Flush",
            "phases": ["TAPER"],
            "system": "aerobic",
            "tags": ["aerobic", "recovery", "low_impact", "cns_freshness"],
            "equipment": [],
            "duration": "18 min",
            "rpe": 4,
            "lactate_load": "low",
            "impact_cost": "low",
            "movement_cost": "low",
        },
    ]
    _patch_bank(monkeypatch, bank, total_drills=3)

    # days_until_fight=28 keeps this out of the late-fight bridge windows, so the
    # result is the plain TAPER blended-pick allocation (alactic primary + one
    # aerobic for a conditioning goal). The two-pass quota fill lives in the
    # non-TAPER branch and is never reached here.
    _output, names, _why, grouped, _missing, _res = _generate(
        _base_flags(phase="TAPER", key_goals=["conditioning"], days_until_fight=28)
    )

    # TAPER caps at two drills (alactic + optional aerobic) and never overshoots.
    assert len(names) <= 2
    assert grouped.get("alactic"), "TAPER always keeps its alactic primary"
    assert grouped.get("aerobic"), "TAPER surfaces aerobic for a conditioning goal"
    # Glycolytic stays absent for a low-fatigue non-lactic taper.
    assert not grouped.get("glycolytic")


def test_phase_ratios_still_determine_quotas(monkeypatch):
    """6. Existing phase ratios still determine quotas.

    The refactor does not touch the ``system_quota`` computation (still
    ``round(total_drills * PHASE_SYSTEM_RATIOS[...])``). With enough budget and
    candidates, exactly the systems that the ratios give a positive quota are
    represented — no more, no fewer. (Downstream noise compression collapses a
    system's redundant extra picks, so representation, not raw count, is the
    observable signal.)
    """
    from fightcamp.config import PHASE_SYSTEM_RATIOS

    total_drills = 4
    expected_quota = {
        k: max(1 if v > 0 else 0, round(total_drills * v))
        for k, v in PHASE_SYSTEM_RATIOS["SPP"].items()
    }
    # SPP ratios 0.5/0.3/0.2 at total_drills=4 -> glyco 2, alactic 1, aerobic 1.
    assert expected_quota == {"glycolytic": 2, "alactic": 1, "aerobic": 1}
    positive_quota_systems = {s for s, q in expected_quota.items() if q > 0}

    _patch_bank(monkeypatch, _spp_bank(), total_drills=total_drills)
    _output, _names, _why, grouped, _missing, _res = _generate(_base_flags())

    represented = {
        s for s in ("aerobic", "glycolytic", "alactic") if grouped.get(s)
    }
    assert represented == positive_quota_systems
