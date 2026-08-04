"""Regression coverage for intake injuries entering live daily tracking."""

from api.auth import AuthenticatedUser
from api.rehab_labels import resolve_rehab_label_policy
from api.services.intake_injury_sync import sync_intake_injuries_for_plan
from tests.support import FakeStore, _build_client, _build_request, finalized_result

ATHLETE = "athlete-1"
AUTH = {"Authorization": "Bearer athlete-token"}
INTAKE_ID = "intake-ankle"


def _active_ankle_intake(
    *,
    timeframe: str = "three_plus_months",
    medical_clearance: str = "yes",
) -> dict:
    return {
        "guided_injuries": [
            {
                "area": "Left ankle",
                "zone": "l_ankle",
                "severity": "moderate",
                "trend": "stable",
                "injury_type": "tendon_ligament",
                "injury_subtypes": ["sprain"],
                "timeframe": timeframe,
                # This answers "Have you been medically cleared?". It permits
                # training around the injury; it does not mean the injury healed.
                "cleared": medical_clearance,
            }
        ]
    }


def _seed_generated_plan(store, *, intake: dict | None = None) -> dict:
    if ATHLETE not in store.profiles:
        store.ensure_profile(
            AuthenticatedUser(
                user_id=ATHLETE,
                email="ari@example.com",
                full_name="Ari Mensah",
                metadata={},
            )
        )
    plan = store.create_plan(
        athlete_id=ATHLETE,
        intake_id=INTAKE_ID,
        request=_build_request(),
        result=finalized_result(),
    )
    store.set_active_plan_id(ATHLETE, plan["id"])
    store.intakes.setdefault(ATHLETE, []).append(
        {
            "id": INTAKE_ID,
            "athlete_id": ATHLETE,
            "intake": intake or _active_ankle_intake(),
            "created_at": "2026-08-04T00:00:00+00:00",
        }
    )
    return plan


def test_medically_cleared_intake_injury_stays_active_for_rehab_labels() -> None:
    store = FakeStore()
    plan = _seed_generated_plan(store)

    flags = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=plan,
    )
    policy = resolve_rehab_label_policy(store, athlete_id=ATHLETE)

    assert len(flags) == 1
    assert flags[0]["source"] == "intake"
    assert flags[0]["body_area"] == "Left ankle"
    assert flags[0]["status"] == "open"
    assert [region.region for region in policy.active_regions] == ["ankle"]


def test_old_cleared_timeframe_remains_resolved_history() -> None:
    store = FakeStore()
    plan = _seed_generated_plan(
        store,
        intake=_active_ankle_intake(
            timeframe="old_cleared",
            medical_clearance="no",
        ),
    )

    flags = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=plan,
    )
    policy = resolve_rehab_label_policy(store, athlete_id=ATHLETE)

    assert flags == []
    assert policy.default_mode == "prehab"
    assert policy.active_regions == []
    assert len(store.injury_flags[ATHLETE]) == 1
    assert store.injury_flags[ATHLETE][0]["status"] == "resolved"


def test_today_read_synchronizes_generated_plan_injury_into_daily_tracker() -> None:
    client, store, _ = _build_client()
    _seed_generated_plan(store)

    response = client.get("/api/today", headers=AUTH)

    assert response.status_code == 200
    injuries = response.json()["open_injuries"]
    assert len(injuries) == 1
    assert injuries[0]["body_area"] == "Left ankle"
    assert injuries[0]["source"] == "intake"


def test_today_does_not_reseed_old_cleared_history_as_live_injury() -> None:
    client, store, _ = _build_client()
    _seed_generated_plan(
        store,
        intake=_active_ankle_intake(
            timeframe="old_cleared",
            medical_clearance="no",
        ),
    )

    response = client.get("/api/today", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["open_injuries"] == []
    assert len(store.injury_flags[ATHLETE]) == 1
    assert store.injury_flags[ATHLETE][0]["status"] == "resolved"


def test_plan_read_self_heals_rehab_policy_without_visiting_today_first() -> None:
    client, store, _ = _build_client()
    plan = _seed_generated_plan(store)

    response = client.get(f"/api/plans/{plan['id']}", headers=AUTH)

    assert response.status_code == 200
    policy = response.json()["rehab_label_policy"]
    assert policy["default_mode"] == "prehab"
    assert [region["region"] for region in policy["active_regions"]] == ["ankle"]
    assert len(store.injury_flags[ATHLETE]) == 1
