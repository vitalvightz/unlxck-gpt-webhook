from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise SystemExit(f"follow-up-2 anchor not found in {path}: {old[:140]!r}")
    target.write_text(text.replace(old, new, 1))


# Keep hyphenated exercise names intact while separating the rendered dose.
replace_once(
    "fightcamp/stage2_validator.py",
    '''    match = re.split(r"\\s+(?:[-–—]|:)\\s+|,|\\(", cleaned, maxsplit=1)\n''',
    '''    match = re.split(r"\\s+[-–—]\\s+|:\\s*|,|\\(", cleaned, maxsplit=1)\n''',
)


# Prove a repair-like second strength role cannot bypass the one-exposure rule
# when the final calendar has no safe ALLOW destination. Goal repair re-enters
# apply_late_camp_role_morph(), so this exercises the same lifecycle it uses.
tests = Path("tests/test_pre_hard_contact_strength.py")
text = tests.read_text()
old = '''def test_repair_like_second_strength_role_is_recompressed_by_final_morph() -> None:\n    weekly = _map()\n    apply_late_camp_role_morph(weekly)\n    week = weekly["weeks"][0]\n    assert _role(weekly)["scheduled_day_hint"] == "Thursday"\n\n    week["session_roles"].append(\n        _strength("Monday", session_index=2, strength_session_index=2)\n    )\n    apply_late_camp_role_morph(weekly)\n\n    strength_roles = [\n        role for role in week["session_roles"] if role.get("category") == "strength"\n    ]\n    assert len(strength_roles) == 1\n    assert strength_roles[0]["role_key"] == "primary_strength_day"\n    assert strength_roles[0]["scheduled_day_hint"] == "Thursday"\n    assert any(\n        PRE_HARD_CONTACT_STRENGTH_CAP_REASON\n        in (row.get("compression_reason_codes") or [])\n        for row in week.get("suppressed_roles") or []\n    )\n'''
new = '''def test_repair_like_second_strength_role_is_recompressed_by_final_morph() -> None:\n    weekly = _map()\n    week = weekly["weeks"][0]\n    week["declared_training_days"] = ["Monday", "Tuesday"]\n    week["calendar_days"] = _calendar(("Monday", 23), ("Tuesday", 22))\n\n    apply_late_camp_role_morph(weekly)\n    assert _role(weekly)["pre_hard_contact_managed_stress"] is True\n\n    # Simulate a retained goal-repair candidate being appended after the first\n    # resolved pass. The repair trial calls the same morph again.\n    week["session_roles"].append(\n        _strength("Monday", session_index=2, strength_session_index=2)\n    )\n    apply_late_camp_role_morph(weekly)\n\n    strength_roles = [\n        role for role in week["session_roles"] if role.get("category") == "strength"\n    ]\n    assert len(strength_roles) == 1\n    assert strength_roles[0]["role_key"] == "primary_strength_day"\n    assert strength_roles[0]["pre_hard_contact_managed_stress"] is True\n    policy = week["pre_hard_contact_strength_policy"]\n    assert policy["active"] is True\n    assert policy["max_meaningful_strength_exposures"] == 1\n'''
if old not in text:
    raise SystemExit("repair-like constrained-calendar regression anchor not found")
tests.write_text(text.replace(old, new, 1))
