"""Request-level enforcement of the consent rules in :mod:`api.compliance`.

Two gates, kept apart because they protect different things:

* :func:`require_onboarding_compliance` — an athlete cannot finish signup or
  onboarding without a usable date of birth and an accepted Terms version.
* :func:`require_health_data_consent` — a feature that processes health data
  cannot run without current, separate, explicit consent.

Both raise ``403`` with a stable ``code`` so the web app can offer the right
recovery action (give the date of birth / accept the Terms / re-consent) instead
of showing a generic error. That is the "degrade safely rather than failing
unpredictably" requirement: withdrawal turns health-dependent *writes* into one
recognisable, actionable refusal, while reads of already-lawful data keep
working.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from .compliance import (
    CODE_DOB_REQUIRED,
    CODE_HEALTH_CONSENT_REQUIRED,
    CODE_TERMS_REQUIRED,
    CODE_UNDER_MINIMUM_AGE,
    HEALTH_CONSENT_REQUIRED_MESSAGE,
    HEALTH_CONSENT_VERSION,
    TERMS_REQUIRED_MESSAGE,
    TERMS_VERSION,
    UNDER_MINIMUM_AGE_MESSAGE,
    evaluate_profile_compliance,
)

# Intake is a mixed endpoint. Keep ordinary camp setup usable after consent is
# withdrawn, but never persist these health/readiness inputs from a bypassed UI.
HEALTH_INTAKE_FIELDS = frozenset({
    "fatigue_level", "injuries", "guided_injury", "guided_injuries",
    "pain", "pain_level", "soreness", "recovery", "sleep", "sleep_quality",
    "medical", "medical_conditions", "medical_restrictions", "restrictions",
    "current_weight_kg", "target_weight_kg", "target_weight_range_kg",
    "bodyweight", "body_weight",
})
HEALTH_ATHLETE_FIELDS = frozenset({"weight_kg", "target_weight_kg"})


def strip_health_intake_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Return an intake draft with only non-health fields retained."""
    cleaned = {key: value for key, value in payload.items() if key not in HEALTH_INTAKE_FIELDS}
    athlete = cleaned.get("athlete")
    if isinstance(athlete, dict):
        cleaned["athlete"] = {
            key: value for key, value in athlete.items() if key not in HEALTH_ATHLETE_FIELDS
        }
    return cleaned


def _forbidden(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": code, "message": message, **extra},
    )


def require_onboarding_compliance(profile: Any) -> None:
    """Block signup/onboarding completion until age and Terms are on record.

    Applies to athletes only. Admins reach the app through their own workspace
    and never pass through athlete onboarding, so gating them would lock out the
    people who have to operate the service.
    """
    if getattr(profile, "role", None) != "athlete":
        return

    state = evaluate_profile_compliance(profile)
    if state.date_of_birth is None:
        raise _forbidden(
            CODE_DOB_REQUIRED,
            "Add your date of birth to continue.",
        )
    if not state.meets_minimum_age:
        raise _forbidden(CODE_UNDER_MINIMUM_AGE, UNDER_MINIMUM_AGE_MESSAGE)
    if not state.terms_accepted:
        raise _forbidden(
            CODE_TERMS_REQUIRED,
            TERMS_REQUIRED_MESSAGE,
            required_version=TERMS_VERSION,
        )


def require_health_data_consent(profile: Any) -> None:
    """Block a health-data feature unless explicit consent is currently active.

    Checked *after* the onboarding gate by every caller, so an athlete missing
    both hears about the Terms first rather than being asked to consent to
    health processing before they have agreed to use the service at all.
    """
    if getattr(profile, "role", None) != "athlete":
        return

    if not evaluate_profile_compliance(profile).health_consent_granted:
        raise _forbidden(
            CODE_HEALTH_CONSENT_REQUIRED,
            HEALTH_CONSENT_REQUIRED_MESSAGE,
            required_version=HEALTH_CONSENT_VERSION,
        )


def require_health_feature_access(profile: Any) -> None:
    """The full gate for a personalised, health-dependent feature."""
    require_onboarding_compliance(profile)
    require_health_data_consent(profile)
