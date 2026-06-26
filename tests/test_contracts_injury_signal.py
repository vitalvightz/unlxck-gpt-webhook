"""Unit tests for the derived injury-risk signal (api/contracts/injury_signal).

Pure/deterministic: no store, no clock — every case is fixed dates + logged rows.
"""

from api.contracts.injury_signal import (
    HIGH_PAIN_AFTER,
    derive_injury_signal,
)

TODAY = "2026-06-18"


def _completion(day: str, pain_after=None, status: str = "done") -> dict:
    return {"training_day": day, "pain_after": pain_after, "status": status}


def _checkin(day: str, *, pain: str = "none", active_injury: str = "none") -> dict:
    return {"training_day": day, "pain": pain, "active_injury": active_injury}


def _derive(completions=None, checkins=None, current=TODAY, current_phase=None):
    return derive_injury_signal(
        completions=completions or [],
        checkins=checkins or [],
        current_training_day=current,
        current_phase=current_phase,
    )


def test_no_history_yields_no_signal():
    assert _derive() == []


def test_empty_pain_after_is_ignored():
    # A logged session with no pain reading is not a symptom.
    assert _derive(completions=[_completion(TODAY, pain_after=None)]) == []


def test_high_last_reading_escalates():
    risks = _derive(completions=[_completion(TODAY, pain_after=HIGH_PAIN_AFTER)])
    assert len(risks) == 1
    assert risks[0].category == "high_pain"
    assert "7/10" in risks[0].text
    assert "Ease into load and reassess." in risks[0].text


def test_taper_high_last_reading_uses_freshness_wording():
    risks = _derive(
        completions=[_completion(TODAY, pain_after=HIGH_PAIN_AFTER)],
        current_phase="TAPER",
    )
    assert len(risks) == 1
    assert risks[0].category == "high_pain"
    assert "Keep today minimal, protect freshness, and reassess." in risks[0].text
    assert "Ease into load" not in risks[0].text


def test_rising_trend_flags_pain_delta():
    risks = _derive(
        completions=[
            _completion("2026-06-16", pain_after=2),
            _completion("2026-06-17", pain_after=5),
        ]
    )
    assert len(risks) == 1
    assert risks[0].category == "high_pain"
    assert "2/10 -> 5/10" in risks[0].text


def test_small_rise_is_not_a_trend():
    # 1 -> 2 is only a +1 delta (below PAIN_RISE_DELTA) and both readings sit
    # below ELEVATED, so neither a trend nor a symptom day fires.
    assert _derive(
        completions=[
            _completion("2026-06-16", pain_after=1),
            _completion("2026-06-17", pain_after=2),
        ]
    ) == []


def test_worst_reading_per_day_prevents_fake_trend():
    # Two sessions the same day must collapse to that day's worst reading, so a
    # later low single session cannot read as a drop/rise against an intra-day pair.
    risks = _derive(
        completions=[
            _completion("2026-06-17", pain_after=1),
            _completion("2026-06-17", pain_after=2),
            _completion("2026-06-18", pain_after=5),
        ]
    )
    # 2 (worst of the 17th) -> 5 on the 18th is a +3 rise.
    assert len(risks) == 1
    assert "2/10 -> 5/10" in risks[0].text


def test_recent_symptom_decays_with_reminder():
    # Elevated pain two days ago, nothing since -> a decaying reminder today.
    risks = _derive(completions=[_completion("2026-06-16", pain_after=5)])
    assert len(risks) == 1
    assert risks[0].category == "reminder"
    assert "2 days since" in risks[0].text


def test_recent_symptom_decay_reminder_is_suppressed_in_taper():
    risks = _derive(
        completions=[_completion("2026-06-16", pain_after=5)],
        current_phase="TAPER",
    )
    assert risks == []


def test_symptom_one_day_ago_uses_singular_day():
    risks = _derive(checkins=[_checkin("2026-06-17", pain="high")])
    assert len(risks) == 1
    assert risks[0].category == "reminder"
    assert "1 day since" in risks[0].text


def test_same_day_symptom_is_not_a_decay_reminder():
    # A symptom logged *today* is the same-day check-in's job, not the decay echo.
    assert _derive(checkins=[_checkin(TODAY, pain="high")]) == []


def test_old_symptom_past_decay_window_is_silent():
    # Five days clean is past SYMPTOM_DECAY_DAYS — green should mean green again.
    assert _derive(completions=[_completion("2026-06-13", pain_after=5)]) == []


def test_active_injury_worse_counts_as_symptom():
    risks = _derive(checkins=[_checkin("2026-06-16", active_injury="worse")])
    assert len(risks) == 1
    assert risks[0].category == "reminder"


def test_escalation_beats_decay_when_both_present():
    risks = _derive(
        completions=[
            _completion("2026-06-15", pain_after=5),
            _completion(TODAY, pain_after=HIGH_PAIN_AFTER),
        ]
    )
    assert len(risks) == 1
    assert risks[0].category == "high_pain"


def test_history_outside_lookback_window_ignored():
    assert _derive(completions=[_completion("2026-05-01", pain_after=9)]) == []


def test_malformed_current_day_is_safe():
    assert _derive(completions=[_completion(TODAY, pain_after=9)], current="not-a-date") == []


def test_out_of_range_and_bool_pain_values_ignored():
    assert _derive(completions=[_completion(TODAY, pain_after=99)]) == []
    assert _derive(completions=[_completion(TODAY, pain_after=True)]) == []


def test_float_string_pain_values_are_coerced():
    risks = _derive(completions=[_completion(TODAY, pain_after=" 7.5 ")])
    assert len(risks) == 1
    assert risks[0].category == "high_pain"
    assert "7/10" in risks[0].text
