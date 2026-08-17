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
