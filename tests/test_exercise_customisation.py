"""Athlete swaps, additions and removals on app-generated plans.

The generated card is never edited: changes live in plans.exercise_overrides
and are applied on read, so Plan Detail, Today, session start and exercise
logging all see the same effective workout.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta
from uuid import uuid4

import pytest

from api.models import PlanRequest
from api.services.exercise_overrides import apply_exercise_overrides, override_block_id
from api.services.today_service import _structured_day_for_training_day, resolve_training_day
from tests.support import _build_client

AUTH = {"Authorization": "Bearer athlete-token"}
OTHER = {"Authorization": "Bearer admin-token"}
PLAN_ID = "33333333-3333-3333-3333-333333333333"
OPEN_PLAN_ID = "44444444-4444-4444-4444-444444444444"
SESSION_ID = "s-strength"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@pytest.fixture(autouse=True)
def no_clinical_policies(monkeypatch):
    monkeypatch.setattr("fightcamp.rehab_clinical.load_clinical_policies", lambda: ())
    monkeypatch.setattr("api.services.today_service.load_clinical_policies", lambda: ())


def back_squat(**extra) -> dict:
    return {
        "block_type": "strength", "display_name": "Back Squat", "exercise_key": "back-squat",
        "sets": 4, "reps": 5, "effort": {"method": "RPE", "value": 7},
        "rest": {"value": 180, "unit": "seconds"},
        "load": {"method": "absolute", "value": 100, "unit": "kg", "display": "100 kg"},
        "intensity": "100 kg",
        **extra,
    }


def plank(**extra) -> dict:
    return {"block_type": "accessory", "display_name": "Front Plank", "duration": {"value": 45, "unit": "seconds"},
            "sets": 3, **extra}


def rehab_block() -> dict:
    return {"block_type": "rehab", "display_name": "Ankle Alphabet", "block_id": "rehab-ankle",
            "duration": {"value": 120, "unit": "seconds"}}


def intake(store, **extra):
    request = PlanRequest(
        athlete={"full_name": "Ari Mensah", "technical_style": ["boxing"]}, no_scheduled_fight=True,
        equipment_access=extra.pop("equipment", ["barbell", "dumbbells", "kettlebell", "bands"]),
        key_goals=extra.pop("goals", ["strength"]), **extra,
    )
    return store.create_intake("athlete-1", request)


ANCHOR = {"intent": "Own each rep.", "focus_cue": "Brace", "reset_cue": "Breathe"}


def valid_card(weeks: list[dict]) -> dict:
    """Fill the display schema's required fields so Plan Detail renders the card."""
    for week in weeks:
        week.setdefault("week_goal", "Build strength")
        week.setdefault("start_date", "")
        week.setdefault("end_date", "")
        week.setdefault("load_focus", {k: "maintain" for k in ("volume", "intensity", "specificity", "fatigue_target")})
        week.setdefault("progression", {"week_type": "stabilise", "planned_change_from_previous": ""})
        for day in week["days"]:
            day.setdefault("day_type", "moderate")
            day.setdefault("countdown_label", "")
            day.setdefault("today_card", {"headline": "Strength", "readiness_status": "train_as_planned",
                                          "mindset_anchor": ANCHOR})
            for session in day["sessions"]:
                session.setdefault("objective", "Lower-body strength")
                session.setdefault("mindset_anchor", ANCHOR)
    return {
        "plan_metadata": {"title": "Camp", "sport": "boxing", "plan_type": "open_ongoing_system", "timezone": "UTC",
                          "status": "active", "created_by": "planner"},
        "athlete_context": {"athlete_id": "athlete-1", "sport_profile": "boxing"},
        "event_context": {"event_type": "none"},
        "weeks": weeks,
        "nutrition": {k: "" for k in ("summary", "daily_focus", "training_day_guidance", "fight_week_guidance")},
    }


def seed_dated(store, *, blocks=None, days_ahead=(0,), phase="GPP"):
    today = date.fromisoformat(resolve_training_day(None))
    row = intake(store)
    store.plans[PLAN_ID] = {
        "id": PLAN_ID, "athlete_id": "athlete-1", "intake_id": row["id"], "status": "ready",
        "plan_name": "Camp A", "created_at": f"{today - timedelta(days=3)}T00:00:00+00:00",
        "exercise_overrides": [], "exercise_overrides_revision": 0,
        "structured_plan": valid_card([{"week_index": 1, "phase_label": phase, "days": [
            {"date": (today + timedelta(days=offset)).isoformat(), "phase_label": phase, "sessions": [
                {"session_id": f"{SESSION_ID}-{offset}" if offset else SESSION_ID, "session_type": "strength_power",
                 "title": "Strength", "blocks": copy.deepcopy(blocks or [back_squat(), plank()])},
            ]} for offset in days_ahead
        ]}]),
    }
    store.set_active_plan_id("athlete-1", PLAN_ID)
    return today


def seed_open(store, *, blocks=None):
    """An AI open plan: one weekly template on today's weekday and the next."""
    today = date.fromisoformat(resolve_training_day(None))
    monday = today - timedelta(days=today.weekday())
    weekday = WEEKDAYS[today.weekday()]
    second = WEEKDAYS[(today.weekday() + 1) % 7]
    training_days = [d for d in WEEKDAYS if d in {weekday, second}]
    row = intake(store)
    template_days = []
    for day in training_days:
        template_days.append({"date": "", "weekday": day, "phase_label": "GPP", "day_type": "moderate", "sessions": [
            {"session_type": "strength_power", "title": "Strength" if day == weekday else "Power",
             "blocks": copy.deepcopy(blocks or [back_squat(), plank()]) if day == weekday else [plank()]},
        ]})
    store.plans[OPEN_PLAN_ID] = {
        "id": OPEN_PLAN_ID, "athlete_id": "athlete-1", "intake_id": row["id"], "status": "ready",
        "plan_name": "Open", "created_at": f"{monday}T12:00:00+00:00",
        "exercise_overrides": [], "exercise_overrides_revision": 0,
        "planning_brief": {
            "athlete_snapshot": {"plan_creation_weekday": "Mon", "plan_creation_weekday_basis": "athlete_local_weekday"},
            "open_plan_spec": {"plan_type": "open_ongoing_system", "weekly_template": {"training_days": training_days}},
        },
        "structured_plan": valid_card([{"week_index": 1, "phase_label": "GPP", "days": template_days}]),
    }
    store.set_active_plan_id("athlete-1", OPEN_PLAN_ID)
    return today


def day_blocks(store, plan_id, day, session_id=None):
    matched = _structured_day_for_training_day(store.plans[plan_id], day.isoformat() if isinstance(day, date) else day)
    assert matched is not None
    sessions = matched[0]["sessions"]
    session = next(s for s in sessions if session_id is None or s["session_id"] == session_id)
    return session, session["blocks"]


def detail_day(client, plan_id, day):
    detail = client.get(f"/api/plans/{plan_id}", headers=AUTH)
    assert detail.status_code == 200, detail.text
    return next(d for w in detail.json()["outputs"]["structured_plan"]["weeks"] for d in w["days"]
                if d["date"] == day.isoformat())


def squat_id(day):
    return f"blk-{day.isoformat()}-back-squat"


def options(client, plan_id, day, session_id, block_id, **params):
    return client.get(f"/api/plans/{plan_id}/exercise-changes/alternatives", headers=AUTH,
                      params={"date": day.isoformat(), "session_id": session_id, "block_id": block_id, **params})


def change(client, plan_id, **body):
    payload = {"client_request_id": str(uuid4()), **body}
    return client.post(f"/api/plans/{plan_id}/exercise-changes", headers=AUTH, json=payload), payload


# ---------------------------------------------------------------------------
# Alternatives
# ---------------------------------------------------------------------------


def test_alternatives_preserve_purpose_and_respect_equipment_and_metadata():
    client, store, _ = _build_client()
    today = seed_dated(store)
    response = options(client, PLAN_ID, today, SESSION_ID, squat_id(today))
    assert response.status_code == 200, response.text
    body = response.json()
    names = [a["name"] for a in body["alternatives"]]
    assert names, body
    assert "Back Squat" not in names and "Front Plank" not in names
    assert len(names) <= 5
    for alternative in body["alternatives"]:
        # Evidence-backed reasons only: every top pick names a real match.
        assert alternative["reason"]
    # Same squat pattern, from the verified bank, within the athlete's kit.
    assert "Cossack Squat" in names
    assert any("squat pattern" in (a["reason"] or "").lower() for a in body["alternatives"])
    # No pull-up bar / trap bar / sled options without that equipment.
    for alternative in body["alternatives"]:
        assert not any(e.lower() in {"trap bar", "sled", "pullup bar", "machine"} for e in alternative["equipment"] or [])
    assert body["scopes"] == [{"value": "occurrence", "label": "Just this workout"}]


def test_equipment_mismatch_is_excluded():
    client, store, _ = _build_client()
    today = seed_dated(store)
    store.intakes["athlete-1"][-1]["intake"]["equipment_access"] = []
    body = options(client, PLAN_ID, today, SESSION_ID, squat_id(today)).json()
    from fightcamp.training_context import normalize_equipment_list
    from api.services.training_library import cache
    index = cache.get()
    for alternative in body["alternatives"]:
        raw = index.by_id[alternative["catalogue_id"]]["entry"]["raw"]
        assert set(normalize_equipment_list(raw.get("equipment"))) <= {"bodyweight", "none"}


def test_alternatives_never_raise_session_stress_or_phase():
    client, store, _ = _build_client()
    today = seed_dated(store)
    from api.services.training_library import cache
    index = cache.get()
    body = options(client, PLAN_ID, today, SESSION_ID, squat_id(today), all=True).json()
    ranks = {"none": 0, "low": 1, "moderate": 2, "high": 3}
    original = next(r for r in index.records if r["entry"]["exercise_key"] == "back-squat")["entry"]["raw"]
    for alternative in body["alternatives"]:
        raw = index.by_id[alternative["catalogue_id"]]["entry"]["raw"]
        assert "GPP" in raw["phases"]
        for field in ("cns_load", "movement_cost", "impact_cost"):
            assert ranks[raw[field]] <= ranks[original[field]], (alternative["name"], field)


def test_dose_carries_sets_reps_effort_but_never_absolute_load():
    client, store, _ = _build_client()
    today = seed_dated(store)
    body = options(client, PLAN_ID, today, SESSION_ID, squat_id(today)).json()
    cossack = next(a for a in body["alternatives"] if a["name"] == "Cossack Squat")
    assert cossack["prescription"] == "4 × 5 · RPE 7"
    response, _ = change(client, PLAN_ID, action="swap", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today), catalogue_id=cossack["catalogue_id"])
    assert response.status_code == 200, response.text
    _, blocks = day_blocks(store, PLAN_ID, today)
    swapped = blocks[0]
    assert swapped["display_name"] == "Cossack Squat"
    assert swapped["exercise_key"] == "cossack-squat"
    assert (swapped["sets"], swapped["reps"]) == (4, 5)
    assert swapped["effort"] == {"method": "RPE", "value": 7}
    assert swapped["rest"] == {"value": 180, "unit": "seconds"}
    assert "load" not in swapped and "intensity" not in swapped
    assert swapped["athlete_change"]["original_name"] == "Back Squat"


def test_incompatible_interval_dose_is_not_copied():
    client, store, _ = _build_client()
    today = seed_dated(store, blocks=[back_squat(sets=None, reps=None, rounds=6, work={"value": 30, "unit": "seconds"}), plank()])
    body = options(client, PLAN_ID, today, SESSION_ID, squat_id(today)).json()
    assert body["alternatives"]
    for alternative in body["alternatives"]:
        # Rep work cannot inherit a 6 × 30s interval prescription.
        assert alternative["dose_required"] is True
        assert alternative["prescription"] is None
    pick = body["alternatives"][0]
    response, _ = change(client, PLAN_ID, action="swap", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today), catalogue_id=pick["catalogue_id"])
    assert response.status_code == 422
    response, _ = change(client, PLAN_ID, action="swap", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today), catalogue_id=pick["catalogue_id"],
                         dose={"mode": "reps", "sets": 3, "reps": 8})
    assert response.status_code == 200, response.text
    _, blocks = day_blocks(store, PLAN_ID, today)
    assert (blocks[0]["sets"], blocks[0]["reps"]) == (3, 8)
    assert "rounds" not in blocks[0] and "work" not in blocks[0]


def squat_hold(**extra) -> dict:
    return {"block_type": "strength", "display_name": "Squat Isometric", "exercise_key": "squat-isometric-110-1rm-parallel",
            "sets": 3, "duration": {"value": 6, "unit": "seconds"}, "rest": {"value": 120, "unit": "seconds"}, **extra}


def test_injury_restriction_cannot_be_bypassed():
    from fightcamp.injury_filtering import injury_flag_reasons, injury_violation_reasons
    from api.services.training_library import cache

    index = cache.get()
    client, store, _ = _build_client()
    today = seed_dated(store, blocks=[squat_hold(), plank()])
    hold_id = f"blk-{today}-squat-isometric-110-1rm-parallel"
    healthy = options(client, PLAN_ID, today, SESSION_ID, hold_id, all=True).json()
    front = next(a for a in healthy["alternatives"] if a["exercise_key"] == "front-squat-isometric-105-1rm-100")

    store.create_injury_flag("athlete-1", {"body_area": "knee", "description": "knee pain on squats"})
    injured = options(client, PLAN_ID, today, SESSION_ID, hold_id, all=True).json()
    # Heavy knee-dominant work is what the planner itself excludes for a knee.
    assert front["exercise_key"] not in {a["exercise_key"] for a in injured["alternatives"]}
    for alternative in injured["alternatives"]:
        raw = dict(index.by_id[alternative["catalogue_id"]]["entry"]["raw"])
        assert not injury_violation_reasons(raw, ["knee knee pain on squats"])
        assert not injury_flag_reasons(raw, ["knee knee pain on squats"])
    # A forged write for it is refused server-side, however well it matched.
    response, _ = change(client, PLAN_ID, action="swap", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=hold_id, catalogue_id=front["catalogue_id"])
    assert response.status_code == 409
    assert store.plans[PLAN_ID]["exercise_overrides"] == []


def test_unknown_injury_state_fails_closed():
    client, store, _ = _build_client()
    today = seed_dated(store)

    def broken(*args, **kwargs):
        raise RuntimeError("injury store down")

    store.list_injury_flags = broken
    response = options(client, PLAN_ID, today, SESSION_ID, squat_id(today))
    assert response.status_code == 503


def test_unknown_or_unavailable_candidates_are_refused_server_side():
    client, store, _ = _build_client()
    today = seed_dated(store)
    from api.services.training_library import cache
    index = cache.get()
    trap = next(r for r in index.records if r["entry"]["exercise_key"] == "trap-bar-deadlift")
    response, _ = change(client, PLAN_ID, action="swap", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today), catalogue_id=trap["entry"]["catalogue_id"])
    assert response.status_code == 409
    response, _ = change(client, PLAN_ID, action="swap", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today), catalogue_id="exercise_bank.json:not-real")
    assert response.status_code == 409
    assert store.plans[PLAN_ID]["exercise_overrides"] == []


# ---------------------------------------------------------------------------
# Swap / remove / add / undo
# ---------------------------------------------------------------------------


def _cossack(client, today, plan_id=PLAN_ID, session_id=SESSION_ID, block_id=None):
    body = options(client, plan_id, today, session_id, block_id or squat_id(today)).json()
    return next(a for a in body["alternatives"] if a["name"] == "Cossack Squat")


def test_swap_is_idempotent_and_visible_identically_in_plan_detail_and_today():
    client, store, _ = _build_client()
    today = seed_dated(store)
    pick = _cossack(client, today)
    body = {"action": "swap", "date": today.isoformat(), "session_id": SESSION_ID,
            "block_id": squat_id(today), "catalogue_id": pick["catalogue_id"]}
    first, payload = change(client, PLAN_ID, **body)
    assert first.status_code == 200, first.text
    retry = client.post(f"/api/plans/{PLAN_ID}/exercise-changes", headers=AUTH, json=payload)
    assert retry.status_code == 200 and retry.json()["id"] == first.json()["id"]
    assert len(store.plans[PLAN_ID]["exercise_overrides"]) == 1
    assert store.plans[PLAN_ID]["exercise_overrides_revision"] == 1
    # The generated card is untouched.
    assert store.plans[PLAN_ID]["structured_plan"]["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["display_name"] == "Back Squat"
    session, blocks = day_blocks(store, PLAN_ID, today)
    detail = detail_day(client, PLAN_ID, today)["sessions"][0]
    assert [b["display_name"] for b in detail["blocks"]] == [b["display_name"] for b in blocks] == ["Cossack Squat", "Front Plank"]
    assert detail["blocks"][0]["block_id"] == blocks[0]["block_id"] == override_block_id(first.json()["id"])
    # Refresh: a fresh read still shows the change.
    assert detail_day(client, PLAN_ID, today)["sessions"][0]["blocks"][0]["display_name"] == "Cossack Squat"


def test_remove_and_undo():
    client, store, _ = _build_client()
    today = seed_dated(store, blocks=[back_squat(), plank(), plank(display_name="Side Plank", exercise_key="side-plank")])
    plank_id = f"blk-{today}-front-plank"
    response, _ = change(client, PLAN_ID, action="remove", date=today.isoformat(), session_id=SESSION_ID, block_id=plank_id)
    assert response.status_code == 200, response.text
    session, blocks = day_blocks(store, PLAN_ID, today)
    assert [b["display_name"] for b in blocks] == ["Back Squat", "Side Plank"]
    assert session["athlete_removed"][0]["display_name"] == "Front Plank"
    undo = client.post(f"/api/plans/{PLAN_ID}/exercise-changes/{response.json()['id']}/undo", headers=AUTH, json={})
    assert undo.status_code == 200, undo.text
    session, blocks = day_blocks(store, PLAN_ID, today)
    assert [b["display_name"] for b in blocks] == ["Back Squat", "Front Plank", "Side Plank"]
    assert "athlete_removed" not in session
    # Undo is idempotent and the entry is kept as history.
    again = client.post(f"/api/plans/{PLAN_ID}/exercise-changes/{response.json()['id']}/undo", headers=AUTH, json={})
    assert again.status_code == 200
    assert store.plans[PLAN_ID]["exercise_overrides"][0]["revoked_at"]


def test_removing_critical_work_asks_first_and_last_exercise_is_kept():
    client, store, _ = _build_client()
    today = seed_dated(store)
    response, _ = change(client, PLAN_ID, action="remove", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "confirm_remove"
    assert "only strength work" in response.json()["detail"]["message"]
    response, _ = change(client, PLAN_ID, action="remove", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today), confirmed=True)
    assert response.status_code == 200, response.text
    response, _ = change(client, PLAN_ID, action="remove", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=f"blk-{today}-front-plank", confirmed=True)
    assert response.status_code == 409
    assert "at least one" in response.json()["detail"]


def test_add_inserts_one_exercise_without_duplicates():
    client, store, _ = _build_client()
    today = seed_dated(store)
    additions = client.get(f"/api/plans/{PLAN_ID}/exercise-changes/additions", headers=AUTH,
                           params={"date": today.isoformat(), "session_id": SESSION_ID})
    assert additions.status_code == 200, additions.text
    suggestions = additions.json()["alternatives"]
    assert suggestions
    assert not {s["name"] for s in suggestions} & {"Back Squat", "Front Plank"}
    pick = suggestions[0]
    dose = None if not pick["dose_required"] else (
        {"mode": "reps", "sets": 3, "reps": 8} if pick["dose_mode"] == "reps" else {"mode": "duration", "duration_seconds": 30})
    response, payload = change(client, PLAN_ID, action="add", date=today.isoformat(), session_id=SESSION_ID,
                               catalogue_id=pick["catalogue_id"], dose=dose)
    assert response.status_code == 200, response.text
    client.post(f"/api/plans/{PLAN_ID}/exercise-changes", headers=AUTH, json=payload)  # retried
    _, blocks = day_blocks(store, PLAN_ID, today)
    assert [b["display_name"] for b in blocks] == ["Back Squat", "Front Plank", pick["name"]]
    assert len({b["block_id"] for b in blocks}) == 3
    # The same exercise is not suggested twice once added.
    again = client.get(f"/api/plans/{PLAN_ID}/exercise-changes/additions", headers=AUTH,
                       params={"date": today.isoformat(), "session_id": SESSION_ID, "all": True}).json()
    assert pick["name"] not in {s["name"] for s in again["alternatives"]}


def additions(client, today, **params):
    return client.get(f"/api/plans/{PLAN_ID}/exercise-changes/additions", headers=AUTH,
                      params={"date": today.isoformat(), "session_id": SESSION_ID, **params})


def test_add_can_use_anything_from_the_library():
    client, store, _ = _build_client()
    today = seed_dated(store)
    # A footwork drill and sled work: outside the strength suggestions and
    # outside the athlete's equipment, but an explicit library pick.
    found = additions(client, today, q="sled push").json()
    sled = next(a for a in found["alternatives"] if "sled" in a["name"].lower())
    assert "Sled" in " ".join(sled["equipment"] or []) or sled["equipment"] is None
    footwork = additions(client, today, q="pivot").json()["alternatives"]
    assert footwork
    for pick in (sled, footwork[0]):
        dose = None if not pick["dose_required"] else (
            {"mode": "reps", "sets": 3, "reps": 6} if pick["dose_mode"] == "reps"
            else {"mode": "duration", "duration_seconds": 60} if pick["dose_mode"] == "duration"
            else {"mode": "intervals", "rounds": 3, "work_seconds": 30, "rest_seconds": 60})
        response, _ = change(client, PLAN_ID, action="add", date=today.isoformat(), session_id=SESSION_ID,
                             catalogue_id=pick["catalogue_id"], dose=dose)
        assert response.status_code == 200, response.text
    _, blocks = day_blocks(store, PLAN_ID, today)
    assert [b["display_name"] for b in blocks][-2:] == [sled["name"], footwork[0]["name"]]
    # Whatever its type, the athlete's own addition stays removable.
    added = blocks[-1]
    response, _ = change(client, PLAN_ID, action="remove", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=added["block_id"], confirmed=True)
    assert response.status_code == 200, response.text
    # Already in the workout: not offered again.
    again = additions(client, today, q="sled push").json()["alternatives"]
    assert sled["catalogue_id"] not in {a["catalogue_id"] for a in again}


def test_library_add_still_respects_injury_restrictions():
    from api.services.training_library import cache

    client, store, _ = _build_client()
    today = seed_dated(store)
    store.create_injury_flag("athlete-1", {"body_area": "knee", "description": "knee pain on squats"})
    found = additions(client, today, q="front squat isometric").json()
    assert "front-squat-isometric-105-1rm-100" not in {a["exercise_key"] for a in found["alternatives"]}
    assert "injury guidance" in (found["notice"] or "")
    held = next(r for r in cache.get().records if r["entry"]["exercise_key"] == "front-squat-isometric-105-1rm-100")
    response, _ = change(client, PLAN_ID, action="add", date=today.isoformat(), session_id=SESSION_ID,
                         catalogue_id=held["entry"]["catalogue_id"], dose={"mode": "duration", "duration_seconds": 6})
    assert response.status_code == 409
    assert store.plans[PLAN_ID]["exercise_overrides"] == []


def test_rehab_and_clinical_blocks_stay_protected():
    client, store, _ = _build_client()
    today = seed_dated(store, blocks=[back_squat(), plank(), rehab_block()])
    response = options(client, PLAN_ID, today, SESSION_ID, "rehab-ankle")
    assert response.status_code == 409
    response, _ = change(client, PLAN_ID, action="remove", date=today.isoformat(), session_id=SESSION_ID,
                         block_id="rehab-ankle", confirmed=True)
    assert response.status_code == 409
    # A forged override entry cannot remove rehab on read either.
    store.plans[PLAN_ID]["exercise_overrides"] = [{
        "id": "forged", "action": "remove", "scope": "occurrence", "date": today.isoformat(),
        "session_id": SESSION_ID, "block_id": "rehab-ankle"}]
    _, blocks = day_blocks(store, PLAN_ID, today)
    assert "Ankle Alphabet" in [b["display_name"] for b in blocks]


def test_started_and_past_workouts_cannot_change():
    client, store, _ = _build_client()
    today = seed_dated(store)
    client.post("/api/today/checkin", headers=AUTH, json={
        "plan_id": PLAN_ID, "sleep": "good", "body": "normal", "pain": "none", "phase": "GPP"})
    pick = _cossack(client, today)
    start = client.post("/api/today/session-completion", headers=AUTH,
                        json={"plan_id": PLAN_ID, "session_id": SESSION_ID, "status": "started"})
    assert start.status_code == 201, start.text
    response, _ = change(client, PLAN_ID, action="swap", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today), catalogue_id=pick["catalogue_id"])
    assert response.status_code == 409
    response, _ = change(client, PLAN_ID, action="swap", date=(today - timedelta(days=1)).isoformat(),
                         session_id=SESSION_ID, block_id=squat_id(today), catalogue_id=pick["catalogue_id"])
    assert response.status_code == 409


def test_logging_uses_the_effective_exercise():
    client, store, _ = _build_client()
    today = seed_dated(store)
    client.post("/api/today/checkin", headers=AUTH, json={
        "plan_id": PLAN_ID, "sleep": "good", "body": "normal", "pain": "none", "phase": "GPP"})
    pick = _cossack(client, today)
    response, _ = change(client, PLAN_ID, action="swap", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=squat_id(today), catalogue_id=pick["catalogue_id"])
    new_id = override_block_id(response.json()["id"])
    start = client.post("/api/today/session-completion", headers=AUTH,
                        json={"plan_id": PLAN_ID, "session_id": SESSION_ID, "status": "started"})
    assert start.status_code == 201, start.text
    log = client.post("/api/today/exercise-log", headers=AUTH,
                      json={"plan_id": PLAN_ID, "block_id": new_id, "status": "as_prescribed"})
    assert log.status_code == 201, log.text
    assert log.json()["log"]["exercise_key"] == "cossack-squat"
    assert log.json()["log"]["prescribed"]["display_name"] == "Cossack Squat"
    stale = client.post("/api/today/exercise-log", headers=AUTH,
                        json={"plan_id": PLAN_ID, "block_id": squat_id(today), "status": "as_prescribed"})
    assert stale.status_code == 404
    done = client.post("/api/today/session-completion", headers=AUTH,
                       json={"plan_id": PLAN_ID, "session_id": SESSION_ID, "status": "done", "session_rpe": 7})
    assert done.status_code == 201, done.text
    # Once done, the occurrence is history: undo cannot rewrite it.
    undo = client.post(f"/api/plans/{PLAN_ID}/exercise-changes/{response.json()['id']}/undo", headers=AUTH, json={})
    assert undo.status_code == 409


def test_other_athletes_cannot_change_or_read_options():
    client, store, _ = _build_client()
    today = seed_dated(store)
    response = client.get(f"/api/plans/{PLAN_ID}/exercise-changes/alternatives", headers=OTHER,
                          params={"date": today.isoformat(), "session_id": SESSION_ID, "block_id": squat_id(today)})
    assert response.status_code == 404
    response = client.post(f"/api/plans/{PLAN_ID}/exercise-changes", headers=OTHER, json={
        "client_request_id": str(uuid4()), "action": "remove", "date": today.isoformat(),
        "session_id": SESSION_ID, "block_id": squat_id(today), "confirmed": True})
    assert response.status_code == 404
    assert store.plans[PLAN_ID]["exercise_overrides"] == []


def test_concurrent_write_is_detected_and_retried():
    client, store, _ = _build_client()
    today = seed_dated(store, blocks=[back_squat(), plank(), plank(display_name="Side Plank", exercise_key="side-plank")])
    original = store.compare_and_set_plan_exercise_overrides
    calls = {"n": 0}

    def racing(plan_id, athlete_id, *, expected_revision, overrides):
        calls["n"] += 1
        if calls["n"] == 1:
            # Another device wrote first.
            store.plans[plan_id]["exercise_overrides_revision"] += 1
            return None
        return original(plan_id, athlete_id, expected_revision=expected_revision, overrides=overrides)

    store.compare_and_set_plan_exercise_overrides = racing
    response, _ = change(client, PLAN_ID, action="remove", date=today.isoformat(), session_id=SESSION_ID,
                         block_id=f"blk-{today}-side-plank")
    assert response.status_code == 200, response.text
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Scopes on open plans
# ---------------------------------------------------------------------------


def _open_ids(store, day):
    session, blocks = day_blocks(store, OPEN_PLAN_ID, day)
    return session["session_id"], next(b["block_id"] for b in blocks if b["display_name"] == "Back Squat")


def test_current_only_change_does_not_affect_future_occurrences():
    client, store, _ = _build_client()
    today = seed_open(store)
    session_id, block_id = _open_ids(store, today)
    body = options(client, OPEN_PLAN_ID, today, session_id, block_id).json()
    assert [s["value"] for s in body["scopes"]] == ["occurrence", "future"]
    pick = next(a for a in body["alternatives"] if a["name"] == "Cossack Squat")
    response, _ = change(client, OPEN_PLAN_ID, action="swap", date=today.isoformat(), session_id=session_id,
                         block_id=block_id, catalogue_id=pick["catalogue_id"])
    assert response.status_code == 200, response.text
    assert day_blocks(store, OPEN_PLAN_ID, today)[1][0]["display_name"] == "Cossack Squat"
    next_week = today + timedelta(days=7)
    assert day_blocks(store, OPEN_PLAN_ID, next_week)[1][0]["display_name"] == "Back Squat"


def test_future_change_applies_forward_and_restore_keeps_history():
    client, store, _ = _build_client()
    today = seed_open(store)
    session_id, block_id = _open_ids(store, today)
    pick = next(a for a in options(client, OPEN_PLAN_ID, today, session_id, block_id).json()["alternatives"]
                if a["name"] == "Cossack Squat")
    response, _ = change(client, OPEN_PLAN_ID, action="swap", scope="future", date=today.isoformat(),
                         session_id=session_id, block_id=block_id, catalogue_id=pick["catalogue_id"])
    assert response.status_code == 200, response.text
    for weeks in (0, 1, 2, 5):
        day = today + timedelta(days=7 * weeks)
        assert day_blocks(store, OPEN_PLAN_ID, day)[1][0]["display_name"] == "Cossack Squat", weeks
    # The other training day is a different workout: untouched.
    other = today + timedelta(days=1)
    assert [b["display_name"] for b in day_blocks(store, OPEN_PLAN_ID, other)[1]] == ["Front Plank"]
    # Complete today's workout, then restore from next week: today keeps the change.
    client.post("/api/today/checkin", headers=AUTH, json={
        "plan_id": OPEN_PLAN_ID, "sleep": "good", "body": "normal", "pain": "none", "phase": "GPP"})
    done = client.post("/api/today/session-completion", headers=AUTH, json={
        "plan_id": OPEN_PLAN_ID, "session_id": session_id, "status": "done", "session_rpe": 6})
    assert done.status_code == 201, done.text
    undo = client.post(f"/api/plans/{OPEN_PLAN_ID}/exercise-changes/{response.json()['id']}/undo",
                       headers=AUTH, json={})
    assert undo.status_code == 200, undo.text
    entry = store.plans[OPEN_PLAN_ID]["exercise_overrides"][0]
    assert entry["ends_before"] == (today + timedelta(days=1)).isoformat() and not entry.get("revoked_at")
    assert day_blocks(store, OPEN_PLAN_ID, today)[1][0]["display_name"] == "Cossack Squat"
    assert day_blocks(store, OPEN_PLAN_ID, today + timedelta(days=7))[1][0]["display_name"] == "Back Squat"


def test_open_plan_detail_and_today_show_the_same_effective_workout():
    client, store, _ = _build_client()
    today = seed_open(store)
    session_id, block_id = _open_ids(store, today)
    pick = next(a for a in options(client, OPEN_PLAN_ID, today, session_id, block_id).json()["alternatives"]
                if a["name"] == "Cossack Squat")
    response, _ = change(client, OPEN_PLAN_ID, action="swap", scope="future", date=today.isoformat(),
                         session_id=session_id, block_id=block_id, catalogue_id=pick["catalogue_id"])
    assert response.status_code == 200, response.text
    for day in (today, today + timedelta(days=7)):
        detail = detail_day(client, OPEN_PLAN_ID, day)["sessions"][0]["blocks"]
        _, effective = day_blocks(store, OPEN_PLAN_ID, day)
        assert [b["display_name"] for b in detail] == [b["display_name"] for b in effective]
        assert [b["block_id"] for b in detail] == [b["block_id"] for b in effective]
        assert detail[0]["athlete_change"]["scope"] == "future"


def test_future_scope_is_refused_on_dated_camps():
    client, store, _ = _build_client()
    today = seed_dated(store)
    pick = _cossack(client, today)
    response, _ = change(client, PLAN_ID, action="swap", scope="future", date=today.isoformat(),
                         session_id=SESSION_ID, block_id=squat_id(today), catalogue_id=pick["catalogue_id"])
    assert response.status_code == 422


def test_custom_plans_are_not_customised_here():
    plan_row = {"planning_brief": {"custom_plan": {"id": "x"}}, "exercise_overrides": [{
        "id": "a", "action": "remove", "scope": "occurrence", "date": "2026-10-12", "session_id": "s", "block_id": "b"}]}
    card = {"weeks": [{"days": [{"date": "2026-10-12", "sessions": [
        {"session_id": "s", "blocks": [{"block_id": "b", "block_type": "strength", "display_name": "X"}]}]}]}]}
    assert apply_exercise_overrides(plan_row, card) is card


def test_generated_cards_cannot_claim_athlete_changes():
    from api.services.effective_structured_plan import resolve_effective_structured_plan

    today = date.fromisoformat(resolve_training_day(None))
    row = {"id": PLAN_ID, "structured_plan": {"weeks": [{"week_index": 1, "days": [{"date": today.isoformat(), "sessions": [
        {"session_id": "s", "session_type": "strength_power", "athlete_removed": [{"display_name": "Y"}],
         "blocks": [back_squat(athlete_change={"action": "swap"})]}]}]}]}}
    resolved = resolve_effective_structured_plan(row)
    session = resolved["weeks"][0]["days"][0]["sessions"][0]
    assert "athlete_removed" not in session and "athlete_change" not in session["blocks"][0]
