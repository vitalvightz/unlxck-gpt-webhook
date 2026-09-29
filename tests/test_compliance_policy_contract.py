"""shared/compliance-policy.json is the one copy of the consent versions and age bands.

The web app (web/lib/compliance.ts) imports the same file, so these tests pin
the backend side: the constants come from the file, and a broken file stops the
process at import rather than letting a default version slip through.
"""

import json
from pathlib import Path

import pytest

from api import compliance

POLICY_PATH = Path(__file__).resolve().parents[1] / "shared" / "compliance-policy.json"


def test_backend_constants_are_the_shared_policy():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert compliance.TERMS_VERSION == policy["terms_version"]
    assert compliance.HEALTH_CONSENT_VERSION == policy["health_consent_version"]
    assert compliance.PRIVACY_NOTICE_VERSION == policy["privacy_notice_version"]
    assert compliance.MINIMUM_SIGNUP_AGE_YEARS == policy["minimum_signup_age_years"]
    assert compliance.ADULT_AGE_YEARS == policy["adult_age_years"]


def test_web_reads_the_same_policy_file():
    source = (Path(__file__).resolve().parents[1] / "web" / "lib" / "compliance.ts").read_text()

    assert 'from "../../shared/compliance-policy.json"' in source
    # No second literal copy of a version or age band in the web module.
    for literal in ('"0.1-pre-launch"', '"1.0"', '"1.5"', "= 13;", "= 18;"):
        assert literal not in source


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (None, "missing"),
        ("{not json", "not valid JSON"),
        ("[]", "must be a JSON object"),
        (
            '{"terms_version": "", "health_consent_version": "1", "privacy_notice_version": "1",'
            ' "minimum_signup_age_years": 13, "adult_age_years": 18}',
            "terms_version",
        ),
        (
            '{"terms_version": "t", "health_consent_version": "1", "privacy_notice_version": "1",'
            ' "minimum_signup_age_years": true, "adult_age_years": 18}',
            "minimum_signup_age_years",
        ),
        (
            '{"terms_version": "t", "health_consent_version": "1", "privacy_notice_version": "1",'
            ' "minimum_signup_age_years": 18, "adult_age_years": 13}',
            "below the adult age",
        ),
    ],
)
def test_a_broken_policy_file_fails_loudly(tmp_path, monkeypatch, contents, message):
    path = tmp_path / "compliance-policy.json"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(compliance, "_POLICY_PATH", path)

    with pytest.raises(RuntimeError, match=message):
        compliance._load_compliance_policy()
