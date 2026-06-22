"""Contract-to-storage integration tests for the Today/Overview service.

These exercise api/services/today_service.py against the in-memory FakeStore with
an injected ``now``, so training-day boundaries and recommendation validity are
deterministic without a live clock or database.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from api.contracts.completion import completion_landing_state, completion_status_of
from api.services.today_service import (
    _scan_forward_for_next_training,
    build_today_command_view,
    submit_today_checkin,
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
        assert row["recommendation_reason"] == "Poor sleep; use the modified option today."
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

    def test_client_supplied_recommendation_is_ignored(self):
        store = _store_with_plan()
        # Client tries to force train_as_planned, but pain=high is a hard override.
        payload = _checkin_payload(pain="high", recommendation_state="train_as_planned")
        row = submit_today_checkin(store, athlete_id=ATHLETE, athlete_timezone="", payload=payload)
        assert row["recommendation_state"] == "pull_back"


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
        assert view.today.next_session["title"] == "Posterior chain strength + control"
        assert view.today.next_session["title"] != "Hard sparring"

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
            store, athlete_id=ATHLETE, athlete_timezone="", payload=self._payload(status="skipped")
        )
        assert row["status"] == "skipped"
        assert completion_landing_state(completion_status_of(row)) == "completed"

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

    def test_dict_entry_without_date_is_returned(self):
        # Undated (weekday-only) plans can't be compared, so any later-week
        # training day qualifies as the next session.
        entry = {"weekday": "Wed", "calendar_date": None, "effective_load": "hard"}
        result = self._scan([], [entry], training_date=date(2026, 6, 20))
        assert result is entry
