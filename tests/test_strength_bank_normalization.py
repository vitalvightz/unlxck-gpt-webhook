"""The cached strength bank is canonical from the first read.

Selection writes the normalized movement back onto the rows it reads, and the
quality classifier reads that movement. If the loader handed out raw rows, a
plan generated in a cold process without ``prime_strength_banks`` would depend
on which plans the process had generated before it.
"""
from __future__ import annotations

import copy

import pytest

from fightcamp import strength

_HOME = ["dumbbells", "kettlebell", "bands", "pullup_bar", "bodyweight"]


def _flags(phase: str, goals: list[str], equipment: list[str]) -> dict:
    return {
        "phase": phase, "fatigue": "low", "equipment": equipment, "fight_format": "mma",
        "style_tactical": ["pressure_fighter"], "key_goals": goals, "training_frequency": 5,
        "training_days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "days_until_fight": 56, "injuries": [],
    }


@pytest.fixture
def cold_bank(monkeypatch):
    monkeypatch.setattr(strength, "_exercise_bank_cache", None)


def _names(block: dict) -> list[str]:
    return [exercise["name"] for exercise in block["exercises"]]


def test_loaded_bank_is_already_normalized(cold_bank):
    bank = strength.get_exercise_bank()
    snapshot = copy.deepcopy(bank)
    for item in bank:
        strength.normalize_exercise_movement(item)
    assert bank == snapshot


def test_generation_does_not_rewrite_cached_rows(cold_bank):
    snapshot = copy.deepcopy(strength.get_exercise_bank())
    strength.generate_strength_block(flags=_flags("SPP", ["power"], _HOME), weaknesses=[])
    assert strength.get_exercise_bank() == snapshot


def test_block_does_not_depend_on_earlier_generations(monkeypatch):
    target = _flags("SPP", ["power"], _HOME)

    monkeypatch.setattr(strength, "_exercise_bank_cache", None)
    first = _names(strength.generate_strength_block(flags=target, weaknesses=[]))

    monkeypatch.setattr(strength, "_exercise_bank_cache", None)
    for phase, goals in (("GPP", ["strength"]), ("SPP", ["conditioning"]), ("SPP", ["grappling"])):
        strength.generate_strength_block(flags=_flags(phase, goals, _HOME), weaknesses=["core"])
    after_others = _names(strength.generate_strength_block(flags=target, weaknesses=[]))

    assert after_others == first
