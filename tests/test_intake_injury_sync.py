"""Regression coverage for intake injuries entering live daily tracking."""

from concurrent.futures import ThreadPoolExecutor

from api.auth import AuthenticatedUser
from api.rehab_labels import resolve_rehab_label_policy
from api.services.intake_injury_sync import sync_intake_injuries_for_plan
from api.services.today_readiness_boundary import build_today_command_view
from tests.support import FakeStore, _build_client, _build_request, finalized_result

ATHLETE = "athlete-1"
AUTH = {"Authorization": "Bearer athlete-token"}
ANKLE_DESCRIPTION = "Left ankle: tendon ligament. sprain"


def _active_ankle_intake() -> dict:
    return {
        "guided_injuries": [
            {
                "area": "Left ankle",
                "zone": "l_ankle",
                "severity": "moderate",
                "trend": "stable",
                "injury_type": "tendon_ligament",
                "injury_subtypes": ["sprain"],
                "timeframe": "three_plus_months",
                # Medical clearance permits training around the injury; it does
                # not mean the injury itself has resolved.
                "cleared": "yes",
            }
        ]
    }


def _ensure_profile(store: FakeStore) -> None:
    if ATHLETE not in store.profiles:
        store.ensure_profile(
            AuthenticatedUser(
                user_id=ATHLETE,
                email="ari@example.com",
                full_name="Ari Mensah",
                metadata={},
            )
        )


def _seed_generated_plan(
    store: FakeStore,
    *,
    intake_id: str,
    intake: dict | None = None,
    active: bool = True,
) -> dict:
    _ensure_profile(store)
    plan = store.create_plan(
        athlete_id=ATHLETE,
        intake_id=intake_id,
        request=_build_request(),
        result=finalized_result(),
    )
    if active:
        store.set_active_plan_id(ATHLETE, plan["id"])
    store.intakes.setdefault(ATHLETE, []).append(
        {
            "id": intake_id,
            "athlete_id": ATHLETE,
            "intake": intake or _active_ankle_intake(),
            "created_at": "2026-08-04T00:00:00+00:00",
        }
    )
    return plan


def _create_legacy_ankle_flag(
    store: FakeStore,
    *,
    plan_id: str,
    status: str,
    resolved_at: str | None = None,
) -> dict:
    return store.create_injury_flag(
        ATHLETE,
        {
            "plan_id": plan_id,
            "source": "intake",
            "source_key": None,
            "body_area": "Left ankle",
            "description": ANKLE_DESCRIPTION,
            "severity": "moderate",
            "status": status,
            "resolved_at": resolved_at,
        },
    )


def test_canonical_background_path_recognises_medically_cleared_active_injury() -> None:
    """XP and notification consumers call the canonical boundary directly."""
    store = FakeStore()
    _seed_generated_plan(store, intake_id="intake-current")

    view = build_today_command_view(
        store,
        athlete_id=ATHLETE,
        athlete_timezone="",
    )
    policy = resolve_rehab_label_policy(store, athlete_id=ATHLETE)

    assert [injury["body_area"] for injury in view.open_injuries] == ["Left ankle"]
    assert [region.region for region in policy.active_regions] == ["ankle"]


def test_today_and_plan_reads_create_one_intake_flag_under_concurrency() -> None:
    client, store, _ = _build_client()
    plan = _seed_generated_plan(store, intake_id="intake-current")

    def read_today() -> int:
        return client.get("/api/today", headers=AUTH).status_code

    def read_plan() -> int:
        return client.get(f"/api/plans/{plan['id']}", headers=AUTH).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(
            pool.map(
                lambda index: read_today() if index % 2 else read_plan(),
                range(16),
            )
        )

    assert statuses == [200] * 16
    intake_flags = [
        flag for flag in store.injury_flags[ATHLETE] if flag.get("source") == "intake"
    ]
    assert len(intake_flags) == 1
    assert intake_flags[0].get("source_key")


def test_resolved_old_plan_injury_does_not_block_new_same_area_injury() -> None:
    store = FakeStore()
    old_plan = _seed_generated_plan(
        store,
        intake_id="intake-old",
        active=False,
    )
    old_flags = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=old_plan,
    )
    store.update_injury_flag(
        old_flags[0]["id"],
        {
            "status": "resolved",
            "resolved_at": "2026-08-01T12:00:00+00:00",
        },
    )

    new_plan = _seed_generated_plan(
        store,
        intake_id="intake-new",
        active=True,
    )
    new_flags = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=new_plan,
    )

    assert len(new_flags) == 1
    assert new_flags[0]["plan_id"] == new_plan["id"]
    assert new_flags[0]["status"] == "open"
    assert len({flag["source_key"] for flag in store.injury_flags[ATHLETE]}) == 2


def test_failed_injury_flag_read_causes_no_blind_insert() -> None:
    class FailedReadStore(FakeStore):
        def list_injury_flags(self, *args, **kwargs):
            raise RuntimeError("temporary injury_flags read failure")

    store = FailedReadStore()
    plan = _seed_generated_plan(store, intake_id="intake-current")

    flags = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=plan,
    )

    assert flags == []
    assert store.injury_flags.get(ATHLETE, []) == []


def test_legacy_open_null_key_is_adopted_without_duplicate() -> None:
    store = FakeStore()
    plan = _seed_generated_plan(store, intake_id="intake-current")
    legacy = _create_legacy_ankle_flag(
        store,
        plan_id=plan["id"],
        status="open",
    )

    active = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=plan,
    )

    rows = [
        flag for flag in store.injury_flags[ATHLETE] if flag.get("source") == "intake"
    ]
    assert len(rows) == 1
    assert rows[0]["id"] == legacy["id"]
    assert rows[0]["status"] == "open"
    assert rows[0]["source_key"]
    assert [flag["id"] for flag in active] == [legacy["id"]]


def test_legacy_resolved_null_key_stays_resolved_and_is_not_reopened() -> None:
    store = FakeStore()
    plan = _seed_generated_plan(store, intake_id="intake-current")
    resolved_at = "2026-08-02T09:15:00+00:00"
    legacy = _create_legacy_ankle_flag(
        store,
        plan_id=plan["id"],
        status="resolved",
        resolved_at=resolved_at,
    )

    active = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=plan,
    )

    rows = [
        flag for flag in store.injury_flags[ATHLETE] if flag.get("source") == "intake"
    ]
    assert active == []
    assert len(rows) == 1
    assert rows[0]["id"] == legacy["id"]
    assert rows[0]["status"] == "resolved"
    assert rows[0]["resolved_at"] == resolved_at
    assert rows[0]["source_key"]


def test_legacy_duplicates_are_collapsed_without_reopening_resolved_state() -> None:
    store = FakeStore()
    plan = _seed_generated_plan(store, intake_id="intake-current")
    _create_legacy_ankle_flag(
        store,
        plan_id=plan["id"],
        status="open",
    )
    resolved = _create_legacy_ankle_flag(
        store,
        plan_id=plan["id"],
        status="resolved",
        resolved_at="2026-08-02T09:15:00+00:00",
    )

    active = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=plan,
    )

    rows = [
        flag for flag in store.injury_flags[ATHLETE] if flag.get("source") == "intake"
    ]
    canonical = next(flag for flag in rows if flag["id"] == resolved["id"])
    assert active == []
    assert canonical["status"] == "resolved"
    assert canonical["source_key"]
    assert len({flag["source_key"] for flag in rows}) == 2
    assert all(flag["status"] == "resolved" for flag in rows)


def test_old_cleared_timeframe_remains_history_only() -> None:
    store = FakeStore()
    _seed_generated_plan(
        store,
        intake_id="intake-history",
        intake={
            "guided_injuries": [
                {
                    **_active_ankle_intake()["guided_injuries"][0],
                    "timeframe": "old_cleared",
                    "cleared": "no",
                }
            ]
        },
    )

    view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="")

    assert view.open_injuries == []
    assert store.injury_flags.get(ATHLETE, []) == []
