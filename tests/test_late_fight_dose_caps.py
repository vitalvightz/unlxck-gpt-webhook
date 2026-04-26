from fightcamp.conditioning import athlete_facing_system_label
from fightcamp.stage2_payload import _apply_late_fight_dose_caps


def _slot(slot_id: str, name: str, *, prescription: str = "") -> dict:
    return {
        "slot_id": slot_id,
        "selected": {
            "name": name,
            "prescription": prescription,
        },
    }


def test_d6_high_cut_suppresses_neural_stacking_between_explosive_and_ankle():
    pools = {
        "TAPER": {
            "strength_slots": [],
            "conditioning_slots": [
                _slot("c1", "Explosive Boxing Burst Intervals"),
                _slot("c2", "Ankle Snap Bounce"),
            ],
            "rehab_slots": [],
        }
    }
    updated = _apply_late_fight_dose_caps(
        pools,
        days_until_fight=6,
        athlete_model={"cut_severity_bucket": "high", "weight_cut_pct": 6.0},
    )
    names = [slot["selected"]["name"] for slot in updated["TAPER"]["conditioning_slots"]]
    assert not ({"Explosive Boxing Burst Intervals", "Ankle Snap Bounce"} <= set(names))


def test_d1_punch_specific_max_isometric_hold_is_capped_to_tiny_final_cue():
    pools = {
        "TAPER": {
            "strength_slots": [
                _slot("s1", "Punch-Specific Max Isometric Hold", prescription="3 x 10-12s per side"),
            ],
            "conditioning_slots": [],
            "rehab_slots": [],
        }
    }
    updated = _apply_late_fight_dose_caps(
        pools,
        days_until_fight=1,
        athlete_model={},
    )
    prescription = updated["TAPER"]["strength_slots"][0]["selected"]["prescription"]
    assert "1–2 sets x 3–5s per side" in prescription


def test_d1_blocks_band_resisted_jab_cross_med_ball_and_multiple_neural_cues():
    pools = {
        "TAPER": {
            "strength_slots": [
                _slot("s1", "Band-Resisted Jab-Cross"),
                _slot("s2", "Punch-Specific Max Isometric Hold"),
                _slot("s3", "Medicine-Ball Punch Throw"),
            ],
            "conditioning_slots": [
                _slot("c1", "Ankle Snap Bounce"),
            ],
            "rehab_slots": [_slot("r1", "Breathing reset"), _slot("r2", "Mobility reset")],
        }
    }
    updated = _apply_late_fight_dose_caps(
        pools,
        days_until_fight=1,
        athlete_model={},
    )
    remaining = {
        slot["selected"]["name"]
        for slot in updated["TAPER"]["strength_slots"] + updated["TAPER"]["conditioning_slots"]
    }
    assert "Band-Resisted Jab-Cross" not in remaining
    assert "Medicine-Ball Punch Throw" not in remaining
    assert "Ankle Snap Bounce" not in remaining
    assert len([name for name in remaining if "Isometric Hold" in name or "Punch" in name]) <= 1
    assert len(updated["TAPER"]["rehab_slots"]) <= 1


def test_d7_keeps_only_one_primary_neural_alactic_drill():
    pools = {
        "TAPER": {
            "strength_slots": [
                _slot("s1", "Band-Resisted Jab-Cross"),
                _slot("s2", "Medicine-Ball Punch Throw"),
            ],
            "conditioning_slots": [
                _slot("c1", "Ankle Snap Bounce"),
            ],
            "rehab_slots": [],
        }
    }
    updated = _apply_late_fight_dose_caps(
        pools,
        days_until_fight=7,
        athlete_model={},
    )
    remaining = updated["TAPER"]["strength_slots"] + updated["TAPER"]["conditioning_slots"]
    assert len(remaining) == 1


def test_agility_ladder_long_rest_is_not_labelled_glycolytic():
    label = athlete_facing_system_label(
        {
            "name": "Agility Ladder Power Drills",
            "system": "glycolytic",
            "timing": "4 x 30s",
            "rest": "90s between reps",
            "tags": ["coordination", "reactive", "footwork"],
        },
        late_window="d13_to_d8",
    )
    assert label != "glycolytic"
