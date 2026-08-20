"""Completed rehab work becomes attributable evidence — or is explicitly refused.

The invariant this suite defends: a ``RehabExposureEvent`` asserts "this
specific tissue did this specific work". Every part of that must be known from
the record. When any part is not, the resolver must say so with a code and
write nothing — never guess, and never emit a positive observation with the
unknown parts quietly defaulted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from api.contracts import rehab_completion as module
from api.contracts.rehab_completion import (
    DURING_ANSWERS,
    LIMIT_ANSWERS,
    REASON_ATTRIBUTION_UNKNOWN,
    build_exposure_id,
    build_rehab_exposure_event,
    REASON_EPISODE_UNKNOWN,
    REASON_LATERALITY_UNKNOWN,
    REASON_MULTIPLE_POSSIBLE_INJURIES,
    REASON_NOT_COMPLETED,
    REASON_NOT_REHAB_WORK,
    build_rehab_response_prompts,
    completed_dose_from_session,
    completed_dose_stopped_early,
    exposure_response_from_answers,
    resolve_rehab_completion,
    resolve_rehab_exposure_candidate,
)
from api.contracts.rehab_exposure import ExposureResponse
from fightcamp.config import DATA_DIR
from fightcamp.rehab_protocols import rehab_drill_options_for_phase

DONE = {"status": "done"}
ATHLETE = "8f14e45f-ceea-4a1a-9d2b-1c3a5e7b9d01"
PLAN_ID = "77777777-7777-7777-7777-777777777777"
DAY = "2026-08-20"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _bank_drill(location: str = "ankle", injury_type: str = "sprain") -> dict:
    """A real drill straight out of the shipped rehab bank."""
    bank = json.loads((DATA_DIR / "rehab_bank.json").read_text(encoding="utf-8"))
    return next(
        drill
        for entry in bank
        if entry["location"] == location and entry["type"] == injury_type
        for drill in entry["drills"]
    )


def _reviewed_drill(**overrides) -> dict:
    """The same drill as if its demand had been clinically reviewed.

    Used to exercise the eligible path. It does NOT reflect the shipped bank —
    see ``test_no_shipped_drill_can_currently_be_logged``.
    """
    drill = {
        **_bank_drill(),
        "load": "low",
        "impact": "none",
        "velocity": "low",
        "laterality_applicability": "side_specific",
    }
    drill.update(overrides)
    return drill


def _injury(**overrides) -> dict:
    injury = {
        "id": "11111111-1111-1111-1111-111111111111",
        "episode_id": "22222222-2222-2222-2222-222222222222",
        "status": "open",
        "body_region": "ankle",
        "side": "left",
        "label": "Left ankle",
    }
    injury.update(overrides)
    return injury


# ---------------------------------------------------------------------------
# Rehab work is identified by canonical id, never by display name
# ---------------------------------------------------------------------------


def test_rehab_options_carry_the_canonical_bank_drill_id():
    options = rehab_drill_options_for_phase("sprain", "ankle", "GPP", limit=4)
    assert options
    for option in options:
        assert option["drill"]["id"]
        assert option["drill"]["target_regions"]


def test_the_rendered_line_wrapper_is_unchanged_by_the_identity_resolver():
    """``_rehab_drills_for_phase`` delegates, so the two can never diverge."""
    from fightcamp.rehab_protocols import _rehab_drills_for_phase

    for phase in ("GPP", "SPP", "TAPER"):
        options = rehab_drill_options_for_phase("sprain", "ankle", phase, limit=6)
        assert [option["line"] for option in options] == _rehab_drills_for_phase(
            "sprain", "ankle", phase, limit=6
        )


def test_an_item_without_a_canonical_id_is_not_rehab_work():
    """A display name alone must never become an exposure."""
    candidate = resolve_rehab_exposure_candidate(
        {"name": "Single-Leg Balance on Foam Pad"}, [_injury()], completion=DONE
    )
    assert candidate.eligible is False
    assert candidate.reasons == (REASON_NOT_REHAB_WORK,)


def test_a_drill_without_target_regions_is_not_rehab_work():
    candidate = resolve_rehab_exposure_candidate(
        {"id": "some_drill", "target_regions": []}, [_injury()], completion=DONE
    )
    assert candidate.reasons == (REASON_NOT_REHAB_WORK,)


# ---------------------------------------------------------------------------
# The shipped bank cannot yet produce evidence, and says so
# ---------------------------------------------------------------------------


def test_a_shipped_bank_drill_can_be_logged_with_unknown_demand():
    """An unreviewed demand must not cost us the observation."""
    candidate = resolve_rehab_exposure_candidate(_bank_drill(), [_injury()], completion=DONE)
    assert candidate.eligible is True
    assert candidate.demand.load == "unknown"
    assert candidate.demand.impact == "unknown"
    assert candidate.demand.velocity == "unknown"


def test_unknown_demand_is_flagged_as_non_qualifying_evidence():
    """Recordable, but never positive evidence of capacity."""
    candidate = resolve_rehab_exposure_candidate(_bank_drill(), [_injury()], completion=DONE)
    event = build_rehab_exposure_event(
        candidate,
        athlete_id=ATHLETE,
        plan_id=PLAN_ID,
        session_id="s1",
        training_day=DAY,
        completion=DONE,
    )
    assert event.has_unknown_demand is True
    assert event.demand.has_unknown_level is True


def test_a_fully_reviewed_demand_is_not_flagged():
    candidate = resolve_rehab_exposure_candidate(_reviewed_drill(), [_injury()], completion=DONE)
    event = build_rehab_exposure_event(
        candidate,
        athlete_id=ATHLETE,
        plan_id=PLAN_ID,
        session_id="s1",
        training_day=DAY,
        completion=DONE,
    )
    assert event.has_unknown_demand is False


@pytest.mark.parametrize("missing", ["load", "impact", "velocity"])
def test_each_unreviewed_level_becomes_unknown_not_a_default(missing):
    """"Not stated" must never be laundered into a low-demand claim."""
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(**{missing: None}), [_injury()], completion=DONE
    )
    assert candidate.eligible is True
    assert getattr(candidate.demand, missing) == "unknown"
    assert candidate.demand.has_unknown_level is True


def test_an_unrecognised_demand_level_is_read_as_unknown():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(load="enormous"), [_injury()], completion=DONE
    )
    assert candidate.demand.load == "unknown"


def test_unknown_is_a_valid_level_in_the_bank_schema():
    from fightcamp.rehab_schema import IMPACT_VALUES, LOAD_VALUES, VELOCITY_VALUES

    assert "unknown" in LOAD_VALUES
    assert "unknown" in IMPACT_VALUES
    assert "unknown" in VELOCITY_VALUES


def test_demand_unknown_is_no_longer_an_ineligibility_reason():
    assert not hasattr(module, "REASON_DEMAND_UNKNOWN")


# ---------------------------------------------------------------------------
# Attribution never guesses
# ---------------------------------------------------------------------------


def test_a_reviewed_drill_on_a_matching_injury_is_eligible():
    candidate = resolve_rehab_exposure_candidate(_reviewed_drill(), [_injury()], completion=DONE)
    assert candidate.eligible is True
    assert candidate.reasons == ()
    assert candidate.injury_id == "11111111-1111-1111-1111-111111111111"
    assert candidate.injury_episode_id == "22222222-2222-2222-2222-222222222222"
    assert candidate.body_region == "ankle"
    assert candidate.side == "left"
    assert candidate.demand is not None


def test_no_matching_region_is_attribution_unknown():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(), [_injury(body_region="shoulder")], completion=DONE
    )
    assert candidate.reasons == (REASON_ATTRIBUTION_UNKNOWN,)
    assert candidate.injury_id is None


def test_two_injuries_in_the_same_region_are_ambiguous():
    """Nothing says which the work was for, so neither may claim it."""
    injuries = [_injury(), _injury(id="33333333-3333-3333-3333-333333333333", episode_id="44444444-4444-4444-4444-444444444444", side="right")]
    candidate = resolve_rehab_exposure_candidate(_reviewed_drill(), injuries, completion=DONE)
    assert candidate.reasons == (REASON_MULTIPLE_POSSIBLE_INJURIES,)
    assert candidate.injury_id is None
    assert set(candidate.candidate_injury_ids) == {"11111111-1111-1111-1111-111111111111", "33333333-3333-3333-3333-333333333333"}


def test_an_unknown_injury_side_is_laterality_unknown():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(), [_injury(side="unknown")], completion=DONE
    )
    assert REASON_LATERALITY_UNKNOWN in candidate.reasons
    assert candidate.side is None


def test_a_bilateral_only_drill_cannot_evidence_one_side():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(laterality_applicability="bilateral_only"), [_injury()], completion=DONE
    )
    assert REASON_LATERALITY_UNKNOWN in candidate.reasons


def test_a_bilateral_injury_accepts_a_bilateral_only_drill():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(laterality_applicability="bilateral_only"),
        [_injury(side="bilateral")],
        completion=DONE,
    )
    assert candidate.eligible is True
    assert candidate.side == "bilateral"


def test_a_missing_episode_id_blocks_logging():
    """Without an episode the evidence could not be isolated from a stale one."""
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(), [_injury(episode_id="")], completion=DONE
    )
    assert REASON_EPISODE_UNKNOWN in candidate.reasons


def test_a_resolved_injury_is_not_a_target():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(), [_injury(status="resolved")], completion=DONE
    )
    assert candidate.reasons == (REASON_ATTRIBUTION_UNKNOWN,)


def test_a_surface_injury_never_receives_a_loading_exposure():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(), [_injury(injury_type="blister")], completion=DONE
    )
    assert candidate.reasons == (REASON_ATTRIBUTION_UNKNOWN,)


def test_every_missing_part_is_reported_at_once():
    """One pass shows the whole gap, not one blocker at a time."""
    candidate = resolve_rehab_exposure_candidate(
        _bank_drill(), [_injury(side="unknown", episode_id="")], completion=DONE
    )
    assert set(candidate.reasons) == {REASON_EPISODE_UNKNOWN, REASON_LATERALITY_UNKNOWN}


# ---------------------------------------------------------------------------
# Only completed work counts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["not_started", "skipped", "started", ""])
def test_work_that_was_not_done_is_not_an_exposure(status):
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(), [_injury()], completion={"status": status}
    )
    assert candidate.reasons == (REASON_NOT_COMPLETED,)


def test_a_missing_completion_is_not_an_exposure():
    assert resolve_rehab_exposure_candidate(_reviewed_drill(), [_injury()]).reasons == (
        REASON_NOT_COMPLETED,
    )


# ---------------------------------------------------------------------------
# Dose honesty
# ---------------------------------------------------------------------------


def test_marking_done_records_performed_with_amount_unknown():
    """A session completion proves exposure, not every prescribed rep."""
    dose = completed_dose_from_session(DONE)
    assert dose.completion_state == "performed_amount_unknown"
    assert dose.completed_fraction is None
    assert dose.sets is None
    assert dose.reps is None
    assert dose.duration_seconds is None


def test_a_modified_session_does_not_claim_a_completed_fraction():
    dose = completed_dose_from_session({"status": "modified"})
    assert dose.completion_state == "partial_amount_unknown"
    assert dose.completed_fraction is None
    assert dose.stopped_early is None


def test_the_prescription_is_carried_only_where_the_session_states_it():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(),
        [_injury()],
        completion=DONE,
        prescribed={"sets": 3, "reps": 10},
    )
    assert candidate.prescribed_dose is not None
    assert candidate.prescribed_dose.sets == 3
    assert candidate.prescribed_dose.reps == 10
    assert candidate.prescribed_dose.duration_seconds is None


def test_no_prescription_means_no_prescribed_dose():
    candidate = resolve_rehab_exposure_candidate(_reviewed_drill(), [_injury()], completion=DONE)
    assert candidate.prescribed_dose is None


def test_the_prescribed_dose_is_never_reused_as_the_completed_dose():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(), [_injury()], completion=DONE, prescribed={"sets": 3, "reps": 10}
    )
    completed = completed_dose_from_session(DONE)
    assert candidate.prescribed_dose.sets == 3
    assert completed.sets is None


# ---------------------------------------------------------------------------
# The injury-specific question
# ---------------------------------------------------------------------------


def test_the_block_is_raised_only_for_attributable_rehab_work():
    """Unreviewed demand still asks; an unattributable drill does not."""
    injuries = [_injury()]
    attributable = resolve_rehab_completion([_bank_drill()], injuries, completion=DONE)
    unattributable = resolve_rehab_completion(
        [_reviewed_drill()], [_injury(body_region="shoulder")], completion=DONE
    )

    assert attributable.has_attributable_rehab is True
    assert unattributable.has_attributable_rehab is False


def test_a_normal_training_session_raises_no_injury_question():
    resolution = resolve_rehab_completion([], [_injury()], completion=DONE)
    assert resolution.has_attributable_rehab is False
    assert build_rehab_response_prompts(resolution, [_injury()]) == ()


def test_the_prompt_names_the_injury():
    injuries = [_injury()]
    resolution = resolve_rehab_completion([_reviewed_drill()], injuries, completion=DONE)
    prompt = build_rehab_response_prompts(resolution, injuries)[0]

    assert prompt.injury_label == "LEFT ANKLE"
    assert prompt.injury_id == "11111111-1111-1111-1111-111111111111"
    assert prompt.during_question == "How did it feel during the rehab work?"
    assert prompt.limit_question == "Did you have to reduce or stop because of it?"


def test_one_prompt_per_injury_however_many_drills_targeted_it():
    injuries = [_injury()]
    drills = [_reviewed_drill(), _reviewed_drill(id="ankle_sprain_banded_ankle_circles")]
    resolution = resolve_rehab_completion(drills, injuries, completion=DONE)
    prompts = build_rehab_response_prompts(resolution, injuries)

    assert len(prompts) == 1
    assert len(prompts[0].drill_ids) == 2


def test_the_question_asks_for_no_diagnosis_or_mechanism():
    injuries = [_injury()]
    resolution = resolve_rehab_completion([_reviewed_drill()], injuries, completion=DONE)
    prompt = build_rehab_response_prompts(resolution, injuries)[0]
    words = set(re.findall(r"[a-z]+", f"{prompt.during_question} {prompt.limit_question}".lower()))

    # Whole words, so the plain-English "because" is not read as "cause".
    assert not words & {"why", "cause", "caused", "mechanism", "describe", "structure"}
    assert not any(word.startswith("diagnos") for word in words)


# ---------------------------------------------------------------------------
# Answers map onto the contract without inventing precision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("during", DURING_ANSWERS)
def test_the_during_answer_is_stored_verbatim(during):
    response = ExposureResponse(**exposure_response_from_answers(during, "no"))
    assert response.during_response == during


def test_an_unasked_question_is_not_stored_as_an_answer():
    """"We did not ask" must never read as "the athlete said nothing was wrong"."""
    response = ExposureResponse(**exposure_response_from_answers(None, None))
    assert response.during_response == "not_reported"
    assert response.worsening_reported is None
    assert response.stopped_due_to_symptoms is None


def test_a_categorical_answer_never_becomes_a_pain_score():
    for during in DURING_ANSWERS:
        response = ExposureResponse(**exposure_response_from_answers(during, "no"))
        assert response.pain_during is None
        assert response.pain_immediate_after is None


@pytest.mark.parametrize("during", DURING_ANSWERS)
def test_an_exposure_level_answer_never_becomes_an_injury_status_signal(during):
    """``worse`` here is about this drill, not about the injury going backwards.

    ``worsening_reported`` is liable to be read later as a broader injury
    setback, so a single uncomfortable drill must never set it.
    """
    response = ExposureResponse(**exposure_response_from_answers(during, "no"))
    assert response.worsening_reported is None
    assert response.during_response == during


@pytest.mark.parametrize(
    "limit,stopped,early",
    [("no", False, False), ("reduced", False, True), ("stopped", True, True)],
)
def test_reduced_is_distinguished_from_stopped(limit, stopped, early):
    """Cutting work short is a real observation, and is not "stopped"."""
    response = ExposureResponse(**exposure_response_from_answers("same", limit))
    assert response.stopped_due_to_symptoms is stopped
    assert completed_dose_stopped_early(limit) is early


def test_an_unanswered_limit_question_leaves_both_fields_unset():
    response = ExposureResponse(**exposure_response_from_answers("same", None))
    assert response.stopped_due_to_symptoms is None
    assert completed_dose_stopped_early(None) is None


def test_answer_vocabularies_are_the_specified_ones():
    assert DURING_ANSWERS == ("better", "same", "worse", "not_sure")
    assert LIMIT_ANSWERS == ("no", "reduced", "stopped")


def test_the_mapping_only_produces_valid_contract_fields():
    """Every combination must construct a valid ExposureResponse."""
    for during in (*DURING_ANSWERS, None, "junk"):
        for limit in (*LIMIT_ANSWERS, None, "junk"):
            ExposureResponse(**exposure_response_from_answers(during, limit))


# ---------------------------------------------------------------------------
# Nothing here interprets or progresses
# ---------------------------------------------------------------------------


def test_the_public_surface_carries_no_tolerance_judgement():
    """Observations only: nothing here names, returns or stores "tolerated"."""
    from api.contracts.rehab_exposure import ExposureResponse as _Response

    surface = set(module.__all__) | set(module.RehabExposureCandidate.__dataclass_fields__)
    surface |= set(module.RehabCompletionResolution.__dataclass_fields__)
    surface |= set(_Response.model_fields)
    assert not any("toler" in name.lower() for name in surface)


def test_this_module_does_not_touch_the_rehab_stage_resolver():
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "resolve_rehab_stage" not in source
    assert "rehab_stage" not in {name.lower() for name in module.__all__}


def test_the_stage_ladder_is_still_capped_at_restore():
    """PR 3.5 adds evidence capture. It does not unlock progression."""
    from api.contracts.rehab_stage import MAX_RESOLVABLE_STAGE, STAGE_RESTORE

    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE


# ---------------------------------------------------------------------------
# The event, and why re-submitting cannot duplicate evidence
# ---------------------------------------------------------------------------


def _event(**kwargs):
    candidate = resolve_rehab_exposure_candidate(_bank_drill(), [_injury()], completion=DONE)
    payload = {
        "athlete_id": ATHLETE,
        "plan_id": PLAN_ID,
        "session_id": "session-1",
        "training_day": DAY,
        "completion": DONE,
    }
    payload.update(kwargs)
    return build_rehab_exposure_event(candidate, **payload)


def test_the_same_completion_always_builds_the_same_exposure_id():
    assert _event().exposure_id == _event().exposure_id


def test_the_whole_event_is_deterministic_so_a_retry_cannot_conflict():
    """PR3's RPC is idempotent only for an identical payload under a known id."""
    assert _event().model_dump(mode="json") == _event().model_dump(mode="json")


def test_a_different_drill_gets_a_different_exposure_id():
    base = build_exposure_id(
        athlete_id=ATHLETE,
        plan_id=PLAN_ID,
        injury_episode_id="22222222-2222-2222-2222-222222222222",
        drill_id="drill_a",
        session_id="session-1",
        training_day=DAY,
        rehab_occurrence_key="block:rehab-1",
    )
    other = build_exposure_id(
        athlete_id=ATHLETE,
        plan_id=PLAN_ID,
        injury_episode_id="22222222-2222-2222-2222-222222222222",
        drill_id="drill_b",
        session_id="session-1",
        training_day=DAY,
        rehab_occurrence_key="block:rehab-1",
    )
    assert base != other


@pytest.mark.parametrize(
    "field,value",
    [
        ("athlete_id", "99999999-9999-9999-9999-999999999999"),
        ("plan_id", "88888888-8888-8888-8888-888888888888"),
        ("injury_episode_id", "55555555-5555-5555-5555-555555555555"),
        ("session_id", "session-2"),
        ("training_day", "2026-08-21"),
        ("rehab_occurrence_key", "block:rehab-2"),
    ],
)
def test_every_identity_part_changes_the_exposure_id(field, value):
    args = {
        "athlete_id": ATHLETE,
        "plan_id": PLAN_ID,
        "injury_episode_id": "22222222-2222-2222-2222-222222222222",
        "drill_id": "drill_a",
        "session_id": "session-1",
        "training_day": DAY,
        "rehab_occurrence_key": "block:rehab-1",
    }
    assert build_exposure_id(**args) != build_exposure_id(**{**args, field: value})


def test_a_new_episode_does_not_reuse_the_previous_episodes_exposure_id():
    """Episode rotation must not collide with stale evidence."""
    args = {
        "athlete_id": ATHLETE,
        "plan_id": PLAN_ID,
        "drill_id": "drill_a",
        "session_id": "session-1",
        "training_day": DAY,
        "rehab_occurrence_key": "block:rehab-1",
    }
    first = build_exposure_id(injury_episode_id="22222222-2222-2222-2222-222222222222", **args)
    rotated = build_exposure_id(injury_episode_id="66666666-6666-6666-6666-666666666666", **args)
    assert first != rotated


def test_the_event_carries_the_injury_identity_the_database_checks():
    event = _event()
    assert str(event.injury_id) == "11111111-1111-1111-1111-111111111111"
    assert str(event.injury_episode_id) == "22222222-2222-2222-2222-222222222222"
    assert event.body_region == "ankle"
    assert event.side == "left"
    assert event.is_attributable_to(_injury()) is True


def test_the_event_records_the_athletes_answers():
    event = _event(during="worse", limit="reduced")
    assert event.response.during_response == "worse"
    assert event.response.worsening_reported is None
    assert event.response.stopped_due_to_symptoms is False
    assert event.dose_completed.stopped_early is True


def test_reduced_and_stopped_remain_distinct_without_inventing_a_fraction():
    full = _event(during="same", limit="no")
    reduced = _event(during="same", limit="reduced")
    stopped = _event(during="same", limit="stopped")

    assert full.dose_completed.completion_state == "performed_amount_unknown"
    assert full.dose_completed.completed_fraction is None
    assert reduced.dose_completed.completion_state == "partial_amount_unknown"
    assert reduced.dose_completed.completed_fraction is None
    assert reduced.dose_completed.stopped_early is True
    assert reduced.response.stopped_due_to_symptoms is False
    assert stopped.dose_completed.completion_state == "partial_amount_unknown"
    assert stopped.dose_completed.completed_fraction is None
    assert stopped.dose_completed.stopped_early is True
    assert stopped.response.stopped_due_to_symptoms is True


def test_provenance_marks_the_athlete_as_the_source():
    assert _event().provenance.source == "athlete_logged_rehab"


def test_an_ineligible_candidate_is_refused_rather_than_filled_in():
    candidate = resolve_rehab_exposure_candidate(
        _bank_drill(), [_injury(side="unknown")], completion=DONE
    )
    with pytest.raises(ValueError, match="not eligible"):
        build_rehab_exposure_event(
            candidate,
            athlete_id=ATHLETE,
            plan_id=PLAN_ID,
            session_id="s1",
            training_day=DAY,
            completion=DONE,
        )
