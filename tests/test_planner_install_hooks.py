"""The planner's import-time policy hooks reach every module that uses them.

``fightcamp/__init__.py`` installs three policies by replacing functions on
other planner modules (late-fight dosage caps on ``conditioning``, phase
eligibility on ``stage2_payload``, authority integrity on ``stage2_pipeline``).
A module that binds one of those functions by name (``from .conditioning import
generate_conditioning_block``) keeps whatever object existed when it was
imported. Today the install runs first, so every binding is the governed one;
an import-order change would silently hand some call sites the ungoverned
original. These tests fail loudly if that ever happens.

They run in a fresh interpreter so the import order is production's, not
whatever earlier tests happened to import.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# (module, attribute) pairs that an install() hook replaces.
PATCHED_FUNCTIONS = (
    ("fightcamp.conditioning", "render_conditioning_block"),
    ("fightcamp.conditioning", "generate_conditioning_block"),
    ("fightcamp.conditioning", "_load_bank"),
    ("fightcamp.stage2_payload", "build_planning_brief"),
    ("fightcamp.stage2_payload", "_build_late_fight_allowed_exercises_by_day"),
    ("fightcamp.stage2_pipeline", "_validator_report_with_required_countdown_sessions"),
)
INSTALL_FLAGS = (
    ("fightcamp.conditioning", "_STYLE_TAPER_DOSAGE_POLICY_INSTALLED"),
    ("fightcamp.stage2_payload", "_LATE_FIGHT_PHASE_ELIGIBILITY_INSTALLED"),
    ("fightcamp.stage2_pipeline", "_PLANNER_AUTHORITY_INTEGRITY_INSTALLED"),
)
# Production entry points: the worker's Stage 1 planner and Stage 2 / structured
# card generation.
ENTRY_POINTS = (
    "fightcamp.plan_pipeline",
    "fightcamp.main",
    "api.generation.orchestrator",
    "api.stage2_automation",
    "api.structured_plan_generation",
)

_PROBE = """
import importlib, json, sys, types
entry_points, patched_functions, install_flags = json.loads(sys.argv[1])
for name in entry_points:
    importlib.import_module(name)
flags = {f"{m}.{a}": getattr(importlib.import_module(m), a, False) is True for m, a in install_flags}
stale = []
for module_name, attr in patched_functions:
    governed = getattr(importlib.import_module(module_name), attr)
    for name, module in list(sys.modules.items()):
        if not name.startswith(("fightcamp", "api")) or not isinstance(module, types.ModuleType):
            continue
        for bound_name, value in vars(module).items():
            # The ungoverned original is defined in module_name under attr; any
            # binding of it that is not the governed object missed the install.
            if (
                callable(value)
                and getattr(value, "__module__", None) == module_name
                and getattr(value, "__name__", None) == attr
                and value is not governed
            ):
                stale.append(f"{name}.{bound_name} -> ungoverned {module_name}.{attr}")
print(json.dumps({"flags": flags, "stale": stale}))
"""


def _probe(entry_points=ENTRY_POINTS) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps([list(entry_points), PATCHED_FUNCTIONS, INSTALL_FLAGS])],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_every_install_hook_runs_on_production_import():
    flags = _probe()["flags"]
    assert flags and all(flags.values()), flags


def test_no_module_keeps_an_ungoverned_planner_function():
    assert _probe()["stale"] == []


def test_importing_a_leaf_module_first_still_installs_every_hook():
    # A direct import of a leaf module still runs fightcamp/__init__ first.
    report = _probe(entry_points=("fightcamp.coach_review", *ENTRY_POINTS))
    assert all(report["flags"].values()), report["flags"]
    assert report["stale"] == []
