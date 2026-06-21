import logging

import pytest
from fightcamp import strength


def _flags(**overrides):
    flags = {
        "phase": "GPP",
        "random_seed": 7,
        "injuries": [],
        "fatigue": "low",
        "equipment": ["bodyweight", "dumbbell", "barbell", "medicine_ball", "bands"],
        "training_days": ["Mon", "Tue", "Thu", "Sat"],
        "training_frequency": 4,
        "days_until_fight": 28,
        "fight_format": "mma",
    }
    flags.update(overrides)
    return flags


def test_strength_classify_calls_are_bounded_with_caching(monkeypatch):
    calls = {"count": 0}
    original = strength.classify_strength_item

    def _spy(exercise):
        calls["count"] += 1
        return original(exercise)

    monkeypatch.setattr(strength, "classify_strength_item", _spy)
    result = strength.generate_strength_block(flags=_flags())
    unique_names = {ex.get("name") for ex in result.get("exercises", []) if ex.get("name")}
    assert len(unique_names) > 0
    assert calls["count"] <= 500


def test_injury_decision_cache_reduces_factory_calls(monkeypatch):
    calls = {"count": 0}
    original_factory = strength.make_guarded_decision_factory

    def _wrapped_factory(*args, **kwargs):
        decision_fn = original_factory(*args, **kwargs)

        def _spy(item):
            calls["count"] += 1
            return decision_fn(item)

        return _spy

    monkeypatch.setattr(strength, "make_guarded_decision_factory", _wrapped_factory)
    result = strength.generate_strength_block(
        flags=_flags(injuries=[{"location": "right knee", "severity": "low", "type": "instability", "status": "stable"}])
    )
    assert result.get("exercises")
    assert calls["count"] <= 250


def test_strength_reservoir_cap_logs_degrade(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    seed_ex = next(ex for ex in strength.get_exercise_bank() if "GPP" in ex.get("phases", []))
    large_bank = []
    for i in range(650):
        clone = dict(seed_ex)
        clone["name"] = f"{seed_ex.get('name', 'exercise')}_{i}"
        large_bank.append(clone)
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: large_bank)
    monkeypatch.setattr(strength, "score_exercise", lambda **kwargs: (1.0, {"reason_codes": []}))
    strength.generate_strength_block(flags=_flags(training_frequency=7, training_days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]))
    assert any("candidate_reservoir_capped" in rec.message for rec in caplog.records)


def test_knee_instability_payload_reaches_conditioning_without_timeout():
    pytest.importorskip("fastapi")
    from fightcamp.main import generate_plan_sync
    from support import _build_request

    payload = _build_request(
        {"injuries": "Right knee is wobbly (low, stable). Type: instability"}
    ).to_payload()

    codes: list[str] = []
    result = generate_plan_sync(
        payload,
        progress_callback=lambda code, *_args: codes.append(code),
    )

    assert result.get("status") != "invalid_input", result
    assert "stage1_strength_phase_gpp_finished" in codes
    assert "stage1_strength_phase_spp_finished" in codes
    assert "stage1_strength_block_finished" in codes
    assert "stage1_conditioning_block_started" in codes
    assert "stage1_planner_timeout" not in codes

def test_normal_payload_strength_structure_present():
    result = strength.generate_strength_block(flags=_flags(phase="SPP", days_until_fight=35))
    assert result.get("block")
    assert result.get("exercises")
    assert result.get("candidate_reservoir") is not None
