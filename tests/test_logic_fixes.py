import ast
import random
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.camp_phases import calculate_phase_weeks
from fightcamp.conditioning import generate_conditioning_block
from fightcamp.strength import generate_strength_block, score_exercise
from fightcamp.training_context import calculate_exercise_numbers


def _load_goal_normalizer():
    main_path = Path(__file__).resolve().parents[1] / "fightcamp" / "main.py"
    source = main_path.read_text()
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "GOAL_NORMALIZER":
                    return ast.literal_eval(node.value)
    raise AssertionError("GOAL_NORMALIZER not found")


def _normalize_goals(labels):
    goal_normalizer = _load_goal_normalizer()
    return [goal_normalizer.get(label, label).lower() for label in labels]


def _base_equipment():
    return [
        "plate",
        "wrist_roller",
        "pullup_bar",
        "dumbbells",
        "bands",
        "kettlebell",
        "medicine_ball",
        "sled",
        "landmine",
        "sledgehammer",
        "heavy_bag",
        "assault_bike",
    ]


def test_empty_injuries_returns_tuple():
    rehab_path = Path(__file__).resolve().parents[1] / "fightcamp" / "rehab_protocols.py"
    source = rehab_path.read_text()
    tree = ast.parse(source)
    target = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "generate_rehab_protocols":
            target = node
            break
    assert target is not None

    return_tuple_found = False
    for node in ast.walk(target):
        if isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp):
            if isinstance(node.test.op, ast.Not) and isinstance(node.test.operand, ast.Name):
                if node.test.operand.id == "injury_string":
                    for stmt in node.body:
                        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Tuple):
                            return_tuple_found = True
    assert return_tuple_found


def test_goal_normalizer_hits_strength_and_conditioning():
    random.seed(0)
    goals = _normalize_goals(
        ["Power & Explosiveness", "Conditioning / Endurance", "Speed / Reaction"]
    )
    flags = {
        "phase": "GPP",
        "fight_format": "mma",
        "style_tactical": ["pressure fighter"],
        "style_technical": ["mma"],
        "training_days": ["mon", "wed", "fri"],
        "training_frequency": 3,
        "equipment": _base_equipment(),
        "key_goals": goals,
        "fatigue": "low",
    }
    strength_block = generate_strength_block(flags=flags, weaknesses=[], mindset_cue=None)
    assert any(
        entry["reasons"].get("goal_hits", 0) > 0 for entry in strength_block["why_log"]
    )

    cond_block, _, cond_reasons = generate_conditioning_block(flags)
    assert cond_block
    assert any(r["reasons"].get("goal_hits", 0) > 0 for r in cond_reasons)


def test_grappling_goal_hits_strength_and_conditioning():
    random.seed(1)
    flags = {
        "phase": "GPP",
        "fight_format": "mma",
        "style_tactical": ["grappler"],
        "style_technical": ["mma"],
        "training_days": ["mon", "wed", "fri"],
        "training_frequency": 3,
        "equipment": _base_equipment(),
        "key_goals": ["grappling"],
        "fatigue": "low",
    }
    strength_block = generate_strength_block(flags=flags, weaknesses=[], mindset_cue=None)
    assert any(
        entry["reasons"].get("goal_hits", 0) > 0 for entry in strength_block["why_log"]
    )

    _, _, cond_reasons = generate_conditioning_block(flags)
    assert any(r["reasons"].get("goal_hits", 0) > 0 for r in cond_reasons)


def test_wrestling_uses_mma_weights_in_conditioning():
    random.seed(2)
    flags = {
        "phase": "GPP",
        "fight_format": "mma",
        "style_tactical": ["clinch fighter"],
        "style_technical": ["wrestling"],
        "training_days": ["mon", "wed", "fri"],
        "training_frequency": 3,
        "equipment": _base_equipment(),
        "key_goals": [],
        "fatigue": "low",
    }
    _, _, reasons = generate_conditioning_block(flags)
    mma_weights = {0.5, 0.3, 0.2}
    assert any(r["reasons"].get("load_adjustments") in mma_weights for r in reasons)


def test_taper_respects_total_drills():
    random.seed(3)
    flags = {
        "phase": "TAPER",
        "fight_format": "mma",
        "style_tactical": ["pressure fighter"],
        "style_technical": ["mma"],
        "training_days": ["mon", "wed", "fri", "sat", "sun", "tue"],
        "training_frequency": 6,
        "equipment": _base_equipment(),
        "key_goals": ["endurance"],
        "fatigue": "low",
    }
    _, selected, _ = generate_conditioning_block(flags)
    expected = calculate_exercise_numbers(6, "TAPER")["conditioning"]
    assert len(selected) == expected


def test_equipment_bonus_requires_required_equipment():
    score, reasons = score_exercise(
        exercise_tags=[],
        weakness_tags=[],
        goal_tags=[],
        style_tags=[],
        phase_tags=[],
        current_phase="GPP",
        fatigue_level="low",
        available_equipment=["barbell"],
        required_equipment=[],
        is_rehab=False,
    )
    assert score is not None
    assert reasons["equipment_boost"] == 0.0


def test_days_align_with_weeks():
    phases = calculate_phase_weeks(2, "mma")
    for phase in ("GPP", "SPP", "TAPER"):
        assert phases["days"][phase] == phases[phase] * 7
        if phases[phase] == 0:
            assert phases["days"][phase] == 0
