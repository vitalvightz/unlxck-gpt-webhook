"""Regression coverage for support conditioning elapsed-time/round-dose separation."""

import pytest

from api.structured_plan_deterministic_fallback import _session
from fightcamp.gap_fill_inserts import _INSERT_META


@pytest.mark.parametrize("rounds,total", [(4, 11), (3, 8)])
def test_shadow_flow_round_dose_is_not_elapsed_session_time(rounds, total):
    label = "Shadowboxing Aerobic Flow"
    instruction = _INSERT_META["aerobic_shadow_flow"]["display_text"]
    if rounds == 3:
        instruction = instruction.replace("4 x 2 min", "3 x 2 min")
    role = {
        "role_key": "aerobic_shadow_flow",
        "athlete_facing_label": label,
        "exercise_key": "tempo-shadowboxing",
        "prescribed_duration_min": total,
        "display_text": instruction,
        "category": "support_insert",
    }
    session = _session(role, 12)
    assert session is not None
    assert len(session["blocks"]) == 1
    block = session["blocks"][0]
    assert block["rounds"] == rounds
    assert block["work"] == {"value": 2, "unit": "minutes"}
    assert block["rest"] == {"value": 60, "unit": "seconds"}
    assert block.get("duration") != {"value": total, "unit": "minutes"}
    assert role["prescribed_duration_min"] == total
