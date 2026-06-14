"""Stage 2 structured-plan persistence, mapping, and automator integration.

These tests cover the additive structured_plan path end-to-end without breaking
the legacy raw plan_text flow:

* persistence: ``SupabaseAppStore.create_plan`` writes the new columns.
* mapping: ``_map_plan_detail`` surfaces a valid structured plan, falls back to
  plan_text when it is missing/malformed, and exposes admin debug status.
* automator: ``OpenAIStage2Automator.finalize`` attempts structured generation
  (incl. one repair retry) when enabled, and never blocks the raw plan.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


import api.stage2_automation as stage2_module
from api.plan_mappers import _map_plan_detail
from api.services.admin_stage2_service import (
    approve_review_required_plan,
    run_structured_plan_post_processing,
)
from api.stage2_automation import (
    OpenAIStage2Automator,
    attempt_structured_plan_for_result,
)
from api.store import SupabaseAppStore
from api.structured_plan_generation import StructuredPlanOutcome, build_structured_plan_outcome
from api.structured_plan_models import SCHEMA_VERSION

from support import FakeStore, _build_request, _now
from test_structured_plan_models import _valid_plan


class _StructuredAutomator:
    """Minimal automator exposing only the structured conversion hook."""

    def __init__(self, outcome: StructuredPlanOutcome, costs=None):
        self.outcome = outcome
        self.costs = costs or []
        self.calls: list[dict] = []

    async def _attempt_structured_plan(self, *, final_plan_text, planning_brief, source, log_context=None):
        self.calls.append(
            {"final_plan_text": final_plan_text, "planning_brief": planning_brief, "source": source}
        )
        return self.outcome, list(self.costs)


def _valid_outcome(raw_markdown: str = "# final plan") -> StructuredPlanOutcome:
    return build_structured_plan_outcome(_valid_plan(), raw_markdown=raw_markdown)


# ---------------------------------------------------------------------------
# Persistence: create_plan writes structured_plan + schema_version
# ---------------------------------------------------------------------------


def _capture_create_plan(result: dict) -> dict:
    """Run create_plan against a mock client and return the inserted payload."""
    store = SupabaseAppStore(client=MagicMock(), admin_emails=set())
    captured: dict = {}

    def _insert(payload: dict):
        captured["payload"] = payload
        handle = MagicMock()
        handle.execute.return_value = MagicMock(data=[{"id": "plan-1", **payload}])
        return handle

    store.client.table.return_value.insert.side_effect = _insert
    store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake-1",
        request=_build_request(),
        result=result,
    )
    return captured["payload"]


# A. Existing raw-only Stage 2 plan still saves (structured columns stay NULL).
def test_create_plan_raw_only_leaves_structured_columns_null():
    payload = _capture_create_plan(
        {"status": "ready", "plan_text": "# raw", "final_plan_text": "# raw"}
    )
    assert payload["plan_text"] == "# raw"
    assert payload["structured_plan"] is None
    assert payload["schema_version"] is None


# B. Valid structured output is persisted beside plan_text.
def test_create_plan_persists_valid_structured_plan():
    structured = _valid_plan()
    payload = _capture_create_plan(
        {
            "status": "ready",
            "plan_text": "# raw",
            "final_plan_text": "# raw",
            "structured_plan": structured,
            "schema_version": SCHEMA_VERSION,
        }
    )
    assert payload["plan_text"] == "# raw"  # raw fallback kept
    assert payload["structured_plan"] == structured
    assert payload["schema_version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Mapping: _map_plan_detail
# ---------------------------------------------------------------------------


def _plan_row(**overrides) -> dict:
    row = {
        "id": "plan-1",
        "athlete_id": "athlete-1",
        "full_name": "Ari Mensah",
        "status": "generated",
        "plan_text": "# raw plan",
        "stage2_validator_report": {"errors": [], "warnings": []},
    }
    row.update(overrides)
    return row


# H (valid) + B mapping: structured plan surfaces in outputs.
def test_map_plan_detail_returns_structured_plan_when_valid():
    detail = _map_plan_detail(
        _plan_row(structured_plan=_valid_plan()), include_admin=True
    )
    assert detail.outputs.plan_text == "# raw plan"
    assert detail.outputs.structured_plan is not None
    assert detail.outputs.schema_version == SCHEMA_VERSION
    assert detail.admin_outputs.structured_schema_version == SCHEMA_VERSION


# A + H (none): legacy row with no structured_plan returns plan_text only.
def test_map_plan_detail_falls_back_to_plan_text_when_missing():
    detail = _map_plan_detail(_plan_row(), include_admin=True)
    assert detail.outputs.structured_plan is None
    assert detail.outputs.schema_version is None
    assert detail.outputs.plan_text == "# raw plan"
    assert detail.admin_outputs.structured_plan_status == "not_attempted"


# H (malformed): a malformed structured_plan is dropped, plan_text still returns.
def test_map_plan_detail_drops_malformed_structured_plan():
    detail = _map_plan_detail(
        _plan_row(structured_plan={"plan_metadata": "not-an-object"}),
        include_admin=True,
    )
    assert detail.outputs.structured_plan is None
    assert detail.outputs.plan_text == "# raw plan"


# C (admin debug): invalid structured attempt records status + errors for admin.
def test_map_plan_detail_exposes_invalid_structured_debug():
    row = _plan_row(
        structured_plan=None,
        stage2_validator_report={
            "errors": [],
            "warnings": [],
            "structured_plan": {
                "status": "invalid_fallback_used",
                "errors": ["plan_metadata: field required"],
                "schema_version": None,
            },
        },
    )
    detail = _map_plan_detail(row, include_admin=True)
    assert detail.outputs.structured_plan is None  # invalid never exposed
    assert detail.outputs.plan_text == "# raw plan"  # fallback preserved
    assert detail.admin_outputs.structured_plan_status == "invalid_fallback_used"
    assert detail.admin_outputs.structured_plan_errors == ["plan_metadata: field required"]


# ---------------------------------------------------------------------------
# Automator integration
# ---------------------------------------------------------------------------


class _FakeResponses:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    async def create(self, **request: object) -> object:
        self.calls.append(request)
        return self.outputs.pop(0)


class _FakeClient:
    def __init__(self, outputs: list[object]) -> None:
        self.responses = _FakeResponses(outputs)


def _response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="resp_test",
        output_text=text,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def _stage1_result() -> dict:
    return {
        "plan_text": "# Stage 1 Draft",
        "coach_notes": "### Coach Review",
        "pdf_url": None,
        "why_log": {},
        "stage2_payload": {"ok": True},
        "planning_brief": {"schema_version": "planning_brief.v1", "fight_date": "2026-06-13"},
        "stage2_handoff_text": "handoff",
    }


def _pass_review(**_):
    return {
        "status": "PASS",
        "needs_retry": False,
        "validator_report": {"errors": [], "warnings": [], "review_flag_count": 0},
    }


def test_finalize_skips_structured_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_PLAN", raising=False)
    monkeypatch.setattr(stage2_module, "review_stage2_output", _pass_review)
    client = _FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    # Only the single plan-text call; no structured calls when disabled.
    assert len(client.responses.calls) == 1
    assert result["structured_plan"] is None
    assert result["schema_version"] is None
    assert result["stage2_validator_report"]["structured_plan"]["status"] == "not_attempted"
    assert result["plan_text"] == "# final plan"


def test_finalize_attaches_valid_structured_plan(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", _pass_review)
    client = _FakeClient([_response("# final plan"), _response(json.dumps(_valid_plan()))])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert len(client.responses.calls) == 2  # plan + structured first pass
    assert result["plan_text"] == "# final plan"  # raw fallback untouched
    assert result["schema_version"] == SCHEMA_VERSION
    assert isinstance(result["structured_plan"], dict)
    assert result["stage2_validator_report"]["structured_plan"]["status"] == "valid"


def _fail_review(*codes: str):
    error_codes = codes or ("true_internal_system_leak",)

    def _review(**_):
        return {
            "status": "FAIL",
            "needs_retry": True,
            "validator_report": {
                "errors": [{"code": code} for code in error_codes],
                "warnings": [],
                "blocking_warnings": [],
                "review_flag_count": 0,
            },
        }

    return _review


def test_finalize_soft_hold_rescued_by_clean_card(monkeypatch: pytest.MonkeyPatch):
    # A hold whose only error is non-safety (internal scaffolding leak) is
    # published when a schema-valid structured card vouches for it.
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", _fail_review("true_internal_system_leak"))
    client = _FakeClient([_response("# final plan"), _response(json.dumps(_valid_plan()))])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert result["status"] == "publishable_with_flags"
    assert result["plan_text"] == "# final plan"
    assert isinstance(result["structured_plan"], dict)
    assert result["stage2_validator_report"]["structured_plan"]["status"] == "valid"
    # The original error is still recorded for admin visibility.
    assert result["stage2_validator_report"]["errors"] == [{"code": "true_internal_system_leak"}]


def test_finalize_soft_hold_reverts_to_hold_when_card_invalid(monkeypatch: pytest.MonkeyPatch):
    # Same soft hold, but the card never validates -> the plan is held after all.
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", _fail_review("true_internal_system_leak"))
    client = _FakeClient(
        [
            _response("# final plan"),
            _response(json.dumps(["not", "a", "plan"])),  # invalid first pass
            _response(json.dumps(["still", "broken"])),  # repair still invalid
        ]
    )
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert result["status"] == "held_for_review"
    assert result["plan_text"] == ""
    assert result["final_plan_text"] == "# final plan"
    assert result["structured_plan"] is None


def test_finalize_safety_hold_is_never_rescued(monkeypatch: pytest.MonkeyPatch):
    # A safety error (restriction violation) holds regardless of the card; the
    # structured attempt is not even made because the hold is not displayable.
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", _fail_review("restriction_violation"))
    client = _FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert result["status"] == "held_for_review"
    assert len(client.responses.calls) == 1  # no structured call attempted
    assert result["stage2_validator_report"]["structured_plan"]["status"] == "not_attempted"


def test_finalize_soft_hold_held_when_structured_disabled(monkeypatch: pytest.MonkeyPatch):
    # With structured generation off, a soft hold behaves exactly as before
    # (held_for_review) — no card can rescue it, so the status never flaps.
    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_PLAN", raising=False)
    monkeypatch.setattr(stage2_module, "review_stage2_output", _fail_review("true_internal_system_leak"))
    client = _FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert result["status"] == "held_for_review"
    assert len(client.responses.calls) == 1


def test_finalize_uses_one_repair_retry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", _pass_review)
    client = _FakeClient(
        [
            _response("# final plan"),
            _response(json.dumps(["not", "a", "plan"])),  # invalid first structured pass
            _response(json.dumps(_valid_plan())),  # repaired structured pass
        ]
    )
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert len(client.responses.calls) == 3  # plan + first + repair
    assert isinstance(result["structured_plan"], dict)
    assert result["schema_version"] == SCHEMA_VERSION
    assert (
        result["stage2_validator_report"]["structured_plan"]["status"]
        == "repair_attempted_valid"
    )


def test_finalize_keeps_raw_plan_when_structured_invalid_after_repair(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", _pass_review)
    client = _FakeClient(
        [
            _response("# final plan"),
            _response(json.dumps(["not", "a", "plan"])),  # invalid
            _response(json.dumps(["still", "broken"])),  # repair still invalid
        ]
    )
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert result["plan_text"] == "# final plan"  # user still gets the raw plan
    assert result["structured_plan"] is None  # invalid never persisted
    debug = result["stage2_validator_report"]["structured_plan"]
    assert debug["status"] == "invalid_fallback_used"
    assert debug["errors"]


def test_finalize_accumulates_structured_call_costs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", _pass_review)
    # plan pass (10/5) + structured first (10/5) + structured repair (10/5).
    client = _FakeClient(
        [
            _response("# final plan"),
            _response(json.dumps(["not", "a", "plan"])),  # invalid -> triggers repair
            _response(json.dumps(_valid_plan())),
        ]
    )
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    cost = result["stage2_cost"]
    # 3 calls summed: input 3*10, output 3*5, total 3*15.
    assert cost["stage2_input_tokens"] == 30
    assert cost["stage2_output_tokens"] == 15
    assert cost["stage2_total_tokens"] == 45


def test_finalize_cost_unchanged_when_structured_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_PLAN", raising=False)
    monkeypatch.setattr(stage2_module, "review_stage2_output", _pass_review)
    client = _FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    # Single plan-text call only: no double counting of the merge step.
    assert result["stage2_cost"]["stage2_input_tokens"] == 10
    assert result["stage2_cost"]["stage2_output_tokens"] == 5
    assert result["stage2_cost"]["stage2_total_tokens"] == 15


def test_finalize_does_not_crash_when_structured_model_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", _pass_review)
    # Second call (structured) raises; the raw plan must still come back.
    client = _FakeClient([_response("# final plan"), RuntimeError("boom")])

    async def create(**request):
        client.responses.calls.append(request)
        output = client.responses.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    client.responses.create = create  # type: ignore[assignment]
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert result["plan_text"] == "# final plan"
    assert result["structured_plan"] is None
    assert result["stage2_validator_report"]["structured_plan"]["status"] == "not_attempted"


# ---------------------------------------------------------------------------
# Centralized trigger: attempt_structured_plan_for_result
# ---------------------------------------------------------------------------


def test_helper_attaches_structured_on_displayable_result(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    automator = _StructuredAutomator(_valid_outcome())
    result = {"status": "ready", "final_plan_text": "# final plan", "stage2_validator_report": {}}

    out, _costs = asyncio.run(
        attempt_structured_plan_for_result(
            result, planning_brief={}, automator=automator, source="admin_stage2"
        )
    )

    assert len(automator.calls) == 1
    assert out["structured_plan"] is not None
    assert out["schema_version"] == SCHEMA_VERSION
    assert out["stage2_validator_report"]["structured_plan"]["status"] == "valid"


def test_helper_attaches_for_publishable_with_flags(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    automator = _StructuredAutomator(_valid_outcome())
    result = {
        "status": "publishable_with_flags",
        "final_plan_text": "# final plan",
        "stage2_validator_report": {},
    }
    out, _costs = asyncio.run(
        attempt_structured_plan_for_result(result, planning_brief={}, automator=automator, source="x")
    )
    assert len(automator.calls) == 1
    assert out["structured_plan"] is not None


def test_helper_skips_non_displayable_status(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    automator = _StructuredAutomator(_valid_outcome())
    result = {"status": "review_required", "final_plan_text": "# x", "stage2_validator_report": {}}

    out, _costs = asyncio.run(
        attempt_structured_plan_for_result(result, planning_brief={}, automator=automator, source="x")
    )

    assert automator.calls == []  # no model call for a non-displayable plan
    assert out["structured_plan"] is None
    assert out["stage2_validator_report"]["structured_plan"]["status"] == "not_attempted"


def test_helper_skips_when_env_disabled(monkeypatch):
    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_PLAN", raising=False)
    automator = _StructuredAutomator(_valid_outcome())
    result = {"status": "ready", "final_plan_text": "# x", "stage2_validator_report": {}}
    out, _costs = asyncio.run(
        attempt_structured_plan_for_result(result, planning_brief={}, automator=automator, source="x")
    )
    assert automator.calls == []
    assert out["structured_plan"] is None


def test_helper_skips_when_automator_has_no_converter(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    result = {"status": "ready", "final_plan_text": "# x", "stage2_validator_report": {}}
    out, _costs = asyncio.run(
        attempt_structured_plan_for_result(result, planning_brief={}, automator=object(), source="x")
    )
    assert out["structured_plan"] is None
    assert out["stage2_validator_report"]["structured_plan"]["status"] == "not_attempted"


# ---------------------------------------------------------------------------
# Admin approval is fast/DB-only; structured conversion is deferred
# ---------------------------------------------------------------------------


def _seed_held_plan(store: FakeStore, *, plan_id: str = "plan-1") -> str:
    store.profiles["athlete-1"] = {"id": "athlete-1", "full_name": "Ari Mensah"}
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": "athlete-1",
        "full_name": "Ari Mensah",
        "status": "held_for_review",
        "plan_text": "",
        "final_plan_text": "# approved plan",
        "draft_plan_text": "# draft plan",
        "planning_brief": None,
        "stage2_validator_report": {},
        "stage2_status": "stage2_failed",
        "stage2_attempt_count": 1,
        "created_at": _now(),
    }
    return plan_id


def test_admin_approve_is_db_only_and_skips_synchronous_structured(monkeypatch):
    """Approval must be a fast DB-only release.

    Structured conversion can call the model and is slow enough to trip the
    frontend/proxy request timeout (the false "Connection issue" bug), so the
    approval path must not run it synchronously. It still returns a ready plan
    with plan_text populated; structured conversion is left to the background
    post-processing step.
    """
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    store = FakeStore()
    plan_id = _seed_held_plan(store)
    automator = _StructuredAutomator(_valid_outcome("# approved plan"))

    detail = asyncio.run(
        approve_review_required_plan(plan_id=plan_id, store=store, stage2=automator)
    )

    assert detail.status == "ready"
    assert detail.outputs.plan_text == "# approved plan"  # plan_text preserved
    # No synchronous conversion: nothing structured on the response or row, and
    # the converter was never invoked during approval.
    assert detail.outputs.structured_plan is None
    assert store.plans[plan_id].get("structured_plan") is None
    assert automator.calls == []


def test_structured_post_processing_converts_after_approval(monkeypatch):
    """The non-blocking post-processing step performs the deferred conversion."""
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    store = FakeStore()
    plan_id = _seed_held_plan(store)
    automator = _StructuredAutomator(_valid_outcome("# approved plan"))

    asyncio.run(
        approve_review_required_plan(plan_id=plan_id, store=store, stage2=automator)
    )
    assert automator.calls == []  # nothing during the fast approval

    asyncio.run(
        run_structured_plan_post_processing(plan_id=plan_id, store=store, stage2=automator)
    )

    # Conversion ran exactly once and is persisted, without disturbing the live
    # released plan (status/plan_text intact).
    assert len(automator.calls) == 1
    assert store.plans[plan_id]["structured_plan"] is not None
    assert store.plans[plan_id]["schema_version"] == SCHEMA_VERSION
    assert store.plans[plan_id]["status"] == "ready"
    assert store.plans[plan_id]["plan_text"] == "# approved plan"


def test_structured_post_processing_failure_keeps_plan_text_and_ready(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    store = FakeStore()
    plan_id = _seed_held_plan(store)
    failed = StructuredPlanOutcome(status="invalid_fallback_used", errors=["bad shape"])
    automator = _StructuredAutomator(failed)

    asyncio.run(
        approve_review_required_plan(plan_id=plan_id, store=store, stage2=automator)
    )
    asyncio.run(
        run_structured_plan_post_processing(plan_id=plan_id, store=store, stage2=automator)
    )

    # A structured failure leaves the released raw markdown plan intact.
    assert store.plans[plan_id]["status"] == "ready"
    assert store.plans[plan_id]["plan_text"] == "# approved plan"
    assert store.plans[plan_id].get("structured_plan") is None


class _ConcurrentMutationAutomator(_StructuredAutomator):
    """Automator that runs a concurrent admin action *during* the slow conversion.

    Simulates the race the narrow structured writer guards against: the model
    conversion takes seconds, and a second admin rewrites the plan row in the
    meantime (reject, archive, rename, manual Stage 2 edit).
    """

    def __init__(self, outcome, *, on_convert, costs=None):
        super().__init__(outcome, costs=costs)
        self._on_convert = on_convert

    async def _attempt_structured_plan(self, **kwargs):
        self._on_convert()
        return await super()._attempt_structured_plan(**kwargs)


def _track_full_stage2_writes(store: FakeStore) -> dict[str, int]:
    """Spy on ``update_plan_stage2`` so tests can prove the narrow path is used."""
    counter = {"calls": 0}
    original = store.update_plan_stage2

    def _tracked(plan_id, result):
        counter["calls"] += 1
        return original(plan_id, result)

    store.update_plan_stage2 = _tracked  # type: ignore[method-assign]
    return counter


def test_structured_post_processing_does_not_overwrite_concurrent_manual_edit(monkeypatch):
    """A concurrent manual Stage 2 edit must survive the deferred conversion.

    The edit keeps the plan athlete-visible (``ready``) but rewrites plan_text /
    stage2_status / stage2_retry_text / attempt count. The background writer must
    only touch the structured-output columns, so the manual edit is preserved.
    The full ``update_plan_stage2`` writer (which rebuilds all of those fields
    from the stale pre-conversion snapshot) must never run here.
    """
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    store = FakeStore()
    plan_id = _seed_held_plan(store)

    asyncio.run(
        approve_review_required_plan(
            plan_id=plan_id, store=store, stage2=_StructuredAutomator(_valid_outcome("# approved plan"))
        )
    )

    def _concurrent_manual_edit():
        row = store.plans[plan_id]
        row["status"] = "ready"
        row["plan_text"] = "# manually edited plan"
        row["final_plan_text"] = "# manually edited plan"
        row["stage2_status"] = "manual_stage2_pass"
        row["stage2_retry_text"] = "tweak the taper"
        row["stage2_attempt_count"] = 2

    stage2_calls = _track_full_stage2_writes(store)
    automator = _ConcurrentMutationAutomator(
        _valid_outcome("# approved plan"), on_convert=_concurrent_manual_edit
    )

    asyncio.run(
        run_structured_plan_post_processing(plan_id=plan_id, store=store, stage2=automator)
    )

    row = store.plans[plan_id]
    # The newer manual edit is fully preserved — no field regressed to the stale
    # pre-conversion snapshot.
    assert row["status"] == "ready"
    assert row["plan_text"] == "# manually edited plan"
    assert row["final_plan_text"] == "# manually edited plan"
    assert row["stage2_status"] == "manual_stage2_pass"
    assert row["stage2_retry_text"] == "tweak the taper"
    assert row["stage2_attempt_count"] == 2
    # The structured output is still persisted via the narrow writer only.
    assert row["structured_plan"] is not None
    assert row["schema_version"] == SCHEMA_VERSION
    assert stage2_calls["calls"] == 0


def test_structured_post_processing_does_not_overwrite_concurrent_reject(monkeypatch):
    """A concurrent reject/archive must not be resurrected by the conversion.

    The plan leaves the athlete-visible state mid-conversion (status flips to
    ``archived``, plan_text cleared). The deferred structured write must leave
    that newer terminal state untouched rather than re-releasing the plan.
    """
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    store = FakeStore()
    plan_id = _seed_held_plan(store)

    asyncio.run(
        approve_review_required_plan(
            plan_id=plan_id, store=store, stage2=_StructuredAutomator(_valid_outcome("# approved plan"))
        )
    )

    def _concurrent_reject():
        row = store.plans[plan_id]
        row["status"] = "archived"
        row["plan_text"] = ""
        row["final_plan_text"] = ""
        row["stage2_status"] = "admin_rejected"
        row["stage2_retry_text"] = "rejected by reviewer"

    stage2_calls = _track_full_stage2_writes(store)
    automator = _ConcurrentMutationAutomator(
        _valid_outcome("# approved plan"), on_convert=_concurrent_reject
    )

    asyncio.run(
        run_structured_plan_post_processing(plan_id=plan_id, store=store, stage2=automator)
    )

    row = store.plans[plan_id]
    # The concurrent reject/archive survives intact.
    assert row["status"] == "archived"
    assert row["plan_text"] == ""
    assert row["final_plan_text"] == ""
    assert row["stage2_status"] == "admin_rejected"
    assert row["stage2_retry_text"] == "rejected by reviewer"
    # The full Stage 2 writer was never used (it would have failed the
    # archived->ready transition or otherwise clobbered the row).
    assert stage2_calls["calls"] == 0


def test_structured_post_processing_persists_narrow_fields_without_regression(monkeypatch):
    """Structured output is persisted; every non-structured field is unchanged."""
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "1")
    store = FakeStore()
    plan_id = _seed_held_plan(store)

    asyncio.run(
        approve_review_required_plan(
            plan_id=plan_id, store=store, stage2=_StructuredAutomator(_valid_outcome("# approved plan"))
        )
    )
    # Snapshot the released row immediately after approval.
    approved = dict(store.plans[plan_id])

    stage2_calls = _track_full_stage2_writes(store)
    asyncio.run(
        run_structured_plan_post_processing(
            plan_id=plan_id, store=store, stage2=_StructuredAutomator(_valid_outcome("# approved plan"))
        )
    )

    row = store.plans[plan_id]
    # Structured output produced and persisted.
    assert row["structured_plan"] is not None
    assert row["schema_version"] == SCHEMA_VERSION
    # No regression on any lifecycle/text field.
    for field in (
        "status",
        "plan_text",
        "draft_plan_text",
        "final_plan_text",
        "stage2_status",
        "stage2_retry_text",
        "stage2_attempt_count",
    ):
        assert row[field] == approved[field], field
    # Only the narrow writer touched the row.
    assert stage2_calls["calls"] == 0


def test_admin_approve_without_env_flag_skips_structured(monkeypatch):
    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_PLAN", raising=False)
    store = FakeStore()
    plan_id = _seed_held_plan(store)
    automator = _StructuredAutomator(_valid_outcome("# approved plan"))

    detail = asyncio.run(
        approve_review_required_plan(plan_id=plan_id, store=store, stage2=automator)
    )
    # Even the background step is a no-op when the env flag is off.
    asyncio.run(
        run_structured_plan_post_processing(plan_id=plan_id, store=store, stage2=automator)
    )

    assert detail.status == "ready"
    assert detail.outputs.structured_plan is None
    assert store.plans[plan_id].get("structured_plan") is None
    assert automator.calls == []
