import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import (
    load_injury_exclusion_map_v2,
    validate_injury_exclusion_map_v2,
)


def test_injury_exclusion_map_v2_is_consistent():
    exclusion_map = load_injury_exclusion_map_v2()
    issues = validate_injury_exclusion_map_v2(exclusion_map)
    assert issues == []
