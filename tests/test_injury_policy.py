import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_formatting import parse_injuries_and_restrictions
from fightcamp.injury_policy import compile_injury_policy, evaluate_injury_policy


def test_guided_injury_caution_parses_into_case_and_limit_rule():
    text = (
        "Hip / groin - mild, improving, can train fully. "
        "Avoid: sprinting. "
        "Caution: deep hip flexion. "
        "Notes: feels better but still bites at the end range."
    )

    injuries, restrictions = parse_injuries_and_restrictions(text)

    assert len(injuries) == 1
    assert injuries[0]["aggravating_movements"] == ["sprinting"]
    assert injuries[0]["cautious_movements"] == ["deep hip flexion"]
    assert any(rule["strength"] == "avoid" for rule in restrictions)
    assert any(rule["strength"] == "limit" for rule in restrictions)

    policy = compile_injury_policy(parsed_injuries=injuries, restrictions=restrictions)
    assert len(policy.cases) == 1
    case = policy.cases[0]
    assert case.trend == "improving"
    assert case.functional_impact == "can_train_fully"
    assert case.protection_level == 0
    assert any(rule.source == "explicit_aggravator" for rule in policy.movement_rules)
    assert any(rule.source == "explicit_caution" for rule in policy.movement_rules)


def test_explicit_aggravator_blocks_and_caution_penalizes():
    text = (
        "Shoulder - moderate, stable, can train with modifications. "
        "Avoid: overhead pressing. "
        "Caution: bench press."
    )
    injuries, restrictions = parse_injuries_and_restrictions(text)
    policy = compile_injury_policy(parsed_injuries=injuries, restrictions=restrictions)

    blocked = evaluate_injury_policy(
        policy=policy,
        text="Barbell Overhead Press",
        tags=["overhead", "press_heavy"],
    )
    assert blocked["action"] == "exclude"
    assert any(match["source"] == "explicit_aggravator" for match in blocked["matched_rules"])

    cautious = evaluate_injury_policy(
        policy=policy,
        text="Bench Press",
        tags=["upper_push"],
    )
    assert cautious["action"] == "modify"
    assert cautious["score_penalty"] == -0.6
    assert any(match["source"] == "explicit_caution" for match in cautious["matched_rules"])


def test_worsening_key_movement_loss_escalates_return_stage():
    text = (
        "Knee - severe, worsening, cannot do key movements properly. "
        "Avoid: jumping, lateral cutting."
    )
    injuries, restrictions = parse_injuries_and_restrictions(text)
    policy = compile_injury_policy(parsed_injuries=injuries, restrictions=restrictions)

    assert policy.cases[0].protection_level == 3
    assert policy.rehab_directives[0].return_stage == "protect"
    assert "high_impact_lower" in policy.rehab_directives[0].blocked_exposure_keys


def test_policy_trace_contains_case_source_and_movement_key():
    text = (
        "Shoulder - moderate, stable, can train with modifications. "
        "Avoid: overhead pressing."
    )
    injuries, restrictions = parse_injuries_and_restrictions(text)
    policy = compile_injury_policy(parsed_injuries=injuries, restrictions=restrictions)

    result = evaluate_injury_policy(
        policy=policy,
        text="Push Press",
        tags=["overhead", "press_heavy"],
    )

    assert result["trace"]
    trace = result["trace"][0]
    assert trace["case_id"] == policy.cases[0].id
    assert trace["source"] == "explicit_aggravator"
    assert trace["movement_key"] == "heavy_overhead_pressing"
