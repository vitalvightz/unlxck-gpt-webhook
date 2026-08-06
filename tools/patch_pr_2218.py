from pathlib import Path


PLANNER_PATH = Path("fightcamp/stage2_payload_late_fight.py")
TEST_PATH = Path("tests/test_late_fight_calendar_regression.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_planner() -> None:
    planner = PLANNER_PATH.read_text()

    planner = replace_once(
        planner,
        '''def _late_fight_hard_sparring_plan(
    *,
    days_until_fight: Any,
    athlete_model: dict[str, Any],
    declared_hard_days: list[str] | None = None,
    phase: str = "TAPER",
    stage_key: str = "late_fight_window",
    week_index: int = 1,
) -> list[dict[str, Any]]:''',
        '''def _late_fight_hard_sparring_plan(
    *,
    days_until_fight: Any,
    athlete_model: dict[str, Any],
    declared_hard_days: list[str] | None = None,
    phase: str = "TAPER",
    stage_key: str = "late_fight_window",
    week_index: int = 1,
    window_start_d_day: int | None = None,
    window_end_d_day: int | None = None,
) -> list[dict[str, Any]]:''',
        "planner signature",
    )

    planner = replace_once(
        planner,
        '''        if fight_weekday:
            end_d = max(0, days - 6)
            week["fight_weekday"] = fight_weekday
            week["projected_days_until_fight_end"] = end_d
            week["span_days"] = days - end_d + 1''',
        '''        if fight_weekday:
            start_d = window_start_d_day if isinstance(window_start_d_day, int) else days
            end_d = (
                window_end_d_day
                if isinstance(window_end_d_day, int)
                else max(0, days - 6)
            )
            if start_d < end_d:
                start_d, end_d = end_d, start_d
            week["fight_weekday"] = fight_weekday
            week["projected_days_until_fight_end"] = end_d
            week["span_days"] = start_d - end_d + 1''',
        "planner calendar window",
    )

    planner = replace_once(
        planner,
        '''            hard_sparring_plan = _late_fight_hard_sparring_plan(
                days_until_fight=start_day,
                athlete_model=segment_athlete,
                declared_hard_days=filtered_sparring,
                phase=phase,
                stage_key=stage_key,
                week_index=week_index,
            )''',
        '''            # Keep sparring dose truth aligned to the exact countdown
            # segment rendered by the seven weekday slots. The D-21..D-14
            # bridge drops D-21 and displays D-20..D-14, so its shared Friday
            # must be judged as D-14 rather than inheriting a D-21 hard verdict.
            rendered_start_day = min(start_day, end_day + len(_WEEKDAY_NAMES) - 1)
            hard_sparring_plan = _late_fight_hard_sparring_plan(
                days_until_fight=start_day,
                athlete_model=segment_athlete,
                declared_hard_days=filtered_sparring,
                phase=phase,
                stage_key=stage_key,
                week_index=week_index,
                window_start_d_day=rendered_start_day,
                window_end_d_day=end_day,
            )''',
        "segment sparring call",
    )

    PLANNER_PATH.write_text(planner)


def patch_tests() -> None:
    tests = TEST_PATH.read_text()
    marker = "def test_d21_shared_weekday_uses_rendered_d14_sparring_verdict():"
    if marker in tests:
        raise RuntimeError("regression test already exists")

    tests += '''


def test_d21_shared_weekday_uses_rendered_d14_sparring_verdict():
    # A Friday plan created at D-21 and a Friday fight make D-21 and D-14
    # share the same weekday. The calendar drops D-21 because eight countdown
    # days cannot fit seven weekday slots. The visible Friday must therefore
    # carry D-14's technical verdict, never D-21's hard verdict.
    athlete = _athlete(21, fight_date=FIGHT_FRIDAY)
    athlete["hard_sparring_days"] = ["friday"]
    athlete["training_days"] = ["monday", "tuesday", "wednesday", "thursday", "friday"]

    role_map = _build_late_fight_weekly_role_map(21, athlete, None, phase="TAPER")
    role_map = apply_fight_day_override_to_weekly_role_map(role_map, athlete)
    bridge = role_map["weeks"][0]
    assert bridge["countdown_span"] == {"start_day": 21, "end_day": 14}

    friday_entries = [
        entry
        for entry in bridge["hard_sparring_plan"]
        if str(entry.get("day") or "").strip().lower() == "friday"
    ]
    assert len(friday_entries) == 1
    assert friday_entries[0]["d_day"] == 14
    assert friday_entries[0]["effective_load"] == "technical"
    assert friday_entries[0]["status"] == "convert_to_technical_suggested"
    assert "d17_hard_sparring_ban" in friday_entries[0]["reason_codes"]
    assert not any(
        entry.get("d_day") == 21 and entry.get("effective_load") == "hard"
        for entry in bridge["hard_sparring_plan"]
    )

    brief = {"weekly_role_map": role_map, "athlete_model": athlete, "fight_date": FIGHT_FRIDAY}
    schedule = extract_weekly_schedule(brief, week_index=0, fight_date=FIGHT_FRIDAY)
    assert schedule is not None
    friday = next(day for day in schedule["days"] if day["weekday"] == "Fri")
    assert friday["d_day"] == 14
    assert friday["effective_load"] == "technical"
    assert friday["status"] == "convert_to_technical_suggested"
    assert "d17_hard_sparring_ban" in friday["reason_codes"]
'''
    TEST_PATH.write_text(tests)


if __name__ == "__main__":
    patch_planner()
    patch_tests()
