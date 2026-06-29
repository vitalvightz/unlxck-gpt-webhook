from __future__ import annotations

import json
from pathlib import Path

from fightcamp import conditioning
from fightcamp.late_selector_windows import D1, D4_TO_D2, D6_TO_D5, D7, D13_TO_D8, D21_TO_D14
from fightcamp.training_context import normalize_equipment_list
from fightcamp.stage2_payload import build_stage2_payload
from fightcamp.training_context import TrainingContext


def _generic_conditioning_bank(phases: list[str] | None = None) -> list[dict]:
    phases = phases or ["GPP", "SPP", "TAPER"]
    return [
        {
            "name": "Generic Boxing Tempo",
            "placement": "conditioning",
            "system": "aerobic",
            "phases": phases,
            "tags": ["boxing", "conditioning", "aerobic"],
            "timing": "12 min steady",
            "rest": "",
            "load": "moderate",
        },
        {
            "name": "Generic Boxing Intervals",
            "placement": "conditioning",
            "system": "glycolytic",
            "phases": phases,
            "tags": ["boxing", "conditioning", "glycolytic"],
            "timing": "4 x 60s",
            "rest": "60s",
            "load": "hard",
        },
        {
            "name": "Generic Boxing Acceleration",
            "placement": "conditioning",
            "system": "alactic",
            "phases": phases,
            "tags": ["boxing", "alactic", "speed"],
            "work_sec": 6,
            "rest_sec": 90,
            "rounds": 4,
            "timing": "4 x 6s",
            "rest": "90s",
            "load": "fast",
        },
    ]


def _style_visibility_flags(phase: str, *, sport: str = "boxing", technical: list[str] | None = None) -> dict:
    return {
        "phase": phase,
        "sport": sport,
        "style_technical": technical or [sport],
        "style_tactical": ["Counter Striker"],
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "fatigue": "low",
        "equipment": ["bodyweight"],
        "training_frequency": 3,
        "days_available": 3,
        "days_until_fight": 35,
        "time_to_fight_days": 35,
        "injuries": [],
        "restrictions": [],
    }


def _patch_conditioning_visibility_banks(
    monkeypatch,
    *,
    style_bank: list[dict],
    total_drills: int = 2,
    base_phases: list[str] | None = None,
) -> None:
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: _generic_conditioning_bank(base_phases))
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: style_bank)
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "select_coordination_drill", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(conditioning, "_load_bank", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": total_drills})


def test_gpp_valid_style_conditioning_candidate_surfaces_when_conditioning_selected(monkeypatch):
    style_drill = {
        "name": "Counter Reactive Footwork",
        "placement": "conditioning",
        "system": "aerobic",
        "phases": ["GPP"],
        "tags": ["reactive", "footwork"],
        "timing": "10 min technical tempo",
        "rest": "",
        "load": "moderate",
    }
    _patch_conditioning_visibility_banks(monkeypatch, style_bank=[style_drill])

    _text, selected_names, _why, _grouped, _missing, reservoir = conditioning.generate_conditioning_block(
        _style_visibility_flags("GPP")
    )

    diagnostics = reservoir["__style_conditioning__"]
    assert "Counter Reactive Footwork" in selected_names
    assert diagnostics["style_target"] >= 1
    assert diagnostics["entries_selected"] == 1
    assert diagnostics["final_selected_style_conditioning_names"] == ["Counter Reactive Footwork"]


def test_spp_style_conditioning_is_picked_before_generic_system_fallback(monkeypatch):
    style_drill = {
        "name": "Counter Reactive Intervals",
        "placement": "conditioning",
        "system": "glycolytic",
        "phases": ["SPP"],
        "tags": ["reactive", "timing"],
        "timing": "4 x 45s",
        "rest": "75s",
        "load": "hard",
    }
    _patch_conditioning_visibility_banks(monkeypatch, style_bank=[style_drill])

    _text, selected_names, _why, grouped, _missing, reservoir = conditioning.generate_conditioning_block(
        _style_visibility_flags("SPP")
    )

    assert selected_names[0] == "Counter Reactive Intervals"
    assert grouped["glycolytic"][0]["name"] == "Counter Reactive Intervals"
    assert reservoir["__style_conditioning__"]["style_remaining_before_selection"] >= 1


def test_style_conditioning_expanded_style_tag_match_does_not_need_raw_tactical_token(monkeypatch):
    style_drill = {
        "name": "Expanded Reactive Match",
        "placement": "conditioning",
        "system": "glycolytic",
        "phases": ["SPP"],
        "tags": ["reactive"],
        "timing": "4 x 40s",
        "rest": "80s",
        "load": "hard",
    }
    _patch_conditioning_visibility_banks(monkeypatch, style_bank=[style_drill])

    _text, selected_names, _why, _grouped, _missing, reservoir = conditioning.generate_conditioning_block(
        _style_visibility_flags("SPP", sport="mma", technical=["mma"])
    )

    diagnostics = reservoir["__style_conditioning__"]
    assert "Expanded Reactive Match" in selected_names
    assert "reactive" in diagnostics["target_style_tags"]
    assert diagnostics["entries_passing_target_style_match"] == 1


def test_boxing_still_blocks_mma_grappling_and_kick_style_conditioning(monkeypatch):
    banned_drill = {
        "name": "MMA Sprawl Kick Chain",
        "placement": "conditioning",
        "system": "glycolytic",
        "phases": ["SPP"],
        "tags": ["reactive", "mma", "grappling", "kick"],
        "timing": "4 x 45s",
        "rest": "75s",
        "load": "hard",
    }
    _patch_conditioning_visibility_banks(monkeypatch, style_bank=[banned_drill])

    _text, selected_names, _why, _grouped, _missing, reservoir = conditioning.generate_conditioning_block(
        _style_visibility_flags("SPP")
    )

    diagnostics = reservoir["__style_conditioning__"]
    assert "MMA Sprawl Kick Chain" not in selected_names
    assert diagnostics["entries_blocked_by_sport_language_ban"] == 1
    assert diagnostics["entries_selected"] == 0


def test_alactic_style_conditioning_without_rest_structure_is_rejected(monkeypatch):
    invalid_alactic = {
        "name": "Bad Counter Burst",
        "placement": "conditioning",
        "system": "alactic",
        "phases": ["SPP"],
        "tags": ["reactive", "speed"],
        "work_sec": 12,
        "rest_sec": 20,
        "rounds": 6,
        "timing": "6 x 12s",
        "rest": "20s",
        "load": "fast",
    }
    _patch_conditioning_visibility_banks(monkeypatch, style_bank=[invalid_alactic])

    _text, selected_names, _why, _grouped, _missing, reservoir = conditioning.generate_conditioning_block(
        _style_visibility_flags("SPP")
    )

    diagnostics = reservoir["__style_conditioning__"]
    assert "Bad Counter Burst" not in selected_names
    assert diagnostics["entries_blocked_by_alactic_structure"] == 1
    assert diagnostics["entries_scored"] == 0


def test_style_conditioning_diagnostics_explain_no_contribution(monkeypatch):
    equipment_blocked = {
        "name": "Sled Counter Pressure",
        "placement": "conditioning",
        "system": "glycolytic",
        "phases": ["SPP"],
        "tags": ["reactive", "pressure"],
        "equipment": ["sled"],
        "timing": "5 x 30s",
        "rest": "90s",
        "load": "hard",
    }
    _patch_conditioning_visibility_banks(monkeypatch, style_bank=[equipment_blocked])

    _text, selected_names, _why, _grouped, _missing, reservoir = conditioning.generate_conditioning_block(
        _style_visibility_flags("SPP")
    )

    diagnostics = reservoir["__style_conditioning__"]
    assert "Sled Counter Pressure" not in selected_names
    assert diagnostics["total_style_bank_entries_loaded"] == 1
    assert diagnostics["entries_passing_phase"] == 1
    assert diagnostics["entries_passing_target_style_match"] == 1
    assert diagnostics["entries_blocked_by_equipment"] == 1
    assert diagnostics["entries_selected"] == 0
    assert diagnostics["final_selected_style_conditioning_names"] == []


def test_taper_does_not_pull_from_style_conditioning_bank(monkeypatch):
    taper_style = {
        "name": "Dirty Taper Style Conditioning",
        "placement": "conditioning",
        "system": "glycolytic",
        "phases": ["TAPER"],
        "tags": ["reactive", "boxing", "conditioning"],
        "timing": "5 x 60s",
        "rest": "45s",
        "load": "hard",
    }
    _patch_conditioning_visibility_banks(
        monkeypatch,
        style_bank=[taper_style],
        total_drills=2,
        base_phases=["TAPER"],
    )

    _text, selected_names, _why, _grouped, _missing, reservoir = conditioning.generate_conditioning_block(
        {
            **_style_visibility_flags("TAPER"),
            "days_until_fight": 14,
            "time_to_fight_days": 14,
        }
    )

    diagnostics = reservoir["__style_conditioning__"]
    assert "Dirty Taper Style Conditioning" not in selected_names
    assert diagnostics["style_target"] == 0
    assert diagnostics["style_remaining_before_selection"] == 0
    assert diagnostics["entries_selected"] == 0



def test_late_window_blocks_non_taper_phased_conditioning_even_if_otherwise_valid():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Band-Resisted Sprint Starts (ATP-PCr)",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["acceleration", "low_volume"],
            "work_sec": 10,
            "rest_sec": 80,
            "rounds": 8,
        },
        system="alactic",
        window=D6_TO_D5,
        bridge_rules={"glycolytic_touch_max": 0},
    )

    assert result["blocked"] is True
    assert "late_conditioning_block_not_taper_phased" in result["block_codes"]


def test_d7_and_under_blocks_non_rehab_band_conditioning_work():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Band-Resisted Sprint Starts (ATP-PCr)",
            "phases": ["TAPER"],
            "system": "alactic",
            "tags": ["acceleration", "speed"],
            "equipment": "bands",
            "work_sec": 10,
            "rest_sec": 80,
            "rounds": 6,
        },
        system="alactic",
        window=D7,
        bridge_rules={},
    )

    assert result["blocked"] is True
    assert "late_conditioning_block_band_work_lockout" in result["block_codes"]


def test_d1_blocks_rehab_band_conditioning_work():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Band External Rotation Mobility",
            "phases": ["TAPER"],
            "system": "aerobic",
            "tags": ["mobility", "rehab_friendly", "recovery"],
            "equipment": "bands",
            "work_sec": 20,
            "rest_sec": 40,
            "rounds": 2,
        },
        system="aerobic",
        window=D1,
        bridge_rules={},
    )

    assert result["blocked"] is True
    assert "late_conditioning_block_band_work_lockout" in result["block_codes"]



def test_late_window_blocks_non_taper_phased_conditioning_in_d13_to_d8():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Band-Resisted Sprint Starts (ATP-PCr)",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["acceleration", "low_volume"],
            "work_sec": 10,
            "rest_sec": 80,
            "rounds": 8,
        },
        system="alactic",
        window=D13_TO_D8,
        bridge_rules={"glycolytic_touch_max": 0},
    )

    assert result["blocked"] is True
    assert "late_conditioning_block_not_taper_phased" in result["block_codes"]




def test_late_window_blocks_non_taper_phased_conditioning_in_d1():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Band-Resisted Sprint Starts (ATP-PCr)",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["acceleration", "low_volume"],
            "work_sec": 10,
            "rest_sec": 80,
            "rounds": 8,
        },
        system="alactic",
        window=D1,
        bridge_rules={"glycolytic_touch_max": 0},
    )

    assert result["blocked"] is True
    assert "late_conditioning_block_not_taper_phased" in result["block_codes"]


def test_bridge_window_d21_to_d14_does_not_auto_block_spp_only_by_phase():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Band-Resisted Sprint Starts (ATP-PCr)",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["acceleration", "low_volume"],
            "work_sec": 10,
            "rest_sec": 80,
            "rounds": 8,
        },
        system="alactic",
        window=D21_TO_D14,
        bridge_rules={"glycolytic_touch_max": 1},
    )

    assert "late_conditioning_block_not_taper_phased" not in result["block_codes"]


def test_taper_phased_conditioning_remains_eligible_in_all_taper_only_windows():
    for window in (D13_TO_D8, D7, D6_TO_D5, D4_TO_D2, D1):
        result = conditioning._evaluate_conditioning_late_window(
            {
                "name": "Reactive Shuffle Repeats",
                "phases": ["TAPER"],
                "system": "alactic",
                "tags": ["low_impact", "cns_freshness", "skill_refinement"],
                "work_sec": 8,
                "rest_sec": 80,
                "rounds": 6,
            },
            system="alactic",
            window=window,
            bridge_rules={"glycolytic_touch_max": 0},
        )

        assert result["blocked"] is False

def test_late_window_keeps_taper_phased_conditioning_eligible():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Reactive Shuffle Repeats",
            "phases": ["TAPER"],
            "system": "alactic",
            "tags": ["low_impact", "cns_freshness", "skill_refinement"],
            "work_sec": 8,
            "rest_sec": 80,
            "rounds": 6,
        },
        system="alactic",
        window=D6_TO_D5,
        bridge_rules={"glycolytic_touch_max": 0},
    )

    assert result["blocked"] is False


def test_athlete_facing_system_label_returns_string_for_spp_only_drill():
    label = conditioning.athlete_facing_system_label(
        {
            "name": "Band-Resisted Sprint Starts (ATP-PCr)",
            "phases": ["SPP"],
            "system": "alactic",
            "tags": ["acceleration", "low_volume"],
            "work_sec": 10,
            "rest_sec": 80,
            "rounds": 8,
        },
        late_window=D6_TO_D5,
    )

    assert label == "footwork speed repeatability"

def test_late_taper_blocks_dense_glycolytic_from_structured_metadata():
    result = conditioning._evaluate_conditioning_late_window(
        {
            "name": "Neutral Tempo Blend",
            "system": "glycolytic",
            "tags": ["conditioning"],
            "work_sec": 75,
            "rest_sec": 45,
            "rounds": 5,
            "rpe": 8,
            "lactate_load": "high",
            "impact_cost": "low",
            "movement_cost": "high",
        },
        system="glycolytic",
        window=D4_TO_D2,
        bridge_rules={"glycolytic_touch_max": 1},
    )

    assert result["blocked"] is True
    assert "late_conditioning_block_structured_glycolytic_density" in result["block_codes"]
    assert "late_conditioning_penalty_high_lactate_metadata" in result["reason_codes"]


def test_athlete_facing_label_uses_structured_dose_before_text_parsing():
    label = conditioning.athlete_facing_system_label(
        {
            "name": "Plain Tempo Blend",
            "system": "glycolytic",
            "tags": [],
            "work_sec": 60,
            "rest_sec": 45,
            "rounds": 4,
            "lactate_load": "high",
        },
        late_window=None,
    )
    late_label = conditioning.athlete_facing_system_label(
        {
            "name": "Plain Tempo Blend",
            "system": "glycolytic",
            "tags": [],
            "work_sec": 60,
            "rest_sec": 45,
            "rounds": 4,
            "lactate_load": "high",
        },
        late_window=D4_TO_D2,
    )

    assert label == "glycolytic"
    assert late_label == "coordination conditioning"


def test_injury_restriction_filter_still_removes_unsafe_conditioning_option(monkeypatch):
    unsafe = {
        "name": "Jump Shuttle",
        "phases": ["SPP"],
        "system": "alactic",
        "tags": ["explosive", "high_impact", "mech_landing_impact"],
        "equipment": [],
        "work_sec": 8,
        "rest_sec": 90,
        "rounds": 4,
        "impact_cost": "high",
        "lactate_load": "low",
        "movement_cost": "moderate",
    }
    safe = {
        "name": "Bike Sprint",
        "phases": ["SPP"],
        "system": "alactic",
        "tags": ["explosive", "low_impact"],
        "equipment": ["assault_bike"],
        "work_sec": 8,
        "rest_sec": 90,
        "rounds": 4,
        "impact_cost": "low",
        "lactate_load": "low",
        "movement_cost": "low",
    }
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [unsafe, safe])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_format_weights", lambda: {"boxing": {"SPP": {"alactic": 1.0}}})
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": 1})

    _text, names, _why, grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        {
            "phase": "SPP",
            "fatigue": "low",
            "sport": "boxing",
            "fight_format": "boxing",
            "style_tactical": [],
            "style_technical": ["boxing"],
            "equipment": ["assault_bike"],
            "training_days": ["Mon"],
            "training_frequency": 1,
            "days_available": 1,
            "key_goals": ["conditioning"],
            "weaknesses": [],
            "injuries": [],
            "restrictions": [{"restriction": "high_impact", "strength": "avoid"}],
            "days_until_fight": 28,
        }
    )

    assert "Jump Shuttle" not in names
    assert all(
        drill.get("name") != "Jump Shuttle"
        for drills in grouped.values()
        for drill in drills
    )


def test_stage1_to_stage2_payload_carries_conditioning_metadata_scores_and_omissions():
    training_context = TrainingContext(
        fatigue="moderate",
        training_frequency=3,
        days_available=3,
        training_days=["Mon", "Wed", "Fri"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure"],
        weaknesses=["cardio"],
        equipment=["bodyweight"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["conditioning"],
        training_preference="short sessions",
        mental_block=[],
        age=26,
        weight=155.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 1, "SPP": 0, "TAPER": 0, "days": {"GPP": 7}},
        days_until_fight=35,
    )
    selected = {
        "name": "Tempo Shadowboxing",
        "system": "aerobic",
        "tags": ["aerobic", "low_impact"],
        "work_sec": 120,
        "rest_sec": 60,
        "rounds": 3,
        "total_minutes": 8,
        "rpe": 5,
        "impact_cost": "low",
        "lactate_load": "low",
        "movement_cost": "low",
    }
    alternate = {
        "name": "Bike Flush",
        "system": "aerobic",
        "tags": ["aerobic", "low_impact"],
        "total_minutes": 12,
        "rpe": 4,
        "impact_cost": "low",
        "lactate_load": "low",
        "movement_cost": "low",
    }
    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="5-0",
        rounds_format="3x3",
        camp_len=6,
        short_notice=False,
        restrictions=[],
        phase_weeks={"GPP": 1, "days": {"GPP": 7}},
        strength_blocks={"GPP": None},
        conditioning_blocks={
            "GPP": {
                "grouped_drills": {"aerobic": [selected]},
                "why_log": [
                    {
                        "name": "Tempo Shadowboxing",
                        "system": "aerobic",
                        "explanation": "base aerobic rhythm",
                        "reasons": {"final_score": 4.2, "reason_codes": ["system_quota"]},
                    }
                ],
                "candidate_reservoir": {
                    "aerobic": [
                        {
                            "drill": alternate,
                            "score": 3.8,
                            "reasons": {"final_score": 3.8, "reason_codes": ["alternate"]},
                            "explanation": "same system alternate",
                        }
                    ]
                },
                "missing_systems": ["glycolytic"],
            }
        },
        rehab_blocks={},
    )

    slot = payload["candidate_pools"]["GPP"]["conditioning_slots"][0]

    assert slot["selected"]["score"] == 4.2
    assert slot["selected"]["selection_metadata"]["lactate_load"] == "low"
    assert slot["selected"]["selection_metadata"]["work_sec"] == 120
    assert slot["alternates"][0]["score"] == 3.8
    assert slot["alternates"][0]["selection_metadata"]["total_minutes"] == 12
    assert payload["omission_ledger"]["GPP"]["conditioning"][0]["reason"] == "missing_system"


def test_coordination_bank_duplicate_names_are_resolved():
    data = json.loads(Path("data/coordination_bank.json").read_text(encoding="utf-8"))
    items = [item for values in data.values() if isinstance(values, list) for item in values]
    counts: dict[str, int] = {}
    for item in items:
        key = item["name"].strip().casefold()
        counts[key] = counts.get(key, 0) + 1

    assert {name: count for name, count in counts.items() if count > 1} == {}


def test_boxing_sprint_starts_are_not_tight_window_taper_defaults():
    data = json.loads(Path("data/conditioning_bank.json").read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in data}
    sprint_starts = [
        by_name[name]
        for name in ("Band-Resisted Sprint Start", "Band-Resisted Sprint Starts (ATP-PCr)")
    ]

    assert {item["name"] for item in sprint_starts} == {
        "Band-Resisted Sprint Start",
        "Band-Resisted Sprint Starts (ATP-PCr)",
    }
    for item in sprint_starts:
        assert item["phases"] == ["SPP"]
        assert "TAPER" not in item["phases"]
        assert "late_windows" not in item
        assert "TAPER" not in item["phases"]
        assert "SPP" in item["phases"]

    safe_taper_options = {
        "Explosive Boxing Burst Intervals",
        "Reactive Shuffle Repeats",
    }
    assert safe_taper_options.issubset(by_name)
    for name in safe_taper_options:
        item = by_name[name]
        assert item["phases"] == ["TAPER"]
        assert "d6_to_d5" in item["late_windows"]

    exercise_data = json.loads(Path("data/exercise_bank.json").read_text(encoding="utf-8"))
    exercise_by_name = {item["name"]: item for item in exercise_data if isinstance(item, dict) and "name" in item}
    for name in (
        "Band-Resisted Jab-Cross Primer",
        "Technical Shadowboxing Tempo",
        "Mobility Reset Flow",
    ):
        assert name in exercise_by_name
        assert "TAPER" in exercise_by_name[name].get("phases", [])
    assert any(
        "breathing" in str(item.get("name", "")).casefold() and "TAPER" in item.get("phases", [])
        for item in exercise_data
        if isinstance(item, dict)
    )


def test_band_resisted_sprint_starts_are_spp_only_across_conditioning_banks():
    conditioning_data = json.loads(Path("data/conditioning_bank.json").read_text(encoding="utf-8"))
    style_data = json.loads(Path("data/style_conditioning_bank.json").read_text(encoding="utf-8"))

    def _iter_band_resisted_sprint_starts(items: list[dict]) -> list[dict]:
        matches: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).lower()
            duration = str(item.get("duration", "")).lower()
            notes = str(item.get("notes", "")).lower()
            blob = f"{name} {duration} {notes}"
            if "band-resisted sprint start" in blob:
                matches.append(item)
        return matches

    matched = _iter_band_resisted_sprint_starts(conditioning_data) + _iter_band_resisted_sprint_starts(style_data)
    assert matched
    for item in matched:
        assert item.get("phases") == ["SPP"]
        assert "TAPER" not in item.get("phases", [])


def test_late_support_fallback_uses_window_appropriate_names():
    assert conditioning._late_support_fallback(D1)["name"] == "Final Readiness Cue Reset"
    assert conditioning._late_support_fallback(D21_TO_D14)["name"] == "Late-Camp Readiness Cue Reset"
    assert conditioning._late_support_fallback(D7)["name"] == "Late-Camp Readiness Cue Reset"


def test_boxing_jump_reset_is_not_taper_metadata_and_d6_prefers_low_impact_bursts():
    data = json.loads(Path("data/conditioning_bank.json").read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in data}

    jump_reset = by_name["Band-Assisted Jump Reset"]
    assert "TAPER" not in jump_reset["phases"]
    assert jump_reset["phases"] == ["SPP"]

    burst = by_name["Explosive Boxing Burst Intervals"]
    shuffle = by_name["Reactive Shuffle Repeats"]
    for item in (burst, shuffle):
        assert item["phases"] == ["TAPER"]
        assert "d6_to_d5" in item["late_windows"]
        assert "d1" not in item["late_windows"]
        assert conditioning._evaluate_conditioning_late_window(
            item,
            system=item["system"],
            window=D6_TO_D5,
            bridge_rules={},
        )["blocked"] is False
        assert conditioning._evaluate_conditioning_late_window(
            item,
            system=item["system"],
            window=D1,
            bridge_rules={},
        )["blocked"] is True


def test_generated_boxing_d6_taper_uses_low_impact_alactic_not_jump_or_sprint_start():
    result = conditioning.generate_conditioning_block(
        {
            "phase": "TAPER",
            "fatigue": "moderate",
            "style_technical": ["boxing"],
            "style_tactical": ["out-boxer"],
            "sport": "boxing",
            "key_goals": ["speed", "power", "conditioning"],
            "weaknesses": ["footwork", "sharpness"],
            "injuries": [],
            "restrictions": [],
            "equipment": ["bands", "bodyweight", "medicine_ball"],
            "training_frequency": 5,
            "days_available": 5,
            "days_until_fight": 6,
            "time_to_fight_days": 6,
            "weight_cut_pct": 5.0,
        }
    )

    plan_text, selected_names, *_rest, candidate_reservoir = result
    blocked: dict[str, set[str]] = {}
    for entry in candidate_reservoir["__late_window__"]["blocked"]:
        blocked.setdefault(entry["name"], set()).update(entry["reason_codes"])
    penalized = {
        entry["name"]: set(entry["penalty_codes"])
        for entry in candidate_reservoir["__late_window__"]["penalized"]
    }

    assert "Explosive Boxing Burst Intervals" not in selected_names
    assert "Reactive Shuffle Repeats" in selected_names
    assert "late_penalty_missing_governance_metadata" in penalized["Explosive Boxing Burst Intervals"]
    assert "late_penalty_missing_governance_metadata" in penalized["Reactive Shuffle Repeats"]
    assert "Band-Assisted Jump Reset" not in plan_text
    assert "Band-Resisted Sprint Start" not in plan_text
    assert "Band-Resisted Sprint Starts (ATP-PCr)" not in plan_text


def test_final_week_taper_caps_keep_primers_submaximal():
    d6 = conditioning._late_fight_dosage_caps(6)
    d1 = conditioning._late_fight_dosage_caps(1)

    assert "RPE 8" not in d6
    assert "RPE 8" not in d1
    assert "3-4 bursts max (6 sec @ RPE 6-7" in d6
    assert "RPE 3-5" in d1


def test_late_fight_generation_keeps_safe_support_available_across_windows():
    base_flags = {
        "phase": "TAPER",
        "fatigue": "moderate",
        "style_technical": ["boxing"],
        "style_tactical": ["out-boxer"],
        "sport": "boxing",
        "key_goals": ["conditioning", "sharpness"],
        "weaknesses": ["footwork", "sharpness"],
        "injuries": [],
        "restrictions": [],
        "equipment": ["bodyweight"],
        "training_frequency": 4,
        "days_available": 4,
        "weight_cut_pct": 5.0,
    }

    for days_until_fight in (18, 10, 6, 3, 1):
        result = conditioning.generate_conditioning_block(
            {
                **base_flags,
                "days_until_fight": days_until_fight,
                "time_to_fight_days": days_until_fight,
            }
        )
        _plan_text, selected_names, why_log, grouped_drills, _missing_systems, _candidate_reservoir = result

        assert selected_names, f"D-{days_until_fight} collapsed to no safe support"
        if days_until_fight == 1:
            selected_drills = [drill for drills in grouped_drills.values() for drill in drills]
            assert selected_drills
            for drill in selected_drills:
                tags = set(conditioning.normalize_tags(drill.get("tags", [])))
                assert tags & {"breathing", "visualization", "tactical", "readiness_check"}
                assert not drill.get("equipment")
                assert float(drill.get("rpe_max", drill.get("rpe", 0)) or 0) <= 3
            assert any(
                "late_support_fallback" in entry.get("reasons", {}).get("reason_codes", [])
                for entry in why_log
            )


def test_equipment_aliases_normalize_machine_variants():
    normalized = normalize_equipment_list(
        ["Air Bike", "Echo Bike", "Rowing Machine", "SkiErg", "concept2 rower"]
    )
    assert set(normalized) == {"assault_bike", "rower", "ski_erg"}


def test_taper_d19_gas_tank_signal_keeps_one_low_noise_aerobic_machine_dose():
    result = conditioning.generate_conditioning_block(
        {
            "phase": "TAPER",
            "fatigue": "low",
            "style_technical": ["boxing"],
            "style_tactical": ["out-boxer"],
            "sport": "boxing",
            "key_goals": ["conditioning"],
            "weaknesses": ["gas_tank"],
            "injuries": ["ankle"],
            "restrictions": [],
            "equipment": ["Air Bike", "Rowing Machine", "bodyweight"],
            "training_frequency": 5,
            "days_available": 5,
            "days_until_fight": 19,
            "time_to_fight_days": 19,
            "weight_cut_pct": 3.0,
        }
    )
    _text, selected_names, _why_log, grouped_drills, _missing, _reservoir = result
    selected_aerobic = [d.get("name", "") for d in grouped_drills.get("aerobic", [])]
    blocked = {
        entry["name"]: set(entry["reason_codes"])
        for entry in _reservoir["__late_window__"]["blocked"]
    }
    penalized = {
        entry["name"]: set(entry["penalty_codes"])
        for entry in _reservoir["__late_window__"]["penalized"]
    }
    assert selected_aerobic == ["Easy Assault Bike"]
    assert not any(
        "late_block_missing_cost_metadata" in reason_codes
        for name, reason_codes in blocked.items()
        if any(term in name.lower() for term in ("rower", "bike"))
    )
    assert "late_penalty_missing_governance_metadata" in penalized["Easy Assault Bike"]


def test_machine_biased_gas_tank_helper_detects_bike_and_rower():
    assert conditioning._is_machine_biased_gas_tank_drill(
        {"name": "Assault Bike Zone 2 Steady", "system": "aerobic", "lactate_load": "low", "rpe": 5}
    )
    assert conditioning._is_machine_biased_gas_tank_drill(
        {"equipment": ["rower"], "tags": ["recovery"], "lactate_load": "low", "rpe": 5}
    )
    assert not conditioning._is_machine_biased_gas_tank_drill({"name": "Battle Rope Waves", "equipment": ["battle_ropes"]})


def test_machine_biased_gas_tank_helper_rejects_glycolytic_machine_intervals():
    drill = {
        "name": "Assault Bike Tabata",
        "system": "glycolytic",
        "equipment": ["assault_bike"],
        "tags": ["conditioning"],
        "notes": "8 x 20s hard / 10s easy",
        "rpe": 9,
        "lactate_load": "high",
    }
    assert not conditioning._is_machine_biased_gas_tank_drill(drill)


def test_focus_token_normalization_matches_ui_labels():
    values = conditioning._normalize_focus_tokens(["Gas Tank", "Conditioning", "work_capacity"])
    assert "gas tank" in values
    assert "gas_tank" in values
    assert "conditioning" in values
    assert "work capacity" in values


def test_d16_profile_keeps_low_aerobic_machine_and_rejects_dense_machine_work(monkeypatch):
    safe_machine = {
        "name": "Assault Bike Easy Gas Tank Ride",
        "placement": "conditioning",
        "system": "aerobic",
        "phases": ["SPP"],
        "equipment": ["assault_bike"],
        "tags": ["conditioning", "aerobic", "low_impact", "recovery"],
        "rpe": 5,
        "lactate_load": "low",
        "notes": "12-18 min easy nasal breathing",
    }
    unsafe_machine = {
        "name": "Assault Bike Tabata",
        "placement": "conditioning",
        "system": "glycolytic",
        "phases": ["SPP"],
        "equipment": ["assault_bike"],
        "tags": ["conditioning", "work_capacity"],
        "rpe": 9,
        "lactate_load": "high",
        "notes": "8 x 20s hard / 10s easy",
    }
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [unsafe_machine, safe_machine])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "_load_bank", lambda *_args, **_kwargs: [])

    _text, selected_names, _why, grouped_drills, _missing, _reservoir = conditioning.generate_conditioning_block(
        {
            "phase": "SPP",
            "sport": "boxing",
            "style_tactical": ["Pressure Fighter"],
            "key_goals": ["Power", "Conditioning"],
            "weaknesses": ["Gas Tank"],
            "fatigue": "moderate",
            "equipment": ["Assault Bike", "Rower", "Battle Ropes"],
            "training_frequency": 5,
            "days_available": 5,
            "days_until_fight": 16,
            "weight_cut_pct": 3.0,
            "injuries": [],
            "restrictions": [],
        }
    )
    blob = " ".join(selected_names + [d.get("name", "") for d in grouped_drills.get("aerobic", [])]).lower()
    assert "assault bike" in blob or "rower" in blob
    assert "tabata" not in blob


def test_taper_d16_profile_allows_only_low_noise_machine_gas_tank(monkeypatch):
    safe_machine = {
        "name": "Concept2 Rower Recovery Rows",
        "placement": "conditioning",
        "system": "aerobic",
        "phases": ["TAPER"],
        "equipment": ["rower"],
        "tags": ["conditioning", "aerobic", "low_impact", "recovery"],
        "rpe": 5,
        "lactate_load": "low",
        "notes": "10-15 min smooth nasal breathing",
    }
    unsafe_machine = {
        "name": "Assault Bike Capacity Builder 20min EMOM",
        "placement": "conditioning",
        "system": "glycolytic",
        "phases": ["TAPER"],
        "equipment": ["assault_bike"],
        "tags": ["conditioning", "work_capacity"],
        "rpe": 8,
        "lactate_load": "high",
        "notes": "EMOM intervals",
    }
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [unsafe_machine, safe_machine])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "_load_bank", lambda *_args, **_kwargs: [])

    _text, selected_names, _why, grouped_drills, _missing, _reservoir = conditioning.generate_conditioning_block(
        {
            "phase": "TAPER",
            "sport": "boxing",
            "key_goals": ["Power", "Conditioning"],
            "weaknesses": ["Gas Tank"],
            "fatigue": "moderate",
            "equipment": ["Assault Bike", "Rower"],
            "training_frequency": 5,
            "days_available": 5,
            "days_until_fight": 16,
            "weight_cut_pct": 3.0,
            "injuries": [],
            "restrictions": [],
        }
    )
    blob = " ".join(selected_names + [d.get("name", "") for d in grouped_drills.get("aerobic", [])]).lower()
    assert "rower" in blob or "bike" in blob
    assert "tabata" not in blob
    assert "emom" not in blob

def test_preferred_exercise_names_get_strong_score_boost(monkeypatch):
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [
        {
            "name": "Assault Bike Easy Gas Tank Ride",
            "placement": "conditioning",
            "phases": ["GPP"],
            "system": "aerobic",
            "tags": ["aerobic", "recovery", "low_impact"],
            "equipment": ["assault_bike"],
        },
        {
            "name": "Generic Aerobic Builder",
            "placement": "conditioning",
            "phases": ["GPP"],
            "system": "aerobic",
            "tags": ["aerobic", "recovery", "low_impact"],
            "equipment": ["assault_bike"],
        },
    ])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])

    _block, names, reasons, _grouped, _missing, _reservoir = conditioning.generate_conditioning_block(
        {
            "phase": "GPP",
            "fatigue": "low",
            "style_technical": ["boxing"],
            "style_tactical": ["boxing"],
            "key_goals": ["gas_tank"],
            "weaknesses": ["gas_tank"],
            "equipment": ["assault_bike"],
            "training_frequency": 2,
            "preferred_exercise_names": ["Assault Bike Easy Gas Tank Ride"],
        }
    )

    assert names
    assert names[0] == "Assault Bike Easy Gas Tank Ride"
    by_name = {entry.get("name"): entry for entry in reasons}
    assert "preferred_exercise_name_match:+3.0" in by_name["Assault Bike Easy Gas Tank Ride"].get("reasons", {}).get("reason_codes", [])
    assert "preferred exercise match" in (by_name["Assault Bike Easy Gas Tank Ride"].get("explanation", "")).lower()
