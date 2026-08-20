"""The generation boundary must resolve the CURRENT rehab stage and keep episodes apart.

This closes the exact gap the production handoff review named: Today resolves an
injury's live ``rehab_stage`` from recent check-ins, but plan generation used to
run off the stored intake — a different clock — so a freshly-resolved stage never
reached drill selection. These tests assert the missing hop end to end:

    stored open injury_flags row
      -> api.contracts.rehab_stage.resolve_rehab_stages          (current stage)
      -> api.services.rehab_stage_snapshot.annotate_payload...    (ephemeral stamp)
      -> fightcamp.input_parsing (parsed injury carries the stage + identity)
      -> fightcamp.rehab_protocols merge (one episode, kept atomic)
      -> fightcamp.rehab_selector                                 (stage-safe)

and, separately, that two injuries sharing a body region stay two isolated
episodes — no stage or evidence contamination between them.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from api.contracts.rehab_stage import STAGE_CALM, STAGE_RESTORE  # noqa: E402
from api.services.rehab_stage_snapshot import (  # noqa: E402
    annotate_payload_with_rehab_stage,
    resolve_open_injury_rehab_context,
)
from api.services.today_service import _guided_intake_injury_candidate  # noqa: E402
from fightcamp import rehab_protocols  # noqa: E402
from fightcamp.input_parsing import (  # noqa: E402
    _extract_guided_injuries,
    _parse_guided_injuries,
)
from fightcamp.rehab_selector import select_rehab_candidate  # noqa: E402
from tests.support import FakeStore  # noqa: E402

ATHLETE = "athlete-boundary"


def _guided(area: str, **overrides) -> dict:
    injury = {
        "area": area,
        "severity": "moderate",
        "trend": "stable",
        "injury_type": "tendon_ligament",
        "injury_subtypes": ["sprain"],
        "timeframe": "three_plus_months",
    }
    injury.update(overrides)
    return injury


def _flag_for_guided(store: FakeStore, guided: dict, **overrides) -> dict:
    """Create the injury_flags row an intake guided injury would sync to.

    Deriving body_area/description from the same candidate builder the snapshot
    uses guarantees the test exercises the real identity match, not a hand-tuned
    string.
    """
    candidate = _guided_intake_injury_candidate({**guided, "cleared": ""}, plan_id="p1")
    fields = {
        "plan_id": "p1",
        "source": "intake",
        "body_area": candidate["body_area"],
        "description": candidate["description"],
        "severity": "moderate",
        "status": "monitoring",
        "side": "left",
        "created_at": "2026-07-01T00:00:00+00:00",
        # A per-injury follow-up report resolves this episode to RESTORE.
        "latest_reported_status": "improving",
    }
    fields.update(overrides)
    return store.create_injury_flag(ATHLETE, fields)


# --------------------------------------------------------------------------- #
# The production hop: current stage, resolved server-side, stamped ephemerally
# --------------------------------------------------------------------------- #


def test_generation_stamps_the_currently_resolved_stage_not_the_intake_state():
    store = FakeStore()
    guided = _guided("Left ankle")
    # The intake itself says nothing about a rehab stage — it never did. The
    # flag, reported on again as improving, currently resolves to RESTORE.
    flag = _flag_for_guided(store, guided)

    payload = {"guided_injuries": [dict(guided)]}
    annotated = annotate_payload_with_rehab_stage(payload, store=store, athlete_id=ATHLETE)

    context = annotated["guided_injuries"][0]["rehab_generation_context"]
    assert context["rehab_stage"] == STAGE_RESTORE
    assert context["injury_id"] == flag["id"]
    assert context["episode_id"] == flag["episode_id"]
    assert context["athlete_id"] == ATHLETE
    # The original intake dict is not mutated in place.
    assert "rehab_generation_context" not in payload["guided_injuries"][0]


def test_a_flag_with_no_followup_resolves_calm_at_generation():
    store = FakeStore()
    guided = _guided("Left ankle")
    _flag_for_guided(store, guided, latest_reported_status="ongoing")

    annotated = annotate_payload_with_rehab_stage(
        {"guided_injuries": [dict(guided)]}, store=store, athlete_id=ATHLETE
    )
    assert annotated["guided_injuries"][0]["rehab_generation_context"]["rehab_stage"] == STAGE_CALM


def test_no_matching_flag_leaves_the_payload_stage_unaware():
    store = FakeStore()
    payload = {"guided_injuries": [_guided("Left ankle")]}
    annotated = annotate_payload_with_rehab_stage(payload, store=store, athlete_id=ATHLETE)
    assert "rehab_generation_context" not in annotated["guided_injuries"][0]


def test_a_raising_store_never_blocks_generation():
    class Boom(FakeStore):
        def list_injury_flags(self, *args, **kwargs):
            raise RuntimeError("db down")

    store = Boom()
    payload = {"guided_injuries": [_guided("Left ankle")]}
    annotated = annotate_payload_with_rehab_stage(payload, store=store, athlete_id=ATHLETE)
    assert "rehab_generation_context" not in annotated["guided_injuries"][0]


def test_stamped_context_reaches_parsed_injuries_through_input_parsing():
    store = FakeStore()
    guided = _guided("Left ankle")
    flag = _flag_for_guided(store, guided)
    payload = annotate_payload_with_rehab_stage(
        {"guided_injuries": [dict(guided)]},
        store=store,
        athlete_id=ATHLETE,
    )

    guided_injuries = _extract_guided_injuries(payload)
    parsed_injuries, _ = _parse_guided_injuries(guided_injuries)
    parsed = [
        entry
        for entry in parsed_injuries
        if str(entry.get("rehab_stage") or "")
    ]
    assert parsed, "the resolved stage did not survive into parsed injuries"
    entry = parsed[0]
    assert entry["rehab_stage"] == STAGE_RESTORE
    assert entry["injury_id"] == flag["id"]
    assert entry["episode_id"] == flag["episode_id"]
    assert entry["athlete_id"] == ATHLETE


# --------------------------------------------------------------------------- #
# Two injuries at one location stay two isolated episodes
# --------------------------------------------------------------------------- #


def test_two_same_region_injuries_resolve_independently():
    store = FakeStore()
    settling = _guided("Left ankle", injury_subtypes=["sprain"])
    flaring = _guided("Left ankle", injury_type="tendon", injury_subtypes=["tendinopathy"])
    settling_flag = _flag_for_guided(store, settling, latest_reported_status="improving")
    flaring_flag = _flag_for_guided(store, flaring, latest_reported_status="ongoing")

    context = resolve_open_injury_rehab_context(store, ATHLETE)
    # Two distinct episodes, each with its own stage — never merged into one.
    stages = {c["injury_id"]: c["rehab_stage"] for c in context.values()}
    assert stages[settling_flag["id"]] == STAGE_RESTORE
    assert stages[flaring_flag["id"]] == STAGE_CALM
    assert settling_flag["episode_id"] != flaring_flag["episode_id"]


def test_merge_keeps_one_episodes_context_atomic():
    """A shared-location group adopts one episode whole — no field is blended."""
    restore_entry = {
        "canonical_location": "ankle",
        "location": "ankle",
        "injury_type": "sprain",
        "rehab_type": "sprain",
        "severity": "moderate",
        "laterality": "left",
        "athlete_id": ATHLETE,
        "injury_id": "injury-restore",
        "episode_id": "episode-restore",
        "rehab_stage": STAGE_RESTORE,
        "rehab_exposures": [{"drill_id": "restore-drill"}],
    }
    calm_entry = {
        "canonical_location": "ankle",
        "location": "ankle",
        "injury_type": "tendinopathy",
        "rehab_type": "tendinopathy",
        "severity": "moderate",
        "laterality": "left",
        "athlete_id": ATHLETE,
        "injury_id": "injury-calm",
        "episode_id": "episode-calm",
        "rehab_stage": STAGE_CALM,
        "rehab_exposures": [{"drill_id": "calm-drill"}],
    }

    merged = rehab_protocols._merge_injuries_by_location([restore_entry, calm_entry])
    group = next(g for g in merged if g.get("rehab_stage"))

    # The most-protective episode (CALM) wins, and every context field belongs
    # to THAT episode. The RESTORE episode's exposures or identity must never
    # ride along with the CALM stage.
    assert group["rehab_stage"] == STAGE_CALM
    assert group["injury_id"] == "injury-calm"
    assert group["episode_id"] == "episode-calm"
    assert group["rehab_exposures"] == [{"drill_id": "calm-drill"}]


def test_merge_is_order_independent():
    def entry(injury_id, episode_id, stage, drill):
        return {
            "canonical_location": "ankle",
            "location": "ankle",
            "injury_type": "sprain",
            "rehab_type": "sprain",
            "severity": "moderate",
            "laterality": "left",
            "injury_id": injury_id,
            "episode_id": episode_id,
            "rehab_stage": stage,
            "rehab_exposures": [{"drill_id": drill}],
        }

    a = entry("i-restore", "e-restore", STAGE_RESTORE, "restore-drill")
    b = entry("i-calm", "e-calm", STAGE_CALM, "calm-drill")

    forward = next(g for g in rehab_protocols._merge_injuries_by_location([a, b]) if g.get("rehab_stage"))
    reverse = next(g for g in rehab_protocols._merge_injuries_by_location([b, a]) if g.get("rehab_stage"))

    for group in (forward, reverse):
        assert group["rehab_stage"] == STAGE_CALM
        assert group["injury_id"] == "i-calm"
        assert group["rehab_exposures"] == [{"drill_id": "calm-drill"}]


# --------------------------------------------------------------------------- #
# Stage-safe primary AND alternates
# --------------------------------------------------------------------------- #


def test_restore_rejects_advanced_drills_from_primary_and_alternates():
    """A RESTORE injury may not be handed LOAD/DYNAMIC work — as primary or swap."""
    injury = {
        "body_region": "ankle",
        "canonical_location": "ankle",
        "injury_type": "sprain",
        "side": "left",
        "severity": "moderate",
        "id": "injury-a",
        "episode_id": "episode-a",
    }
    candidates = [
        {"id": "calm-iso", "rehab_stage": "calm", "target_regions": ["ankle"], "care_pathway": "msk", "injury_type": "sprain"},
        {"id": "restore-control", "rehab_stage": "restore", "target_regions": ["ankle"], "care_pathway": "msk", "injury_type": "sprain"},
        {"id": "load-heavy", "rehab_stage": "load", "target_regions": ["ankle"], "care_pathway": "msk", "injury_type": "sprain"},
        {"id": "dynamic-plyo", "rehab_stage": "dynamic", "target_regions": ["ankle"], "care_pathway": "msk", "injury_type": "sprain"},
    ]

    result = select_rehab_candidate(
        injury=injury,
        rehab_stage=STAGE_RESTORE,
        candidates=candidates,
        available_equipment=None,
    )

    ranked_ids = [str(drill.get("id")) for drill in result.ranked_drills]
    # Neither the chosen drill nor any alternate is above the live stage.
    assert "load-heavy" not in ranked_ids
    assert "dynamic-plyo" not in ranked_ids
    # The stage-exact drill leads; the more-protective CALM drill is a valid swap.
    assert result.selected_drill_id == "restore-control"
    assert "calm-iso" in ranked_ids
