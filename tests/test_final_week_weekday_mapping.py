"""Unit tests for final-week countdown-to-real-weekday mapping.

Covers:
- _fight_weekday_from_context  – computes the fight's real weekday from the
  plan-creation weekday and days_until_fight.
- _countdown_weekday_map       – anchors the fight date and maps each D-N label
  to its real weekday.
- _nearest_available_day       – finds the closest available day for a given
  target weekday.
- can_render_late_taper_day – filters which countdown labels are eligible for
  app-owned rendering without remapping calendar weekdays.
- Session sequence weekday/label annotation applied in
  _build_late_fight_session_sequence.
"""

from __future__ import annotations


from fightcamp.stage2_payload_late_fight import (
    _build_late_fight_session_sequence,
    _countdown_weekday_map,
    _fight_weekday_from_context,
    _nearest_available_day,
    can_render_late_taper_day,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _athlete(days_until_fight: int, **overrides) -> dict:
    base = {
        "days_until_fight": days_until_fight,
        "fatigue": "moderate",
        "readiness_flags": [],
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": ["tuesday", "thursday"],
        "support_work_days": ["friday"],
        "plan_creation_weekday": "monday",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _fight_weekday_from_context
# ---------------------------------------------------------------------------

class TestFightWeekdayFromContext:
    def test_basic_monday_plus_5_gives_saturday(self):
        result = _fight_weekday_from_context("monday", 5)
        assert result == "saturday"

    def test_friday_plus_2_gives_sunday(self):
        result = _fight_weekday_from_context("friday", 2)
        assert result == "sunday"

    def test_wednesday_plus_0_gives_wednesday(self):
        result = _fight_weekday_from_context("wednesday", 0)
        assert result == "wednesday"

    def test_saturday_plus_1_gives_sunday(self):
        result = _fight_weekday_from_context("saturday", 1)
        assert result == "sunday"

    def test_sunday_plus_7_wraps_to_sunday(self):
        result = _fight_weekday_from_context("sunday", 7)
        assert result == "sunday"

    def test_thursday_plus_3_gives_sunday(self):
        result = _fight_weekday_from_context("thursday", 3)
        assert result == "sunday"

    def test_case_insensitive_plan_creation_weekday(self):
        assert _fight_weekday_from_context("Monday", 5) == "saturday"
        assert _fight_weekday_from_context("FRIDAY", 2) == "sunday"

    def test_short_form_weekday_is_accepted(self):
        assert _fight_weekday_from_context("mon", 5) == "saturday"
        assert _fight_weekday_from_context("fri", 2) == "sunday"

    def test_returns_none_for_none_weekday(self):
        assert _fight_weekday_from_context(None, 5) is None

    def test_returns_none_for_empty_string_weekday(self):
        assert _fight_weekday_from_context("", 5) is None

    def test_returns_none_for_unknown_weekday(self):
        assert _fight_weekday_from_context("funday", 5) is None

    def test_returns_none_for_negative_days(self):
        assert _fight_weekday_from_context("monday", -1) is None

    def test_returns_none_for_non_integer_days(self):
        assert _fight_weekday_from_context("monday", "not_a_number") is None
        assert _fight_weekday_from_context("monday", None) is None


# ---------------------------------------------------------------------------
# _countdown_weekday_map
# ---------------------------------------------------------------------------

class TestCountdownWeekdayMap:
    def test_monday_creation_saturday_fight_5_days_out(self):
        # Plan created Monday, fight on Saturday (5 days later)
        result = _countdown_weekday_map("monday", 5)
        assert result == {
            "D-0": "saturday",
            "D-1": "friday",
            "D-2": "thursday",
            "D-3": "wednesday",
            "D-4": "tuesday",
            "D-5": "monday",
        }

    def test_d0_maps_to_fight_day(self):
        result = _countdown_weekday_map("wednesday", 3)
        assert result["D-0"] == "saturday"

    def test_only_days_up_to_days_until_fight_are_included(self):
        result = _countdown_weekday_map("thursday", 2)
        assert set(result.keys()) == {"D-0", "D-1", "D-2"}

    def test_d7_includes_all_eight_labels(self):
        result = _countdown_weekday_map("sunday", 7)
        assert set(result.keys()) == {"D-0", "D-1", "D-2", "D-3", "D-4", "D-5", "D-6", "D-7"}

    def test_d0_returns_single_entry(self):
        result = _countdown_weekday_map("friday", 0)
        assert result == {"D-0": "friday"}

    def test_returns_empty_for_none_weekday(self):
        assert _countdown_weekday_map(None, 5) == {}

    def test_returns_empty_for_invalid_days(self):
        assert _countdown_weekday_map("monday", "bad") == {}

    def test_weekday_wrap_around_sunday(self):
        # Friday creation + 3 days = Monday fight
        result = _countdown_weekday_map("friday", 3)
        assert result["D-0"] == "monday"
        assert result["D-1"] == "sunday"
        assert result["D-2"] == "saturday"
        assert result["D-3"] == "friday"

    def test_not_capped_at_seven_days(self):
        # Countdown map must project all the way back to D-N, not stop at D-7.
        result = _countdown_weekday_map("monday", 10)
        assert len(result) == 11
        assert set(result.keys()) == {f"D-{n}" for n in range(0, 11)}
        assert result["D-10"] == "monday"

    def test_2026_05_09_countdown_anchor_weekdays(self):
        # Fight date Saturday 2026-05-09; D-14 is Saturday 2026-04-25.
        result = _countdown_weekday_map("saturday", 14)
        assert result["D-14"] == "saturday"
        assert result["D-13"] == "sunday"
        assert result["D-7"] == "saturday"
        assert result["D-5"] == "monday"
        assert result["D-3"] == "wednesday"
        assert result["D-1"] == "friday"
        assert result["D-0"] == "saturday"


# ---------------------------------------------------------------------------
# _nearest_available_day
# ---------------------------------------------------------------------------

class TestNearestAvailableDay:
    def test_target_is_available_returns_target(self):
        result = _nearest_available_day("wednesday", ["monday", "wednesday", "friday"])
        assert result == "wednesday"

    def test_nearest_forward_when_target_unavailable(self):
        # Target = tuesday (index 1), available = [monday (0), thursday (3)]
        # delta=1: forward=wednesday(2) not available; backward=monday(0) available → monday returned
        result = _nearest_available_day("tuesday", ["monday", "thursday"])
        assert result == "monday"

    def test_nearest_backward_beats_farther_forward(self):
        # Target = saturday, available = [monday, friday]
        # Forward: sunday (not), monday (avail, delta=2)
        # Backward: friday (avail, delta=1) → friday wins
        result = _nearest_available_day("saturday", ["monday", "friday"])
        assert result == "friday"

    def test_returns_none_for_empty_available_days(self):
        result = _nearest_available_day("monday", [])
        assert result is None

    def test_single_available_day_is_always_returned(self):
        result = _nearest_available_day("friday", ["wednesday"])
        assert result == "wednesday"

    def test_case_insensitive(self):
        # The function normalises inputs to lowercase internally and returns lowercase
        result = _nearest_available_day("WEDNESDAY", ["Monday", "WEDNESDAY", "Friday"])
        assert result is not None
        assert result.lower() == "wednesday"


# ---------------------------------------------------------------------------
# can_render_late_taper_day
# ---------------------------------------------------------------------------

class TestCanRenderLateTaperDay:
    def test_d1_to_d6_respect_declared_availability_but_d0_is_always_legal(self):
        assert can_render_late_taper_day(countdown_offset=6, weekday="monday", training_days=["tuesday"]) is False
        assert can_render_late_taper_day(countdown_offset=1, weekday="saturday", training_days=["tuesday"]) is False
        assert can_render_late_taper_day(countdown_offset=0, weekday="sunday", training_days=[])

    def test_d7_and_earlier_requires_training_day_match(self):
        assert can_render_late_taper_day(countdown_offset=7, weekday="sunday", training_days=["tuesday"]) is False
        assert can_render_late_taper_day(countdown_offset=12, weekday="tuesday", training_days=["tuesday"]) is True


# ---------------------------------------------------------------------------
# Session sequence countdown_label and real_weekday annotations
# ---------------------------------------------------------------------------

class TestSessionSequenceWeekdayAnnotation:
    def test_d5_sequence_includes_countdown_label(self):
        athlete = _athlete(5, plan_creation_weekday="monday")
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert len(sequence) >= 1
        assert sequence[0]["countdown_label"] == "D-3"

    def test_d5_sequence_includes_real_weekday(self):
        # Monday creation + 5 days = Saturday fight; D-5 = Monday
        athlete = _athlete(5, plan_creation_weekday="monday")
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert sequence[0]["real_weekday"] == "wednesday"
        assert sequence[0]["countdown_display_label"] == "D-3 (Wednesday)"

    def test_d5_first_role_is_alactic_sharpness(self):
        athlete = _athlete(5, plan_creation_weekday="monday")
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert sequence[0]["role_key"] == "fight_week_freshness_day"

    def test_d3_default_sequence_has_freshness_only_for_short_notice(self):
        athlete = _athlete(
            3,
            plan_creation_weekday="wednesday",
            fatigue="low",
            readiness_flags=["fight_week", "short_notice"],
        )
        sequence = _build_late_fight_session_sequence(3, athlete)
        role_keys = [entry["role_key"] for entry in sequence]
        assert role_keys == ["fight_week_freshness_day", "neural_primer_day"]

    def test_d3_default_sequence_has_alactic_and_freshness_without_short_notice(self):
        athlete = _athlete(3, plan_creation_weekday="wednesday", fatigue="moderate", readiness_flags=[])
        sequence = _build_late_fight_session_sequence(3, athlete)
        role_keys = [entry["role_key"] for entry in sequence]
        assert role_keys == ["fight_week_freshness_day", "neural_primer_day"]

    def test_sequence_does_not_invent_days_when_calendar_anchor_is_missing(self):
        athlete = _athlete(5)
        del athlete["plan_creation_weekday"]
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert sequence == []

    def test_unavailable_countdown_day_is_skipped_not_remapped(self):
        # Friday creation + five days means D-3 is Sunday. Sunday is not an
        # available training day, so no app-owned role may be moved from D-3
        # onto Monday while retaining the D-3 label.
        athlete = _athlete(
            5,
            plan_creation_weekday="friday",
            training_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert sequence
        assert all(entry.get("scheduled_countdown_label") != "D-3" for entry in sequence)
        assert all("resolved_training_weekday" not in entry for entry in sequence)

    def test_display_labels_only_use_real_available_countdown_weekdays(self):
        athlete = _athlete(
            5,
            plan_creation_weekday="friday",
            training_days=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        )
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert all(entry.get("scheduled_countdown_label") != "D-3" for entry in sequence)
        assert all("resolved_training_weekday" not in entry for entry in sequence)
        assert all(
            entry.get("countdown_display_label")
            == f'{entry["scheduled_countdown_label"]} ({entry["real_weekday"].title()})'
            for entry in sequence
            if entry.get("scheduled_countdown_label") and entry.get("real_weekday")
        )

    def test_countdown_label_absent_when_days_none(self):
        athlete = _athlete(5, plan_creation_weekday="monday")
        athlete["days_until_fight"] = None
        sequence = _build_late_fight_session_sequence(None, athlete)
        for entry in sequence:
            assert "countdown_label" not in entry
