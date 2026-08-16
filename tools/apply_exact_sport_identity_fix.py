from pathlib import Path

path = Path('fightcamp/conditioning.py')
text = path.read_text(encoding='utf-8')

def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 anchor, found {count}')
    text = text.replace(old, new, 1)

replace_once(
'''def _style_exact_sport_bonus(raw_tags: list[str], selection_format: str) -> float:\n    \"\"\"Return the small preference for a raw exact-sport style-bank match.\n\n    Raw bank tags are inspected before compatibility rewrites so a rewritten\n    Muay Thai tag cannot masquerade as a native boxing tag.\n    \"\"\"\n    sport = str(selection_format or \"\").strip().lower()\n    if not sport:\n        return 0.0\n    return STYLE_EXACT_SPORT_BONUS if sport in set(normalize_tags(raw_tags or [])) else 0.0\n''',
'''def _style_specificity_sport_tag(primary_tech: str, selection_format: str) -> str:\n    \"\"\"Preserve the athlete's real sport identity before format collapsing.\n\n    BJJ and wrestling intentionally use MMA programming weights, but they must\n    not therefore make an MMA-tagged style drill look more sport-specific than\n    a BJJ- or wrestling-tagged drill.\n    \"\"\"\n    tech = str(primary_tech or \"\").strip().lower().replace(\"-\", \" \" )\n    aliases = {\n        \"boxer\": \"boxing\",\n        \"boxing\": \"boxing\",\n        \"kickboxer\": \"kickboxing\",\n        \"kickboxing\": \"kickboxing\",\n        \"karate\": \"kickboxing\",\n        \"muay thai\": \"muay_thai\",\n        \"muaythai\": \"muay_thai\",\n        \"muay_thai\": \"muay_thai\",\n        \"mma\": \"mma\",\n        \"bjj\": \"bjj\",\n        \"wrestler\": \"wrestler\",\n        \"wrestling\": \"wrestler\",\n        \"grappler\": \"bjj\",\n        \"grappling\": \"bjj\",\n    }\n    return aliases.get(tech, str(selection_format or \"\").strip().lower())\n\n\ndef _style_exact_sport_bonus(raw_tags: list[str], athlete_sport_tag: str) -> float:\n    \"\"\"Return the small preference for a raw exact-sport style-bank match.\n\n    Raw bank tags are inspected before compatibility rewrites. The athlete sport\n    tag is deliberately distinct from the broader programming format.\n    \"\"\"\n    sport = str(athlete_sport_tag or \"\").strip().lower()\n    if not sport:\n        return 0.0\n    return STYLE_EXACT_SPORT_BONUS if sport in set(normalize_tags(raw_tags or [])) else 0.0\n''',
'helper replacement',
)

replace_once(
'''    fight_format = style_map.get(primary_tech, \"mma\")\n    selection_format = _normalize_fight_format(fight_format)\n    energy_weights = get_format_weights().get(selection_format, {})\n''',
'''    fight_format = style_map.get(primary_tech, \"mma\")\n    selection_format = _normalize_fight_format(fight_format)\n    specificity_sport_tag = _style_specificity_sport_tag(primary_tech, selection_format)\n    energy_weights = get_format_weights().get(selection_format, {})\n''',
'sport identity anchor',
)

replace_once(
'''                sport_specificity_bonus = _style_exact_sport_bonus(\n                    drill.get(\"tags\", []), selection_format\n                )\n''',
'''                sport_specificity_bonus = _style_exact_sport_bonus(\n                    drill.get(\"tags\", []), specificity_sport_tag\n                )\n''',
'scoring call anchor',
)

path.write_text(text, encoding='utf-8')

# Replace focused tests with explicit sport-vs-format coverage.
test_path = Path('tests/test_style_exact_sport_bonus.py')
t = test_path.read_text(encoding='utf-8')
t = t.replace(
'''def _flags(style: str, sport: str = \"mma\") -> dict:\n    technical = {\"mma\": \"mma\", \"boxing\": \"boxing\", \"kickboxing\": \"kickboxing\", \"muay_thai\": \"muay thai\"}[sport]\n''',
'''def _flags(style: str, sport: str = \"mma\", technical_style: str | None = None) -> dict:\n    technical = technical_style or {\"mma\": \"mma\", \"boxing\": \"boxing\", \"kickboxing\": \"kickboxing\", \"muay_thai\": \"muay thai\", \"bjj\": \"bjj\", \"wrestling\": \"wrestling\"}[sport]\n''')
t = t.replace(
'''def _run_pair(monkeypatch, style: str, sport: str = \"mma\", other_sport: str | None = None):\n    exact = _style_drill(f\"Exact {style}\", style, sport)\n    other = _style_drill(f\"Other {style}\", style, other_sport)\n    monkeypatch.setattr(conditioning, \"get_style_conditioning_bank\", lambda: [other, exact])\n    monkeypatch.setattr(conditioning, \"get_conditioning_bank\", lambda: [])\n    result = conditioning.generate_conditioning_block(_flags(style, sport))\n''',
'''def _run_pair(monkeypatch, style: str, sport: str = \"mma\", other_sport: str | None = None, technical_style: str | None = None):\n    exact_tag = conditioning._style_specificity_sport_tag(technical_style or sport, \"mma\" if sport in {\"bjj\", \"wrestling\"} else sport)\n    exact = _style_drill(f\"Exact {style}\", style, exact_tag)\n    other = _style_drill(f\"Other {style}\", style, other_sport)\n    monkeypatch.setattr(conditioning, \"get_style_conditioning_bank\", lambda: [other, exact])\n    monkeypatch.setattr(conditioning, \"get_conditioning_bank\", lambda: [])\n    result = conditioning.generate_conditioning_block(_flags(style, sport, technical_style=technical_style))\n''')
t = t.replace(
'''def test_raw_exact_sport_helper_uses_pre_rewrite_tags():\n    assert conditioning._style_exact_sport_bonus([\"boxing\", \"counter_striker\"], \"boxing\") == 0.5\n    assert conditioning._style_exact_sport_bonus([\"muay_thai\", \"counter_striker\"], \"boxing\") == 0.0\n    assert conditioning._style_exact_sport_bonus([\"kickboxing\", \"muay_thai\", \"brawler\"], \"kickboxing\") == 0.5\n    assert conditioning._style_exact_sport_bonus([\"kickboxing\", \"muay_thai\", \"brawler\"], \"muay_thai\") == 0.5\n    assert conditioning._style_exact_sport_bonus([\"brawler\"], \"mma\") == 0.0\n''',
'''def test_raw_exact_sport_helper_uses_pre_rewrite_tags():\n    assert conditioning._style_specificity_sport_tag(\"bjj\", \"mma\") == \"bjj\"\n    assert conditioning._style_specificity_sport_tag(\"wrestling\", \"mma\") == \"wrestler\"\n    assert conditioning._style_exact_sport_bonus([\"boxing\", \"counter_striker\"], \"boxing\") == 0.5\n    assert conditioning._style_exact_sport_bonus([\"muay_thai\", \"counter_striker\"], \"boxing\") == 0.0\n    assert conditioning._style_exact_sport_bonus([\"kickboxing\", \"muay_thai\", \"brawler\"], \"kickboxing\") == 0.5\n    assert conditioning._style_exact_sport_bonus([\"kickboxing\", \"muay_thai\", \"brawler\"], \"muay_thai\") == 0.5\n    assert conditioning._style_exact_sport_bonus([\"brawler\"], \"mma\") == 0.0\n''')

t += '''\n\ndef test_bjj_identity_is_preserved_when_programming_format_is_mma(monkeypatch):\n    exact, mma_drill, candidates, diagnostics = _run_pair(\n        monkeypatch, \"submission_hunter\", sport=\"bjj\", other_sport=\"mma\", technical_style=\"bjj\"\n    )\n    assert candidates[exact[\"name\"]][\"reasons\"][\"sport_specificity_bonus\"] == 0.5\n    assert candidates[mma_drill[\"name\"]][\"reasons\"][\"sport_specificity_bonus\"] == 0.0\n    assert candidates[exact[\"name\"]][\"score\"] == pytest.approx(candidates[mma_drill[\"name\"]][\"score\"] + 0.5)\n    assert diagnostics[\"entries_exact_sport_bonus_applied\"] == 1\n\n\ndef test_wrestling_identity_is_preserved_when_programming_format_is_mma(monkeypatch):\n    exact, mma_drill, candidates, diagnostics = _run_pair(\n        monkeypatch, \"wrestler\", sport=\"wrestling\", other_sport=\"mma\", technical_style=\"wrestling\"\n    )\n    assert candidates[exact[\"name\"]][\"reasons\"][\"sport_specificity_bonus\"] == 0.5\n    assert candidates[mma_drill[\"name\"]][\"reasons\"][\"sport_specificity_bonus\"] == 0.0\n    assert candidates[exact[\"name\"]][\"score\"] == pytest.approx(candidates[mma_drill[\"name\"]][\"score\"] + 0.5)\n    assert diagnostics[\"entries_exact_sport_bonus_applied\"] == 1\n\n\ndef test_mma_athlete_does_not_reward_bjj_specific_drill(monkeypatch):\n    exact, bjj_drill, candidates, _ = _run_pair(\n        monkeypatch, \"submission_hunter\", sport=\"mma\", other_sport=\"bjj\", technical_style=\"mma\"\n    )\n    assert candidates[exact[\"name\"]][\"reasons\"][\"sport_specificity_bonus\"] == 0.5\n    assert candidates[bjj_drill[\"name\"]][\"reasons\"][\"sport_specificity_bonus\"] == 0.0\n'''

test_path.write_text(t, encoding='utf-8')
