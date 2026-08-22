import pytest

from fightcamp.athlete_model import _derive_competitive_maturity


@pytest.mark.parametrize(
    "status, record, expected",
    [
        ("professional", "0-0", "early_pro"),
        ("professional", "1-0", "early_pro"),
        ("pro", "2-0", "early_pro"),
        ("professional", "3-0", "developing_pro"),
        ("pro", "4-1", "developing_pro"),
        ("professional", "6-0", "developing_pro"),
        ("professional", "7-0", "established_pro"),
        ("pro", "9-2", "established_pro"),
        ("professional fighter", "9-2", "established_pro"),
        ("pro-fighter", "9-2", "established_pro"),
    ],
)
def test_competitive_maturity_buckets_professionals_by_total_bouts(status, record, expected):
    assert _derive_competitive_maturity(status, record)["competitive_maturity"] == expected


def test_professional_record_parsing_still_exposes_total_bouts():
    profile = _derive_competitive_maturity("professional", "9-2")

    assert profile["wins"] == 9
    assert profile["losses"] == 2
    assert profile["draws"] == 0
    assert profile["total_bouts"] == 11
    assert profile["competitive_maturity"] == "established_pro"


@pytest.mark.parametrize(
    "record, expected",
    [
        ("2-1", "novice_amateur"),
        ("7-1", "developing_amateur"),
        ("19-2", "experienced_amateur"),
    ],
)
def test_existing_amateur_maturity_buckets_are_unchanged(record, expected):
    assert _derive_competitive_maturity("amateur", record)["competitive_maturity"] == expected


def test_unknown_or_invalid_status_stays_unknown_even_with_valid_record():
    assert (
        _derive_competitive_maturity("white collar", "9-2")["competitive_maturity"]
        == "unknown_competitive_maturity"
    )


def test_invalid_professional_record_stays_unknown():
    profile = _derive_competitive_maturity("professional", "nine-and-two")

    assert profile["total_bouts"] is None
    assert profile["competitive_maturity"] == "unknown_competitive_maturity"
