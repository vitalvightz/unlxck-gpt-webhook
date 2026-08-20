"""PR4 injury-episode LOAD eligibility, including the shadow-mode boundary."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from api.contracts.load_eligibility import (
    BLOCKED_ACTIVE_WORSENING,
    BLOCKED_MEDICAL_REVIEW,
    BLOCKED_RED_FLAG,
    ELIGIBLE_LOAD_CRITERIA_MET,
    FAIL_DURING_RESPONSE_WORSE,
    FAIL_NEXT_DAY_RESPONSE_WORSE,
    FAIL_STOPPED_DUE_TO_SYMPTOMS,
    IGNORED_ATHLETE_MISMATCH,
    IGNORED_DUPLICATE_EXPOSURE,
    IGNORED_EPISODE_MISMATCH,
    IGNORED_INJURY_MISMATCH,
    IGNORED_REGION_MISMATCH,
    IGNORED_SIDE_MISMATCH,
    INSUFFICIENT_HISTORY_TRUNCATED,
    INSUFFICIENT_UNRESOLVED_NEGATIVE_EVIDENCE,
    INSUFFICIENT_UNSUPPORTED_INJURY_TYPE,
    LOAD_CRITERIA_REGISTRY,
    LOAD_ELIGIBILITY_ENGINE_VERSION,
    NOT_APPLICABLE_CURRENT_STAGE,
    NOT_APPLICABLE_SURFACE_PATHWAY,
    LoadCriteria,
    criteria_for_injury_type,
    resolve_injury_type,
    resolve_load_eligibility,
)
from api.contracts.rehab_exposure import RehabExposureEvent
from api.contracts.rehab_stage import (
    MAX_RESOLVABLE_STAGE,
    REASON_RED_FLAG_GATE,
    REASON_URGENT_INJURY_TYPE,
    STAGE_DYNAMIC,
    STAGE_LOAD,
    STAGE_RESTORE,
    STAGE_RETURN,
    RehabStageDecision,
)
from api.services import today_service as today_service_module
from api.store import SupabaseAppStore
from fightcamp.rehab_schema import CARE_TYPE_MUSCULOSKELETAL, CARE_TYPE_WOUND_CARE
from tests.support import FakeStore

ATHLETE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_ATHLETE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
INJURY = "11111111-1111-1111-1111-111111111111"
OTHER_INJURY = "22222222-2222-2222-2222-222222222222"
EPISODE = "33333333-3333-3333-3333-333333333333"
OLD_EPISODE = "44444444-4444-4444-4444-444444444444"
GROUP = "55555555-5555-5555-5555-555555555555"
START = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)


def _synthetic_criteria(*, requires_quantified_dose: bool) -> LoadCriteria:
    """Exact test-only rule; production LOAD_CRITERIA_REGISTRY stays empty."""

    return LoadCriteria(
        injury_type="sprain",
        taxonomy_family="soft_tissue",
        provenance="test_only_synthetic_criterion",
        qualifying_loads=frozenset({"low"}),
        requires_quantified_dose=requires_quantified_dose,
        allowed_during_responses=frozenset({"same", "better"}),
        requires_delayed_response=False,
        allowed_delayed_responses=frozenset({"same", "better"}),
        historical_negative_resolution_rule=None,
    )


SYNTHETIC_QUANTIFIED_CRITERIA = _synthetic_criteria(requires_quantified_dose=True)
SYNTHETIC_UNQUANTIFIED_CRITERIA = _synthetic_criteria(requires_quantified_dose=False)


def _injury(**updates: object) -> dict:
    row = {
        "id": INJURY,
        "athlete_id": ATHLETE,
        "episode_id": EPISODE,
        "body_region": "ankle",
        "side": "left",
        "body_area": "left ankle",
        "description": "ankle sprain",
        "injury_type": "sprain",
        "status": "open",
        "latest_reported_status": "same",
        "created_at": "2026-08-10T10:00:00+00:00",
        "updated_at": "2026-08-20T09:00:00+00:00",
    }
    row.update(updates)
    return row


def _stage(
    stage: str | None = STAGE_RESTORE,
    *,
    medical_gate: bool = False,
    reasons: tuple[str, ...] = (),
    pathway: str = CARE_TYPE_MUSCULOSKELETAL,
) -> RehabStageDecision:
    return RehabStageDecision(
        stage=stage,
        care_pathway=pathway,
        medical_gate=medical_gate,
        reasons=reasons,
    )


def _event(
    number: int = 1,
    *,
    athlete_id: str = ATHLETE,
    injury_id: str = INJURY,
    episode_id: str = EPISODE,
    body_region: str = "ankle",
    side: str = "left",
    response_group_id: str | None = GROUP,
    load: str = "low",
    impact: str = "none",
    velocity: str = "low",
    completion_state: str | None = "quantified",
    during_response: str = "same",
    next_day_response: str = "same",
    stopped_due_to_symptoms: bool | None = False,
    worsening_reported: bool | None = False,
    include_response: bool = True,
) -> dict:
    if completion_state == "quantified":
        completed_dose: dict = {"reps": 10, "completion_state": "quantified"}
    else:
        completed_dose = {"completion_state": completion_state}
    payload: dict = {
        "exposure_id": str(UUID(int=100 + number)),
        "response_group_id": response_group_id,
        "injury_id": injury_id,
        "injury_episode_id": episode_id,
        "drill_id": f"test_drill_{number}",
        "body_region": body_region,
        "side": side,
        "demand": {
            "target_regions": [body_region],
            "load": load,
            "impact": impact,
            "velocity": velocity,
        },
        "dose_completed": completed_dose,
        "occurred_at": (START + timedelta(minutes=number)).isoformat(),
        "provenance": {
            "source": "athlete_logged_rehab",
            "recorded_at": (START + timedelta(minutes=number)).isoformat(),
        },
    }
    if include_response:
        payload["response"] = {
            "during_response": during_response,
            "next_day_response": next_day_response,
            "stopped_due_to_symptoms": stopped_due_to_symptoms,
            "worsening_reported": worsening_reported,
        }
    # Validate the fixture through the production contract before returning it.
    event = RehabExposureEvent.model_validate(payload)
    return {
        "id": str(event.exposure_id),
        "athlete_id": athlete_id,
        "event_json": event.model_dump(mode="json"),
    }


def _resolve(
    *rows: dict,
    injury: dict | None = None,
    stage: RehabStageDecision | None = None,
    athlete_id: str = ATHLETE,
    history_truncated: bool = False,
    criteria: LoadCriteria | None = None,
):
    return resolve_load_eligibility(
        athlete_id=athlete_id,
        injury=injury or _injury(),
        stage_decision=stage or _stage(),
        exposure_rows=list(rows),
        history_truncated=history_truncated,
        criteria_registry={criteria.injury_type: criteria} if criteria else None,
    )


def _criterion(result, name: str):
    return next(item for item in result.criteria_results if item.criterion == name)


# ---------------------------------------------------------------------------
# Exact evidence isolation and grouping (acceptance tests 1-6, 34)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("irrelevant", "ignored_reason"),
    [
        (_event(2, episode_id=OLD_EPISODE), IGNORED_EPISODE_MISMATCH),
        (_event(3, side="right"), IGNORED_SIDE_MISMATCH),
        (_event(4, body_region="knee"), IGNORED_REGION_MISMATCH),
        (_event(5, athlete_id=OTHER_ATHLETE), IGNORED_ATHLETE_MISMATCH),
        (_event(6, injury_id=OTHER_INJURY), IGNORED_INJURY_MISMATCH),
    ],
)
def test_01_to_04_other_identity_evidence_is_ignored(irrelevant, ignored_reason):
    result = _resolve(irrelevant, _event(1))
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.evidence_summary.exposure_count == 1
    assert result.evidence_summary.ignored_reason_counts[ignored_reason] == 1


def test_05_copied_exposures_share_one_independent_response_group():
    result = _resolve(_event(1), _event(2), _event(3))
    assert result.decision == "insufficient_evidence"
    assert result.evidence_summary.exposure_count == 3
    assert result.evidence_summary.independent_response_group_count == 1
    assert result.evidence_summary.qualifying_response_group_ids == []


def test_06_separate_response_groups_remain_separate():
    second_group = "66666666-6666-6666-6666-666666666666"
    result = _resolve(_event(1), _event(2, response_group_id=second_group))
    assert result.evidence_summary.independent_response_group_count == 2
    assert result.evidence_summary.qualifying_response_group_ids == []


def test_34_duplicate_retry_rows_do_not_increase_evidence_count():
    row = _event(1)
    result = _resolve(row, dict(row))
    assert result.evidence_summary.exposure_count == 1
    assert result.evidence_summary.independent_response_group_count == 1
    assert result.evidence_summary.ignored_reason_counts[IGNORED_DUPLICATE_EXPOSURE] == 1


def test_bounded_reader_keeps_newest_200_and_newest_negative_cannot_be_excluded():
    store = FakeStore()
    for number in range(1, 202):
        group_id = str(UUID(int=10_000 + number))
        row = _event(
            number,
            response_group_id=group_id,
            during_response="worse" if number == 201 else "same",
        )
        store.create_rehab_exposure(ATHLETE, row["event_json"])

    window = store.list_rehab_exposures(
        ATHLETE,
        injury_id=INJURY,
        injury_episode_id=EPISODE,
        limit=200,
    )
    assert window.history_truncated is True
    assert len(window.rows) == 200
    assert window.rows[0]["event_json"]["drill_id"] == "test_drill_2"
    assert window.rows[-1]["event_json"]["drill_id"] == "test_drill_201"

    result = _resolve(
        *window.rows,
        history_truncated=window.history_truncated,
        criteria=SYNTHETIC_QUANTIFIED_CRITERIA,
    )
    assert result.decision == "not_eligible"
    assert FAIL_DURING_RESPONSE_WORSE in result.reason_codes
    assert result.evidence_summary.history_truncated is True


def test_truncated_positive_window_is_insufficient_never_eligible():
    store = FakeStore()
    for number in range(1, 202):
        row = _event(number, response_group_id=str(UUID(int=20_000 + number)))
        store.create_rehab_exposure(ATHLETE, row["event_json"])

    window = store.list_rehab_exposures(
        ATHLETE,
        injury_id=INJURY,
        injury_episode_id=EPISODE,
        limit=200,
    )
    result = _resolve(
        *window.rows,
        history_truncated=window.history_truncated,
        criteria=SYNTHETIC_QUANTIFIED_CRITERIA,
    )
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_HISTORY_TRUNCATED]
    assert result.eligible_for_load is False
    assert result.evidence_summary.history_truncated is True


def test_supabase_reader_fetches_descending_then_returns_chronology():
    class Query:
        def __init__(self):
            self.order_call = None
            self.limit_call = None

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def order(self, column, *, desc=False):
            self.order_call = (column, desc)
            return self

        def limit(self, size, **_kwargs):
            self.limit_call = size
            return self

        def execute(self):
            return type(
                "Response",
                (),
                {
                    "data": [
                        {"id": "3", "occurred_at": "2026-08-20T03:00:00+00:00"},
                        {"id": "2", "occurred_at": "2026-08-20T02:00:00+00:00"},
                    ]
                },
            )()

    query = Query()
    store = object.__new__(SupabaseAppStore)
    store.client = type("Client", (), {"table": lambda _self, _name: query})()
    window = store.list_rehab_exposures(
        ATHLETE,
        injury_id=INJURY,
        injury_episode_id=EPISODE,
        limit=200,
    )
    assert query.order_call == ("occurred_at", True)
    assert query.limit_call == 201
    assert window.history_truncated is False
    assert [row["id"] for row in window.rows] == ["2", "3"]


# ---------------------------------------------------------------------------
# Uncertainty and honest completion semantics (acceptance tests 7-14)
# ---------------------------------------------------------------------------


def test_07_no_exposures_is_insufficient_not_a_failure_or_success():
    result = _resolve()
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.evidence_summary.exposure_count == 0
    assert result.eligible_for_load is False


@pytest.mark.parametrize(
    ("field", "unknown"),
    [("load", "unknown"), ("impact", "unknown"), ("velocity", "unknown")],
)
def test_08_and_31_any_unknown_demand_dimension_cannot_qualify(field, unknown):
    kwargs = {field: unknown}
    result = _resolve(_event(1, **kwargs))
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.evidence_summary.classification_counts == {"unusable_for_capacity": 1}


def test_09_unknown_demand_with_worse_response_is_still_negative():
    result = _resolve(_event(1, load="unknown", during_response="worse"))
    assert result.decision == "not_eligible"
    assert FAIL_DURING_RESPONSE_WORSE in result.reason_codes
    assert result.evidence_summary.classification_counts == {"negative_response": 1}


def test_10_not_sure_does_not_count_as_positive():
    result = _resolve(_event(1, during_response="not_sure"))
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.evidence_summary.classification_counts == {"incomplete_unknown": 1}


def test_11_not_yet_known_is_not_a_favourable_delayed_response():
    result = _resolve(_event(1, next_day_response="not_yet_known"))
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.evidence_summary.qualifying_exposure_ids == []


@pytest.mark.parametrize("completion_state", ["partial_amount_unknown", "performed_amount_unknown"])
def test_12_and_13_unquantified_work_never_becomes_full_dose(completion_state):
    result = _resolve(_event(1, completion_state=completion_state))
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.evidence_summary.classification_counts == {"incomplete_unknown": 1}


def test_14_missing_response_is_not_treated_as_same_or_no_symptoms():
    result = _resolve(_event(1, include_response=False))
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.evidence_summary.classification_counts == {"incomplete_unknown": 1}


def test_missing_response_group_identity_cannot_inflate_positive_evidence():
    result = _resolve(_event(1, response_group_id=None))
    assert result.decision == "insufficient_evidence"
    assert result.evidence_summary.independent_response_group_count == 0


# ---------------------------------------------------------------------------
# Negative evidence and authoritative safety precedence (tests 15-19)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"stopped_due_to_symptoms": True}, FAIL_STOPPED_DUE_TO_SYMPTOMS),
        ({"during_response": "worse"}, FAIL_DURING_RESPONSE_WORSE),
        ({"next_day_response": "worse"}, FAIL_NEXT_DAY_RESPONSE_WORSE),
    ],
)
def test_negative_exposure_responses_prevent_eligibility(kwargs, reason):
    result = _resolve(_event(1, **kwargs))
    assert result.decision == "not_eligible"
    assert reason in result.reason_codes


def test_15_red_flag_is_medically_blocked():
    result = _resolve(stage=_stage(medical_gate=True, reasons=(REASON_RED_FLAG_GATE,)))
    assert result.decision == "medically_blocked"
    assert result.reason_codes == [BLOCKED_RED_FLAG]


def test_16_medical_review_gate_is_medically_blocked():
    result = _resolve(
        stage=_stage(
            "calm",
            medical_gate=True,
            reasons=(REASON_URGENT_INJURY_TYPE,),
        )
    )
    assert result.decision == "medically_blocked"
    assert result.reason_codes == [BLOCKED_MEDICAL_REVIEW]


def test_17_surface_injury_is_outside_msk_load_eligibility():
    result = _resolve(
        injury=_injury(injury_type="cut", description="cut", body_area="left ankle cut"),
        stage=_stage(None, pathway=CARE_TYPE_WOUND_CARE),
    )
    assert result.decision == "not_applicable"
    assert result.reason_codes == [NOT_APPLICABLE_SURFACE_PATHWAY]


def test_18_current_unresolved_worsening_prevents_eligibility():
    result = _resolve(
        _event(1),
        injury=_injury(latest_reported_status="worse"),
        stage=_stage("calm"),
    )
    assert result.decision == "not_eligible"
    assert result.reason_codes == [BLOCKED_ACTIVE_WORSENING]


def test_19_urgent_gate_precedes_apparently_positive_evidence():
    result = _resolve(
        _event(1),
        injury=_injury(injury_type="fracture", description="fracture"),
        stage=_stage("calm", medical_gate=True, reasons=(REASON_URGENT_INJURY_TYPE,)),
    )
    assert result.decision == "medically_blocked"
    assert ELIGIBLE_LOAD_CRITERIA_MET not in result.reason_codes


def test_latest_negative_response_is_current_not_eligible_evidence():
    older_group = "66666666-6666-6666-6666-666666666666"
    latest_group = "77777777-7777-7777-7777-777777777777"
    result = _resolve(
        _event(1, response_group_id=older_group, during_response="same"),
        _event(2, response_group_id=latest_group, during_response="worse"),
    )
    assert result.decision == "not_eligible"
    assert result.reason_codes == [FAIL_DURING_RESPONSE_WORSE]


def test_historical_negative_followed_by_newer_evidence_is_unresolved_not_a_lifetime_veto():
    older_group = "66666666-6666-6666-6666-666666666666"
    latest_group = "77777777-7777-7777-7777-777777777777"
    result = _resolve(
        _event(1, response_group_id=older_group, during_response="worse"),
        _event(2, response_group_id=latest_group, during_response="better"),
    )
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [
        INSUFFICIENT_UNRESOLVED_NEGATIVE_EVIDENCE,
        FAIL_DURING_RESPONSE_WORSE,
    ]
    criterion = _criterion(result, "historical_negative_evidence_resolved")
    assert criterion.status == "unknown"
    assert criterion.response_group_ids == [older_group]


# ---------------------------------------------------------------------------
# Stage/camp isolation and shadow integration (tests 20-26)
# ---------------------------------------------------------------------------


def test_20_calm_is_not_requalified_for_load():
    result = _resolve(_event(1), stage=_stage("calm"))
    assert result.decision == "not_applicable"
    assert result.reason_codes == [NOT_APPLICABLE_CURRENT_STAGE]


def test_21_restore_fails_closed_without_sourced_condition_criteria():
    result = _resolve(_event(1))
    assert result.current_stage == STAGE_RESTORE
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.eligible_for_load is False


def test_synthetic_exact_quantified_criterion_can_return_shadow_eligible():
    result = _resolve(_event(1), criteria=SYNTHETIC_QUANTIFIED_CRITERIA)
    assert result.current_stage == STAGE_RESTORE
    assert result.decision == "eligible"
    assert result.reason_codes == [ELIGIBLE_LOAD_CRITERIA_MET]
    assert _criterion(result, "completed_dose_quantified").status == "pass"
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE


def test_synthetic_exact_nonquantified_criterion_uses_known_loading_candidate():
    row = _event(1, completion_state="performed_amount_unknown")
    result = _resolve(row, criteria=SYNTHETIC_UNQUANTIFIED_CRITERIA)
    assert result.current_stage == STAGE_RESTORE
    assert result.decision == "eligible"
    dose_criterion = _criterion(result, "completed_dose_quantified")
    assert dose_criterion.status == "not_applicable"
    assert dose_criterion.reason_code == "quantified_dose_not_required_for_criterion"
    assert result.evidence_summary.qualifying_exposure_ids == [row["id"]]
    # Eligibility does not rewrite the honest unquantified observation.
    assert row["event_json"]["dose_completed"]["completion_state"] == "performed_amount_unknown"
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE


def test_22_shadow_decision_does_not_mutate_injury_or_stage_decision():
    injury = _injury()
    original = dict(injury)
    stage = _stage()
    result = _resolve(_event(1), injury=injury, stage=stage)
    assert result.decision == "insufficient_evidence"
    assert injury == original
    assert stage.stage == STAGE_RESTORE


def test_23_and_24_live_stage_ceiling_remains_restore():
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE
    assert MAX_RESOLVABLE_STAGE not in {STAGE_LOAD, STAGE_DYNAMIC, STAGE_RETURN}


@pytest.mark.parametrize("future_stage", [STAGE_LOAD, STAGE_DYNAMIC, STAGE_RETURN])
def test_future_stages_are_not_requalified(future_stage):
    result = _resolve(_event(1), stage=_stage(future_stage))
    assert result.decision == "not_applicable"
    assert result.reason_codes == [NOT_APPLICABLE_CURRENT_STAGE]


def test_25_and_26_camp_phase_has_zero_effect_and_is_not_an_engine_input():
    results = [
        _resolve(_event(1), injury=_injury(camp_phase=phase))
        for phase in ("GPP", "SPP", "TAPER")
    ]
    assert "camp_phase" not in inspect.signature(resolve_load_eligibility).parameters
    assert [result.decision for result in results] == ["insufficient_evidence"] * 3
    assert [result.reason_codes for result in results] == [
        [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    ] * 3


def test_today_shadow_log_does_not_change_live_stage_output(monkeypatch, caplog):
    injury = _injury()
    store = FakeStore()
    store.injury_flags[ATHLETE] = [dict(injury)]
    store.create_rehab_exposure(ATHLETE, _event(1)["event_json"])
    decision = _stage()
    monkeypatch.setattr(
        today_service_module,
        "resolve_rehab_stages",
        lambda *_args, **_kwargs: {INJURY: decision},
    )
    monkeypatch.setattr(
        today_service_module,
        "resolve_load_eligibility",
        lambda **kwargs: resolve_load_eligibility(
            **kwargs,
            criteria_registry={"sprain": SYNTHETIC_QUANTIFIED_CRITERIA},
        ),
    )

    with caplog.at_level("INFO"):
        stamped = today_service_module._with_rehab_stage(
            [injury], store=store, athlete_id=ATHLETE
        )

    assert stamped[0]["rehab_stage"] == STAGE_RESTORE
    assert "load_eligibility" not in stamped[0]
    record = next(record for record in caplog.records if "load_eligibility_shadow {" in record.message)
    payload = json.loads(record.message.split("load_eligibility_shadow ", 1)[1])
    assert payload["result"] == "eligible"
    assert payload["history_truncated"] is False
    assert payload["engine_version"] == LOAD_ELIGIBILITY_ENGINE_VERSION


def test_shadow_evidence_cannot_change_today_enrichment_output(monkeypatch):
    decision = _stage()
    monkeypatch.setattr(
        today_service_module,
        "resolve_rehab_stages",
        lambda *_args, **_kwargs: {INJURY: decision},
    )
    monkeypatch.setattr(
        today_service_module,
        "resolve_load_eligibility",
        lambda **kwargs: resolve_load_eligibility(
            **kwargs,
            criteria_registry={"sprain": SYNTHETIC_QUANTIFIED_CRITERIA},
        ),
    )
    without_evidence = FakeStore()
    with_evidence = FakeStore()
    with_evidence.create_rehab_exposure(ATHLETE, _event(1)["event_json"])

    first = today_service_module._with_rehab_stage(
        [_injury()], store=without_evidence, athlete_id=ATHLETE
    )
    second = today_service_module._with_rehab_stage(
        [_injury()], store=with_evidence, athlete_id=ATHLETE
    )
    assert first == second
    assert first[0]["rehab_stage"] == STAGE_RESTORE


# ---------------------------------------------------------------------------
# Criteria integrity, absence of universal thresholds, determinism (27-34)
# ---------------------------------------------------------------------------


def test_27_unsupported_symptom_only_type_is_insufficient():
    result = _resolve(
        _event(1),
        injury=_injury(injury_type="pain", description="ankle pain"),
    )
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]


def test_free_text_cannot_manufacture_progression_injury_type():
    injury = _injury(description="ankle sprain?", body_area="left ankle")
    injury.pop("injury_type")
    assert resolve_injury_type(injury) == "unspecified"
    result = _resolve(_event(1), injury=injury)
    assert result.injury_type == "unspecified"
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]


def test_only_exact_structured_taxonomy_field_can_select_an_injury_type():
    assert resolve_injury_type(_injury(injury_type="sprain")) == "sprain"
    assert resolve_injury_type(_injury(injury_type="made_up", description="sprain")) == "unspecified"


@pytest.mark.parametrize(
    "injury_type",
    ["sprain", "strain", "tendonitis", "instability", "impingement"],
)
def test_28_taxonomy_label_without_progression_provenance_is_unsupported(injury_type):
    assert criteria_for_injury_type(injury_type) is None
    result = _resolve(_event(1), injury=_injury(injury_type=injury_type))
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]


def test_29_no_generic_family_rule_can_leak_across_injury_types():
    assert dict(LOAD_CRITERIA_REGISTRY) == {}
    assert all(
        criteria_for_injury_type(injury_type) is None
        for injury_type in ("sprain", "strain", "tendonitis", "instability", "pain")
    )


def test_30_minimal_mobility_demand_cannot_prove_loading_capacity():
    result = _resolve(_event(1, load="minimal"))
    assert result.decision == "insufficient_evidence"
    assert result.reason_codes == [INSUFFICIENT_UNSUPPORTED_INJURY_TYPE]
    assert result.evidence_summary.classification_counts == {"neutral_observation": 1}


def test_32_criteria_have_no_day_or_elapsed_time_threshold():
    names = {field.name for field in fields(LoadCriteria)}
    assert not names & {"days", "min_days", "elapsed_days", "injury_age"}
    old = _resolve(_event(1), injury=_injury(created_at="2020-01-01T00:00:00+00:00"))
    recent = _resolve(_event(1), injury=_injury(created_at="2026-08-19T00:00:00+00:00"))
    assert (old.decision, old.reason_codes) == (recent.decision, recent.reason_codes)


def test_33_criteria_have_no_session_or_exposure_count_threshold():
    names = {field.name for field in fields(LoadCriteria)}
    assert not names & {"sessions", "min_sessions", "exposures", "min_exposures"}
    one = _resolve(_event(1))
    two = _resolve(
        _event(1),
        _event(2, response_group_id="66666666-6666-6666-6666-666666666666"),
    )
    assert (one.decision, one.reason_codes) == (two.decision, two.reason_codes)


def test_result_is_deterministic_across_input_order():
    rows = [
        _event(1),
        _event(2, response_group_id="66666666-6666-6666-6666-666666666666"),
    ]
    first = _resolve(*rows)
    second = _resolve(*reversed(rows))
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_evaluated_at_is_a_source_watermark_not_the_current_clock():
    result = _resolve(_event(1))
    assert result.evaluated_at == START + timedelta(minutes=1)
    assert result.engine_version == "1"
