"""Age gating, Terms acceptance and health-data consent.

Covers the launch requirements in docs/children-age-appropriate-use-policy.md
and docs/health-data-lawful-basis-dpia.md: under-13 is refused, 13-17 is a
minor, neither Terms nor health-data consent can be bypassed, withdrawal is
respected, and the ordinary adult flow is unaffected.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from api.compliance import (
    ADULT_AGE_YEARS,
    CODE_HEALTH_CONSENT_REQUIRED,
    CODE_TERMS_REQUIRED,
    CODE_UNDER_MINIMUM_AGE,
    HEALTH_CONSENT_VERSION,
    HEALTH_CONSENT_REQUIRED_MESSAGE,
    MINIMUM_SIGNUP_AGE_YEARS,
    TERMS_VERSION,
    age_band,
    age_years,
    evaluate_profile_compliance,
    health_consent_active,
    is_minor,
    meets_minimum_age,
    terms_accepted,
)
from api.store import _signup_date_of_birth
from api.auth import AuthenticatedUser
from tests.support import (
    DEFAULT_ATHLETE_USER,
    _build_client,
    _build_request,
    clear_compliance,
    grant_default_compliance,
    withdraw_health_consent,
)

ATHLETE = {"Authorization": "Bearer athlete-token"}
TODAY = date(2026, 8, 17)


def _dob_for_age(years: int, *, reference: date = TODAY) -> str:
    """A date of birth that makes someone exactly ``years`` old on ``reference``."""
    return reference.replace(year=reference.year - years).isoformat()


# ---------------------------------------------------------------------------
# Age derivation
# ---------------------------------------------------------------------------


def test_age_is_counted_in_completed_years_not_calendar_years():
    # The day before a 13th birthday is still 12: an off-by-one here would let a
    # 12-year-old through on the strength of the year number alone.
    assert age_years("2013-08-18", reference=TODAY) == 12
    assert age_years("2013-08-17", reference=TODAY) == 13


@pytest.mark.parametrize("years", [0, 5, 12])
def test_under_13_does_not_meet_the_minimum_age(years):
    assert meets_minimum_age(_dob_for_age(years), reference=TODAY) is False


@pytest.mark.parametrize("years", [MINIMUM_SIGNUP_AGE_YEARS, 15, 17, ADULT_AGE_YEARS, 40])
def test_13_and_over_meets_the_minimum_age(years):
    assert meets_minimum_age(_dob_for_age(years), reference=TODAY) is True


@pytest.mark.parametrize("years", [13, 14, 15, 16, 17])
def test_13_to_17_is_classified_as_a_minor(years):
    assert is_minor(_dob_for_age(years), reference=TODAY) is True


@pytest.mark.parametrize("years", [18, 19, 35])
def test_18_and_over_is_not_a_minor(years):
    assert is_minor(_dob_for_age(years), reference=TODAY) is False


def test_unknown_date_of_birth_fails_safe_to_minor():
    # An unverified account must not get the adult weight-cut surface.
    assert is_minor(None) is True
    assert is_minor("") is True
    assert is_minor("not-a-date") is True
    assert meets_minimum_age(None) is False


def test_age_bands_match_the_children_policy():
    assert age_band(_dob_for_age(14), reference=TODAY) == "13-15"
    assert age_band(_dob_for_age(17), reference=TODAY) == "16-17"
    assert age_band(_dob_for_age(21), reference=TODAY) == "adult"
    assert age_band(None) == "unknown"


def test_a_future_date_of_birth_is_not_usable():
    future = (TODAY + timedelta(days=1)).isoformat()
    assert age_years(future, reference=TODAY) is None
    assert meets_minimum_age(future, reference=TODAY) is False


# ---------------------------------------------------------------------------
# Consent evaluation
# ---------------------------------------------------------------------------


def test_terms_acceptance_requires_the_current_version():
    now = datetime.now(timezone.utc).isoformat()
    assert terms_accepted(terms_version=TERMS_VERSION, terms_accepted_at=now) is True
    # A superseded acceptance no longer satisfies the gate — that is the point
    # of recording the version.
    assert terms_accepted(terms_version="0.0-old", terms_accepted_at=now) is False
    assert terms_accepted(terms_version=TERMS_VERSION, terms_accepted_at=None) is False


def test_withdrawal_wins_over_an_older_grant():
    granted = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    withdrawn = datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat()
    assert (
        health_consent_active(
            health_consent_at=granted,
            health_consent_withdrawn_at=withdrawn,
            health_consent_version=HEALTH_CONSENT_VERSION,
        )
        is False
    )


def test_a_later_grant_supersedes_an_earlier_withdrawal():
    withdrawn = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    granted = datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat()
    assert (
        health_consent_active(
            health_consent_at=granted,
            health_consent_withdrawn_at=withdrawn,
            health_consent_version=HEALTH_CONSENT_VERSION,
        )
        is True
    )


def test_consent_against_a_superseded_version_does_not_count():
    granted = datetime.now(timezone.utc).isoformat()
    assert (
        health_consent_active(
            health_consent_at=granted,
            health_consent_withdrawn_at=None,
            health_consent_version="0.9",
        )
        is False
    )


def test_private_trial_acknowledgement_is_not_treated_as_consent():
    # The requirement is explicit: private_trial_ack_at must not stand in for
    # either document. A profile with only that marker is not consented.
    state = evaluate_profile_compliance(
        {"private_trial_ack_at": datetime.now(timezone.utc).isoformat()}
    )
    assert state.terms_accepted is False
    assert state.health_consent_granted is False
    assert state.onboarding_complete is False


# ---------------------------------------------------------------------------
# Signup: under-13 rejection and server-stamped evidence
# ---------------------------------------------------------------------------


def test_under_13_signup_metadata_never_seeds_a_profile_date_of_birth():
    child = AuthenticatedUser(
        user_id="child-1",
        email="kid@example.com",
        full_name="Young Athlete",
        metadata={"date_of_birth": _dob_for_age(11, reference=date.today())},
    )
    assert _signup_date_of_birth(child) is None


def test_adult_signup_metadata_seeds_the_profile_date_of_birth():
    adult = AuthenticatedUser(
        user_id="adult-1",
        email="adult@example.com",
        full_name="Adult Athlete",
        metadata={"date_of_birth": "1996-05-04"},
    )
    assert _signup_date_of_birth(adult) == "1996-05-04"


def test_under_13_acceptance_is_rejected_by_the_api():
    client, store, _ = _build_client()
    clear_compliance(store)

    response = client.post(
        "/api/me/compliance",
        headers=ATHLETE,
        json={
            "date_of_birth": _dob_for_age(12, reference=date.today()),
            "accept_terms": True,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == CODE_UNDER_MINIMUM_AGE
    # Nothing was written: a rejected signup leaves no age on the profile.
    assert store.profiles[DEFAULT_ATHLETE_USER.user_id]["date_of_birth"] is None


def test_thirteen_to_seventeen_signup_is_accepted_and_marked_minor():
    client, store, _ = _build_client()
    clear_compliance(store)

    response = client.post(
        "/api/me/compliance",
        headers=ATHLETE,
        json={
            "date_of_birth": _dob_for_age(15, reference=date.today()),
            "accept_terms": True,
            "health_data_consent": True,
        },
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["is_minor"] is True
    assert profile["meets_minimum_age"] is True
    assert profile["age_band"] == "13-15"


def test_consent_timestamps_and_versions_come_from_the_server():
    client, store, _ = _build_client()
    clear_compliance(store)

    response = client.post(
        "/api/me/compliance",
        headers=ATHLETE,
        json={
            "date_of_birth": "1996-05-04",
            "accept_terms": True,
            "health_data_consent": True,
            # Client-supplied evidence must be ignored outright — these keys are
            # not part of the request model at all.
            "terms_accepted_at": "1999-01-01T00:00:00+00:00",
            "health_consent_version": "999",
        },
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["terms_version"] == TERMS_VERSION
    assert profile["health_consent_version"] == HEALTH_CONSENT_VERSION
    assert datetime.fromisoformat(profile["terms_accepted_at"]).year >= 2026
    assert datetime.fromisoformat(profile["health_consent_at"]).year >= 2026
    stored = store.profiles[DEFAULT_ATHLETE_USER.user_id]
    assert stored["terms_accepted_at"] == profile["terms_accepted_at"]
    assert stored["health_data_consent"] is True


def test_terms_acceptance_does_not_grant_health_consent():
    # Article 9 consent has to be separately affirmative: accepting the Terms
    # alone must leave health processing unconsented.
    client, store, _ = _build_client()
    clear_compliance(store)

    response = client.post(
        "/api/me/compliance",
        headers=ATHLETE,
        json={"date_of_birth": "1996-05-04", "accept_terms": True},
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["terms_accepted"] is True
    assert profile["health_consent_granted"] is False


def test_compliance_state_survives_a_profile_update():
    client, store, _ = _build_client()

    client.put("/api/me", headers=ATHLETE, json={"full_name": "Renamed Athlete"})
    profile = client.get("/api/me", headers=ATHLETE).json()["profile"]

    assert profile["terms_accepted"] is True
    assert profile["health_consent_granted"] is True


def test_declining_health_consent_still_leaves_a_usable_account():
    """Health consent must not be a precondition of having an account.

    Consent that is a condition of the service is not freely given (UK GDPR
    Art. 7(4)), which would invalidate the Article 9(2)(a) basis it exists to
    establish. So an athlete can supply their age, accept the Terms, decline
    health processing, and still hold an account and finish onboarding.
    """
    client, store, _ = _build_client()
    clear_compliance(store)

    response = client.post(
        "/api/me/compliance",
        headers=ATHLETE,
        json={"date_of_birth": "1996-05-04", "accept_terms": True},
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["terms_accepted"] is True
    assert profile["health_consent_granted"] is False
    # Never consented is not the same as withdrew — the audit trail keeps them
    # apart, so declining at signup must not write a withdrawal timestamp.
    assert profile["health_consent_at"] is None
    assert profile["health_consent_withdrawn_at"] is None

    # The account works: onboarding proceeds, only the health-dependent
    # features are unavailable.
    assert (
        client.patch(
            "/api/onboarding/draft",
            headers=ATHLETE,
            json={"onboarding_draft": {"current_step": 1}},
        ).status_code
        == 200
    )
    assert client.get("/api/me", headers=ATHLETE).status_code == 200


def test_onboarding_completeness_does_not_depend_on_health_consent():
    state = evaluate_profile_compliance(
        {
            "date_of_birth": "1996-05-04",
            "terms_version": TERMS_VERSION,
            "terms_accepted_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    assert state.health_consent_granted is False
    assert state.onboarding_complete is True


# ---------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------


def test_onboarding_draft_is_blocked_until_the_terms_are_accepted():
    client, store, _ = _build_client()
    clear_compliance(store)

    response = client.patch(
        "/api/onboarding/draft",
        headers=ATHLETE,
        json={"onboarding_draft": {"current_step": 1}},
    )

    assert response.status_code == 403
    # Missing date of birth is reported before the Terms: the athlete is asked
    # for one thing at a time, in the order the gate applies them.
    assert response.json()["detail"]["code"] == "date_of_birth_required"


def test_onboarding_draft_reports_terms_when_only_the_terms_are_missing():
    client, store, _ = _build_client()
    clear_compliance(store)
    store.record_compliance_acceptance(
        DEFAULT_ATHLETE_USER.user_id, date_of_birth="1996-05-04"
    )

    response = client.patch(
        "/api/onboarding/draft",
        headers=ATHLETE,
        json={"onboarding_draft": {"current_step": 1}},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == CODE_TERMS_REQUIRED


def test_onboarding_draft_succeeds_once_the_terms_are_accepted():
    client, _store, _ = _build_client()

    response = client.patch(
        "/api/onboarding/draft",
        headers=ATHLETE,
        json={"onboarding_draft": {"current_step": 1}},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.parametrize("plan_source", ["self_serve", "quick_build"])
def test_plan_generation_without_health_consent_allows_non_health_payload(plan_source):
    client, store, _ = _build_client()
    clear_compliance(store)
    store.record_compliance_acceptance(
        DEFAULT_ATHLETE_USER.user_id,
        date_of_birth="1996-05-04",
        accept_terms=True,
    )

    request_payload = _build_request().model_dump(mode="json")
    request_payload["fatigue_level"] = ""
    request_payload["injuries"] = ""
    request_payload["guided_injury"] = None
    request_payload["guided_injuries"] = None
    request_payload["athlete"]["weight_kg"] = None
    request_payload["athlete"]["target_weight_kg"] = None
    response = client.post(
        "/api/plans/generate",
        headers={**ATHLETE, "X-Plan-Source": plan_source},
        json=request_payload,
    )

    assert response.status_code == 202
    job = store.get_generation_job(response.json()["job_id"])
    assert job is not None
    assert job["source"] == plan_source
    assert job["request_payload"]["_generation_health_mode"] == "withheld"
    assert "fatigue_level" not in job["request_payload"]
    assert "injuries" not in job["request_payload"]
    assert "weight_kg" not in job["request_payload"]["athlete"]
    assert "target_weight_kg" not in job["request_payload"]["athlete"]


@pytest.mark.parametrize(
    "override",
    [
        {"injuries": "sore knee"},
        {"fatigue_level": "high"},
        {"guided_injury": {"area": "left knee", "severity": "moderate"}},
        {"guided_injuries": [{"area": "left knee", "severity": "moderate"}]},
        {"athlete": {"weight_kg": 72}},
        {"athlete": {"target_weight_kg": 68}},
    ],
)
def test_plan_generation_without_health_consent_rejects_health_payload(override):
    client, store, _ = _build_client()
    withdraw_health_consent(store)
    payload = _build_request(
        {
            "fatigue_level": "",
            "injuries": "",
            "guided_injury": None,
            "guided_injuries": None,
            "athlete": {"weight_kg": None, "target_weight_kg": None},
        }
    ).model_dump(mode="json")
    athlete_override = override.get("athlete")
    payload.update({key: value for key, value in override.items() if key != "athlete"})
    if athlete_override:
        payload["athlete"].update(athlete_override)

    response = client.post("/api/plans/generate", headers=ATHLETE, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == CODE_HEALTH_CONSENT_REQUIRED


@pytest.mark.parametrize(
    "override",
    [
        {"injuries": "sore knee"},
        {"fatigue_level": "high"},
        {"guided_injury": {"area": "left knee", "severity": "moderate"}},
        {"athlete": {"weight_kg": 72}},
        {"athlete": {"target_weight_kg": 68}},
    ],
)
def test_plan_generation_with_active_health_consent_keeps_health_payload(override):
    client, store, _ = _build_client()
    payload = _build_request(
        {
            "fatigue_level": "",
            "injuries": "",
            "guided_injury": None,
            "guided_injuries": None,
            "athlete": {"weight_kg": None, "target_weight_kg": None},
        }
    ).model_dump(mode="json")
    athlete_override = override.get("athlete")
    payload.update({key: value for key, value in override.items() if key != "athlete"})
    if athlete_override:
        payload["athlete"].update(athlete_override)

    response = client.post("/api/plans/generate", headers=ATHLETE, json=payload)

    assert response.status_code == 202
    job = store.get_generation_job(response.json()["job_id"])
    assert job is not None
    for key, value in override.items():
        if key == "athlete":
            for athlete_key, athlete_value in value.items():
                assert job["request_payload"]["athlete"][athlete_key] == athlete_value
        elif isinstance(value, dict):
            for nested_key, nested_value in value.items():
                assert job["request_payload"][key][nested_key] == nested_value
        else:
            assert job["request_payload"][key] == value


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/today/checkin",
            {
                "plan_id": "plan-1",
                "sleep": "good",
                "body": "normal",
                "pain": "none",
                "phase": "GPP",
            },
        ),
        (
            "post",
            "/api/injury-flags",
            {"body_area": "left shoulder", "description": "aching", "severity": "moderate"},
        ),
    ],
)
def test_health_data_writes_require_consent(method, path, payload):
    client, store, _ = _build_client()
    withdraw_health_consent(store)

    response = getattr(client, method)(path, headers=ATHLETE, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == CODE_HEALTH_CONSENT_REQUIRED
    assert response.json()["detail"]["message"] == HEALTH_CONSENT_REQUIRED_MESSAGE


def test_onboarding_without_health_consent_keeps_only_non_health_fields():
    client, store, _ = _build_client()
    withdraw_health_consent(store)

    response = client.patch(
        "/api/onboarding/draft",
        headers=ATHLETE,
        json={"onboarding_draft": {
            "current_step": 3,
            "fight_date": "2026-10-01",
            "fatigue_level": "high",
            "injuries": "sore knee",
            "guided_injuries": [{"area": "knee"}],
            "athlete": {"full_name": "Ari", "weight_kg": 72, "target_weight_kg": 68},
        }},
    )

    assert response.status_code == 200
    draft = store.profiles["athlete-1"]["onboarding_draft"]
    assert draft["current_step"] == 3
    assert draft["fight_date"] == "2026-10-01"
    assert draft["athlete"] == {"full_name": "Ari"}
    assert not ({"fatigue_level", "injuries", "guided_injuries"} & draft.keys())


def test_withdrawal_stops_new_health_processing():
    client, store, _ = _build_client()

    withdrawal = client.post(
        "/api/me/compliance", headers=ATHLETE, json={"health_data_consent": False}
    )
    assert withdrawal.status_code == 200
    profile = withdrawal.json()["profile"]
    assert profile["health_consent_granted"] is False
    # The grant itself is preserved rather than erased: "consented on X,
    # withdrew on Y" is the record the retention policy needs.
    assert profile["health_consent_at"]
    assert profile["health_consent_withdrawn_at"]

    blocked = client.post(
        "/api/plans/generate",
        headers=ATHLETE,
        json=_build_request().model_dump(mode="json"),
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == CODE_HEALTH_CONSENT_REQUIRED


def test_withdrawal_degrades_safely_and_leaves_reads_working():
    client, store, _ = _build_client()
    withdraw_health_consent(store)

    # Reading back data already collected lawfully still works: withdrawal must
    # not lock an athlete out of their own record.
    assert client.get("/api/me", headers=ATHLETE).status_code == 200
    assert client.get("/api/nutrition/current", headers=ATHLETE).status_code == 200
    # Writing new health data does not.
    write = client.put(
        "/api/nutrition/current",
        headers=ATHLETE,
        json={"nutrition_profile": {"age": 27}},
    )
    assert write.status_code == 403
    assert write.json()["detail"]["code"] == CODE_HEALTH_CONSENT_REQUIRED


def test_re_consenting_restores_health_features():
    client, store, _ = _build_client()
    withdraw_health_consent(store)

    restored = client.post(
        "/api/me/compliance", headers=ATHLETE, json={"health_data_consent": True}
    )

    assert restored.status_code == 200
    assert restored.json()["profile"]["health_consent_granted"] is True
    assert (
        client.post(
            "/api/plans/generate",
            headers=ATHLETE,
            json=_build_request().model_dump(mode="json"),
        ).status_code
        == 202
    )


# ---------------------------------------------------------------------------
# The existing adult flow
# ---------------------------------------------------------------------------


def test_consented_adult_flow_is_unchanged():
    client, store, _ = _build_client()
    grant_default_compliance(store)

    profile = client.get("/api/me", headers=ATHLETE).json()["profile"]
    assert profile["is_minor"] is False
    assert profile["age_band"] == "adult"
    assert profile["terms_accepted"] is True
    assert profile["health_consent_granted"] is True

    assert (
        client.patch(
            "/api/onboarding/draft",
            headers=ATHLETE,
            json={"onboarding_draft": {"current_step": 2}},
        ).status_code
        == 200
    )
    generated = client.post(
        "/api/plans/generate",
        headers=ATHLETE,
        json=_build_request().model_dump(mode="json"),
    )
    assert generated.status_code == 202


def test_private_trial_acknowledgement_behaviour_is_preserved():
    client, store, _ = _build_client()

    response = client.put(
        "/api/me", headers=ATHLETE, json={"private_trial_acknowledged": True}
    )

    assert response.status_code == 200
    stamped = response.json()["profile"]["private_trial_ack_at"]
    assert stamped and datetime.fromisoformat(stamped)
    # Still a distinct field from the consent evidence.
    assert stamped != response.json()["profile"]["terms_accepted_at"]
