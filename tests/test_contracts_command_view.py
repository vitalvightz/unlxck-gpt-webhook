"""Tests for the normalized command-view builder + risk watch (Block 4 §6, §7)."""

from api.contracts.command_view import (
    build_command_view,
    make_risk,
    resolve_decision_tier,
    sort_risk_watch,
    visible_risk_watch,
)

TODAY = "2026-06-18"
PLAN = {"id": "plan-1", "name": "Camp A", "phase": "SPP"}
READINESS_REASON = "\n".join(
    [
        "Session reduced.",
        "Poor sleep means your body has less room to recover today.",
        "Cut 1 round and do not add extra conditioning.",
    ]
)


def _rec(training_day=TODAY, decision="modify", reason=READINESS_REASON, triggers=None):
    return {
        "training_day": training_day,
        "decision": decision,
        "reason": reason,
        "triggers": list(triggers or []),
    }


class TestEmptyState:
    def test_no_active_plan_yields_empty_state_with_intake_cta(self):
        view = build_command_view(current_training_day=TODAY, plan=None)
        assert view.active_plan == {}
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.completion_status == "not_started"
        assert [a.id for a in view.quick_actions] == ["complete_intake"]
        assert view.quick_actions[0].route == "/intake"

    def test_empty_plan_mapping_is_treated_as_no_plan(self):
        view = build_command_view(current_training_day=TODAY, plan={})
        assert view.active_plan == {}
        assert [a.id for a in view.quick_actions] == ["complete_intake"]


class TestRecommendationMirror:
    def test_active_plan_no_checkin_is_not_checked_in(self):
        view = build_command_view(current_training_day=TODAY, plan=PLAN, recommendation=None)
        assert view.active_plan.get("id") == "plan-1"
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.recommendation_reason is None
        assert {a.id for a in view.quick_actions} == {"open_today", "view_plan"}

    def test_active_plan_accepts_persisted_plan_field_names(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan={"plan_id": "plan-2", "plan_name": "Fight camp", "status": "ready"},
            recommendation=None,
        )
        assert view.active_plan.get("id") == "plan-2"
        assert view.active_plan.get("name") == "Fight camp"
        assert {a.id for a in view.quick_actions} == {"open_today", "view_plan"}
        assert any(a.route == "/plans/plan-2" for a in view.quick_actions)

    def test_valid_recommendation_is_mirrored(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, recommendation=_rec(decision="pull_back")
        )
        assert view.today.recommendation_state == "pull_back"
        assert view.today.recommendation_reason == READINESS_REASON

    def test_expired_recommendation_returns_not_checked_in(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, recommendation=_rec(training_day="2026-06-17")
        )
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.recommendation_reason is None


class TestCompletionStatus:
    def test_started_completion_surfaces_started(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, completion={"status": "started"}
        )
        assert view.today.completion_status == "started"

    def test_terminal_completions_surface_status(self):
        for status in ("done", "modified", "skipped"):
            view = build_command_view(
                current_training_day=TODAY, plan=PLAN, completion={"status": status}
            )
            assert view.today.completion_status == status


class TestGracefulDegradation:
    def test_missing_structured_plan_session_does_not_crash(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, next_session=None, week_summary=None
        )
        assert view.today.next_session == {}
        assert view.week_summary == {}

    def test_next_session_passthrough(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, next_session={"weekday": "Thu", "load": "hard"}
        )
        assert view.today.next_session == {"weekday": "Thu", "load": "hard"}
        assert view.today.session_scope == "next"
        assert view.today.session_label == "Next session"

    def test_today_session_label_when_scoped_to_today(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            next_session={"weekday": "Thu", "load": "hard"},
            session_scope="today",
        )
        assert view.today.session_scope == "today"
        assert view.today.session_label == "Today's session"


class TestRiskWatch:
    def test_risk_watch_is_sorted_by_priority(self):
        risks = [
            make_risk("fatigue", text="Poor sleep streak"),
            make_risk("stop_red_flag", text="Stop"),
            make_risk("high_pain", text="High pain"),
        ]
        view = build_command_view(current_training_day=TODAY, plan=PLAN, risks=risks)
        categories = [item.category for item in view.risk_watch]
        assert categories == ["stop_red_flag", "high_pain", "fatigue"]

    def test_visible_risk_watch_limits_to_two_plus_overflow(self):
        ordered = sort_risk_watch(
            [
                make_risk("stop_red_flag"),
                make_risk("active_injury_worse"),
                make_risk("high_pain"),
                make_risk("fatigue"),
            ]
        )
        visible, overflow = visible_risk_watch(ordered)
        assert [v.category for v in visible] == ["stop_red_flag", "active_injury_worse"]
        assert overflow == 2

    def test_risk_items_carry_icon_label_text_and_tone(self):
        item = make_risk("high_pain", text="Pain is high")
        assert item.icon and item.label and item.tone
        assert item.text == "Pain is high"

    def test_mapping_risks_are_coerced(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            risks=[{"category": "weight_cut", "text": "5% to cut"}],
        )
        assert view.risk_watch[0].category == "weight_cut"
        assert view.risk_watch[0].text == "5% to cut"


class TestShape:
    def test_view_serializes_to_documented_shape(self):
        view = build_command_view(current_training_day=TODAY, plan=PLAN)
        dumped = view.model_dump()
        assert set(dumped) == {
            "active_plan",
            "today",
            "risk_watch",
            "open_injuries",
            "week_summary",
            "quick_actions",
        }
        assert set(dumped["today"]) == {
            "training_day",
            "recommendation_state",
            "recommendation_reason",
            "decision_tier",
            "injury_hold_exempt",
            "recommendation_contributors",
            "recommendation_sources",
            "recommendation_confidence",
            "recommendation_confidence_note",
            "recommendation_sources_are_historical",
            "warnings",
            "next_session",
            "session_scope",
            "session_label",
            "completion_status",
        }
        assert dumped["today"]["training_day"] == TODAY


class TestDecisionTier:
    """The single authoritative tier the banner and the risk footer both render."""

    def test_green_modify_pullback_map_directly(self):
        assert resolve_decision_tier(recommendation_state="train_as_planned", recommendation_reason="Full session.") == "green"
        assert resolve_decision_tier(recommendation_state="modify", recommendation_reason="Session reduced.") == "modify"
        assert resolve_decision_tier(recommendation_state="not_checked_in", recommendation_reason=None) == "not_checked_in"

    def test_plain_pull_back_is_pull_back_not_stop(self):
        # A soft-warning pull-back ("Pull back today.") is a PULL BACK tier, never a
        # STOP — this is the exact banner/footer contradiction being closed.
        reason = "\n".join(["Pull back today.", "Several warnings are showing.", "Skip combat work."])
        assert resolve_decision_tier(recommendation_state="pull_back", recommendation_reason=reason) == "pull_back"

    def test_rehab_only_and_no_training_are_stop(self):
        rehab = "\n".join(["Rehab only today.", "The injury is worse.", "No sparring."])
        assert resolve_decision_tier(recommendation_state="pull_back", recommendation_reason=rehab) == "stop"
        no_train = "\n".join(["No training today.", "You selected a red flag symptom.", "Seek medical advice."])
        assert resolve_decision_tier(recommendation_state="pull_back", recommendation_reason=no_train) == "stop"

    def test_severe_injury_is_stop_even_before_checkin(self):
        tier = resolve_decision_tier(
            recommendation_state="not_checked_in",
            recommendation_reason=None,
            open_injuries=[{"severity": "severe", "status": "open"}],
        )
        assert tier == "stop"

    def test_tier_never_weaker_than_a_stop_level_risk(self):
        # If a stop-level risk is showing in the footer, the tier is at least STOP so
        # the two surfaces can never contradict.
        tier = resolve_decision_tier(
            recommendation_state="not_checked_in",
            recommendation_reason=None,
            risks=[make_risk("active_injury_worse", text="Active severe injury.")],
        )
        assert tier == "stop"

    def test_build_command_view_exposes_the_tier(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(decision="modify"),
        )
        assert view.today.decision_tier == "modify"


class TestContributorsAndSources:
    """The card's "why today changed" chips and its "Based on" line, both derived
    from the engine's own trigger codes so they cannot drift from the decision."""

    def test_contributors_are_exposed_for_a_live_recommendation(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["poor_sleep", "flat_body", "phase_spp"]),
        )
        assert view.today.recommendation_contributors == ["Poor sleep", "Body feels flat"]

    def test_context_markers_never_render_as_contributors(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["phase_taper", "contact_sport", "session_risk_low"]),
        )
        assert view.today.recommendation_contributors == []

    def test_contributors_are_capped_at_three(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(
                triggers=[
                    "poor_sleep",
                    "flat_body",
                    "manageable_pain",
                    "recent_hard_session",
                    "fight_week",
                ]
            ),
        )
        assert len(view.today.recommendation_contributors) == 3

    def test_a_streak_absorbs_the_single_day_signal_it_covers(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["poor_sleep", "poor_sleep_3_day_streak"]),
        )
        assert view.today.recommendation_contributors == ["Poor sleep, 3 days"]

    def test_sources_name_only_the_inputs_the_decision_used(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["repeated_poor_readiness", "session_risk_high"]),
        )
        assert view.today.recommendation_sources == [
            "today's check-in",
            "your last few check-ins",
            "today's planned session",
        ]

    def test_open_injuries_are_named_as_a_source(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["poor_sleep"]),
            open_injuries=[{"severity": "moderate", "status": "open", "label": "left knee"}],
        )
        assert "your tracked injuries" in view.today.recommendation_sources

    def test_a_degraded_context_hold_claims_no_history_it_could_not_read(self):
        # The hold exists BECAUSE the history failed to load, so the card must not
        # then claim it was based on that history.
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["context_degraded"]),
        )
        assert view.today.recommendation_contributors == ["Check-in history incomplete"]
        assert view.today.recommendation_sources == ["today's check-in"]

    def test_an_expired_recommendation_exposes_no_contributors(self):
        # Expired recommendations are history, never live readiness — and an
        # explanation of a decision that is no longer in force is worse than none.
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(training_day="2026-06-17", triggers=["poor_sleep"]),
        )
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.recommendation_contributors == []
        assert view.today.recommendation_sources == []

    def test_no_recommendation_yields_empty_lists(self):
        view = build_command_view(current_training_day=TODAY, plan=PLAN)
        assert view.today.recommendation_contributors == []
        assert view.today.recommendation_sources == []


class TestConfidenceBand:
    """Confidence reports DATA COMPLETENESS, not predictive accuracy. It answers
    "how much did this call have to go on", which the engine knows for certain."""

    def test_no_triggers_yields_no_band_rather_than_a_confident_default(self):
        # A recommendation stored before the engine recorded triggers has nothing
        # to judge it by. Defaulting to "high" would put the most confident claim
        # on the one decision nothing is known about.
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, recommendation=_rec(triggers=[])
        )
        assert view.today.recommendation_state == "modify"
        assert view.today.recommendation_confidence is None
        assert view.today.recommendation_confidence_note == ""

    def test_a_failed_read_outranks_the_thinness_it_causes(self):
        # A failed history read leaves the engine seeing no history, so it also
        # tags sparse_history. Reporting the thinness would tell the athlete their
        # history is missing when it exists and could not be loaded, and would
        # point them at a fix (check in tomorrow) that cannot help.
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["checkins_unavailable", "poor_sleep", "sparse_history"]),
        )
        assert view.today.recommendation_confidence == "moderate"
        assert "couldn't load your recent check-ins" in view.today.recommendation_confidence_note

    def test_a_complete_context_is_high_confidence_with_no_qualifier(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["poor_sleep", "session_risk_high"]),
        )
        assert view.today.recommendation_confidence == "high"
        assert view.today.recommendation_confidence_note == ""

    def test_no_prior_checkins_drops_confidence_to_moderate(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["poor_sleep", "sparse_history"]),
        )
        assert view.today.recommendation_confidence == "moderate"
        assert "no recent days to compare" in view.today.recommendation_confidence_note

    def test_an_unresolved_session_drops_confidence_to_moderate(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["poor_sleep", "session_unresolved"]),
        )
        assert view.today.recommendation_confidence == "moderate"

    def test_an_unavailable_context_is_low_confidence(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(decision="pull_back", triggers=["context_unavailable"]),
        )
        assert view.today.recommendation_confidence == "low"

    def test_the_qualifier_names_the_strongest_gap_only(self):
        # One reason, not a list of everything missing: the athlete needs the thing
        # to act on, and a stacked list reads as an error log.
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["context_degraded", "sparse_history"]),
        )
        note = view.today.recommendation_confidence_note
        assert note.count("Less to go on today") == 1
        assert "couldn't load some of your recent history" in note

    def test_completeness_codes_never_render_as_contributors(self):
        # They describe the DATA, not the athlete. "Sparse history" in the "what
        # moved this" list would read as a reason the session changed, which it is
        # not — the confidence band is where it belongs.
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            recommendation=_rec(triggers=["poor_sleep", "sparse_history", "session_unresolved"]),
        )
        assert view.today.recommendation_contributors == ["Poor sleep"]


class TestContributorLimit:
    def test_a_zero_limit_suppresses_the_list(self):
        from api.contracts.readiness_message import contributor_labels

        assert contributor_labels(("poor_sleep", "flat_body"), limit=0) == ()
        assert contributor_labels(("poor_sleep", "flat_body"), limit=1) == ("Poor sleep",)


class TestSelfSufficientDecisions:
    """A decision that needs no history to stand keeps its full band.

    Thin data takes nothing away from a red-flag stop. Tagging it anyway produced
    the worst reading on the card: "STOP TODAY" beside a lowered band, which says
    the stop is uncertain when it is the most certain call the engine makes.
    """

    def _band_for(self, checkin_kwargs) -> tuple[str, str]:
        from api.contracts.readiness_message import (
            ReadinessCheckin,
            ReadinessContext,
            build_readiness_adjustment,
            confidence_band,
        )

        # A brand-new athlete: no prior check-ins, no resolvable session.
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(**checkin_kwargs), ReadinessContext(training_day=TODAY)
        )
        return adjustment.decision, confidence_band(adjustment.triggers)

    def test_a_red_flag_stop_is_not_reported_as_uncertain(self):
        assert self._band_for({"sharp_pain": True}) == ("pull_back", "high")
        assert self._band_for({"neurological_symptoms": True}) == ("pull_back", "high")

    def test_an_injury_stop_is_not_reported_as_uncertain(self):
        assert self._band_for({"active_injury": "worse"}) == ("pull_back", "high")

    def test_a_high_pain_stop_is_not_reported_as_uncertain(self):
        assert self._band_for({"pain": "high"}) == ("pull_back", "high")

    def test_an_ordinary_fatigue_call_still_reflects_thin_data(self):
        # Poor sleep genuinely reads differently against a history, so the band
        # still drops. Only the self-sufficient signals are exempt.
        assert self._band_for({"sleep": "poor"}) == ("modify", "moderate")
