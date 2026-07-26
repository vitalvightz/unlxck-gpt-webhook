"""Guards for helpers that were deduplicated onto a single canonical definition.

Each of these existed as two or more hand-maintained copies. The copies had
already drifted (see ``test_weekday_normalizers_accept_the_same_spellings``), so
these tests assert identity rather than equal behaviour: a future edit that
reintroduces a local copy fails here instead of silently diverging again.
"""
from __future__ import annotations

import pathlib

import pytest


def test_weekday_normalizers_are_the_canonical_function():
    from api.services.open_plan_timeline import normalize_weekday as timeline_normalize
    from api.structured_plan_generation import _normalize_weekday as structured_normalize
    from fightcamp.weekly_schedule_view import normalize_weekday as canonical

    assert timeline_normalize is structured_normalize is canonical


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("weds", "Wed"),   # was Stage-1 only; the two API maps lacked it
        ("Weds", "Wed"),
        ("wed.", "Wed"),   # trailing-dot strip was Stage-1 only
        ("Tues.", "Tue"),
        ("wednesday", "Wed"),
        ("MON", "Mon"),
        ("bogus", None),
        ("", None),
        (None, None),
    ],
)
def test_weekday_normalizers_accept_the_same_spellings(raw, expected):
    from api.services.open_plan_timeline import normalize_weekday as timeline_normalize
    from api.structured_plan_generation import _normalize_weekday as structured_normalize
    from fightcamp.weekly_schedule_view import normalize_weekday as canonical

    assert canonical(raw) == expected
    assert timeline_normalize(raw) == expected
    assert structured_normalize(raw) == expected


def test_high_pressure_weight_cut_is_the_canonical_function():
    from fightcamp.nutrition import _is_high_pressure_weight_cut as nutrition_high_pressure
    from fightcamp.recovery import _is_high_pressure_weight_cut as recovery_high_pressure
    from fightcamp.weight_cut import is_high_pressure_weight_cut as canonical

    assert nutrition_high_pressure is recovery_high_pressure is canonical


def test_utc_now_iso_is_the_canonical_function():
    from api.generation.time_utils import utc_now_iso as canonical
    from api.generation_job_helpers import _utc_now_iso as helpers_now
    from api.stage2_automation import _utc_now_iso as stage2_now
    from api.store import _utc_now_iso as store_now
    from api.structured_card_lifecycle import utc_now_iso as lifecycle_now

    assert store_now is helpers_now is stage2_now is lifecycle_now is canonical


def test_lazy_scheduler_shim_is_shared():
    """api.app and the triage-resume service must route through one shim.

    Both kept a copy of the create-only guard that keeps the planner out of a
    web process; a divergent copy would silently reintroduce the heavy import.
    """
    from api.app import schedule_generation_job_if_needed as app_schedule
    from api.generation.lazy_scheduler import schedule_generation_job_if_needed as canonical
    from api.services.triage_resume_service import (
        schedule_generation_job_if_needed as triage_schedule,
    )

    assert app_schedule is triage_schedule is canonical


def test_creating_a_job_does_not_import_the_planner():
    """The create-only path must not pull fightcamp.main into a web process.

    Runs in a subprocess: other tests in this suite legitimately import the
    planner, so an in-process ``sys.modules`` check would depend on test order.
    """
    import subprocess
    import sys

    probe = (
        "import sys\n"
        "import api.app\n"
        "import api.services.triage_resume_service\n"
        "import api.services.open_plan_timeline\n"
        "import api.structured_plan_generation\n"
        "leaked = [m for m in ('fightcamp.main', 'api.generation.scheduler',\n"
        "                      'api.generation.orchestrator', 'api.generation.stage1_runner')\n"
        "          if m in sys.modules]\n"
        "print('LEAKED=' + ','.join(leaked))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(pathlib.Path(__file__).resolve().parent.parent),
    )
    assert result.returncode == 0, result.stderr
    assert "LEAKED=\n" in result.stdout or result.stdout.rstrip().endswith("LEAKED="), (
        f"generation runtime leaked into the web import path: {result.stdout!r}"
    )
