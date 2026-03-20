"""Tests for bank warm-cache optimisation (follow-up to PR #538).

Covers:
1. prime_plan_banks() sets the _BANKS_WARM flag on first (cold) call.
2. Second call short-circuits (warm path) and the individual prime functions
   are NOT called again.
3. Resetting _BANKS_WARM causes a fresh cold prime on the next call.
4. Warm-cache path still produces a valid full plan output.
5. Deterministic seeding is preserved across back-to-back warm-cache requests.
6. API response shape is unchanged after the warm-cache optimisation.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

import fightcamp.plan_pipeline_runtime as _runtime
from fightcamp.main import generate_plan

_DATA_PATH = Path(__file__).resolve().parents[1] / "test_data.json"


def _load_data() -> dict:
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_warm_flag():
    """Reset the module-level warm flag so tests are isolated."""
    _runtime._BANKS_WARM = False


# ---------------------------------------------------------------------------
# 1 – cold call sets the warm flag
# ---------------------------------------------------------------------------

def test_prime_plan_banks_sets_warm_flag_after_cold_call():
    _reset_warm_flag()
    assert _runtime._BANKS_WARM is False
    _runtime.prime_plan_banks()
    assert _runtime._BANKS_WARM is True


# ---------------------------------------------------------------------------
# 2 – second call short-circuits (warm path)
# ---------------------------------------------------------------------------

def test_prime_plan_banks_warm_path_skips_sub_primes(caplog):
    _reset_warm_flag()
    # First call: cold
    _runtime.prime_plan_banks()
    assert _runtime._BANKS_WARM is True

    call_counts: dict[str, int] = {"strength": 0, "conditioning": 0, "rehab": 0}

    original_strength = _runtime.prime_strength_banks
    original_conditioning = _runtime.prime_conditioning_banks
    original_rehab = _runtime.prime_rehab_bank

    def _count_strength():
        call_counts["strength"] += 1
        original_strength()

    def _count_conditioning():
        call_counts["conditioning"] += 1
        original_conditioning()

    def _count_rehab():
        call_counts["rehab"] += 1
        original_rehab()

    with (
        patch.object(_runtime, "prime_strength_banks", _count_strength),
        patch.object(_runtime, "prime_conditioning_banks", _count_conditioning),
        patch.object(_runtime, "prime_rehab_bank", _count_rehab),
        caplog.at_level(logging.DEBUG),
    ):
        _runtime.prime_plan_banks()

    assert call_counts["strength"] == 0, "prime_strength_banks must not be called on warm path"
    assert call_counts["conditioning"] == 0, "prime_conditioning_banks must not be called on warm path"
    assert call_counts["rehab"] == 0, "prime_rehab_bank must not be called on warm path"
    assert "path=warm" in caplog.text


# ---------------------------------------------------------------------------
# 3 – resetting the flag forces a fresh cold prime
# ---------------------------------------------------------------------------

def test_prime_plan_banks_cold_after_flag_reset():
    # Ensure already warm.
    _runtime.prime_plan_banks()
    assert _runtime._BANKS_WARM is True

    # Reset flag.
    _reset_warm_flag()
    assert _runtime._BANKS_WARM is False

    call_counts: dict[str, int] = {"strength": 0, "conditioning": 0, "rehab": 0}

    original_strength = _runtime.prime_strength_banks
    original_conditioning = _runtime.prime_conditioning_banks
    original_rehab = _runtime.prime_rehab_bank

    def _count_strength():
        call_counts["strength"] += 1
        original_strength()

    def _count_conditioning():
        call_counts["conditioning"] += 1
        original_conditioning()

    def _count_rehab():
        call_counts["rehab"] += 1
        original_rehab()

    with (
        patch.object(_runtime, "prime_strength_banks", _count_strength),
        patch.object(_runtime, "prime_conditioning_banks", _count_conditioning),
        patch.object(_runtime, "prime_rehab_bank", _count_rehab),
    ):
        _runtime.prime_plan_banks()

    assert call_counts["strength"] == 1, "prime_strength_banks must be called once on cold path"
    assert call_counts["conditioning"] == 1, "prime_conditioning_banks must be called once on cold path"
    assert call_counts["rehab"] == 1, "prime_rehab_bank must be called once on cold path"
    assert _runtime._BANKS_WARM is True


# ---------------------------------------------------------------------------
# 4 – warm-cache path still produces a valid plan
# ---------------------------------------------------------------------------

def test_warm_cache_path_produces_valid_plan():
    """Second generate_plan call (warm banks) must return a non-empty plan.
    The warm flag must be set (banks loaded) for the entire session."""
    data = _load_data()
    # First call: cold prime
    result1 = asyncio.run(generate_plan(data))
    assert result1.get("plan_text"), "first call must produce plan_text"
    # After the first call banks must be warm.
    assert _runtime._BANKS_WARM is True, "banks must be warm after first request"

    # Second call: warm prime – banks already warm, flag stays True.
    result2 = asyncio.run(generate_plan(data))
    assert result2.get("plan_text"), "warm-cache call must produce plan_text"
    assert result2.get("stage2_payload") is not None
    assert result2.get("planning_brief") is not None
    assert _runtime._BANKS_WARM is True, "warm flag must remain True after second request"


# ---------------------------------------------------------------------------
# 5 – deterministic seeding preserved across warm-cache requests
# ---------------------------------------------------------------------------

def test_deterministic_seeding_preserved_across_warm_requests():
    """Same seed must produce identical plan_text across multiple warm calls."""
    seed = 7
    data1 = _load_data()
    data1["random_seed"] = seed
    data2 = _load_data()
    data2["random_seed"] = seed

    # Ensure warm state before running.
    _runtime.prime_plan_banks()
    assert _runtime._BANKS_WARM is True

    result1 = asyncio.run(generate_plan(data1))
    # Banks must remain warm between the two generate_plan calls.
    assert _runtime._BANKS_WARM is True, "warm flag must not be cleared between requests"
    result2 = asyncio.run(generate_plan(data2))

    assert result1["plan_text"] == result2["plan_text"], (
        "Identical seeds must produce identical plan_text regardless of warm-cache state"
    )


# ---------------------------------------------------------------------------
# 6 – API response shape unchanged
# ---------------------------------------------------------------------------

_EXPECTED_KEYS = {
    "pdf_url",
    "why_log",
    "coach_notes",
    "plan_text",
    "stage2_payload",
    "planning_brief",
    "stage2_handoff_text",
}


def test_api_response_shape_unchanged_after_warm_cache():
    """All expected response keys must be present on the warm-cache path."""
    data = _load_data()
    # Ensure warm state.
    _runtime.prime_plan_banks()
    result = asyncio.run(generate_plan(data))
    assert _EXPECTED_KEYS.issubset(result.keys()), (
        f"Missing keys: {_EXPECTED_KEYS - result.keys()}"
    )
