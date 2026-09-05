from __future__ import annotations

import pytest

from fightcamp.session_composition import _select_bounded_records


def _record(name: str, priority: int, families: set[str]) -> dict:
    return {
        "slot": {},
        "name": name,
        "families": families,
        "support_only": families == {"support"},
        "sort_key": (priority, priority - 1),
        "original_index": priority - 1,
    }


@pytest.mark.parametrize("role_key", ["neural_plus_strength_day", "transfer_strength_day"])
def test_p1_prefers_hybrid_before_single_family_slot_consumes_capacity(role_key: str) -> None:
    records = [
        _record("Broad Jump", 1, {"lower_power"}),
        _record("Heavy RDL → Broad Jump", 2, {"lower_strength", "lower_power"}),
        _record("Pallof Hold", 3, {"support"}),
    ]

    selected, dropped = _select_bounded_records(
        records,
        role_key=role_key,
        cap=2,
        pressure=1,
    )

    names = [record["name"] for record in selected]
    assert names == ["Heavy RDL → Broad Jump", "Pallof Hold"]
    assert "Broad Jump" not in names
    assert dropped["Broad Jump"] == "redundant_major_family"

    covered = set().union(*(record["families"] for record in selected))
    assert "lower_power" in covered
    assert "lower_strength" in covered
