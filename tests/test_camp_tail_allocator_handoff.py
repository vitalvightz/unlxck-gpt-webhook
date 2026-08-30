from __future__ import annotations

import fightcamp.camp_week_fillers as fillers
from fightcamp.camp_week_fillers import _role_d_day, _splice_late_fight_tail


def _week(calendar_days, roles):
    return {
        "calendar_days": calendar_days,
        "session_roles": roles,
        "intentionally_unused_days": [],
        "phase": "TAPER",
    }


def _role(role_key: str, d_day: int, weekday: str, *, category: str = "strength"):
    return {
        "role_key": role_key,
        "category": category,
        "countdown_offset": d_day,
        "countdown_label": f"D-{d_day}",
        "scheduled_countdown_label": f"D-{d_day}",
        "scheduled_day_hint": weekday,
    }


def test_d30_keeps_d14_normal_and_splices_finished_d13_tail(monkeypatch):
    weekly_role_map = {
        "weeks": [
            _week(
                [
                    {"weekday": "monday", "d_day": 15},
                    {"weekday": "tuesday", "d_day": 14},
                    {"weekday": "wednesday", "d_day": 13},
                    {"weekday": "thursday", "d_day": 12},
                ],
                [
                    _role("normal_d14", 14, "tuesday"),
                    _role("normal_d13", 13, "wednesday"),
                    _role("normal_d12", 12, "thursday"),
                ],
            ),
            _week(
                [
                    {"weekday": "monday", "d_day": 8},
                    {"weekday": "tuesday", "d_day": 7},
                    {"weekday": "wednesday", "d_day": 6},
                    {"weekday": "thursday", "d_day": 5},
                    {"weekday": "friday", "d_day": 4},
                ],
                [_role("normal_d7", 7, "tuesday")],
            ),
            _week(
                [
                    {"weekday": "monday", "d_day": 3},
                    {"weekday": "tuesday", "d_day": 2},
                    {"weekday": "wednesday", "d_day": 1},
                    {"weekday": "thursday", "d_day": 0},
                ],
                [
                    _role("normal_d1", 1, "wednesday"),
                    _role("fight_day_protocol", 0, "thursday", category="protocol"),
                ],
            ),
        ]
    }
    athlete_model = {
        "days_until_fight": 30,
        "plan_creation_weekday": "monday",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    }

    calls = []

    def fake_finished_tail(days_until_fight, model, *, start_day):
        calls.append((days_until_fight, start_day, model["days_until_fight"]))
        roles = [
            _role("late_d13", 13, "wednesday"),
            _role("late_d7", 7, "tuesday"),
            _role("late_d1", 1, "wednesday"),
        ]
        return {
            "session_sequence": roles,
            "day_metadata": {
                13: {"stage_key": "d13_to_d8", "payload_mode": "pre_fight_compressed_payload"},
                7: {"stage_key": "d7", "payload_mode": "late_fight_week_payload"},
                1: {"stage_key": "d1", "payload_mode": "pre_fight_day_payload"},
            },
            "segments": [
                {
                    "stage_key": "d13_to_d8",
                    "payload_mode": "pre_fight_compressed_payload",
                    "countdown_span": {"start_day": 13, "end_day": 8},
                    "intentional_compression": {"active": True},
                    "role_budget": {"max_active_roles": 3},
                },
                {
                    "stage_key": "d7",
                    "payload_mode": "late_fight_week_payload",
                    "countdown_span": {"start_day": 7, "end_day": 7},
                    "intentional_compression": {"active": True},
                    "role_budget": {"max_active_roles": 2},
                },
                {
                    "stage_key": "d1",
                    "payload_mode": "pre_fight_day_payload",
                    "countdown_span": {"start_day": 1, "end_day": 1},
                    "intentional_compression": {"active": True},
                    "role_budget": {"max_active_roles": 1},
                },
            ],
        }

    monkeypatch.setattr(fillers, "build_finished_late_fight_tail", fake_finished_tail)

    assert _splice_late_fight_tail(weekly_role_map, athlete_model) is True
    assert calls == [(30, 13, 30)]

    placed = {
        role["role_key"]: (_role_d_day(week, role), role)
        for week in weekly_role_map["weeks"]
        for role in week["session_roles"]
        if isinstance(role, dict)
    }

    # D-14 remains physically owned by the normal planner.
    assert placed["normal_d14"][0] == 14

    # Normal-planner roles inside D-13 -> D-1 are gone.
    for role_key in ("normal_d13", "normal_d12", "normal_d7", "normal_d1"):
        assert role_key not in placed

    # Finished late-fight roles own the tail and carry their real window metadata.
    assert placed["late_d13"][0] == 13
    assert placed["late_d13"][1]["governance"]["authority"] == "finished_late_fight_tail"
    assert placed["late_d13"][1]["late_fight_payload_mode"] == "pre_fight_compressed_payload"
    assert placed["late_d7"][1]["late_fight_payload_mode"] == "late_fight_week_payload"
    assert placed["late_d1"][1]["late_fight_payload_mode"] == "pre_fight_day_payload"

    # D-0 remains the existing deterministic fight-day protocol.
    assert placed["fight_day_protocol"][0] == 0

    # Mixed weeks carry segment metadata without changing D-14 ownership.
    first_week = weekly_role_map["weeks"][0]
    assert 14 not in first_week["late_fight_tail_days"]
    assert 13 in first_week["late_fight_tail_days"]
    assert first_week["late_fight_tail_segments"][0]["stage_key"] == "d13_to_d8"

    assert weekly_role_map["late_fight_tail_handoff"] == {
        "active": True,
        "normal_planner_through_d": 14,
        "late_fight_planner_from_d": 13,
        "source": "finished_existing_late_fight_path",
    }


def test_finished_tail_tactical_watches_are_not_reselected_or_collapsed(monkeypatch):
    watch_a = {
        **_role("tactical_watch", 10, "monday", category="support_insert"),
        "late_fight_tail_owned": True,
        "tactical_watch_key": "direct-tail-a",
        "display_text": "Direct D-13-path watch A",
    }
    watch_b = {
        **_role("tactical_watch", 7, "thursday", category="support_insert"),
        "late_fight_tail_owned": True,
        "tactical_watch_key": "direct-tail-b",
        "display_text": "Direct D-13-path watch B",
    }
    week = _week(
        [
            {"weekday": "monday", "d_day": 10},
            {"weekday": "thursday", "d_day": 7},
        ],
        [watch_a, watch_b],
    )
    week["late_fight_tail_days"] = [10, 7]

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("normal camp watch selector must not rewrite the finished tail")

    monkeypatch.setattr(fillers._impl, "_ensure_tactical_watch", should_not_run)
    used_watch_keys: set[str] = set()
    usage_ledger = fillers._new_usage_ledger()

    assert fillers._ensure_tactical_watch(
        week,
        {"days_until_fight": 30},
        "TAPER",
        used_watch_keys,
        usage_ledger,
    ) is True
    assert [role["display_text"] for role in week["session_roles"]] == [
        "Direct D-13-path watch A",
        "Direct D-13-path watch B",
    ]
    assert used_watch_keys == {"direct-tail-a", "direct-tail-b"}


def test_d13_generated_plan_is_not_spliced_again(monkeypatch):
    weekly_role_map = {"weeks": []}
    athlete_model = {"days_until_fight": 13}

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("direct D-13 plan must keep its existing late-fight route")

    monkeypatch.setattr(fillers, "build_finished_late_fight_tail", should_not_run)
    assert _splice_late_fight_tail(weekly_role_map, athlete_model) is False
    assert "late_fight_tail_handoff" not in weekly_role_map
