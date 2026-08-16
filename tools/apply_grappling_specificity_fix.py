from pathlib import Path

path = Path('fightcamp/conditioning.py')
text = path.read_text(encoding='utf-8')
old = '''        "grappler": "bjj",\n        "grappling": "bjj",\n'''
new = '''        "grappler": "grappling",\n        "grappling": "grappling",\n'''
if text.count(old) != 1:
    raise SystemExit(f'grappling alias anchor: expected 1, found {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')

test_path = Path('tests/test_style_exact_sport_bonus.py')
t = test_path.read_text(encoding='utf-8')
anchor = '''    assert conditioning._style_specificity_sport_tag("wrestling", "mma") == "wrestling"\n'''
replacement = anchor + '''    assert conditioning._style_specificity_sport_tag("grappling", "mma") == "grappling"\n'''
if t.count(anchor) != 1:
    raise SystemExit(f'test helper anchor: expected 1, found {t.count(anchor)}')
t = t.replace(anchor, replacement, 1)

t += '''\n\ndef test_generic_grappling_does_not_inherit_bjj_specificity(monkeypatch):\n    exact, bjj_drill, candidates, diagnostics = _run_pair(\n        monkeypatch, \"grappler\", sport=\"mma\", other_sport=\"bjj\", technical_style=\"grappling\"\n    )\n    # Rebuild the exact row with the canonical generic-grappling sport token.\n    assert exact[\"tags\"][0] == \"grappling\"\n    assert candidates[exact[\"name\"]][\"reasons\"][\"sport_specificity_bonus\"] == 0.5\n    assert candidates[bjj_drill[\"name\"]][\"reasons\"][\"sport_specificity_bonus\"] == 0.0\n    assert diagnostics[\"entries_exact_sport_bonus_applied\"] == 1\n'''

test_path.write_text(t, encoding='utf-8')
