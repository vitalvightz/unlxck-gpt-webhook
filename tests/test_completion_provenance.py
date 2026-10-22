"""A legacy NULL-origin row that carries occurrence-owned evidence is a reported session.

A frozen prescription snapshot or rehab result belongs to one executed session.
Legacy sibling credit copied RPE, pain and notes, so those never prove execution.
"""
import pytest

from fightcamp.completed_workload import completed_workload, completion_origin_of, has_unverified_completions

DAY = "2026-10-22"


def legacy(**fields):
    return {"source": "unlxck", "status": "done", "completion_origin": None, "training_day": "2026-10-18",
            "session_id": "rehab-2026-10-18-x", "notes": "", **fields}


@pytest.mark.parametrize("evidence", [
    {"rehab_performance": "done_as_shown", "prescription_snapshot": {"session": {}}},  # the real 18 Oct row
    {"prescription_snapshot": {"session": {}}}, {"rehab_response_contexts": [{"id": "c"}]},
])
def test_legacy_row_with_execution_evidence_is_reported(evidence):
    row = legacy(**evidence)
    assert completion_origin_of(row) == "reported"
    assert not has_unverified_completions([row], DAY)


@pytest.mark.parametrize("copied", [{}, {"session_rpe": 1, "notes": "Feel sharp ready for fight"}, {"pain_after": 0}])
def test_copied_or_bare_legacy_row_stays_unverified(copied):
    # The real 13 Oct pair: identical RPE and notes on two sibling rows.
    row = legacy(**copied)
    assert completion_origin_of(row) is None
    assert has_unverified_completions([row], DAY)


def test_stored_origin_wins():
    assert completion_origin_of(legacy(completion_origin="day_credit", session_rpe=None)) == "day_credit"
    assert completion_origin_of(legacy(completion_origin="reported")) == "reported"


def test_proven_legacy_session_counts_as_workload():
    hard = legacy(session_rpe=9, prescription_snapshot={"session": {}}, training_day="2026-10-21")
    assert completed_workload([hard], DAY) == completed_workload([{**hard, "completion_origin": "reported"}], DAY)
