from fightcamp.priority_clarification_tags import derive_clarification_tags


def test_empty_missing_malformed_returns_empty():
    assert derive_clarification_tags(None) == []
    assert derive_clarification_tags([]) == []
    assert derive_clarification_tags(["bad"]) == []
    assert derive_clarification_tags([{"tag": "", "detail": ""}]) == []


def test_conditioning_late_round_fatigue_maps_correctly():
    assert derive_clarification_tags([{"tag": "conditioning", "detail": "Late-round fatigue"}]) == [
        "glycolytic",
        "conditioning",
        "work_capacity",
        "mental_toughness",
    ]


def test_conditioning_recovery_between_bursts_maps_correctly():
    assert derive_clarification_tags([{"tag": "conditioning", "detail": "Recovery between bursts"}]) == [
        "anaerobic_alactic",
        "aerobic",
        "recovery",
        "cns_freshness",
    ]


def test_power_drops_when_tired_maps_correctly():
    assert derive_clarification_tags([{"tag": "power", "detail": "Power drops when tired"}]) == [
        "explosive",
        "rate_of_force",
        "work_capacity",
        "conditioning",
        "anaerobic_alactic",
    ]


def test_strength_posterior_chain_maps_correctly():
    assert derive_clarification_tags([{"tag": "strength", "detail": "Posterior-chain strength"}]) == [
        "posterior_chain",
        "hip_dominant",
        "hamstring",
        "deadlift",
    ]


def test_strength_lower_body_maps_correctly():
    assert derive_clarification_tags([{"tag": "strength", "detail": "Lower-body strength"}]) == [
        "posterior_chain",
        "quad_dominant",
        "hip_dominant",
        "deadlift",
        "compound",
    ]


def test_mobility_stiffness_under_fatigue_maps_correctly():
    assert derive_clarification_tags([{"tag": "mobility", "detail": "Movement stiffness under fatigue"}]) == [
        "mobility",
        "movement_quality",
        "range",
        "cns_freshness",
    ]


def test_speed_reaction_maps_correctly():
    assert derive_clarification_tags([{"tag": "speed", "detail": "Reaction speed"}]) == [
        "reactive",
        "visual_processing",
        "coordination",
        "decision_speed",
    ]


def test_multiple_details_dedupe_and_preserve_order():
    assert derive_clarification_tags(
        [
            {"tag": "conditioning", "detail": "Late-round fatigue"},
            {"tag": "conditioning", "detail": "Repeated hard efforts"},
        ]
    ) == ["glycolytic", "conditioning", "work_capacity", "mental_toughness"]


def test_generic_fallback_uses_entry_tag():
    assert derive_clarification_tags([{"tag": "strength", "detail": "I want to improve it overall"}]) == [
        "strength",
        "compound",
        "posterior_chain",
        "core",
    ]


def test_unknown_detail_returns_empty():
    assert derive_clarification_tags([{"tag": "conditioning", "detail": "Some random text"}]) == []


def test_normalization_variants_map_to_same_result():
    expected = ["glycolytic", "conditioning", "work_capacity", "mental_toughness"]
    variants = ["Late-round fatigue", "late round fatigue", "late_round_fatigue", "Late Round Fatigue"]

    for variant in variants:
        assert derive_clarification_tags([{"tag": "conditioning", "detail": variant}]) == expected
