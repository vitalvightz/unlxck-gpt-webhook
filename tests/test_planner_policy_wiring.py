"""Planner policies are applied where the governed functions are defined.

Three policies govern planner functions: late-fight dosage caps on
``conditioning``, phase eligibility on ``stage2_payload``, and authority
integrity on ``stage2_pipeline`` and ``stage2_policy``. Each owning module wraps
its own functions with the policy's ``governed_*`` factory at the end of the
module, so the name is governed from the moment it exists and every importer,
in any import order, gets the governed version. ``import fightcamp`` runs no
code.

(These policies used to be installed by ``fightcamp/__init__.py`` replacing the
functions after import, which left any module that bound one by name before the
install holding the ungoverned original.)

The checks run in fresh interpreters so the import order is the one under test,
not whatever earlier tests happened to import.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# (owning module, attribute, policy module whose wrapper governs it)
GOVERNED = (
    ("fightcamp.conditioning", "render_conditioning_block", "fightcamp.late_fight_dosage_policy"),
    ("fightcamp.conditioning", "generate_conditioning_block", "fightcamp.late_fight_dosage_policy"),
    ("fightcamp.conditioning", "_load_bank", "fightcamp.late_fight_dosage_policy"),
    ("fightcamp.stage2_payload", "build_planning_brief", "fightcamp.late_fight_phase_eligibility"),
    (
        "fightcamp.stage2_payload",
        "_build_late_fight_allowed_exercises_by_day",
        "fightcamp.late_fight_phase_eligibility",
    ),
    (
        "fightcamp.stage2_pipeline",
        "_validator_report_with_required_countdown_sessions",
        "fightcamp.planner_authority_integrity",
    ),
    ("fightcamp.stage2_pipeline", "build_stage2_retry", "fightcamp.planner_authority_integrity"),
    ("fightcamp.stage2_policy", "apply_stage2_release_policy", "fightcamp.planner_authority_integrity"),
    # Imported by name from stage2_policy, after the policy governed it.
    ("fightcamp.stage2_pipeline", "apply_stage2_release_policy", "fightcamp.planner_authority_integrity"),
)
POLICY_MODULES = sorted({policy for _owner, _attr, policy in GOVERNED})
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
first, entry_points, governed, policies, sabotage = json.loads(sys.argv[1])
importlib.import_module(first)
for name in entry_points:
    importlib.import_module(name)
if sabotage:
    exec(sabotage)
policy_files = {importlib.import_module(p).__file__: p for p in policies}

def governing_policy(value):
    code = getattr(value, "__code__", None)
    if code is None or not hasattr(value, "__wrapped__"):
        return None
    return policy_files.get(code.co_filename)

bindings = {
    f"{owner}.{attr}": governing_policy(getattr(importlib.import_module(owner), attr))
    for owner, attr, _policy in governed
}
wrapped = sorted(
    f"{name}.{bound}"
    for name, module in list(sys.modules.items())
    if name.startswith("fightcamp.") and isinstance(module, types.ModuleType)
    for bound, value in vars(module).items()
    if governing_policy(value) is not None and value.__wrapped__.__module__ == name
)
stale = []
for owner, attr, _policy in governed:
    governed_fn = getattr(importlib.import_module(owner), attr)
    original = governed_fn.__wrapped__
    for name, module in list(sys.modules.items()):
        if not name.startswith(("fightcamp", "api")) or not isinstance(module, types.ModuleType):
            continue
        for bound, value in vars(module).items():
            if value is governed_fn or not callable(value):
                continue
            if value is original or (
                getattr(value, "__module__", None) == original.__module__
                and getattr(value, "__name__", None) == original.__name__
            ):
                stale.append(f"{name}.{bound} -> ungoverned {original.__module__}.{original.__name__}")
print(json.dumps({"bindings": bindings, "wrapped": wrapped, "stale": sorted(set(stale))}))
"""


def _probe(first: str, entry_points=ENTRY_POINTS, sabotage: str = "") -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE,
            json.dumps([first, list(entry_points), [list(item) for item in GOVERNED], POLICY_MODULES, sabotage]),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("owner", sorted({owner for owner, _attr, _policy in GOVERNED}))
def test_a_module_imported_on_its_own_is_already_governed(owner):
    bindings = _probe(owner, entry_points=())["bindings"]

    assert bindings == {f"{o}.{attr}": policy for o, attr, policy in GOVERNED}


def test_every_policy_wrapper_in_use_is_listed():
    # A new governed_* wrapper applied where a function is defined must be added
    # to GOVERNED, so the checks here cover it.
    wrapped = set(_probe("fightcamp.main")["wrapped"])

    assert wrapped == {
        f"{owner}.{attr}"
        for owner, attr, _policy in GOVERNED
        if (owner, attr) != ("fightcamp.stage2_pipeline", "apply_stage2_release_policy")
    }


def test_no_module_keeps_an_ungoverned_planner_function():
    assert _probe("fightcamp.coach_review")["stale"] == []


def test_the_guard_reports_a_stale_binding_by_identity():
    report = _probe(
        "fightcamp.main",
        sabotage=(
            "import api.stage2_automation as s\n"
            "s.build_stage2_retry = s.build_stage2_retry.__wrapped__\n"
        ),
    )
    assert report["stale"] == [
        "api.stage2_automation.build_stage2_retry -> ungoverned "
        "fightcamp.stage2_pipeline.build_stage2_retry"
    ]


def test_the_guard_reports_a_stale_function_rebound_from_another_module():
    # stage2_pipeline binds a stage2_policy function; its original lives in
    # stage2_policy, so a name-only check against stage2_pipeline would miss it.
    report = _probe(
        "fightcamp.main",
        sabotage=(
            "import api.stage2_automation as s\n"
            "s.apply_stage2_release_policy = s.apply_stage2_release_policy.__wrapped__\n"
        ),
    )
    assert report["stale"] == [
        "api.stage2_automation.apply_stage2_release_policy -> ungoverned "
        "fightcamp.stage2_policy.apply_stage2_release_policy"
    ]


def test_importing_the_package_runs_nothing():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, fightcamp; print([m for m in sys.modules if m.startswith('fightcamp.')])",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert result.stdout.strip() == "[]"


def test_no_planner_module_replaces_another_modules_attributes():
    found = []
    for path in sorted((REPO_ROOT / "fightcamp").rglob("*.py")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (
                (node.level >= 1 and node.module is None) or node.module == "fightcamp"
            ):
                module_aliases |= {alias.asname or alias.name for alias in node.names}
            elif isinstance(node, ast.Import):
                module_aliases |= {
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name.startswith("fightcamp.")
                }
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            else:
                targets = []
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id in module_aliases
                ):
                    found.append(f"{relative}:{node.lineno}: {ast.unparse(target)}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "setattr"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in module_aliases
            ):
                found.append(f"{relative}:{node.lineno}: setattr({node.args[0].id}, ...)")

    assert found == []
