"""Candidate discovery for exercise demo videos; Gemini remains the video judge."""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

import httpx

from api.services.exercise_media import YOUTUBE_API_TIMEOUT_SECONDS, parse_youtube_video_id

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
DATAFORSEO_SEARCH_URL = "https://api.dataforseo.com/v3/serp/youtube/organic/live/advanced"
DATAFORSEO_TIMEOUT_SECONDS = 30.0
DATAFORSEO_TIMEOUT_RETRIES = 2
DATAFORSEO_RETRY_BACKOFF_SECONDS = 1.0
DATAFORSEO_TRANSIENT_HTTP_STATUS_CODES = {408, 425, 500, 502, 503, 504}
DATAFORSEO_EMPTY_RESULT_RETRIES = 3
DATAFORSEO_EMPTY_RESULT_BACKOFF_SECONDS = 2.0
YTDLP_SEARCH_SIZE = 5
YTDLP_MAX_DURATION_SECONDS = 180
YTDLP_TIMEOUT_SECONDS = 30
YTDLP_RETRIES = 2
YTDLP_RETRY_BACKOFF_SECONDS = 2.0
MAX_SEARCH_QUERIES = 3

SEARCH_PROVIDER_ENV = "EXERCISE_MEDIA_SEARCH_PROVIDER"
DATAFORSEO_LOGIN_ENV = "DATAFORSEO_LOGIN"
DATAFORSEO_PASSWORD_ENV = "DATAFORSEO_PASSWORD"
DATAFORSEO_LOCATION_CODE_ENV = "DATAFORSEO_LOCATION_CODE"
DATAFORSEO_LANGUAGE_CODE_ENV = "DATAFORSEO_LANGUAGE_CODE"
DATAFORSEO_STOP_STATUS_CODES = {40200, 40202, 40203, 40210}


class CandidateSearchError(RuntimeError):
    """Provider-level candidate discovery failure; checkpoint and stop the batch."""


class CandidateSearchQuotaExceeded(CandidateSearchError):
    """Candidate-search quota/rate limit exhaustion; checkpoint and stop."""


class CandidateSearcher(Protocol):
    label: str

    def search(
        self,
        row: dict[str, str],
        exclude: set[str],
        progress: "SearchProgress | None" = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> Iterable[str]: ...

    def close(self) -> None: ...


@dataclass
class SearchProgress:
    queries_used: int = 0
    pending: list[str] = field(default_factory=list)


def search_queries(row: dict[str, str]) -> list[str]:
    name = (row.get("example_name") or (row.get("exercise_key") or "").replace("-", " ")).strip()
    if not name:
        return []
    # Only public exercise metadata goes to search providers, never an athlete's
    # cue, health information, notes or full intake.
    sport = (row.get("sport") or "").strip()
    terms = " ".join(part for part in (name, sport) if part)
    aliases = [
        alias.strip().replace("-", " ")
        for alias in (row.get("aliases") or "").split("|")
        if alias.strip()
    ]
    queries = [f"{terms} exercise demonstration", f"{terms} drill technique"]
    queries.extend(f"{alias} {sport} exercise demonstration".strip() for alias in aliases)
    queries.append(f"{terms} tutorial")
    return list(dict.fromkeys(queries))[:MAX_SEARCH_QUERIES]


def _rewind_query(progress: SearchProgress, checkpoint: Callable[[], None] | None) -> None:
    progress.queries_used = max(0, progress.queries_used - 1)
    if checkpoint:
        checkpoint()


def _search_http_error(response: httpx.Response) -> CandidateSearchError:
    status = response.status_code
    quota = status == 429
    try:
        body = response.json()
    except ValueError:
        body = None

    evidence: list[str] = []
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            evidence.extend(str(error.get(key) or "") for key in ("status", "message"))
            for item in error.get("errors") or []:
                if isinstance(item, dict):
                    evidence.extend(str(item.get(key) or "") for key in ("reason", "message"))
        elif error is not None:
            evidence.append(str(error))

    compact = re.sub(r"[^a-z0-9]", "", " ".join(evidence).lower())
    if status == 403 and any(
        token in compact
        for token in ("quota", "dailylimit", "ratelimit", "userratelimit", "resourceexhausted")
    ):
        quota = True

    if quota:
        return CandidateSearchQuotaExceeded(
            f"YouTube search quota/rate limit reached (HTTP {status})"
        )
    return CandidateSearchError(f"YouTube search HTTP {status}")


class YouTubeCandidateSearch:
    label = "YouTube Data API"

    def __init__(self, api_key: str, *, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self._client = client or httpx.Client(timeout=YOUTUBE_API_TIMEOUT_SECONDS)
        self._failure: tuple[type[CandidateSearchError], str] | None = None

    def close(self) -> None:
        self._client.close()

    def search(
        self,
        row: dict[str, str],
        exclude: set[str],
        progress: SearchProgress | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> Iterable[str]:
        """Fetch five ranked videos at a time, lazily, with at most three queries."""
        if self._failure:
            error_type, message = self._failure
            raise error_type(message)
        seen = {parse_youtube_video_id(url) or url for url in exclude}
        progress = progress or SearchProgress()
        queries = search_queries(row)
        while True:
            while progress.pending:
                url = progress.pending[0]
                video_id = parse_youtube_video_id(url)
                if video_id and video_id not in seen:
                    yield url
                    seen.add(video_id)
                # Leave an in-flight URL pending until Gemini completes it.
                progress.pending.pop(0)
            if progress.queries_used >= len(queries):
                break
            query = queries[progress.queries_used]
            progress.queries_used += 1
            if checkpoint:
                checkpoint()
            try:
                response = self._client.get(
                    YOUTUBE_SEARCH_URL,
                    headers={"X-Goog-Api-Key": self.api_key},
                    params={
                        "part": "snippet",
                        "type": "video",
                        "q": query,
                        "maxResults": 5,
                        "order": "relevance",
                        "videoEmbeddable": "true",
                        "fields": "items(id/videoId)",
                    },
                )
                if response.status_code != 200:
                    raise _search_http_error(response)
                body = response.json()
                if not isinstance(body, dict) or not isinstance(body.get("items"), list):
                    raise CandidateSearchError("YouTube search returned an unexpected response")
            except CandidateSearchQuotaExceeded as exc:
                _rewind_query(progress, checkpoint)
                self._failure = (CandidateSearchQuotaExceeded, str(exc))
                raise
            except (httpx.HTTPError, ValueError, CandidateSearchError) as exc:
                # A provider failure is operational, not a verdict on this row.
                # Rewind so a later run retries the same query from its checkpoint.
                _rewind_query(progress, checkpoint)
                message = (
                    str(exc)
                    if isinstance(exc, CandidateSearchError)
                    else f"YouTube search: {type(exc).__name__}"
                )
                self._failure = (CandidateSearchError, message)
                raise CandidateSearchError(message) from exc

            for item in body["items"]:
                video_id = (
                    (item.get("id") or {}).get("videoId")
                    if isinstance(item, dict) and isinstance(item.get("id"), dict)
                    else None
                )
                if (
                    not isinstance(video_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id)
                    or video_id in seen
                ):
                    continue
                url = f"https://www.youtube.com/watch?v={video_id}"
                if url not in progress.pending:
                    progress.pending.append(url)
            if checkpoint:
                checkpoint()


def _dataforseo_status_error(body: object) -> CandidateSearchError | None:
    if not isinstance(body, dict):
        return CandidateSearchError("DataForSEO search returned an unexpected response")

    top_code = body.get("status_code")
    tasks = body.get("tasks")
    if top_code != 20000:
        if top_code in DATAFORSEO_STOP_STATUS_CODES:
            return CandidateSearchQuotaExceeded(
                f"DataForSEO search unavailable (status {top_code})"
            )
        return CandidateSearchError(f"DataForSEO search failed (status {top_code})")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        return CandidateSearchError("DataForSEO search returned no task result")

    task_code = tasks[0].get("status_code")
    if task_code != 20000:
        if task_code in DATAFORSEO_STOP_STATUS_CODES:
            return CandidateSearchQuotaExceeded(
                f"DataForSEO search unavailable (status {task_code})"
            )
        return CandidateSearchError(f"DataForSEO search failed (status {task_code})")
    return None


def _dataforseo_video_ids(body: object) -> list[str]:
    if not isinstance(body, dict):
        return []
    tasks = body.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        return []

    ids: list[str] = []
    for result in tasks[0].get("result") or []:
        if not isinstance(result, dict):
            continue
        for item in result.get("items") or []:
            if not isinstance(item, dict) or item.get("type") != "youtube_video":
                continue
            # Gemini is looking for a landscape exercise demo, so don't spend
            # a model call on an explicitly identified Short/live broadcast.
            if item.get("is_shorts") is True or item.get("is_live") is True:
                continue
            video_id = item.get("video_id")
            if isinstance(video_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                ids.append(video_id)
    return list(dict.fromkeys(ids))


class DataForSEOCandidateSearch:
    label = "DataForSEO YouTube SERP"

    def __init__(
        self,
        login: str,
        password: str,
        *,
        location_code: int = 2840,
        language_code: str = "en",
        client: httpx.Client | None = None,
    ) -> None:
        self.login = login
        self.password = password
        self.location_code = location_code
        self.language_code = language_code
        self._client = client or httpx.Client(timeout=DATAFORSEO_TIMEOUT_SECONDS)
        self._failure: tuple[type[CandidateSearchError], str] | None = None

    def close(self) -> None:
        self._client.close()

    def search(
        self,
        row: dict[str, str],
        exclude: set[str],
        progress: SearchProgress | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> Iterable[str]:
        """Search YouTube through DataForSEO Live SERP, up to three queries."""
        if self._failure:
            error_type, message = self._failure
            raise error_type(message)

        seen = {parse_youtube_video_id(url) or url for url in exclude}
        progress = progress or SearchProgress()
        queries = search_queries(row)
        while True:
            while progress.pending:
                url = progress.pending[0]
                video_id = parse_youtube_video_id(url)
                if video_id and video_id not in seen:
                    yield url
                    seen.add(video_id)
                progress.pending.pop(0)

            if progress.queries_used >= len(queries):
                break

            query = queries[progress.queries_used]
            progress.queries_used += 1
            if checkpoint:
                checkpoint()

            try:
                response: httpx.Response | None = None
                for attempt in range(DATAFORSEO_TIMEOUT_RETRIES + 1):
                    try:
                        response = self._client.post(
                            DATAFORSEO_SEARCH_URL,
                            auth=(self.login, self.password),
                            json=[
                                {
                                    "keyword": query,
                                    "location_code": self.location_code,
                                    "language_code": self.language_code,
                                    "device": "desktop",
                                }
                            ],
                        )
                    except httpx.TransportError as exc:
                        if attempt < DATAFORSEO_TIMEOUT_RETRIES:
                            time.sleep(DATAFORSEO_RETRY_BACKOFF_SECONDS)
                            continue
                        raise CandidateSearchError(
                            f"DataForSEO search unavailable after "
                            f"{DATAFORSEO_TIMEOUT_RETRIES + 1} attempts "
                            f"({type(exc).__name__})"
                        ) from exc

                    if (
                        response.status_code in DATAFORSEO_TRANSIENT_HTTP_STATUS_CODES
                        and attempt < DATAFORSEO_TIMEOUT_RETRIES
                    ):
                        time.sleep(DATAFORSEO_RETRY_BACKOFF_SECONDS)
                        continue
                    break

                if response is None:
                    raise CandidateSearchError("DataForSEO search returned no response")
                if response.status_code == 429:
                    raise CandidateSearchQuotaExceeded(
                        "DataForSEO search rate limit reached (HTTP 429)"
                    )
                if response.status_code != 200:
                    raise CandidateSearchError(
                        f"DataForSEO search HTTP {response.status_code}"
                    )
                body = response.json()
                error = _dataforseo_status_error(body)
                if error is not None:
                    # A freshly activated account can occasionally return a
                    # successful top-level response with no task payload from
                    # the Live endpoint. Treat that as transient and retry the
                    # same query a few times before stopping the batch.
                    if str(error) == "DataForSEO search returned no task result":
                        for empty_attempt in range(DATAFORSEO_EMPTY_RESULT_RETRIES):
                            time.sleep(DATAFORSEO_EMPTY_RESULT_BACKOFF_SECONDS)
                            response = self._client.post(
                                DATAFORSEO_SEARCH_URL,
                                auth=(self.login, self.password),
                                json=[
                                    {
                                        "keyword": query,
                                        "location_code": self.location_code,
                                        "language_code": self.language_code,
                                        "device": "desktop",
                                    }
                                ],
                            )
                            if response.status_code != 200:
                                break
                            body = response.json()
                            error = _dataforseo_status_error(body)
                            if error is None:
                                break
                    if error is not None:
                        raise error
            except CandidateSearchQuotaExceeded as exc:
                _rewind_query(progress, checkpoint)
                self._failure = (CandidateSearchQuotaExceeded, str(exc))
                raise
            except (httpx.HTTPError, ValueError, CandidateSearchError) as exc:
                # Any provider failure stops the batch at this row. The query is
                # rewound so a later run resumes from the same checkpoint.
                _rewind_query(progress, checkpoint)
                message = (
                    str(exc)
                    if isinstance(exc, CandidateSearchError)
                    else f"DataForSEO search: {type(exc).__name__}"
                )
                self._failure = (CandidateSearchError, message)
                raise CandidateSearchError(message) from exc

            for video_id in _dataforseo_video_ids(body):
                if video_id in seen:
                    continue
                url = f"https://www.youtube.com/watch?v={video_id}"
                if url not in progress.pending:
                    progress.pending.append(url)
            if checkpoint:
                checkpoint()




def _ytdlp_video_ids(info: object) -> list[str]:
    if not isinstance(info, dict):
        return []
    entries = info.get("entries")
    if not isinstance(entries, list):
        return []

    ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("live_status") in {"is_live", "is_upcoming"}:
            continue
        # Cost guard: Gemini video review should never ingest long or
        # duration-unknown search results. yt-dlp search metadata normally
        # includes duration; unknown duration fails closed to manual review.
        try:
            duration_s = float(entry.get("duration"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(duration_s) or duration_s <= 0 or duration_s > YTDLP_MAX_DURATION_SECONDS:
            continue
        video_id = entry.get("id")
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            video_id = parse_youtube_video_id(str(entry.get("url") or ""))
        if isinstance(video_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            ids.append(video_id)
    return list(dict.fromkeys(ids))


class YtDlpCandidateSearch:
    label = "yt-dlp YouTube search"

    def __init__(self, *, ydl_factory=None, sleep: Callable[[float], None] | None = None) -> None:
        if ydl_factory is None:
            try:
                from yt_dlp import YoutubeDL
            except ImportError as exc:  # pragma: no cover - dependency wiring
                raise CandidateSearchError(
                    "yt-dlp discovery requested but yt-dlp is not installed"
                ) from exc
            ydl_factory = YoutubeDL
        self._ydl_factory = ydl_factory
        self._sleep = sleep or time.sleep
        self._failure: tuple[type[CandidateSearchError], str] | None = None

    def close(self) -> None:
        return None

    def _fetch(self, query: str) -> object:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "socket_timeout": YTDLP_TIMEOUT_SECONDS,
            "playlistend": YTDLP_SEARCH_SIZE,
        }
        with self._ydl_factory(options) as ydl:
            return ydl.extract_info(
                f"ytsearch{YTDLP_SEARCH_SIZE}:{query}",
                download=False,
            )

    def search(
        self,
        row: dict[str, str],
        exclude: set[str],
        progress: SearchProgress | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> Iterable[str]:
        """Search YouTube directly with yt-dlp, preserving review checkpoints."""
        if self._failure:
            error_type, message = self._failure
            raise error_type(message)

        seen = {parse_youtube_video_id(url) or url for url in exclude}
        progress = progress or SearchProgress()
        queries = search_queries(row)

        while True:
            while progress.pending:
                url = progress.pending[0]
                video_id = parse_youtube_video_id(url)
                if video_id and video_id not in seen:
                    yield url
                    seen.add(video_id)
                progress.pending.pop(0)

            if progress.queries_used >= len(queries):
                break

            query = queries[progress.queries_used]
            progress.queries_used += 1
            if checkpoint:
                checkpoint()

            try:
                info: object | None = None
                for attempt in range(YTDLP_RETRIES + 1):
                    try:
                        info = self._fetch(query)
                        break
                    except Exception as exc:  # yt-dlp wraps provider/network failures
                        message = str(exc).lower()
                        if any(
                            token in message
                            for token in (
                                "http error 429",
                                "too many requests",
                                "sign in to confirm you're not a bot",
                                "sign in to confirm you’re not a bot",
                            )
                        ):
                            raise CandidateSearchQuotaExceeded(
                                "yt-dlp/YouTube search rate-limited or bot-challenged"
                            ) from exc
                        if attempt < YTDLP_RETRIES:
                            self._sleep(YTDLP_RETRY_BACKOFF_SECONDS)
                            continue
                        raise CandidateSearchError(
                            f"yt-dlp search unavailable after {YTDLP_RETRIES + 1} attempts "
                            f"({type(exc).__name__})"
                        ) from exc

                if not isinstance(info, dict):
                    raise CandidateSearchError("yt-dlp search returned an unexpected response")
            except CandidateSearchQuotaExceeded as exc:
                _rewind_query(progress, checkpoint)
                self._failure = (CandidateSearchQuotaExceeded, str(exc))
                raise
            except CandidateSearchError as exc:
                _rewind_query(progress, checkpoint)
                self._failure = (CandidateSearchError, str(exc))
                raise

            for video_id in _ytdlp_video_ids(info):
                if video_id in seen:
                    continue
                url = f"https://www.youtube.com/watch?v={video_id}"
                if url not in progress.pending:
                    progress.pending.append(url)
            if checkpoint:
                checkpoint()



def _location_code_from_env() -> int:
    raw = os.getenv(DATAFORSEO_LOCATION_CODE_ENV, "2840").strip() or "2840"
    try:
        return int(raw)
    except ValueError as exc:
        raise CandidateSearchError(
            f"{DATAFORSEO_LOCATION_CODE_ENV} must be an integer"
        ) from exc


def build_candidate_search(
    *,
    provider: str | None = None,
    youtube_api_key: str | None = None,
) -> CandidateSearcher | None:
    """Build exactly one discovery provider.

    Auto mode uses yt-dlp so exercise discovery does not depend on a paid SERP
    account. DataForSEO and the YouTube Data API remain explicit fallbacks.
    """
    selected = (provider or os.getenv(SEARCH_PROVIDER_ENV, "auto")).strip().lower()
    if selected not in {"auto", "dataforseo", "youtube", "ytdlp"}:
        raise CandidateSearchError(
            f"{SEARCH_PROVIDER_ENV} must be auto, ytdlp, dataforseo or youtube"
        )

    login = os.getenv(DATAFORSEO_LOGIN_ENV, "").strip()
    password = os.getenv(DATAFORSEO_PASSWORD_ENV, "").strip()
    language = os.getenv(DATAFORSEO_LANGUAGE_CODE_ENV, "en").strip() or "en"

    def dataforseo_searcher() -> CandidateSearcher:
        if not login or not password:
            raise CandidateSearchError(
                f"DataForSEO discovery requested but {DATAFORSEO_LOGIN_ENV} "
                f"and {DATAFORSEO_PASSWORD_ENV} are not both set"
            )
        return DataForSEOCandidateSearch(
            login,
            password,
            location_code=_location_code_from_env(),
            language_code=language,
        )

    if selected == "ytdlp" or selected == "auto":
        return YtDlpCandidateSearch()

    if selected == "dataforseo":
        return dataforseo_searcher()

    if selected == "youtube":
        if not youtube_api_key:
            raise CandidateSearchError(
                "YouTube discovery requested but YOUTUBE_DATA_API_KEY is not set"
            )
        return YouTubeCandidateSearch(youtube_api_key)

    return None
