from api.structured_plan_generation import _normalize_block, build_structured_plan_prompt
from api.structured_plan_models import SessionBlock

# These regressions protect the execution-first exercise block contract.


def test_session_block_has_first_class_stop_rules():
    block = SessionBlock(
        block_id="band-punch",
        block_type="accessory",
        display_name="Band-Resisted Punch",
        stop_rules=["Sharp ankle pain or uncontrolled balance loss."],
    )
    assert block.stop_rules == ["Sharp ankle pain or uncontrolled balance loss."]


def test_normalizer_moves_stop_coaching_cue_out_of_cues():
    block = _normalize_block(
        {
            "block_id": "burst",
            "block_type": "conditioning",
            "display_name": "Explosive Boxing Burst Intervals",
            "coaching_cues": ["All-out punch intent", "Stop: if punch speed or stance control drops."],
        }
    )
    assert block["coaching_cues"] == ["All-out punch intent"]
    assert block["stop_rules"] == ["if punch speed or stance control drops."]
    assert "progression_rule" not in block


def test_normalizer_splits_valid_progression_from_embedded_stop_rule():
    block = _normalize_block(
        {
            "block_id": "band-punch",
            "block_type": "accessory",
            "display_name": "Band-Resisted Punch",
            "progression_rule": "Increase band resistance when punch speed stays high — Stop: sharp shoulder pain.",
        }
    )
    assert block["progression_rule"] == "Increase band resistance when punch speed stays high"
    assert block["stop_rules"] == ["sharp shoulder pain."]


def test_normalizer_hides_taper_programming_but_preserves_stop_rule():
    block = _normalize_block(
        {
            "block_id": "band-punch",
            "block_type": "accessory",
            "display_name": "Band-Resisted Punch",
            "progression_rule": "Maintain dose; do not add volume in taper window — Stop: any sharp ankle pain, new swelling, or loss of balance.",
        }
    )
    assert "progression_rule" not in block
    assert block["stop_rules"] == ["any sharp ankle pain, new swelling, or loss of balance."]


def test_converter_prompt_keeps_stop_rules_separate_from_progression():
    prompt = build_structured_plan_prompt(plan_markdown="D-7 — Band-Resisted Punch")
    assert '"stop_rules"' in prompt
    assert '"Stop:" / "Stop rule:" ->' in prompt
    assert '"Stop rule:" content as progression_rule' not in prompt


def test_normalizer_routes_planning_prose_away_from_execution_cues():
    block = _normalize_block(
        {
            "block_id": "band-punch",
            "block_type": "accessory",
            "display_name": "Band-Resisted Punch",
            "coaching_cues": [
                "Purpose: transfer horizontal punching force under slight resistance",
                "Why today: single neural touch without disrupting taper",
                "Explosive intent; accelerate through full range",
                "Easier: reduce band tension",
                "Reset guard immediately",
                "Stop: sharp ankle pain or uncontrolled balance loss",
            ],
            "regression_options": ["Reduce band tension"],
        }
    )
    assert block["purpose"] == "transfer horizontal punching force under slight resistance"
    assert block["why_today"] == "single neural touch without disrupting taper"
    assert block["coaching_cues"] == [
        "Explosive intent; accelerate through full range",
        "Reset guard immediately",
    ]
    assert block["regression_options"] == ["Reduce band tension"]
    assert block["stop_rules"] == ["sharp ankle pain or uncontrolled balance loss"]


def test_converter_prompt_keeps_reasoning_rich_but_cues_execution_only():
    prompt = build_structured_plan_prompt(plan_markdown="D-7 — Band-Resisted Punch")
    assert '"why_today"' in prompt
    assert "execution-only how-to instructions" in prompt
    assert '"Why today:" -> why_today' in prompt
