from pathlib import Path

path = Path("tests/test_structured_plan_stop_rules.py")
text = path.read_text()
old = '''def test_converter_prompt_keeps_stop_rules_separate_from_progression():
    prompt = build_structured_plan_prompt(plan_markdown="D-7 — Band-Resisted Punch")
    assert '"stop_rules"' in prompt
    assert '"Stop rule:" content as stop_rules' in prompt
    assert '"Stop rule:" content as progression_rule' not in prompt
'''
new = '''def test_converter_prompt_keeps_stop_rules_separate_from_progression():
    prompt = build_structured_plan_prompt(plan_markdown="D-7 — Band-Resisted Punch")
    assert '"stop_rules"' in prompt
    assert '"Stop:" / "Stop rule:" ->' in prompt
    assert '"Stop rule:" content as progression_rule' not in prompt
'''
if text.count(old) != 1:
    raise SystemExit("expected legacy stop-rule prompt assertion exactly once")
path.write_text(text.replace(old, new, 1))
