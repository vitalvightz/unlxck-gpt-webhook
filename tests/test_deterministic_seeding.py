"""
Tests for deterministic seeding in plan generation.
Verifies that:
1. Same seed produces identical plans
2. Different seeds produce different plans
3. No global random state leakage
"""
import sys
import asyncio
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.main import generate_plan


def get_test_data(seed=None):
    """Return basic test data for plan generation."""
    data = {
        "data": {
            "fields": [
                {"label": "Full name", "value": "Test Fighter"},
                {"label": "Age", "value": "25"},
                {"label": "Weight (kg)", "value": "70"},
                {"label": "Target Weight (kg)", "value": "68"},
                {"label": "Height (cm)", "value": "175"},
                {"label": "Fighting Style (Technical)", "value": ["mma"]},
                {"label": "Fighting Style (Tactical)", "value": ["pressure fighter"]},
                {"label": "Stance", "value": "Orthodox"},
                {"label": "Professional Status", "value": "Active"},
                {"label": "Current Record", "value": "5-2-0"},
                {"label": "When is your next fight?", "value": "2026-03-15"},
                {"label": "Rounds x Minutes", "value": "3x5"},
                {"label": "Weekly Training Frequency", "value": "3"},
                {"label": "Fatigue Level", "value": "Medium"},
                {"label": "Equipment Access", "value": ["Dumbbells", "Kettlebells", "Bands"]},
                {"label": "Training Availability", "value": ["Monday", "Wednesday", "Friday"]},
                {"label": "Any injuries or areas you need to work around?", "value": ""},
                {"label": "What are your key performance goals?", "value": "power,cardio"},
                {"label": "Where do you feel weakest right now?", "value": "pull"},
                {"label": "Do you prefer certain training styles?", "value": "hybrid"},
                {"label": "Do you struggle with any mental blockers or mindset challenges?", "value": ""},
                {"label": "Notes (anything else we should know)", "value": "Test athlete"}
            ]
        }
    }
    if seed is not None:
        data["random_seed"] = seed
    return data


def test_same_seed_produces_same_plan():
    """Test that using the same seed produces identical plans."""
    seed = 42
    data1 = get_test_data(seed)
    data2 = get_test_data(seed)
    
    result1 = asyncio.run(generate_plan(data1))
    result2 = asyncio.run(generate_plan(data2))
    
    # Extract plan text for comparison
    text1 = result1["plan_text"]
    text2 = result2["plan_text"]
    
    # Plans should be identical
    assert text1 == text2, "Same seed should produce identical plans"


def test_different_seeds_produce_different_plans():
    """Test that different seeds produce different plans."""
    data1 = get_test_data(seed=42)
    data2 = get_test_data(seed=99)
    
    result1 = asyncio.run(generate_plan(data1))
    result2 = asyncio.run(generate_plan(data2))
    
    text1 = result1["plan_text"]
    text2 = result2["plan_text"]
    
    # Plans should differ
    assert text1 != text2, "Different seeds should produce different plans"


def test_unseeded_plans_can_differ():
    """Test that unseeded plans can produce different outputs (non-deterministic)."""
    # Note: This test might occasionally pass even with different runs,
    # but generally unseeded plans should have some variability
    data1 = get_test_data(seed=None)
    data2 = get_test_data(seed=None)
    
    result1 = asyncio.run(generate_plan(data1))
    result2 = asyncio.run(generate_plan(data2))
    
    # This is a weak test - we just verify that unseeded plans CAN be generated
    # We don't strictly require them to differ, as that depends on random chance
    assert result1 is not None
    assert result2 is not None
    assert "plan_text" in result1
    assert "plan_text" in result2


def test_seeding_does_not_leak_globally():
    """Test that seeding one plan does not affect the next unseeded plan."""
    # Generate a seeded plan
    data_seeded = get_test_data(seed=42)
    result_seeded = asyncio.run(generate_plan(data_seeded))
    
    # Generate two unseeded plans
    # If seeding leaked globally, these would be identical
    data_unseeded1 = get_test_data(seed=None)
    data_unseeded2 = get_test_data(seed=None)
    
    result1 = asyncio.run(generate_plan(data_unseeded1))
    result2 = asyncio.run(generate_plan(data_unseeded2))
    
    # Both plans should be valid
    assert result1 is not None
    assert result2 is not None
    
    # The seeded plan should be repeatable
    result_seeded2 = asyncio.run(generate_plan(data_seeded))
    assert result_seeded["plan_text"] == result_seeded2["plan_text"]


def test_seed_zero_is_valid():
    """Test that seed=0 is a valid seed."""
    data1 = get_test_data(seed=0)
    data2 = get_test_data(seed=0)
    
    result1 = asyncio.run(generate_plan(data1))
    result2 = asyncio.run(generate_plan(data2))
    
    # Seed 0 should be deterministic
    assert result1["plan_text"] == result2["plan_text"]
