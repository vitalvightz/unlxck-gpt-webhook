"""Guards for the late-fight allocation memo and the countdown-label parse cache.

``_late_fight_practical_allocation_plan`` runs an exhaustive assignment search that
dominates late-fight build time, and ``build_planning_brief`` asks for the same
allocation two to three times per plan with identical inputs. It is memoised.

The risk a memo introduces is not staleness — the inputs fully determine the result
and nothing in the module is time- or randomness-dependent — but *sharing*: callers
mutate the returned roles in place (``session_index`` renumbering,
``_soften_late_strength_touches``). These tests lock down that every caller gets an
isolated copy and that distinct athletes never collide on a cache key.
"""

from __future__ import annotations

import pytest

from fightcamp.stage2_payload_late_fight import (
    _allocation_cache,
    _countdown_offset,
    _late_fight_practical_allocation_plan,
)


@pytest.fixture(autouse=True)
def _clear_allocation_cache():
    _allocation_cache.clear()
    yield
    _allocation_cache.clear()


def _athlete(**overrides) -> dict:
    athlete = {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        "hard_sparring_days": ["tuesday", "saturday"],
        "fatigue": "low",
        "weight_cut_pct": 0.0,
        "weight_cut_risk": False,
        "readiness_flags": [],
        "injuries": [],
        "fight_date": "2026-06-26",
        "days_until_fight": 20,
        "plan_creation_weekday": "friday",
    }
    athlete.update(overrides)
    return athlete


def test_repeated_calls_return_equal_allocations():
    athlete = _athlete()
    first = _late_fight_practical_allocation_plan(20, athlete)
    second = _late_fight_practical_allocation_plan(20, athlete)
    assert first == second
    assert len(_allocation_cache) == 1


def test_callers_never_share_mutable_allocation_state():
    # The real hazard: callers renumber session_index and soften roles in place.
    # A memo that handed back the cached object would leak one caller's edits into
    # the next plan built from the same inputs.
    athlete = _athlete()
    first = _late_fight_practical_allocation_plan(20, athlete)
    baseline_roles = len(first.get("session_roles", []))
    assert baseline_roles, "fixture must produce session roles for this to mean anything"

    first["session_roles"].append({"role_key": "injected_by_caller"})
    for role in first["session_roles"]:
        role["session_index"] = 999
    first["mode"] = "mutated"

    second = _late_fight_practical_allocation_plan(20, athlete)
    assert len(second["session_roles"]) == baseline_roles
    assert second["mode"] != "mutated"
    assert all(role.get("session_index") != 999 for role in second["session_roles"])

    # And the objects themselves are distinct, not just equal.
    third = _late_fight_practical_allocation_plan(20, athlete)
    assert third is not second
    assert all(a is not b for a, b in zip(second["session_roles"], third["session_roles"]))


def test_distinct_athletes_do_not_share_a_cache_entry():
    quiet = _late_fight_practical_allocation_plan(20, _athlete())
    loaded = _late_fight_practical_allocation_plan(
        20, _athlete(hard_sparring_days=["monday", "tuesday", "thursday", "saturday"])
    )
    assert len(_allocation_cache) == 2
    # Same athlete again must reproduce the first result, not the second.
    assert _late_fight_practical_allocation_plan(20, _athlete()) == quiet
    assert loaded == _late_fight_practical_allocation_plan(
        20, _athlete(hard_sparring_days=["monday", "tuesday", "thursday", "saturday"])
    )


def test_same_athlete_at_a_different_countdown_is_a_different_entry():
    _late_fight_practical_allocation_plan(20, _athlete(days_until_fight=20))
    _late_fight_practical_allocation_plan(14, _athlete(days_until_fight=14))
    assert len(_allocation_cache) == 2


def test_unencodable_athlete_model_still_builds():
    # A model carrying something JSON cannot represent must skip the cache and
    # compute rather than raise — never silently key on a lossy stringification.
    athlete = _athlete(guided_injury={"reported_at": object()})
    allocation = _late_fight_practical_allocation_plan(20, athlete)
    assert isinstance(allocation, dict)
    assert "session_roles" in allocation
    assert not _allocation_cache, "unencodable inputs must not be cached"


def test_cache_is_bounded():
    from fightcamp.stage2_payload_late_fight import _ALLOCATION_CACHE_MAXSIZE

    for days in range(3, 3 + _ALLOCATION_CACHE_MAXSIZE + 3):
        _late_fight_practical_allocation_plan(days, _athlete(days_until_fight=days))
    assert len(_allocation_cache) <= _ALLOCATION_CACHE_MAXSIZE


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("D-5", 5),
        ("d-5", 5),
        (" D-17 ", 17),
        ("D-05", 5),
        ("D-0", 0),
        ("D-", None),
        ("Dx", None),
        ("", None),
        (None, None),
        (0, None),
        (5, None),
        (["D-5"], None),
    ],
)
def test_countdown_offset_parses_exactly_as_before(label, expected):
    # The parse is cached on the hot path; it must still fold every input the
    # uncached version handled, including non-strings that lru_cache cannot key.
    assert _countdown_offset(label) == expected
