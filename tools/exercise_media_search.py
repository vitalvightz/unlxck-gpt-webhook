"""Bounded YouTube candidate discovery; Gemini remains the video judge."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

import httpx

from api.services.exercise_media import YOUTUBE_API_TIMEOUT_SECONDS, parse_youtube_video_id

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
MAX_SEARCH_QUERIES = 3


class CandidateSearchError(RuntimeError):
    pass


class CandidateSearchQuotaExceeded(CandidateSearchError):
    """YouTube search quota/rate limit exhaustion; stop the batch and resume later."""


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
        for token in (
            "quota",
            "dailylimit",
            "ratelimit",
            "userratelimit",
            "resourc eexhausted".replace(" ", ""),
        )
    ):
        quota = True

    if quota:
        return CandidateSearchQuotaExceeded(
            f"YouTube search quota/rate limit reached (HTTP {status})"
        )
    return CandidateSearchError(f"YouTube search HTTP {status}")


@dataclass
class SearchProgress:
    queries_used: int = 0
    pending: list[str] = field(default_factory=list)


def search_queries(row: dict[str, str]) -> list[str]:
    name = (row.get("example_name") or (row.get("exercise_key") or "").replace("-", " ")).strip()
    if not name:
        return []
    # Only public exercise metadata goes to YouTube, never an athlete's cue,
    # health information, notes or full intake.
    sport = (row.get("sport") or "").strip()
    terms = " ".join(part for part in (name, sport) if part)
    aliases = [alias.strip().replace("-", " ") for alias in (row.get("aliases") or "").split("|") if alias.strip()]
    queries = [f"{terms} exercise demonstration", f"{terms} drill technique"]
    queries.extend(f"{alias} {sport} exercise demonstration".strip() for alias in aliases)
    queries.append(f"{terms} tutorial")
    return list(dict.fromkeys(queries))[:MAX_SEARCH_QUERIES]


class YouTubeCandidateSearch:
    def __init__(self, api_key: str, *, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self._client = client or httpx.Client(timeout=YOUTUBE_API_TIMEOUT_SECONDS)
        self._failure: tuple[type[CandidateSearchError], str] | None = None

    def close(self) -> None:
        self._client.close()

    def search(
        self, row: dict[str, str], exclude: set[str], progress: SearchProgress | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> Iterable[str]:
        """Fetch five ranked videos at a time, lazily, with at most three queries.

        Stopping the review loop stops discovery too. No pagination or Gemini
        calls occur here; duplicates across queries and supplied URLs are skipped.
        """
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
                        "part": "snippet", "type": "video", "q": query,
                        "maxResults": 5, "order": "relevance", "videoEmbeddable": "true",
                        "fields": "items(id/videoId)",
                    },
                )
                if response.status_code != 200:
                    raise _search_http_error(response)
                body = response.json()
                if not isinstance(body, dict) or not isinstance(body.get("items"), list):
                    raise CandidateSearchError("YouTube search returned an unexpected response")
            except CandidateSearchQuotaExceeded as exc:
                # The query did not complete, so preserve it for the next run
                # after quota resets instead of burning one of this row's searches.
                progress.queries_used = max(0, progress.queries_used - 1)
                if checkpoint:
                    checkpoint()
                self._failure = (CandidateSearchQuotaExceeded, str(exc))
                raise
            except (httpx.HTTPError, ValueError, CandidateSearchError) as exc:
                # Never expose an httpx exception's URL/headers or API body.
                message = str(exc) if isinstance(exc, CandidateSearchError) else f"YouTube search: {type(exc).__name__}"
                self._failure = (CandidateSearchError, message)
                raise CandidateSearchError(message) from exc
            for item in body["items"]:
                video_id = (item.get("id") or {}).get("videoId") if isinstance(item, dict) and isinstance(item.get("id"), dict) else None
                if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) or video_id in seen:
                    continue
                url = f"https://www.youtube.com/watch?v={video_id}"
                if url not in progress.pending:
                    progress.pending.append(url)
            if checkpoint:
                checkpoint()
