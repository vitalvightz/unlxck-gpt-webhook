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
