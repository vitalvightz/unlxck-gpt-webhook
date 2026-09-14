from types import SimpleNamespace

from fightcamp import plan_pipeline_blocks
from fightcamp.plan_pipeline_blocks import _is_rotational_power_anchor
from fightcamp.strength import (
    ROTATIONAL_POWER_COVERAGE_BOOST,
    _rotational_power_coverage_adjustment,
)
from fightcamp.strength_session_quality import classify_strength_item, missing_base_categories


def test_bodyweight_jump_is_power_not_loaded_strength():
    profile = classify_strength_item(
        {
            "name": "Jump Squat",
            "method": "power",
            "equipment": "bodyweight",
            "tags": ["explosive", "mech_lower_jump", "triple_extension"],
        }
    )

    assert profile["quality_class"] == "anchor_power"
    assert "lower_body_power" in profile["base_categories"]
    assert "lower_body_jump" in profile["base_categories"]
    assert "lower_body_explosive_anchor" in profile["base_categories"]
    assert "lower_body_loaded" not in profile["base_categories"]


def test_single_leg_hyphen_counts_as_unilateral():
    profile = classify_strength_item(
        {
            "name": "Single-Leg Box Jump",
            "method": "plyometric",
            "equipment": "bodyweight",
            "tags": ["plyometric", "mech_lower_jump"],
        }
    )

    assert "unilateral" in profile["base_categories"]


def test_rotational_power_is_not_demoted_to_support():
    profile = classify_strength_item(
        {
            "name": "Woodchopper (Cable)",
            "method": "power",
            "equipment": "cable",
            "tags": ["core", "explosive", "rotational", "mech_trunk_rotation"],
        }
    )

    assert profile["quality_class"] == "anchor_power"
    assert "rotational_power" in profile["base_categories"]


def test_lower_body_explosive_anchor_is_required_only_when_requested():
    exercises = [
        {"name": "Back Squat", "equipment": "barbell", "tags": ["quad_dominant"]},
        {"name": "Bench Press", "equipment": "barbell", "tags": ["upper_body"]},
        {"name": "Split Squat", "equipment": "dumbbell", "tags": ["unilateral"]},
    ]

    assert "lower_body_explosive_anchor" not in missing_base_categories(exercises)
    assert "lower_body_explosive_anchor" in missing_base_categories(
        exercises,
        require_lower_body_explosive_anchor=True,
    )


def test_olympic_lift_satisfies_lower_body_explosive_anchor():
    exercise = {
        "name": "Hang Power Clean",
        "movement": "olympic",
        "method": "power",
        "equipment": "barbell",
        "tags": ["explosive", "triple_extension", "mech_ballistic", "mech_lower_hip_hinge"],
    }
    profile = classify_strength_item(exercise)

    assert "lower_body_olympic" in profile["base_categories"]
    assert "lower_body_explosive_anchor" in profile["base_categories"]
    assert "lower_body_explosive_anchor" not in missing_base_categories(
        [exercise],
        require_lower_body_explosive_anchor=True,
    )


def test_kettlebell_swing_satisfies_lower_body_explosive_anchor():
    exercise = {
        "name": "Kettlebell Swing",
        "movement": "hinge",
        "method": "power",
        "equipment": "kettlebell",
        "tags": ["explosive", "rate_of_force", "mech_ballistic", "mech_lower_hip_hinge"],
    }
    profile = classify_strength_item(exercise)

    assert "lower_body_hip_ballistic" in profile["base_categories"]
    assert "lower_body_explosive_anchor" in profile["base_categories"]
    assert "lower_body_explosive_anchor" not in missing_base_categories(
        [exercise],
        require_lower_body_explosive_anchor=True,
    )


def test_upper_body_plyometric_does_not_satisfy_lower_body_explosive_anchor():
    profile = classify_strength_item(
        {
            "name": "Clap Push-Up",
            "movement": "horizontal_push",
            "method": "plyometric",
            "equipment": "bodyweight",
            "tags": ["explosive", "mech_upper_press", "mech_ballistic"],
        }
    )

    assert "upper_body_ballistic" in profile["base_categories"]
    assert "lower_body_explosive_anchor" not in profile["base_categories"]


def _rotational_profile() -> dict:
    return classify_strength_item(
        {
            "name": "Med-Ball Rotational Throw",
            "method": "power",
            "equipment": "medicine_ball",
            "tags": ["explosive", "rotational", "mech_trunk_rotation"],
        }
    )


def test_rotational_coverage_boost_fires_only_on_an_open_camp_gap():
    profile = _rotational_profile()

    gap_adjustment, gap_codes = _rotational_power_coverage_adjustment(
        profile, active=True, restricted=False
    )
    covered_adjustment, covered_codes = _rotational_power_coverage_adjustment(
        profile, active=False, restricted=False
    )

    assert gap_adjustment == ROTATIONAL_POWER_COVERAGE_BOOST
    assert gap_codes == ["rotational_power_camp_coverage_boost"]
    assert covered_adjustment == 0.0
    assert covered_codes == []


def test_rotational_coverage_boost_skips_restricted_and_non_rotational_candidates():
    restricted_adjustment, _ = _rotational_power_coverage_adjustment(
        _rotational_profile(), active=True, restricted=True
    )
    jump_profile = classify_strength_item(
        {
            "name": "Jump Squat",
            "method": "power",
            "equipment": "bodyweight",
            "tags": ["explosive", "mech_lower_jump", "triple_extension"],
        }
    )
    non_rotational_adjustment, _ = _rotational_power_coverage_adjustment(
        jump_profile, active=True, restricted=False
    )

    assert restricted_adjustment == 0.0
    assert non_rotational_adjustment == 0.0


def _rotational_support_item() -> dict:
    return {
        "name": "Band Anti-Rotation Press",
        "method": "power",
        "equipment": "band",
        "tags": ["explosive", "rotational", "mech_trunk_rotation"],
        # Authored governance: present for trunk support, not as a power anchor.
        "support_only": True,
    }


def _rotational_anchor_item() -> dict:
    return {
        "name": "Med-Ball Rotational Throw",
        "method": "power",
        "equipment": "medicine_ball",
        "tags": ["explosive", "rotational", "mech_trunk_rotation"],
    }


def test_rotational_support_item_does_not_count_as_camp_exposure():
    support_profile = classify_strength_item(_rotational_support_item())

    # The base category survives governance, so category alone is not enough.
    assert "rotational_power" in support_profile["base_categories"]
    assert not support_profile["anchor_capable"]
    assert not _is_rotational_power_anchor(_rotational_support_item())
    assert _is_rotational_power_anchor(_rotational_anchor_item())


def test_camp_gap_stays_open_until_a_rotational_anchor_is_selected(monkeypatch):
    phase_blocks = {
        "GPP": {"exercises": [_rotational_support_item()]},
        "SPP": {"exercises": [_rotational_anchor_item()]},
        "TAPER": {"exercises": []},
    }
    seen_gap_flags: dict[str, bool] = {}

    def fake_generate_strength_block(*, flags, weaknesses=None):
        phase = flags["phase"]
        seen_gap_flags[phase] = bool(flags.get("rotational_power_camp_gap"))
        return phase_blocks[phase]

    monkeypatch.setattr(
        plan_pipeline_blocks, "generate_strength_block", fake_generate_strength_block
    )
    context = SimpleNamespace(
        training_context=SimpleNamespace(to_flags=lambda: {}, weaknesses=[]),
        random_seed=None,
        selection_ignore_restrictions=False,
        plan_input=SimpleNamespace(restrictions=None),
        phase_active=lambda phase: True,
    )

    plan_pipeline_blocks._generate_strength_blocks(context)

    # A governed rotational support item in GPP must not close the gap for SPP;
    # the real rotational anchor selected in SPP closes it for TAPER.
    assert seen_gap_flags == {"GPP": True, "SPP": True, "TAPER": False}
