import logging

from fightcamp.stage1_fail_safe import bounded_max_iterations, log_fail_safe_degrade
from fightcamp import conditioning


def test_bounded_max_iterations_has_floor_and_scales():
    assert bounded_max_iterations(0) == 8
    assert bounded_max_iterations(3) == 12


def test_log_fail_safe_degrade_format(caplog):
    with caplog.at_level(logging.WARNING):
        log_fail_safe_degrade(module="conditioning", phase="SPP", reason="no_candidates", target=2, actual=1)
    assert "[stage1] fail_safe_degrade module=conditioning phase=SPP reason=no_candidates target=2 actual=1" in caplog.text


def test_conditioning_returns_reduced_output_when_unavailable(monkeypatch):
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [])
    flags = {
        "phase": "SPP",
        "sport": "boxing",
        "key_goals": ["conditioning"],
        "weaknesses": [],
        "equipment_access": [],
        "injuries": [],
        "fatigue": "moderate",
        "training_frequency": 4,
        "days_until_fight": 35,
    }
    lines, grouped, *_ = conditioning.generate_conditioning_block(flags)
    assert isinstance(lines, list)
    assert isinstance(grouped, dict)


def test_conditioning_impossible_constraints_degrades_without_timeout(caplog):
    flags = {
        "phase": "TAPER",
        "sport": "boxing",
        "key_goals": ["conditioning"],
        "weaknesses": ["explosive power"],
        "equipment": ["jump rope"],
        "injuries": [{"region": "knee", "severity": "high", "type": "instability"}],
        "fatigue": "high",
        "training_frequency": 2,
        "days_until_fight": 2,
        "restrictions": ["no impact", "no plyometric"],
    }
    with caplog.at_level(logging.WARNING):
        output_lines, selected, _why, grouped, missing, _reservoir = conditioning.generate_conditioning_block(flags)
    assert isinstance(output_lines, list)
    assert isinstance(selected, list)
    assert isinstance(grouped, dict)
    assert isinstance(missing, list)
    assert "fail_safe_degrade module=conditioning" in caplog.text
    assert "timeout" not in caplog.text.lower()


def test_conditioning_cached_try_append_reuses_injury_and_late_eval(monkeypatch):
    injury_calls = 0
    late_calls = 0

    original_injury = conditioning._guarded_injury_decision
    original_late = conditioning._evaluate_conditioning_late_window

    def _count_injury(*args, **kwargs):
        nonlocal injury_calls
        injury_calls += 1
        return original_injury(*args, **kwargs)

    def _count_late(*args, **kwargs):
        nonlocal late_calls
        late_calls += 1
        return original_late(*args, **kwargs)

    monkeypatch.setattr(conditioning, "_guarded_injury_decision", _count_injury)
    monkeypatch.setattr(conditioning, "_evaluate_conditioning_late_window", _count_late)

    flags = {
        "phase": "TAPER",
        "sport": "boxing",
        "key_goals": ["conditioning", "skill_refinement"],
        "weaknesses": ["conditioning"],
        "equipment": ["jump rope", "assault bike"],
        "injuries": [{"region": "knee", "severity": "low", "type": "instability"}],
        "fatigue": "moderate",
        "training_frequency": 3,
        "days_until_fight": 5,
    }
    output_lines, selected, _why, grouped, missing, _reservoir = conditioning.generate_conditioning_block(flags)
    assert isinstance(output_lines, list)
    assert isinstance(selected, list)
    assert isinstance(grouped, dict)
    assert isinstance(missing, list)
    assert injury_calls > 0
    assert late_calls > 0
