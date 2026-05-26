import logging

from fightcamp.stage1_fail_safe import bounded_max_iterations, log_fail_safe_degrade
from fightcamp import conditioning
from fightcamp import injury_guard


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
    output_text, selected, _why, grouped, missing, reservoir = conditioning.generate_conditioning_block(flags)
    assert isinstance(output_text, str)
    assert isinstance(selected, list)
    assert isinstance(grouped, dict)
    assert isinstance(missing, list)
    assert isinstance(reservoir, dict)


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
        "restrictions": [
            {"restriction": "no impact"},
            {"restriction": "no plyometric"},
        ],
    }
    with caplog.at_level(logging.WARNING):
        output_lines, selected, _why, grouped, missing, _reservoir = conditioning.generate_conditioning_block(flags)
    assert isinstance(output_lines, str)
    assert isinstance(selected, list)
    assert isinstance(grouped, dict)
    assert isinstance(missing, list)
    assert "fail_safe_degrade module=conditioning" in caplog.text
    assert "timeout" not in caplog.text.lower()


def test_conditioning_cached_try_append_reuses_injury_and_late_eval(monkeypatch):
    injury_calls = 0
    late_calls = 0

    original_injury = injury_guard.injury_decision
    original_late = conditioning._evaluate_conditioning_late_window

    def _count_injury(*args, **kwargs):
        nonlocal injury_calls
        injury_calls += 1
        return original_injury(*args, **kwargs)

    def _count_late(*args, **kwargs):
        nonlocal late_calls
        late_calls += 1
        return original_late(*args, **kwargs)

    monkeypatch.setattr(injury_guard, "injury_decision", _count_injury)
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
    assert isinstance(output_lines, str)
    assert isinstance(selected, list)
    assert isinstance(grouped, dict)
    assert isinstance(missing, list)
    assert injury_calls > 0
    assert late_calls > 0


def test_generate_conditioning_block_scope_audit_all_phases_no_name_or_unbound():
    base_flags = {
        "sport": "boxing",
        "key_goals": ["conditioning"],
        "weaknesses": ["gas tank"],
        "equipment": ["jump rope", "assault bike"],
        "injuries": [{"region": "knee", "severity": "low", "type": "instability"}],
        "fatigue": "moderate",
        "training_frequency": 3,
    }
    for phase in ("GPP", "SPP", "TAPER"):
        flags = {**base_flags, "phase": phase, "days_until_fight": 10 if phase != "TAPER" else 5}
        try:
            result = conditioning.generate_conditioning_block(flags)
        except (UnboundLocalError, NameError) as exc:
            raise AssertionError(f"{phase} raised scope error: {exc}") from exc
        except Exception as exc:
            raise AssertionError(f"{phase} plan generation failed unexpectedly: {exc}") from exc
        assert isinstance(result, tuple)
        assert len(result) == 6


def test_generate_conditioning_block_knee_instability_emits_base_bank_progress():
    captured: list[str] = []

    def _callback(code: str, _label: str) -> None:
        captured.append(code)

    flags = {
        "phase": "GPP",
        "sport": "boxing",
        "style_tactical": ["Pressure Fighter"],
        "style_technical": ["boxing"],
        "key_goals": ["conditioning"],
        "weaknesses": ["gas tank"],
        "equipment": ["jump rope", "assault bike"],
        "injuries": [{"region": "knee", "severity": "low", "type": "instability"}],
        "fatigue": "moderate",
        "training_frequency": 3,
        "days_until_fight": 35,
        "conditioning_substep_callback": _callback,
    }
    result = conditioning.generate_conditioning_block(flags)
    assert isinstance(result, tuple)
    assert len(result) == 6
    assert "stage1_conditioning_base_bank_score_started" in captured
    assert "stage1_conditioning_base_bank_score_finished" in captured


def test_conditioning_candidate_reservoir_total_is_strictly_capped():
    flags = {
        "phase": "GPP",
        "sport": "mma",
        "key_goals": ["conditioning", "endurance"],
        "weaknesses": ["gas tank", "explosive power"],
        "equipment": ["jump rope", "assault bike", "rower", "medicine ball"],
        "injuries": [],
        "fatigue": "low",
        "training_frequency": 6,
        "days_until_fight": 28,
    }
    _output, _selected, _why, _grouped, _missing, reservoir = conditioning.generate_conditioning_block(flags)
    total = sum(len(v) for v in reservoir.values())
    assert total <= 400
