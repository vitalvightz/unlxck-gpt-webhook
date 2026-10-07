"""Every loggable block carries a server-owned ``block_id``.

Exercise logs key on ``(plan, training day, block_id)``, so the id must exist on
every block whatever the Stage 2 converter emitted, must be the same whether it
was stamped at save or derived on read, and must leave rehab identity alone.
"""

from __future__ import annotations

import copy
from unittest.mock import MagicMock

from api.services.effective_structured_plan import resolve_effective_structured_plan
from api.services.rehab_completion_service import session_rehab_items
from api.store import SupabaseAppStore
from api.structured_block_identity import ensure_structured_block_ids
from api.structured_plan_models import SCHEMA_VERSION

from test_stage2_structured_persistence import _build_request
from test_structured_plan_models import _valid_plan

ANKLE_DRILL = "ankle_sprain_single_leg_balance_on_foam_pad"


def _block(name: str, block_type: str = "strength", **extra) -> dict:
    return {"block_type": block_type, "display_name": name, **extra}


def _plan(*days: dict) -> dict:
    return {"weeks": [{"week_index": 1, "days": list(days)}]}


def _day(date: str, *sessions: list[dict]) -> dict:
    return {
        "date": date,
        "sessions": [
            {"session_id": f"s{index + 1}", "blocks": blocks} for index, blocks in enumerate(sessions)
        ],
    }


def _ids(plan: dict) -> list[list[str | None]]:
    return [
        [block.get("block_id") for session in day["sessions"] for block in session["blocks"]]
        for week in plan["weeks"]
        for day in week["days"]
    ]


def test_missing_ids_are_derived_from_day_and_exercise():
    """Pinned: logs on cards saved before ids were persisted key on these values."""
    plan = _plan(
        _day(
            "2026-10-12",
            [
                _block("Romanian Deadlift (DB)", sets=3, reps="8-12"),
                _block("3 x 2 min easy rounds", "conditioning", exercise_key="tempo-shadowboxing"),
            ],
            [_block("Box breathing reset", "mindset")],
        )
    )

    assert _ids(ensure_structured_block_ids(plan)) == [
        [
            "blk-2026-10-12-romanian-deadlift-db",
            "blk-2026-10-12-tempo-shadowboxing",
            "blk-2026-10-12-box-breathing-reset",
        ]
    ]


def test_existing_ids_are_kept_and_a_complete_card_is_returned_as_is():
    plan = _plan(_day("2026-10-12", [_block("Squat", block_id="locked-d-21-squat"), _block("Row", block_id="blk-1")]))

    assert ensure_structured_block_ids(plan) is plan


def test_the_input_is_never_mutated():
    plan = _plan(_day("2026-10-12", [_block("Squat"), _block("Row", block_id="row")]))
    before = copy.deepcopy(plan)

    stamped = ensure_structured_block_ids(plan)

    assert plan == before
    assert stamped is not plan
    # Untouched blocks stay shared with the stored card rather than copied.
    assert stamped["weeks"][0]["days"][0]["sessions"][0]["blocks"][1] is plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][1]


def test_the_same_exercise_twice_in_a_day_gets_distinct_ids_across_sessions():
    plan = _plan(
        _day("2026-10-12", [_block("Pallof Press"), _block("Pallof Press")], [_block("Pallof Press")]),
        _day("2026-10-14", [_block("Pallof Press")]),
    )

    assert _ids(ensure_structured_block_ids(plan)) == [
        ["blk-2026-10-12-pallof-press", "blk-2026-10-12-pallof-press-2", "blk-2026-10-12-pallof-press-3"],
        ["blk-2026-10-14-pallof-press"],
    ]


def test_a_day_without_a_valid_date_uses_its_week_and_day_slot():
    plan = {
        "weeks": [
            {"days": [{"weekday": "Mon", "sessions": [{"blocks": [_block("Squat")]}]}]},
            {"days": [{"date": "", "sessions": []}, {"date": "tbc", "sessions": [{"blocks": [_block("Squat")]}]}]},
        ]
    }

    assert _ids(ensure_structured_block_ids(plan)) == [["blk-w1d1-squat"], [], ["blk-w2d2-squat"]]


def test_a_derived_id_never_lands_on_one_a_later_block_already_carries():
    plan = _plan(_day("2026-10-12", [_block("Squat"), _block("Front Squat", block_id="blk-2026-10-12-squat")]))

    assert _ids(ensure_structured_block_ids(plan)) == [["blk-2026-10-12-squat-2", "blk-2026-10-12-squat"]]


def test_two_blocks_sharing_an_id_on_one_day_are_separated_but_not_across_days():
    """A shared id on one day would make the two blocks overwrite each other's log."""
    plan = _plan(
        _day("2026-10-12", [_block("Sled Push", block_id="sled-push")], [_block("Sled Push", block_id="sled-push")]),
        _day("2026-10-14", [_block("Sled Push", block_id="sled-push")]),
    )

    assert _ids(ensure_structured_block_ids(plan)) == [["sled-push", "sled-push-2"], ["sled-push"]]


def test_the_dose_is_not_part_of_the_identity():
    light = _plan(_day("2026-10-12", [_block("Squat", sets=3, reps=5, load={"value": 80, "unit": "kg"})]))
    heavy = _plan(_day("2026-10-12", [_block("Squat", sets=5, reps=3, load={"value": 110, "unit": "kg"})]))

    assert _ids(ensure_structured_block_ids(light)) == _ids(ensure_structured_block_ids(heavy))


def test_a_nameless_block_still_gets_an_id():
    plan = _plan(_day("2026-10-12", [{"block_type": "accessory", "display_name": " "}, {"display_name": "", "block_id": "  "}]))

    assert _ids(ensure_structured_block_ids(plan)) == [["blk-2026-10-12-accessory", "blk-2026-10-12-block"]]


def test_stamping_is_idempotent():
    plan = _plan(_day("2026-10-12", [_block("Squat"), _block("Squat"), _block("Row", block_id="row")]))
    stamped = ensure_structured_block_ids(plan)

    assert ensure_structured_block_ids(stamped) is stamped


def test_anything_that_is_not_a_plan_passes_through():
    assert ensure_structured_block_ids(None) is None
    assert ensure_structured_block_ids("not a plan") == "not a plan"
    for value in ({}, {"weeks": None}, {"weeks": [None, {"days": None}, {"days": [None, {"sessions": None}]}]}):
        assert ensure_structured_block_ids(value) is value


# ---------------------------------------------------------------------------
# Rehab identity belongs to the rehab completion contract and is not re-keyed
# ---------------------------------------------------------------------------


def _rehab_block(**extra) -> dict:
    return {"block_type": "rehab", "display_name": "Single-leg balance", "rehab_drill_id": ANKLE_DRILL, **extra}


def test_rehab_blocks_are_left_exactly_as_stored():
    legacy = _rehab_block()
    duplicate_a, duplicate_b = _rehab_block(block_id="rehab:injury-1:balance"), _rehab_block(block_id="rehab:injury-1:balance")
    plan = _plan(_day("2026-10-12", [legacy, duplicate_a, duplicate_b, _block("Squat")]))

    blocks = ensure_structured_block_ids(plan)["weeks"][0]["days"][0]["sessions"][0]["blocks"]

    assert blocks[0] is legacy and "block_id" not in blocks[0]
    assert blocks[1] is duplicate_a and blocks[2] is duplicate_b
    assert blocks[3]["block_id"] == "blk-2026-10-12-squat"


def test_a_legacy_rehab_block_keeps_its_evidence_key_through_the_read_path():
    """A rehab block with no id is identified by its content hash; stamping an id
    on it would re-key work the athlete has already been credited for."""
    plan_row = {
        "id": "plan-1",
        "structured_plan": _plan(_day("2026-10-12", [_rehab_block(), _block("Squat")])),
    }

    items = session_rehab_items(plan_row, training_day="2026-10-12", session_id="s1")

    assert [item["rehab_occurrence_key"].split(":")[0] for item in items] == ["legacy"]


# ---------------------------------------------------------------------------
# Read path: cards saved before ids were persisted
# ---------------------------------------------------------------------------


def _legacy_valid_plan() -> dict:
    plan = _valid_plan()
    for week in plan["weeks"]:
        for day in week["days"]:
            for session in day["sessions"]:
                for block in session["blocks"]:
                    block["block_id"] = None
    return plan


def test_the_effective_plan_always_carries_block_ids():
    stored = _legacy_valid_plan()
    before = copy.deepcopy(stored)

    effective = resolve_effective_structured_plan({"id": "plan-1", "structured_plan": stored})

    assert effective is not None
    assert all(block_id and block_id.startswith("blk-2026-05-29-") for day in _ids(effective) for block_id in day)
    assert stored == before


def test_a_read_derives_exactly_the_id_a_save_would_have_stamped():
    stored = _legacy_valid_plan()

    read = resolve_effective_structured_plan({"id": "plan-1", "structured_plan": stored})
    saved = ensure_structured_block_ids(stored)

    assert _ids(read) == _ids(saved)
    assert _ids(resolve_effective_structured_plan({"id": "plan-1", "structured_plan": saved})) == _ids(saved)


# ---------------------------------------------------------------------------
# Save path: every plan write stamps the ids before the card is stored
# ---------------------------------------------------------------------------


def _store() -> SupabaseAppStore:
    return SupabaseAppStore(client=MagicMock(), admin_emails=set())


def _expected_ids() -> list[list[str | None]]:
    return _ids(ensure_structured_block_ids(_legacy_valid_plan()))


def test_create_plan_stores_block_ids():
    store = _store()
    captured: dict = {}

    def _insert(payload: dict):
        captured["payload"] = payload
        handle = MagicMock()
        handle.execute.return_value = MagicMock(data=[{"id": "plan-1", **payload}])
        return handle

    store.client.table.return_value.insert.side_effect = _insert
    card = _legacy_valid_plan()
    store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake-1",
        request=_build_request(),
        result={
            "status": "ready",
            "plan_text": "# raw",
            "final_plan_text": "# raw",
            "structured_plan": card,
            "schema_version": SCHEMA_VERSION,
        },
    )

    assert _ids(captured["payload"]["structured_plan"]) == _expected_ids()
    assert card == _legacy_valid_plan()  # the caller's card is not mutated


def test_stage2_update_payload_stores_block_ids():
    payload = _store()._build_plan_stage2_payload(
        {"id": "plan-1", "status": "ready"},
        {"status": "ready", "plan_text": "# raw", "structured_plan": _legacy_valid_plan()},
    )

    assert _ids(payload["structured_plan"]) == _expected_ids()


def test_stage2_update_payload_without_a_card_is_unchanged():
    store = _store()

    assert "structured_plan" not in store._build_plan_stage2_payload(
        {"id": "plan-1", "status": "ready"}, {"status": "ready", "plan_text": "# raw"}
    )
    cleared = store._build_plan_stage2_payload(
        {"id": "plan-1", "status": "ready"}, {"status": "ready", "plan_text": "# raw", "structured_plan": None}
    )
    assert cleared["structured_plan"] is None


def test_structured_artifacts_write_stores_block_ids():
    store = _store()
    captured: dict = {}

    def _update(payload: dict):
        captured["payload"] = payload
        return MagicMock()

    store.client.table.return_value.update.side_effect = _update
    store.get_plan = lambda plan_id: {"id": plan_id}  # type: ignore[method-assign]

    store.update_plan_structured_artifacts(
        "plan-1",
        structured_plan=_legacy_valid_plan(),
        schema_version=SCHEMA_VERSION,
        stage2_validator_report={},
    )

    assert _ids(captured["payload"]["structured_plan"]) == _expected_ids()
