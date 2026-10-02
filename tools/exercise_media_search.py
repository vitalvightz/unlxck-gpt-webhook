"""Candidate discovery for exercise demo videos; Gemini remains the video judge."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

import httpx

from api.services.exercise_media import YOUTUBE_API_TIMEOUT_SECONDS, parse_youtube_video_id

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
DATAFORSEO_SEARCH_URL = "https://api.dataforseo.com/v3/serp/youtube/organic/live/advanced"
DATAFORSEO_TIMEOUT_SECONDS = 30.0
DATAFORSEO_TIMEOUT_RETRIES = 2
MAX_SEARCH_QUERIES = 3

SEARCH_PROVIDER_ENV = "EXERCISE_MEDIA_SEARCH_PROVIDER"
DATAFORSEO_LOGIN_ENV = "DATAFORSEO_LOGIN"
DATAFORSEO_PASSWORD_ENV = "DATAFORSEO_PASSWORD"
DATAFORSEO_LOCATION_CODE_ENV = "DATAFORSEO_LOCATION_CODE"
DATAFORSEO_LANGUAGE_CODE_ENV = "DATAFORSEO_LANGUAGE_CODE"
DATAFORSEO_STOP_STATUS_CODES = {40202, 40203, 40210}


class CandidateSearchError(RuntimeError):
    pass


class CandidateSearchQuotaExceeded(CandidateSearchError):
    """Candidate-search quota/rate limit exhaustion; stop or fall back."""


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
            except httpx.TimeoutException as exc:
                _rewind_query(progress, checkpoint)
                message = (
                    f"DataForSEO search unavailable after "
                    f"{DATAFORSEO_TIMEOUT_RETRIES + 1} timeout attempts"
                )
                self._failure = (CandidateSearchQuotaExceeded, message)
                raise CandidateSearchQuotaExceeded(message) from exc
            except (httpx.HTTPError, ValueError, CandidateSearchError) as exc:
                # Never expose an httpx exception's URL/headers or API body.
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
                        break
                    except httpx.TimeoutException:
                        if attempt >= DATAFORSEO_TIMEOUT_RETRIES:
                            raise

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
                    raise error
            except CandidateSearchQuotaExceeded as exc:
                _rewind_query(progress, checkpoint)
                self._failure = (CandidateSearchQuotaExceeded, str(exc))
                raise
            except (httpx.HTTPError, ValueError, CandidateSearchError) as exc:
                # Rewind so a fallback provider retries the exact failed query.
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


class FallbackCandidateSearch:
    """Use a primary provider, then continue with a fallback on provider failure."""

    def __init__(
        self,
        primary: CandidateSearcher,
        fallback: CandidateSearcher,
        *,
        on_fallback: Callable[[str], None] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.label = f"{primary.label} -> {fallback.label} fallback"
        self._on_fallback = on_fallback
        self._fallback_reported = False

    def close(self) -> None:
        self.primary.close()
        self.fallback.close()

    def search(
        self,
        row: dict[str, str],
        exclude: set[str],
        progress: SearchProgress | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> Iterable[str]:
        emitted = {parse_youtube_video_id(value) or value for value in exclude}
        try:
            for url in self.primary.search(row, exclude, progress, checkpoint):
                emitted.add(parse_youtube_video_id(url) or url)
                yield url
            return
        except CandidateSearchError as exc:
            # The primary rewinds the failed query before raising, so the
            # fallback starts with that same query rather than skipping it.
            if self._on_fallback is not None and not self._fallback_reported:
                self._on_fallback(
                    f"{self.primary.label} unavailable; using {self.fallback.label}: {exc}"
                )
                self._fallback_reported = True

        yield from self.fallback.search(row, emitted, progress, checkpoint)


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
    on_fallback: Callable[[str], None] | None = None,
) -> CandidateSearcher | None:
    """Build the configured search backend.

    auto uses DataForSEO whenever both credentials are present. The YouTube
    Data API is used for discovery only when DataForSEO is not configured.
    """
    selected = (provider or os.getenv(SEARCH_PROVIDER_ENV, "auto")).strip().lower()
    if selected not in {"auto", "dataforseo", "youtube"}:
        raise CandidateSearchError(
            f"{SEARCH_PROVIDER_ENV} must be auto, dataforseo or youtube"
        )

    login = os.getenv(DATAFORSEO_LOGIN_ENV, "").strip()
    password = os.getenv(DATAFORSEO_PASSWORD_ENV, "").strip()
    language = os.getenv(DATAFORSEO_LANGUAGE_CODE_ENV, "en").strip() or "en"

    youtube: CandidateSearcher | None = (
        YouTubeCandidateSearch(youtube_api_key) if youtube_api_key else None
    )
    dataforseo: CandidateSearcher | None = None
    if selected != "youtube" and login and password:
        dataforseo = DataForSEOCandidateSearch(
            login,
            password,
            location_code=_location_code_from_env(),
            language_code=language,
        )

    if selected == "youtube":
        if youtube is None:
            raise CandidateSearchError(
                "YouTube discovery requested but YOUTUBE_DATA_API_KEY is not set"
            )
        return youtube

    if selected == "dataforseo":
        if dataforseo is None:
            raise CandidateSearchError(
                f"DataForSEO discovery requested but {DATAFORSEO_LOGIN_ENV} "
                f"and {DATAFORSEO_PASSWORD_ENV} are not both set"
            )
        return dataforseo

    if dataforseo:
        return dataforseo
    return youtube
