"""A new profile is never seeded with the athlete's email as their name.

Signup no longer asks for a full name (intake does). ``AuthenticatedUser``
falls back to the email address for display when the auth metadata carries no
name, and seeding the profile with that fallback would prefill the intake's
name field with the athlete's email.
"""

from __future__ import annotations

from api.auth import AuthenticatedUser
from api.store import SupabaseAppStore, _signup_full_name


def _user(full_name: str, email: str = "fighter@example.com", metadata: dict | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(user_id="athlete-new", email=email, full_name=full_name, metadata=metadata or {})


def test_email_fallback_seeds_an_empty_name():
    assert _signup_full_name(_user("fighter@example.com")) == ""
    assert _signup_full_name(_user("Fighter@Example.com ")) == ""
    assert _signup_full_name(_user("")) == ""


def test_a_declared_name_still_seeds_the_profile():
    assert _signup_full_name(_user("Ari Mensah", metadata={"full_name": "Ari Mensah"})) == "Ari Mensah"


def test_new_profile_payload_uses_the_seed_and_keeps_a_stored_name():
    store = SupabaseAppStore.__new__(SupabaseAppStore)
    store.is_admin_email = lambda email: False  # type: ignore[method-assign]

    fresh = store._build_profile_payload(user=_user("fighter@example.com"), existing=None)
    assert fresh["full_name"] == ""

    kept = store._build_profile_payload(user=_user("fighter@example.com"), existing={"full_name": "Ari Mensah"})
    assert kept["full_name"] == "Ari Mensah"
