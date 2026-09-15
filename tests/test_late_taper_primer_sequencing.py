"""Late-tail Style Taper primer sequencing: unused equivalents before repetition.

Production regression (boxing pressure fighter, D-16 at generation, power +
skill refinement, footwork weakness, low fatigue, active cut) put the same
primer on D-12, D-7 and D-5. The bank held several equally appropriate, equally
safe, equally cheap alternatives; the dated allocator simply recomputed the same
deterministic winner each day because Style Taper candidates are exempt from
``consumed_slot_ids`` and nothing remembered what the tail had already used.

These fixtures are self-contained: governance-valid Style Taper entries built in
the test, serialized through the real Stage 2 handoff. No production IDs, no
Supabase, no live bank dependency.
"""
import pytest

from fightcamp.stage2_payload import (
    _build_late_fight_allowed_exercises_by_day,
    _build_late_tail_candidates,
)
from fightcamp.style_taper_governance import (
    assert_style_taper_entry,
    style_taper_primer_family,
)


BOXING_PRESSURE_FIGHTER = {
    "sport": "boxing",
    "fight_format": "boxing",
    "tactical_style": "pressure_fighter",
    "key_goals": ["power", "skill_refinement"],
    "weaknesses": ["footwork"],
    "fatigue": "low",
    "injuries": [],
    "restrictions": [],
    "equipment": ["bodyweight", "partner", "pads"],
    "weight_cut_risk": True,
    # D-13 -> D-5 all resolve to one phase unless a test says otherwise.
    "phase_weeks": {"GPP": 0, "SPP": 13, "TAPER": 0, "days": {"GPP": 6, "SPP": 13, "TAPER": 0}},
}


def _entry(
    name,
    *,
    primer_family="pure_neural",
    tags=("boxing", "pressure_fighter", "speed", "skill_refinement", "footwork"),
    late_windows=("d13_to_d8", "d7", "d6_to_d5"),
    equipment=("bodyweight",),
    contact_level="none",
    rpe_max=4,
    rounds=2,
    work_sec=5,
    rest_sec=120,
    total_minutes=4.2,
):
    """A legal Style Taper bank entry. Asserted against live bank governance."""
    entry = {
        "name": name,
        "description": f"{name} rehearsal primer.",
        "equipment": list(equipment),
        "phases": ["SPP", "TAPER"],
        "system": "alactic",
        "modality": "style sharpness",
        "duration": f"{rounds}x{work_sec}s with {rest_sec}s rest",
        "intensity": "low volume, fast crisp intent",
        "tags": list(tags),
        "mechanical_risk_tags": ["mech_acceleration"],
        "work_sec": work_sec,
        "rest_sec": rest_sec,
        "rounds": rounds,
        "total_minutes": total_minutes,
        "rpe_max": rpe_max,
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
        "execution_intent": "fast_crisp",
        "contact_level": contact_level,
        "late_windows": list(late_windows),
        "primer_family": primer_family,
        "_schema_source": "data/style_taper_conditioning.json",
    }
    assert_style_taper_entry(entry)
    return entry


def _reservoir_candidate(entry, *, bank_order, style_hits=1, goal_hits=1, weakness_hits=0):
    reasons = {
        "style_hits": style_hits,
        "goal_hits": goal_hits,
        "weakness_hits": weakness_hits,
        "final_score": float(1 + style_hits + goal_hits + weakness_hits),
        "reason_codes": ["style_taper_priority"],
        "penalty_codes": [],
    }
    return {
        "drill": {**entry, "bank_order": bank_order},
        "score": reasons["final_score"],
        "reasons": reasons,
        "explanation": "style taper primer",
        "score_evidence": {},
        "metadata": {},
    }


def _pools(candidates, *, phases=("SPP", "TAPER"), extra_conditioning_slots=()):
    """Stage 1 -> Stage 2 handoff for the given reservoir candidates."""
    block = {"candidate_reservoir": {"alactic": list(candidates)}}
    return {
        phase: {
            "strength_slots": [],
            "conditioning_slots": list(extra_conditioning_slots),
            "late_tail_candidates": _build_late_tail_candidates(block, phase),
            "rehab_slots": [],
        }
        for phase in phases
    }


def _roles(*days, role_key="neural_primer_day"):
    return [
        {
            "scheduled_countdown_label": f"D-{day}",
            "role_key": role_key if isinstance(role_key, str) else role_key[index],
            "category": "conditioning",
            "late_fight_tail_owned": True,
        }
        for index, day in enumerate(days)
    ]


def _allocate(pools, roles, athlete=None):
    allowed, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={
            "visible_session_sequence": roles,
            "athlete_model": {**BOXING_PRESSURE_FIGHTER, **(athlete or {})},
        },
        candidate_pools=pools,
    )
    return allowed, assignments


def _sequence(pools, roles, athlete=None):
    _allowed, assignments = _allocate(pools, roles, athlete)
    sequence = []
    for role in roles:
        day = role["scheduled_countdown_label"]
        names = [item["name"] for item in assignments.get(day, [])]
        assert len(names) == 1, f"{day} expected exactly one primer, got {names}"
        sequence.append(names[0])
    return sequence


# --- Test 1: equal qualified alternatives are used before exact reuse --------


def _three_equal_candidates():
    return [
        _reservoir_candidate(_entry("Primer A", primer_family="pure_neural"), bank_order=1),
        _reservoir_candidate(_entry("Primer B", primer_family="pure_neural"), bank_order=2),
        _reservoir_candidate(_entry("Primer C", primer_family="pure_neural"), bank_order=3),
    ]


def test_equal_alternatives_are_used_before_any_exact_reuse():
    sequence = _sequence(_pools(_three_equal_candidates()), _roles(12, 7, 5))

    assert sequence == ["Primer A", "Primer B", "Primer C"]


# --- Test 2: two candidates, three exposures --------------------------------


def test_two_candidates_across_three_exposures_exhaust_both_first():
    candidates = [
        _reservoir_candidate(_entry("Primer A"), bank_order=1),
        _reservoir_candidate(_entry("Primer B"), bank_order=2),
    ]

    sequence = _sequence(_pools(candidates), _roles(12, 7, 5))

    assert sequence == ["Primer A", "Primer B", "Primer A"]


# --- Test 3: only one qualified candidate -----------------------------------


def test_single_qualified_candidate_repeats_without_losing_a_role():
    candidates = [_reservoir_candidate(_entry("Primer A"), bank_order=1)]

    sequence = _sequence(_pools(candidates), _roles(12, 7, 5))

    assert sequence == ["Primer A", "Primer A", "Primer A"]


# --- Test 4: a materially superior candidate may repeat ---------------------


def test_materially_superior_primer_repeats_over_a_worse_unused_option():
    candidates = [
        _reservoir_candidate(
            _entry("Superior Primer"), bank_order=1,
            style_hits=1, goal_hits=2, weakness_hits=1,
        ),
        # Matches neither the athlete's tactical style nor any declared target.
        _reservoir_candidate(
            _entry("Generic Primer", tags=("boxing", "pressure_fighter", "sharpness")),
            bank_order=2, style_hits=0, goal_hits=0, weakness_hits=0,
        ),
    ]

    sequence = _sequence(_pools(candidates), _roles(12, 7, 5))

    assert sequence == ["Superior Primer"] * 3


# --- Test 5: an unsafe unused candidate never beats a safe repeat -----------


@pytest.mark.parametrize(
    "unsafe_kwargs",
    [
        pytest.param({"late_windows": ("d13_to_d8",)}, id="outside_d6_to_d5_window"),
        pytest.param({"contact_level": "cooperative", "rpe_max": 5}, id="higher_contact_cost"),
        pytest.param({"equipment": ("assault_bike",)}, id="equipment_not_available"),
    ],
)
def test_unused_but_unsafe_or_costlier_candidate_never_beats_a_safe_repeat(unsafe_kwargs):
    candidates = [
        _reservoir_candidate(_entry("Primer A"), bank_order=1),
        _reservoir_candidate(_entry("Primer B", **unsafe_kwargs), bank_order=2),
    ]

    # D-5 is the exposure under test: A has already been used twice by then.
    sequence = _sequence(_pools(candidates), _roles(12, 5))

    assert sequence[-1] == "Primer A"


def test_injury_excluded_unused_candidate_never_reaches_the_tail():
    """An unused option Stage 1's injury gate dropped is simply not a candidate."""
    candidates = [_reservoir_candidate(_entry("Primer A"), bank_order=1)]

    sequence = _sequence(_pools(candidates), _roles(12, 7))

    assert sequence == ["Primer A", "Primer A"]


# --- Test 6: primer families rotate inside equivalent choices ---------------


def test_primer_families_rotate_inside_equivalent_choices():
    candidates = [
        _reservoir_candidate(_entry("Pure Primer", primer_family="pure_neural"), bank_order=1),
        _reservoir_candidate(_entry("Technical Primer", primer_family="technical_neural"), bank_order=2),
        _reservoir_candidate(_entry("Tactical Primer", primer_family="tactical_neural"), bank_order=3),
    ]
    pools = _pools(candidates)
    family_by_name = {
        slot["selected"]["name"]: style_taper_primer_family(slot["selected"]["selection_metadata"])
        for slot in pools["SPP"]["late_tail_candidates"]
    }

    sequence = _sequence(pools, _roles(12, 7, 5))

    assert len(set(sequence)) == 3
    assert [family_by_name[name] for name in sequence] == [
        "pure_neural", "technical_neural", "tactical_neural"
    ]


# --- Test 7: family diversity never overrides superior relevance ------------


def test_unused_family_does_not_displace_a_materially_more_relevant_primer():
    candidates = [
        _reservoir_candidate(
            _entry("Relevant Pure Primer", primer_family="pure_neural"), bank_order=1,
            style_hits=1, goal_hits=2, weakness_hits=1,
        ),
        _reservoir_candidate(
            _entry(
                "Off-Target Tactical Primer",
                primer_family="tactical_neural",
                tags=("boxing", "pressure_fighter", "sharpness"),
            ),
            bank_order=2, style_hits=0, goal_hits=0, weakness_hits=0,
        ),
    ]

    sequence = _sequence(_pools(candidates), _roles(12, 7))

    assert sequence == ["Relevant Pure Primer", "Relevant Pure Primer"]


# --- Test 8: usage survives the SPP -> TAPER boundary ----------------------


def test_usage_history_survives_the_spp_to_taper_phase_boundary():
    # D-12 is owned by SPP; D-7 and D-5 fall inside the 8-day TAPER allocation,
    # so the tail is allocated in two phase-scoped batches.
    athlete = {
        "phase_weeks": {"GPP": 0, "SPP": 13, "TAPER": 1,
                        "days": {"GPP": 6, "SPP": 13, "TAPER": 8}},
    }
    roles = _roles(12, 7, 5)
    _allowed, assignments = _allocate(_pools(_three_equal_candidates()), roles, athlete)

    phases = {day: items[0]["phase"] for day, items in assignments.items()}
    assert phases == {"D-12": "SPP", "D-7": "TAPER", "D-5": "TAPER"}
    assert [assignments[f"D-{day}"][0]["name"] for day in (12, 7, 5)] == [
        "Primer A", "Primer B", "Primer C"
    ]


def test_usage_history_survives_a_change_of_late_tail_role_key():
    roles = _roles(12, 7, 5, role_key=[
        "neural_primer_day", "alactic_sharpness_day", "strength_touch_day",
    ])

    sequence = _sequence(_pools(_three_equal_candidates()), roles)

    assert sequence == ["Primer A", "Primer B", "Primer C"]


# --- Test 9: the Style Taper reuse fallback remains -------------------------


def test_reuse_fallback_keeps_filling_days_once_every_option_is_used():
    candidates = [
        _reservoir_candidate(_entry("Primer A"), bank_order=1),
        _reservoir_candidate(_entry("Primer B"), bank_order=2),
    ]

    sequence = _sequence(_pools(candidates), _roles(12, 10, 7, 5))

    assert sequence == ["Primer A", "Primer B", "Primer A", "Primer B"]
    assert all(sequence)


# --- Test 10: non-Style-Taper consumption semantics unchanged ---------------


def _conditioning_slot(name, slot_id):
    return {
        "slot_id": slot_id,
        "role": "alactic",
        "selected": {
            "name": name,
            "source": "conditioning_bank",
            "system": "alactic",
            "movement_patterns": ["alactic", "sharpness"],
            "prescription": "3x10s with 90s rest",
            "fulfillment_authority": True,
            "support_only": False,
            "meaningful_stress": True,
            "selection_metadata": {
                "name": name,
                "system": "alactic",
                "phases": ["SPP", "TAPER"],
                "late_windows": ["d13_to_d8", "d7", "d6_to_d5"],
                "tags": ["boxing", "alactic"],
            },
        },
        "alternates": [],
    }


def test_non_style_taper_candidates_are_still_consumed_once():
    pools = _pools(
        [],
        extra_conditioning_slots=[
            _conditioning_slot("Generic Alactic A", "spp_alactic_a"),
            _conditioning_slot("Generic Alactic B", "spp_alactic_b"),
        ],
    )

    sequence = _sequence(pools, _roles(12, 7, role_key="alactic_sharpness_day"))

    assert sequence == ["Generic Alactic A", "Generic Alactic B"]


def test_single_non_style_taper_candidate_is_not_reused_across_days():
    pools = _pools(
        [], extra_conditioning_slots=[_conditioning_slot("Generic Alactic A", "spp_alactic_a")]
    )
    roles = _roles(12, 7, role_key="alactic_sharpness_day")

    _allowed, assignments = _allocate(pools, roles)

    assert [item["name"] for item in assignments["D-12"]] == ["Generic Alactic A"]
    assert assignments["D-7"] == []


# --- Test 11: support-only fulfillment semantics unchanged -----------------


def test_varied_primers_stay_support_only_and_do_not_discharge_meaningful_work():
    roles = _roles(12, 7, 5)
    _allowed, assignments = _allocate(_pools(_three_equal_candidates()), roles)

    assert [role.get("support_only_fill") for role in roles] == [True, True, True]
    assert [role.get("meaningful_stress_fulfilled") for role in roles] == [False, False, False]
    for role in roles:
        for assignment in assignments[role["scheduled_countdown_label"]]:
            assert assignment["support_only"] is True
            assert assignment["meaningful_stress"] is False
            assert assignment["fulfillment_authority"] is False


# --- Test 12: determinism --------------------------------------------------


def test_sequence_is_identical_across_repeated_runs():
    runs = {
        tuple(_sequence(_pools(_three_equal_candidates()), _roles(12, 10, 7, 5)))
        for _ in range(5)
    }

    assert len(runs) == 1
    assert runs == {("Primer A", "Primer B", "Primer C", "Primer A")}
