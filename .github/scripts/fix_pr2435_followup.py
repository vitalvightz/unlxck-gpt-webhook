from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise SystemExit(f"follow-up anchor not found in {path}: {old[:140]!r}")
    target.write_text(text.replace(old, new, 1))


# The pre-hard consequence runs after final calendar integrity. If it suppresses
# a role, refresh the semantic-intent summary on the surviving role set before
# downstream prescription/goal reconciliation consumes it.
replace_once(
    "fightcamp/late_camp_role_morph.py",
    '''    weekly_role_map = apply_final_calendar_integrity(\n        weekly_role_map,\n        remorph_callback=_apply_late_camp_role_morph_once,\n    )\n    # The pre-hard-contact consequence depends on the finished calendar, not an\n    # earlier placement guess. Running it here also makes goal-repair trials pass\n    # through the same one-strength-exposure policy before dose resolution.\n    return apply_pre_hard_contact_strength_exposure_cap(weekly_role_map)\n''',
    '''    weekly_role_map = apply_final_calendar_integrity(\n        weekly_role_map,\n        remorph_callback=_apply_late_camp_role_morph_once,\n    )\n    # The pre-hard-contact consequence depends on the finished calendar, not an\n    # earlier placement guess. Running it here also makes goal-repair trials pass\n    # through the same one-strength-exposure policy before dose resolution.\n    apply_pre_hard_contact_strength_exposure_cap(weekly_role_map)\n    # The helper may suppress an extra strength role. Refresh the deterministic\n    # semantic summary against the surviving role set; this is dose/metadata only\n    # and does not reopen calendar placement.\n    return _apply_late_camp_role_morph_once(weekly_role_map)\n''',
)


# Make repeated evaluation safe for surviving roles: a prior pre-hard marker must
# not survive if a later finished calendar no longer has the next-day condition.
helper = Path("fightcamp/pre_hard_contact_strength.py")
text = helper.read_text()
anchor = '''        strength_roles = [role for role in roles if str(role.get("category") or "").strip().lower() == "strength"]\n        if not strength_roles:\n            continue\n\n        affected: list[dict[str, Any]] = []\n'''
replacement = '''        strength_roles = [role for role in roles if str(role.get("category") or "").strip().lower() == "strength"]\n        if not strength_roles:\n            week.pop("pre_hard_contact_strength_policy", None)\n            continue\n\n        # Recompute from the finished calendar on every invocation. These fields\n        # are derived state, not sticky readiness state.\n        week.pop("pre_hard_contact_strength_policy", None)\n        for role in strength_roles:\n            for field in (\n                "pre_hard_contact_managed_stress",\n                "pre_hard_contact_effective_hard_distance",\n                "pre_hard_contact_reason_code",\n                "pre_hard_contact_dose_adjustment",\n            ):\n                role.pop(field, None)\n\n        affected: list[dict[str, Any]] = []\n'''
if anchor not in text:
    raise SystemExit("pre-hard derived-state cleanup anchor not found")
helper.write_text(text.replace(anchor, replacement, 1))


# Existing parser accidentally strips any hyphenated first word (e.g.
# Single-Leg -> Leg). Only weekday prefixes are legitimate prefixes here.
replace_once(
    "fightcamp/stage2_validator.py",
    '''    cleaned = re.sub(r"^\\(?[A-Za-z]{2,9}\\)?\\s*[-:]\\s*", "", cleaned).strip()\n''',
    '''    cleaned = re.sub(\n        rf"^\\(?(?:{_COUNTDOWN_CONTRACT_WEEKDAY})\\)?\\s*[-:]\\s*",\n        "",\n        cleaned,\n        flags=re.IGNORECASE,\n    ).strip()\n''',
)


# A complete session S&C allow-list is complete. Generic late-fight-safe exercise
# phrasing is not an exemption from this normal-camp resolved selection contract.
replace_once(
    "fightcamp/stage2_validator.py",
    '''                        if not _late_fight_line_is_exercise_like(rendered_line):\n                            continue\n                        if _late_fight_line_is_generic_allowed(rendered_line):\n                            continue\n                        rendered_label = _rendered_exercise_label(rendered_line)\n''',
    '''                        if not _late_fight_line_is_exercise_like(rendered_line):\n                            continue\n                        rendered_label = _rendered_exercise_label(rendered_line)\n''',
)


# Replace the first lifecycle regression: final integrity should first use a safe
# ALLOW destination when one exists. The cap applies only when DEPRIORITIZE is the
# final legal state because no ALLOW destination exists.
tests = Path("tests/test_pre_hard_contact_strength.py")
text = tests.read_text()
old = '''def test_pre_hard_policy_runs_after_final_calendar_integrity_via_morph() -> None:\n    weekly = _map()\n    apply_late_camp_role_morph(weekly)\n    role = _role(weekly)\n    assert role["pre_hard_contact_managed_stress"] is True\n    assert role["pre_hard_contact_effective_hard_distance"] == 1\n'''
new = '''def test_final_integrity_relocates_pre_hard_strength_when_allow_destination_exists() -> None:\n    weekly = _map()\n    apply_late_camp_role_morph(weekly)\n    role = _role(weekly)\n    assert role["scheduled_day_hint"] == "Thursday"\n    assert "pre_hard_contact_managed_stress" not in role\n\n\ndef test_pre_hard_policy_applies_after_final_integrity_when_no_allow_destination_exists() -> None:\n    weekly = _map()\n    week = weekly["weeks"][0]\n    week["declared_training_days"] = ["Monday", "Tuesday"]\n    week["calendar_days"] = _calendar(("Monday", 23), ("Tuesday", 22))\n    apply_late_camp_role_morph(weekly)\n    role = _role(weekly)\n    assert role["scheduled_day_hint"] == "Monday"\n    assert role["pre_hard_contact_managed_stress"] is True\n    assert role["pre_hard_contact_effective_hard_distance"] == 1\n'''
if old not in text:
    raise SystemExit("lifecycle regression anchor not found")
text = text.replace(old, new, 1)


# Simulate a later goal-repair candidate being appended on the pre-hard day after
# the canonical primary was already moved to the safe day. A second morph must
# route the trial through the same cap and suppress that second exposure.
old = '''def test_repair_like_second_strength_role_is_recompressed_by_final_morph() -> None:\n    weekly = _map()\n    apply_late_camp_role_morph(weekly)\n    week = weekly["weeks"][0]\n    week["session_roles"].append(\n        _strength("Thursday", session_index=2, strength_session_index=2)\n    )\n    apply_late_camp_role_morph(weekly)\n    strength_roles = [\n        role for role in week["session_roles"] if role.get("category") == "strength"\n    ]\n    assert len(strength_roles) == 1\n    assert strength_roles[0]["role_key"] == "primary_strength_day"\n    assert any(\n        PRE_HARD_CONTACT_STRENGTH_CAP_REASON\n        in (row.get("compression_reason_codes") or [])\n        for row in week.get("suppressed_roles") or []\n    )\n'''
new = '''def test_repair_like_second_strength_role_is_recompressed_by_final_morph() -> None:\n    weekly = _map()\n    apply_late_camp_role_morph(weekly)\n    week = weekly["weeks"][0]\n    assert _role(weekly)["scheduled_day_hint"] == "Thursday"\n\n    week["session_roles"].append(\n        _strength("Monday", session_index=2, strength_session_index=2)\n    )\n    apply_late_camp_role_morph(weekly)\n\n    strength_roles = [\n        role for role in week["session_roles"] if role.get("category") == "strength"\n    ]\n    assert len(strength_roles) == 1\n    assert strength_roles[0]["role_key"] == "primary_strength_day"\n    assert strength_roles[0]["scheduled_day_hint"] == "Thursday"\n    assert any(\n        PRE_HARD_CONTACT_STRENGTH_CAP_REASON\n        in (row.get("compression_reason_codes") or [])\n        for row in week.get("suppressed_roles") or []\n    )\n'''
if old not in text:
    raise SystemExit("repair-like regression anchor not found")
text = text.replace(old, new, 1)
tests.write_text(text)
