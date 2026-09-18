"""Static source checks for the date-of-birth-derived age in the web app.

Camp Setup's age field and the Settings date-of-birth editor live inside large
client components that need an authenticated session, a router and several
providers to render, so the node test suite cannot mount them. What matters
about them is structural, though — that Camp Setup has no editable age input,
that the value it shows comes from the profile's date of birth, and that
Settings writes the date through the compliance endpoint and never straight to
Supabase — and that is exactly what a source check can hold in place.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INTAKE_FORM = "web/components/plan-intake-form.tsx"
SETTINGS_PAGE = "web/app/settings/page.tsx"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_camp_setup_has_no_editable_age_input():
    source = _read(INTAKE_FORM)
    # The specific shape of the field that used to exist, and the only way the
    # form could write an age of its own.
    assert 'id="age" type="number"' not in source
    assert 'updateAthlete("age"' not in source


def test_camp_setup_shows_the_profile_derived_age_and_links_to_settings():
    source = _read(INTAKE_FORM)
    assert "deriveAgeFromDateOfBirth(me?.profile.date_of_birth)" in source
    assert 'data-testid="camp-setup-age"' in source
    assert 'href="/settings#account"' in source
    assert "Edit in Settings" in source


def test_camp_setup_review_step_shows_the_derived_age():
    source = _read(INTAKE_FORM)
    review_age = source.index('{ label: "Age", value: formatValue(derivedAge) }')
    # The review line reads the derived value, not the form's copy of it, so the
    # two steps cannot disagree about the athlete's age.
    assert "hasValue(form.athlete.age)" not in source[review_age - 200 : review_age + 200]


def test_settings_initializes_the_date_of_birth_from_the_profile():
    source = _read(SETTINGS_PAGE)
    assert 'const savedDateOfBirth = (me?.profile.date_of_birth ?? "").slice(0, 10);' in source
    assert "setDateOfBirthDraft(savedDateOfBirth);" in source
    assert "deriveAgeFromDateOfBirth(savedDateOfBirth || null)" in source


def test_settings_saves_the_date_of_birth_through_the_compliance_endpoint():
    source = _read(SETTINGS_PAGE)
    assert "await recordCompliance(token, { date_of_birth: next })" in source
    # The browser has no write access to this column, and giving it one is a
    # non-goal of this design: the server must stay the only writer.
    assert "date_of_birth" not in _read("web/lib/supabase.ts")


def test_settings_replaces_the_cached_profile_after_a_successful_change():
    source = _read(SETTINGS_PAGE)
    save = source.index("await recordCompliance(token, { date_of_birth: next })")
    replace = source.index("replaceMe(updated);", save)
    # Everything age-dependent — Camp Setup's displayed age, the weight-cut
    # surface, the safety copy — reads the cached profile, so the response has
    # to replace it or the UI keeps showing the old age band.
    assert replace > save


def test_settings_requires_confirmation_before_changing_the_date_of_birth():
    source = _read(SETTINGS_PAGE)
    assert "if (next !== savedDateOfBirth && !isConfirmingDateOfBirth) {" in source
    assert "setIsConfirmingDateOfBirth(true);" in source


def test_settings_validates_the_date_before_sending_it():
    source = _read(SETTINGS_PAGE)
    assert "validateDateOfBirthChange(next)" in source
    validation = source.index("const validationError = validateDateOfBirthChange(next);")
    request = source.index("await recordCompliance(token, { date_of_birth: next })")
    assert validation < request
