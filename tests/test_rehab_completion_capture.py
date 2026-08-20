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
    REASON_DEMAND_UNKNOWN,
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
        "id": "injury-1",
        "episode_id": "episode-1",
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


def test_no_shipped_drill_can_currently_be_logged():
    """PR3 left load/impact/velocity unreviewed; ExposureDemand requires them."""
    candidate = resolve_rehab_exposure_candidate(_bank_drill(), [_injury()], completion=DONE)
    assert candidate.eligible is False
    assert REASON_DEMAND_UNKNOWN in candidate.reasons


def test_the_demand_gap_is_reported_not_defaulted():
    """The missing levels must not be silently filled with a safe-looking value."""
    candidate = resolve_rehab_exposure_candidate(_bank_drill(), [_injury()], completion=DONE)
    assert candidate.demand is None


@pytest.mark.parametrize("missing", ["load", "impact", "velocity"])
def test_each_required_demand_level_is_individually_required(missing):
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(**{missing: None}), [_injury()], completion=DONE
    )
    assert REASON_DEMAND_UNKNOWN in candidate.reasons


def test_an_unrecognised_demand_level_is_not_accepted():
    candidate = resolve_rehab_exposure_candidate(
        _reviewed_drill(load="enormous"), [_injury()], completion=DONE
    )
    assert REASON_DEMAND_UNKNOWN in candidate.reasons


# ---------------------------------------------------------------------------
# Attribution never guesses
# ---------------------------------------------------------------------------


def test_a_reviewed_drill_on_a_matching_injury_is_eligible():
    candidate = resolve_rehab_exposure_candidate(_reviewed_drill(), [_injury()], completion=DONE)
    assert candidate.eligible is True
    assert candidate.reasons == ()
    assert candidate.injury_id == "injury-1"
    assert candidate.injury_episode_id == "episode-1"
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
    injuries = [_injury(), _injury(id="injury-2", episode_id="episode-2", side="right")]
    candidate = resolve_rehab_exposure_candidate(_reviewed_drill(), injuries, completion=DONE)
    assert candidate.reasons == (REASON_MULTIPLE_POSSIBLE_INJURIES,)
    assert candidate.injury_id is None
    assert set(candidate.candidate_injury_ids) == {"injury-1", "injury-2"}


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
    assert set(candidate.reasons) == {
        REASON_EPISODE_UNKNOWN,
        REASON_LATERALITY_UNKNOWN,
        REASON_DEMAND_UNKNOWN,
    }


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


def test_marking_done_records_a_fraction_not_a_fabricated_dose():
    """A prescribed 3x10 is never echoed back as a completed 3x10."""
    dose = completed_dose_from_session(DONE)
    assert dose.completed_fraction == 1.0
    assert dose.sets is None
    assert dose.reps is None
    assert dose.duration_seconds is None


def test_a_modified_session_does_not_claim_a_completed_fraction():
    dose = completed_dose_from_session({"status": "modified"})
    assert dose.completed_fraction is None
    assert dose.stopped_early is True


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
    injuries = [_injury()]
    attributable = resolve_rehab_completion([_reviewed_drill()], injuries, completion=DONE)
    unattributable = resolve_rehab_completion([_bank_drill()], injuries, completion=DONE)

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
    assert prompt.injury_id == "injury-1"
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


def test_worse_is_recorded_as_worsening_and_better_is_not():
    assert ExposureResponse(**exposure_response_from_answers("worse", "no")).worsening_reported is True
    assert ExposureResponse(**exposure_response_from_answers("better", "no")).worsening_reported is False
    assert ExposureResponse(**exposure_response_from_answers("same", "no")).worsening_reported is False


def test_not_sure_is_not_recorded_as_no_worsening():
    response = ExposureResponse(**exposure_response_from_answers("not_sure", "no"))
    assert response.worsening_reported is None


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
