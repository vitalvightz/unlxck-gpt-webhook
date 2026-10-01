from __future__ import annotations

import json

import httpx
import pytest

from tools import exercise_media as tool
from tools import exercise_media_review as review
from tools import exercise_media_search as discovery
from tests.test_exercise_media_review import URL_A, URL_B, URL_C, _answer, _read_csv, _reviewer, _row, _write_csv

_SEARCH_CLASS = discovery.YouTubeCandidateSearch


def _searcher(responses, calls=None):
    def handler(request):
        assert request.url.path == "/youtube/v3/search"
        assert request.headers["X-Goog-Api-Key"] == "youtube-test-key"
        assert "key" not in request.url.params
        assert request.url.params["type"] == "video"
        assert request.url.params["maxResults"] == "5"
        assert request.url.params["videoEmbeddable"] == "true"
        if calls is not None:
            calls.append(str(request.url.params["q"]))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200, json={"items": [{"id": {"videoId": video_id}} for video_id in response]})

    return _SEARCH_CLASS("youtube-test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_queries_use_exercise_metadata_without_private_cues():
    row = _row(example_name="Tempo Shadowboxing", sport="boxing", aliases="controlled-shadowboxing", plan_cue="private athlete injury", notes="private")
    queries = discovery.search_queries(row)
    assert len(queries) == 3
    assert all("boxing" in query for query in queries)
    assert "Tempo Shadowboxing" in queries[0]
    assert "controlled shadowboxing" in queries[-1]
    assert "private" not in " ".join(queries)


@pytest.mark.parametrize("first", [
    _answer(verdict="partial"), _answer(verdict="no_match"),
    _answer(confidence=0.89), _answer(orientation="vertical"),
])
def test_weak_video_discovers_better_match_and_stops_early(first):
    calls, searches = [], []
    searcher = _searcher([["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]], searches)
    outcome = review.review_row(
        _reviewer({URL_A: first, URL_B: _answer()}, calls), _row(),
        max_candidates=4, delay_s=0, sleep=lambda _: None, log=lambda _: None, search=searcher.search,
    )
    assert outcome.tried == [URL_A, URL_B]
    assert len(calls) == 2 and len(searches) == 1
    updated = review.apply_outcome(_row(), outcome, model="test")
    assert updated["suggested_url"] == URL_B
    assert updated["needs_manual_video"] == "false"
    assert updated["youtube_url"] == ""  # discovery never approves a video


def test_strong_supplied_match_never_searches():
    searches = []
    outcome = review.review_row(
        _reviewer({URL_A: _answer()}), _row(), max_candidates=4, delay_s=0,
        search=_searcher([], searches).search,
    )
    assert outcome.tried == [URL_A] and searches == []


def test_search_deduplicates_video_ids_across_queries_and_url_shapes():
    searches = []
    searcher = _searcher([
        ["AAAAAAAAAAA", "BBBBBBBBBBB", "bad-id"],
        ["BBBBBBBBBBB", "CCCCCCCCCCC"],
        ["CCCCCCCCCCC"],
    ], searches)
    assert list(searcher.search(_row(), {"https://youtu.be/AAAAAAAAAAA?t=30"})) == [URL_B, URL_C]
    assert len(searches) == discovery.MAX_SEARCH_QUERIES
    assert review.candidate_urls(_row(candidate_urls="https://youtu.be/AAAAAAAAAAA|" + URL_B), 4) == [URL_A, URL_B]


def test_search_tries_alternate_query_after_no_new_candidates():
    searches = []
    outcome = review.review_row(
        _reviewer({URL_A: _answer(verdict="partial"), URL_B: _answer()}), _row(),
        max_candidates=4, delay_s=0, sleep=lambda _: None,
        search=_searcher([["AAAAAAAAAAA"], ["BBBBBBBBBBB"]], searches).search,
    )
    assert outcome.best.url == URL_B and len(searches) == 2


def test_attempt_cap_flags_manual_and_prevents_more_search_requests():
    calls, searches = [], []
    outcome = review.review_row(
        _reviewer({url: _answer(verdict="partial") for url in (URL_A, URL_B, URL_C)}, calls), _row(),
        max_candidates=3, delay_s=0, sleep=lambda _: None,
        search=_searcher([["BBBBBBBBBBB", "CCCCCCCCCCC"]], searches).search,
    )
    assert len(calls) == 3 and len(searches) == 1
    assert review.apply_outcome(_row(), outcome, model="test")["needs_manual_video"] == "true"


@pytest.mark.parametrize("response", [
    httpx.Response(403, json={"error": "quota; secret-key"}),
    httpx.Response(200, text="invalid json"),
    httpx.Response(200, json={"items": "malformed"}),
    httpx.ReadTimeout("secret-key transport failure"),
])
def test_search_failures_keep_best_result_and_disable_repeated_requests(response):
    searches, logs = [], []
    searcher = _searcher([response], searches)
    outcome = review.review_row(
        _reviewer({URL_A: _answer(verdict="partial")}), _row(), max_candidates=4,
        delay_s=0, search=searcher.search, log=logs.append,
    )
    updated = review.apply_outcome(_row(), outcome, model="test")
    assert updated["ai_verdict"] == "partial" and updated["needs_manual_video"] == "true"
    assert "YouTube search" in updated["review_note"]
    assert "secret-key" not in " ".join(logs)
    with pytest.raises(discovery.CandidateSearchError):
        list(searcher.search(_row(), set()))
    assert len(searches) == 1


def test_blank_suggestion_can_start_from_search(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(src, [_row(suggested_url="")])
    review.run_review(str(src), str(src), reviewer=_reviewer({URL_B: _answer()}),
                      search=_searcher([["BBBBBBBBBBB"]]).search, delay_s=0, log=lambda _: None)
    row = _read_csv(src)[0]
    assert row["suggested_url"] == URL_B and row["needs_manual_video"] == "false"


def test_no_candidates_found_is_flagged_for_manual_selection(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(src, [_row(suggested_url="")])
    review.run_review(str(src), str(src), reviewer=_reviewer({}),
                      search=_searcher([[], [], []]).search, delay_s=0, log=lambda _: None)
    row = _read_csv(src)[0]
    assert row["needs_manual_video"] == "true" and row["ai_candidates_tried"] == "0"
    assert row["youtube_url"] == ""


def test_candidate_export_can_be_reviewed_without_manual_suggestion_column(tmp_path):
    src = tmp_path / "candidates.csv"
    _write_csv(src, [{column: "" for column in tool.CSV_COLUMNS} | {"exercise_key": "trap-bar-deadlift"}])
    counts = review.run_review(str(src), str(src), reviewer=_reviewer({URL_B: _answer()}),
                             search=_searcher([["BBBBBBBBBBB"]]).search, delay_s=0, log=lambda _: None)
    assert counts["reviewed"] == 1
    assert _read_csv(src)[0]["suggested_url"] == URL_B


def test_invalid_checkpoint_does_not_overwrite_csv(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(src, [_row(ai_review_progress="broken checkpoint")])
    before = src.read_bytes()
    with pytest.raises(review.ReviewInputError, match="ai_review_progress"):
        review.run_review(str(src), str(src), reviewer=_reviewer({}), log=lambda _: None)
    assert src.read_bytes() == before


@pytest.mark.parametrize("separate_out", [False, True])
def test_quota_interruption_resumes_mid_row_without_rewatching_or_resetting_cap(tmp_path, separate_out):
    src = tmp_path / "media.csv"
    out = tmp_path / "reviewed.csv" if separate_out else src
    original = _row(start_s="10", end_s="20", notes="keep curator input")
    _write_csv(src, [original])
    stopped = review.run_review(
        str(src), str(out), reviewer=_reviewer({URL_A: _answer(verdict="partial"), URL_B: httpx.Response(429, json={})}),
        search=_searcher([["BBBBBBBBBBB", "CCCCCCCCCCC"]]).search,
        max_candidates=2, delay_s=0, sleep=lambda _: None, log=lambda _: None,
    )
    assert stopped["quota_stopped"] == 1
    saved = _read_csv(out)[0]
    assert json.loads(saved["ai_review_progress"])["tried"] == [URL_A]
    assert all(saved[key] == value for key, value in original.items())
    calls = []
    resumed = review.run_review(
        str(src), str(out), reviewer=_reviewer({URL_B: _answer(verdict="partial", confidence=0.95)}, calls),
        search=_searcher([["BBBBBBBBBBB", "CCCCCCCCCCC"]]).search,
        max_candidates=2, delay_s=0, sleep=lambda _: None, log=lambda _: None,
    )
    assert resumed["reviewed"] == 1 and len(calls) == 1
    row = _read_csv(out)[0]
    assert row["ai_candidates_tried"] == "2" and row["needs_manual_video"] == "true"
    assert row["suggested_url"] == URL_B and row["ai_review_progress"] == ""
    assert (row["start_s"], row["end_s"], row["notes"]) == ("10", "20", "keep curator input")


def test_redo_weak_revisits_partial_but_skips_strong_and_resumes_output(tmp_path):
    src, out = tmp_path / "media.csv", tmp_path / "reviewed.csv"
    _write_csv(src, [
        _row(exercise_key="strong", suggested_url=URL_A, ai_verdict="match", ai_confidence="0.9", ai_orientation="landscape"),
        _row(exercise_key="weak", suggested_url=URL_B, ai_verdict="partial", ai_confidence="0.9", ai_orientation="landscape"),
    ])
    calls = []
    counts = review.run_review(str(src), str(out), reviewer=_reviewer({URL_B: _answer()}, calls),
                             redo_weak=True, delay_s=0, log=lambda _: None)
    assert counts == {"reviewed": 1, "skipped": 1, "errors": 0} and len(calls) == 1
    counts = review.run_review(str(src), str(out), reviewer=_reviewer({}), redo_weak=True, log=lambda _: None)
    assert counts == {"reviewed": 0, "skipped": 2, "errors": 0}


def test_cli_discovers_by_default_with_key_and_can_disable(tmp_path, monkeypatch):
    src = tmp_path / "media.csv"
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "youtube-test-key")
    monkeypatch.setattr(review, "build_reviewer", lambda model: _reviewer({URL_A: _answer(verdict="partial"), URL_B: _answer()}))
    created = []

    def build_searcher(key):
        assert key == "youtube-test-key"
        created.append(key)
        return _searcher([["BBBBBBBBBBB"]])

    monkeypatch.setattr(discovery, "YouTubeCandidateSearch", build_searcher)
    _write_csv(src, [_row()])
    assert tool.main(["review", str(src), "--delay", "0"]) == 0
    assert _read_csv(src)[0]["needs_manual_video"] == "false"
    _write_csv(src, [_row()])
    assert tool.main(["review", str(src), "--delay", "0", "--no-search"]) == 0
    assert _read_csv(src)[0]["needs_manual_video"] == "true"
    assert len(created) == 1


def test_more_than_five_candidates_is_rejected(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(src, [_row()])
    with pytest.raises(SystemExit) as raised:
        tool.main(["review", str(src), "--max-candidates", "6"])
    assert raised.value.code == 2
    with pytest.raises(review.ReviewInputError):
        review.run_review(str(src), str(src), reviewer=_reviewer({}), max_candidates=6)
