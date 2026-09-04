"""Frontend/persisted sport tokens must keep identity across planning families."""
import logging
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from api import nutrition_workspace
from fightcamp import conditioning, plan_pipeline_runtime as runtime
from fightcamp.athlete_model import _build_athlete_model
from fightcamp.input_parsing import PlanInput
from fightcamp.sports import SUPPORTED_SPORTS, normalize_sport, planning_format
from fightcamp.stage2_planning_brief import _build_sport_load_profile

CASES = [
    ("boxing", "boxing", "boxing"), ("boxer", "boxing", "boxing"),
    ("kickboxing", "kickboxing", "kickboxing"), ("kickboxer", "kickboxing", "kickboxing"),
    ("muay_thai", "muay_thai", "muay_thai"), ("muay thai", "muay_thai", "muay_thai"),
    ("muaythai", "muay_thai", "muay_thai"), ("mma", "mma", "mma"),
    ("wrestling", "wrestling", "mma"), ("wrestler", "wrestling", "mma"),
    ("bjj", "bjj", "mma"), ("jiu jitsu", "bjj", "mma"),
    ("grappler", "grappling", "mma"), ("grappling", "grappling", "mma"),
    ("karate", "karate", "kickboxing"),
]

@pytest.mark.parametrize("token,identity,family", CASES)
def test_sport_identity_and_planning_family(token, identity, family):
    assert normalize_sport(token) == identity
    assert planning_format(token) == family
    assert planning_format(token.upper()) == family
    if identity in {"kickboxing", "muay_thai"}:
        assert planning_format(token) != "mma"


def test_frontend_sport_vocabulary_is_covered():
    source = (Path(__file__).parents[1] / "web/lib/intake-options.ts").read_text()
    options = source.split("export const TECHNICAL_STYLE_OPTIONS:")[1].split("];", 1)[0]
    tokens = set(re.findall(r'value: "([^"]+)"', options))
    assert tokens == set(SUPPORTED_SPORTS)
    assert all(planning_format(token, fallback=None) for token in tokens)


@pytest.mark.parametrize("token,identity,family", CASES)
def test_persisted_intake_runtime_phase_and_athlete_identity(token, identity, family):
    # This is the field envelope produced by PlanRequest.to_payload and replayed
    # from stored intakes. Exercise parsing and the real phase calculator.
    plan_input = PlanInput.from_payload({"data": {"fields": [
        {"label": "Fighting Style (Technical)", "value": [token]},
        {"label": "Training Availability", "value": ["Monday", "Wednesday", "Friday"]},
        {"label": "Weekly Training Frequency", "value": 3},
    ]}})
    with patch.object(runtime, "calculate_phase_weeks", wraps=runtime.calculate_phase_weeks) as phases:
        context = runtime.build_runtime_context(plan_input=plan_input, random_seed=7, logger=logging.getLogger(__name__))
    assert phases.call_args.args[1] == family
    assert context.mapped_format == family
    assert context.canonical_sport == identity
    assert context.training_context.style_technical == [identity]
    model = _build_athlete_model(training_context=context.training_context, sport=family,
        record="0-0", rounds_format="3x3", camp_length_weeks=context.camp_len, short_notice=False)
    assert model["sport"] == identity
    assert model["technical_styles"] == [identity]
    if identity in {"wrestling", "bjj"}:
        assert _build_sport_load_profile(model)["key"] == identity


@pytest.mark.parametrize("token,identity,family", CASES)
def test_nutrition_phase_uses_shared_family(token, identity, family):
    with patch.object(nutrition_workspace, "calculate_phase_weeks", wraps=nutrition_workspace.calculate_phase_weeks) as phases:
        nutrition_workspace._resolve_effective_phase(phase_override=None, days_until_fight=40,
            current_weight_kg=70, target_weight_kg=70, fatigue_level="low", technical_style=[token],
            tactical_style=[], professional_status="amateur", mindset_challenges="")
    assert phases.call_args.args[1] == family


def test_unknown_fallback_is_logged_without_changing_identity(caplog):
    with caplog.at_level(logging.WARNING):
        assert normalize_sport("Unknown Sport") == "unknown_sport"
        assert planning_format("Unknown Sport") == "mma"
        assert planning_format("Unknown Sport", fallback=None) is None
        assert planning_format(None) == "mma"
    assert "unsupported_sport_planning_fallback" in caplog.text


@pytest.mark.parametrize("sport", ["wrestling", "bjj", "muay_thai"])
def test_footwork_identity_takes_precedence_over_reused_format(sport):
    flags = {"sport": sport, "fight_format": "mma", "phase": "SPP", "days_until_fight": 40,
             "equipment": ["bodyweight", "mat", "partner"], "style_tactical": [], "weaknesses": ["footwork"]}
    actual = conditioning.select_technical_footwork_candidates(flags, set(), [])
    expected = conditioning.select_technical_footwork_candidates({**flags, "fight_format": sport}, set(), [])
    assert actual == expected

@pytest.mark.parametrize("sport", SUPPORTED_SPORTS)
def test_conditioning_uses_shared_planning_family(sport):
    with patch.object(conditioning, "_normalize_fight_format", wraps=conditioning._normalize_fight_format) as formats:
        conditioning.generate_conditioning_block({
            "style_technical": [sport], "sport": sport, "phase": "GPP", "fatigue": "low",
            "style_tactical": [], "key_goals": [], "weaknesses": [], "injuries": [],
            "equipment": ["bodyweight"], "training_frequency": 3, "days_until_fight": 40,
        })
    assert formats.call_args_list[0].args == (planning_format(sport),)


@pytest.mark.parametrize("sport", SUPPORTED_SPORTS)
def test_saved_api_request_round_trip_keeps_sport(sport):
    from api.models import PlanRequest
    from support import _build_request

    request = _build_request({"athlete": {"technical_style": [sport]}, "injuries": ""})
    restored = PlanRequest.model_validate_json(request.model_dump_json())
    assert restored.athlete.technical_style == [sport]
    parsed = PlanInput.from_payload(restored.to_payload())
    assert parsed.tech_styles == [sport]
    assert planning_format(parsed.tech_styles[0]) == planning_format(sport)
