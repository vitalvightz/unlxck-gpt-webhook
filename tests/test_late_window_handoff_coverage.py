"""Stage 1 must hand over candidates legal for the windows its camp will reach.

Stage 1 selects by phase; the dated late-fight selector admits a candidate only
when the bank opts that exercise into the role's countdown window. Nothing
reconciled the two, so a 22-day camp handed over a pool in which 1 of 34 slots
was usable at D-13..D-8 and shipped empty physical sessions.

The handoff now carries reservoir candidates that are legal for a window the camp
actually reaches. Stage 1 had already qualified and scored them - this only stops
the handoff discarding its own coverage. Nothing new is selected, and no second
selector is introduced.
"""
import pytest

from fightcamp.late_selector_windows import (
    classify_late_selector_window,
    late_windows_spanned,
    required_late_windows,
)


def test_only_windows_the_camp_reaches_are_required():
    assert late_windows_spanned(3) == {"d4_to_d2", "d1"}
    assert late_windows_spanned(5) == {"d6_to_d5", "d4_to_d2", "d1"}
    assert late_windows_spanned(7) == {"d7", "d6_to_d5", "d4_to_d2", "d1"}
    # A short camp never demands coverage for a window it cannot schedule.
    assert "d13_to_d8" not in late_windows_spanned(7)
    assert "d21_to_d14" not in late_windows_spanned(13)


def test_long_camps_require_every_window_their_tail_owns():
    assert late_windows_spanned(22) == {
        "d21_to_d14", "d13_to_d8", "d7", "d6_to_d5", "d4_to_d2", "d1",
    }
    assert late_windows_spanned(60) == late_windows_spanned(22)


@pytest.mark.parametrize("bad", [None, "", "soon", -1])
def test_unknown_camp_length_requires_nothing(bad):
    assert late_windows_spanned(bad) == set()


def test_spanned_windows_agree_with_the_canonical_classifier():
    for days in range(0, 40):
        for offset in range(0, days + 1):
            window = classify_late_selector_window(offset)
            if window:
                assert window in late_windows_spanned(days), (days, offset)


def test_required_windows_read_the_roles_a_camp_actually_scheduled():
    roles = [
        {"scheduled_countdown_label": "D-13"},
        {"scheduled_countdown_label": "D-11"},
        {"countdown_offset": 6},
        {"scheduled_countdown_label": "not-a-label"},
        {},
    ]
    assert required_late_windows(roles) == {"d13_to_d8", "d6_to_d5"}
    assert required_late_windows([]) == set()


def test_handoff_carries_reservoir_candidates_legal_for_a_required_window():
    from fightcamp.stage2_payload import _build_late_tail_candidates

    block = {
        "candidate_reservoir": {
            "aerobic": [
                {
                    "drill": {
                        "name": "Window Legal Flow",
                        "system": "aerobic",
                        "late_windows": ["d13_to_d8", "d7"],
                        "duration": "12min continuous",
                    },
                    "explanation": "",
                },
                {
                    "drill": {
                        "name": "Not Legal Here",
                        "system": "aerobic",
                        "late_windows": ["d1"],
                        "duration": "5min continuous",
                    },
                    "explanation": "",
                },
            ]
        }
    }
    carried = _build_late_tail_candidates(
        block, "GPP", required_windows={"d13_to_d8"}
    )
    names = [slot["selected"]["name"] for slot in carried]
    assert names == ["Window Legal Flow"]


def test_handoff_carries_nothing_extra_when_no_window_is_required():
    from fightcamp.stage2_payload import _build_late_tail_candidates

    block = {
        "candidate_reservoir": {
            "aerobic": [
                {
                    "drill": {
                        "name": "Window Legal Flow",
                        "system": "aerobic",
                        "late_windows": ["d13_to_d8"],
                        "duration": "12min continuous",
                    },
                    "explanation": "",
                }
            ]
        }
    }
    assert _build_late_tail_candidates(block, "GPP", required_windows=set()) == []
