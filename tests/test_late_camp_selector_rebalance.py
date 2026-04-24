from __future__ import annotations

import json
from pathlib import Path

from fightcamp import conditioning, strength
from tools.late_camp_selector_audit import build_diff, build_snapshot


SNAPSHOT_DIR = Path("tests/golden_snapshots/late_camp_selector_audit")
NEW_LATE_STRENGTH_FAMILY_NAMES = {
    "Isometric Mid-Thigh Pull",
    "Trap-Bar Pin Pull Isometric",
    "Punch-Specific Max Isometric Hold",
    "Overcoming Split-Squat Isometric",
    "Staggered-Stance Medicine-Ball Punch Throw",
    "Towel/Gi Row Isometric Hold",
    "Band-Resisted Jab-Cross Primer",
    "Adductor Squeeze Isometric",
    "Counter-Striker Split-Line Punch Isometric Hold",
    "Pressure-Fighter Staggered Body-Shot Med-Ball Throw",
    "Clinch Towel/Gi Row Isometric Hold",
}


def _strength_flags(days_until_fight: int, **overrides) -> dict:
    base = {
        "phase": "TAPER",
        "fatigue": "low",
        "fight_format": "boxing",
        "sport": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "equipment": ["bodyweight", "bands", "medicine_ball"],
        "training_days": ["Mon", "Wed", "Fri"],
        "training_frequency": 3,
        "days_available": 3,
        "key_goals": ["power"],
        "weaknesses": [],
        "injuries": [],
        "days_until_fight": days_until_fight,
    }
    return {**base, **overrides}


def _conditioning_flags(days_until_fight: int, **overrides) -> dict:
    base = {
        "phase": "TAPER",
        "fatigue": "low",
        "sport": "boxing",
        "fight_format": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "equipment": ["bodyweight", "bands", "medicine_ball"],
        "training_days": ["Mon", "Wed", "Fri"],
        "training_frequency": 3,
        "days_available": 3,
        "key_goals": ["conditioning"],
        "weaknesses": [],
        "injuries": [],
        "days_until_fight": days_until_fight,
    }
    return {**base, **overrides}


def _expanded_late_strength_flags(days_until_fight: int, **overrides) -> dict:
    phase = "SPP" if days_until_fight >= 8 else "TAPER"
    base = _strength_flags(
        days_until_fight,
        phase=phase,
        equipment=[
            "bodyweight",
            "bands",
            "medicine_ball",
            "heavy_bag",
            "pullup_bar",
            "towel",
            "trap_bar",
            "pins",
        ],
        training_days=["Mon", "Tue", "Thu", "Sat"],
        training_frequency=4,
        days_available=4,
        key_goals=["power", "maximal_strength_maintenance", "skill_refinement"],
        style_tactical=["counter_striker"],
    )
    return {**base, **overrides}


def _selected_strength_names(result: dict) -> list[str]:
    return [entry["name"] for entry in result["why_log"]]


def _blocked_strength_names(result: dict) -> set[str]:
    return {
        entry["name"]
        for entry in result["candidate_reservoir"]["__late_window__"]["blocked"]
    }


def test_strength_late_window_keeps_crisp_overhead_when_low_dose(monkeypatch):
    exercise_bank = [
        {
            "name": "Crisp Overhead Snap",
            "phases": ["TAPER"],
            "movement": "vertical_push",
            "method": "power",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["crisp_overhead", "explosive", "neural_primer", "mech_shoulder_overhead"],
        },
        {
            "name": "Dense Overhead Grind",
            "phases": ["TAPER"],
            "movement": "vertical_push",
            "method": "power",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["dense_overhead", "explosive", "mech_shoulder_overhead"],
            "notes": "EMOM 10min overhead work",
        },
        {
            "name": "Support Pull",
            "phases": ["TAPER"],
            "movement": "pull",
            "method": "rehab",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["support_pull", "rehab_friendly"],
        },
        {
            "name": "Core Brace",
            "phases": ["TAPER"],
            "movement": "core",
            "method": "rehab",
            "type": "bilateral",
            "equipment": ["bodyweight"],
            "tags": ["core_brace", "rehab_friendly"],
        },
    ]
    score_map = {
        "crisp_overhead": 10.0,
        "dense_overhead": 10.1,
        "support_pull": 8.0,
        "core_brace": 7.5,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 3})
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]]},
        ),
    )
    monkeypatch.setattr(
        strength,
        "strength_quality_adjustment",
        lambda exercise, phase=None: (
            0.0,
            {
                "quality_class": "anchor_power" if exercise.get("movement") == "vertical_push" else "rehab_support",
                "anchor_capable": exercise.get("movement") != "core",
                "support_only": exercise.get("movement") == "core",
                "base_categories": [],
            },
        ),
    )

    result = strength.generate_strength_block(flags=_strength_flags(7))
    names = [entry["name"] for entry in result["why_log"]]
    blocked = result["candidate_reservoir"]["__late_window__"]["blocked"]

    assert "Crisp Overhead Snap" in names
    assert "Dense Overhead Grind" not in names
    assert any(entry["name"] == "Dense Overhead Grind" for entry in blocked)


def test_strength_late_window_blocks_known_offenders_and_logs_reason_codes(monkeypatch):
    exercise_bank = [
        {
            "name": "EMOM: 5 Squat Cleans + 5 Burpees",
            "phases": ["TAPER"],
            "movement": "compound",
            "method": "conditioning",
            "type": "bilateral",
            "equipment": ["barbell"],
            "tags": ["emom_offender", "explosive", "mech_systemic_fatigue"],
            "notes": "EMOM 10min",
        },
        {
            "name": "Safe Push",
            "phases": ["TAPER"],
            "movement": "vertical_push",
            "method": "power",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["safe_push", "explosive", "neural_primer"],
        },
        {
            "name": "Safe Pull",
            "phases": ["TAPER"],
            "movement": "pull",
            "method": "rehab",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["safe_pull", "rehab_friendly"],
        },
        {
            "name": "Safe Core",
            "phases": ["TAPER"],
            "movement": "core",
            "method": "rehab",
            "type": "bilateral",
            "equipment": ["bodyweight"],
            "tags": ["safe_core", "rehab_friendly"],
        },
    ]
    style_bank = [
        {
            "name": "Jumping Lunge",
            "phases": ["TAPER"],
            "movement": "lunge",
            "method": "strength",
            "type": "unilateral",
            "equipment": ["bodyweight"],
            "tags": ["style_jump", "pressure_fighter", "explosive", "mech_landing_impact", "mech_lower_lunge", "mech_ballistic"],
        }
    ]
    score_map = {
        "emom_offender": 11.0,
        "safe_push": 9.0,
        "safe_pull": 8.0,
        "safe_core": 7.0,
        "style_jump": 10.5,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: style_bank)
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 3})
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]]},
        ),
    )
    monkeypatch.setattr(
        strength,
        "strength_quality_adjustment",
        lambda exercise, phase=None: (
            0.0,
            {
                "quality_class": "anchor_power",
                "anchor_capable": True,
                "support_only": False,
                "base_categories": [],
            },
        ),
    )

    result = strength.generate_strength_block(
        flags=_strength_flags(7, equipment=["bodyweight", "bands", "barbell"], style_tactical=["pressure_fighter"])
    )
    blocked = result["candidate_reservoir"]["__late_window__"]["blocked"]
    blocked_by_name = {entry["name"]: entry["reason_codes"] for entry in blocked}

    assert "EMOM: 5 Squat Cleans + 5 Burpees" in blocked_by_name
    assert "late_strength_block_dense_emom" in blocked_by_name["EMOM: 5 Squat Cleans + 5 Burpees"]
    assert "Jumping Lunge" in blocked_by_name
    assert "late_strength_block_known_offender" in blocked_by_name["Jumping Lunge"]


def test_strength_bridge_phase_activates_late_selector_without_taper_label(monkeypatch):
    exercise_bank = [
        {
            "name": "Jumping Lunge",
            "phases": ["SPP"],
            "movement": "lunge",
            "method": "power",
            "type": "unilateral",
            "equipment": ["bodyweight"],
            "tags": ["style_jump", "explosive", "mech_landing_impact", "mech_lower_lunge", "mech_ballistic"],
        },
        {
            "name": "Band Snap Punch",
            "phases": ["SPP"],
            "movement": "vertical_push",
            "method": "power",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["band_snap", "neural_primer", "speed", "reactive", "low_impact"],
        },
    ]
    score_map = {
        "style_jump": 10.4,
        "band_snap": 10.0,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]]},
        ),
    )
    monkeypatch.setattr(
        strength,
        "strength_quality_adjustment",
        lambda exercise, phase=None: (
            0.0,
            {
                "quality_class": "anchor_power",
                "anchor_capable": True,
                "support_only": False,
                "base_categories": [],
            },
        ),
    )

    result = strength.generate_strength_block(flags=_strength_flags(14, phase="SPP"))

    assert [entry["name"] for entry in result["why_log"]] == ["Band Snap Punch"]
    assert result["candidate_reservoir"]["__late_window__"]["window"] == "d21_to_d14"


def test_strength_d13_high_cut_prefers_lower_noise_touch_over_heavy_loaded_lower(monkeypatch):
    exercise_bank = [
        {
            "name": "Heavy Trap Bar Pull 3x3 @ 85",
            "phases": ["SPP"],
            "movement": "hinge",
            "method": "strength",
            "type": "bilateral",
            "equipment": ["trap_bar"],
            "tags": ["heavy_pull", "neural_primer", "cluster", "mech_cns_high", "mech_lower_hip_hinge"],
            "notes": "Heavy trap-bar strength touch at 85%.",
        },
        {
            "name": "Band Deadlift Pull Snap",
            "phases": ["SPP"],
            "movement": "hinge",
            "method": "power",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["band_snap", "neural_primer", "speed", "reactive", "low_impact", "mech_lower_hip_hinge"],
        },
    ]
    score_map = {
        "heavy_pull": 10.6,
        "band_snap": 10.0,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]]},
        ),
    )
    monkeypatch.setattr(
        strength,
        "strength_quality_adjustment",
        lambda exercise, phase=None: (
            0.0,
            {
                "quality_class": "anchor_loaded" if exercise.get("movement") == "hinge" else "anchor_power",
                "anchor_capable": True,
                "support_only": False,
                "base_categories": [],
            },
        ),
    )

    result = strength.generate_strength_block(
        flags=_strength_flags(
            13,
            phase="SPP",
            equipment=["bands", "trap_bar"],
            cut_severity_bucket="high",
        )
    )

    assert [entry["name"] for entry in result["why_log"]] == ["Band Deadlift Pull Snap"]


def test_strength_d7_deprioritizes_aggressive_med_ball_slam_primer(monkeypatch):
    exercise_bank = [
        {
            "name": "Anti-Rotation Med Ball Slam",
            "phases": ["TAPER"],
            "movement": "core",
            "method": "power",
            "type": "bilateral",
            "equipment": ["medicine_ball"],
            "tags": [
                "slam_primer",
                "neural_primer",
                "anti_rotation",
                "mech_trunk_rotation",
                "mech_ballistic",
            ],
        },
        {
            "name": "Band Snap Punch",
            "phases": ["TAPER"],
            "movement": "vertical_push",
            "method": "power",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["band_snap", "neural_primer", "speed", "reactive", "low_impact"],
        },
    ]
    score_map = {
        "slam_primer": 10.5,
        "band_snap": 10.0,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]]},
        ),
    )
    monkeypatch.setattr(
        strength,
        "strength_quality_adjustment",
        lambda exercise, phase=None: (
            0.0,
            {
                "quality_class": "anchor_power",
                "anchor_capable": True,
                "support_only": False,
                "base_categories": [],
            },
        ),
    )

    result = strength.generate_strength_block(flags=_strength_flags(7))

    assert [entry["name"] for entry in result["why_log"]] == ["Band Snap Punch"]


def test_strength_d1_blocks_trap_bar_jump_and_aggressive_med_ball_slam(monkeypatch):
    exercise_bank = [
        {
            "name": "Trap Bar Jump (Light)",
            "phases": ["TAPER"],
            "movement": "squat",
            "method": "power",
            "type": "bilateral",
            "equipment": ["trap_bar"],
            "tags": ["trap_jump", "neural_primer", "explosive", "mech_ballistic", "mech_lower_jump", "mech_landing_impact"],
        },
        {
            "name": "Anti-Rotation Med Ball Slam",
            "phases": ["TAPER"],
            "movement": "core",
            "method": "power",
            "type": "bilateral",
            "equipment": ["medicine_ball"],
            "tags": ["slam_primer", "neural_primer", "anti_rotation", "mech_trunk_rotation", "mech_ballistic"],
        },
        {
            "name": "Band Snap Punch",
            "phases": ["TAPER"],
            "movement": "vertical_push",
            "method": "power",
            "type": "bilateral",
            "equipment": ["bands"],
            "tags": ["band_snap", "neural_primer", "speed", "reactive", "low_impact"],
        },
    ]
    score_map = {
        "trap_jump": 10.8,
        "slam_primer": 10.6,
        "band_snap": 10.0,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]]},
        ),
    )
    monkeypatch.setattr(
        strength,
        "strength_quality_adjustment",
        lambda exercise, phase=None: (
            0.0,
            {
                "quality_class": "anchor_power",
                "anchor_capable": True,
                "support_only": False,
                "base_categories": [],
            },
        ),
    )

    result = strength.generate_strength_block(flags=_strength_flags(1, equipment=["bands", "trap_bar", "medicine_ball"]))
    blocked = result["candidate_reservoir"]["__late_window__"]["blocked"]
    blocked_by_name = {entry["name"]: entry["reason_codes"] for entry in blocked}

    assert [entry["name"] for entry in result["why_log"]] == ["Band Snap Punch"]
    assert "late_strength_block_trap_bar_jump" in blocked_by_name["Trap Bar Jump (Light)"]
    assert "late_strength_block_aggressive_med_ball_slam" in blocked_by_name["Anti-Rotation Med Ball Slam"]


def test_actual_bank_d21_surfaces_multiple_late_strength_touch_families():
    result = strength.generate_strength_block(
        flags=_expanded_late_strength_flags(21),
        weaknesses=["posterior_chain", "coordination", "balance"],
    )

    names = _selected_strength_names(result)
    late_touch_hits = set(names) & NEW_LATE_STRENGTH_FAMILY_NAMES

    assert len(late_touch_hits) >= 2
    assert any(name in late_touch_hits for name in {"Isometric Mid-Thigh Pull", "Trap-Bar Pin Pull Isometric"})
    assert any(
        name in late_touch_hits
        for name in {
            "Punch-Specific Max Isometric Hold",
            "Counter-Striker Split-Line Punch Isometric Hold",
            "Band-Resisted Jab-Cross Primer",
            "Staggered-Stance Medicine-Ball Punch Throw",
        }
    )


def test_actual_bank_d13_high_cut_prefers_late_safe_strength_touch_over_legacy_taper_noise():
    result = strength.generate_strength_block(
        flags=_expanded_late_strength_flags(
            13,
            phase="TAPER",
            cut_severity_bucket="critical",
        ),
        weaknesses=["posterior_chain", "coordination"],
    )

    names = _selected_strength_names(result)

    assert set(names) & NEW_LATE_STRENGTH_FAMILY_NAMES
    assert "Cluster Set Trap Bar Deadlift" not in names
    assert "Trap Bar Jump (Light)" not in names
    assert "Jump Lunge (Alternating)" not in names


def test_actual_bank_d7_keeps_crisp_low_soreness_primers_and_blocks_aggressive_slam():
    result = strength.generate_strength_block(
        flags=_expanded_late_strength_flags(7),
        weaknesses=["coordination", "balance"],
    )

    names = _selected_strength_names(result)
    assert any(
        name in names
        for name in {
            "Band-Resisted Jab-Cross Primer",
            "Counter-Striker Split-Line Punch Isometric Hold",
            "Punch-Specific Max Isometric Hold",
            "Staggered-Stance Medicine-Ball Punch Throw",
        }
    )
    assert "Anti-Rotation Med Ball Slam" not in names


def test_actual_bank_d1_keeps_only_ultra_safe_micro_dose_strength_options():
    result = strength.generate_strength_block(
        flags=_expanded_late_strength_flags(1),
        weaknesses=["coordination", "balance"],
    )

    names = _selected_strength_names(result)
    blocked = _blocked_strength_names(result)
    allowed_names = {
        "Band-Resisted Jab-Cross Primer",
        "Punch-Specific Max Isometric Hold",
        "Counter-Striker Split-Line Punch Isometric Hold",
        "Towel/Gi Row Isometric Hold",
        "Clinch Towel/Gi Row Isometric Hold",
        "Adductor Squeeze Isometric",
        "Band Face Pull",
        "Banded Lateral Walk",
        "Hollow-Body Hold",
        "Isometric Pallof Hold",
        "Single-Leg Balance (Eyes Closed)",
        "TRX Row",
    }

    assert set(names).issubset(allowed_names)
    assert "Trap Bar Jump (Light)" not in names
    assert "Jump Lunge (Alternating)" not in names
    assert "Anti-Rotation Med Ball Slam" not in names
    assert "Trap Bar Jump (Light)" in blocked
    assert "Anti-Rotation Med Ball Slam" in blocked
    assert "Cluster Set Trap Bar Deadlift" in blocked


def test_conditioning_late_window_keeps_reactive_option_without_generic_glycolytic_leak(monkeypatch):
    conditioning_bank = [
        {
            "name": "Reactive Med Ball Chest Pass",
            "placement": "conditioning",
            "phases": ["TAPER"],
            "system": "ATP-PCr",
            "equipment": ["medicine_ball"],
            "duration": "6x3 reps, 75s rest",
            "tags": ["plyometric", "mech_ballistic", "mech_reactive", "cns_freshness"],
            "notes": "Crisp reactive pass with full recovery.",
        },
        {
            "name": "Fight Pace Leak",
            "placement": "conditioning",
            "phases": ["TAPER"],
            "system": "glycolytic",
            "equipment": [],
            "duration": "5x3min, 30s rest",
            "tags": ["conditioning", "glycolytic", "work_capacity"],
            "notes": "Fight pace rounds under fatigue.",
        },
        {
            "name": "Easy Bike",
            "placement": "conditioning",
            "phases": ["TAPER"],
            "system": "aerobic",
            "equipment": [],
            "duration": "20min easy",
            "tags": ["aerobic", "low_impact", "cns_freshness", "recovery"],
            "notes": "Easy recovery spin.",
        },
    ]

    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: conditioning_bank)
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_format_weights", lambda: {"boxing": {"aerobic": 1.0, "glycolytic": 1.0, "alactic": 1.0}})
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": 2})
    monkeypatch.setattr(conditioning, "_load_bank", lambda *args, **kwargs: [])
    monkeypatch.setattr(conditioning, "select_coordination_drill", lambda *args, **kwargs: None)

    (
        _block_text,
        _names,
        why_log,
        grouped_drills,
        _missing_systems,
        candidate_reservoir,
    ) = conditioning.generate_conditioning_block(_conditioning_flags(7))

    selected_names = [entry["name"] for entry in why_log]
    blocked_names = {entry["name"] for entry in candidate_reservoir["__late_window__"]["blocked"]}

    assert "Reactive Med Ball Chest Pass" in selected_names
    assert "Fight Pace Leak" not in selected_names
    assert "Fight Pace Leak" in blocked_names
    assert "glycolytic" not in grouped_drills


def test_conditioning_bridge_phase_activates_late_window_without_taper_label(monkeypatch):
    conditioning_bank = [
        {
            "name": "Fight Pace Leak",
            "placement": "conditioning",
            "phases": ["SPP"],
            "system": "glycolytic",
            "equipment": [],
            "duration": "5x3min, 30s rest",
            "tags": ["conditioning", "glycolytic", "work_capacity"],
            "notes": "Fight pace rounds under fatigue.",
        },
        {
            "name": "Reactive Med Ball Chest Pass",
            "placement": "conditioning",
            "phases": ["SPP"],
            "system": "ATP-PCr",
            "equipment": ["medicine_ball"],
            "duration": "6x3 reps, 75s rest",
            "tags": ["plyometric", "mech_ballistic", "mech_reactive", "cns_freshness"],
            "notes": "Crisp reactive pass with full recovery.",
        },
        {
            "name": "Easy Bike",
            "placement": "conditioning",
            "phases": ["SPP"],
            "system": "aerobic",
            "equipment": [],
            "duration": "20min easy",
            "tags": ["aerobic", "low_impact", "cns_freshness", "recovery"],
            "notes": "Easy recovery spin.",
        },
    ]

    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: conditioning_bank)
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_format_weights", lambda: {"boxing": {"aerobic": 1.0, "glycolytic": 1.0, "alactic": 1.0}})
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": 2})
    monkeypatch.setattr(conditioning, "_load_bank", lambda *args, **kwargs: [])
    monkeypatch.setattr(conditioning, "select_coordination_drill", lambda *args, **kwargs: None)

    (
        _block_text,
        _names,
        why_log,
        grouped_drills,
        _missing_systems,
        candidate_reservoir,
    ) = conditioning.generate_conditioning_block(_conditioning_flags(14, phase="SPP"))

    selected_names = [entry["name"] for entry in why_log]
    blocked_names = {entry["name"] for entry in candidate_reservoir["__late_window__"]["blocked"]}

    assert candidate_reservoir["__late_window__"]["window"] == "d21_to_d14"
    assert "Fight Pace Leak" not in selected_names
    assert "Fight Pace Leak" in blocked_names
    assert "glycolytic" not in grouped_drills


def test_audit_snapshot_matches_golden():
    expected = json.loads((SNAPSHOT_DIR / "after.json").read_text(encoding="utf-8"))
    assert build_snapshot() == expected


def test_audit_diff_matches_golden_and_keeps_control_window_stable():
    before = json.loads((SNAPSHOT_DIR / "before.json").read_text(encoding="utf-8"))
    after = json.loads((SNAPSHOT_DIR / "after.json").read_text(encoding="utf-8"))
    expected_diff = json.loads((SNAPSHOT_DIR / "diff.json").read_text(encoding="utf-8"))

    actual_diff = build_diff(before, after)

    assert actual_diff == expected_diff
    assert actual_diff["control_d28"]["strength"]["added_winners"] == []
    assert actual_diff["control_d28"]["conditioning"]["added_winners"] == []
