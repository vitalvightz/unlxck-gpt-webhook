from __future__ import annotations

from fightcamp import conditioning
from fightcamp.gap_fill_inserts import select_gap_fill_insert


def _athlete() -> dict:
    return {
        "sport": "boxing",
        "fight_format": "boxing",
        "status": "professional",
        "training_days": ["monday", "wednesday", "friday"],
        "hard_sparring_days": [],
        "fatigue": "low",
        "fatigue_level": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": ["power"],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
        "days_until_fight": 21,
        "plan_creation_weekday": "monday",
        "style_tactical": ["counter_striker"],
        "style_technical": ["boxing"],
        "equipment": ["bodyweight"],
    }


def test_gap_fill_can_use_technical_footwork_bank_without_explicit_footwork_focus():
    athlete = _athlete()
    original_goals = list(athlete["key_goals"])
    # Tactical Watch normally outranks footwork in this time band. Mark a recent
    # watch as already used so the real filler scorer is free to choose its next
    # best legal role; footwork can then win without being a selected goal.
    usage_ledger = {
        "used_role_keys": {"tactical_watch"},
        "used_categories": {"tactical"},
        "role_key_offsets": {"tactical_watch": [12]},
        "category_counts": {"tactical": 1},
        "used_tactical_watch_keys": set(),
    }

    role = select_gap_fill_insert(
        athlete,
        14,
        usage_ledger=usage_ledger,
        gap_span=5,
    )

    assert role is not None
    assert role["role_key"] == "footwork_walkthrough"
    assert role["technical_footwork_fallback"] is False
    assert role["technical_footwork_source"] == "technical_footwork_bank.json"
    assert role["technical_footwork_name"] == "Step-Back Pivot Reset"
    # The contextual filler permission must not rewrite the athlete's real goals.
    assert athlete["key_goals"] == original_goals


def test_normal_training_plan_still_requires_footwork_relevance():
    athlete = _athlete()
    flags = {
        **athlete,
        "phase": "SPP",
    }

    assert conditioning.select_technical_footwork_drill(flags, set(), []) is None
