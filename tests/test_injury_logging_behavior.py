import logging

from fightcamp import injury_filtering


def _run_match() -> None:
    injury_filtering._INJURY_MATCH_DETAILS_CACHE.clear()
    item = {"name": "DB Split Squat", "tags": []}
    injury_filtering.injury_match_details(item, ["knee pain"])


def test_exclusion_log_suppressed_when_injury_debug_off(monkeypatch, caplog):
    monkeypatch.setenv("INJURY_DEBUG", "0")

    with caplog.at_level(logging.INFO, logger=injury_filtering.logger.name):
        _run_match()

    assert "[injury-exclusion]" not in caplog.text


def test_exclusion_log_emitted_when_injury_debug_on(monkeypatch, caplog):
    monkeypatch.setenv("INJURY_DEBUG", "1")

    with caplog.at_level(logging.INFO, logger=injury_filtering.logger.name):
        _run_match()

    assert "[injury-exclusion]" in caplog.text
