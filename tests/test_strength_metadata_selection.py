from __future__ import annotations

import json
from pathlib import Path

from fightcamp import strength
from fightcamp.late_selector_windows import D1, D4_TO_D2, D7, D13_TO_D8


def _flags(**overrides) -> dict:
    base = {
        "phase": "TAPER",
        "fatigue": "low",
        "fight_format": "boxing",
        "sport": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "equipment": ["bodyweight", "bands"],
        "training_days": ["Mon"],
        "training_frequency": 1,
        "days_available": 1,
        "key_goals": ["power"],
        "weaknesses": [],
        "injuries": [],
        "days_until_fight": 3,
    }
    return {**base, **overrides}


def _selected_names(result: dict) -> list[str]:
    return [entry["name"] for entry in result["why_log"]]


def _exercise_bank_items() -> list[dict]:
    return json.loads(Path("data/exercise_bank.json").read_text(encoding="utf-8"))


def _exercise_named(name: str) -> dict:
    for item in _exercise_bank_items():
        if item["name"] == name:
            return item
    raise AssertionError(f"Missing exercise bank item: {name}")


def _quality_passthrough(exercise, phase=None):
    return 0.0, strength.classify_strength_item(exercise)


def _patch_minimal_strength_runtime(monkeypatch, exercise_bank: list[dict], score_map: dict[str, float]) -> None:
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "strength_quality_adjustment", _quality_passthrough)
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]], "reason_codes": []},
        ),
    )


def test_late_strength_selection_prefers_explicit_low_cost_metadata(monkeypatch):
    exercise_bank = [
        {
            "name": "Dense Jump Primer",
            "phases": ["TAPER"],
            "method": "power",
            "movement": "lunge",
            "type": "unilateral",
            "tags": ["dense_jump", "explosive", "mech_landing_impact", "mech_lower_lunge"],
            "equipment": "bodyweight",
            "impact_cost": "high",
            "eccentric_cost": "high",
            "landing_cost": "high",
            "soreness_risk": "high",
            "cns_load": "high",
        },
        {
            "name": "Shadow Snap-Down Primer",
            "phases": ["TAPER"],
            "method": "power",
            "movement": "core",
            "type": "bilateral",
            "tags": ["shadow_snap", "explosive", "speed", "mech_ballistic"],
            "equipment": "bodyweight",
            "late_windows": [D4_TO_D2],
            "impact_cost": "low",
            "eccentric_cost": "low",
            "landing_cost": "none",
            "soreness_risk": "low",
            "cns_load": "low",
            "low_impact": True,
            "low_eccentric": True,
            "cns_freshness": True,
        },
    ]
    _patch_minimal_strength_runtime(monkeypatch, exercise_bank, {"dense_jump": 10.0, "shadow_snap": 9.5})

    result = strength.generate_strength_block(flags=_flags())

    assert _selected_names(result) == ["Shadow Snap-Down Primer"]
    selected_reasons = result["why_log"][0]["reasons"]["reason_codes"]
    assert "late_strength_boost_low_soreness" in selected_reasons
    assert "late_strength_boost_low_impact" in selected_reasons
    assert "late_strength_boost_low_eccentric" in selected_reasons


def test_active_weight_cut_blocks_explicitly_incompatible_strength_item():
    result = strength._evaluate_strength_late_window(
        {
            "name": "Heavy Trap Bar Cluster",
            "phases": ["TAPER"],
            "movement": "hinge",
            "tags": ["mech_lower_hip_hinge", "mech_cns_high"],
            "equipment": "trap_bar",
            "cut_buckets_allowed": ["none", "low"],
            "impact_cost": "low",
            "eccentric_cost": "high",
            "landing_cost": "none",
            "soreness_risk": "high",
            "cns_load": "high",
        },
        window=D7,
        cut_bucket="high",
    )

    assert result["blocked"] is True
    assert "late_strength_block_cut_bucket_mismatch" in result["block_codes"]
    assert "late_strength_penalty_cut_pressure_high_cost_metadata" in result["reason_codes"]


def test_d7_and_under_blocks_non_rehab_band_strength_work():
    # Loaded, non-rehab band strength work (no late-safe primer markers) is locked
    # out in the final week. Low-dose neural primers are exempt and covered by the
    # late-camp selector tests.
    result = strength._evaluate_strength_late_window(
        {
            "name": "Band-Resisted Heavy Row",
            "phases": ["TAPER"],
            "movement": "horizontal_pull",
            "method": "strength",
            "tags": ["strength", "loaded", "compound"],
            "equipment": "bands",
        },
        window=D7,
        cut_bucket="none",
    )

    assert result["blocked"] is True
    assert "late_strength_block_band_work_lockout" in result["block_codes"]


def test_high_fatigue_athlete_avoids_high_cns_load(monkeypatch):
    exercise_bank = [
        {
            "name": "High CNS Med-Ball Blast",
            "phases": ["SPP"],
            "method": "power",
            "movement": "core",
            "type": "bilateral",
            "tags": ["high_cns", "explosive", "mech_ballistic", "mech_cns_high"],
            "equipment": "bodyweight",
            "cns_load": "high",
            "soreness_risk": "low",
            "impact_cost": "low",
            "eccentric_cost": "low",
            "landing_cost": "none",
        },
        {
            "name": "Low CNS Pallof Hold",
            "phases": ["SPP"],
            "method": "strength",
            "movement": "core",
            "type": "isometric",
            "tags": ["low_cns", "isometric", "anti_rotation", "mech_trunk_stability"],
            "equipment": "bands",
            "cns_load": "low",
            "soreness_risk": "low",
            "impact_cost": "low",
            "eccentric_cost": "low",
            "landing_cost": "none",
        },
    ]
    _patch_minimal_strength_runtime(monkeypatch, exercise_bank, {"high_cns": 10.0, "low_cns": 9.8})

    result = strength.generate_strength_block(flags=_flags(phase="SPP", fatigue="high", days_until_fight=21))

    assert _selected_names(result) == ["Low CNS Pallof Hold"]
    blocked_reasons = result["candidate_reservoir"]["core"][1]["score_evidence"]["reason_codes"]
    assert "strength_penalty_high_fatigue_high_cns_load" in blocked_reasons


def test_explicit_low_impact_metadata_overrides_landing_tag_heuristic():
    result = strength._evaluate_strength_late_window(
        {
            "name": "Low-Amplitude Ankle Pop",
            "phases": ["TAPER"],
            "movement": "core",
            "tags": ["explosive", "mech_landing_impact"],
            "equipment": "bodyweight",
            "impact_cost": "low",
            "eccentric_cost": "low",
            "landing_cost": "low",
            "soreness_risk": "low",
            "cns_load": "low",
            "low_impact": True,
            "low_eccentric": True,
        },
        window=D4_TO_D2,
        cut_bucket="none",
    )

    assert result["blocked"] is False
    assert "late_strength_block_trap_bar_jump" not in result["block_codes"]
    assert "late_strength_boost_low_impact" in result["reason_codes"]


def test_strength_bank_duplicate_names_are_resolved():
    items = _exercise_bank_items()
    counts: dict[str, int] = {}
    for item in items:
        key = item["name"].strip().casefold()
        counts[key] = counts.get(key, 0) + 1

    assert {name: count for name, count in counts.items() if count > 1} == {}


def test_strength_bank_removes_taper_from_developmental_or_high_cost_items():
    expected_phases = {
        # NOTE: "Hang Power Clean" is referenced by the late-fight validator and
        # bank_inferred_tags but is not present in exercise_bank.json, so it is
        # not asserted here. Track separately whether it should be added.
        "Slow-Lowered Pull-Up": ["GPP", "SPP"],
        "Med Ball Scoop Toss": ["SPP"],
        "Anti-Rotation Med Ball Slam": ["SPP"],
        "Nordic Hamstring Curl": ["GPP"],
        "Landmine Press": ["GPP", "SPP"],
        "Band-Resisted Push Press": ["SPP"],
        "Weighted Hanging Leg Raise": ["SPP"],
        "Medicine-Ball Chest Toss": ["SPP"],
        "Neck Harness Flexion": ["GPP"],
        "Tabata Sprints (Treadmill/Row)": ["SPP"],
        "Sprawl-to-Burpee": ["SPP"],
        "Neck Harness Lateral Flexion": ["GPP"],
        "3-Minute Heavy Bag Interval": ["SPP"],
    }

    for name, phases in expected_phases.items():
        item = _exercise_named(name)
        assert "TAPER" not in item["phases"]
        assert item["phases"] == phases


def test_loaded_strength_touches_are_blocked_from_tight_late_windows():
    for name in (
        "Isometric Mid-Thigh Pull",
        "Trap-Bar Pin Pull Isometric",
        "Overcoming Split-Squat Isometric",
        "Landmine Split-Stance Punch Press",
    ):
        item = _exercise_named(name)

        d7_result = strength._evaluate_strength_late_window(item, window=D7)
        d1_result = strength._evaluate_strength_late_window(item, window=D1)

        assert d7_result["blocked"] is True
        assert d1_result["blocked"] is True
        assert "late_strength_block_window_mismatch" in d7_result["block_codes"]
        assert "late_strength_block_window_mismatch" in d1_result["block_codes"]


def test_d21_only_loaded_strength_touches_do_not_leak_to_d13():
    for name in ("Trap Bar Deadlift", "Sandbag Shouldering"):
        item = _exercise_named(name)

        d13_result = strength._evaluate_strength_late_window(item, window=D13_TO_D8)

        assert item["late_windows"] == ["d21_to_d14"]
        assert d13_result["blocked"] is True
        assert "late_strength_block_familiarity_required_late" in d13_result["block_codes"]


def test_d1_explicit_taper_windows_exclude_loaded_sprint_jump_and_eccentric_drills():
    risky_equipment = {"barbell", "trap_bar"}
    risky_tags = {"eccentric", "mech_lower_jump", "mech_landing_impact"}
    risky_d1_names = {
        "staggered-stance medicine-ball punch throw",
        "light heavy-bag technical tempo",
        "scapular pull-up hold",
    }

    for item in _exercise_bank_items():
        if "TAPER" not in item.get("phases", []):
            continue
        if "d1" not in {str(window).lower() for window in item.get("late_windows", [])}:
            continue

        equipment = set(str(item.get("equipment", "")).split(","))
        tags = set(item.get("tags", []))
        name = item["name"].lower()

        assert not equipment & risky_equipment
        assert item.get("movement") != "olympic"
        assert not tags & risky_tags
        assert "sprint start" not in name
        assert "jump" not in name
        assert name not in risky_d1_names


def test_good_taper_readiness_options_remain_available():
    expected_windows = {
        "Band-Resisted Jab-Cross Primer": {"d21_to_d14", "d13_to_d8"},
        "Technical Shadowboxing Tempo": {"d1", "d4_to_d2"},
        "Band Row Speed Focus": {"d4_to_d2"},
        "Mobility Reset Flow": {"d1", "d4_to_d2"},
        "Band Face Pull": {"d4_to_d2"},
        "Staggered-Stance Medicine-Ball Punch Throw": {"d4_to_d2"},
        "Scapular Pull-Up Hold": {"d4_to_d2"},
        "Light Heavy-Bag Technical Tempo": {"d4_to_d2"},
    }
    full_cut_access = {
        "Diaphragmatic Breathing Drills",
        "Band Face Pull",
        "Controlled Bird-Dog",
        "Banded Hip Flexor Stretch",
        "Mobility Reset Flow",
    }
    all_cut_buckets = {"none", "low", "moderate", "high", "critical", "extreme"}

    for name, windows in expected_windows.items():
        item = _exercise_named(name)
        assert "TAPER" in item["phases"]
        assert windows.issubset(set(item.get("late_windows", [])))
        assert item["soreness_risk"] == "low"
        assert item["eccentric_cost"] == "low"
        assert item["cns_load"] == "low"
        if name in full_cut_access:
            assert set(item["cut_buckets_allowed"]) == all_cut_buckets

    mobility_reset_flow = _exercise_named("Mobility Reset Flow")
    assert mobility_reset_flow["phases"] == ["GPP", "SPP", "TAPER"]


def test_late_window_blocking_is_respected_for_real_strength_bank_item():
    for name in (
        "Staggered-Stance Medicine-Ball Punch Throw",
        "Scapular Pull-Up Hold",
        "Light Heavy-Bag Technical Tempo",
    ):
        item = _exercise_named(name)

        d4_result = strength._evaluate_strength_late_window(item, window=D4_TO_D2)
        d1_result = strength._evaluate_strength_late_window(item, window=D1)

        assert d4_result["blocked"] is False
        assert "late_strength_boost_window_fit" in d4_result["reason_codes"]
        assert d1_result["blocked"] is True
        assert "late_strength_block_window_mismatch" in d1_result["block_codes"]


def test_d3_blocks_med_ball_punch_throw_even_inside_d4_to_d2_window():
    item = _exercise_named("Staggered-Stance Medicine-Ball Punch Throw")

    d4_result = strength._evaluate_strength_late_window(item, window=D4_TO_D2, days_until_fight=4)
    d3_result = strength._evaluate_strength_late_window(item, window=D4_TO_D2, days_until_fight=3)

    assert d4_result["blocked"] is False
    assert d3_result["blocked"] is True
    assert "late_strength_block_d3_throw_lockout" in d3_result["block_codes"]


def test_d1_blocks_band_strength_work_even_with_rehab_metadata():
    item = _exercise_named("Band Face Pull")

    d1_result = strength._evaluate_strength_late_window(item, window=D1, days_until_fight=1)

    assert d1_result["blocked"] is True
    assert "late_strength_block_band_work_lockout" in d1_result["block_codes"]


def test_split_squat_iso_variants_have_correct_late_window_intent():
    overcoming = _exercise_named("Overcoming Split-Squat Isometric")
    assert overcoming["late_windows"] == ["d21_to_d14", "d13_to_d8"]
    assert overcoming["cns_freshness"] is False
    assert overcoming["cns_load"] == "moderate"
    assert overcoming["soreness_risk"] == "moderate"
    assert overcoming["cut_buckets_allowed"] == ["none", "low", "moderate"]
    assert overcoming["phase_role"] == "late_strength_touch"
    assert overcoming["subfamily"] == "loaded_lower_isometric"


def test_high_intent_or_ballistic_late_taper_variants_are_not_in_d7_plus():
    expectations = {
        "Punch-Specific Max Isometric Hold": {"d21_to_d14", "d13_to_d8"},
        "Staggered-Stance Medicine-Ball Punch Throw": {"d13_to_d8", "d4_to_d2"},
        "Half-Kneeling Medicine-Ball Punch Throw": {"d13_to_d8"},
        "Seated Medicine-Ball Punch Throw": {"d13_to_d8"},
    }

    for name, windows in expectations.items():
        item = _exercise_named(name)
        assert set(item["late_windows"]) == windows
        assert "d7" not in windows
        assert "d6_to_d5" not in windows
        assert "d1" not in windows
