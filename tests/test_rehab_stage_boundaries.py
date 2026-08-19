"""PR2 boundaries: the stage is resolved and exposed, and nothing else moved.

PR2 separates rehabilitation stage from camp phase. It deliberately does NOT
migrate the rehab bank (PR3) or make the stage authoritative for drill selection
(PR4). These tests pin that boundary from both sides:

* the new metadata does not reach exercise selection, and
* rehab selection still works while PR1's ``rehab_stage`` fields are ``null``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from api.contracts import rehab_stage as stage_module
from api.contracts.rehab_stage import resolve_rehab_stage, resolve_rehab_stages
from api.models import InjuryFlagRecord
from api.services import today_service as today_service_module
from api.services.today_service import build_today_command_view
from fightcamp import rehab_protocols
from fightcamp.config import DATA_DIR
from fightcamp.rehab_protocols import generate_rehab_protocols, get_rehab_bank
from fightcamp.rehab_schema import CARE_TYPE_MUSCULOSKELETAL, REHAB_STAGES
from tests.support import FakeStore

ATHLETE = "athlete-1"
PLAN = "11111111-1111-1111-1111-111111111111"
PHASES = ("GPP", "SPP", "TAPER")


def _store_with_plan() -> FakeStore:
    store = FakeStore()
    store.plans[PLAN] = {
        "id": PLAN,
        "athlete_id": ATHLETE,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    return store


# ---------------------------------------------------------------------------
# The bank is untouched: PR3 still owns the content migration
# ---------------------------------------------------------------------------


def test_pr1_drill_stage_metadata_is_still_unmigrated():
    """PR2 must not populate what PR3 owns."""
    bank = json.loads((DATA_DIR / "rehab_bank.json").read_text(encoding="utf-8"))
    msk_drills = [
        drill
        for entry in bank
        for drill in entry.get("drills", [])
        if "rehab_stage" in drill
    ]
    assert msk_drills, "expected PR1's musculoskeletal drills to carry the field"
    assert all(drill["rehab_stage"] is None for drill in msk_drills)


def test_rehab_selection_still_works_with_null_drill_stages():
    """A null ``rehab_stage`` must not filter a drill out of selection."""
    assert all(
        drill.get("rehab_stage") is None
        for entry in get_rehab_bank()
        for drill in entry.get("drills", [])
        if "rehab_stage" in drill
    )
    for phase in PHASES:
        text, _seen = generate_rehab_protocols(
            injury_string="ankle sprain",
            exercise_data=[],
            current_phase=phase,
            parsed_entries=[
                {"canonical_location": "ankle", "rehab_type": "sprain", "severity": "moderate"}
            ],
        )
        assert "Ankle" in text
        assert "•" in text, f"no drills selected during {phase}"


@pytest.mark.parametrize("phase", PHASES)
def test_rehab_output_is_unchanged_by_the_new_resolver(phase):
    """Selection reads no stage metadata, so it cannot have moved."""
    kwargs = {
        "injury_string": "ankle sprain",
        "exercise_data": [],
        "current_phase": phase,
        "parsed_entries": [
            {"canonical_location": "ankle", "rehab_type": "sprain", "severity": "moderate"}
        ],
    }
    first, _ = generate_rehab_protocols(**kwargs)
    second, _ = generate_rehab_protocols(**kwargs)
    assert first == second
    assert "calm" not in first.lower().split()
    assert "restore stage" not in first.lower()


def test_rehab_selection_does_not_call_the_stage_resolver(monkeypatch):
    """The hard proof that PR4's wiring has not leaked into PR2."""

    def _explode(*_args, **_kwargs):  # pragma: no cover - only runs on regression
        raise AssertionError("rehab selection must not resolve a rehab stage in PR2")

    monkeypatch.setattr(stage_module, "resolve_rehab_stage", _explode)
    monkeypatch.setattr(stage_module, "resolve_rehab_stages", _explode)

    text, _seen = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[{"canonical_location": "ankle", "rehab_type": "sprain"}],
    )
    assert text


def test_rehab_protocols_does_not_import_the_stage_resolver():
    """Selection and staging stay in separate layers."""
    source = (
        __import__("pathlib").Path(rehab_protocols.__file__).read_text(encoding="utf-8")
    )
    assert "resolve_rehab_stage" not in source


# ---------------------------------------------------------------------------
# Camp phase is no longer walked as a rehab ladder
# ---------------------------------------------------------------------------


def test_the_phase_walking_helper_is_gone():
    """``combine_three_phase_drills`` mapped the camp arrow onto a rehab ladder."""
    assert not hasattr(rehab_protocols, "combine_three_phase_drills")


def test_phase_progression_is_still_a_selection_key():
    """Removing the conflation must not remove phase-based selection itself."""
    entries = [entry for entry in get_rehab_bank() if entry.get("phase_progression")]
    assert entries
    assert rehab_protocols._entry_phases(entries[0])


@pytest.mark.parametrize("phase", PHASES)
def test_phase_specific_rehab_notes_still_render(phase):
    text, _seen = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=[],
        current_phase=phase,
        parsed_entries=[{"canonical_location": "ankle", "rehab_type": "sprain"}],
    )
    assert "Why today:" in text


def test_sparring_day_volume_ceiling_is_unchanged():
    text, _seen = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[{"canonical_location": "ankle", "rehab_type": "sprain"}],
        day_type="sparring",
    )
    assert text.count("  • ") == 1


def test_high_severity_filtering_is_unchanged():
    text, _seen = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[
            {"canonical_location": "ankle", "rehab_type": "sprain", "severity": "high"}
        ],
    )
    assert "pogo" not in text.lower()
    assert "depth jump" not in text.lower()


def test_red_flag_block_is_unchanged():
    text, _seen = generate_rehab_protocols(
        injury_string="suspected fracture in left ankle",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[
            {
                "canonical_location": "ankle",
                "injury_type": "fracture",
                "flags": ["urgent", "structural_red_flag"],
            }
        ],
    )
    assert "Red Flag Detected" in text
    assert "cleared by a clinician" in text


def test_surface_injuries_still_get_wound_care_not_loading_rehab():
    text, _seen = generate_rehab_protocols(
        injury_string="cut on left eyebrow",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[{"canonical_location": "face", "rehab_type": "cut"}],
    )
    assert "Skin/surface injury" in text
    assert "  • " not in text


# ---------------------------------------------------------------------------
# Exposure: the stage reaches Today without changing anything else
# ---------------------------------------------------------------------------


def test_open_injuries_are_stamped_with_a_resolved_stage():
    store = _store_with_plan()
    store.create_injury_flag(
        ATHLETE, {"body_area": "left ankle", "description": "ankle sprain", "status": "open"}
    )
    view = build_today_command_view(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
        now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
    )
    assert view is not None

    stamped = today_service_module._with_rehab_stage(
        store.list_injury_flags(ATHLETE), store=store, athlete_id=ATHLETE
    )
    assert stamped
    assert stamped[0]["rehab_stage"] in (*REHAB_STAGES, None)
    assert stamped[0]["rehab_care_pathway"] == CARE_TYPE_MUSCULOSKELETAL
    assert isinstance(stamped[0]["rehab_stage_reasons"], list)


def test_a_new_injury_is_stamped_calm_whatever_the_plan_phase():
    store = _store_with_plan()
    store.create_injury_flag(
        ATHLETE, {"body_area": "left ankle", "description": "ankle sprain", "status": "open"}
    )
    stamped = today_service_module._with_rehab_stage(
        store.list_injury_flags(ATHLETE), store=store, athlete_id=ATHLETE
    )
    assert stamped[0]["rehab_stage"] == "calm"


def test_stage_enrichment_degrades_rather_than_failing_the_day(monkeypatch):
    store = _store_with_plan()
    store.create_injury_flag(
        ATHLETE, {"body_area": "left ankle", "description": "ankle sprain", "status": "open"}
    )

    def _explode(*_args, **_kwargs):
        raise RuntimeError("resolver unavailable")

    monkeypatch.setattr(today_service_module, "resolve_rehab_stages", _explode)
    stamped = today_service_module._with_rehab_stage(
        store.list_injury_flags(ATHLETE), store=store, athlete_id=ATHLETE
    )
    assert stamped and "rehab_stage" not in stamped[0]


def test_stage_enrichment_survives_a_failing_history_read():
    class BrokenStore(FakeStore):
        def list_today_checkins(self, athlete_id, *, limit=14):
            raise RuntimeError("history unavailable")

    store = BrokenStore()
    store.plans[PLAN] = {"id": PLAN, "athlete_id": ATHLETE, "status": "ready"}
    store.create_injury_flag(
        ATHLETE, {"body_area": "left ankle", "description": "ankle sprain", "status": "open"}
    )
    stamped = today_service_module._with_rehab_stage(
        store.list_injury_flags(ATHLETE), store=store, athlete_id=ATHLETE
    )
    # A failed read is not tolerance: the injury falls back to the safest stage.
    assert stamped[0]["rehab_stage"] == "calm"


def test_empty_injury_list_is_a_no_op():
    store = _store_with_plan()
    assert today_service_module._with_rehab_stage([], store=store, athlete_id=ATHLETE) == []


# ---------------------------------------------------------------------------
# The API model binds to the canonical enum
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", REHAB_STAGES)
def test_every_canonical_stage_is_accepted_by_the_api_model(stage):
    record = InjuryFlagRecord(
        id="1", athlete_id=ATHLETE, description="ankle sprain", rehab_stage=stage
    )
    assert record.rehab_stage == stage


def test_the_api_model_rejects_a_stage_outside_the_canonical_enum():
    with pytest.raises(ValueError):
        InjuryFlagRecord(
            id="1", athlete_id=ATHLETE, description="ankle sprain", rehab_stage="peaking"
        )


def test_the_api_model_defaults_to_no_stage():
    record = InjuryFlagRecord(id="1", athlete_id=ATHLETE, description="ankle sprain")
    assert record.rehab_stage is None
    assert record.rehab_care_pathway is None
    assert record.rehab_stage_reasons == []


def test_there_is_exactly_one_stage_enum_in_the_codebase():
    """A second ladder would be the bug this whole PR exists to prevent."""
    from api import models

    assert stage_module.REHAB_STAGES is REHAB_STAGES
    assert set(models.RehabStage.__args__) == set(REHAB_STAGES)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Public API shape
# ---------------------------------------------------------------------------


def test_the_resolver_is_exported_from_the_contracts_package():
    from api import contracts

    assert contracts.resolve_rehab_stage is resolve_rehab_stage
    assert contracts.resolve_rehab_stages is resolve_rehab_stages
    assert contracts.REHAB_STAGES is REHAB_STAGES
