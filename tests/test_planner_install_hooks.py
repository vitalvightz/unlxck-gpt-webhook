"""The planner's import-time policy hooks reach every module that uses them.

``fightcamp/__init__.py`` installs three policies by replacing functions on
other planner modules (late-fight dosage caps on ``conditioning``, phase
eligibility on ``stage2_payload``, authority integrity on ``stage2_pipeline``
and ``stage2_policy``). A module that binds one of those functions by name
(``from .stage2_pipeline import build_stage2_retry``) keeps whatever object
existed when it was imported. Today the install runs first, so every binding is
the governed one; an import-order change would silently hand some call sites
the ungoverned original. These tests fail loudly if that ever happens.

The patched names are read from the ``install()`` functions themselves, so a
new patch is guarded without editing this file. The checks run in a fresh
interpreter so the import order is production's, not whatever earlier tests
happened to import.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_MODULES = (
    "planner_authority_integrity",
    "late_fight_dosage_policy",
    "late_fight_phase_eligibility",
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
# Known at the time of writing; the derived set must include them, so a parser
# that silently finds nothing cannot pass.
KNOWN_PATCHES = {
    ("fightcamp.conditioning", "render_conditioning_block"),
    ("fightcamp.conditioning", "generate_conditioning_block"),
    ("fightcamp.stage2_payload", "build_planning_brief"),
    ("fightcamp.stage2_pipeline", "build_stage2_retry"),
    ("fightcamp.stage2_policy", "apply_stage2_release_policy"),
    ("fightcamp.stage2_pipeline", "apply_stage2_release_policy"),
}


def _install_assignments() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(patched functions, install flags) assigned by every hook's install()."""
    patches: list[tuple[str, str]] = []
    flags: list[tuple[str, str]] = []
    for hook in HOOK_MODULES:
        tree = ast.parse((REPO_ROOT / "fightcamp" / f"{hook}.py").read_text(encoding="utf-8"))
        install = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "install"
        )
        aliases: dict[str, str] = {}
        for node in ast.walk(install):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
                for alias in node.names:
                    aliases[alias.asname or alias.name] = f"fightcamp.{alias.name}"
        for node in ast.walk(install):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id in aliases
                ):
                    pair = (aliases[target.value.id], target.attr)
                    (flags if isinstance(node.value, ast.Constant) else patches).append(pair)
    return patches, flags


_PROBE = """
import importlib, json, sys, types
entry_points, patches, flags, sabotage = json.loads(sys.argv[1])
for name in entry_points:
    importlib.import_module(name)
if sabotage:
    exec(sabotage)
flag_state = {f"{m}.{a}": getattr(importlib.import_module(m), a, False) is True for m, a in flags}
stale = []
for module_name, attr in patches:
    governed = getattr(importlib.import_module(module_name), attr)
    original = getattr(governed, "__wrapped__", None)
    # The ungoverned original is identified by identity when the governed
    # function wraps it, otherwise by the name it was defined under.
    origin_module = getattr(original, "__module__", None) or module_name
    origin_name = getattr(original, "__name__", None) or attr
    for name, module in list(sys.modules.items()):
        if not name.startswith(("fightcamp", "api")) or not isinstance(module, types.ModuleType):
            continue
        for bound_name, value in vars(module).items():
            if value is governed or not callable(value):
                continue
            if value is original or (
                getattr(value, "__module__", None) == origin_module
                and getattr(value, "__name__", None) == origin_name
            ):
                stale.append(f"{name}.{bound_name} -> ungoverned {origin_module}.{origin_name}")
print(json.dumps({"flags": flag_state, "stale": sorted(set(stale))}))
"""


def _probe(entry_points=ENTRY_POINTS, sabotage: str = "") -> dict:
    patches, flags = _install_assignments()
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps([list(entry_points), patches, flags, sabotage])],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_every_patch_the_install_hooks_make_is_guarded():
    patches, flags = _install_assignments()

    assert KNOWN_PATCHES <= set(patches)
    assert len(flags) == len(HOOK_MODULES)


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


def test_the_guard_reports_a_stale_binding_by_identity():
    # What an import-order regression would leave behind in the API layer.
    report = _probe(
        sabotage=(
            "import api.stage2_automation as s\n"
            "s.build_stage2_retry = s.build_stage2_retry.__wrapped__\n"
        )
    )
    assert report["stale"] == [
        "api.stage2_automation.build_stage2_retry -> ungoverned "
        "fightcamp.stage2_pipeline.build_stage2_retry"
    ]


def test_the_guard_reports_a_stale_function_rebound_from_another_module():
    # stage2_pipeline re-binds a stage2_policy function; its original lives in
    # stage2_policy, so a name-only check against stage2_pipeline would miss it.
    report = _probe(
        sabotage=(
            "import api.stage2_automation as s\n"
            "s.apply_stage2_release_policy = s.apply_stage2_release_policy.__wrapped__\n"
        )
    )
    assert report["stale"] == [
        "api.stage2_automation.apply_stage2_release_policy -> ungoverned "
        "fightcamp.stage2_policy.apply_stage2_release_policy"
    ]
