"""Stage 1 keeps only as many primaries per system as the phase workload needs.

`_resolve_conditioning_sessions` historically kept exactly one primary per
energy system and dropped the rest, so a system whose best drill could not carry
the phase workload reached composition permanently underfilled. The cap is now
derived from the shared `conditioning_phase_workload_envelope`.
"""
from fightcamp.conditioning import _conditioning_workload_primary_cap


def _drill(name, *, work_sec=None, rounds=None, duration=None, fallback=False):
    drill = {"name": name}
    if work_sec is not None:
        drill["work_sec"] = work_sec
    if rounds is not None:
        drill["rounds"] = rounds
    if duration is not None:
        drill["duration"] = duration
    if fallback:
        drill["render_as_fallback"] = True
    return drill


def test_one_drill_that_carries_the_target_stays_a_single_primary():
    # SPP glycolytic target is 480s; 5 x 5min = 1500s on its own.
    drills = [
        _drill("Pad EMOM", work_sec=300, rounds=5),
        _drill("Extra Circuit", work_sec=120, rounds=4),
    ]
    assert _conditioning_workload_primary_cap(drills, phase="SPP", system="glycolytic") == 1


def test_short_drills_stack_only_until_the_target_is_met():
    # 80s + 600s continuous clears the 480s SPP aerobic target at two drills.
    drills = [
        _drill("Bike Primer", work_sec=10, rounds=8),
        _drill("Rhythm Flow", duration="10-15min continuous"),
        _drill("Third Drill", duration="10min continuous"),
    ]
    assert _conditioning_workload_primary_cap(drills, phase="SPP", system="aerobic") == 2


def test_taper_has_no_phase_target_and_keeps_one_primary():
    drills = [
        _drill("Sharpness A", work_sec=10, rounds=4),
        _drill("Sharpness B", work_sec=10, rounds=4),
    ]
    assert _conditioning_workload_primary_cap(drills, phase="TAPER", system="aerobic") == 1


def test_undosed_drill_stops_the_stack_rather_than_guessing():
    drills = [
        _drill("Bike Primer", work_sec=10, rounds=8),
        _drill("Undosed Drill"),
        _drill("Rhythm Flow", duration="15min continuous"),
    ]
    assert _conditioning_workload_primary_cap(drills, phase="SPP", system="aerobic") == 1


def test_explicit_fallbacks_never_count_as_primaries():
    drills = [
        _drill("Bike Primer", work_sec=10, rounds=8),
        _drill("Backup", duration="20min continuous", fallback=True),
        _drill("Rhythm Flow", duration="15min continuous"),
    ]
    assert _conditioning_workload_primary_cap(drills, phase="SPP", system="aerobic") == 2


def test_never_returns_zero_when_only_fallbacks_exist():
    drills = [_drill("Backup", duration="20min continuous", fallback=True)]
    assert _conditioning_workload_primary_cap(drills, phase="SPP", system="aerobic") == 1


# ---------------------------------------------------------------------------
# Stage 1 measures the dose the athlete will actually receive
# ---------------------------------------------------------------------------


def _round_drill(name, *, work_sec, rounds, rest_sec=60):
    return {
        "name": name,
        "work_sec": work_sec,
        "rounds": rounds,
        "rest_sec": rest_sec,
        "round_based": True,
    }


def test_stage1_keeps_a_second_primary_when_the_athlete_round_is_short():
    """A 3x3min drill covers the 480s SPP target; the same drill at 2min rounds
    delivers 360s, so Stage 1 must not discard the slot composition will need."""
    drills = [
        _round_drill("Shadow Rounds", work_sec=180, rounds=3),
        _drill("Sprawl Circuit", work_sec=30, rounds=5),
    ]
    long_round = _conditioning_workload_primary_cap(
        drills, phase="SPP", system="glycolytic", round_seconds=180.0
    )
    short_round = _conditioning_workload_primary_cap(
        drills, phase="SPP", system="glycolytic", round_seconds=120.0
    )
    assert long_round == 1
    assert short_round == 2


def test_stage1_without_a_rounds_format_measures_the_bank_dose():
    drills = [
        _round_drill("Shadow Rounds", work_sec=180, rounds=3),
        _drill("Sprawl Circuit", work_sec=30, rounds=5),
    ]
    assert (
        _conditioning_workload_primary_cap(
            drills, phase="SPP", system="glycolytic", round_seconds=None
        )
        == 1
    )


def test_stage1_leaves_non_round_drills_on_their_own_dose():
    """A long round length must not inflate a drill that is not round-based."""
    drills = [_drill("Bike Block", work_sec=240, rounds=2), _drill("Filler", work_sec=30, rounds=4)]
    for round_seconds in (None, 120.0, 300.0):
        assert (
            _conditioning_workload_primary_cap(
                drills, phase="SPP", system="glycolytic", round_seconds=round_seconds
            )
            == 1
        )
