"""Server-authoritative age, Terms and health-data consent rules.

UK launch compliance treats three facts as *server* facts, never client claims:

* **Age band** is derived from a stored date of birth. The client never sends an
  ``is_minor`` flag — it sends a date, and this module decides. Under-13 is
  rejected outright (``docs/children-age-appropriate-use-policy.md``: "Under 13:
  not supported at initial public launch").
* **Terms acceptance** is recorded by version and by a server-stamped time, so
  "which Terms did this athlete agree to, and when" has one auditable answer.
* **Health-data consent** is recorded separately from Terms, because UK GDPR
  Article 9(2)(a) explicit consent must be "specific, affirmative, recorded,
  separate from general Terms, and withdrawable"
  (``docs/health-data-lawful-basis-dpia.md``). Bundling it into Terms would
  invalidate it.

``private_trial_ack_at`` is deliberately NOT reused for either: it records a
different thing (that a tester read the trial briefing) and carries no version,
so it cannot evidence consent to a specific document.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

# Version strings recorded alongside each acceptance. Bumping one means existing
# acceptances no longer satisfy the gate and the athlete is re-asked — that is
# the point of versioning, so only bump when the document materially changes.
#
# TERMS_VERSION tracks the "Version:" line of docs/terms-of-use.md.
TERMS_VERSION = "0.1-pre-launch"
# HEALTH_CONSENT_VERSION tracks the health-data consent wording shown alongside
# the Privacy Notice (docs/privacy-notice.md, "Lawful bases").
HEALTH_CONSENT_VERSION = "1.0"

# PRIVACY_NOTICE_VERSION tracks revisions to the Privacy Notice itself. It is
# deliberately NOT the same constant as HEALTH_CONSENT_VERSION: the notice can be
# corrected without changing what the athlete agreed to, and re-collecting
# Article 9(2)(a) consent for an editorial fix would take health-dependent
# features offline for every athlete until they answered again. Unlike the other
# two this version gates nothing — the notice is information, not agreement — so
# it is recorded for display and audit only.
PRIVACY_NOTICE_VERSION = "1.3"

# Age bands. 13 is the floor for an account at all; 18 is the line above which
# the adult flow applies. Both come from the Children & Age-Appropriate Use
# Policy and the Terms ("intended for users aged 13 or over").
MINIMUM_SIGNUP_AGE_YEARS = 13
ADULT_AGE_YEARS = 18

# Stable machine-readable codes. The web app switches on these to show the right
# recovery action, so they are part of the API contract — do not rename them
# without updating web/lib/compliance.ts.
CODE_DOB_REQUIRED = "date_of_birth_required"
CODE_DOB_INVALID = "date_of_birth_invalid"
CODE_UNDER_MINIMUM_AGE = "under_minimum_age"
CODE_TERMS_REQUIRED = "terms_acceptance_required"
CODE_HEALTH_CONSENT_REQUIRED = "health_data_consent_required"

UNDER_MINIMUM_AGE_MESSAGE = (
    f"UNLXCK accounts are for athletes aged {MINIMUM_SIGNUP_AGE_YEARS} or over."
)
TERMS_REQUIRED_MESSAGE = "Accept the Terms of Use to continue."
HEALTH_CONSENT_REQUIRED_MESSAGE = (
    "This feature uses health information, so it needs your separate health-data "
    "consent. You can give or withdraw it in Settings under Privacy."
)


def _today(reference: date | None = None) -> date:
    return reference or datetime.now(timezone.utc).date()


def parse_date_of_birth(value: Any) -> date | None:
    """A calendar date from ``YYYY-MM-DD`` text, a ``date``, or ``None``.

    Returns ``None`` for anything unusable rather than raising: callers decide
    whether a missing date is "not collected yet" (onboarding) or "rejected"
    (acceptance endpoint), and those need different responses.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Tolerate a full timestamp: Postgres date columns round-trip as plain
    # dates, but a JSON payload may carry an ISO datetime.
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def age_years(date_of_birth: Any, *, reference: date | None = None) -> int | None:
    """Completed years of age, or ``None`` when the date is unusable."""
    dob = parse_date_of_birth(date_of_birth)
    if dob is None:
        return None
    today = _today(reference)
    if dob > today:
        return None
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


def meets_minimum_age(date_of_birth: Any, *, reference: date | None = None) -> bool:
    """Whether a stored date of birth clears the 13+ floor."""
    years = age_years(date_of_birth, reference=reference)
    return years is not None and years >= MINIMUM_SIGNUP_AGE_YEARS


def is_minor(date_of_birth: Any, *, reference: date | None = None) -> bool:
    """Whether the athlete is under 18.

    An unknown date of birth is treated as a minor. Age assurance failing open
    would hand an unverified account the adult weight-cut surface, which is the
    exact outcome the child policy exists to prevent — so unknown fails safe.
    """
    years = age_years(date_of_birth, reference=reference)
    if years is None:
        return True
    return years < ADULT_AGE_YEARS


def age_band(date_of_birth: Any, *, reference: date | None = None) -> str:
    """Coarse band used for age-appropriate copy: ``unknown``/``13-15``/``16-17``/``adult``."""
    years = age_years(date_of_birth, reference=reference)
    if years is None:
        return "unknown"
    if years < MINIMUM_SIGNUP_AGE_YEARS:
        return "under_13"
    if years < 16:
        return "13-15"
    if years < ADULT_AGE_YEARS:
        return "16-17"
    return "adult"


def terms_accepted(
    *,
    terms_version: Any,
    terms_accepted_at: Any,
    required_version: str = TERMS_VERSION,
) -> bool:
    """Whether the stored acceptance covers the version currently in force."""
    return bool(str(terms_accepted_at or "").strip()) and str(
        terms_version or ""
    ).strip() == required_version


def health_consent_active(
    *,
    health_consent_at: Any,
    health_consent_withdrawn_at: Any,
    health_data_consent: Any = None,
    health_consent_version: Any = None,
    required_version: str = HEALTH_CONSENT_VERSION,
) -> bool:
    """Whether health-data processing is currently covered by explicit consent.

    Withdrawal wins over a grant whenever it is at least as recent, so a stale
    grant timestamp can never resurrect a withdrawn consent. A grant recorded
    against a superseded consent version does not count either — re-consent is
    required when the wording changes.
    """
    # New profile rows carry the direct boolean choice. ``None`` remains
    # compatible with records read before that column was deployed; their
    # timestamp evidence still gives the same verdict during rollout.
    if health_data_consent is not None and health_data_consent is not True:
        return False
    granted_at = _parse_timestamp(health_consent_at)
    if granted_at is None:
        return False
    if str(health_consent_version or "").strip() != required_version:
        return False
    withdrawn_at = _parse_timestamp(health_consent_withdrawn_at)
    if withdrawn_at is None:
        return True
    return granted_at > withdrawn_at


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class ComplianceStatus:
    """The server's verdict on one athlete's consent state."""

    date_of_birth: str | None
    age_band: str
    is_minor: bool
    meets_minimum_age: bool
    terms_accepted: bool
    health_consent_granted: bool

    @property
    def onboarding_complete(self) -> bool:
        """Whether signup/onboarding may be completed.

        Terms plus a usable date of birth. Health-data consent is deliberately
        excluded: it must stay a separate, refusable choice, so refusing it
        cannot lock the athlete out of the account entirely.
        """
        return self.meets_minimum_age and self.terms_accepted


def evaluate_profile_compliance(profile: Any, *, reference: date | None = None) -> ComplianceStatus:
    """Derive the compliance verdict from a profile record or row.

    Accepts either a ``ProfileRecord`` or the raw dict a store read returns, so
    the same rules apply on both sides of the mapping layer.
    """

    def _read(name: str) -> Any:
        if isinstance(profile, dict):
            return profile.get(name)
        return getattr(profile, name, None)

    dob_raw = _read("date_of_birth")
    dob = parse_date_of_birth(dob_raw)
    return ComplianceStatus(
        date_of_birth=dob.isoformat() if dob else None,
        age_band=age_band(dob, reference=reference),
        is_minor=is_minor(dob, reference=reference),
        meets_minimum_age=meets_minimum_age(dob, reference=reference),
        terms_accepted=terms_accepted(
            terms_version=_read("terms_version"),
            terms_accepted_at=_read("terms_accepted_at"),
        ),
        health_consent_granted=health_consent_active(
            health_data_consent=_read("health_data_consent"),
            health_consent_at=_read("health_consent_at"),
            health_consent_withdrawn_at=_read("health_consent_withdrawn_at"),
            health_consent_version=_read("health_consent_version"),
        ),
    )
