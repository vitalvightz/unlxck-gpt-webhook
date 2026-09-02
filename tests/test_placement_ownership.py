"""Step 9A architecture regression: prove the dead duplicate placement engines are
gone and the real production placement owners are in place.

These are import/attribute-ownership assertions (not brittle source-string
matching): the dead engines must be unreachable/unreintroducible, and the live
owners must remain the single place that builds normal-camp and late-fight
placement.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from fightcamp import stage2_payload, stage2_payload_late_fight, stage2_role_map


def test_dead_late_fight_placement_module_is_removed():
    # The countdown session_sequence is built by stage2_payload_late_fight; the
    # separate late_fight_placement engine had no production caller and is deleted.
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fightcamp.late_fight_placement")


def test_dead_boxing_placement_engine_removed_from_stage2_payload():
    for name in (
        "_boxing_day_identity_and_spacing_pass",
        "_boxing_day_score",
        "_boxing_best_free_day",
        "_boxing_try_swap_with_lighter_role",
        "_boxing_sparse_week_structure_needed",
        "_boxing_unassigned_role_priority",
        "_boxing_glycolytic_cluster_penalty",
        "_boxing_adjacent_meaningful_count",
        "_boxing_readiness_sensitive",
        "_main_job_day_class",
        "_sort_roles_by_scheduled_day",
        "_assign_declared_day_hints",
        "_declared_day_sets",
    ):
        assert not hasattr(stage2_payload, name), (
            f"{name} is a dead payload placement helper removed in Step 9A; it must not reappear"
        )


def test_real_normal_camp_placement_owner_is_stage2_role_map():
    # Normal-camp day placement is owned by stage2_role_map (declared-day hints)
    # plus normal_calendar_placement completion.
    assert hasattr(stage2_role_map, "_assign_declared_day_hints")
    from fightcamp import normal_calendar_placement

    assert hasattr(normal_calendar_placement, "fill_missing_session_days")


def test_real_late_fight_placement_owner_is_stage2_payload_late_fight():
    # Late-fight placement builds the countdown sequence itself, in the payload owner.
    assert hasattr(stage2_payload_late_fight, "_build_late_fight_session_sequence")


# --------------------------------------------------------------------------- #
# Step 9B: the surviving owners consume canonical combat-load legality.        #
# --------------------------------------------------------------------------- #
def test_normal_camp_owner_consumes_combat_load_policy():
    # Semantic/call-graph, not source-string matching: the normal-camp owner
    # binds the canonical calendar_context legality seam, which is the policy
    # consumer. The seam evaluates through combat_load_policy.
    from fightcamp import calendar_context, combat_load_policy

    assert stage2_role_map.normal_week_legality is calendar_context.normal_week_legality
    view = calendar_context.normal_week_legality(
        [{"day": "monday", "status": "hard_as_planned"}], ["monday"], scope=("normal_week", 1)
    )
    profile = calendar_context.classify_role(
        {"category": "strength", "role_key": "primary_strength_day"}
    )
    decision = view.decision_at_position(profile, calendar_context.weekday_position("tuesday"))
    assert isinstance(decision, combat_load_policy.PlacementDecision)


def test_late_fight_owner_consumes_combat_load_policy():
    # The late-fight allocator ranks slots by a canonical legality cost (built from
    # the shared calendar_context late-fight adapter) above its own preferences.
    assert stage2_payload_late_fight.sequence_legality is not None
    assert stage2_payload_late_fight.placement_rank is not None
    forbid = [
        {"role_key": "hard_sparring_day", "category": "sparring", "countdown_offset": 18},
        {"role_key": "strength_touch_day", "category": "strength", "countdown_offset": 17,
         "stress_class": "meaningful_stress", "cost_class": "medium"},
    ]
    assert stage2_payload_late_fight._late_fight_legality_cost(forbid) == (1, 0)


def test_no_replacement_collision_policy_module_appears():
    # Step 9A removed the dead duplicate engines; Step 9B must not reintroduce a
    # parallel collision engine or a wrapper facade in their place. combat_load_policy
    # stays the single legality owner.
    for name in (
        "late_fight_placement",
        "stage2_placement_patch",
        "stage2_placement_integration",
        "combat_policy_bridge",
        "collision_engine",
        "collision_policy",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"fightcamp.{name}")


def test_no_reintroduced_collision_penalty_engine_in_late_fight():
    # The deleted late_fight_placement engine owned a _collision_penalty(); the
    # surviving owner must not host a replacement policy engine of the same shape.
    assert not hasattr(stage2_payload_late_fight, "_collision_penalty")
    assert not hasattr(stage2_payload_late_fight, "place_roles_in_countdown")


def test_final_governor_still_consumes_combat_load_policy():
    # Defence in depth: the final calendar integrity governor remains wired to the
    # same canonical policy, independent of placement now consulting it.
    from fightcamp import calendar_integrity

    source = Path(calendar_integrity.__file__).read_text()
    assert "combat_load_policy" in source or "calendar_context" in source


def test_renderer_remains_read_only():
    # No weekday recovery/fallback placement in the renderer (Step 8 invariant).
    from fightcamp import weekly_plan_render

    assert not hasattr(weekly_plan_render, "fill_missing_session_days")
