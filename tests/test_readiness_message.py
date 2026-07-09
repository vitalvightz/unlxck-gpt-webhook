"""Tests for the context-aware Today readiness message engine."""

from api.contracts.readiness_message import (
    ReadinessCheckin,
    ReadinessContext,
    build_readiness_adjustment,
    classify_session_risk,
    is_support_session,
)


def _message_lines(adjustment):
    return adjustment.message.splitlines()


def _assert_card_shape(adjustment):
    lines = _message_lines(adjustment)
    assert 3 <= len(lines) <= 4
    assert all(line.endswith(".") for line in lines)
    assert len(adjustment.message.split()) <= 75
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


def _prior_checkins(*rows):
    return list(rows)


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


# ---------------------------------------------------------------------------
# Type-aware injury × session matrix. `consequence` is the coarse tier the Today
# service attaches from the shared taxonomy (neuro / structural / load_sensitive /
# None). Set explicitly here so the matrix is deterministic and NLP-independent.
# ---------------------------------------------------------------------------


def _injury(consequence, severity="moderate", *, status="open", label="left knee", worse=False):
    return {
        "status": status,
        "severity": severity,
        "consequence": consequence,
        "label": label,
        "latest_reported_status": "worse" if worse else "ongoing",
    }


def _decision(title, injuries):
    return build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=_session(title=title), open_injuries=tuple(injuries)),
    )


def test_neuro_injury_pulls_back_on_every_session():
    for title in ("Recovery mobility", "Technical skill drilling", "Hard sparring"):
        adj = _decision(title, [_injury("neuro", "mild", label="neck nerve issue")])
        assert adj.decision == "pull_back", title
        assert adj.title == "Rehab only today."
        _assert_card_shape(adj)


def test_structural_moderate_injury_scales_by_session_exposure():
    rib = [_injury("structural", "moderate", label="rib")]
    assert _decision("Clinch and wrestling", rib).decision == "pull_back"
    assert _decision("Technical skill drilling", rib).decision == "pull_back"
    assert _decision("Recovery mobility", rib).decision == "modify"


def test_load_sensitive_injury_scales_by_session_exposure():
    tendon = [_injury("load_sensitive", "moderate", label="knee tendon")]
    assert _decision("HIIT conditioning circuit", tendon).decision == "pull_back"
    assert _decision("Bag work and heavy bag rounds", tendon).decision == "pull_back"
    assert _decision("Technical skill drilling", tendon).decision == "modify"
    assert _decision("Recovery mobility", tendon).decision == "train_as_planned"


def test_minor_surface_injury_never_stops_training():
    graze = [_injury(None, "mild", label="knuckle graze")]
    # A hard session may be trimmed to a modify, but a minor surface injury must
    # never force a stop, and a light session stays green.
    assert _decision("Hard sparring", graze).decision in {"modify", "train_as_planned"}
    assert _decision("Hard sparring", graze).decision != "pull_back"
    assert _decision("Recovery mobility", graze).decision == "train_as_planned"


def test_green_copy_never_claims_clear_while_injured():
    adj = _decision("Recovery mobility", [_injury(None, "mild", label="knuckle graze")])
    assert adj.decision == "train_as_planned"
    assert "knuckle graze" in adj.reason
    assert adj.reason != "Your sleep, body, and pain checks are all clear today."
    _assert_card_shape(adj)


def test_green_copy_uses_location_when_injury_condition_is_unrecognized():
    adj = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(
            today_session=_session(title="Recovery mobility"),
            open_injuries=[
                {
                    "status": "open",
                    "severity": "mild",
                    "body_area": "left shoulder tngling i dont know why",
                    "description": "left shoulder tngling i dont know why",
                }
            ],
        ),
    )

    assert adj.decision == "train_as_planned"
    assert "protect your Left shoulder today" in adj.reason
    assert "tngling" not in adj.reason
    assert "i dont know why" not in adj.reason
    _assert_card_shape(adj)


def test_new_high_exposure_session_terms_classify_as_high():
    for title in (
        "Heavy bag rounds",
        "Clinch and wrestling",
        "HIIT conditioning circuit",
        "Explosive plyometric lower body",
        "Live sparring rounds",
    ):
        assert classify_session_risk(_session(title=title)) == "high", title


# ---------------------------------------------------------------------------
# Safe filler / support sessions (mental cue, breathing/mobility reset) must not
# be hard-blocked by an injury — they are the safe work an injury STOP prescribes.
# ---------------------------------------------------------------------------


def test_is_support_session_detects_fillers_and_ignores_hard_work():
    assert is_support_session(_session(title="Tactical Cue Card", session_type="skill")) is True
    assert is_support_session({"title": "Breathing Reset"}) is True
    assert is_support_session({"category": "support_insert", "title": "Anything"}) is True
    assert is_support_session({"stress_class": "support", "title": "x"}) is True
    assert is_support_session({"support_insert_category": "mobility", "title": "x"}) is True
    # A real loaded session that merely mentions mobility in a warm-up is not a filler.
    assert is_support_session(_session(title="Heavy squat then mobility")) is False
    assert is_support_session(_session(title="Hard sparring")) is False


def test_support_session_is_safety_first_high_risk_wording_vetoes_structured_signal():
    # A mislabeled structured "support" flag on a hard session must NOT open the
    # injury exemption — high-risk wording always wins.
    assert is_support_session({"stress_class": "support", "title": "Hard sparring"}) is False
    assert is_support_session({"governance": {"meaningful_stress": False}, "title": "Heavy squat"}) is False
    assert is_support_session({"category": "support_insert", "title": "sparring reset"}) is False
    # A genuine structured filler with safe wording is still accepted.
    assert is_support_session({"category": "support_insert", "title": "Tactical Cue Card"}) is True


def _filler_session():
    return {
        "title": "Tactical Cue Card",
        "session_type": "support_insert",
        "category": "support_insert",
        "support_insert_category": "tactical",
        "effective_load": "technical",
        "objective": "distil one clean in-fight cue",
    }


def test_filler_session_is_not_blocked_by_worse_or_severe_injury():
    for injuries in (
        [{"status": "open", "severity": "moderate", "label": "neck injury",
          "consequence": "neuro", "latest_reported_status": "worse"}],
        [{"status": "open", "severity": "severe", "label": "neck injury", "consequence": "neuro"}],
    ):
        adj = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(today_session=_filler_session(), open_injuries=tuple(injuries)),
        )
        assert adj.decision == "train_as_planned"
        assert adj.title == "Safe session today."
        _assert_card_shape(adj)


def test_filler_session_is_not_blocked_by_high_pain():
    adj = build_readiness_adjustment(
        ReadinessCheckin(pain="high"),
        ReadinessContext(today_session=_filler_session()),
    )
    assert adj.decision == "train_as_planned"


def test_filler_session_still_blocked_by_red_flag_symptom():
    # Acute red-flag symptoms are a medical emergency and stop everything, filler
    # or not.
    adj = build_readiness_adjustment(
        ReadinessCheckin(neurological_symptoms=True),
        ReadinessContext(today_session=_filler_session()),
    )
    assert adj.decision == "pull_back"
    assert adj.title == "No training today."


def test_filler_session_ignores_fatigue_soft_warnings():
    # A restorative filler is not reduced by accumulated fatigue signals — a poor
    # 3-day sleep streak still leaves a breathing/cue-card day fully allowed.
    adj = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat"),
        ReadinessContext(
            training_day="2026-06-18",
            today_session=_filler_session(),
            recent_checkins=[
                {"training_day": "2026-06-17", "sleep": "poor", "body": "flat"},
                {"training_day": "2026-06-16", "sleep": "poor", "body": "flat"},
            ],
        ),
    )
    assert adj.decision == "train_as_planned"
    assert adj.title == "Safe session today."
    _assert_card_shape(adj)


# ---------------------------------------------------------------------------
# Accumulated check-in signals must only be built from RECENT history — sporadic
# check-ins/sessions weeks apart must not inflate a "3-day streak" / "recent load".
# ---------------------------------------------------------------------------


def test_streak_is_not_assembled_from_non_adjacent_checkins():
    adj = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=[
                {"training_day": "2026-06-02", "sleep": "poor"},
                {"training_day": "2026-05-20", "sleep": "poor"},
            ],
            today_session=_session(title="Technical skill drilling"),
        ),
    )
    # Weeks-apart poor sleep is NOT a 3-day streak — just today's single warning.
    assert "poor_sleep_3_day_streak" not in adj.triggers
    assert "poor_sleep" in adj.triggers


def test_adjacent_checkins_still_form_a_streak():
    adj = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=[
                {"training_day": "2026-06-17", "sleep": "poor"},
                {"training_day": "2026-06-16", "sleep": "poor"},
            ],
            today_session=_session(title="Technical skill drilling"),
        ),
    )
    assert "poor_sleep_3_day_streak" in adj.triggers


def test_streak_requires_consecutive_calendar_days():
    adj = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="manageable"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=[
                {"training_day": "2026-06-17", "sleep": "poor", "body": "flat", "pain": "manageable"},
                {"training_day": "2026-06-15", "sleep": "poor", "body": "flat", "pain": "manageable"},
            ],
            today_session=_session(title="Technical skill drilling"),
        ),
    )
    assert "poor_sleep_3_day_streak" not in adj.triggers
    assert "flat_body_3_day_streak" not in adj.triggers
    assert "pain_3_day_streak" not in adj.triggers
    assert "poor_sleep" in adj.triggers


def test_unparseable_training_day_preserves_best_effort_streak():
    adj = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(
            training_day="not-a-date",
            recent_checkins=[
                {"training_day": "2026-06-17", "sleep": "poor"},
                {"training_day": "2026-06-15", "sleep": "poor"},
            ],
            today_session=_session(title="Technical skill drilling"),
        ),
    )
    assert "poor_sleep_3_day_streak" in adj.triggers


def test_recent_hard_load_ignores_stale_sessions():
    adj = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_sessions=[
                {"training_day": "2026-05-20", "session_rpe": 9},
                {"training_day": "2026-05-18", "session_rpe": 9},
            ],
            today_session=_session(title="Technical skill drilling"),
        ),
    )
    # Hard sessions weeks ago are not "recent load".
    assert "recent_hard_load_plus_poor_today" not in adj.triggers


def test_context_worse_injury_uses_clean_label_when_row_has_no_label():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="sharp", pain="none"),
        ReadinessContext(
            today_session=_session(title="Sparring and hard conditioning"),
            open_injuries=[
                {
                    "status": "open",
                    "severity": "mild",
                    "body_area": "cut neck",
                    "description": "cut neck",
                    "latest_reported_status": "worse",
                }
            ],
        ),
    )

    assert adjustment.decision == "pull_back"
    assert "The Neck cut injury is worse." in adjustment.reason
    assert "cut neck" not in adjustment.reason
    assert "active_injury_worse" in adjustment.triggers
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


def test_poor_sleep_plus_flat_body_stacks_two_warnings():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat"),
        ReadinessContext(today_session=_session(title="Heavy lower body plyometrics")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.title == "Session reduced."
    assert "Multiple warning signs are showing" in adjustment.reason
    assert "poor sleep and flat body" in adjustment.reason
    assert "sparring" in adjustment.action
    assert "hard rounds" in adjustment.action
    assert "conditioning finishers" in adjustment.action
    assert "poor_sleep" in adjustment.triggers
    assert "flat_body" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_hard_sparring_only_has_no_warning_sources_or_modify_card():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(today_session=_session(title="Hard sparring")),
    )

    assert adjustment.decision == "train_as_planned"
    assert "Warning sources:" not in adjustment.message
    assert "Multiple warning signs are showing" not in adjustment.message
    assert "session_risk_high" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_selected_injury_severity_without_added_injury_is_not_counted():
    # Draft form state is not part of ReadinessContext.open_injuries. Only an
    # added injury row may count.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(today_session=_session(title="Hard sparring"), open_injuries=()),
    )

    assert adjustment.decision == "train_as_planned"
    assert "active injury" not in adjustment.message.lower()
    assert "tracked_injury_high_risk_session" not in adjustment.triggers
    _assert_card_shape(adjustment)


def test_removing_injury_clears_related_warning_source():
    with_injury = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(
            today_session=_session(title="Hard sparring"),
            open_injuries=(_injury(None, "mild", label="knee pain"),),
        ),
    )
    without_injury = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(today_session=_session(title="Hard sparring"), open_injuries=()),
    )

    assert "tracked_injury_high_risk_session" in with_injury.triggers
    assert "active injury" in with_injury.reason
    assert without_injury.decision == "train_as_planned"
    assert "tracked_injury_high_risk_session" not in without_injury.triggers
    assert "active injury" not in without_injury.message.lower()
    _assert_card_shape(with_injury)
    _assert_card_shape(without_injury)


def test_resetting_checkin_clears_stale_warning_state():
    poor = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="none"),
        ReadinessContext(today_session=_session(title="Technical skill drilling")),
    )
    reset = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(today_session=_session(title="Technical skill drilling")),
    )

    assert poor.decision == "modify"
    assert "Multiple warning signs are showing" in poor.reason
    assert reset.decision == "train_as_planned"
    assert "poor_sleep" not in reset.triggers
    assert "flat_body" not in reset.triggers
    assert "Multiple warning signs are showing" not in reset.message
    _assert_card_shape(poor)
    _assert_card_shape(reset)


def test_one_manageable_pain_warning_does_not_claim_multiple_sources():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(today_session=_session(title="Technical skill drilling")),
    )

    assert adjustment.decision == "modify"
    assert "Manageable pain means the area needs protection today." in adjustment.reason
    assert "Multiple warning signs are showing" not in adjustment.message
    _assert_card_shape(adjustment)


def test_hidden_context_warning_is_surfaced_in_source_list():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "modify"
    assert "Multiple warning signs are showing: poor sleep and the taper phase." in adjustment.reason
    assert "taper_poor_readiness" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_clear_taper_produces_freshness_first_wording():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "train_as_planned"
    assert adjustment.title == "Sharp work only."
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
    assert "Multiple warning signs are showing" in adjustment.message
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
    assert "Multiple warning signs are showing" in adjustment.reason
    assert "Skip sparring, hard rounds, and conditioning finishers" in adjustment.action
    assert "poor_sleep" in adjustment.triggers
    assert "repeated_poor_readiness" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_three_poor_sleep_days_uses_sleep_trend_message():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=_prior_checkins(
                {"training_day": "2026-06-18", "sleep": "good"},
                {"training_day": "2026-06-17", "sleep": "poor"},
                {"training_day": "2026-06-17", "sleep": "good"},
                {"training_day": "2026-06-16", "sleep": "poor"},
            ),
            today_session=_session(title="Moderate strength"),
        ),
    )

    assert adjustment.decision == "modify"
    assert "poor_sleep_3_day_streak" in adjustment.triggers
    assert "Poor sleep has built up for 3 days" in adjustment.reason
    assert "Cut 1 round" in adjustment.action
    _assert_card_shape(adjustment)


def test_three_flat_body_days_uses_body_trend_message():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(body="flat"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=_prior_checkins(
                {"training_day": "2026-06-17", "body": "flat"},
                {"training_day": "2026-06-16", "body": "flat"},
            ),
            today_session=_session(title="Moderate strength"),
        ),
    )

    assert adjustment.decision == "modify"
    assert "flat_body_3_day_streak" in adjustment.triggers
    assert "body has felt flat for 3 days" in adjustment.reason
    assert "Keep rounds technical" in adjustment.action
    _assert_card_shape(adjustment)


def test_three_pain_days_uses_pain_trend_message():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=_prior_checkins(
                {"training_day": "2026-06-17", "pain": "manageable"},
                {"training_day": "2026-06-16", "pain": "manageable"},
            ),
            today_session=_session(title="Moderate strength"),
        ),
    )

    assert adjustment.decision == "modify"
    assert "pain_3_day_streak" in adjustment.triggers
    assert "Pain has shown up for 3 days" in adjustment.reason
    assert "Skip sparring" in adjustment.action
    _assert_card_shape(adjustment)


def test_pain_worsening_trend_pulls_back_before_high_risk_work():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=_prior_checkins(
                {"training_day": "2026-06-17", "pain": "manageable"},
                {"training_day": "2026-06-16", "pain": "none"},
            ),
            today_session=_session(title="Sparring and hard conditioning"),
        ),
    )

    assert adjustment.decision == "pull_back"
    assert "pain_worsening_trend" in adjustment.triggers
    assert "Pain is getting worse" in adjustment.reason
    assert "hard combat work is not safe today" in adjustment.reason
    _assert_card_shape(adjustment)


def test_new_pain_after_clear_days_does_not_trigger_worsening_trend():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=_prior_checkins(
                {"training_day": "2026-06-17", "pain": "none"},
                {"training_day": "2026-06-16", "pain": "none"},
            ),
            today_session=_session(title="Moderate strength"),
        ),
    )

    assert "pain_worsening_trend" not in adjustment.triggers
    assert adjustment.decision == "modify"
    assert "Manageable pain means the area needs protection" in adjustment.reason
    _assert_card_shape(adjustment)


def test_existing_pain_that_stays_manageable_triggers_worsening_trend():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=_prior_checkins(
                {"training_day": "2026-06-17", "pain": "manageable"},
                {"training_day": "2026-06-16", "pain": "none"},
            ),
            today_session=_session(title="Moderate strength"),
        ),
    )

    assert "pain_worsening_trend" in adjustment.triggers
    assert "Pain is getting worse" in adjustment.reason
    _assert_card_shape(adjustment)


def test_manageable_pain_streak_to_high_pain_still_uses_hard_override():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="high"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=_prior_checkins(
                {"training_day": "2026-06-17", "pain": "manageable"},
                {"training_day": "2026-06-16", "pain": "manageable"},
            ),
            today_session=_session(title="Sparring and hard conditioning"),
        ),
    )

    assert adjustment.decision == "pull_back"
    assert adjustment.title == "Rehab only today."
    assert "pain_worsening_trend" not in adjustment.triggers
    assert "pain_high" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_two_hard_sessions_plus_poor_today_uses_load_trend_message():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(
            today_session=_session(title="Moderate strength"),
            recent_sessions=[
                {"training_day": "2026-06-17", "session_rpe": 8},
                {"training_day": "2026-06-16", "session_rpe": 9},
                {"training_day": "2026-06-15", "session_rpe": 5},
            ],
        ),
    )

    assert adjustment.decision == "modify"
    assert "recent_hard_load_plus_poor_today" in adjustment.triggers
    assert "recent training load was high" in adjustment.reason
    assert "Keep rounds controlled" in adjustment.action
    _assert_card_shape(adjustment)


def test_three_soft_warnings_pull_back_before_high_risk_combat_work():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="manageable"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
    )

    assert adjustment.decision == "pull_back"
    assert "Multiple warning signs are showing" in adjustment.reason
    assert "Skip combat work" in adjustment.action
    assert "poor_sleep" in adjustment.triggers
    assert "flat_body" in adjustment.triggers
    assert "manageable_pain" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_three_soft_warnings_without_high_risk_or_pain_can_stay_modify():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="none"),
        ReadinessContext(
            training_day="2026-06-18",
            recent_checkins=_prior_checkins(
                {"training_day": "2026-06-17", "sleep": "poor", "body": "flat"},
                {"training_day": "2026-06-16", "sleep": "poor", "body": "flat"},
            ),
            recent_sessions=[
                {"training_day": "2026-06-17", "session_rpe": 8},
                {"training_day": "2026-06-16", "session_rpe": 9},
                {"training_day": "2026-06-15", "session_rpe": 5},
            ],
            today_session=_session(title="Mobility and recovery"),
        ),
    )

    assert adjustment.decision == "modify"
    assert "Multiple warning signs are showing" in adjustment.reason
    assert "Cut rounds, cap intensity, and remove conditioning" in adjustment.action
    assert "poor_sleep_3_day_streak" in adjustment.triggers
    assert "flat_body_3_day_streak" in adjustment.triggers
    assert "recent_hard_load_plus_poor_today" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_poor_sleep_in_taper_uses_taper_specific_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "modify"
    assert "taper_poor_readiness" in adjustment.triggers
    assert "poor sleep and the taper phase" in adjustment.reason
    assert "Multiple warning signs are showing" in adjustment.message
    _assert_card_shape(adjustment)


def test_flat_body_in_reintegration_uses_reintegration_specific_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(body="flat", phase="REINTEGRATION"),
        ReadinessContext(phase="REINTEGRATION", today_session=_session(title="Mobility")),
    )

    assert adjustment.decision == "modify"
    assert "reintegration_poor_readiness" in adjustment.triggers
    assert "flat body and the return phase" in adjustment.reason
    assert "Multiple warning signs are showing" in adjustment.message
    _assert_card_shape(adjustment)


def test_three_taper_warnings_still_use_stronger_pull_back_stack_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="manageable", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "pull_back"
    assert "Multiple warning signs are showing" in adjustment.message
    assert "Skip combat work" in adjustment.message
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


def test_manageable_pain_before_high_risk_work_pulls_back():
    # A pain signal before hard combat work is a pull-back, not a modify whose
    # action already tells the athlete to skip the whole session (the amber-state /
    # stop-action contradiction). On a lower-risk session it stays a modify.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
    )

    assert adjustment.decision == "pull_back"
    assert "not safe today" in adjustment.reason
    assert "manageable_pain" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_manageable_pain_on_lower_risk_session_stays_modify():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(today_session=_session(title="Technical skill drilling")),
    )

    assert adjustment.decision == "modify"
    assert "clinch" in adjustment.action
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
        (
            ReadinessCheckin(sleep="good", body="normal", pain="none"),
            ReadinessContext(today_session=_session(title="Technical boxing rounds")),
        ),
        (
            ReadinessCheckin(sleep="poor", body="flat", pain="manageable"),
            ReadinessContext(today_session=_session(title="Sparring and hard conditioning")),
        ),
    ]
    banned = (
        "tissue margin",
        "recovery margin",
        "readiness state",
        "prescribed dose",
        "fatigue-heavy accessories",
        "sprinting",
        "plyos",
        "heavy lower-body",
        "max-effort",
        "Remove 1 set",
    )

    for checkin, context in scenarios:
        message = build_readiness_adjustment(checkin, context).message
        for phrase in banned:
            assert phrase not in message
