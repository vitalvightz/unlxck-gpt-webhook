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


def _derive(completions=None, current=TODAY, current_phase=None):
    return derive_injury_signal(
        completions=completions or [],
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
    # below ELEVATED, so no trend fires.
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


def test_old_elevated_reading_does_not_create_a_stale_reminder():
    # Current injury and check-in signals own today's advice. History must not
    # add a generic "days since" message beside newer information.
    assert _derive(completions=[_completion("2026-06-16", pain_after=5)]) == []


def test_high_latest_reading_beats_older_elevated_reading():
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
