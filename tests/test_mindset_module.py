import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.main import _filter_mindset_blocks
from fightcamp.mindset_module import get_mindset_by_phase


def test_kickboxing_mindset_excludes_grappling_cues():
    blocks = _filter_mindset_blocks(["fear of takedowns"], ["kickboxing"], [])
    mindset = get_mindset_by_phase("GPP", {"mental_block": blocks})
    lowered = mindset.lower()
    for banned in ["takedown", "sprawl", "wrestling", "grappling", "wall wrestling"]:
        assert banned not in lowered
