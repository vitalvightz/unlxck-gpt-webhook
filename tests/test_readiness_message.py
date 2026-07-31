"""Tests for the context-aware Today readiness message engine."""

import pytest

from api.contracts.readiness_message import (
    ReadinessCheckin,
    ReadinessContext,
    _GREEN_INJURY_ACTIONS,
    _green_injury_action,
    _soft_warning_message,
    build_readiness_adjustment,
    classify_session_modality,
    classify_session_risk,
    context_labels,
    is_support_session,
    trigger_labels,
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
    graze = _injury(None, "mild", label="knuckle graze")
    graze.update(body_area="right knuckle", description="graze")
    adj = _decision("Recovery mobility", [graze])
    assert adj.decision == "train_as_planned"
    assert "knuckle graze" in adj.reason
    assert adj.reason != "Your sleep, body, and pain checks are all clear today."
    assert "clean" in adj.action
    _assert_card_shape(adj)


def test_green_tightness_copy_is_personalized_without_wound_hygiene():
    tightness = _injury(None, "mild", label="Knee tendon tightness")
    tightness.update(
        body_area="knee tendon",
        description="tightness",
    )

    adj = _decision("Recovery mobility", [tightness])

    assert adj.decision == "train_as_planned"
    assert adj.action == "Ease into the session and stop if the knee tendon tightness builds."
    assert "clean" not in adj.message.lower()
    _assert_card_shape(adj)


def test_green_injury_actions_cover_every_canonical_type():
    from fightcamp.injury_taxonomy import INJURY_TAXONOMY

    assert set(_GREEN_INJURY_ACTIONS) == set(INJURY_TAXONOMY)
    for injury_type in INJURY_TAXONOMY:
        action = _green_injury_action(
            {"injury_type": injury_type},
            str(INJURY_TAXONOMY[injury_type]["display"]),
        )
        assert action.endswith("."), injury_type
        assert len(action.split()) <= 18, injury_type


def test_only_known_surface_injuries_receive_cleaning_advice():
    from fightcamp.injury_taxonomy import INJURY_TAXONOMY

    for injury_type, rule in INJURY_TAXONOMY.items():
        action = _green_injury_action({"injury_type": injury_type}, str(rule["display"]))
        if rule["category"] == "surface":
            assert " clean " in f" {action.lower()} ", injury_type
        else:
            assert "clean" not in action.lower(), injury_type

    unknown = _green_injury_action({"label": "left knee niggle"}, "Left knee niggle")
    assert "clean" not in unknown.lower()


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
    assert adj.reason == "Your check-in is clear, with the left shoulder still being tracked."
    assert adj.action == "Protect the left shoulder and stop if it worsens."
    assert "clean" not in adj.message.lower()
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
    assert is_support_session(_session(title="Hard sparring", session_type="sparring")) is False


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
# A low-stress "support" session can still carry a filler/primer that loads the
# INJURED region (an explosive band row on a bruised shoulder). That must not be
# blanket-declared "safe to do around your injury" — it downgrades to a targeted
# "protect the area" modify.
# ---------------------------------------------------------------------------


def _shoulder_injury():
    return [{"status": "open", "severity": "moderate", "label": "Right shoulder bruise",
             "body_area": "shoulder"}]


def test_freshness_session_with_shoulder_loading_primer_is_flagged():
    # The exact reported failure: fight-week freshness support session carrying a
    # Band Row primer while the shoulder is bruised.
    session = {
        "title": "Fight-week freshness",
        "session_type": "support_insert",
        "stress_class": "support",
        "blocks": [
            {"title": "Mobility Reset Flow", "type": "mobility"},
            {"title": "Band Row Speed Focus", "type": "primer"},
        ],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(_shoulder_injury())),
    )
    assert adj.decision == "modify"
    assert adj.title == "Protect the injured area."
    assert "Right shoulder bruise" in adj.reason
    _assert_card_shape(adj)


def test_filler_with_structured_load_regions_conflicting_is_flagged():
    session = {
        "title": "Technical Shadow Rhythm",
        "category": "support_insert",
        "support_insert_category": "technical",
        "mechanical_load_regions": ["shoulder", "elbow", "wrist", "chest"],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(_shoulder_injury())),
    )
    assert adj.decision == "modify"
    assert adj.title == "Protect the injured area."


def test_filler_with_mechanical_risk_tags_conflicting_is_flagged():
    session = {
        "title": "Fight-week freshness",
        "stress_class": "support",
        "blocks": [{"title": "primer", "mechanical_risk_tags": ["mech_upper_pull"]}],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(active_injury="shoulder"),
        ReadinessContext(today_session=session, open_injuries=tuple(_shoulder_injury())),
    )
    assert adj.decision == "modify"


def test_shoulder_injury_with_lower_body_filler_stays_safe():
    # A footwork/lower-leg filler loads nothing in the shoulder, so a shoulder
    # injury leaves it fully safe — the gate must be region-specific, not a blanket
    # "any injury blocks any physical filler".
    session = {
        "title": "Footwork Walkthrough",
        "category": "support_insert",
        "mechanical_load_regions": ["ankle", "foot", "knee"],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(_shoulder_injury())),
    )
    assert adj.decision == "train_as_planned"
    assert adj.title == "Safe session today."


def test_non_loading_filler_with_shoulder_injury_stays_safe():
    # A pure mental cue loads nothing, so even a shoulder injury leaves it safe.
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=_filler_session(), open_injuries=tuple(_shoulder_injury())),
    )
    assert adj.decision == "train_as_planned"
    assert adj.title == "Safe session today."


def test_tactical_review_text_does_not_read_as_physical_loading():
    # Reviewer regression #1: a tactical-watch objective can name a movement word
    # ("your jab") in prose without the athlete throwing anything. The keyword
    # fallback must only scan physical entry NAMES, and must skip an entry that
    # is structurally tactical/mental regardless of its wording.
    session = {
        "title": "Fight Tactical Watch",
        "session_type": "support_insert",
        "category": "support_insert",
        "support_insert_category": "tactical",
        "objective": "Review how the opponent reacts to your jab.",
        "coach_note": "Focus on entries, exits, and footwork patterns to counter.",
        "reason": "Sharpen the fight plan without loading the shoulder.",
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(_shoulder_injury())),
    )
    assert adj.decision == "train_as_planned"
    assert adj.title == "Safe session today."


def test_physical_block_name_still_flagged_when_tactical_wrapper_present():
    # The exclusion is scoped to the entry that is actually tactical/mental — a
    # genuinely physical block nested next to it must still be caught.
    session = {
        "title": "Fight-week freshness",
        "session_type": "support_insert",
        "stress_class": "support",
        "blocks": [
            {"title": "Fight Tactical Watch", "support_insert_category": "tactical"},
            {"title": "Band Row Speed Focus"},
        ],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(_shoulder_injury())),
    )
    assert adj.decision == "modify"
    assert adj.title == "Protect the injured area."


def test_walk_flush_flagged_for_ankle_injury():
    # Reviewer regression #2: walk_flush/aerobic_walk_flush previously declared no
    # load regions at all, so a brisk walk read as "safe" for an ankle sprain.
    ankle_injury = [{"status": "open", "severity": "moderate", "label": "Ankle sprain",
                      "body_area": "ankle"}]
    session = {
        "title": "Brisk Walk Flush",
        "category": "support_insert",
        "support_insert_category": "conditioning_maintenance",
        "mechanical_load_regions": ["ankle", "foot", "achilles", "calf", "knee"],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(ankle_injury)),
    )
    assert adj.decision == "modify"
    assert adj.title == "Protect the injured area."


def test_shadow_rhythm_flagged_for_knee_injury_via_footwork_load():
    # Reviewer regression #2: technical_shadow_rhythm / aerobic_shadow_flow only
    # declared the upper body despite entries/exits/stance work loading the knee.
    knee_injury = [{"status": "open", "severity": "moderate", "label": "Knee strain",
                     "body_area": "knee"}]
    session = {
        "title": "Technical Shadow Rhythm",
        "category": "support_insert",
        "support_insert_category": "technical",
        "mechanical_load_regions": ["shoulder", "elbow", "wrist", "chest", "ankle", "knee"],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(knee_injury)),
    )
    assert adj.decision == "modify"
    assert adj.title == "Protect the injured area."


def test_targeted_rehab_stays_safe_even_for_the_matching_injury():
    # mobility_rehab / joint_prep are gentle, pain-free work explicitly targeted
    # at the flagged restriction — their regional overlap is the point of
    # prescribing them, not a hazard, so they must stay in the safe branch.
    session = {
        "title": "Mobility/Rehab Reset",
        "category": "support_insert",
        "support_insert_category": "mobility",
        "mechanical_load_regions": [],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(_shoulder_injury())),
    )
    assert adj.decision == "train_as_planned"
    assert adj.title == "Safe session today."


def test_disc_substring_does_not_misfire_on_knee_discomfort():
    # Reviewer regression #3: "disc" is a lower_back keyword; a naive substring
    # check would misread "knee discomfort" as a disc/lower-back injury and wrongly
    # flag an unrelated lower-back-loading filler.
    knee_injury = [{"status": "open", "severity": "mild", "label": "knee discomfort",
                     "body_area": "knee"}]
    lower_back_loading_session = {
        "title": "Fight-week freshness",
        "category": "support_insert",
        "mechanical_load_regions": ["lower_back", "hamstring"],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=lower_back_loading_session, open_injuries=tuple(knee_injury)),
    )
    assert adj.decision == "train_as_planned"
    assert adj.title == "Safe session today."
    # The substring bug would have added lower_back to the injured-region set;
    # confirm directly that "knee discomfort" resolves to knee only.
    from api.contracts.readiness_message import _active_injury_regions

    assert _active_injury_regions(
        ReadinessCheckin(), ReadinessContext(open_injuries=tuple(knee_injury))
    ) == {"knee"}


def test_structured_body_area_is_authoritative_over_free_text_wording():
    # Reviewer regression #3: the structured body_area should drive region
    # resolution directly rather than relying purely on a text scan of label.
    quad_injury = [{"status": "open", "severity": "moderate", "label": "Thigh knock",
                     "body_area": "quad"}]
    session = {
        "title": "Squat Primer",
        "category": "support_insert",
        "mechanical_load_regions": ["quad", "knee"],
    }
    adj = build_readiness_adjustment(
        ReadinessCheckin(),
        ReadinessContext(today_session=session, open_injuries=tuple(quad_injury)),
    )
    assert adj.decision == "modify"
    assert adj.title == "Protect the injured area."


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
            today_session=_session(title="Sparring and hard conditioning", session_type="sparring"),
            open_injuries=[
                {
                    "status": "open",
                    "severity": "mild",
                    "body_area": "strained shoulder",
                    "description": "strained shoulder",
                    "latest_reported_status": "worse",
                }
            ],
        ),
    )

    assert adjustment.decision == "pull_back"
    assert "The Shoulder strain injury is worse." in adjustment.reason
    assert "strained shoulder" not in adjustment.reason
    assert "active_injury_worse" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_high_pain_returns_rehab_only_guidance():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="high"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
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
    assert "Drop 1 set per main lift" in adjustment.action
    assert "reps in reserve" in adjustment.action
    _assert_card_shape(adjustment)


def test_flat_body_caps_intensity():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(body="flat"),
        ReadinessContext(today_session=_session(title="Moderate strength")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.title == "Intensity capped."
    assert "flat body" in adjustment.reason.lower()
    assert "no maxes" in adjustment.action.lower()
    _assert_card_shape(adjustment)


def test_poor_sleep_plus_flat_body_reduces_the_relevant_load():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat"),
        ReadinessContext(today_session=_session(title="Heavy lower body plyometrics")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.title == "Session reduced."
    assert adjustment.reason == "Your readiness is down, so reduce heavy loading today."
    assert "signals are stacking" not in adjustment.reason
    assert trigger_labels(adjustment.triggers) == ("Poor sleep", "Feeling flat")
    assert "Cut the heavy top sets and back-off volume" in adjustment.action
    assert "keep the remaining lifts controlled" in adjustment.action
    assert "poor_sleep" in adjustment.triggers
    assert "flat_body" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_hard_sparring_only_has_no_warning_sources_or_modify_card():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(today_session=_session(title="Hard sparring", session_type="sparring")),
    )

    assert adjustment.decision == "train_as_planned"
    assert "Warning sources:" not in adjustment.message
    assert "signals are stacking up" not in adjustment.message
    assert "session_risk_high" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_selected_injury_severity_without_added_injury_is_not_counted():
    # Draft form state is not part of ReadinessContext.open_injuries. Only an
    # added injury row may count.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(today_session=_session(title="Hard sparring", session_type="sparring"), open_injuries=()),
    )

    assert adjustment.decision == "train_as_planned"
    assert "active injury" not in adjustment.message.lower()
    assert "tracked_injury_high_risk_session" not in adjustment.triggers
    _assert_card_shape(adjustment)


def test_removing_injury_clears_related_warning_source():
    with_injury = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(
            today_session=_session(title="Hard sparring", session_type="sparring"),
            open_injuries=(_injury(None, "mild", label="knee pain"),),
        ),
    )
    without_injury = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none"),
        ReadinessContext(today_session=_session(title="Hard sparring", session_type="sparring"), open_injuries=()),
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
    assert poor.reason == "Your readiness is down, so reduce heavy loading today."
    assert "signals are stacking" not in poor.reason
    assert reset.decision == "train_as_planned"
    assert "poor_sleep" not in reset.triggers
    assert "flat_body" not in reset.triggers
    assert "signals are stacking up" not in reset.message
    _assert_card_shape(poor)
    _assert_card_shape(reset)


def test_one_manageable_pain_warning_does_not_claim_multiple_sources():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(pain="manageable"),
        ReadinessContext(today_session=_session(title="Technical skill drilling")),
    )

    assert adjustment.decision == "modify"
    assert "Manageable pain means the area needs protection today." in adjustment.reason
    assert "signals are stacking up" not in adjustment.message
    _assert_card_shape(adjustment)


def test_taper_is_recorded_as_context_and_never_as_a_warning():
    # Being in taper is a plan, not a symptom. It is still recorded, so the card
    # can show it as CONTEXT, but it must not count as a signal or appear in the
    # reason as though something were wrong.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "modify"
    assert "taper_poor_readiness" in adjustment.triggers
    assert context_labels(adjustment.triggers) == ("Taper phase",)
    assert trigger_labels(adjustment.triggers) == ("Poor sleep",)
    assert "taper" not in adjustment.reason.lower()
    assert "warning sign" not in adjustment.message.lower()
    _assert_card_shape(adjustment)


def test_clear_taper_produces_freshness_first_wording():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="good", body="normal", pain="none", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "train_as_planned"
    assert adjustment.title == "Sharp work only."
    assert "sharpness" in adjustment.reason
    assert "lifts" in adjustment.action
    assert "back-off" in adjustment.action
    _assert_card_shape(adjustment)


def test_taper_poor_flat_manageable_pain_pulls_back_without_modify_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="manageable", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "pull_back"
    assert "Pull back today." in adjustment.message
    assert "Your readiness is too low for heavy loading today." in adjustment.message
    assert "Skip heavy loading today. Use recovery or light mobility instead." in adjustment.message
    assert "signals are stacking" not in adjustment.message
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
    assert adjustment.reason == "Your readiness is down, so reduce heavy loading today."
    assert "signals are stacking" not in adjustment.reason
    assert "Cut the heavy top sets and back-off volume" in adjustment.action
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
    assert "Cut total sets" in adjustment.action
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
    assert "Cap intensity" in adjustment.action
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
    assert "Skip heavy loading" in adjustment.action
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
            today_session=_session(title="Sparring and hard conditioning", session_type="sparring"),
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
            today_session=_session(title="Sparring and hard conditioning", session_type="sparring"),
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
    assert "Keep loads controlled" in adjustment.action
    _assert_card_shape(adjustment)


def test_three_soft_warnings_pull_back_before_high_risk_combat_work():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="manageable"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
    )

    assert adjustment.decision == "pull_back"
    assert adjustment.reason == "Your readiness is too low for hard combat work today."
    assert adjustment.action == "Skip hard combat work today. Use recovery or light mobility instead."
    assert "signals are stacking" not in adjustment.reason
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
    assert adjustment.reason == "Your readiness is down, so reduce heavy loading today."
    assert "signals are stacking" not in adjustment.reason
    assert "Cut sets, cap load, and add no extra work" in adjustment.action
    assert "poor_sleep_3_day_streak" in adjustment.triggers
    assert "flat_body_3_day_streak" in adjustment.triggers
    assert "recent_hard_load_plus_poor_today" in adjustment.triggers
    _assert_card_shape(adjustment)


def test_poor_sleep_in_taper_reads_as_one_signal_not_two():
    # One poor night is one signal. Counting the phase alongside it is what used
    # to tier this as "multiple warning signs" and pull the athlete off combat.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "modify"
    assert "Poor sleep means your body has less room to recover today." in adjustment.reason
    assert "stacking up" not in adjustment.reason
    _assert_card_shape(adjustment)


def test_flat_body_in_reintegration_reads_as_one_signal_not_two():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(body="flat", phase="REINTEGRATION"),
        ReadinessContext(phase="REINTEGRATION", today_session=_session(title="Mobility")),
    )

    assert adjustment.decision == "modify"
    assert "reintegration_poor_readiness" in adjustment.triggers
    assert context_labels(adjustment.triggers) == ("Return phase",)
    assert "stacking up" not in adjustment.reason
    _assert_card_shape(adjustment)


def test_three_taper_warnings_still_use_stronger_pull_back_stack_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="manageable", phase="TAPER"),
        ReadinessContext(phase="TAPER", today_session=_session(title="Primer")),
    )

    assert adjustment.decision == "pull_back"
    assert "Your readiness is too low for heavy loading today." in adjustment.message
    assert "Skip heavy loading today. Use recovery or light mobility instead." in adjustment.message
    assert "signals are stacking" not in adjustment.message
    _assert_card_shape(adjustment)


def test_high_risk_combat_session_uses_combat_reduction_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
    )

    assert adjustment.decision == "modify"
    assert "sparring" in adjustment.action
    assert "hard rounds" in adjustment.action
    assert "conditioning finishers" in adjustment.action
    _assert_card_shape(adjustment)


def test_flat_body_high_risk_uses_bag_or_max_output_copy():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(body="flat"),
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
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
        ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
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
    assert "avoid painful ranges" in adjustment.action
    _assert_card_shape(adjustment)


def test_hyphenated_combat_sports_are_recognized_for_contact_guidance():
    for style in ("muay-thai", "jiu-jitsu"):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(sleep="poor"),
            ReadinessContext(
                intake={"athlete": {"technical_style": [style]}},
                today_session=_session(title="Sparring and hard conditioning", session_type="sparring"),
            ),
        )

        assert adjustment.decision == "modify"
        assert "contact_sport" in adjustment.triggers
        # The subject here is sport RECOGNITION (the trigger above). The action is
        # asserted to give contact-specific guidance, but not via the "extra contact
        # rounds" suffix: that suffix is now suppressed when the action already says
        # to drop contact work, as this one does.
        assert "sparring" in adjustment.action.lower()
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
            today_session=_session(title="Technical boxing rounds", session_type="sparring"),
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
            ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
        ),
        (
            ReadinessCheckin(body="flat"),
            ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
        ),
        (
            ReadinessCheckin(pain="manageable"),
            ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
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
            ReadinessContext(today_session=_session(title="Technical boxing rounds", session_type="sparring")),
        ),
        (
            ReadinessCheckin(sleep="poor", body="flat", pain="manageable"),
            ReadinessContext(today_session=_session(title="Sparring and hard conditioning", session_type="sparring")),
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


def test_collapsing_warning_pair_does_not_claim_multiple_sources():
    # A pair where one label is fully absorbed by a stronger co-occurring signal
    # must NOT tier as "multiple" and then list a single source. It should fall
    # through to the surviving warning's specific single-source message.
    for warnings in (
        ("pain_worsening_trend", "pain_3_day_streak"),
        ("recent_hard_load_plus_poor_today", "recent_hard_session"),
    ):
        _, _, reason, _ = _soft_warning_message(
            warnings, session_risk="medium", phase="SPP", fight_week=False
        )
        assert "stacking up" not in reason

    # A genuine two-signal pair still reduces the session without restating a count.
    _, _, reason, _ = _soft_warning_message(
        ("poor_sleep", "flat_body"), session_risk="medium", phase="GPP", fight_week=False
    )
    assert reason == "Your readiness is down, so reduce hard combat work today."
    assert "signals are stacking" not in reason


def test_session_modality_reads_the_structured_session_type_tag():
    # Classification comes from the structured session_type tag, not the title.
    assert classify_session_modality({"session_type": "strength_power"}) == "strength"
    assert classify_session_modality({"session_type": "sparring"}) == "combat"
    assert classify_session_modality({"session_type": "fight_or_match"}) == "combat"
    assert classify_session_modality({"session_type": "skill"}) == "combat"
    assert classify_session_modality({"session_type": "conditioning"}) == "conditioning"
    assert classify_session_modality({"session_type": "mixed"}) == "mixed"
    # Loose aliases upstream also accepts still classify.
    assert classify_session_modality({"session_type": "strength"}) == "strength"
    assert classify_session_modality({"session_type": "s&c"}) == "strength"
    assert classify_session_modality({"session_type": "spar"}) == "combat"


def test_session_modality_uses_tag_and_blocks_never_title_text():
    # The tag is authoritative: a lifting title under a sparring tag is combat, and
    # a title that merely CONTAINS a keyword ("pressure", "padding") never flips it.
    assert classify_session_modality({"session_type": "sparring", "title": "Heavy squat and deadlift"}) == "combat"
    assert classify_session_modality({"session_type": "strength_power", "title": "Boxing footwork"}) == "strength"
    # No tag, but typed blocks still classify (structured, not text).
    assert classify_session_modality({"blocks": [{"type": "strength"}, {"type": "accessory"}]}) == "strength"
    assert classify_session_modality({"blocks": [{"type": "strength"}, {"type": "sparring"}]}) == "mixed"
    assert classify_session_modality({"blocks": [{"type": "conditioning"}]}) == "conditioning"
    # A title alone (no tag, no typed blocks) no longer classifies -> combat default.
    assert classify_session_modality({"title": "Pressure and padding drills"}) == "unknown"
    assert classify_session_modality({"title": "Primary strength anchor"}) == "unknown"
    assert classify_session_modality({}) == "unknown"
    assert classify_session_modality(None) == "unknown"


def test_mixed_session_type_defers_to_block_types():
    # "mixed" is not final: single-modality blocks refine it, a genuine mix keeps
    # it, and blocks with no work-type leave it "mixed".
    strength_blocks = [{"type": "strength"}, {"type": "accessory"}]
    assert classify_session_modality({"session_type": "mixed", "blocks": strength_blocks}) == "strength"
    both_blocks = [{"type": "strength"}, {"type": "sparring"}]
    assert classify_session_modality({"session_type": "mixed", "blocks": both_blocks}) == "mixed"
    # cooldown/mindset blocks carry no work-type signal -> stays "mixed".
    assert classify_session_modality({"session_type": "mixed", "blocks": [{"type": "mindset"}]}) == "mixed"
    assert classify_session_modality({"session_type": "mixed"}) == "mixed"


def test_block_fallback_reads_the_real_block_type_field():
    # Real plan data spells this field "block_type" (SessionBlock in
    # api/structured_plan_models.py, persisted by structured_plan_generation) — the
    # fallback must read it, not just the hand-written "type" shorthand, or it is
    # dead on every generated plan.
    real_strength = [{"block_id": "b1", "block_type": "strength"}, {"block_id": "b2", "block_type": "accessory"}]
    assert classify_session_modality({"blocks": real_strength}) == "strength"
    # An ambiguous tag ("primer"/"recovery"/"rehab") over real strength blocks must
    # still reach strength framing.
    assert classify_session_modality({"session_type": "primer", "blocks": real_strength}) == "strength"
    assert classify_session_modality({"session_type": "mixed", "blocks": real_strength}) == "strength"
    assert classify_session_modality({"blocks": [{"block_type": "sparring"}]}) == "combat"
    assert classify_session_modality({"blocks": [{"block_type": "conditioning"}]}) == "conditioning"
    assert (
        classify_session_modality({"blocks": [{"block_type": "strength"}, {"block_type": "sparring"}]}) == "mixed"
    )


def test_strength_and_conditioning_alias_maps_to_strength_like_upstream():
    # Upstream normalises "s&c" / "strength_and_conditioning" to strength_power
    # (api/structured_plan_generation.py _SESSION_TYPE_ALIASES), so we match that
    # decision: strength framing (sets / load), not mixed.
    assert classify_session_modality({"session_type": "strength_and_conditioning"}) == "strength"
    assert classify_session_modality({"session_type": "s&c"}) == "strength"


def test_strength_multi_signal_reason_matches_strength_action():
    # Two warnings on a strength session must not read "reduce combat work" above a
    # "cut your sets" action — the reason and action share the same lever.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat"),
        ReadinessContext(today_session=_session(title="Heavy lower body strength")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.reason == "Your readiness is down, so reduce heavy loading today."
    assert "signals are stacking" not in adjustment.reason
    assert "combat work" not in adjustment.reason.lower()
    assert "top sets" in adjustment.action
    _assert_card_shape(adjustment)


def test_strength_session_poor_sleep_uses_sets_not_rounds():
    # The exact case from the screenshot: a strength anchor + poor sleep must talk
    # sets / reps-in-reserve, never "cut a round".
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(today_session=_session(title="Primary strength anchor")),
    )

    assert adjustment.decision == "modify"
    assert "Drop 1 set per main lift" in adjustment.action
    assert "reps in reserve" in adjustment.action
    assert "round" not in adjustment.action.lower()
    assert "conditioning" not in adjustment.action.lower()
    _assert_card_shape(adjustment)


def test_combat_session_poor_sleep_still_uses_rounds():
    # Regression: the combat framing is unchanged for a pure combat session.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(today_session=_session(title="Hard sparring", session_type="sparring")),
    )

    assert adjustment.decision == "modify"
    assert "round" in adjustment.action.lower()
    assert "set" not in adjustment.action.lower()
    _assert_card_shape(adjustment)


def _mixed_session(**overrides):
    """A session that genuinely trains both levers: lifting AND combat work."""
    return _session(
        title="Technical work",
        session_type="mixed",
        blocks=[{"block_type": "strength"}, {"block_type": "sparring"}],
        **overrides,
    )


def test_mixed_session_action_names_both_levers():
    # A mixed day is lifting alongside combat work, so the action must address the
    # rounds AND the loading — the combat-only default spoke to half the session.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(today_session=_mixed_session()),
    )

    assert classify_session_modality(_mixed_session()) == "mixed"
    assert adjustment.decision == "modify"
    action = adjustment.action.lower()
    assert "round" in action
    assert "set" in action
    _assert_card_shape(adjustment)


@pytest.mark.parametrize(
    "checkin",
    [
        ReadinessCheckin(sleep="poor"),
        ReadinessCheckin(body="flat"),
        ReadinessCheckin(pain="manageable"),
        ReadinessCheckin(previous_session="hard"),
        ReadinessCheckin(sleep="poor", body="flat"),
    ],
)
def test_mixed_session_never_speaks_only_one_lever(checkin):
    # Whatever the warning, a mixed day names a rounds/conditioning lever and a
    # sets/load lever, so neither half of the session is left unaddressed.
    adjustment = build_readiness_adjustment(checkin, ReadinessContext(today_session=_mixed_session()))

    action = adjustment.action.lower()
    combat_lever = any(term in action for term in ("round", "sparring", "conditioning", "impact"))
    strength_lever = any(term in action for term in ("set", "load", "lift"))
    assert combat_lever, adjustment.action
    assert strength_lever, adjustment.action
    _assert_card_shape(adjustment)


def test_mixed_multi_signal_reason_names_both_levers_without_a_signal_count():
    # The reason's "reduce X" clause must cover the same two levers as the action.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat"),
        ReadinessContext(today_session=_mixed_session()),
    )

    assert adjustment.decision == "modify"
    assert adjustment.reason == (
        "Your readiness is down, so reduce hard combat work and heavy loading today."
    )
    assert "signals are stacking" not in adjustment.reason
    assert "sparring" in adjustment.action.lower()
    assert "top sets" in adjustment.action
    _assert_card_shape(adjustment)


def test_mixed_multi_signal_pull_back_uses_the_exact_two_lever_action():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor", body="flat", pain="manageable"),
        ReadinessContext(today_session=_mixed_session(effective_load="hard")),
    )

    assert adjustment.decision == "pull_back"
    assert adjustment.reason == (
        "Your readiness is too low for hard combat work or heavy loading today."
    )
    assert adjustment.action == (
        "Skip hard combat work and heavy loading today. "
        "Use recovery or light mobility instead."
    )
    assert "signals are stacking" not in adjustment.message
    _assert_card_shape(adjustment)


def test_mixed_session_copy_differs_from_both_pure_modalities():
    # Mixed is its own framing now: no longer a copy of the combat default, and not
    # the strength copy either.
    checkin = ReadinessCheckin(sleep="poor")
    mixed = build_readiness_adjustment(checkin, ReadinessContext(today_session=_mixed_session()))
    combat = build_readiness_adjustment(
        checkin, ReadinessContext(today_session=_session(title="Technical work", session_type="skill"))
    )
    strength = build_readiness_adjustment(
        checkin, ReadinessContext(today_session=_session(title="Technical work", session_type="strength_power"))
    )

    assert mixed.action != combat.action
    assert mixed.action != strength.action


_CONTACT_SPORT_PLAN = {"technical_style": "MMA"}


@pytest.mark.parametrize("session_type", ["sparring", "mixed"])
def test_contact_suffix_skipped_when_action_already_drops_contact(session_type):
    # High-risk contact day whose action already says "Skip sparring…": appending
    # "and do not add extra contact rounds" only restated it.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(
            today_session=_session(title="Hard sparring and max squat", session_type=session_type),
            active_plan=_CONTACT_SPORT_PLAN,
        ),
    )

    assert adjustment.session_risk == "high"
    assert adjustment.decision == "modify"
    assert "sparring" in adjustment.action.lower()
    assert "do not add extra contact rounds" not in adjustment.action
    _assert_card_shape(adjustment)


@pytest.mark.parametrize("session_type", ["sparring", "mixed"])
def test_contact_suffix_still_added_when_action_never_mentions_contact(session_type):
    # The suffix still carries information when the action only talks about
    # rounds/load, so it must survive the redundancy guard.
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(previous_session="very_hard"),
        ReadinessContext(
            today_session=_session(title="Hard sparring and max squat", session_type=session_type),
            phase="SPP",
            active_plan=_CONTACT_SPORT_PLAN,
        ),
    )

    assert adjustment.session_risk == "high"
    assert adjustment.decision == "modify"
    assert adjustment.action.endswith("and do not add extra contact rounds.")
    _assert_card_shape(adjustment)


def test_high_risk_strength_day_names_maxes_and_grinders():
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(sleep="poor"),
        ReadinessContext(today_session=_session(title="Heavy squat 1rm work")),
    )

    assert adjustment.decision == "modify"
    assert adjustment.session_risk == "high"
    assert "maxes or grinders" in adjustment.action.lower()
    assert "round" not in adjustment.action.lower()
    _assert_card_shape(adjustment)


class TestContextIsNotASignal:
    """Camp phase and fight week change how cautious a call is. They are not
    evidence that anything is wrong with the athlete, and must never be counted
    as one of the signals that set the decision."""

    def _adjust(self, *, phase="GPP", fight_date=None, session=None, **checkin):
        return build_readiness_adjustment(
            ReadinessCheckin(phase=phase, **checkin),
            ReadinessContext(
                training_day="2026-08-02",
                phase=phase,
                active_plan={"fight_date": fight_date} if fight_date else None,
                today_session=session,
            ),
        )

    def test_the_same_check_in_is_not_harsher_just_because_of_the_calendar(self):
        # The regression this class exists for: one poor night read as three
        # warning signs in taper and pulled the athlete off combat work, while the
        # identical check-in in GPP only reduced the session.
        technical = _session(title="Technical drilling", session_type="skill")
        gpp = self._adjust(sleep="poor", phase="GPP", session=technical)
        taper = self._adjust(
            sleep="poor", phase="TAPER", fight_date="2026-08-06", session=technical
        )
        assert gpp.decision == taper.decision == "modify"

    def test_context_never_appears_in_the_trigger_list(self):
        adjustment = self._adjust(
            sleep="poor", phase="TAPER", fight_date="2026-08-06",
            session=_session(title="Technical drilling", session_type="skill"),
        )
        assert trigger_labels(adjustment.triggers) == ("Poor sleep",)
        assert context_labels(adjustment.triggers) == ("Fight week", "Taper phase")

    def test_context_alone_is_a_planned_reduction_not_a_problem(self):
        adjustment = self._adjust(
            phase="TAPER", fight_date="2026-08-06",
            session=_session(title="Technical drilling", session_type="skill"),
        )
        assert adjustment.decision == "train_as_planned"
        assert trigger_labels(adjustment.triggers) == ()

    def test_no_athlete_facing_copy_calls_context_a_warning(self):
        for phase, fight_date in (("TAPER", "2026-08-06"), ("REINTEGRATION", None), ("GPP", None)):
            adjustment = self._adjust(
                sleep="poor", body="flat", pain="manageable",
                phase=phase, fight_date=fight_date,
            )
            assert "warning" not in adjustment.message.lower()


class TestStakesEscalation:
    """Context raises the decision one level only where being wrong is expensive.
    The calendar is not what makes a day risky: exposure is."""

    SPAR = {"session_type": "sparring", "title": "Hard sparring"}
    TECHNICAL = {"session_type": "skill", "title": "Technical drilling"}

    def _decision(self, *, phase, fight_date=None, session=None, **checkin):
        return build_readiness_adjustment(
            ReadinessCheckin(phase=phase, **checkin),
            ReadinessContext(
                training_day="2026-08-02",
                phase=phase,
                active_plan={"fight_date": fight_date} if fight_date else None,
                today_session=session,
            ),
        ).decision

    def test_no_elevated_stakes_means_no_escalation(self):
        assert self._decision(sleep="poor", phase="GPP", session=self.TECHNICAL) == "modify"

    def test_hard_exposure_in_fight_week_escalates(self):
        assert self._decision(
            sleep="poor", phase="TAPER", fight_date="2026-08-06", session=self.SPAR
        ) == "pull_back"

    def test_an_unconfirmed_session_in_fight_week_escalates(self):
        # We cannot grade what we cannot resolve, so this is the "safer option
        # rather than guessing" case.
        assert self._decision(
            sleep="poor", phase="TAPER", fight_date="2026-08-06"
        ) == "pull_back"

    def test_light_exposure_in_fight_week_does_not_escalate(self):
        # The distinction that matters: fight week does not escalate on its own.
        assert self._decision(
            sleep="poor", phase="TAPER", fight_date="2026-08-06", session=self.TECHNICAL
        ) == "modify"

    def test_competition_tomorrow_escalates_whatever_the_session(self):
        assert self._decision(
            sleep="poor", phase="TAPER", fight_date="2026-08-03", session=self.TECHNICAL
        ) == "pull_back"

    def test_a_clean_check_in_never_escalates(self):
        assert self._decision(
            phase="TAPER", fight_date="2026-08-03", session=self.SPAR
        ) == "train_as_planned"


def test_the_stacked_signal_tier_is_calendar_independent():
    # There is exactly one place camp context may escalate a decision, and it
    # requires costly exposure. This branch used to promote on the calendar too,
    # so the same three signals on the same medium-risk session were a reduced
    # session in GPP and a pull-back in taper — the behaviour the trigger/context
    # split exists to remove, surviving in one branch.
    signals = ("poor_sleep", "flat_body", "repeated_poor_readiness")
    decisions = {
        _soft_warning_message(
            signals, session_risk="medium", phase=phase, fight_week=fight_week
        )[0]
        for phase, fight_week in (("GPP", False), ("TAPER", False), ("REINTEGRATION", False), ("SPP", True))
    }
    assert decisions == {"modify"}


def test_the_stacked_signal_tier_still_pulls_back_on_exposure_and_pain():
    # What DOES decide it: how exposed the athlete is, and whether one of the
    # signals is pain. Both are signal-driven, and both survive untouched.
    hard, _, _, _ = _soft_warning_message(
        ("poor_sleep", "flat_body", "repeated_poor_readiness"),
        session_risk="high", phase="GPP", fight_week=False,
    )
    assert hard == "pull_back"

    painful, _, _, _ = _soft_warning_message(
        ("poor_sleep", "flat_body", "manageable_pain"),
        session_risk="medium", phase="GPP", fight_week=False,
    )
    assert painful == "pull_back"
