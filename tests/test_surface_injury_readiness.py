"""Stable surface (skin) injuries must not steer Today's readiness decision.

A blister, graze or abrasion is integumentary, not musculoskeletal. While it is
intact, non-severe and carries no red flag it is a hygiene/friction constraint:
it stays visible and checkable, but it must not reduce the session, suppress
recovery, or produce rehab work. When it DOES get worse, what changes is decided
by the skin — open? bleeding? coverable? — and the strongest outcome is losing
contact work, never losing the day.

These tests pin both halves: the canonical classification
(``fightcamp.injury_registry.classify_surface_injury``) and what the Today engine
does with it, including that every existing severe / infection / bleeding
protection still fires.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.contracts.command_view import build_command_view
from api.contracts.injury_checkin import DeclaredInjury, reconcile_injury_checkin
from api.contracts.readiness_message import (
    ReadinessCheckin,
    ReadinessContext,
    build_readiness_adjustment,
    classify_injury_surface,
    decision_sources,
    explanation_metadata,
    safety_checks,
    surface_exposure_codes,
    surface_restriction_codes,
)
from api.models import InjuryFlagRecord, TodayInjuryDeclaration
from api.routes.daily import _map_injury_flag
from api.services.today_service import (
    _guided_intake_injury_candidate,
    _load_relevant_worse_injury,
    _with_surface_class,
)
from fightcamp.injury_registry import classify_surface_injury
from tests.support import _build_client

ATHLETE = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"

HARD_SPARRING = {
    "title": "Hard sparring",
    "session_type": "sparring",
    "effective_load": "hard",
}
NON_CONTACT_RECOVERY = {
    "title": "Easy aerobic bike and mobility",
    "session_type": "recovery",
    "effective_load": "easy",
}
STRENGTH_SESSION = {
    "title": "Moderate strength accessories",
    "session_type": "strength_power",
    "effective_load": "technical",
}
# Repeated friction over a covered area without being contact work.
FRICTION_SESSION = {
    "title": "Technical pad and bag work",
    "session_type": "skill",
    "effective_load": "technical",
}
# Direct impact with nobody else involved. An open wound is exposed here just as
# it is in sparring, so this has to reach the same contact restriction.
IMPACT_SESSION = {
    "title": "Plyometric landings and depth jumps",
    "session_type": "impact",
    "effective_load": "hard",
}
STRUCTURED_IMPACT_SESSION = {
    "title": "Power development",
    "session_type": "strength_power",
    "effective_load": "hard",
    "blocks": [{"title": "Depth jumps", "type": "impact", "tags": ["high_impact_plyo"]}],
}
HARD_BAG_SESSION = {
    "title": "Hard bag power rounds",
    "session_type": "skill",
    "effective_load": "hard",
}
MIXED_CONTACT_IMPACT_SESSION = {
    "title": "Sparring and power development",
    "session_type": "mixed",
    "effective_load": "hard",
    "blocks": [
        {"title": "Technical sparring", "type": "sparring"},
        {"title": "Repeated depth jumps", "type": "impact", "tags": ["landing_stress_high"]},
    ],
}
# Explicitly built to avoid contact. Naming the thing it avoids must not read as
# doing it.
NO_CONTACT_SESSION = {
    "title": "Technical drilling, no contact",
    "session_type": "skill",
    "effective_load": "technical",
    "objective": "Non-contact footwork and shadow work",
}
CONTACT_FREE_SESSION = {
    "title": "Contact-free technical drilling",
    "session_type": "skill",
    "effective_load": "technical",
}
NO_HARD_SPARRING_SESSION = {
    "title": "No hard sparring",
    "session_type": "skill",
    "effective_load": "technical",
}


def _blister(**overrides):
    """A tracked blister flag as the Today service stores it."""
    return {
        "id": "flag-blister",
        "status": "open",
        "severity": "moderate",
        "body_area": "left foot",
        "description": "blister on left foot",
        "label": "Left foot blister",
        "latest_reported_status": "ongoing",
        **overrides,
    }


def _shoulder_strain(**overrides):
    return {
        "id": "flag-shoulder",
        "status": "open",
        "severity": "moderate",
        "body_area": "left shoulder",
        "description": "shoulder strain",
        "label": "Left shoulder strain",
        "latest_reported_status": "ongoing",
        "consequence": "load_sensitive",
        **overrides,
    }


def _surface_check(adjustment):
    checks = [c for c in safety_checks(adjustment.triggers) if c["code"] == "surface_injury"]
    return checks[0] if checks else None


# ---------------------------------------------------------------------------
# Canonical classification
# ---------------------------------------------------------------------------


class TestCanonicalClassification:
    def test_intact_moderate_blister_is_stable_surface(self):
        assert classify_surface_injury({"injury_type": "blister", "severity": "moderate"}).classification == (
            "stable_surface"
        )

    @pytest.mark.parametrize("injury_type", ["blister", "graze", "abrasion", "cut", "laceration"])
    def test_every_stable_skin_type_classifies_as_surface(self, injury_type):
        assert classify_surface_injury({"injury_type": injury_type}).classification == "stable_surface"

    def test_worse_but_intact_is_a_local_restriction_not_a_stop(self):
        assessment = classify_surface_injury(
            {
                "injury_type": "blister",
                "severity": "mild",
                "latest_reported_status": "worse",
                "skin_integrity": "intact",
                "bleeding_status": "none",
                "drainage": "none",
                "infection_signs": [],
                "coverable": "yes",
                "friction_or_contact_problem": "no",
            }
        )
        assert assessment.classification == "surface_local_restriction"
        assert not assessment.blocks_contact

    def test_open_but_clean_and_coverable_blocks_contact_only(self):
        assessment = classify_surface_injury(
            {
                "injury_type": "blister",
                "skin_integrity": "open",
                "bleeding_status": "controlled",
                "drainage": "none",
                "coverable": "yes",
            }
        )
        assert assessment.classification == "surface_no_contact"
        assert assessment.blocks_contact
        assert not assessment.needs_medical_review

    def test_not_coverable_blocks_contact(self):
        assert (
            classify_surface_injury({"injury_type": "graze", "coverable": "no"}).classification
            == "surface_no_contact"
        )

    def test_worse_with_unknown_skin_integrity_is_cautious_but_not_a_stop(self):
        assessment = classify_surface_injury(
            {"injury_type": "blister", "latest_reported_status": "worse", "skin_integrity": "unknown"}
        )
        assert assessment.classification == "surface_no_contact"

    @pytest.mark.parametrize(
        "red_flag",
        [
            {"infection_signs": ["spreading_redness"]},
            {"bleeding_status": "uncontrolled"},
            {"drainage": "present"},
            {"severity": "severe"},
            {"flags": ["red_flag_infection"]},
        ],
    )
    def test_red_flags_route_to_medical_review(self, red_flag):
        assessment = classify_surface_injury({"injury_type": "cut", **red_flag})
        assert assessment.classification == "surface_medical_review"
        assert assessment.needs_medical_review

    def test_non_surface_injuries_are_untouched(self):
        assert classify_surface_injury({"injury_type": "strain"}).classification == "non_surface"
        assert classify_surface_injury({"injury_type": "concussion"}).classification == "non_surface"
        assert classify_surface_injury(None).classification == "non_surface"

    def test_stored_flag_text_resolves_through_the_engine_adapter(self):
        # Today flags carry free text, not a structured injury_type — the adapter
        # scores the type first, then hands it to the same canonical classifier.
        assert classify_injury_surface(_blister()) == "stable_surface"
        assert classify_injury_surface(_shoulder_strain()) == "non_surface"


# ---------------------------------------------------------------------------
# Today readiness decisions
# ---------------------------------------------------------------------------


class TestStableSurfaceDoesNotDrive:
    def test_poor_sleep_alone_drives_the_decision_with_a_blister_present(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(sleep="poor"),
            ReadinessContext(today_session=HARD_SPARRING, open_injuries=[_blister()]),
        )

        assert adjustment.decision == "modify"
        assert "tracked_injury_high_risk_session" not in adjustment.triggers
        assert "active_injury_worse" not in adjustment.triggers

        metadata = explanation_metadata(adjustment.triggers)
        assert metadata["causal_triggers"] == ["Poor sleep"]
        # The blister was assessed and changed nothing: a safety CHECK, never a cause.
        assert metadata["safety_checks"] == [
            {
                "code": "surface_injury",
                "label": "Skin injury",
                "result": "no_session_change",
                "result_label": "No session change",
            }
        ]
        assert "Active injury" not in metadata["causal_triggers"]

    def test_good_readiness_with_a_blister_trains_as_planned(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(today_session=HARD_SPARRING, open_injuries=[_blister()]),
        )

        assert adjustment.decision == "train_as_planned"
        assert "tracked_injury_high_risk_session" not in adjustment.triggers
        # Still visible, as a hygiene note rather than a load instruction.
        assert "clean and covered" in adjustment.action
        assert _surface_check(adjustment)["result"] == "no_session_change"

    def test_a_graze_over_the_ribs_is_not_treated_as_a_rib_injury(self):
        # The tissue UNDER a skin wound is not injured: a rib graze is a dressing
        # problem, so it must not inherit the rib region's structural restriction.
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[
                    _blister(
                        id="flag-graze",
                        body_area="ribs",
                        description="graze over the ribs",
                        label="Rib graze",
                        consequence="structural",
                    )
                ],
            ),
        )

        assert adjustment.decision == "train_as_planned"
        assert "active_injury_restriction" not in adjustment.triggers

    def test_stable_blister_does_not_suppress_a_recovery_session(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(today_session=NON_CONTACT_RECOVERY, open_injuries=[_blister()]),
        )

        assert adjustment.decision == "train_as_planned"

    def test_the_tracked_injury_warning_still_fires_for_a_real_injury(self):
        # Only the blister was excluded from the tracked-injury path: a genuine
        # load-relevant injury on a hard session still raises the warning.
        blister_only = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(today_session=HARD_SPARRING, open_injuries=[_blister()]),
        )
        with_strain = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[_blister(), _shoulder_strain(consequence=None)],
            ),
        )

        assert "tracked_injury_high_risk_session" not in blister_only.triggers
        assert "tracked_injury_high_risk_session" in with_strain.triggers
        assert with_strain.decision == "modify"

    def test_a_declared_stable_injury_with_no_tracked_flags_still_warns(self):
        # No structured injury data to classify, so the check-in's own answer is
        # honoured exactly as before.
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(active_injury="stable"),
            ReadinessContext(today_session=HARD_SPARRING),
        )

        assert "tracked_injury_high_risk_session" in adjustment.triggers


class TestWorseningSurfaceInjury:
    def test_worse_but_intact_blister_is_not_rehab_only(self):
        adjustment = build_readiness_adjustment(
            # The Today service escalates the check-in to "worse" on an injury
            # report; a skin injury must not turn that into a rehab-only day.
            ReadinessCheckin(active_injury="worse"),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[
                    _blister(
                        severity="mild",
                        latest_reported_status="worse",
                        skin_integrity="intact",
                        bleeding_status="none",
                        drainage="none",
                        infection_signs=[],
                        coverable="yes",
                        friction_or_contact_problem="no",
                    )
                ],
            ),
        )

        assert adjustment.decision != "pull_back"
        assert adjustment.title != "Rehab only today."
        assert "active_injury_worse" not in adjustment.triggers
        assert _surface_check(adjustment)["result"] == "local_protection_only"

    def test_poor_sleep_and_open_wound_accumulate_mixed_exposure_restrictions(self):
        # Poor sleep already reduced the session. The wound adds both targeted
        # removals on top without erasing the readiness modification.
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(sleep="poor"),
            ReadinessContext(
                today_session=MIXED_CONTACT_IMPACT_SESSION,
                open_injuries=[
                    _blister(
                        skin_integrity="open",
                        bleeding_status="controlled",
                        drainage="none",
                        coverable="yes",
                    )
                ],
            ),
        )

        assert adjustment.decision in {"modify", "pull_back"}
        assert "Skip all contact work today, including sparring, clinch, and grappling." in adjustment.action
        assert "Remove or replace all direct-impact work today" in adjustment.action
        # The poor-sleep restriction is still there in full.
        assert "conditioning finishers" in adjustment.action
        assert "Poor sleep" in adjustment.reason

        metadata = explanation_metadata(adjustment.triggers)
        assert metadata["causal_triggers"] == ["Poor sleep", "Open skin injury"]
        assert metadata["surface_exposures"] == ["contact_exposure", "direct_impact_exposure"]
        assert metadata["surface_restrictions"] == ["remove_contact", "remove_direct_impact"]
        assert metadata["safety_checks"][0]["result"] == "multiple_restrictions"

    def test_a_pulled_back_day_still_states_the_contact_removal(self):
        # The instruction is never dropped because the existing copy "sounds
        # like" it already covers contact — that inference is what this closes.
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(pain="manageable", sleep="poor", body="flat"),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[_blister(skin_integrity="open", coverable="yes")],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert "Skip all contact work today, including sparring, clinch, and grappling." in adjustment.action
        assert "remove_contact" in surface_restriction_codes(adjustment.triggers)

    def test_open_blister_before_sparring_removes_contact_only(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(active_injury="worse"),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[
                    _blister(
                        latest_reported_status="worse",
                        skin_integrity="open",
                        bleeding_status="controlled",
                        drainage="none",
                        coverable="yes",
                    )
                ],
            ),
        )

        # Contact is removed; the day is not.
        assert adjustment.decision == "modify"
        assert adjustment.title == "Contact off, session on."
        assert "remove_contact" in surface_restriction_codes(adjustment.triggers)
        assert "Skip all contact work today, including sparring, clinch, and grappling." in adjustment.action
        # The wound's own hygiene guidance survives alongside the restriction.
        assert "clean and covered" in adjustment.action
        assert _surface_check(adjustment)["result"] == "no_contact"

    def test_open_blister_does_not_block_a_non_contact_recovery_session(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(active_injury="worse"),
            ReadinessContext(
                today_session=NON_CONTACT_RECOVERY,
                open_injuries=[
                    _blister(
                        latest_reported_status="worse",
                        skin_integrity="open",
                        bleeding_status="controlled",
                        coverable="yes",
                    )
                ],
            ),
        )

        assert adjustment.decision == "train_as_planned"
        assert surface_restriction_codes(adjustment.triggers) == ()
        assert _surface_check(adjustment)["result"] == "no_session_change"

    def test_wound_that_cannot_stay_covered_loses_contact(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[_blister(skin_integrity="intact", coverable="no")],
            ),
        )

        assert adjustment.decision == "modify"
        assert "remove_contact" in surface_restriction_codes(adjustment.triggers)
        assert "Skip all contact work today, including sparring, clinch, and grappling." in adjustment.action
        # It is intact, just not sealable — the copy must not claim it is open.
        assert "can't be kept covered" in adjustment.reason
        assert "is open" not in adjustment.reason
        assert _surface_check(adjustment)["result"] == "no_contact"


class TestSurfaceSafetyPathwaysPreserved:
    def test_infection_signs_route_to_review_and_block_contact(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[_blister(infection_signs=["spreading_redness", "pus"])],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert adjustment.title == "Get this checked."
        assert "surface_injury_medical_review" in adjustment.triggers
        assert "sparring" in adjustment.action.lower()
        assert "medical advice" in adjustment.safety.lower()
        assert _surface_check(adjustment)["result"] == "medical_review"

    def test_uncontrolled_bleeding_keeps_urgent_protection(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[_blister(bleeding_status="uncontrolled")],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert "bleeding" in adjustment.reason.lower()
        assert "surface_injury_medical_review" in adjustment.triggers

    def test_infection_is_not_waved_through_on_a_safe_filler_session(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session={"title": "Breathing reset and mobility/rehab", "session_type": "recovery"},
                open_injuries=[_blister(infection_signs=["fever"])],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert adjustment.title == "Get this checked."

    def test_severe_surface_injury_keeps_the_existing_severe_stop(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(today_session=HARD_SPARRING, open_injuries=[_blister(severity="severe")]),
        )

        assert adjustment.decision == "pull_back"
        assert adjustment.title == "Rehab only today."
        assert "Active severe injury" in adjustment.reason
        assert "active_injury_worse" in adjustment.triggers

    def test_red_flag_symptom_still_stops_everything(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(sharp_pain=True),
            ReadinessContext(today_session=HARD_SPARRING, open_injuries=[_blister()]),
        )

        assert adjustment.decision == "pull_back"
        assert adjustment.title == "No training today."

    def test_worsening_non_surface_injury_still_stops_training(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[_shoulder_strain(latest_reported_status="worse")],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert "is worse" in adjustment.reason
        assert "active_injury_worse" in adjustment.triggers


class TestInjuryPriorityAcrossMixedSets:
    """A skin review must never mask a stronger injury decision.

    The surface medical-review pathway is assessed alongside the red flags, but
    it is weaker than a severe or worsening non-surface injury. Returning it
    first downgraded "stop training" to "get this checked" for an athlete who
    had both — while still leaving the severe injury completely unmentioned.
    """

    def test_severe_shoulder_outranks_an_infected_blister(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[
                    _blister(infection_signs=["pus", "spreading"]),
                    _shoulder_strain(severity="severe"),
                ],
            ),
        )

        # The severe injury owns the decision.
        assert adjustment.decision == "pull_back"
        assert adjustment.title == "Rehab only today."
        assert "Active severe injury" in adjustment.reason
        assert "shoulder" in adjustment.reason.lower()
        assert "active_injury_worse" in adjustment.triggers
        # ...and the skin check is still on the record, not silently dropped.
        assert _surface_check(adjustment)["result"] == "medical_review"
        assert "safety_check:surface_injury:medical_review" in adjustment.triggers

    def test_worsening_shoulder_outranks_an_infected_blister(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[
                    _blister(bleeding_status="uncontrolled"),
                    _shoulder_strain(latest_reported_status="worse"),
                ],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert adjustment.title == "Rehab only today."
        assert "is worse" in adjustment.reason
        assert _surface_check(adjustment)["result"] == "medical_review"

    def test_red_flag_symptom_outranks_an_infected_blister_and_still_records_it(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(sharp_pain=True),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[_blister(infection_signs=["fever"])],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert adjustment.title == "No training today."
        assert "red_flag" in adjustment.triggers
        assert _surface_check(adjustment)["result"] == "medical_review"

    def test_the_skin_review_still_wins_when_nothing_stronger_is_open(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[
                    _blister(infection_signs=["pus"]),
                    _shoulder_strain(),  # tracked, but not severe and not worse
                ],
            ),
        )

        assert adjustment.title == "Get this checked."
        assert "surface_injury_medical_review" in adjustment.triggers

    def test_a_support_session_still_surfaces_the_skin_review(self):
        # The severe-injury stop is exempted on a safe filler day; that exemption
        # must not take the wound review down with it.
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session={
                    "title": "Breathing reset and mobility/rehab",
                    "session_type": "recovery",
                },
                open_injuries=[
                    _blister(infection_signs=["pus"]),
                    _shoulder_strain(severity="severe"),
                ],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert adjustment.title == "Get this checked."


class TestImpactSessionExposure:
    """Direct impact is independent from interpersonal contact."""

    def test_open_wound_replaces_impact_only_plyometrics_not_contact(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=IMPACT_SESSION,
                open_injuries=[_blister(skin_integrity="open")],
            ),
        )

        assert adjustment.decision == "modify"
        assert surface_exposure_codes(adjustment.triggers) == ("direct_impact_exposure",)
        assert surface_restriction_codes(adjustment.triggers) == ("remove_direct_impact",)
        assert "Remove or replace all direct-impact work today" in adjustment.action
        assert "repeated landings or plyometrics" in adjustment.action
        assert "Skip all contact work today" not in adjustment.action
        assert _surface_check(adjustment)["result"] == "direct_impact_removed"

    def test_open_wound_replaces_a_structured_impact_block(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=STRUCTURED_IMPACT_SESSION,
                open_injuries=[_blister(skin_integrity="open")],
            ),
        )

        assert adjustment.decision == "modify"
        assert surface_exposure_codes(adjustment.triggers) == ("direct_impact_exposure",)
        assert surface_restriction_codes(adjustment.triggers) == ("remove_direct_impact",)

    def test_open_wound_explicitly_removes_hard_bag_impact(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_BAG_SESSION,
                open_injuries=[_blister(skin_integrity="open")],
            ),
        )

        assert "direct_impact_exposure" in surface_exposure_codes(adjustment.triggers)
        assert "remove_direct_impact" in surface_restriction_codes(adjustment.triggers)
        assert "hard bag work" in adjustment.action
        assert "Remove or replace all direct-impact work today" in adjustment.action

    def test_open_wound_on_hard_sparring_removes_all_contact(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[_blister(skin_integrity="open")],
            ),
        )

        assert surface_exposure_codes(adjustment.triggers) == ("contact_exposure",)
        assert surface_restriction_codes(adjustment.triggers) == ("remove_contact",)
        assert "Skip all contact work today, including sparring, clinch, and grappling." in adjustment.action

    @pytest.mark.parametrize("session", [NO_CONTACT_SESSION, CONTACT_FREE_SESSION])
    def test_explicitly_contact_free_sessions_do_not_get_contact_restrictions(self, session):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=session,
                open_injuries=[_blister(skin_integrity="open")],
            ),
        )

        # Nothing to remove: the session already has no contact in it. The wound
        # is still checked and recorded, it just changes nothing.
        assert "contact_exposure" not in surface_exposure_codes(adjustment.triggers)
        assert "remove_contact" not in surface_restriction_codes(adjustment.triggers)

    def test_no_hard_sparring_does_not_negate_remaining_sparring(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=NO_HARD_SPARRING_SESSION,
                open_injuries=[_blister(skin_integrity="open")],
            ),
        )

        assert "contact_exposure" in surface_exposure_codes(adjustment.triggers)
        assert "remove_contact" in surface_restriction_codes(adjustment.triggers)


class TestSurfacePlusRealInjury:
    def test_shoulder_strain_drives_load_while_the_blister_stays_separate(self):
        context = ReadinessContext(
            today_session=HARD_SPARRING,
            open_injuries=[_blister(), _shoulder_strain()],
        )
        adjustment = build_readiness_adjustment(ReadinessCheckin(), context)

        # The strain, not the blister, is what restricts load.
        assert adjustment.decision == "pull_back"
        assert "active_injury_restriction" in adjustment.triggers
        assert "shoulder" in adjustment.reason.lower()
        assert "blister" not in adjustment.reason.lower()
        # The blister is still classified — independently — as stable skin.
        assert classify_injury_surface(_blister()) == "stable_surface"
        assert _surface_check(adjustment)["result"] == "no_session_change"


class TestDecisionSources:
    """"Decision based on" names inputs the decision USED, not everything tracked.

    The injury source is read from the decision's own trigger codes, which fire
    at the point an injury actually acted — so it can never be claimed by an
    injury that merely exists.
    """

    @pytest.mark.parametrize(
        ("case", "injury", "session", "expected"),
        [
            ("stable surface", {}, HARD_SPARRING, False),
            (
                "local restriction, nothing rubs it",
                {"latest_reported_status": "worse", "skin_integrity": "intact", "coverable": "yes"},
                NON_CONTACT_RECOVERY,
                False,
            ),
            (
                "local restriction, friction exposure",
                {"latest_reported_status": "worse", "skin_integrity": "intact", "coverable": "yes"},
                FRICTION_SESSION,
                True,
            ),
            (
                "open wound, non-contact day",
                {"skin_integrity": "open", "coverable": "yes"},
                NON_CONTACT_RECOVERY,
                False,
            ),
            (
                "open wound, contact day",
                {"skin_integrity": "open", "coverable": "yes"},
                HARD_SPARRING,
                True,
            ),
            ("infection signs", {"infection_signs": ["pus"]}, HARD_SPARRING, True),
        ],
    )
    def test_only_an_injury_that_acted_is_named_as_a_source(
        self, case, injury, session, expected
    ):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(sleep="poor"),
            ReadinessContext(today_session=session, open_injuries=[_blister(**injury)]),
        )

        named = "your tracked injuries" in decision_sources(adjustment.triggers)
        assert named is expected, case
        # Either way, the skin injury is recorded as a safety check.
        assert _surface_check(adjustment) is not None

    def test_a_stable_blister_is_a_safety_check_not_a_decision_source(self):
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(sleep="poor"),
            ReadinessContext(today_session=HARD_SPARRING, open_injuries=[_blister()]),
        )
        sources = decision_sources(adjustment.triggers)

        assert explanation_metadata(adjustment.triggers)["causal_triggers"] == ["Poor sleep"]
        assert _surface_check(adjustment)["result"] == "no_session_change"
        assert "your tracked injuries" not in sources
        assert "today's check-in" in sources

    def test_a_non_surface_injury_is_named_only_when_it_restricted(self):
        restricted = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(today_session=HARD_SPARRING, open_injuries=[_shoulder_strain()]),
        )
        quiet = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=NON_CONTACT_RECOVERY, open_injuries=[_shoulder_strain()]
            ),
        )

        assert "active_injury_restriction" in restricted.triggers
        assert "your tracked injuries" in decision_sources(restricted.triggers)
        assert "your tracked injuries" not in decision_sources(quiet.triggers)

    def test_an_injury_hold_still_rests_on_the_tracked_injury_alone(self):
        assert decision_sources(["injury_hold"]) == ("your tracked injuries",)

    def test_the_command_view_does_not_name_a_stable_blister_as_a_source(self):
        view = build_command_view(
            current_training_day="2026-07-31",
            plan={"id": PLAN_ID, "status": "ready"},
            recommendation={
                "training_day": "2026-07-31",
                "recommendation_state": "modify",
                "recommendation_reason": "Session reduced.",
                "recommendation_triggers": [
                    "poor_sleep",
                    "safety_check:surface_injury:no_session_change",
                ],
            },
            open_injuries=[_blister()],
        )

        assert "your tracked injuries" not in view.today.recommendation_sources
        assert view.today.recommendation_safety_checks == [
            {
                "code": "surface_injury",
                "label": "Skin injury",
                "result": "no_session_change",
                "result_label": "No session change",
            }
        ]
        # It is still tracked and visible, just not claimed as a decision input.
        assert view.open_injuries


# ---------------------------------------------------------------------------
# Persistence + service routing
# ---------------------------------------------------------------------------


class TestCheckinContract:
    def test_surface_answers_persist_on_an_existing_flag(self):
        plan = reconcile_injury_checkin(
            declared=[
                DeclaredInjury(
                    flag_id="flag-1",
                    status="worse",
                    skin_integrity="open",
                    bleeding_status="controlled",
                    drainage="none",
                    infection_signs=["pus"],
                    coverable="yes",
                    friction_or_contact_problem="no",
                )
            ],
            open_flag_ids=["flag-1"],
        )

        assert plan.updates[0].fields["skin_integrity"] == "open"
        assert plan.updates[0].fields["bleeding_status"] == "controlled"
        assert plan.updates[0].fields["infection_signs"] == ["pus"]
        assert plan.updates[0].fields["coverable"] == "yes"
        assert plan.updates[0].fields["friction_or_contact_problem"] == "no"

    def test_an_ordinary_update_never_blanks_a_stored_answer(self):
        plan = reconcile_injury_checkin(
            declared=[DeclaredInjury(flag_id="flag-1", status="ongoing")],
            open_flag_ids=["flag-1"],
        )

        assert not set(plan.updates[0].fields) & {
            "skin_integrity",
            "bleeding_status",
            "drainage",
            "infection_signs",
            "coverable",
            "friction_or_contact_problem",
        }

    def test_a_new_injury_can_carry_surface_answers(self):
        plan = reconcile_injury_checkin(
            declared=[
                DeclaredInjury(body_area="left foot", description="blister", skin_integrity="intact")
            ],
            open_flag_ids=[],
        )

        assert plan.creates[0]["skin_integrity"] == "intact"


class TestInfectionSignsValidation:
    """One bound, enforced at every layer that can carry the value.

    The injury_flags column allows at most 8. A contract that accepted more
    would turn a validation error into a write failure at persist time, and a
    malformed value read as "omitted" would let an infected wound classify as
    stable skin.
    """

    def test_the_request_model_rejects_more_than_eight_signs(self):
        with pytest.raises(ValidationError):
            TodayInjuryDeclaration(
                flag_id="flag-1",
                status="worse",
                infection_signs=[f"sign_{index}" for index in range(9)],
            )

    def test_the_reconciliation_contract_rejects_more_than_eight_signs(self):
        with pytest.raises(ValidationError):
            DeclaredInjury(
                flag_id="flag-1",
                status="worse",
                infection_signs=[f"sign_{index}" for index in range(9)],
            )

    def test_the_response_record_rejects_more_than_eight_signs(self):
        with pytest.raises(ValidationError):
            InjuryFlagRecord(
                id="flag-1",
                athlete_id="athlete-1",
                description="cut",
                infection_signs=[f"sign_{index}" for index in range(9)],
            )

    @pytest.mark.parametrize("malformed", [{"pus": True}, 7, 1.5, True])
    def test_malformed_infection_signs_are_rejected_not_ignored(self, malformed):
        # Reading these as "omitted" fails OPEN: the classifier would see no
        # infection signs on a wound the client tried to report as infected.
        with pytest.raises(ValidationError):
            TodayInjuryDeclaration(flag_id="flag-1", status="worse", infection_signs=malformed)

    def test_a_single_string_is_still_accepted_as_one_sign(self):
        declaration = TodayInjuryDeclaration(
            flag_id="flag-1", status="worse", infection_signs="pus"
        )

        assert declaration.infection_signs == ["pus"]

    def test_omitted_stays_omitted(self):
        assert TodayInjuryDeclaration(flag_id="flag-1", status="worse").infection_signs is None

    def test_an_explicit_null_is_absent_not_malformed(self):
        # Every surface answer is optional by design. Rejecting null would 422 a
        # client that sends the field for a question it did not ask — including
        # the plain {flag_id, status} update the contract promises stays valid.
        declaration = TodayInjuryDeclaration(
            flag_id="flag-1", status="worse", infection_signs=None
        )

        assert declaration.infection_signs is None

    def test_a_plain_status_update_is_still_accepted(self):
        assert (
            TodayInjuryDeclaration.model_validate(
                {"flag_id": "flag-1", "status": "worse", "infection_signs": None}
            ).infection_signs
            is None
        )


class TestLegacyInjuryResponseMapping:
    """/api/injury-flags must not report a blank wound state.

    The structured answers and the canonical class were dropped by the legacy
    and admin mapper, so the same row Today reports as needing review read as
    having no surface answers at all.
    """

    @staticmethod
    def _row(**overrides):
        return {
            "id": "flag-1",
            "athlete_id": "athlete-1",
            "description": "cut on left eyebrow",
            "body_area": "left eyebrow",
            "severity": "moderate",
            "status": "open",
            "latest_reported_status": "worse",
            **overrides,
        }

    def test_stored_surface_answers_reach_the_legacy_response(self):
        record = _map_injury_flag(
            self._row(
                skin_integrity="open",
                bleeding_status="controlled",
                drainage="none",
                infection_signs=["pus"],
                coverable="yes",
                friction_or_contact_problem="no",
            )
        )

        assert record.skin_integrity == "open"
        assert record.bleeding_status == "controlled"
        assert record.drainage == "none"
        assert record.infection_signs == ["pus"]
        assert record.coverable == "yes"
        assert record.friction_or_contact_problem == "no"
        assert record.latest_reported_status == "worse"

    def test_the_canonical_class_is_computed_for_the_legacy_response(self):
        record = _map_injury_flag(self._row(infection_signs=["pus"]))

        assert record.surface_class == "surface_medical_review"

    def test_a_row_with_no_surface_answers_maps_to_none_not_a_guess(self):
        record = _map_injury_flag(self._row())

        assert record.skin_integrity is None
        assert record.bleeding_status is None
        assert record.infection_signs == []

    def test_an_unrecognised_stored_value_is_dropped_rather_than_raised_on(self):
        # A legacy or hand-edited row must not be able to break the injury list.
        record = _map_injury_flag(self._row(skin_integrity="weird", bleeding_status=""))

        assert record.skin_integrity is None
        assert record.bleeding_status is None

    def test_an_oversized_stored_list_is_truncated_rather_than_failing_the_read(self):
        record = _map_injury_flag(
            self._row(infection_signs=[f"sign_{index}" for index in range(12)])
        )

        assert len(record.infection_signs) == 8


class TestServiceRouting:
    def test_a_worse_skin_injury_is_not_escalated_to_the_generic_stop(self):
        flags = _with_surface_class(
            [_blister(latest_reported_status="worse", skin_integrity="intact", coverable="yes")]
        )

        assert flags[0]["surface_class"] == "surface_local_restriction"
        assert _load_relevant_worse_injury(flags) is False

    def test_a_worse_non_surface_injury_still_escalates(self):
        flags = _with_surface_class([_shoulder_strain(latest_reported_status="worse")])

        assert flags[0]["surface_class"] == "non_surface"
        assert _load_relevant_worse_injury(flags) is True

    def test_a_worse_infected_wound_still_escalates(self):
        flags = _with_surface_class(
            [_blister(latest_reported_status="worse", infection_signs=["pus"])]
        )

        assert flags[0]["surface_class"] == "surface_medical_review"
        assert _load_relevant_worse_injury(flags) is True


class TestGuidedIntakeBootstrap:
    """A wound triaged at intake must arrive in Today with its wound state.

    The bootstrap used to write only area/description/severity/status, so the
    canonical classifier saw a skin injury with every safety question
    unanswered and routed it as ``stable_surface``. An open, infected or
    uncontrolled-bleeding intake cut silently became "no session change".
    """

    @staticmethod
    def _candidate(**guided):
        base = {
            "area": "left eyebrow",
            "injury_type": "surface_injury",
            "surface_type": "cut",
            "severity": "moderate",
        }
        return _guided_intake_injury_candidate({**base, **guided}, plan_id=PLAN_ID)

    def test_guided_open_cut_is_not_bootstrapped_as_stable(self):
        candidate = self._candidate(open_wound="yes")

        assert candidate["skin_integrity"] == "open"
        surface_class = _with_surface_class([{**candidate, "status": "open"}])[0]["surface_class"]
        assert surface_class != "stable_surface"
        assert surface_class == "surface_no_contact"

    def test_guided_uncontrolled_bleeding_is_not_bootstrapped_as_stable(self):
        # Guided intake says "wont_stop"; the classifier reads "uncontrolled".
        # Without the translation the answer is dropped on the floor.
        candidate = self._candidate(bleeding_status="wont_stop")

        assert candidate["bleeding_status"] == "uncontrolled"
        surface_class = _with_surface_class([{**candidate, "status": "open"}])[0]["surface_class"]
        assert surface_class != "stable_surface"
        assert surface_class == "surface_medical_review"

    def test_guided_infection_signs_are_not_bootstrapped_as_stable(self):
        candidate = self._candidate(infection_signs=["pus", "spreading"])

        assert candidate["infection_signs"] == ["pus", "spreading"]
        surface_class = _with_surface_class([{**candidate, "status": "open"}])[0]["surface_class"]
        assert surface_class != "stable_surface"
        assert surface_class == "surface_medical_review"

    def test_an_open_intake_cut_removes_contact_end_to_end(self):
        candidate = self._candidate(open_wound="yes")
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[{**candidate, "id": "flag-intake", "status": "open"}],
            ),
        )

        assert "remove_contact" in surface_restriction_codes(adjustment.triggers)
        assert "Skip all contact work today" in adjustment.action

    def test_an_infected_intake_cut_routes_to_medical_review_end_to_end(self):
        candidate = self._candidate(infection_signs=["pus"])
        adjustment = build_readiness_adjustment(
            ReadinessCheckin(),
            ReadinessContext(
                today_session=HARD_SPARRING,
                open_injuries=[{**candidate, "id": "flag-intake", "status": "open"}],
            ),
        )

        assert adjustment.decision == "pull_back"
        assert adjustment.title == "Get this checked."

    def test_the_none_answers_are_not_written_as_infection_signs(self):
        # "None" is the athlete saying there is nothing to report, not a sign.
        candidate = self._candidate(infection_signs=["none"], open_wound="no")

        assert "infection_signs" not in candidate
        assert candidate["skin_integrity"] == "intact"
        assert (
            _with_surface_class([{**candidate, "status": "open"}])[0]["surface_class"]
            == "stable_surface"
        )

    def test_unanswered_questions_are_left_absent_rather_than_guessed(self):
        candidate = self._candidate()

        assert not {
            "skin_integrity",
            "bleeding_status",
            "infection_signs",
            "coverable",
            "drainage",
        } & set(candidate)

    def test_infection_signs_are_capped_to_the_column_limit(self):
        # The bootstrap swallows write errors, so an oversized list would drop
        # the entire wound instead of the surplus signs.
        candidate = self._candidate(infection_signs=[f"sign_{index}" for index in range(12)])

        assert len(candidate["infection_signs"]) == 8


class TestSurfaceStateLifecycle:
    """A wound has to be able to get better, not just worse.

    The stored skin answers are what a contact restriction rests on, so a later
    check-in must be able to update them — otherwise an open blister that closed
    over would keep blocking contact forever.
    """

    def _open_blister_flag(self, client) -> str:
        opened = client.post(
            "/api/today/injury-checkin",
            headers=ATHLETE,
            json={
                "injuries": [
                    {
                        "body_area": "left foot",
                        "description": "blister on left foot",
                        "status": "worse",
                        "skin_integrity": "open",
                        "bleeding_status": "controlled",
                        "drainage": "none",
                        "infection_signs": [],
                        "coverable": "yes",
                        "friction_or_contact_problem": "yes",
                    }
                ]
            },
        )
        assert opened.status_code == 201
        flag = opened.json()["open_injuries"][0]
        assert flag["surface_class"] == "surface_no_contact"
        return str(flag["id"])

    def test_an_open_blister_that_closes_over_stops_blocking_contact(self):
        client, store, _ = _build_client()
        store.plans[PLAN_ID] = {
            "id": PLAN_ID,
            "athlete_id": "athlete-1",
            "status": "ready",
            "plan_name": "Camp A",
            "created_at": "2026-06-01T00:00:00+00:00",
        }
        flag_id = self._open_blister_flag(client)

        eased = client.post(
            "/api/today/injury-checkin",
            headers=ATHLETE,
            json={
                "injuries": [
                    {
                        "flag_id": flag_id,
                        "status": "improving",
                        "skin_integrity": "intact",
                        "bleeding_status": "none",
                        "drainage": "none",
                        "infection_signs": [],
                        "coverable": "yes",
                    }
                ]
            },
        )

        assert eased.status_code == 201
        flag = eased.json()["open_injuries"][0]
        assert flag["skin_integrity"] == "intact"
        assert flag["bleeding_status"] == "none"
        # No longer an open wound, so contact is no longer blocked. The stored
        # friction answer was not re-asked, so it survives and keeps the wound at
        # a local restriction rather than fully stable.
        assert flag["surface_class"] == "surface_local_restriction"
        assert classify_injury_surface(flag) != "surface_no_contact"

    def test_an_infected_wound_that_clears_leaves_the_review_pathway(self):
        client, store, _ = _build_client()
        store.plans[PLAN_ID] = {
            "id": PLAN_ID,
            "athlete_id": "athlete-1",
            "status": "ready",
            "plan_name": "Camp A",
            "created_at": "2026-06-01T00:00:00+00:00",
        }
        opened = client.post(
            "/api/today/injury-checkin",
            headers=ATHLETE,
            json={
                "injuries": [
                    {
                        "body_area": "left foot",
                        "description": "blister on left foot",
                        "status": "worse",
                        "skin_integrity": "open",
                        "infection_signs": ["pus"],
                        "coverable": "yes",
                        "friction_or_contact_problem": "no",
                    }
                ]
            },
        ).json()["open_injuries"][0]
        assert opened["surface_class"] == "surface_medical_review"

        cleared = client.post(
            "/api/today/injury-checkin",
            headers=ATHLETE,
            json={
                "injuries": [
                    {
                        "flag_id": opened["id"],
                        "status": "improving",
                        "skin_integrity": "intact",
                        "bleeding_status": "none",
                        "drainage": "none",
                        "infection_signs": [],
                        "coverable": "yes",
                    }
                ]
            },
        ).json()["open_injuries"][0]

        assert cleared["infection_signs"] == []
        assert cleared["surface_class"] == "stable_surface"

    def test_a_report_without_surface_answers_keeps_the_stored_state(self):
        # An update that does not carry the answers must not silently clear them:
        # only an athlete-confirmed recheck changes what is on record.
        client, store, _ = _build_client()
        store.plans[PLAN_ID] = {
            "id": PLAN_ID,
            "athlete_id": "athlete-1",
            "status": "ready",
            "plan_name": "Camp A",
            "created_at": "2026-06-01T00:00:00+00:00",
        }
        flag_id = self._open_blister_flag(client)

        same = client.post(
            "/api/today/injury-checkin",
            headers=ATHLETE,
            json={"injuries": [{"flag_id": flag_id, "status": "ongoing"}]},
        ).json()["open_injuries"][0]

        assert same["skin_integrity"] == "open"
        assert same["surface_class"] == "surface_no_contact"
