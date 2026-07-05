"""Tests for the context-aware Today readiness message engine."""

from api.contracts.readiness_message import (
    ReadinessCheckin,
    ReadinessContext,
    build_readiness_adjustment,
    classify_session_risk,
)


def _message_lines(adjustment):
    return adjustment.message.splitlines()


def _assert_card_shape(adjustment):
    lines = _message_lines(adjustment)
    assert 3 <= len(lines) <= 4
    assert all(line.endswith(".") for line in lines)
    assert len(adjustment.message.split()) <= 55
    assert adjustment.title
    assert adjustment.reason
    assert adjustment.action


def _session(**overrides):
    return {
        "title": "Strength session",
        "session_type": "strength",
        "effective_load": "technical",
        **overrides,
    }


def test_session_risk_classifies_core_terms():
    assert classify_session_risk(_session(title="Mobility and easy aerobic bike")) == "low"
    assert classify_session_risk(_session(title="Moderate strength accessories")) == "medium"
    assert classify_session_risk(_session(title="Heavy lower body and hard conditioning")) == "high"


def test_red_flag_always_returns_no_training_today():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="sharp", pain="none", sharp_pain=True),
        ReadinessContext(today_session=_session(title="Easy mobility")),
    )

    assert adjustment.decision == "pull_back"
    assert adjustment.title == "No training today."
    assert "red flag" in adjustment.reason
    assert "seek medical advice" in adjustment.action
    _assert_card_shape(adjustment)


def test_injury_worse_overrides_good_sleep_and_motivation_signals():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="sharp", pain="none", active_injury="worse"),
        ReadinessContext(today_session=_session(title="Full session")),
    )

    assert adjustment.decision == "pull_back"
    assert adjustment.title == "Rehab only today."
    assert "injury is worse" in adjustment.reason
    assert "sparring" in adjustment.action
    assert "hard bag work" in adjustment.action
    _assert_card_shape(adjustment)


def test_high_pain_returns_rehab_only_guidance():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="high"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
    )

    assert adjustment.decision == "pull_back"
    assert adjustment.title == "Rehab only today."
    assert "Pain is high" in adjustment.reason
    assert "rehab or easy mobility" in adjustment.action
    _assert_card_shape(adjustment)


def test_poor_sleep_removes_one_set_or_reduces_volume():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(today_session=_session(title="Moderate strength")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.title == "Session reduced."
    assert "Poor sleep" in adjustment.reason
    assert "Cut 1 round" in adjustment.action
    assert "set" not in adjustment.message.lower()
    _assert_card_shape(adjustment)


def test_flat_body_caps_intensity():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(body="flat"),
        ReadinessContext(today_session=_session(title="Moderate strength")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.title == "Intensity capped."
    assert "flat body" in adjustment.reason.lower()
    assert "all-out work" in adjustment.action
    _assert_card_shape(adjustment)


def test_poor_sleep_plus_flat_body_gives_stronger_reduction():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat"),
        ReadinessContext(today_session=_session(title="Heavy lower body plyometrics")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.title == "Session reduced."
    assert "Poor sleep plus a flat body" in adjustment.reason
    assert "sparring" in adjustment.action
    assert "hard rounds" in adjustment.action
    assert "conditioning finishers" in adjustment.action
    _assert_card_shape(adjustment)


def test_taper_produces_freshness_first_wording():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.title == "Session reduced."
    assert "sharpness" in adjustment.reason
    assert "speed" in adjustment.action
    assert "timing" in adjustment.action
    _assert_card_shape(adjustment)


def test_taper_poor_flat_manageable_pain_pulls_back_without_modify_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="manageable", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "pull_back"
    assert "Pull back today." in adjustment.message
    assert "recovery day" in adjustment.message
    assert "Skip combat work" in adjustment.message
    assert "Keep sharp work only" not in adjustment.message
    assert "Remove 1 set" not in adjustment.message
    assert "fatigue-heavy accessories" not in adjustment.message
    _assert_card_shape(adjustment)


def test_repeated_poor_readiness_adds_stronger_warning():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=[
                {"training_day": "2026-06-17", "recommendation_state": "modify"},
                {"training_day": "2026-06-16", "sleep": "poor"},
            ],
            today_session=_session(title="Moderate strength"),
        ),
    )

    assert adjustment.decision == "modify"
    assert "body is not bouncing back" in adjustment.reason
    assert "Cut rounds and intensity" in adjustment.action
    _assert_card_shape(adjustment)


def test_high_risk_combat_session_uses_combat_reduction_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
    )

    assert adjustment.decision == "modify"
    assert "sparring" in adjustment.action
    assert "hard rounds" in adjustment.action
    assert "conditioning finishers" in adjustment.action
    _assert_card_shape(adjustment)


def test_flat_body_high_risk_uses_bag_or_max_output_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(body="flat"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
    )

    assert adjustment.decision == "modify"
    assert "hard bag rounds" in adjustment.action or "max-output conditioning" in adjustment.action
    _assert_card_shape(adjustment)


def test_manageable_pain_high_risk_uses_contact_protection_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
    )

    assert adjustment.decision == "modify"
    assert "clinch pressure" in adjustment.action or "hard bag work" in adjustment.action
    _assert_card_shape(adjustment)


def test_hyphenated_combat_sports_are_recognized_for_contact_guidance():
    for style in ("muay-thai", "jiu-jitsu"):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(sleep="poor"),
            ReadinessContext(
                intake={"athlete": {"technical_style": [style]}},
                today_session=_session(title="Sparring and hard conditioning"),
            ),
        )

        assert adjustment.decision == "modify"
        assert "contact_sport" in adjustment.triggers
        assert "contact rounds" in adjustment.action
        _assert_card_shape(adjustment)


def test_past_fight_date_does_not_trigger_fight_week_message():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none", phase="GPP"),
        ReadinessContext(
            training_day="2026-06-18",
            active_plan={"fight_date": "2026-06-15"},
            today_session=_session(title="Strength session"),
        ),
    )

    assert adjustment.decision == "train_as_planned"
    assert adjustment.title == "Full session."
    assert "fight_week" not in adjustment.triggers
    assert "Fight week" not in adjustment.message
    _assert_card_shape(adjustment)


def test_fight_week_uses_timing_speed_and_rhythm_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none", phase="GPP"),
        ReadinessContext(
            training_day="2026-06-18",
            active_plan={"fight_date": "2026-06-21"},
            today_session=_session(title="Technical boxing rounds"),
        ),
    )

    assert adjustment.decision == "train_as_planned"
    assert adjustment.title == "Sharp work only."
    assert "Fight week rewards freshness" in adjustment.reason
    assert "timing, speed, and rhythm" in adjustment.action
    _assert_card_shape(adjustment)


def test_message_explains_change_reason_and_next_action_without_filler():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat"),
        ReadinessContext(today_session=_session(title="Hard conditioning")),
    )

    lines = _message_lines(adjustment)
    assert lines[0] == "Session reduced."
    assert "so" not in lines[0].lower()
    assert "listen to your body" not in adjustment.message.lower()
    assert "consider modifying" not in adjustment.message.lower()
    assert "based on your readiness" not in adjustment.message.lower()
    _assert_card_shape(adjustment)


def test_readiness_messages_do_not_use_old_general_training_terms():
    scenarios = [
        (
            ReadinessCheckin(sleep="poor"),
            ReadinessContext(today_session=_session(title="Moderate strength")),
        ),
        (
            ReadinessCheckin(sleep="poor"),
            ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
        ),
        (
            ReadinessCheckin(body="flat"),
            ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
        ),
        (
            ReadinessCheckin(pain="manageable"),
            ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
        ),
        (
            ReadinessCheckin(sleep="poor", phase="TAPER"),
            ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
        ),
        (
            ReadinessCheckin(sleep="poor", body="flat", pain="manageable", phase="TAPER"),
            ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
        ),
    ]
    banned = (
        "plyos",
        "sprinting",
        "heavy lower-body",
        "tissue margin",
        "recovery margin",
        "fatigue-heavy accessories",
        "Remove 1 set",
    )

    for checkin, context in scenarios:
        message = build_readiness_adjustment(checkin, context).message
        for phrase in banned:
            assert phrase not in message
