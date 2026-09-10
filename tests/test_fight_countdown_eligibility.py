from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import api.services.push_notifications as push_notifications
from api.services.fight_countdown_eligibility import (
    LATE_FIGHT_COUNTDOWN_COPY,
    filter_late_fight_countdown_candidates,
    late_fight_countdown_candidate_is_eligible,
)
from api.services.notification_foundation import NotificationCandidate
from api.services.notification_templates import (
    LATE_FIGHT_COUNTDOWN_COPY as TEMPLATE_COPY,
)


class CountdownStore:
    def __init__(self) -> None:
        self.active_plan_id = "plan-active"
        self.plans: dict[str, dict] = {
            "plan-active": {
                "id": "plan-active",
                "athlete_id": "athlete-1",
                "status": "ready",
                "technical_style": ["boxing"],
                "fight_date": "2026-09-13",
            },
            "plan-old": {
                "id": "plan-old",
                "athlete_id": "athlete-1",
                "status": "ready",
                "technical_style": ["boxing"],
                "fight_date": "2026-09-13",
            },
        }

    def get_active_plan_id(self, _athlete_id: str) -> str | None:
        return self.active_plan_id

    def get_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict | None:
        plan = self.plans.get(plan_id)
        if plan is None or plan.get("athlete_id") != athlete_id:
            return None
        return dict(plan)


def _candidate(*, plan_id: str = "plan-active", variant_id: str = "fc-d03") -> NotificationCandidate:
    countdown = "D-3" if variant_id == "fc-d03" else "D-1"
    training_day = "2026-09-10" if variant_id == "fc-d03" else "2026-09-12"
    return NotificationCandidate(
        profile_id="athlete-1",
        notification_type="fight_countdown",
        intent="fight_countdown",
        category="plan_update_alerts",
        priority=48,
        title="old title",
        body="old body",
        url=f"/plans/{plan_id}",
        tag="fight-countdown",
        dedupe_key=f"fight-countdown:{plan_id}:{countdown}",
        expires_at=datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc) + timedelta(days=2),
        timezone_name="UTC",
        training_day=training_day,
        variant_id=variant_id,
        notification_class="event",
        source_event_metadata={"plan_id": plan_id, "countdown": countdown},
    )


def test_d3_requires_current_active_combat_plan_with_bout_date() -> None:
    store = CountdownStore()
    assert late_fight_countdown_candidate_is_eligible(store, _candidate()) is True


def test_d1_accepts_normalized_combat_alias_on_active_plan() -> None:
    store = CountdownStore()
    store.plans["plan-active"]["technical_style"] = ["Boxer"]
    assert late_fight_countdown_candidate_is_eligible(
        store,
        _candidate(variant_id="fc-d01"),
    ) is True


def test_non_combat_profile_tag_cannot_make_non_combat_active_plan_eligible() -> None:
    store = CountdownStore()
    store.plans["plan-active"]["technical_style"] = ["football"]
    assert late_fight_countdown_candidate_is_eligible(store, _candidate()) is False


def test_missing_confirmed_bout_date_fails_closed() -> None:
    store = CountdownStore()
    store.plans["plan-active"]["fight_date"] = None
    assert late_fight_countdown_candidate_is_eligible(store, _candidate()) is False


def test_candidate_from_old_saved_plan_is_rejected_after_active_plan_switch() -> None:
    store = CountdownStore()
    assert late_fight_countdown_candidate_is_eligible(
        store,
        _candidate(plan_id="plan-old"),
    ) is False


def test_bout_date_change_invalidates_stale_d3_candidate() -> None:
    store = CountdownStore()
    store.plans["plan-active"]["fight_date"] = "2026-09-14"
    assert late_fight_countdown_candidate_is_eligible(store, _candidate()) is False


def test_late_countdown_filter_enforces_approved_copy_within_push_limits() -> None:
    store = CountdownStore()
    for variant_id in ("fc-d03", "fc-d01"):
        filtered = filter_late_fight_countdown_candidates(
            store,
            [_candidate(variant_id=variant_id)],
        )
        assert len(filtered) == 1
        title, body = LATE_FIGHT_COUNTDOWN_COPY[variant_id]
        assert filtered[0].title == title
        assert filtered[0].body == body
        assert len(title) <= 40
        assert len(body) <= 90

    d3 = LATE_FIGHT_COUNTDOWN_COPY["fc-d03"]
    assert d3 == (
        "D-3. FRESHNESS WINS NOW.",
        "No added conditioning, extra rounds or fatigue. Touch the sharpness, then leave it.",
    )
    d1 = LATE_FIGHT_COUNTDOWN_COPY["fc-d01"]
    assert d1 == (
        "D-1. THE WORK IS DONE. KEEP TODAY LIGHT",
        "and sharp. No extra conditioning or unnecessary rounds. Follow your coach's plan.",
    )


def test_other_notification_variants_are_untouched() -> None:
    store = CountdownStore()
    candidate = _candidate(variant_id="fc-d07")
    filtered = filter_late_fight_countdown_candidates(store, [candidate])
    assert filtered == [candidate]


def test_bundled_template_copy_is_the_same_source_as_the_delivery_guard() -> None:
    # One owner for the approved strings: the bundled catalogue, the Supabase v2
    # rows and the last-mile enforcement cannot drift apart.
    assert LATE_FIGHT_COUNTDOWN_COPY is TEMPLATE_COPY


def test_non_supported_sports_combat_disciplines_still_qualify() -> None:
    store = CountdownStore()
    for style in ("karate", "Grappler", "wrestling"):
        store.plans["plan-active"]["technical_style"] = [style]
        assert late_fight_countdown_candidate_is_eligible(store, _candidate()) is True


def test_candidate_carrying_only_notification_type_is_gated_and_recopied() -> None:
    store = CountdownStore()
    candidate = replace(_candidate(plan_id="plan-old"), intent="")
    assert late_fight_countdown_candidate_is_eligible(store, candidate) is False

    eligible = replace(_candidate(), intent="")
    filtered = filter_late_fight_countdown_candidates(store, [eligible])
    assert filtered[0].title == LATE_FIGHT_COUNTDOWN_COPY["fc-d03"][0]


def test_enforced_copy_is_recorded_in_source_metadata() -> None:
    store = CountdownStore()
    filtered = filter_late_fight_countdown_candidates(store, [_candidate()])
    assert filtered[0].source_event_metadata["late_countdown_copy_enforced"] is True


def test_ineligible_candidate_never_reaches_the_delivery_ledger(monkeypatch) -> None:
    """The ordering the whole guard depends on: filter before any claim."""

    store = CountdownStore()
    prepared_with: list[list[NotificationCandidate]] = []

    monkeypatch.setattr(
        push_notifications, "push_notifications_configured", lambda: True
    )
    monkeypatch.setattr(
        push_notifications,
        "prepare_notification_delivery",
        lambda _store, candidates, **_kwargs: prepared_with.append(list(candidates)),
    )

    candidates = [_candidate(plan_id="plan-old")]
    assert push_notifications.dispatch_push_candidates(store, candidates) == 0
    assert prepared_with == []
    # The caller's list shrinks so morning_push does not treat a rejected
    # countdown as a delivered candidate and skip its fallbacks.
    assert candidates == []
