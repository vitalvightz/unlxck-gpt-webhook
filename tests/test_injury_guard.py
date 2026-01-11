import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import injury_violation_reasons, match_forbidden


def test_match_forbidden_avoids_substrings():
    assert match_forbidden("Pressure Fighter", ["press"]) == []
    assert match_forbidden("pressuring drills", ["press"]) == []
    assert match_forbidden("pressure cooker", ["press"]) == []
    assert match_forbidden("skipping rope", ["kipping"]) == []
    assert match_forbidden("membership plan", ["hip"]) == []
    assert match_forbidden("stomach ache", ["toe"]) == []


def test_match_forbidden_respects_phrases():
    assert match_forbidden("toe taps", ["toe tap", "toe taps"]) == ["toe taps"]
    assert match_forbidden("hip hinge progression", ["hip hinge"]) == ["hip hinge"]


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
        {"name": "Pressure Fighter", "tags": []}, injuries=["shoulder"]
    )
    assert no_false_positive == []
