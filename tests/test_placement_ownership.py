"""Step 9A architecture regression: prove the dead duplicate placement engines are
gone and the real production placement owners are in place.

These are import/attribute-ownership assertions (not brittle source-string
matching): the dead engines must be unreachable/unreintroducible, and the live
owners must remain the single place that builds normal-camp and late-fight
placement.
"""
from __future__ import annotations

import importlib

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
