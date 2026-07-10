"""Contract-to-storage integration tests for the Today/Overview service.

These exercise api/services/today_service.py against the in-memory FakeStore with
an injected ``now``, so training-day boundaries and recommendation validity are
deterministic without a live clock or database.
"""

from datetime import date, datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from api.models import WeeklyDayEntry, WeeklySchedule
from api.routes.daily import _resolve_today_and_next
from api.contracts.completion import completion_landing_state, completion_status_of
from api.services.today_service import (
    _scan_forward_for_next_training,
    build_today_command_view,
    submit_today_checkin,
    submit_today_injury_checkin,
    upsert_session_completion,
)
from tests.support import FakeStore

NY = "America/New_York"
ATHLETE = "athlete-1"
PLAN = "11111111-1111-1111-1111-111111111111"
OTHER_PLAN = "22222222-2222-2222-2222-222222222222"


def _store_with_plan(plan_id: str = PLAN, athlete_id: str = ATHLETE) -> FakeStore:
    store = FakeStore()
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": athlete_id,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    return store


def _attach_intake(
    store: FakeStore,
    intake: dict,
    *,
    plan_id: str = PLAN,
    athlete_id: str = ATHLETE,
    intake_id: str = "intake-1",
) -> None:
    store.intakes.setdefault(athlete_id, []).append(
        {
            "id": intake_id,
            "athlete_id": athlete_id,
            "intake": intake,
            "created_at": "2026-06-01T00:00:00+00:00",
        }
    )
    store.plans[plan_id]["intake_id"] = intake_id


def _taper_planning_brief() -> dict:
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "TAPER",
                    "hard_sparring_plan": [],
                }
            ]
        }
    }


def _calendar_training_brief(*, active_offsets: list[int]) -> dict:
    today = date(2026, 6, 18)
    monday = today - timedelta(days=today.weekday())
    calendar_days = [
        {
            "weekday": (monday + timedelta(days=offset)).strftime("%A"),
            "calendar_date": (monday + timedelta(days=offset)).isoformat(),
            "d_day": 30 - offset,
        }
        for offset in range(7)
    ]
    hard_sparring_plan = []
    for offset in active_offsets:
        training_date = today + timedelta(days=offset)
        hard_sparring_plan.append(
            {
                "day": training_date.strftime("%A"),
                "hard_day_class": "managed_hard",
                "effective_load": "technical",
                "status": "technical_skill",
                "reason": "Plan card for the matched training day.",
                "coach_note": "Keep it sharp and clean.",
                "reason_codes": [],
            }
        )
    return {
        "fight_date": "2026-07-18",
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "calendar_days": calendar_days,
                    "hard_sparring_plan": hard_sparring_plan,
                }
            ]
        },
    }


def _monday_rest_tuesday_training_brief() -> dict:
    monday = date(2026, 6, 22)
    calendar_days = [
        {
            "weekday": (monday + timedelta(days=offset)).strftime("%A"),
            "calendar_date": (monday + timedelta(days=offset)).isoformat(),
            "d_day": 25 - offset,
        }
        for offset in range(7)
    ]
    return {
        "fight_date": "2026-07-17",
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "GPP",
                    "calendar_days": calendar_days,
                    "hard_sparring_plan": [
                        {
                            "day": "Tuesday",
                            "hard_day_class": "primary_hard",
                            "effective_load": "hard",
                            "status": "hard_as_planned",
                            "reason": "Tuesday is the next real session.",
                            "coach_note": "Hard sparring.",
                            "reason_codes": [],
                        }
                    ],
                }
            ]
        },
    }


def _monday_strength_structured_plan() -> dict:
    return {
        "weeks": [
            {
                "phase_label": "GPP",
                "days": [
                    {
                        "date": "2026-06-22",
                        "countdown_label": "D-25",
                        "day_type": "high",
                        "today_card": {
                            "headline": "Posterior chain strength + control",
                        },
                        "sessions": [
                            {
                                "session_id": "2026-06-22-strength",
                                "session_type": "strength",
                                "title": "Posterior chain strength + control",
                                "objective": "Rebuild single-leg control and hinge strength.",
                                "blocks": [],
                            }
                        ],
                    },
                    {
                        "date": "2026-06-23",
                        "countdown_label": "D-24",
                        "day_type": "high",
                        "sessions": [
                            {
                                "session_id": "2026-06-23-sparring",
                                "session_type": "sparring",
                                "title": "Hard sparring",
                                "blocks": [],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def _combined_contact_and_app_structured_plan() -> dict:
    return {
        "weeks": [
            {
                "phase_label": "SPP",
                "days": [
                    {
                        "date": "2026-06-18",
                        "countdown_label": "D-18",
                        "day_type": "high",
                        "today_card": {"headline": "Power Transfer Touch"},
                        "sessions": [
                            {
                                "session_id": "2026-06-18-contact",
                                "session_type": "sparring",
                                "title": "Coach-led boxing - technical only",
                                "blocks": [],
                            },
                            {
                                "session_id": "2026-06-18-app",
                                "session_type": "skill",
                                "title": "Power Transfer Touch",
                                "objective": "Preserve punch speed without fatigue.",
                                "blocks": [
                                    {
                                        "block_type": "skill",
                                        "display_name": "Band-Resisted Jab-Cross Primer",
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "date": "2026-06-25",
                        "countdown_label": "D-11",
                        "day_type": "high",
                        "sessions": [
                            {
                                "session_id": "2026-06-25-hard",
                                "session_type": "sparring",
                                "title": "Hard sparring",
                                "blocks": [],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def _out_of_order_countdown_structured_plan() -> dict:
    return {
        "weeks": [
            {
                "phase_label": "TAPER",
                "days": [
                    {
                        "date": "2026-06-23",
                        "countdown_label": "D-9",
                        "day_type": "high",
                        "sessions": [
                            {
                                "session_id": "2026-06-23-app",
                                "session_type": "strength",
                                "title": "Tuesday app session",
                                "blocks": [],
                            }
                        ],
                    },
                    {
                        "date": "2026-06-27",
                        "countdown_label": "D-5",
                        "day_type": "high",
                        "sessions": [
                            {
                                "session_id": "2026-06-27-sparring",
                                "session_type": "sparring",
                                "title": "Saturday technical sparring",
                                "blocks": [],
                            }
                        ],
                    },
                    {
                        "date": "2026-06-26",
                        "countdown_label": "D-6",
                        "day_type": "high",
                        "sessions": [
                            {
                                "session_id": "2026-06-26-app",
                                "session_type": "app_session",
                                "title": "Friday app session",
                                "blocks": [],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def _tuesday_today_saturday_technical_brief() -> dict:
    tuesday = date(2026, 6, 23)
    monday = tuesday - timedelta(days=tuesday.weekday())
    calendar_days = [
        {
            "weekday": (monday + timedelta(days=offset)).strftime("%A"),
            "calendar_date": (monday + timedelta(days=offset)).isoformat(),
            "d_day": 9 - offset,
        }
        for offset in range(7)
    ]
    return {
        "fight_date": "2026-07-02",
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "calendar_days": calendar_days,
                    "hard_sparring_plan": [
                        {
                            "day": "Tuesday",
                            "hard_day_class": "managed_hard",
                            "effective_load": "reduced",
                            "status": "technical_skill",
                            "reason": "Tuesday app session.",
                            "coach_note": "Light power and balance.",
                            "reason_codes": [],
                        },
                        {
                            "day": "Saturday",
                            "hard_day_class": "technical",
                            "effective_load": "technical",
                            "status": "convert_to_technical_suggested",
                            "reason": "Saturday technical only.",
                            "coach_note": "Technical work.",
                            "reason_codes": [],
                        },
                    ],
                }
            ]
        },
    }


class SummaryActiveStore(FakeStore):
    """Mirror production auto-active selection, where list_user_plans is summary-only."""

    def list_user_plans(self, athlete_id: str) -> list[dict]:
        rows = super().list_user_plans(athlete_id)
        return [
            {
                key: value
                for key, value in row.items()
                if key not in {"structured_plan", "planning_brief", "stage2_payload"}
            }
            for row in rows
        ]


class NullCheckinListStore(FakeStore):
    def list_today_checkins_for_day(self, athlete_id: str, training_day: str):
        return None


class TestDailyScheduleResolver:
    def test_next_session_uses_earliest_future_calendar_date(self):
        week = WeeklySchedule(
            plan_id=PLAN,
            week_index=0,
            week_count=1,
            days=[
                WeeklyDayEntry(
                    weekday="Tue",
                    calendar_date="2026-06-23",
                    effective_load="hard",
                    status="app_session",
                ),
                WeeklyDayEntry(
                    weekday="Sat",
                    calendar_date="2026-06-27",
                    effective_load="technical",
                    status="technical_sparring",
                ),
                WeeklyDayEntry(
                    weekday="Fri",
                    calendar_date="2026-06-26",
                    effective_load="reduced",
                    status="app_session",
                ),
            ],
        )

        today_entry, next_entry = _resolve_today_and_next(week, today=date(2026, 6, 23))

        assert today_entry is not None
        assert today_entry.calendar_date == "2026-06-23"
        assert next_entry is not None
        assert next_entry.weekday == "Fri"
        assert next_entry.calendar_date == "2026-06-26"


def _multi_week_taper_brief() -> dict:
    """A two-week taper where each week has a single training day.

    Week 0 trains on Mon (2026-06-15); week 1 trains on Wed (2026-06-24). Every
    other day is rest, mirroring real taper/late-camp weeks. Used to prove the
    "Next session" lookup crosses the week boundary instead of stopping at the
    end of the current week.
    """
    week0_monday = date(2026, 6, 15)

    def _calendar_days(monday: date, d_day_for_monday: int) -> list[dict]:
        return [
            {
                "weekday": (monday + timedelta(days=offset)).strftime("%A"),
                "calendar_date": (monday + timedelta(days=offset)).isoformat(),
                "d_day": d_day_for_monday - offset,
            }
            for offset in range(7)
        ]

    def _training_day(weekday: str) -> dict:
        return {
            "day": weekday,
            "hard_day_class": "managed_hard",
            "effective_load": "technical",
            "status": "technical_skill",
            "reason": "Plan card for the matched training day.",
            "coach_note": "Keep it sharp and clean.",
            "reason_codes": [],
        }

    return {
        "fight_date": "2026-07-11",
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "TAPER",
                    "calendar_days": _calendar_days(week0_monday, 26),
                    "hard_sparring_plan": [_training_day("Monday")],
                },
                {
                    "phase": "TAPER",
                    "calendar_days": _calendar_days(week0_monday + timedelta(days=7), 19),
                    "hard_sparring_plan": [_training_day("Wednesday")],
                },
            ]
        },
    }


def _checkin_payload(**overrides) -> dict:
    base = {
        "plan_id": PLAN,
        "sleep": "good",
        "body": "normal",
        "pain": "none",
        "phase": "GPP",
        "active_injury": "none",
        "previous_session": "none",
        "sharp_pain": False,
        "instability": False,
        "swelling": False,
        "neurological_symptoms": False,
        "illness_symptoms": False,
        "cannot_warm_into_movement": False,
        "worse_next_day_pain": False,
    }
    return {**base, **overrides}


class TestTrainingDayPersistence:
    def test_0359_local_stores_previous_training_day(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 3, 59, tzinfo=ZoneInfo(NY))
        row = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone=NY, payload=_checkin_payload(), now=now
        )
        assert row["training_day"] == "2026-06-17"

    def test_0400_local_stores_current_training_day(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 4, 0, tzinfo=ZoneInfo(NY))
        row = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone=NY, payload=_checkin_payload(), now=now
        )
        assert row["training_day"] == "2026-06-18"

    def test_missing_timezone_fallback_does_not_crash(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)
        row = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone=None, payload=_checkin_payload(), now=now
        )
        assert row["training_day"] == "2026-06-18"


class TestCheckinSubmit:
    def test_checkin_and_recommendation_persist(self):
        store = _store_with_plan()
        row = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(sleep="poor")
        )
        assert store.today_checkins[ATHLETE], "check-in row must persist"
        assert row["recommendation_state"] == "modify"
        assert row["recommendation_reason"].splitlines() == [
            "Session reduced.",
            "Poor sleep means your body has less room to recover today.",
            "Cut 1 round and do not add extra conditioning.",
        ]
        assert "poor_sleep" in row["recommendation_triggers"]

    def test_same_day_duplicate_upserts_single_row(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(), now=now)
        second = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(sleep="poor"), now=now
        )
        assert len(store.today_checkins[ATHLETE]) == 1
        assert second["recommendation_state"] == "modify"
        assert second["warnings"] == [
            "You already completed a check-in today. This response applies to the current active plan only."
        ]

    def test_client_supplied_recommendation_is_ignored(self):
        store = _store_with_plan()
        # Client tries to force train_as_planned, but pain=high is a hard override.
        payload = _checkin_payload(pain="high", recommendation_state="train_as_planned")
        row = submit_today_checkin(store, athlete_id=ATHLETE, athlete_timezone="", payload=payload)
        assert row["recommendation_state"] == "pull_back"

    def test_same_day_other_plan_checkin_is_allowed_with_warning(self):
        store = _store_with_plan()
        store.plans[OTHER_PLAN] = {
            "id": OTHER_PLAN,
            "athlete_id": ATHLETE,
            "status": "ready",
            "plan_name": "Camp B",
            "created_at": "2026-06-02T00:00:00+00:00",
        }
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)

        submit_today_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=_checkin_payload(plan_id=OTHER_PLAN),
            now=now,
        )
        row = submit_today_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=_checkin_payload(plan_id=PLAN),
            now=now,
        )

        assert len(store.today_checkins[ATHLETE]) == 2
        assert row["warnings"] == [
            "You already completed a check-in today. This response applies to the current active plan only."
        ]

    def test_same_day_warning_handles_null_lister_and_immutable_row(self):
        store = NullCheckinListStore()
        store.plans[PLAN] = {
            "id": PLAN,
            "athlete_id": ATHLETE,
            "status": "ready",
            "plan_name": "Camp A",
            "created_at": "2026-06-01T00:00:00+00:00",
        }
        original_upsert = store.upsert_today_checkin

        def immutable_upsert(athlete_id: str, fields: dict) -> MappingProxyType:
            return MappingProxyType(original_upsert(athlete_id, fields))

        store.upsert_today_checkin = immutable_upsert  # type: ignore[method-assign]

        row = submit_today_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=_checkin_payload(),
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )

        assert row["warnings"] == []
        assert row["plan_id"] == PLAN


class TestPlanOwnership:
    def _seed_other(self, store):
        store.plans[OTHER_PLAN] = {
            "id": OTHER_PLAN,
            "athlete_id": "someone-else",
            "status": "ready",
            "plan_name": "Other",
            "created_at": "2026-06-01T00:00:00+00:00",
        }

    def test_checkin_rejected_when_plan_not_owned(self):
        store = _store_with_plan()
        self._seed_other(store)
        with pytest.raises(HTTPException) as exc:
            submit_today_checkin(
                store,
                athlete_id=ATHLETE,
                athlete_timezone="",
                payload=_checkin_payload(plan_id=OTHER_PLAN),
            )
        assert exc.value.status_code == 404
        assert not store.today_checkins.get(ATHLETE)

    def test_completion_rejected_when_plan_not_owned(self):
        store = _store_with_plan()
        self._seed_other(store)
        with pytest.raises(HTTPException) as exc:
            upsert_session_completion(
                store,
                athlete_id=ATHLETE,
                athlete_timezone="",
                payload={"plan_id": OTHER_PLAN, "session_id": "s1", "status": "started"},
            )
        assert exc.value.status_code == 404
        assert not store.session_completions.get(ATHLETE)


class TestPlanIdValidation:
    def test_checkin_rejects_malformed_plan_id(self):
        store = _store_with_plan()
        with pytest.raises(HTTPException) as exc:
            submit_today_checkin(
                store,
                athlete_id=ATHLETE,
                athlete_timezone="",
                payload=_checkin_payload(plan_id="not-a-uuid"),
            )
        assert exc.value.status_code == 422
        assert not store.today_checkins.get(ATHLETE)

    def test_completion_rejects_malformed_plan_id(self):
        store = _store_with_plan()
        with pytest.raises(HTTPException) as exc:
            upsert_session_completion(
                store,
                athlete_id=ATHLETE,
                athlete_timezone="",
                payload={"plan_id": "not-a-uuid", "session_id": "s1", "status": "started"},
            )
        assert exc.value.status_code == 422
        assert not store.session_completions.get(ATHLETE)


class TestRecommendationValidity:
    def test_same_training_day_recommendation_is_live(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(sleep="poor"), now=now
        )
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="", now=now)
        assert view.today.recommendation_state == "modify"
        assert view.today.recommendation_reason

    def test_previous_training_day_returns_not_checked_in(self):
        store = _store_with_plan()
        submit_today_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=_checkin_payload(sleep="poor"),
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )
        # Next day: the prior recommendation has expired.
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
        )
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.recommendation_reason is None


class TestCommandView:
    def test_no_active_plan_returns_intake_cta(self):
        store = FakeStore()  # no plan seeded
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view.active_plan == {}
        assert [a.id for a in view.quick_actions] == ["complete_intake"]

    def test_active_plan_without_checkin_is_not_checked_in(self):
        store = _store_with_plan()
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view.active_plan.get("id") == PLAN
        assert view.today.recommendation_state == "not_checked_in"

    def test_missing_structured_plan_does_not_crash(self):
        # Minimal plan row (no planning_brief) must degrade, not raise.
        store = _store_with_plan()
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view.today.next_session == {}
        assert view.today.completion_status == "not_started"

    def test_guided_intake_injury_seeds_open_injury_flag(self):
        store = _store_with_plan()
        _attach_intake(
            store,
            {
                "guided_injuries": [
                    {
                        "area": "Left shoulder",
                        "zone": "l_shoulder",
                        "severity": "high",
                        "trend": "same",
                        "surface_type": "bruise",
                        "cleared": "",
                    }
                ]
            },
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert len(view.open_injuries) == 1
        seeded = view.open_injuries[0]
        assert seeded["source"] == "intake"
        assert seeded["plan_id"] == PLAN
        assert seeded["body_area"] == "Left shoulder"
        assert seeded["severity"] == "severe"
        assert seeded["status"] == "open"
        assert "bruise" in seeded["description"]

    def test_guided_intake_description_does_not_repeat_body_area(self):
        store = _store_with_plan()
        _attach_intake(
            store,
            {
                "guided_injuries": [
                    {
                        "area": "Left shoulder",
                        "zone": "l_shoulder",
                        "severity": "moderate",
                        "trend": "same",
                        "notes": "Left shoulder bruise",
                    }
                ]
            },
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert view.open_injuries[0]["description"] == "Left shoulder bruise"

    def test_guided_intake_injury_bootstrap_is_idempotent(self):
        store = _store_with_plan()
        _attach_intake(
            store,
            {
                "guided_injuries": [
                    {
                        "area": "Left shoulder",
                        "zone": "l_shoulder",
                        "severity": "moderate",
                        "trend": "same",
                    }
                ]
            },
        )

        build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert len(store.injury_flags[ATHLETE]) == 1

    def test_intake_bootstrap_write_failure_does_not_break_today(self):
        class FailingBootstrapStore(FakeStore):
            def create_injury_flag(self, athlete_id: str, fields: dict) -> dict:
                raise RuntimeError("temporary write failure")

        store = FailingBootstrapStore()
        store.plans[PLAN] = _store_with_plan().plans[PLAN]
        _attach_intake(
            store,
            {
                "guided_injuries": [
                    {
                        "area": "Left shoulder",
                        "zone": "l_shoulder",
                        "severity": "high",
                        "trend": "same",
                    }
                ]
            },
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert view.active_plan.get("id") == PLAN
        assert view.open_injuries == []

    def test_cleared_guided_intake_injury_is_not_seeded(self):
        store = _store_with_plan()
        _attach_intake(
            store,
            {
                "guided_injuries": [
                    {
                        "area": "Left shoulder",
                        "zone": "l_shoulder",
                        "severity": "high",
                        "trend": "improving",
                        "cleared": "yes",
                    }
                ],
                "injuries": "left shoulder bruise",
            },
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert view.open_injuries == []
        assert store.injury_flags.get(ATHLETE, []) == []

    def test_cleared_intake_seeded_injury_stays_cleared(self):
        """Clearing an intake-seeded injury must not re-seed it on the next load."""
        store = _store_with_plan()
        _attach_intake(
            store,
            {
                "guided_injuries": [
                    {
                        "area": "Left shoulder",
                        "zone": "l_shoulder",
                        "severity": "high",
                        "trend": "same",
                    }
                ]
            },
        )

        # First load seeds the open flag from intake.
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert len(view.open_injuries) == 1
        flag_id = view.open_injuries[0]["id"]

        # Athlete presses "Cleared" on the daily check-in.
        result = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            payload={"injuries": [{"flag_id": flag_id, "status": "resolved"}]},
        )
        assert result["open_injuries"] == []

        # The injury must not come back the next time Today loads, even though the
        # intake payload still lists it.
        view_after = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view_after.open_injuries == []

    @pytest.mark.parametrize(
        ("guided_severity", "flag_severity"),
        [("low", "mild"), ("moderate", "moderate"), ("high", "severe"), ("", "moderate")],
    )
    def test_guided_intake_severity_maps_to_flag_severity(
        self,
        guided_severity: str,
        flag_severity: str,
    ):
        store = _store_with_plan()
        _attach_intake(
            store,
            {
                "guided_injury": {
                    "area": "Left knee",
                    "zone": "l_knee",
                    "severity": guided_severity,
                    "trend": "improving",
                }
            },
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert view.open_injuries[0]["severity"] == flag_severity
        assert view.open_injuries[0]["status"] == "monitoring"

    def test_legacy_intake_injury_text_seeds_conservative_flag(self):
        store = _store_with_plan()
        _attach_intake(store, {"injuries": "Shoulder bruise after sparring"})

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert len(view.open_injuries) == 1
        seeded = view.open_injuries[0]
        assert seeded["source"] == "intake"
        assert seeded["severity"] == "moderate"
        assert seeded["status"] == "open"
        assert seeded["description"] == "Shoulder bruise after sparring"

    def test_intake_injury_dedupes_against_existing_open_flag(self):
        store = _store_with_plan()
        store.create_injury_flag(
            ATHLETE,
            {
                "source": "manual",
                "plan_id": PLAN,
                "body_area": "Left shoulder",
                "description": "Left shoulder soreness",
                "severity": "mild",
                "status": "open",
            },
        )
        _attach_intake(
            store,
            {
                "guided_injuries": [
                    {
                        "area": "Left shoulder",
                        "zone": "l_shoulder",
                        "severity": "high",
                        "trend": "same",
                    }
                ]
            },
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert len(view.open_injuries) == 1
        assert view.open_injuries[0]["source"] == "manual"

    def test_intake_injury_dedupe_checks_beyond_display_limit(self):
        store = _store_with_plan()
        store.create_injury_flag(
            ATHLETE,
            {
                "source": "manual",
                "plan_id": PLAN,
                "body_area": "Left shoulder",
                "description": "Left shoulder soreness",
                "severity": "mild",
                "status": "open",
            },
        )
        for index in range(20):
            store.create_injury_flag(
                ATHLETE,
                {
                    "source": "checkin",
                    "plan_id": PLAN,
                    "body_area": f"Area {index}",
                    "description": f"Area {index}",
                    "severity": "mild",
                    "status": "open",
                },
            )
        _attach_intake(
            store,
            {
                "guided_injuries": [
                    {
                        "area": "Left shoulder",
                        "zone": "l_shoulder",
                        "severity": "high",
                        "trend": "same",
                    }
                ]
            },
        )

        build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

        assert len(store.injury_flags[ATHLETE]) == 21
        assert not [flag for flag in store.injury_flags[ATHLETE] if flag["source"] == "intake"]

    def test_logged_session_pain_surfaces_without_a_checkin(self):
        # The badge must reflect training reality even with no check-in today:
        # a high logged post-session pain reading drives a risk-watch item.
        store = _store_with_plan()
        store.session_completions[ATHLETE] = [
            {
                "id": "c1",
                "athlete_id": ATHLETE,
                "plan_id": PLAN,
                "session_id": "s1",
                "training_day": "2026-06-18",
                "status": "done",
                "pain_after": 8,
            }
        ]
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )
        assert view.today.recommendation_state == "not_checked_in"
        assert "high_pain" in [risk.category for risk in view.risk_watch]

    def test_recent_symptom_keeps_a_decaying_reminder(self):
        # A symptom two days ago, clean since, no check-in today: the badge stays
        # live with a decaying reminder rather than reverting to a blank green.
        store = _store_with_plan()
        store.session_completions[ATHLETE] = [
            {
                "id": "c1",
                "athlete_id": ATHLETE,
                "plan_id": PLAN,
                "session_id": "s1",
                "training_day": "2026-06-16",
                "status": "done",
                "pain_after": 5,
            }
        ]
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )
        assert "reminder" in [risk.category for risk in view.risk_watch]

    def test_recent_symptom_decay_reminder_is_suppressed_in_taper(self):
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _taper_planning_brief()
        store.session_completions[ATHLETE] = [
            {
                "id": "c1",
                "athlete_id": ATHLETE,
                "plan_id": PLAN,
                "session_id": "s1",
                "training_day": "2026-06-16",
                "status": "done",
                "pain_after": 5,
            }
        ]
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )
        assert "reminder" not in [risk.category for risk in view.risk_watch]

    def test_injury_checkin_opens_flag_and_surfaces_it(self):
        store = _store_with_plan()
        result = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            payload={"injuries": [{"body_area": "left knee", "status": "ongoing"}]},
        )
        assert len(result["open_injuries"]) == 1
        flag = result["open_injuries"][0]
        assert flag["status"] == "open"
        assert flag["plan_id"] == PLAN  # attached to the active plan

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert len(view.open_injuries) == 1
        assert "reminder" in [risk.category for risk in view.risk_watch]

    def test_injury_checkin_rejects_stale_flag_id_without_identity(self):
        store = _store_with_plan()
        with pytest.raises(HTTPException) as exc_info:
            submit_today_injury_checkin(
                store,
                athlete_id=ATHLETE,
                payload={"injuries": [{"flag_id": "ghost", "status": "ongoing"}]},
            )

        assert exc_info.value.status_code == 422
        assert "body_area or description" in str(exc_info.value.detail)
        assert store.injury_flags.get(ATHLETE, []) == []

    def test_injury_checkin_resolves_an_open_flag(self):
        store = _store_with_plan()
        opened = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            payload={"injuries": [{"body_area": "calf", "status": "ongoing"}]},
        )
        flag_id = opened["open_injuries"][0]["id"]

        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        resolved = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            payload={"injuries": [{"flag_id": flag_id, "status": "resolved"}]},
            now=now,
        )
        assert resolved["open_injuries"] == []  # no longer open/monitoring

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view.open_injuries == []
        injury_categories = {"active_injury_worse", "reminder"}
        assert not (injury_categories & {risk.category for risk in view.risk_watch})

    def test_injury_checkin_status_update_preserves_existing_severity(self):
        store = _store_with_plan()
        opened = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            payload={"injuries": [{"body_area": "shoulder", "severity": "severe", "status": "worse"}]},
        )
        flag_id = opened["open_injuries"][0]["id"]

        updated = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            payload={"injuries": [{"flag_id": flag_id, "status": "ongoing"}]},
        )

        assert updated["open_injuries"][0]["severity"] == "severe"

    def test_worse_injury_refreshes_existing_readiness_recommendation(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        initial = submit_today_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=_checkin_payload(),
            now=now,
        )
        assert initial["recommendation_state"] == "train_as_planned"

        submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={"injuries": [{"body_area": "belly", "severity": "severe", "status": "worse"}]},
            now=now,
        )

        updated = store.get_today_checkin(ATHLETE, PLAN, "2026-06-18")
        assert updated is not None
        assert updated["active_injury"] == "none"
        assert updated["recommendation_state"] == "pull_back"
        assert "active_injury_worse" in updated["recommendation_triggers"]
        assert "Rehab only today." in updated["recommendation_reason"]

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="", now=now)
        assert view.today.recommendation_state == "pull_back"
        assert "Rehab only today." in (view.today.recommendation_reason or "")

    def test_worse_mild_injury_stop_survives_later_mild_injury(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(), now=now
        )

        knee = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={"injuries": [{"body_area": "knee", "severity": "mild", "status": "worse"}]},
            now=now,
        )
        assert knee["recommendation"]["recommendation_state"] == "pull_back"
        assert knee["open_injuries"][0]["latest_reported_status"] == "worse"

        updated = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={
                "injuries": [
                    {"body_area": "ear", "description": "ear cut", "severity": "mild", "status": "ongoing"}
                ]
            },
            now=now,
        )

        assert updated["recommendation"]["recommendation_state"] == "pull_back"
        assert "active_injury_worse" in updated["recommendation"]["recommendation_triggers"]

    def test_multiple_mild_injuries_without_worsening_do_not_stop(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(), now=now
        )

        updated = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={
                "injuries": [
                    {"body_area": "knee", "severity": "mild", "status": "ongoing"},
                    {"body_area": "ear", "description": "ear cut", "severity": "mild", "status": "ongoing"},
                ]
            },
            now=now,
        )

        assert updated["recommendation"]["recommendation_state"] in {"train_as_planned", "modify"}
        assert "active_injury_worse" not in updated["recommendation"]["recommendation_triggers"]

    def test_severe_injury_stop_survives_later_mild_injury(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(), now=now
        )

        submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={"injuries": [{"body_area": "shoulder", "severity": "severe", "status": "ongoing"}]},
            now=now,
        )
        updated = submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={
                "injuries": [
                    {"body_area": "ear", "description": "ear cut", "severity": "mild", "status": "ongoing"}
                ]
            },
            now=now,
        )

        assert updated["recommendation"]["recommendation_state"] == "pull_back"
        assert "active_injury_worse" in updated["recommendation"]["recommendation_triggers"]

    def test_severe_ongoing_injury_escalates_recommendation_to_pull_back(self):
        # The reported bug: a severe injury added as "ongoing" (not "worse") used
        # to leave the recommendation at the daily "load reduced" copy. It must
        # now pull training back at the source, driven by severity.
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        initial = submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(), now=now
        )
        assert initial["recommendation_state"] == "train_as_planned"

        submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={"injuries": [{"body_area": "chest", "severity": "severe", "status": "ongoing"}]},
            now=now,
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="", now=now)
        assert view.today.recommendation_state == "pull_back"

    def test_intake_severe_injury_escalates_command_view_without_a_checkin(self):
        # A severe injury carried in from intake (no injury check-in refresh) is
        # still escalated by the command-view catch-all.
        store = _store_with_plan()
        store.create_injury_flag(
            ATHLETE,
            {"source": "intake", "plan_id": PLAN, "body_area": "neck", "severity": "severe", "status": "open"},
        )
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert view.today.recommendation_state == "pull_back"
        assert "severe injury" in (view.today.recommendation_reason or "").lower()

    def _cue_card_structured_plan(self):
        return {"weeks": [{"phase_label": "SPP", "days": [{
            "date": "2026-06-18", "day_type": "skill", "phase_label": "SPP",
            "countdown_label": "D-11",
            "sessions": [{
                "session_id": "2026-06-18-cue", "session_type": "support_insert",
                "category": "support_insert", "support_insert_category": "tactical",
                "title": "Tactical Cue Card", "objective": "distil one clean in-fight cue",
                "stress_class": "support", "governance": {"meaningful_stress": False},
                "blocks": [{"type": "mindset", "title": "Write one cue"}],
            }],
            "today_card": {"headline": "Tactical Cue Card"},
        }]}]}

    def test_severe_injury_does_not_block_a_safe_filler_session(self):
        # A neck injury cannot stop you writing a mental cue card. Today's low-cost
        # support/filler session is exempt from the injury hold: not stopped, and
        # the command view flags it so the UI never blocks it.
        store = _store_with_plan()
        store.plans[PLAN]["structured_plan"] = self._cue_card_structured_plan()
        store.create_injury_flag(
            ATHLETE,
            {"source": "intake", "plan_id": PLAN, "body_area": "neck",
             "description": "neck nerve pinch", "severity": "severe", "status": "open"},
        )
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="", now=now)
        assert view.today.injury_hold_exempt is True
        assert view.today.decision_tier != "stop"
        assert "session blocked" not in (view.today.recommendation_reason or "").lower()

    def test_filler_session_is_completable_despite_severe_injury(self):
        store = _store_with_plan()
        store.plans[PLAN]["structured_plan"] = self._cue_card_structured_plan()
        store.create_injury_flag(
            ATHLETE,
            {"source": "intake", "plan_id": PLAN, "body_area": "neck",
             "description": "neck nerve pinch", "severity": "severe", "status": "open"},
        )
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        row = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="",
            payload={"plan_id": PLAN, "session_id": "2026-06-18-cue", "status": "done"}, now=now,
        )
        assert row["status"] == "done"

    def test_new_injury_refreshes_existing_readiness_before_high_risk_session(self):
        store = _store_with_plan()
        structured_plan = _combined_contact_and_app_structured_plan()
        structured_plan["weeks"][0]["days"][0]["sessions"][1]["session_type"] = "sparring"
        structured_plan["weeks"][0]["days"][0]["sessions"][1]["title"] = "Hard sparring"
        store.plans[PLAN]["structured_plan"] = structured_plan
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        initial = submit_today_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=_checkin_payload(phase="SPP"),
            now=now,
        )
        assert initial["recommendation_state"] == "train_as_planned"

        submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={"injuries": [{"body_area": "left shoulder", "severity": "moderate", "status": "ongoing"}]},
            now=now,
        )

        updated = store.get_today_checkin(ATHLETE, PLAN, "2026-06-18")
        assert updated is not None
        assert updated["recommendation_state"] == "modify"
        assert "tracked_injury_high_risk_session" in updated["recommendation_triggers"]
        assert "Load controlled." in updated["recommendation_reason"]

    def test_tendon_injury_pulls_back_before_high_risk_session_with_tier(self):
        # Type-aware escalation end-to-end: a moderate tendon (load-sensitive) injury
        # before a high-exposure session is a pull-back, and the command view exposes
        # the authoritative decision_tier the whole UI renders from.
        store = _store_with_plan()
        structured_plan = _combined_contact_and_app_structured_plan()
        structured_plan["weeks"][0]["days"][0]["sessions"][1]["session_type"] = "sparring"
        structured_plan["weeks"][0]["days"][0]["sessions"][1]["title"] = "Hard sparring"
        store.plans[PLAN]["structured_plan"] = structured_plan
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=_checkin_payload(phase="SPP"), now=now
        )

        submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={
                "injuries": [
                    {"body_area": "knee", "description": "knee tendonitis", "severity": "moderate", "status": "ongoing"}
                ]
            },
            now=now,
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="", now=now)
        assert view.today.recommendation_state == "pull_back"
        assert view.today.decision_tier == "pull_back"

    def test_severe_open_injury_is_a_stop_level_risk(self):
        store = _store_with_plan()
        submit_today_injury_checkin(
            store,
            athlete_id=ATHLETE,
            payload={"injuries": [{"body_area": "shoulder", "severity": "severe", "status": "worse"}]},
        )
        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")
        assert "active_injury_worse" in [risk.category for risk in view.risk_watch]

    def test_active_plan_phase_comes_from_resolved_current_week(self):
        store = _store_with_plan()
        # Simulate a legacy/minimal row with no top-level phase. Today must use
        # the current resolved week phase so the frontend cannot downgrade TAPER
        # decisions to GPP when it submits the check-in.
        store.plans[PLAN]["planning_brief"] = _taper_planning_brief()
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )
        assert view.active_plan.get("phase") == "TAPER"

    def test_today_session_uses_current_plan_day(self):
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _calendar_training_brief(active_offsets=[0])
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )
        assert view.today.next_session["calendar_date"] == "2026-06-18"
        assert view.today.next_session["session_id"] == "2026-06-18"
        assert view.today.next_session["session_relation"] == "today"
        assert view.today.next_session["effective_load"] == "technical"

    def test_today_session_falls_forward_to_next_training_day(self):
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _calendar_training_brief(active_offsets=[1])
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )
        assert view.today.next_session["calendar_date"] == "2026-06-19"
        assert view.today.next_session["session_id"] == "2026-06-19"
        assert view.today.next_session["session_relation"] == "next"
        assert view.today.completion_status == "not_started"
        assert view.today.session_scope == "next"

    def test_completed_today_session_falls_forward_to_next_training_day(self):
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _calendar_training_brief(active_offsets=[0, 1])
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)

        active_view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=now,
        )
        assert active_view.today.session_scope == "today"
        assert active_view.today.session_label == "Today's session"
        assert active_view.today.next_session["calendar_date"] == "2026-06-18"

        upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={"plan_id": PLAN, "session_id": "2026-06-18", "status": "done"},
            now=now,
        )

        completed_view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=now,
        )
        assert completed_view.today.completion_status == "done"
        assert completed_view.today.session_scope == "next"
        assert completed_view.today.session_label == "Next session"
        assert completed_view.today.next_session["calendar_date"] == "2026-06-19"
        assert completed_view.today.next_session["session_relation"] == "next"

    def test_completed_today_structured_fallback_uses_earliest_future_date(self):
        store = _store_with_plan()
        store.plans[PLAN]["structured_plan"] = _out_of_order_countdown_structured_plan()
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)

        upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={"plan_id": PLAN, "session_id": "2026-06-23-app", "status": "done"},
            now=now,
        )

        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=now,
        )

        assert view.today.completion_status == "done"
        assert view.today.session_scope == "next"
        assert view.today.next_session["calendar_date"] == "2026-06-26"
        assert view.today.next_session["weekday"] == "Friday"
        assert view.today.next_session["title"] == "Friday app session"
        assert view.today.next_session["title"] != "Saturday technical sparring"

    def test_completed_today_prefers_earlier_structured_app_card_over_later_weekly_technical(self):
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _tuesday_today_saturday_technical_brief()
        store.plans[PLAN]["structured_plan"] = _out_of_order_countdown_structured_plan()
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)

        upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload={"plan_id": PLAN, "session_id": "2026-06-23-app", "status": "done"},
            now=now,
        )

        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=now,
        )

        assert view.today.completion_status == "done"
        assert view.today.session_scope == "next"
        assert view.today.next_session["calendar_date"] == "2026-06-26"
        assert view.today.next_session["weekday"] == "Friday"
        assert view.today.next_session["title"] == "Friday app session"
        assert view.today.next_session["title"] != "Technical sparring"

    def test_calendar_rest_day_falls_forward_to_next_real_session(self):
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _monday_rest_tuesday_training_brief()
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc),
        )
        assert view.today.session_scope == "next"
        assert view.today.session_label == "Next session"
        assert view.today.next_session["calendar_date"] == "2026-06-23"
        assert view.today.next_session["session_relation"] == "next"
        assert view.today.next_session["effective_load"] == "hard"

    def test_structured_today_session_overrides_next_sparring_preview(self):
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _monday_rest_tuesday_training_brief()
        store.plans[PLAN]["structured_plan"] = _monday_strength_structured_plan()
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc),
        )
        assert view.today.session_scope == "today"
        assert view.today.session_label == "Today's session"
        assert view.today.next_session["session_relation"] == "today"
        assert view.today.next_session["session_id"] == "2026-06-22-strength"
        assert view.today.next_session["weekday"] == "Monday"
        assert view.today.next_session["title"] == "Posterior chain strength + control"
        assert view.today.next_session["title"] != "Hard sparring"

    def test_structured_today_combined_contact_prefers_app_session_summary(self):
        store = _store_with_plan()
        store.plans[PLAN]["structured_plan"] = _combined_contact_and_app_structured_plan()

        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
        )

        assert view.today.session_scope == "today"
        assert view.today.next_session["session_relation"] == "today"
        assert view.today.next_session["session_id"] == "2026-06-18-app"
        assert view.today.next_session["title"] == "Power Transfer Touch"
        assert view.today.next_session["coach_led_contact"] == "Coach-led boxing - technical only"
        assert view.today.next_session["title"] != "Hard sparring"

    def test_auto_active_summary_row_rehydrates_structured_today_session_and_phase(self):
        store = SummaryActiveStore()
        store.plans[PLAN] = {
            "id": PLAN,
            "athlete_id": ATHLETE,
            "status": "ready",
            "plan_name": "Camp A",
            "created_at": "2026-06-01T00:00:00+00:00",
            "structured_plan": _monday_strength_structured_plan(),
        }

        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc),
        )

        assert view.active_plan.get("phase") == "GPP"
        assert view.today.session_scope == "today"
        assert view.today.next_session["calendar_date"] == "2026-06-23"
        assert view.today.next_session["title"] == "Hard sparring"

    def test_malformed_structured_session_degrades_without_crashing(self):
        store = _store_with_plan()
        store.plans[PLAN]["structured_plan"] = {
            "weeks": [
                {
                    "phase_label": "GPP",
                    "days": [
                        {
                            "date": "2026-06-23",
                            "day_type": "high",
                            "sessions": ["bad-session"],
                        }
                    ],
                }
            ]
        }

        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc),
        )

        assert view.active_plan.get("phase") == "GPP"
        assert view.today.next_session == {}

    def test_other_plan_checkin_warning_surfaces_in_command_view_without_blocking(self):
        store = _store_with_plan()
        store.plans[OTHER_PLAN] = {
            "id": OTHER_PLAN,
            "athlete_id": ATHLETE,
            "status": "ready",
            "plan_name": "Camp B",
            "created_at": "2026-05-31T00:00:00+00:00",
        }
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        submit_today_checkin(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=_checkin_payload(plan_id=OTHER_PLAN),
            now=now,
        )

        view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="", now=now)

        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.warnings == [
            "You already completed a check-in today. This response applies to the current active plan only."
        ]

    def test_next_session_crosses_into_following_week(self):
        # Week 0 trains only on Mon; the rest of the week is rest. On a later
        # day with no remaining training this week the next session lives in
        # week 1 (Wed). It must surface rather than reporting "No session found".
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _multi_week_taper_brief()
        for now in (
            datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),  # Thu, week 0
            datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),  # Sat, week 0
            datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc),  # Sun, week 0
        ):
            view = build_today_command_view(
                store, athlete_id=ATHLETE, athlete_timezone="", now=now
            )
            assert view.today.next_session["calendar_date"] == "2026-06-24"
            assert view.today.next_session["session_relation"] == "next"

    def test_next_session_prefers_todays_training_day(self):
        # When today itself is the training day, the card shows today's session
        # and never jumps ahead to a later week.
        store = _store_with_plan()
        store.plans[PLAN]["planning_brief"] = _multi_week_taper_brief()
        view = build_today_command_view(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            now=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),  # Mon, week 0
        )
        assert view.today.next_session["calendar_date"] == "2026-06-15"
        assert view.today.next_session["session_relation"] == "today"


class TestSessionCompletion:
    def _payload(self, **overrides) -> dict:
        base = {"plan_id": PLAN, "session_id": "sess-1", "status": "started"}
        return {**base, **overrides}

    def test_start_sets_started_at(self):
        store = _store_with_plan()
        row = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="started")
        )
        assert row["status"] == "started"
        assert row["started_at"]
        assert completion_landing_state(completion_status_of(row)) == "resume"

    def test_done_sets_completed_at(self):
        store = _store_with_plan()
        row = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="done")
        )
        assert row["status"] == "done"
        assert row["completed_at"]
        assert completion_landing_state(completion_status_of(row)) == "completed"

    def test_modified_requires_modification_reason(self):
        store = _store_with_plan()
        with pytest.raises(HTTPException) as exc:
            upsert_session_completion(
                store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="modified")
            )
        assert exc.value.status_code == 422
        row = upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(status="modified", modification_reason="swapped to recovery"),
        )
        assert row["status"] == "modified"
        assert row["completed_at"]

    def test_skipped_is_allowed(self):
        store = _store_with_plan()
        row = upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(status="skipped", modification_reason="travel day"),
        )
        assert row["status"] == "skipped"
        assert completion_landing_state(completion_status_of(row)) == "completed"

    def test_skipped_requires_a_reason(self):
        store = _store_with_plan()
        with pytest.raises(HTTPException) as exc:
            upsert_session_completion(
                store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="skipped")
            )
        assert exc.value.status_code == 422

    def _add_severe_injury(self, store, *, status: str = "open"):
        store.create_injury_flag(
            ATHLETE,
            {
                "source": "checkin",
                "plan_id": PLAN,
                "body_area": "chest",
                "description": "chest bruise",
                "severity": "severe",
                "status": status,
            },
        )

    @pytest.mark.parametrize("training_status", ["started", "done", "modified"])
    def test_active_severe_injury_blocks_training_completion(self, training_status):
        # Server-side hold: a severe injury rejects actually training the session,
        # so the block is enforced at the API, not just hidden in the UI.
        store = _store_with_plan()
        self._add_severe_injury(store)
        payload = self._payload(status=training_status)
        if training_status == "modified":
            payload["modification_reason"] = "tried anyway"
        with pytest.raises(HTTPException) as exc:
            upsert_session_completion(store, athlete_id=ATHLETE, athlete_timezone="", payload=payload)
        assert exc.value.status_code == 409
        assert "severe injury" in exc.value.detail.lower()

    def test_severe_injury_easing_still_blocks_completion(self):
        # The bypass: marking it easing (monitoring) must not open completion.
        store = _store_with_plan()
        self._add_severe_injury(store, status="monitoring")
        with pytest.raises(HTTPException) as exc:
            upsert_session_completion(
                store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="done")
            )
        assert exc.value.status_code == 409

    def test_severe_injury_still_allows_skipping_the_session(self):
        # The athlete can still log that they backed off.
        store = _store_with_plan()
        self._add_severe_injury(store)
        row = upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(status="skipped", modification_reason="injury hold"),
        )
        assert row["status"] == "skipped"

    def test_moderate_injury_does_not_block_completion(self):
        store = _store_with_plan()
        store.create_injury_flag(
            ATHLETE,
            {"source": "checkin", "plan_id": PLAN, "body_area": "calf", "severity": "moderate", "status": "open"},
        )
        row = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="done")
        )
        assert row["status"] == "done"

    def test_resolved_severe_injury_does_not_block_completion_when_supplied(self):
        store = _store_with_plan()
        self._add_severe_injury(store, status="resolved")
        row = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="done")
        )
        assert row["status"] == "done"

    def test_duplicate_completion_upserts_single_row(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
        upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="started"), now=now
        )
        upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(status="done"),
            now=now,
        )
        assert len(store.session_completions[ATHLETE]) == 1
        assert store.session_completions[ATHLETE][0]["status"] == "done"

    def test_completed_at_preserved_on_idempotent_resave(self):
        store = _store_with_plan()
        first = upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(status="done"),
            now=datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc),
        )
        resave = upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(status="done", session_rpe=7),
            now=datetime(2026, 6, 18, 18, 0, tzinfo=timezone.utc),
        )
        # completed_at is not overwritten by the later save.
        assert resave["completed_at"] == first["completed_at"]
        assert resave["session_rpe"] == 7

    def test_backward_transition_clears_completed_at(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)
        upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="done"), now=now
        )
        back = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="started"), now=now
        )
        # Moving back to started keeps started_at but clears completed_at.
        assert back["status"] == "started"
        assert back["started_at"]
        assert back["completed_at"] is None

    def test_reset_to_not_started_clears_both_timestamps(self):
        store = _store_with_plan()
        now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)
        upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="done"), now=now
        )
        reset = upsert_session_completion(
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="not_started"), now=now
        )
        assert reset["started_at"] is None
        assert reset["completed_at"] is None


class TestScanForwardForNextTraining:
    """Direct coverage for the cross-week scan, including dict-shaped entries.

    In production the schedule resolver yields ``WeeklyDayEntry`` objects, but
    the rest of the service treats schedule entries as either objects or plain
    dicts. These assert the scan reads ``calendar_date`` correctly for dict
    entries so it never mistakes a past dated session for the next one.
    """

    @staticmethod
    def _week(days):
        return SimpleNamespace(week_count=2, days=days)

    @staticmethod
    def _parse(value):
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def _scan(self, current_days, later_days, training_date):
        current = self._week(current_days)
        later = self._week(later_days)
        return _scan_forward_for_next_training(
            {"id": PLAN},
            week=current,
            week_index=0,
            training_date=training_date,
            weekly_schedule_or_none=lambda _row, *, week_index: later if week_index == 1 else None,
            parse_iso_date=self._parse,
        )

    def test_dict_entry_skips_past_dated_session(self):
        # A later week whose only training day is dated on/before today must be
        # skipped rather than surfaced as the "next" session.
        past = {"weekday": "Mon", "calendar_date": "2026-06-15", "effective_load": "technical"}
        result = self._scan([], [past], training_date=date(2026, 6, 20))
        assert result is None

    def test_dict_entry_returns_future_dated_session(self):
        future = {"weekday": "Wed", "calendar_date": "2026-06-24", "effective_load": "technical"}
        result = self._scan([], [future], training_date=date(2026, 6, 20))
        assert result is future

    def test_dict_entry_returns_earliest_future_dated_session(self):
        saturday = {"weekday": "Sat", "calendar_date": "2026-06-27", "effective_load": "technical"}
        friday = {"weekday": "Fri", "calendar_date": "2026-06-26", "effective_load": "reduced"}
        result = self._scan([], [saturday, friday], training_date=date(2026, 6, 23))
        assert result is friday

    def test_dict_entry_without_date_is_returned(self):
        # Undated (weekday-only) plans can't be compared, so any later-week
        # training day qualifies as the next session.
        entry = {"weekday": "Wed", "calendar_date": None, "effective_load": "hard"}
        result = self._scan([], [entry], training_date=date(2026, 6, 20))
        assert result is entry


class TestRetroLogCompletion:
    """Explicit past training_day = 7-day back-fill (retro-log) contract."""

    NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)  # training day 2026-06-19

    def _payload(self, **overrides) -> dict:
        base = {"plan_id": PLAN, "session_id": "sess-1", "status": "done"}
        return {**base, **overrides}

    def _upsert(self, store, **overrides):
        return upsert_session_completion(
            store,
            athlete_id=ATHLETE,
            athlete_timezone="",
            payload=self._payload(**overrides),
            now=self.NOW,
        )

    def _structured_store(self):
        store = _store_with_plan()
        store.plans[PLAN]["structured_plan"] = {
            "weeks": [
                {
                    "days": [
                        {
                            "date": "2026-06-16",
                            "sessions": [{"session_id": "sess-1", "title": "Lower power", "blocks": []}],
                        },
                        {
                            "date": "2026-06-17",
                            "sessions": [{"title": "Untitled primary", "blocks": []}],
                        },
                    ]
                }
            ]
        }
        return store

    def test_retro_done_persists_requested_training_day(self):
        store = _store_with_plan()
        row = self._upsert(store, training_day="2026-06-16", session_rpe=7)
        assert row["training_day"] == "2026-06-16"
        assert row["status"] == "done"
        assert row["completed_at"]

    def test_todays_date_in_training_day_behaves_like_the_normal_flow(self):
        store = _store_with_plan()
        row = self._upsert(store, training_day="2026-06-19", status="started")
        assert row["training_day"] == "2026-06-19"
        assert row["status"] == "started"

    def test_future_training_day_is_rejected(self):
        store = _store_with_plan()
        with pytest.raises(HTTPException) as exc:
            self._upsert(store, training_day="2026-06-20")
        assert exc.value.status_code == 422
        assert "future" in exc.value.detail

    def test_older_than_window_is_rejected(self):
        store = _store_with_plan()
        # 2026-06-12 is exactly 7 days back — allowed; 2026-06-11 is not.
        row = self._upsert(store, training_day="2026-06-12")
        assert row["training_day"] == "2026-06-12"
        with pytest.raises(HTTPException) as exc:
            self._upsert(store, training_day="2026-06-11")
        assert exc.value.status_code == 422

    def test_past_day_rejects_non_terminal_statuses(self):
        store = _store_with_plan()
        for bad_status in ("started", "not_started"):
            with pytest.raises(HTTPException) as exc:
                self._upsert(store, training_day="2026-06-16", status=bad_status)
            assert exc.value.status_code == 422

    def test_retro_log_bypasses_the_severe_injury_hold(self):
        # The injury hold protects today's training; a retro-log records what
        # already happened, so it must not be blocked.
        store = _store_with_plan()
        store.create_injury_flag(
            ATHLETE,
            {
                "source": "checkin",
                "plan_id": PLAN,
                "body_area": "chest",
                "description": "chest bruise",
                "severity": "severe",
                "status": "open",
            },
        )
        row = self._upsert(store, training_day="2026-06-16")
        assert row["status"] == "done"
        # The same status logged for today stays blocked.
        with pytest.raises(HTTPException) as exc:
            self._upsert(store)
        assert exc.value.status_code == 409

    def test_structured_plan_rejects_days_outside_the_plan(self):
        store = self._structured_store()
        with pytest.raises(HTTPException) as exc:
            self._upsert(store, training_day="2026-06-15")
        assert exc.value.status_code == 422
        assert "not part of this plan" in exc.value.detail

    def test_structured_plan_rejects_sessions_not_scheduled_that_day(self):
        store = self._structured_store()
        with pytest.raises(HTTPException) as exc:
            self._upsert(store, training_day="2026-06-16", session_id="sess-9")
        assert exc.value.status_code == 422
        assert "not scheduled" in exc.value.detail

    def test_structured_plan_accepts_the_scheduled_session(self):
        store = self._structured_store()
        row = self._upsert(store, training_day="2026-06-16")
        assert row["training_day"] == "2026-06-16"

    def test_structured_plan_accepts_the_day_date_fallback_id(self):
        # An id-less primary session logs under the day-date session id,
        # mirroring _structured_session_entry_for_day.
        store = self._structured_store()
        row = self._upsert(store, training_day="2026-06-17", session_id="2026-06-17")
        assert row["session_id"] == "2026-06-17"

    def test_skipped_retro_log_still_requires_a_reason(self):
        store = _store_with_plan()
        with pytest.raises(HTTPException) as exc:
            self._upsert(store, training_day="2026-06-16", status="skipped")
        assert exc.value.status_code == 422
        row = self._upsert(
            store, training_day="2026-06-16", status="skipped", modification_reason="was travelling"
        )
        assert row["status"] == "skipped"
