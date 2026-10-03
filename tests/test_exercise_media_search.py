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




def _dataforseo_searcher(responses, calls=None):
    def handler(request):
        assert request.url.path == "/v3/serp/youtube/organic/live/advanced"
        assert request.method == "POST"
        assert request.headers["Authorization"].startswith("Basic ")
        payload = json.loads(request.content)
        assert isinstance(payload, list) and len(payload) == 1
        assert payload[0]["device"] == "desktop"
        assert payload[0]["location_code"] == 2840
        assert payload[0]["language_code"] == "en"
        if calls is not None:
            calls.append(payload[0]["keyword"])
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        items = []
        for item in response:
            if isinstance(item, dict):
                items.append(item)
            else:
                items.append({"type": "youtube_video", "video_id": item})
        return httpx.Response(
            200,
            json={
                "status_code": 20000,
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [{"items": items}],
                    }
                ],
            },
        )

    return discovery.DataForSEOCandidateSearch(
        "login",
        "password",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


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
    httpx.Response(200, text="invalid json"),
    httpx.Response(200, json={"items": "malformed"}),
    httpx.ReadTimeout("secret-key transport failure"),
])
def test_youtube_provider_failures_propagate_and_rewind_query(response):
    searches = []
    searcher = _searcher([response], searches)
    progress = discovery.SearchProgress()

    with pytest.raises(discovery.CandidateSearchError) as raised:
        list(searcher.search(_row(), set(), progress))

    assert "secret-key" not in str(raised.value)
    assert progress.queries_used == 0
    with pytest.raises(discovery.CandidateSearchError):
        list(searcher.search(_row(), set(), progress))
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


def _video_uri(call):
    # The shared reviewer stub records the full Gemini request payload.
    return next(part["uri"] for part in call["input"] if part["type"] == "video")


def test_redo_weak_retries_legacy_dataforseo_timeout_rows_in_same_pass(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(src, [
        _row(
            exercise_key="legacy-timeout",
            suggested_url="",
            ai_verdict="error",
            ai_shows="DataForSEO search: ReadTimeout",
            ai_redo_weak_pass="1",
        ),
        _row(
            exercise_key="completed-weak",
            suggested_url=URL_A,
            ai_verdict="partial",
            ai_confidence="0.9",
            ai_orientation="landscape",
            ai_start_s="42",
            ai_end_s="54",
            ai_redo_weak_pass="1",
        ),
    ])

    calls = []
    counts = review.run_review(
        str(src), str(src),
        reviewer=_reviewer({URL_B: _answer()}, calls),
        search=_searcher([["BBBBBBBBBBB"]]).search,
        redo_weak=True, max_candidates=1, delay_s=0, log=lambda _: None,
    )

    assert counts["reviewed"] == 1
    assert counts["skipped"] == 1
    assert [_video_uri(call) for call in calls] == [URL_B]
    rows = _read_csv(src)
    assert rows[0]["ai_verdict"] == "match"
    assert rows[0]["ai_redo_weak_pass"] == "1"


def test_redo_weak_resumes_forward_after_interruption(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(src, [
        _row(exercise_key="weak-a", suggested_url=URL_A, candidate_urls=URL_B,
             ai_verdict="partial", ai_confidence="0.9", ai_orientation="landscape",
             ai_start_s="42", ai_end_s="54"),
        _row(exercise_key="weak-b", suggested_url=URL_A, candidate_urls=URL_C,
             ai_verdict="partial", ai_confidence="0.9", ai_orientation="landscape",
             ai_start_s="42", ai_end_s="54"),
    ])

    first_calls = []
    counts = review.run_review(
        str(src), str(src),
        reviewer=_reviewer({URL_B: _answer(verdict="partial")}, first_calls),
        redo_weak=True, max_candidates=1, limit=1, delay_s=0, log=lambda _: None,
    )
    assert counts["reviewed"] == 1
    first = _read_csv(src)
    assert first[0]["ai_redo_weak_pass"] == "1"
    assert first[1].get("ai_redo_weak_pass", "") == ""

    second_calls = []
    counts = review.run_review(
        str(src), str(src),
        reviewer=_reviewer({URL_C: _answer(verdict="partial")}, second_calls),
        redo_weak=True, max_candidates=1, delay_s=0, log=lambda _: None,
    )
    assert counts["reviewed"] == 1
    assert counts["skipped"] == 1
    assert [_video_uri(call) for call in second_calls] == [URL_C]
    resumed = _read_csv(src)
    assert resumed[0]["ai_redo_weak_pass"] == "1"
    assert resumed[1]["ai_redo_weak_pass"] == "1"


def test_redo_weak_revisits_partial_but_skips_strong_and_resumes_output(tmp_path):
    src, out = tmp_path / "media.csv", tmp_path / "reviewed.csv"
    _write_csv(src, [
        _row(exercise_key="strong", suggested_url=URL_A, ai_verdict="match", ai_confidence="0.9", ai_orientation="landscape", ai_start_s="42", ai_end_s="54"),
        _row(exercise_key="weak", suggested_url=URL_B, ai_verdict="partial", ai_confidence="0.9", ai_orientation="landscape", ai_start_s="42", ai_end_s="54"),
    ])
    calls = []
    counts = review.run_review(str(src), str(out), reviewer=_reviewer({URL_C: _answer()}, calls),
                             search=_searcher([["BBBBBBBBBBB", "CCCCCCCCCCC"]]).search,
                             redo_weak=True, delay_s=0, log=lambda _: None)
    assert counts == {"reviewed": 1, "skipped": 1, "errors": 0} and len(calls) == 1
    counts = review.run_review(str(src), str(out), reviewer=_reviewer({}), redo_weak=True, log=lambda _: None)
    assert counts == {"reviewed": 0, "skipped": 2, "errors": 0}


@pytest.mark.parametrize(("start", "end"), [(None, None), ("00:00", "00:00"), ("00:10", "00:11"), ("00:10", "00:50")])
def test_no_usable_loop_keeps_searching_and_prefers_valid_match(start, end):
    outcome = review.review_row(
        _reviewer({URL_A: _answer(confidence=0.99, segment_start=start, segment_end=end), URL_B: _answer(confidence=0.90)}),
        _row(), max_candidates=4, delay_s=0, sleep=lambda _: None,
        search=_searcher([["BBBBBBBBBBB"]]).search,
    )
    assert outcome.tried == [URL_A, URL_B]
    assert outcome.best.url == URL_B
    assert review.apply_outcome(_row(), outcome, model="test")["needs_manual_video"] == "false"


def test_no_loop_match_is_flagged_manual_when_no_better_video_exists():
    outcome = review.review_row(_reviewer({URL_A: _answer(segment_start="00:00", segment_end="00:00")}),
                               _row(), max_candidates=1, delay_s=0)
    updated = review.apply_outcome(_row(), outcome, model="test")
    assert updated["ai_verdict"] == "match" and updated["needs_manual_video"] == "true"


@pytest.mark.parametrize("separate_out", [False, True])
def test_redo_weak_seeds_legacy_no_loop_history_and_watches_only_new_ids(tmp_path, separate_out):
    src = tmp_path / "media.csv"
    out = tmp_path / "reviewed.csv" if separate_out else src
    _write_csv(src, [_row(
        suggested_url=URL_A, candidate_urls="https://youtu.be/AAAAAAAAAAA?t=30",
        ai_verdict="match", ai_confidence="0.99", ai_orientation="landscape", ai_start_s="", ai_end_s="",
        start_s="10", end_s="20", notes="keep manual values",
    )])
    calls = []
    review.run_review(str(src), str(out), reviewer=_reviewer({URL_B: _answer(verdict="partial")}, calls),
                      search=_searcher([["AAAAAAAAAAA", "BBBBBBBBBBB"], [], []]).search,
                      max_candidates=1, redo_weak=True, delay_s=0, log=lambda _: None)
    saved = _read_csv(out)[0]
    assert len(calls) == 1 and saved["ai_reviewed_video_ids"] == "AAAAAAAAAAA|BBBBBBBBBBB"
    assert saved["needs_manual_video"] == "true"
    assert saved["suggested_url"] == URL_A  # the previous closer match is kept
    calls = []
    review.run_review(str(src), str(out), reviewer=_reviewer({URL_C: _answer()}, calls),
                      search=_searcher([["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]]).search,
                      max_candidates=1, redo_weak=True, delay_s=0, log=lambda _: None)
    row = _read_csv(out)[0]
    assert len(calls) == 1 and row["suggested_url"] == URL_C
    assert row["ai_reviewed_video_ids"] == "AAAAAAAAAAA|BBBBBBBBBBB|CCCCCCCCCCC"
    assert row["needs_manual_video"] == "false"
    assert (row["start_s"], row["end_s"], row["notes"]) == ("10", "20", "keep manual values")


def test_supplied_history_is_excluded_before_the_candidate_cap():
    row = _row(suggested_url=URL_A, candidate_urls=f"{URL_B}|{URL_C}", ai_reviewed_video_ids="AAAAAAAAAAA|BBBBBBBBBBB")
    outcome = review.review_row(_reviewer({URL_C: _answer()}), row, max_candidates=1, delay_s=0)
    assert outcome.tried == [URL_C]


def test_no_new_candidates_preserves_prior_best_and_watched_history(tmp_path):
    src = tmp_path / "media.csv"
    row = _row(ai_verdict="partial", ai_confidence="0.9", ai_orientation="landscape", ai_start_s="42", ai_end_s="54",
               ai_reviewed_video_ids="AAAAAAAAAAA|BBBBBBBBBBB")
    _write_csv(src, [row])
    review.run_review(str(src), str(src), reviewer=_reviewer({}), search=_searcher([["AAAAAAAAAAA"], ["BBBBBBBBBBB"], []]).search,
                      redo_weak=True, delay_s=0, log=lambda _: None)
    saved = _read_csv(src)[0]
    assert saved["ai_verdict"] == "partial" and saved["suggested_url"] == URL_A
    assert saved["ai_reviewed_video_ids"] == row["ai_reviewed_video_ids"]
    assert saved["ai_candidates_tried"] == "0" and saved["needs_manual_video"] == "true"


def test_query_budget_and_fetched_candidate_survive_repeated_quota_stops(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(src, [_row(suggested_url="")])
    searches = []
    stopped = review.run_review(
        str(src), str(src), reviewer=_reviewer({URL_B: httpx.Response(429, json={})}),
        search=_searcher([[], [], ["BBBBBBBBBBB"]], searches).search, delay_s=0, log=lambda _: None,
    )
    assert stopped["quota_stopped"] == 1 and len(searches) == 3
    progress = json.loads(_read_csv(src)[0]["ai_review_progress"])
    assert progress["search_progress"] == {"queries_used": 3, "pending": [URL_B]}
    assert progress["reviewed_video_ids"] == []  # 429 did not watch this video
    for response in (httpx.Response(429, json={}), _answer(verdict="partial")):
        review.run_review(str(src), str(src), reviewer=_reviewer({URL_B: response}),
                          search=_searcher([], searches).search, delay_s=0, log=lambda _: None)
    row = _read_csv(src)[0]
    assert len(searches) == 3 and row["ai_reviewed_video_ids"] == "BBBBBBBBBBB"
    assert row["ai_review_progress"] == "" and row["needs_manual_video"] == "true"


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



def test_youtube_search_quota_stops_batch_without_marking_rows_error(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(
        src,
        [
            _row(exercise_key="first", suggested_url=""),
            _row(exercise_key="second", suggested_url=""),
        ],
    )
    response = httpx.Response(
        403,
        json={
            "error": {
                "code": 403,
                "message": "The request cannot be completed because you have exceeded your quota.",
                "errors": [{"reason": "quotaExceeded"}],
            }
        },
    )
    searches = []
    counts = review.run_review(
        str(src),
        str(src),
        reviewer=_reviewer({}),
        search=_searcher([response], searches).search,
        delay_s=0,
        log=lambda _: None,
    )

    assert counts["quota_stopped"] == 1
    assert counts["search_quota_stopped"] == 1
    assert len(searches) == 1
    rows = _read_csv(src)
    assert rows[0].get("ai_verdict", "") == ""
    assert rows[1].get("ai_verdict", "") == ""
    progress = json.loads(rows[0]["ai_review_progress"])
    assert progress["search_progress"]["queries_used"] == 0


def test_youtube_search_quota_failure_is_sticky_and_classified():
    response = httpx.Response(
        429,
        json={"error": {"message": "rate limit", "errors": [{"reason": "rateLimitExceeded"}]}},
    )
    searcher = _searcher([response])
    with pytest.raises(discovery.CandidateSearchQuotaExceeded):
        list(searcher.search(_row(), set()))
    with pytest.raises(discovery.CandidateSearchQuotaExceeded):
        list(searcher.search(_row(), set()))



def test_dataforseo_discovers_youtube_videos_and_skips_shorts_and_live():
    calls = []
    searcher = _dataforseo_searcher(
        [[
            {"type": "youtube_video", "video_id": "AAAAAAAAAAA", "is_shorts": True},
            {"type": "youtube_video", "video_id": "BBBBBBBBBBB", "is_live": True},
            {"type": "youtube_channel", "video_id": "CCCCCCCCCCC"},
            {"type": "youtube_video", "video_id": "CCCCCCCCCCC", "is_shorts": False},
        ]],
        calls,
    )
    urls = []
    for url in searcher.search(_row(), set()):
        urls.append(url)
        if urls:
            break
    assert urls == [URL_C]
    assert calls == ["Trap Bar Deadlift exercise demonstration"]


def test_search_clients_use_provider_specific_timeouts():
    youtube = discovery.YouTubeCandidateSearch("youtube-test-key")
    dataforseo = discovery.DataForSEOCandidateSearch("login", "password")
    try:
        assert youtube._client.timeout.read == discovery.YOUTUBE_API_TIMEOUT_SECONDS
        assert dataforseo._client.timeout.read == discovery.DATAFORSEO_TIMEOUT_SECONDS
    finally:
        youtube.close()
        dataforseo.close()


def test_dataforseo_retries_transport_failures_before_success(monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(discovery.time, "sleep", sleeps.append)
    searcher = _dataforseo_searcher(
        [
            httpx.ReadTimeout("timeout 1"),
            httpx.ReadTimeout("timeout 2"),
            ["BBBBBBBBBBB"],
        ],
        calls,
    )

    assert next(iter(searcher.search(_row(), set()))) == URL_B
    assert len(calls) == discovery.DATAFORSEO_TIMEOUT_RETRIES + 1
    assert sleeps == [discovery.DATAFORSEO_RETRY_BACKOFF_SECONDS] * 2


def test_dataforseo_retries_transient_http_failures_before_success(monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(discovery.time, "sleep", sleeps.append)
    searcher = _dataforseo_searcher(
        [
            httpx.Response(500, json={"error": "temporary"}),
            httpx.Response(503, json={"error": "temporary"}),
            ["BBBBBBBBBBB"],
        ],
        calls,
    )

    assert next(iter(searcher.search(_row(), set()))) == URL_B
    assert len(calls) == discovery.DATAFORSEO_TIMEOUT_RETRIES + 1
    assert sleeps == [discovery.DATAFORSEO_RETRY_BACKOFF_SECONDS] * 2


def test_dataforseo_transport_exhaustion_is_provider_error_and_rewinds_query():
    calls = []
    searcher = _dataforseo_searcher(
        [
            httpx.ReadTimeout("timeout 1"),
            httpx.ReadTimeout("timeout 2"),
            httpx.ReadTimeout("timeout 3"),
        ],
        calls,
    )
    progress = discovery.SearchProgress()

    with pytest.raises(discovery.CandidateSearchError, match="unavailable after 3 attempts"):
        list(searcher.search(_row(), set(), progress))

    assert len(calls) == discovery.DATAFORSEO_TIMEOUT_RETRIES + 1
    assert progress.queries_used == 0
    with pytest.raises(discovery.CandidateSearchError):
        list(searcher.search(_row(), set(), progress))
    assert len(calls) == discovery.DATAFORSEO_TIMEOUT_RETRIES + 1


def test_dataforseo_http_failure_is_provider_error_and_rewinds_query():
    calls = []
    searcher = _dataforseo_searcher(
        [httpx.Response(400, json={"error": "bad request"})],
        calls,
    )
    progress = discovery.SearchProgress()

    with pytest.raises(discovery.CandidateSearchError, match="HTTP 400"):
        list(searcher.search(_row(), set(), progress))

    assert calls == ["Trap Bar Deadlift exercise demonstration"]
    assert progress.queries_used == 0


def test_auto_provider_uses_dataforseo_without_youtube_fallback(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.delenv("EXERCISE_MEDIA_SEARCH_PROVIDER", raising=False)

    searcher = discovery.build_candidate_search(youtube_api_key="youtube-test-key")
    try:
        assert isinstance(searcher, discovery.DataForSEOCandidateSearch)
        assert searcher.label == "DataForSEO YouTube SERP"
    finally:
        searcher.close()


@pytest.mark.parametrize(
    ("login", "password"),
    [("login", ""), ("", "password")],
)
def test_auto_provider_rejects_partial_dataforseo_configuration(monkeypatch, login, password):
    monkeypatch.setenv("DATAFORSEO_LOGIN", login)
    monkeypatch.setenv("DATAFORSEO_PASSWORD", password)
    monkeypatch.delenv("EXERCISE_MEDIA_SEARCH_PROVIDER", raising=False)

    with pytest.raises(discovery.CandidateSearchError, match="partially configured"):
        discovery.build_candidate_search(youtube_api_key="youtube-test-key")


def test_auto_provider_uses_youtube_only_when_dataforseo_missing(monkeypatch):
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_PASSWORD", raising=False)
    monkeypatch.delenv("EXERCISE_MEDIA_SEARCH_PROVIDER", raising=False)

    searcher = discovery.build_candidate_search(youtube_api_key="youtube-test-key")
    try:
        assert isinstance(searcher, discovery.YouTubeCandidateSearch)
    finally:
        searcher.close()


def test_explicit_dataforseo_requires_credentials(monkeypatch):
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_PASSWORD", raising=False)
    with pytest.raises(discovery.CandidateSearchError, match="DATAFORSEO_LOGIN"):
        discovery.build_candidate_search(provider="dataforseo", youtube_api_key=None)


def test_dataforseo_rate_limit_is_classified_as_quota_stop():
    searcher = _dataforseo_searcher(
        [
            httpx.Response(
                200,
                json={
                    "status_code": 20000,
                    "tasks": [{"status_code": 40202, "status_message": "rate limit"}],
                },
            )
        ]
    )
    with pytest.raises(discovery.CandidateSearchQuotaExceeded):
        list(searcher.search(_row(), set()))


@pytest.mark.parametrize("status_code", [40200, 40203, 40210])
def test_dataforseo_account_limits_stop_batch_without_marking_rows_error(tmp_path, status_code):
    src = tmp_path / "media.csv"
    _write_csv(
        src,
        [
            _row(exercise_key="first", suggested_url=""),
            _row(exercise_key="second", suggested_url=""),
        ],
    )
    response = httpx.Response(
        200,
        json={
            "status_code": 20000,
            "tasks": [{"status_code": status_code, "status_message": "provider unavailable"}],
        },
    )
    searches = []
    counts = review.run_review(
        str(src),
        str(src),
        reviewer=_reviewer({}),
        search=_dataforseo_searcher([response], searches).search,
        delay_s=0,
        log=lambda _: None,
    )

    assert counts["quota_stopped"] == 1
    assert counts["search_quota_stopped"] == 1
    assert len(searches) == 1
    rows = _read_csv(src)
    assert rows[0].get("ai_verdict", "") == ""
    assert rows[1].get("ai_verdict", "") == ""
    progress = json.loads(rows[0]["ai_review_progress"])
    assert progress["search_progress"]["queries_used"] == 0


def test_dataforseo_provider_failure_stops_batch_without_marking_rows_error(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(
        src,
        [
            _row(exercise_key="first", suggested_url=""),
            _row(exercise_key="second", suggested_url=""),
        ],
    )
    searches = []
    searcher = _dataforseo_searcher(
        [httpx.Response(400, json={"error": "bad request"})],
        searches,
    )

    counts = review.run_review(
        str(src),
        str(src),
        reviewer=_reviewer({}),
        search=searcher.search,
        delay_s=0,
        log=lambda _: None,
    )

    assert counts["search_stopped"] == 1
    assert counts["errors"] == 0
    assert len(searches) == 1
    rows = _read_csv(src)
    assert rows[0].get("ai_verdict", "") == ""
    assert rows[1].get("ai_verdict", "") == ""
    progress = json.loads(rows[0]["ai_review_progress"])
    assert progress["search_progress"]["queries_used"] == 0


def test_dataforseo_timeout_exhaustion_stops_batch_without_poisoning_later_rows(tmp_path):
    src = tmp_path / "media.csv"
    _write_csv(
        src,
        [
            _row(exercise_key="first", suggested_url=""),
            _row(exercise_key="second", suggested_url=""),
        ],
    )
    searches = []
    searcher = _dataforseo_searcher(
        [
            httpx.ReadTimeout("timeout 1"),
            httpx.ReadTimeout("timeout 2"),
            httpx.ReadTimeout("timeout 3"),
        ],
        searches,
    )

    counts = review.run_review(
        str(src),
        str(src),
        reviewer=_reviewer({}),
        search=searcher.search,
        delay_s=0,
        log=lambda _: None,
    )

    assert counts["search_stopped"] == 1
    assert counts["errors"] == 0
    assert len(searches) == discovery.DATAFORSEO_TIMEOUT_RETRIES + 1
    rows = _read_csv(src)
    assert rows[0].get("ai_verdict", "") == ""
    assert rows[1].get("ai_verdict", "") == ""
    progress = json.loads(rows[0]["ai_review_progress"])
    assert progress["search_progress"]["queries_used"] == 0


def test_explicit_youtube_ignores_invalid_dataforseo_location(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setenv("DATAFORSEO_LOCATION_CODE", "not-an-integer")

    searcher = discovery.build_candidate_search(
        provider="youtube",
        youtube_api_key="youtube-test-key",
    )
    try:
        assert isinstance(searcher, discovery.YouTubeCandidateSearch)
    finally:
        searcher.close()
