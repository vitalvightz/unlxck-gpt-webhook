from __future__ import annotations

from types import SimpleNamespace

from fightcamp.late_fight_dosage_policy import (
    _repair_taper_phase_winner_for_current_window,
)
from fightcamp.planner_authority_integrity import late_physical_planner_preflight


def test_preflight_does_not_infer_late_tail_ownership_from_d12() -> None:
    brief = {
        "athlete_snapshot": {
            "phase_weeks": {"days": {"GPP": 6, "SPP": 13, "TAPER": 6}}
        },
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "session_roles": [
                        {
                            "role_key": "secondary_strength_day",
                            "category": "strength",
                            "scheduled_countdown_label": "D-12",
                            "selected_exercise_assignments": [],
                        }
                    ],
                }
            ]
        },
    }

    assert late_physical_planner_preflight(brief) == []


def _style_taper_drill(name: str, windows: list[str], *, bank_order: int) -> dict:
    return {
        "name": name,
        "_schema_source": "style_taper_conditioning.json",
        "phases": ["TAPER"],
        "late_windows": windows,
        "system": "alactic",
        "bank_order": bank_order,
    }


def test_taper_phase_winner_is_current_window_legal_but_reservoir_stays_complete() -> None:
    illegal_winner = _style_taper_drill(
        "Earlier Window Primer", ["d13_to_d8"], bank_order=1
    )
    d7_candidate = _style_taper_drill("D7 Primer", ["d7"], bank_order=2)
    future_candidate = _style_taper_drill(
        "D4-D2 Primer", ["d4_to_d2"], bank_order=3
    )

    reservoir = {
        "alactic": [
            {
                "drill": d7_candidate,
                "score": 4,
                "reasons": {"style_hits": 1, "goal_hits": 1, "weakness_hits": 0},
                "explanation": "D7 legal",
            },
            {
                "drill": future_candidate,
                "score": 3,
                "reasons": {"style_hits": 1, "goal_hits": 0, "weakness_hits": 0},
                "explanation": "Future window",
            },
        ]
    }
    result = (
        "old output",
        [illegal_winner["name"]],
        [
            {
                "name": illegal_winner["name"],
                "system": "alactic",
                "reasons": {},
                "explanation": "old",
            }
        ],
        {"alactic": [illegal_winner]},
        [],
        reservoir,
    )
    module = SimpleNamespace(
        render_conditioning_block=lambda grouped, **_: grouped["alactic"][0]["name"]
    )

    repaired = _repair_taper_phase_winner_for_current_window(
        result,
        flags={
            "phase": "TAPER",
            "days_until_fight": 7,
            "training_frequency": 4,
            "sport": "mma",
        },
        conditioning_module=module,
    )

    assert repaired[1] == ["D7 Primer"]
    assert repaired[3]["alactic"][0]["name"] == "D7 Primer"
    assert "d7" in repaired[3]["alactic"][0]["late_windows"]
    # The dated selector still receives the future-window candidate; repairing
    # the visible phase winner must not shrink the Stage-1 candidate reservoir.
    assert any(
        entry["drill"]["name"] == "D4-D2 Primer"
        for entry in repaired[5]["alactic"]
    )
