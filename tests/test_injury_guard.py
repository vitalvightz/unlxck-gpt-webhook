import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.conditioning import _INJURY_GUARD_LOGGED, _drill_text_injury_reasons, _is_drill_text_safe, select_coordination_drill
from fightcamp.injury_filtering import (
    audit_missing_tags,
    build_injury_exclusion_map,
    infer_tags_from_name,
    injury_flag_reasons,
    injury_violation_reasons,
    is_injury_safe,
    match_forbidden,
    normalize_injury_regions,
)


def test_match_forbidden_avoids_substrings():
    assert match_forbidden("Pressure Fighter", ["press"]) == []
    assert match_forbidden("pressuring drills", ["press"]) == []
    assert match_forbidden("pressure cooker", ["press"]) == []
    assert match_forbidden("Pressure Fighter’s Cutoff Circuit", ["press"]) == []
    assert match_forbidden("compression switch", ["press"]) == []
    assert match_forbidden("skipping rope", ["kipping"]) == []
    assert match_forbidden("membership plan", ["hip"]) == []
    assert match_forbidden("stomach ache", ["toe"]) == []


def test_match_forbidden_word_boundaries():
    assert match_forbidden("pressure fighter", ["press"]) == []
    assert match_forbidden("Pressure Cooker", ["press"]) == []
    assert match_forbidden("pressuring", ["press"]) == []
    assert match_forbidden("depress", ["press"]) == []
    assert match_forbidden("bench", ["bench press"]) == []
    assert match_forbidden("benched", ["bench press"]) == []
    assert match_forbidden("benching", ["bench press"]) == []
    assert match_forbidden("overhead costs", ["overhead"]) == []
    assert match_forbidden("overhead-like work", ["overhead"]) == []


def test_match_forbidden_respects_phrases():
    assert match_forbidden("toe taps", ["toe tap", "toe taps"]) == ["toe taps"]
    assert match_forbidden("hip hinge progression", ["hip hinge"]) == ["hip hinge"]
    assert match_forbidden("bench press", ["bench press", "press"]) == ["bench press"]


def test_match_forbidden_true_positives():
    assert match_forbidden("bench press", ["bench press"]) == ["bench press"]
    assert match_forbidden("overhead press", ["overhead press"]) == ["overhead press"]
    assert match_forbidden("push press", ["push press"]) == ["push press"]
    assert match_forbidden("snatch complex", ["snatch"]) == ["snatch"]
    assert match_forbidden("ring dip", ["ring dip"]) == ["ring dip"]


def test_match_forbidden_true_positives_by_region():
    shoulder_cases = [
        ("bench press", "bench press"),
        ("push press", "push press"),
        ("clean & press", "clean & press"),
        ("overhead carry", "overhead carry"),
        ("snatch", "snatch"),
    ]
    for text, pattern in shoulder_cases:
        assert match_forbidden(text, [pattern]) == [pattern]

    knee_cases = [("depth jump", "depth jump"), ("box jump", "box jump"), ("split jump", "split jump")]
    for text, pattern in knee_cases:
        assert match_forbidden(text, [pattern]) == [pattern]

    achilles_cases = [
        ("sprint", "sprint"),
        ("acceleration", "acceleration"),
        ("hill sprint", "hill sprint"),
        ("sled sprint", "sled sprint"),
    ]
    for text, pattern in achilles_cases:
        assert match_forbidden(text, [pattern]) == [pattern]


def test_infer_tags_from_name_avoids_substrings():
    assert infer_tags_from_name("Pressure Fighter's Cutoff Circuit") == set()


def test_injury_guard_real_exclusions_still_apply():
    shoulder_reasons = injury_violation_reasons(
        {"name": "Bench Press", "tags": []}, injuries=["shoulder injury"]
    )
    assert any("shoulder:tag:upper_push" in reason for reason in shoulder_reasons)

    overhead_reasons = injury_violation_reasons(
        {"name": "Overhead Carry", "tags": []}, injuries=["shoulder"]
    )
    assert any("shoulder:keyword:overhead carry" in reason for reason in overhead_reasons)

    no_false_positive = injury_violation_reasons(
        {"name": "Pressure Fighter's Cutoff Circuit", "tags": []},
        injuries=["shoulder"],
    )
    assert no_false_positive == []

    knee_reasons = injury_violation_reasons(
        {"name": "Box Jump", "tags": []}, injuries=["knee pain"]
    )
    assert any("knee:tag:high_impact_plyo" in reason for reason in knee_reasons)

    hip_reasons = injury_violation_reasons(
        {"name": "Hip Hinge Progression", "tags": []}, injuries=["hip impingement"]
    )
    assert any("hip:keyword:hip hinge" in reason for reason in hip_reasons)


def test_injury_guard_region_false_positives():
    knee_false_positive = injury_violation_reasons(
        {"name": "Sandbox Jumper Conditioning", "tags": []}, injuries=["knee pain"]
    )
    assert knee_false_positive == []

    hip_false_positive = injury_violation_reasons(
        {"name": "Ship Hinge Flow", "tags": []}, injuries=["hip impingement"]
    )
    assert hip_false_positive == []


def test_injury_guard_field_restrictions():
    name_only = {"name": "Pressure Fighter Stomp", "purpose": "bench press power", "tags": []}
    name_only_reasons = _drill_text_injury_reasons(name_only, ["shoulder injury"])
    assert name_only_reasons == []


def test_normalize_injury_regions_parses_phrases():
    assert normalize_injury_regions(["ACL tear"]) == {"knee"}
    assert normalize_injury_regions(["lumbar strain"]) == {"lower_back"}


def test_drill_text_filter_matches_notes_and_tags():
    keyword_drill = {"name": "Landing Primer", "notes": "Avoid hard landing", "tags": []}
    keyword_reasons = _drill_text_injury_reasons(keyword_drill, ["knee pain"])
    assert keyword_reasons
    assert any("hard landing" in reason["patterns"] for reason in keyword_reasons)

    tag_drill = {"name": "Vertical Throw", "notes": "", "tags": ["overhead"]}
    tag_reasons = _drill_text_injury_reasons(tag_drill, ["shoulder"])
    assert tag_reasons
    assert any("overhead" in reason["tags"] for reason in tag_reasons)


def test_injury_exclusion_map_contains_known_drill():
    exclusions = build_injury_exclusion_map()
    assert "exercise_bank:Barbell Overhead Press" in exclusions["shoulder"]


def test_audit_missing_tags_reports_totals():
    counts = audit_missing_tags()
    total = counts.pop("total")
    assert total == sum(counts.values())


def _make_drill(name: str, **overrides: str):
    base = {
        "name": name,
        "purpose": "",
        "timing": "",
        "equipment_note": "",
        "tags": [],
    }
    base.update(overrides)
    return base


def _filter_for_injuries(drills: list[dict], injuries: list[str]) -> list[dict]:
    return [
        drill
        for drill in drills
        if _is_drill_text_safe(drill, injuries, label="conditioning") and is_injury_safe(drill, injuries)
    ]


def test_integration_filtering_on_mini_bank():
    shoulder_false = [
        "Pressure Cooker",
        "Pressure Fighter's Cutoff Circuit",
        "Pressure Fighter Stomp",
        "Pressure Fighter Cutoff Hop",
    ]
    shoulder_true = [
        "Sandbag Clean & Press (ATP-PCr)",
        "Overhead Carry Complex",
        "Kettlebell Snatch Test",
        "Bench Press Isometric (110% 1RM @ 90° Elbow)",
    ]
    drills = [_make_drill(name) for name in shoulder_false + shoulder_true]
    filtered = _filter_for_injuries(drills, ["shoulder"])
    filtered_names = {d["name"] for d in filtered}
    assert set(shoulder_false).issubset(filtered_names)
    assert not any(name in filtered_names for name in shoulder_true)

    wrist_true = ["Handstand Hold", "Bear Crawl", "Snatch Balance"]
    wrist_false = ["Wrist Mobility Flow", "Grip Prep Circuit", "Bear Hug Walk"]
    wrist_drills = [_make_drill(name) for name in wrist_true + wrist_false]
    wrist_filtered = _filter_for_injuries(wrist_drills, ["wrist"])
    wrist_names = {d["name"] for d in wrist_filtered}
    assert set(wrist_false).issubset(wrist_names)
    assert not any(name in wrist_names for name in wrist_true)

    knee_true = ["Depth Jump Series", "Box Jump Repeats", "Split Jump Ladder"]
    knee_false = ["Jumping Jack Series", "Sandbox Jumper Conditioning", "Hip Hinge Flow"]
    knee_drills = [_make_drill(name) for name in knee_true + knee_false]
    knee_filtered = _filter_for_injuries(knee_drills, ["knee"])
    knee_names = {d["name"] for d in knee_filtered}
    assert set(knee_false).issubset(knee_names)
    assert not any(name in knee_names for name in knee_true)

    achilles_true = ["Max Sprint Intervals", "Depth Jump Waves", "Drop Jump Series"]
    achilles_false = ["Bike Tempo Ride", "Upper Body Cycle", "Pool Recovery"]
    achilles_drills = [_make_drill(name) for name in achilles_true + achilles_false]
    achilles_filtered = _filter_for_injuries(achilles_drills, ["achilles"])
    achilles_names = {d["name"] for d in achilles_filtered}
    assert set(achilles_false).issubset(achilles_names)
    assert not any(name in achilles_names for name in achilles_true)


def test_cross_bank_guard_consistency(monkeypatch):
    injuries = ["shoulder"]
    pressure_drills = [_make_drill("Pressure Cooker"), _make_drill("Pressure Fighter Stomp")]
    press_drills = [_make_drill("Bench Press Isometric"), _make_drill("Overhead Carry Complex")]

    conditioning_drills = pressure_drills + press_drills
    filtered_conditioning = _filter_for_injuries(conditioning_drills, injuries)
    filtered_names = {d["name"] for d in filtered_conditioning}
    assert set(d["name"] for d in pressure_drills).issubset(filtered_names)
    assert not any(d["name"] in filtered_names for d in press_drills)

    style_filtered = _filter_for_injuries(conditioning_drills, injuries)
    style_names = {d["name"] for d in style_filtered}
    assert set(d["name"] for d in pressure_drills).issubset(style_names)
    assert not any(d["name"] in style_names for d in press_drills)

    taper_filtered = _filter_for_injuries(conditioning_drills, injuries)
    taper_names = {d["name"] for d in taper_filtered}
    assert set(d["name"] for d in pressure_drills).issubset(taper_names)
    assert not any(d["name"] in taper_names for d in press_drills)

    coord_drills = [
        {
            **_make_drill("Pressure Fighter Coordination"),
            "phases": ["GPP"],
            "placement": "conditioning",
            "equipment": [],
        },
        {
            **_make_drill("Bench Press Coordination"),
            "phases": ["GPP"],
            "placement": "conditioning",
            "equipment": [],
        },
    ]
    monkeypatch.setattr("fightcamp.conditioning.coordination_bank", coord_drills)
    selection = select_coordination_drill(
        {"key_goals": ["coordination"], "phase": "GPP", "equipment": []},
        existing_names=set(),
        injuries=injuries,
    )
    assert selection is not None
    assert selection["name"] == "Pressure Fighter Coordination"

    strength_filtered = [drill for drill in press_drills + pressure_drills if is_injury_safe(drill, injuries)]
    strength_names = {d["name"] for d in strength_filtered}
    assert set(d["name"] for d in pressure_drills).issubset(strength_names)
    assert not any(d["name"] in strength_names for d in press_drills)


def test_injury_guard_log_deduped(capsys):
    _INJURY_GUARD_LOGGED.clear()
    drill = _make_drill("Bench Press Isometric")
    injuries = ["shoulder"]
    _is_drill_text_safe(drill, injuries, label="conditioning")
    _is_drill_text_safe(drill, injuries, label="conditioning")
    output = capsys.readouterr().out.strip().splitlines()
    guard_lines = [line for line in output if "[injury-guard]" in line]
    assert len(guard_lines) == 1


def test_regression_shoulders_exclusion_allowlist():
    excluded = [
        "Bench Press",
        "Incline Press",
        "Push Press",
        "Overhead Press",
        "Strict Press",
        "Military Press",
        "Overhead Carry",
        "Ring Dip",
        "Snatch Balance",
        "Jerk Complex",
    ]
    allowed = [
        "Pressure Cooker",
        "Pressure Fighter Stomp",
        "Footwork Ladder",
        "Bike Tempo Ride",
        "Shadowboxing Drill",
        "Core Rotation Flow",
        "Low Impact Mobility",
        "Breathing Reset",
        "Recovery Walk",
        "Skill Refinement Drill",
    ]
    for name in excluded:
        assert injury_violation_reasons({"name": name, "tags": []}, ["shoulder"])
    for name in allowed:
        assert injury_violation_reasons({"name": name, "tags": []}, ["shoulder"]) == []


def test_risk_levels_distinguish_flag_from_exclude(monkeypatch):
    test_rules = {
        "demo": {
            "ban_keywords": ["deadlift"],
            "ban_tags": [],
            "flag_keywords": ["carry"],
            "flag_tags": ["loaded_carry"],
        }
    }
    monkeypatch.setattr("fightcamp.injury_filtering.INJURY_RULES", test_rules)
    assert injury_violation_reasons({"name": "Deadlift", "tags": []}, ["demo"])
    assert injury_flag_reasons({"name": "Loaded Carry", "tags": ["loaded_carry"]}, ["demo"])
    assert injury_violation_reasons({"name": "Loaded Carry", "tags": ["loaded_carry"]}, ["demo"]) == []


def test_regression_sentinel_drills_per_region():
    sentinels = {
        "shoulder": {
            "excluded": [
                "Bench Press",
                "Incline Press",
                "Push Press",
                "Overhead Press",
                "Strict Press",
                "Military Press",
                "Overhead Carry",
                "Ring Dip",
                "Snatch Balance",
                "Jerk Complex",
                "Wall Ball Throws",
            ],
            "allowed": [
                "Pressure Cooker",
                "Pressure Fighter Stomp",
                "Footwork Ladder",
                "Bike Tempo Ride",
                "Shadowboxing Drill",
                "Core Rotation Flow",
                "Low Impact Mobility",
                "Breathing Reset",
                "Recovery Walk",
                "Skill Refinement Drill",
            ],
        },
        "ankle": {
            "excluded": [
                "Hard Cuts Drill",
                "Lateral Bounds Series",
                "Uneven Surface Run",
                "Depth Jump Series",
                "Hard Cuts Reaction",
                "Lateral Bounds Ladder",
                "Uneven Surface Hops",
                "Depth Jump Waves",
                "Hard Cuts and Go",
                "Lateral Bounds Repeats",
            ],
            "allowed": [
                "Bike Tempo Ride",
                "Rowing Tempo",
                "Upper Body Cycle",
                "Core Rotation Flow",
                "Shadowboxing Drill",
                "Mobility Reset",
                "Breathing Reset",
                "Low Impact Mobility",
                "Recovery Walk",
                "Pool Recovery",
            ],
        },
        "knee": {
            "excluded": [
                "Depth Jump Series",
                "Drop Jump Waves",
                "Hard Landing Primer",
                "Heavy Squat Waves",
                "Walking Lunge Ladder",
                "Split Squat Ladder",
                "Box Jump Repeats",
                "Jump Squat Waves",
                "Depth Jump Ladder",
                "Box Jump Series",
            ],
            "allowed": [
                "Bike Tempo Ride",
                "Upper Body Cycle",
                "Core Rotation Flow",
                "Shadowboxing Drill",
                "Breathing Reset",
                "Rowing Tempo",
                "Mobility Reset",
                "Recovery Walk",
                "Pool Recovery",
                "Low Impact Mobility",
            ],
        },
        "wrist": {
            "excluded": [
                "Push-Up Ladder",
                "Handstand Hold",
                "Front Rack Carry",
                "Power Clean",
                "Hang Clean",
                "Clean and Jerk",
                "Snatch Balance",
                "Bear Crawl",
                "Bear Crawl Flow",
                "Snatch Complex",
            ],
            "allowed": [
                "Bike Tempo Ride",
                "Rowing Tempo",
                "Shadowboxing Drill",
                "Footwork Ladder",
                "Core Rotation Flow",
                "Breathing Reset",
                "Recovery Walk",
                "Low Impact Mobility",
                "Pool Recovery",
                "Aerobic Bike",
            ],
        },
        "lower_back": {
            "excluded": [
                "Deadlift",
                "Romanian Deadlift",
                "Back Squat",
                "Good Morning",
                "Jefferson Curl",
                "Heavy Hinge Complex",
                "Deadlift Holds",
                "Romanian Deadlift Iso",
                "Back Squat Waves",
                "Good Morning Flow",
            ],
            "allowed": [
                "Bike Tempo Ride",
                "Rowing Tempo",
                "Upper Body Cycle",
                "Shadowboxing Drill",
                "Breathing Reset",
                "Footwork Ladder",
                "Core Rotation Flow",
                "Low Impact Mobility",
                "Recovery Walk",
                "Pool Recovery",
            ],
        },
    }
    for region, cases in sentinels.items():
        for name in cases["excluded"]:
            assert injury_violation_reasons({"name": name, "tags": []}, [region])
        for name in cases["allowed"]:
            assert injury_violation_reasons({"name": name, "tags": []}, [region]) == []
