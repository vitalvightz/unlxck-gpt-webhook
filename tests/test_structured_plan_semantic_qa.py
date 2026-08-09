from api.structured_plan_semantic_qa import (
    build_structured_card_semantic_qa_prompt,
    parse_structured_card_semantic_qa,
)


def test_semantic_qa_parser_accepts_clean_pass():
    result = parse_structured_card_semantic_qa('{"verdict":"pass","issues":[]}')
    assert result.passed is True
    assert result.issues == ()


def test_semantic_qa_parser_fails_closed_on_invalid_json():
    result = parse_structured_card_semantic_qa("not-json")
    assert result.passed is False
    assert result.issues


def test_semantic_qa_parser_keeps_path_and_reason():
    result = parse_structured_card_semantic_qa('{"verdict":"fail","issues":[{"path":"weeks.0.days.0.sessions.0.blocks.0.stop_rules.0","reason":"isolated symptom"}]}')
    assert result.passed is False
    assert result.issues == ("weeks.0.days.0.sessions.0.blocks.0.stop_rules.0: isolated symptom",)


def test_semantic_qa_prompt_catches_orphan_stop_rule_without_rewriting():
    prompt = build_structured_card_semantic_qa_prompt({"weeks": [{"days": [{"sessions": [{"blocks": [{"stop_rules": ["discharge"]}]}]}]}]})
    assert 'only "discharge"' in prompt
    assert "Do not rewrite the plan" in prompt
    assert '"stop_rules":["discharge"]' in prompt
