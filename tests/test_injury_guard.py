import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import (
    infer_tags_from_name,
    injury_violation_reasons,
    match_forbidden,
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


def test_infer_tags_from_name_avoids_substrings():
    assert infer_tags_from_name("Pressure Fighter's Cutoff Circuit") == set()


def test_injury_guard_real_exclusions_still_apply():
    shoulder_reasons = injury_violation_reasons(
        {"name": "Bench Press", "tags": []}, injuries=["shoulder injury"]
    )
    assert any("shoulder:keyword:bench press" in reason for reason in shoulder_reasons)

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
    assert any("knee:keyword:box jump" in reason for reason in knee_reasons)

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
