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
