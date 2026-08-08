from pathlib import Path
import py_compile
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected one match, found {text.count(old)}")
    return text.replace(old, new, 1)


# 1) Final-week mapping tests: D-1..D-6 now obey the same declared
# availability contract as every other pre-fight day. D-0 is the only bypass.
path = Path("tests/test_final_week_weekday_mapping.py")
text = path.read_text()
text = replace_once(
    text,
    '''class TestCanRenderLateTaperDay:
    def test_d6_to_d0_ignore_declared_availability(self):
        assert can_render_late_taper_day(countdown_offset=6, weekday="monday", training_days=["tuesday"])
        assert can_render_late_taper_day(countdown_offset=1, weekday="saturday", training_days=["tuesday"])
        assert can_render_late_taper_day(countdown_offset=0, weekday="sunday", training_days=[])

    def test_d7_and_earlier_requires_training_day_match(self):''',
    '''class TestCanRenderLateTaperDay:
    def test_d1_to_d6_respect_declared_availability_but_d0_is_always_legal(self):
        assert can_render_late_taper_day(countdown_offset=6, weekday="monday", training_days=["tuesday"]) is False
        assert can_render_late_taper_day(countdown_offset=1, weekday="saturday", training_days=["tuesday"]) is False
        assert can_render_late_taper_day(countdown_offset=0, weekday="sunday", training_days=[])

    def test_d7_and_earlier_requires_training_day_match(self):''',
    "final-week availability bypass test",
)
text = replace_once(
    text,
    '''    def test_sequence_entries_lack_real_weekday_when_plan_creation_weekday_missing(self):
        athlete = _athlete(5)
        del athlete["plan_creation_weekday"]
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert len(sequence) >= 1
        for entry in sequence:
            assert "real_weekday" not in entry
''',
    '''    def test_sequence_does_not_invent_days_when_calendar_anchor_is_missing(self):
        athlete = _athlete(5)
        del athlete["plan_creation_weekday"]
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert sequence == []
''',
    "missing calendar anchor test",
)
text = replace_once(
    text,
    '''    def test_session_keeps_calendar_true_weekday_when_countdown_day_unavailable(self):
        # Plan creation = friday, fight = wednesday (5 days later)
        # D-5 lands on friday which IS available → stays friday
        athlete = _athlete(
            5,
            plan_creation_weekday="friday",
            training_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert sequence[0]["real_weekday"] == "sunday"
        assert sequence[0]["resolved_training_weekday"] == "monday"

    def test_display_label_keeps_raw_calendar_weekday(self):
        # Friday creation + 5 days = Wednesday fight, so D-3 is Sunday on the
        # raw calendar. Sunday is unavailable and must not leak into output.
        athlete = _athlete(
            5,
            plan_creation_weekday="friday",
            training_days=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        )
        sequence = _build_late_fight_session_sequence(5, athlete)
        freshness = next(entry for entry in sequence if entry["role_key"] == "fight_week_freshness_day")

        assert freshness["scheduled_countdown_label"] == "D-3"
        assert freshness["real_weekday"] == "sunday"
        assert freshness["resolved_training_weekday"] == "saturday"
        assert freshness["countdown_display_label"] == "D-3 (Sunday)"
''',
    '''    def test_unavailable_countdown_day_is_skipped_not_remapped(self):
        # Friday creation + five days means D-3 is Sunday. Sunday is not an
        # available training day, so no app-owned role may be moved from D-3
        # onto Monday while retaining the D-3 label.
        athlete = _athlete(
            5,
            plan_creation_weekday="friday",
            training_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert sequence
        assert all(entry.get("scheduled_countdown_label") != "D-3" for entry in sequence)
        assert all("resolved_training_weekday" not in entry for entry in sequence)

    def test_display_labels_only_use_real_available_countdown_weekdays(self):
        athlete = _athlete(
            5,
            plan_creation_weekday="friday",
            training_days=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        )
        sequence = _build_late_fight_session_sequence(5, athlete)
        assert all(entry.get("scheduled_countdown_label") != "D-3" for entry in sequence)
        assert all("resolved_training_weekday" not in entry for entry in sequence)
        assert all(
            entry.get("countdown_display_label")
            == f'{entry["scheduled_countdown_label"]} ({entry["real_weekday"].title()})'
            for entry in sequence
            if entry.get("scheduled_countdown_label") and entry.get("real_weekday")
        )
''',
    "nearest-day remap tests",
)
path.write_text(text)


# 2) The old countdown-based Tactical Watch phase assertion is obsolete.
# Dedicated phase-authority tests now prove D-8 can be TAPER and D-6 can be SPP.
path = Path("tests/test_tactical_watch_bank_v2.py")
text = path.read_text()
pattern = r'''\ndef test_late_fight_watch_phase_follows_the_countdown\(\):\n.*?(?=\ndef test_late_fight_watch_is_never_scheduled_on_fight_day\(\):)'''
text, count = re.subn(pattern, "\n", text, count=1, flags=re.S)
if count != 1:
    raise RuntimeError(f"stale Tactical Watch countdown-phase test: replaced {count}")
path.write_text(text)


# 3) Calendar/availability regression assertions must not preserve the old
# fight-week bypass. Monday/Saturday/Sunday remain unavailable when only
# Tue/Wed/Thu are declared.
path = Path("tests/test_stage2_payload_late_fight_roles.py")
text = path.read_text()
text = replace_once(text, '    assert "D-6" in role_by_label\n    assert "D-1" in role_by_label\n', '    assert "D-6" not in role_by_label\n    assert "D-1" not in role_by_label\n', "D6/D1 availability assertions")
text = replace_once(text, '    assert "D-6" in policy["eligible_countdown_labels"]\n', '    assert "D-6" not in policy["eligible_countdown_labels"]\n', "permission policy D6 assertion")
text = replace_once(text, '    assert "D-6" in labels\n\n    countdown_map', '    assert "D-6" not in labels\n\n    countdown_map', "composite D6 assertion")
text = replace_once(
    text,
    '            assert offset <= 6 or weekday in {"tuesday", "wednesday", "thursday"}\n',
    '            assert weekday in {"tuesday", "wednesday", "thursday"}\n',
    "fight-week bypass assertion",
)
path.write_text(text)


# 4) A Wednesday-only athlete may legitimately have an empty sub-window when
# that countdown slice contains no Wednesday. The invariant is no manufactured
# unavailable day, not "every sub-window must contain app work".
path = Path("tests/test_late_fight_calendar_regression.py")
text = path.read_text()
old = '''@pytest.mark.parametrize("profile", list(_PROFILE_BUILDERS))
@pytest.mark.parametrize("days_until_fight", list(range(1, 22)))
def test_no_active_window_resolves_to_zero_sessions(profile, days_until_fight):
    # Every active late-fight window (D-1..D-21) must place at least one
    # app-owned session for every athlete shape. D-0 is the only legitimately
    # empty active mode and is excluded from the sweep.
    athlete = _PROFILE_BUILDERS[profile](days_until_fight)
    roles = _late_fight_allocation_plan(days_until_fight, athlete).get("session_roles", [])
    assert roles, f"{profile} D-{days_until_fight} resolved to an empty active window"
    app_owned = [r for r in roles if _is_app_owned_visible_role(r.get("role_key"))]
    assert app_owned, f"{profile} D-{days_until_fight} placed no app-owned session"
'''
new = '''@pytest.mark.parametrize("profile", ["pro_pressure_mon_thu", "all_days"])
@pytest.mark.parametrize("days_until_fight", list(range(1, 22)))
def test_active_window_keeps_required_app_work_when_legal_days_exist(profile, days_until_fight):
    athlete = _PROFILE_BUILDERS[profile](days_until_fight)
    roles = _late_fight_allocation_plan(days_until_fight, athlete).get("session_roles", [])
    assert roles, f"{profile} D-{days_until_fight} resolved to an empty active window"
    app_owned = [r for r in roles if _is_app_owned_visible_role(r.get("role_key"))]
    assert app_owned, f"{profile} D-{days_until_fight} placed no app-owned session"


@pytest.mark.parametrize("days_until_fight", list(range(1, 22)))
def test_sparse_availability_never_manufactures_an_unavailable_app_day(days_until_fight):
    athlete = _sparse_boxer(days_until_fight)
    roles = _late_fight_allocation_plan(days_until_fight, athlete).get("session_roles", [])
    for role in roles:
        if not _is_app_owned_visible_role(role.get("role_key")):
            continue
        weekday = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip().lower()
        assert weekday == "wednesday"
'''
text = replace_once(text, old, new, "sparse active-window invariant")
path.write_text(text)


# 5) #2230 made Fight Tactical Watch mandatory. Tests that still expect the
# legacy cue-card filler should assert the actual mandatory role instead.
path = Path("tests/test_stage2_payload_modes.py")
text = path.read_text()
text = text.replace('            "tactical_cue_card",\n', '            "tactical_watch",\n', 1)
text = text.replace('        assert [entry["role_key"] for entry in app_sequence] == ["tactical_cue_card"]\n', '        assert [entry["role_key"] for entry in app_sequence] == ["tactical_watch"]\n', 1)
path.write_text(text)

path = Path("tests/test_stage2_planning_brief.py")
text = path.read_text()
text = replace_once(
    text,
    '''    assert roles_from_seq == [
        "tactical_cue_card",
        "fight_week_freshness_day",
        "neural_primer_day",
    ]
    support_entries = [
        entry
        for entry in brief["late_fight_session_sequence"]
        if entry["role_key"] == "tactical_cue_card"
    ]''',
    '''    assert roles_from_seq == [
        "tactical_watch",
        "fight_week_freshness_day",
        "neural_primer_day",
    ]
    support_entries = [
        entry
        for entry in brief["late_fight_session_sequence"]
        if entry["role_key"] == "tactical_watch"
    ]''',
    "D5 mandatory Tactical Watch expectation",
)
text = replace_once(
    text,
    '''    assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]] == [
        "fight_week_freshness_day",
        "neural_primer_day",
    ]''',
    '''    assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]] == [
        "fight_week_freshness_day",
        "tactical_watch",
        "neural_primer_day",
    ]''',
    "D3 mandatory Tactical Watch expectation",
)
path.write_text(text)


for filename in (
    "tests/test_final_week_weekday_mapping.py",
    "tests/test_tactical_watch_bank_v2.py",
    "tests/test_stage2_payload_late_fight_roles.py",
    "tests/test_late_fight_calendar_regression.py",
    "tests/test_stage2_payload_modes.py",
    "tests/test_stage2_planning_brief.py",
):
    py_compile.compile(filename, doraise=True)
