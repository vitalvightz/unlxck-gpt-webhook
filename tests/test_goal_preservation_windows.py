"""Development windows must cover a real development week, not a stray remainder.

`_requirements` anchors windows at the countdown cutoff and counts outward, so
any remainder lands at the far end - the opening days of camp. Rounding the
window count up turned that remainder into its own requirement, demanding a
full development-week exposure from a sliver that can be a single day. Every
plan for a 21/22-day camp failed goal preservation for this reason.
"""
import pytest

from fightcamp.goal_preservation import _requirements


def _windows(days, state="build", goal="conditioning"):
    entry = {"goal": goal, "state": state}
    brief = {"athlete_snapshot": {"days_until_fight": days}}
    return [(w["min_d_day"], w["max_d_day"]) for w in _requirements(entry, brief)]


# 27 days is exactly two full weeks past the cutoff, so it legitimately
# yields two windows and is covered by the full-week test below.
@pytest.mark.parametrize("days", [14, 15, 20, 21, 22, 26])
def test_short_camps_ask_for_one_window_not_a_sliver(days):
    windows = _windows(days)
    assert len(windows) == 1
    assert windows[0] == (14, days)


def test_full_weeks_still_get_their_own_window():
    assert _windows(28) == [(14, 20), (21, 28)]
    assert _windows(35) == [(14, 20), (21, 27), (28, 35)]


def test_no_window_is_narrower_than_a_development_week():
    """The remainder is absorbed by the earliest window, never left standalone."""
    for days in range(14, 70):
        windows = _windows(days)
        assert windows[-1][1] == days, days
        for low, high in windows[:-1]:
            assert high - low + 1 == 7, (days, low, high)
        # Only the absorbing window may exceed a week; none may be shorter.
        assert windows[-1][1] - windows[-1][0] + 1 >= 1
        if len(windows) > 1:
            assert windows[-1][1] - windows[-1][0] + 1 >= 7, days


def test_windows_are_contiguous_and_start_at_the_cutoff():
    windows = _windows(45)
    assert windows[0][0] == 14
    for earlier, later in zip(windows, windows[1:]):
        assert later[0] == earlier[1] + 1
