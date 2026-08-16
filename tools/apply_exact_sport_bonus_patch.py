from pathlib import Path


path = Path("fightcamp/conditioning.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 anchor, found {count}")
    text = text.replace(old, new, 1)


if "STYLE_EXACT_SPORT_BONUS = 0.5" not in text:
    replace_once(
        "PREFERRED_EXERCISE_NAME_BOOST = 3.0\n",
        "PREFERRED_EXERCISE_NAME_BOOST = 3.0\nSTYLE_EXACT_SPORT_BONUS = 0.5\n",
        "constant anchor",
    )

    helper_anchor = '''def _conditioning_clarification_bonus(tags: list[str], derived_clarification_tags: list[str]) -> tuple[float, list[str]]:\n    if not derived_clarification_tags:\n        return 0.0, []\n    hits = sorted(set(tags).intersection(derived_clarification_tags))\n    if not hits:\n        return 0.0, []\n    bonus = min(len(hits) * CONDITIONING_CLARIFICATION_TAG_BONUS, CONDITIONING_MAX_CLARIFICATION_TAG_BONUS)\n    return bonus, hits\n'''
    helper_replacement = helper_anchor + '''\n\ndef _style_exact_sport_bonus(raw_tags: list[str], selection_format: str) -> float:\n    \"\"\"Return the small preference for a raw exact-sport style-bank match.\n\n    Raw bank tags are inspected before compatibility rewrites so a rewritten\n    Muay Thai tag cannot masquerade as a native boxing tag.\n    \"\"\"\n    sport = str(selection_format or \"\").strip().lower()\n    if not sport:\n        return 0.0\n    return STYLE_EXACT_SPORT_BONUS if sport in set(normalize_tags(raw_tags or [])) else 0.0\n'''
    replace_once(helper_anchor, helper_replacement, "helper anchor")

    replace_once(
        '        "entries_scored": 0,\n        "entries_selected": 0,\n',
        '        "entries_scored": 0,\n        "entries_exact_sport_bonus_applied": 0,\n        "entries_selected": 0,\n        "final_selected_exact_sport_names": [],\n',
        "diagnostics anchor",
    )

    replace_once(
        "            for drill in style_conditioning_bank:\n                d = drill.copy()\n",
        "            for drill in style_conditioning_bank:\n                # Compute specificity before any runtime sport-tag compatibility rewrite.\n                sport_specificity_bonus = _style_exact_sport_bonus(\n                    drill.get(\"tags\", []), selection_format\n                )\n                d = drill.copy()\n",
        "raw sport anchor",
    )

    replace_once(
        "                score += equip_bonus\n                score += _conditioning_collision_safe_priority_bonus(\n",
        "                score += equip_bonus\n                score += sport_specificity_bonus\n                if sport_specificity_bonus:\n                    style_conditioning_diagnostics[\"entries_exact_sport_bonus_applied\"] += 1\n                score += _conditioning_collision_safe_priority_bonus(\n",
        "score anchor",
    )

    replace_once(
        '                    "equipment_boost": equip_bonus,\n                    "preferred_exercise_name_match": PREFERRED_EXERCISE_NAME_BOOST if preferred_name_match else 0.0,\n',
        '                    "equipment_boost": equip_bonus,\n                    "sport_specificity_bonus": sport_specificity_bonus,\n                    "exact_sport_match": bool(sport_specificity_bonus),\n                    "preferred_exercise_name_match": PREFERRED_EXERCISE_NAME_BOOST if preferred_name_match else 0.0,\n',
        "reason metadata anchor",
    )

    replace_once(
        '                if preferred_name_match:\n                    reasons["reason_codes"].append(f"preferred_exercise_name_match:+{PREFERRED_EXERCISE_NAME_BOOST:.1f}")\n\n                entry = (d, score, reasons)\n',
        '                if preferred_name_match:\n                    reasons["reason_codes"].append(f"preferred_exercise_name_match:+{PREFERRED_EXERCISE_NAME_BOOST:.1f}")\n                if sport_specificity_bonus:\n                    reasons["reason_codes"].append(\n                        f"exact_sport_match:+{STYLE_EXACT_SPORT_BONUS:.1f}"\n                    )\n\n                entry = (d, score, reasons)\n',
        "reason code anchor",
    )

    replace_once(
        '    if reasons.get("equipment_boost"):\n        parts.append("equipment boost")\n    if reasons.get("load_adjustments"):\n',
        '    if reasons.get("equipment_boost"):\n        parts.append("equipment boost")\n    if reasons.get("sport_specificity_bonus"):\n        parts.append("exact sport match")\n    if reasons.get("load_adjustments"):\n',
        "explanation anchor",
    )

    replace_once(
        '    style_conditioning_diagnostics["entries_selected"] = len(final_style_conditioning_names)\n    style_conditioning_diagnostics["final_selected_style_conditioning_names"] = final_style_conditioning_names\n',
        '    style_conditioning_diagnostics["entries_selected"] = len(final_style_conditioning_names)\n    style_conditioning_diagnostics["final_selected_style_conditioning_names"] = final_style_conditioning_names\n    style_conditioning_diagnostics["final_selected_exact_sport_names"] = [\n        name\n        for name in final_style_conditioning_names\n        if reason_lookup.get(name, {}).get("sport_specificity_bonus", 0) > 0\n    ]\n',
        "selected diagnostics anchor",
    )

    path.write_text(text, encoding="utf-8")


test_path = Path("tests/test_style_exact_sport_bonus.py")
test_path.write_text('''import pytest\n\nfrom fightcamp import conditioning\n\n\nTACTICAL_STYLES = (\n    "distance_striker",\n    "counter_striker",\n    "pressure_fighter",\n    "brawler",\n    "clinch_fighter",\n    "kicker",\n    "wrestler",\n    "grappler",\n    "scrambler",\n    "submission_hunter",\n)\n\n\ndef _style_drill(name: str, style: str, sport: str | None) -> dict:\n    tags = [style]\n    if sport:\n        tags.insert(0, sport)\n    return {\n        "name": name,\n        "equipment": ["bodyweight"],\n        "phases": ["GPP", "SPP"],\n        "system": "aerobic",\n        "modality": "controlled technical conditioning",\n        "duration": "180s work / 60s rest x 3 rounds",\n        "intensity": "moderate",\n        "tags": tags,\n        "notes": "Sustainable technical conditioning with clean mechanics.",\n        "equipment_note": "Bodyweight only.",\n        "work_sec": 180,\n        "rest_sec": 60,\n        "rounds": 3,\n        "rpe": 5,\n        "impact_cost": "low",\n        "lactate_load": "low",\n        "movement_cost": "low",\n        "mechanical_risk_tags": [],\n    }\n\n\ndef _flags(style: str, sport: str = "mma") -> dict:\n    technical = {"mma": "mma", "boxing": "boxing", "kickboxing": "kickboxing", "muay_thai": "muay thai"}[sport]\n    return {\n        "phase": "GPP",\n        "sport": sport,\n        "style_technical": [technical],\n        "style_tactical": [style.replace("_", " ")],\n        "key_goals": ["conditioning"],\n        "weaknesses": [],\n        "fatigue": "low",\n        "equipment": [],\n        "training_frequency": 2,\n        "days_available": 2,\n        "days_until_fight": 35,\n        "time_to_fight_days": 35,\n        "injuries": [],\n        "restrictions": [],\n    }\n\n\ndef _run_pair(monkeypatch, style: str, sport: str = "mma", other_sport: str | None = None):\n    exact = _style_drill(f"Exact {style}", style, sport)\n    other = _style_drill(f"Other {style}", style, other_sport)\n    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [other, exact])\n    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [])\n    result = conditioning.generate_conditioning_block(_flags(style, sport))\n    reservoir = result[5]\n    candidates = {\n        entry["drill"]["name"]: entry\n        for entry in reservoir.get("aerobic", [])\n        if entry.get("drill", {}).get("name") in {exact["name"], other["name"]}\n    }\n    return exact, other, candidates, reservoir["__style_conditioning__"]\n\n\ndef test_raw_exact_sport_helper_uses_pre_rewrite_tags():\n    assert conditioning._style_exact_sport_bonus(["boxing", "counter_striker"], "boxing") == 0.5\n    assert conditioning._style_exact_sport_bonus(["muay_thai", "counter_striker"], "boxing") == 0.0\n    assert conditioning._style_exact_sport_bonus(["kickboxing", "muay_thai", "brawler"], "kickboxing") == 0.5\n    assert conditioning._style_exact_sport_bonus(["kickboxing", "muay_thai", "brawler"], "muay_thai") == 0.5\n    assert conditioning._style_exact_sport_bonus(["brawler"], "mma") == 0.0\n\n\n@pytest.mark.parametrize("style", TACTICAL_STYLES)\ndef test_exact_sport_bonus_is_global_across_all_tactical_styles(monkeypatch, style):\n    exact, other, candidates, diagnostics = _run_pair(monkeypatch, style)\n    assert set(candidates) == {exact["name"], other["name"]}\n    exact_entry = candidates[exact["name"]]\n    other_entry = candidates[other["name"]]\n    assert exact_entry["score"] == pytest.approx(other_entry["score"] + 0.5)\n    assert exact_entry["reasons"]["sport_specificity_bonus"] == 0.5\n    assert exact_entry["reasons"]["exact_sport_match"] is True\n    assert "exact_sport_match:+0.5" in exact_entry["reasons"]["reason_codes"]\n    assert other_entry["reasons"]["sport_specificity_bonus"] == 0.0\n    assert other_entry["reasons"]["exact_sport_match"] is False\n    assert diagnostics["entries_exact_sport_bonus_applied"] == 1\n    assert exact["name"] in diagnostics["final_selected_style_conditioning_names"]\n    assert exact["name"] in diagnostics["final_selected_exact_sport_names"]\n\n\ndef test_cross_sport_tie_is_broken_by_exact_sport(monkeypatch):\n    exact, other, candidates, _ = _run_pair(monkeypatch, "counter_striker", "mma", "boxing")\n    assert candidates[exact["name"]]["score"] == pytest.approx(candidates[other["name"]]["score"] + 0.5)\n\n\ndef test_boxing_runtime_rewrite_cannot_fake_exact_sport_bonus(monkeypatch):\n    exact, converted, candidates, diagnostics = _run_pair(monkeypatch, "counter_striker", "boxing", "muay_thai")\n    assert set(candidates) == {exact["name"], converted["name"]}\n    assert candidates[exact["name"]]["reasons"]["sport_specificity_bonus"] == 0.5\n    assert candidates[converted["name"]]["reasons"]["sport_specificity_bonus"] == 0.0\n    assert candidates[exact["name"]]["score"] == pytest.approx(candidates[converted["name"]]["score"] + 0.5)\n    assert diagnostics["entries_exact_sport_bonus_applied"] == 1\n''', encoding="utf-8")
