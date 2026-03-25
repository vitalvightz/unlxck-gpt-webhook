from fightcamp.cluster_coverage import (
    active_cluster_ids,
    get_cluster_coverage_manifest,
    validate_cluster_manifest_coverage,
)


def test_active_cluster_ids_match_boxing_profiles():
    cluster_ids = active_cluster_ids(
        sport="boxing",
        goal_keys=["repeatability_endurance"],
        weakness_keys=["gas_tank"],
        style_keys=["pressure_fighter"],
    )

    assert cluster_ids == ["boxing__repeatability_endurance__gas_tank__pressure_fighter"]


def test_validate_cluster_manifest_coverage_passes_current_banks():
    assert validate_cluster_manifest_coverage() == []


def test_manifest_keeps_rehab_and_style_completion_contracts():
    rows = {row["cluster_id"]: row for row in get_cluster_coverage_manifest()}

    rehab_row = rows["boxing__rehab_return__trunk_rotation_return"]
    assert rehab_row["cluster_type"] == "rehab_return"
    assert set(rehab_row["mandatory_categories"]) == {"rehab_progression", "return_bridge"}
    assert rehab_row["forbidden_categories"] == ["generic_fight_pace"]
    assert rehab_row["rehab_required"] is True

    mma_row = rows["mma__style_completion__coordination_proprioception__hybrid"]
    assert mma_row["cluster_type"] == "style_completion"
    assert set(mma_row["mandatory_categories"]) == {"style_specific", "coordination_style"}
    assert mma_row["preferred_categories"] == ["conditioning"]

    assert rows["muay_thai__style_completion__repeatability_endurance__clinch_fighter"]["sports"] == ["muay_thai"]
    assert rows["wrestling__style_completion__gas_tank__grappler"]["sports"] == ["wrestling"]
    assert rows["bjj__style_completion__gas_tank__grappler"]["sports"] == ["bjj"]