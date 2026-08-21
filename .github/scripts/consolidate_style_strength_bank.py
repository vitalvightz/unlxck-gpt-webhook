from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STYLE = ROOT / "data/style_specific_exercises"
EXERCISE = ROOT / "data/exercise_bank.json"
INFERRED = ROOT / "data/bank_inferred_tags.json"
EXCLUSIONS = ROOT / "data/injury_exclusion_map.json"
STRENGTH = ROOT / "fightcamp/strength.py"
INJURY_FILTERING = ROOT / "fightcamp/injury_filtering.py"

MIGRATE_NAMES = {
    "Wrist Roller Extensions",
    "Barbell Thruster",
    "Turkish Get-Up",
    "Counter-Striker Split-Line Punch Isometric Hold",
    "Pressure-Fighter Staggered Body-Shot Med-Ball Throw",
}


def remove_top_level_functions(text: str, names: set[str]) -> str:
    text = text.lstrip("\ufeff")
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            spans.append((node.lineno - 1, node.end_lineno, node.name))
    found = {name for _, _, name in spans}
    assert found == names, f"functions missing: {sorted(names - found)}"
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start:end]
    return "".join(lines)


def remove_top_level_assignments(text: str, names: set[str]) -> str:
    text = text.lstrip("\ufeff")
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        assigned: set[str] = set()
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigned.add(node.target.id)
        for name in assigned & names:
            spans.append((node.lineno - 1, node.end_lineno, name))
    found = {name for _, _, name in spans}
    assert found == names, f"assignments missing: {sorted(names - found)}"
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start:end]
    return "".join(lines)


def remove_monkeypatch_attr_calls(text: str, attr_name: str) -> str:
    text = text.lstrip("\ufeff")
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "setattr":
            continue
        if not isinstance(call.func.value, ast.Name) or call.func.value.id != "monkeypatch":
            continue
        if len(call.args) < 2:
            continue
        key = call.args[1]
        if isinstance(key, ast.Constant) and key.value == attr_name:
            spans.append((node.lineno - 1, node.end_lineno))
    for start, end in sorted(set(spans), reverse=True):
        del lines[start:end]
    return "".join(lines)


def migrate_bank() -> set[str]:
    style_items = json.loads(STYLE.read_text(encoding="utf-8"))
    style_by_name = {item["name"]: item for item in style_items}
    assert MIGRATE_NAMES <= style_by_name.keys()

    raw = EXERCISE.read_text(encoding="utf-8")
    main_items = json.loads(raw)
    existing = {item["name"] for item in main_items}
    assert not (MIGRATE_NAMES & existing), f"unexpected exact duplicates: {MIGRATE_NAMES & existing}"

    additions = [item for item in style_items if item["name"] in MIGRATE_NAMES]
    assert len(additions) == len(MIGRATE_NAMES)
    trimmed = raw.rstrip()
    assert trimmed.endswith("]")
    prefix = trimmed[:-1].rstrip()
    encoded = ",\n".join("  " + json.dumps(item, indent=2, ensure_ascii=False).replace("\n", "\n  ") for item in additions)
    EXERCISE.write_text(f"{prefix},\n{encoded}\n]\n", encoding="utf-8")

    final = json.loads(EXERCISE.read_text(encoding="utf-8"))
    names = [item["name"] for item in final]
    assert len(names) == len(set(names)), "duplicate names in exercise_bank after migration"
    assert MIGRATE_NAMES <= set(names)
    return set(names)


def migrate_inferred_tags() -> None:
    rows = json.loads(INFERRED.read_text(encoding="utf-8"))
    kept = [row for row in rows if row.get("bank") != "style_specific_exercises"]
    ids = {row.get("item_id") for row in kept}
    for row in rows:
        if row.get("bank") != "style_specific_exercises" or row.get("name") not in MIGRATE_NAMES:
            continue
        target = f"exercise_bank:{row['name']}"
        if target in ids:
            continue
        moved = dict(row)
        moved["bank"] = "exercise_bank"
        moved["item_id"] = target
        kept.append(moved)
        ids.add(target)
    assert not any(row.get("bank") == "style_specific_exercises" for row in kept)
    INFERRED.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def migrate_exclusions(main_names: set[str]) -> None:
    data = json.loads(EXCLUSIONS.read_text(encoding="utf-8"))
    for region, entries in data.items():
        result: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            if entry.startswith("style_specific_exercises:"):
                name = entry.split(":", 1)[1]
                if name not in main_names:
                    continue
                entry = f"exercise_bank:{name}"
            if entry not in seen:
                result.append(entry)
                seen.add(entry)
        data[region] = result
    EXCLUSIONS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert "style_specific_exercises:" not in EXCLUSIONS.read_text(encoding="utf-8")


def retire_loader() -> None:
    text = INJURY_FILTERING.read_text(encoding="utf-8")
    text = remove_top_level_functions(text, {"_load_style_specific_exercises"})
    dead_collect_line = '    banks["style_specific_exercises"] = _load_style_specific_exercises(mode=mode)\n'
    assert dead_collect_line in text, "collect_banks retired source line missing"
    text = text.replace(dead_collect_line, "", 1)
    INJURY_FILTERING.write_text(text, encoding="utf-8")


def retire_strength_side_channel() -> None:
    text = STRENGTH.read_text(encoding="utf-8")
    text = text.replace("    _load_style_specific_exercises,\n", "")
    text = remove_top_level_functions(text, {"get_style_exercises", "normalize_style_tags"})
    text = remove_top_level_assignments(text, {"_style_exercises_cache", "CANONICAL_STYLE_TAGS", "STYLE_INSERT_SCORE_MARGIN"})
    text = text.replace("    get_style_exercises()\n", "")
    text = text.replace("    style_exercises = get_style_exercises()\n", "")
    text = text.replace("        style_exercises = list(style_exercises)\n        rng.shuffle(style_exercises)\n", "")

    start_marker = "    # ------- STYLE-SPECIFIC INJECTION -------\n"
    end_marker = "    def _apply_movement_caps(\n"
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    assert start >= 0 and end > start, "style injection block markers missing"
    text = text[:start] + text[end:]

    old_sig = '''    def _apply_movement_caps(\n        exercises: list[dict],\n        *,\n        protected_names: set[str] | None = None,\n    ) -> list[dict]:\n        protected_names = {name for name in (protected_names or set()) if name}\n'''
    new_sig = '''    def _apply_movement_caps(exercises: list[dict]) -> list[dict]:\n'''
    assert old_sig in text, "movement cap signature changed"
    text = text.replace(old_sig, new_sig, 1)

    old_branch = '''        for ex in exercises:\n            name = ex.get("name")\n            movement = _cached_movement(ex)\n            if movement != "unknown" and movement_counts.get(movement, 0) >= 2:\n                if name in protected_names:\n                    replaceable_indices = [\n                        idx\n                        for idx, existing in enumerate(capped)\n                        if existing.get("name") not in protected_names\n                        and _cached_movement(existing) == movement\n                    ]\n                    if replaceable_indices:\n                        replace_index = min(\n                            replaceable_indices,\n                            key=lambda idx: score_lookup.get(capped[idx].get("name"), 0.0),\n                        )\n                        capped[replace_index] = ex\n                continue\n'''
    new_branch = '''        for ex in exercises:\n            movement = _cached_movement(ex)\n            if movement != "unknown" and movement_counts.get(movement, 0) >= 2:\n                continue\n'''
    assert old_branch in text, "protected movement-cap branch changed"
    text = text.replace(old_branch, new_branch, 1)
    text = text.replace(", protected_names=protected_style_names", "")
    text = "".join(line for line in text.splitlines(keepends=True) if "_ensure_protected_style_selection" not in line)
    STRENGTH.write_text(text, encoding="utf-8")


def update_tests() -> None:
    meta = ROOT / "tests/test_strength_metadata_selection.py"
    text = meta.read_text(encoding="utf-8")
    start = text.find("def test_style_specific_technical_primer_does_not_satisfy_strength_maintenance")
    assert start >= 0
    end = text.find("\ndef ", start + 1)
    assert end > start
    block = text[start:end]
    block = block.replace(
        "def test_style_specific_technical_primer_does_not_satisfy_strength_maintenance",
        "def test_tactical_style_technical_primer_does_not_satisfy_strength_maintenance",
        1,
    )
    block = block.replace('"style_specific_exercises.json"', '"exercise_bank.json"')
    assert "        [maintenance],\n" in block
    block = block.replace("        [maintenance],\n", "        [technical_primer, maintenance],\n", 1)
    block = block.replace('    monkeypatch.setattr(strength, "get_style_exercises", lambda: [technical_primer])\n', "")
    meta.write_text(text[:start] + block + text[end:], encoding="utf-8")

    style_test = ROOT / "tests/test_style_logic.py"
    text = style_test.read_text(encoding="utf-8")
    text = text.replace(
        "from fightcamp.strength import normalize_exercise_movement, normalize_style_tags, generate_strength_block\n",
        "from fightcamp.strength import normalize_exercise_movement, generate_strength_block\n",
    )
    text = remove_top_level_functions(text, {"test_style_tag_mapping"})
    style_test.write_text(text, encoding="utf-8")

    schema_test = ROOT / "tests/test_bank_schema_validation.py"
    text = schema_test.read_text(encoding="utf-8")
    text = text.replace('source="style_specific_exercises.json"', 'source="universal_gpp_strength.json"')
    schema_test.write_text(text, encoding="utf-8")

    for path in (ROOT / "tests").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        text = remove_monkeypatch_attr_calls(text, "get_style_exercises")
        text = "".join(
            line for line in text.splitlines(keepends=True)
            if "strength._style_exercises_cache" not in line
        )
        path.write_text(text, encoding="utf-8")


def verify_no_dead_code() -> None:
    forbidden = {
        "_load_style_specific_exercises",
        "get_style_exercises",
        "STYLE_INSERT_SCORE_MARGIN",
        "CANONICAL_STYLE_TAGS",
        "normalize_style_tags",
        "_style_exercises_cache",
        "protected_style_choice",
        "protected_style_names",
    }
    offenders: list[str] = []
    for base in ("fightcamp", "api", "tests", "tools", "web"):
        root = ROOT / base
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)}:{token}")
    assert not offenders, "dead style-bank code remains: " + ", ".join(offenders)


main_names = migrate_bank()
migrate_inferred_tags()
migrate_exclusions(main_names)
retire_loader()
retire_strength_side_channel()
update_tests()
STYLE.unlink()
verify_no_dead_code()
assert not STYLE.exists()
subprocess.run(
    [
        "git",
        "add",
        "--",
        "tests/test_lower_body_plyo_selection.py",
        "tests/test_operational_hardening.py",
    ],
    cwd=ROOT,
    check=True,
)
