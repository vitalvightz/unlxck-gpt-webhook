from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


role_map = "fightcamp/stage2_role_map.py"

# A resolved sparring plan with zero effective hard days is authoritative. The
# old ``effective(...) or declared`` fallback silently turned technical-only
# contact back into hard-load pressure.
replace_once(
    role_map,
    "    return training_days, hard_sparring, support_work\n\n\ndef _append_day_hint",
    '''    return training_days, hard_sparring, support_work\n\n\ndef _resolved_effective_hard_days(\n    hard_sparring_plan: list[dict] | None,\n    declared_hard_days: set[str] | list[str],\n) -> set[str]:\n    """Resolve hard-load days without confusing technical contact with hard sparring.\n\n    When a resolved hard-sparring plan is present, even an empty effective set is\n    authoritative: D-17 technical-only conversions still own their calendar days\n    but are no longer hard-load exposures. Legacy/direct callers without a\n    resolved plan retain the declared-day fallback.\n    """\n    if hard_sparring_plan is not None:\n        return set(effective_hard_days(hard_sparring_plan))\n    return set(declared_hard_days)\n\n\ndef _append_day_hint''',
)

replace_once(
    role_map,
    '    effective_hard_days_set = set(effective_hard_days(hard_sparring_plan or [])) or set(hard_sparring_days)',
    '''    effective_hard_days_set = _resolved_effective_hard_days(\n        hard_sparring_plan,\n        hard_sparring_days,\n    )''',
)

# Phase guardrails say ``primary_strength`` semantically, while execution roles
# are named neural_plus_strength_day / neural_primer_day etc. Make that must-keep
# token real instead of letting those roles rank as ordinary strength.
replace_once(
    role_map,
    '''    # Must-keep roles always survive compression\n    if preferred_system in must_keep or role_key in must_keep:\n        return 100''',
    '''    # Must-keep roles always survive compression. ``primary_strength`` is a\n    # semantic phase requirement rather than a literal execution role key.\n    if "primary_strength" in must_keep and role_key in _PRIMARY_STRENGTH_ROLE_KEYS:\n        return 100\n    if preferred_system in must_keep or role_key in must_keep:\n        return 100''',
)

# Keep declared contact in the frequency/calendar budget, but derive hard-load
# pressure from the resolved effective plan.
replace_once(
    role_map,
    '''    hard_sparring_days_set = set(_ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))))\n    sessions_per_week = int(athlete_model.get("training_frequency") or len(training_days))''',
    '''    hard_sparring_days_set = set(_ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", []))))\n    effective_hard_sparring_days_set = _resolved_effective_hard_days(\n        hard_sparring_plan,\n        hard_sparring_days_set,\n    )\n    sessions_per_week = int(athlete_model.get("training_frequency") or len(training_days))''',
)

# At D-17 inward the countdown rule has already reduced declared hard contact to
# technical-only. If proximity is the *only* readiness compression signal, do
# not subtract another programmed slot on top of that contact downgrade. Real
# fatigue/cut/injury pressure still produces compression > 1 and is unchanged.
replace_once(
    role_map,
    '''    compression_floor = compute_integrated_compression_floor(\n        base_floor=_compression_floor_value(compression),\n        week_entry=week_entry,\n        athlete_model=athlete_model,\n    )\n\n    # Step 3: Compute target number of non-sparring active sessions''',
    '''    compression_floor = compute_integrated_compression_floor(\n        base_floor=_compression_floor_value(compression),\n        week_entry=week_entry,\n        athlete_model=athlete_model,\n    )\n\n    days_to_fight = athlete_model.get("days_until_fight")\n    if (\n        hard_sparring_plan is not None\n        and locked_spar_days\n        and not effective_hard_sparring_days_set\n        and isinstance(days_to_fight, int)\n        and 0 <= days_to_fight <= 17\n        and compression == 1\n    ):\n        compression_floor = 0\n\n    # Step 3: Compute target number of non-sparring active sessions''',
)

replace_once(
    role_map,
    '    is_hard_spar_week = len(hard_sparring_days_set) >= 2',
    '''    # Technical-only contact still occupies its declared calendar slot, but\n    # only effective hard sparring drives hard-week ranking and reason codes.\n    is_hard_spar_week = len(effective_hard_sparring_days_set) >= 2''',
)

# Regression: exact schedule geometry that #2383's one-contact fixture did not
# cover. Exercise names remain deliberately unconstrained.
tests = Path("tests/test_late_camp_architecture_cliff.py")
test_text = tests.read_text()
if "class TestTwoDeclaredContactLateCampRegression:" in test_text:
    raise SystemExit("two-contact regression tests already present")
test_text += r'''


# --------------------------------------------------------------------------- #
# C. TWO DECLARED CONTACT DAYS AFTER D-17 DOWNGRADE
# --------------------------------------------------------------------------- #

class TestTwoDeclaredContactLateCampRegression:
    """D-17..D-14 normal-camp regression with Tue/Fri declared contact."""

    @staticmethod
    def _case(days, monkeypatch):
        return _run(
            days,
            monkeypatch,
            availability="Monday, Tuesday, Wednesday, Thursday, Friday",
            hard_sparring="Tuesday, Friday",
            frequency="4",
            weight="88",
            target_weight="88",
            fatigue="low",
            key_goals="speed",
            primary_goal="speed",
            weak="footwork, power",
            primary_weak="footwork",
        )

    @pytest.mark.parametrize("days", [17, 16, 15, 14])
    def test_downgraded_contact_is_not_counted_as_two_hard_days(self, days, monkeypatch):
        brief = self._case(days, monkeypatch)
        for week in _weeks(brief):
            hard_plan = week.get("hard_sparring_plan") or []
            if not hard_plan:
                continue
            assert week.get("effective_hard_sparring_days") == []
            reason_codes = set((week.get("intentional_compression") or {}).get("reason_codes") or [])
            for suppressed in week.get("suppressed_roles") or []:
                reason_codes.update(suppressed.get("compression_reason_codes") or [])
            assert "two_hard_spar_days" not in reason_codes

    def test_d16_keeps_strength_and_alactic_sharpness_without_inflating_frequency(self, monkeypatch):
        brief = self._case(16, monkeypatch)
        weeks = {str(week.get("phase") or "").upper(): week for week in _weeks(brief)}
        spp = weeks["SPP"]
        taper = weeks["TAPER"]

        spp_core = [
            role for role in spp.get("session_roles") or []
            if role.get("category") in {"strength", "conditioning", "recovery"}
        ]
        taper_core = [
            role for role in taper.get("session_roles") or []
            if role.get("category") in {"strength", "conditioning", "recovery"}
        ]

        assert any(role.get("category") == "strength" for role in spp_core)
        assert any(role.get("category") == "conditioning" for role in spp_core)
        assert any(role.get("role_key") == "neural_primer_day" for role in taper_core)
        assert any(role.get("preferred_system") == "alactic" for role in taper_core)

        # Tuesday/Friday remain declared contact ownership, so the two app-owned
        # sessions must fit the other legal days. Two contact appointments + two
        # programmed sessions = requested frequency four; no volume inflation.
        for week, core_roles in ((spp, spp_core), (taper, taper_core)):
            assert len(core_roles) <= 2
            for role in core_roles:
                assert str(role.get("scheduled_day_hint") or "").strip().lower() not in {"tuesday", "friday"}
'''
tests.write_text(test_text)
