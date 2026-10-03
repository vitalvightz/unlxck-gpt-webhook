"""Demo videos for plan exercises.

Videos live in ``public.exercise_media`` (one row per exercise, keyed by a
normalized slug) and are attached to a plan when it is served, never stored in
``structured_plan``. That keeps two guarantees:

* the Stage-2 model is never the source of a video ID (a hallucinated ID is a
  broken or wrong player), and
* a video can be added, swapped or retired without regenerating any plan.

Resolution is best-effort: a missing table, an outage or an unknown exercise
yields no media, and the block renders cues-only.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qs, urlparse

import httpx

from api.models import ExerciseMedia

logger = logging.getLogger(__name__)

INDEX_TTL_SECONDS = 300.0
# After a failed load, retry sooner than the full TTL but not on every request.
INDEX_FAILURE_TTL_SECONDS = 60.0
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_API_KEY_ENV = "YOUTUBE_DATA_API_KEY"
YOUTUBE_API_TIMEOUT_SECONDS = 8.0
# videos.list accepts up to 50 IDs per call (1 quota unit per call).
_VIDEOS_PER_REQUEST = 50

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
# A dose the converter appended to the exercise name after a spaced dash:
# "Assault Bike - 25 min", "Turkish Get-Up – 3 reps per side". The tail must
# start with a number, so a hyphenated name ("Get-Up") or a worded qualifier
# ("Box Jump - Max Height") is never cut.
_DOSE_SUFFIX_RE = re.compile(r"\s+[-–—]\s+\d[^-–—]*$")


def strip_dose_suffix(name: str | None) -> str:
    """Drop a trailing " - <dose>" from an exercise name; unchanged otherwise.

    "Assault Bike - 25 min" -> "Assault Bike"
    "Turkish Get-Up - 3 reps per side" -> "Turkish Get-Up"
    """
    text = str(name or "")
    stripped = _DOSE_SUFFIX_RE.sub("", text).rstrip()
    # Keep the name whole when no exercise words would be left ("5 - 10 min").
    return stripped if re.search(r"[A-Za-z]", stripped) else text


def normalize_exercise_key(name: str | None) -> str:
    """Slug an exercise name without dropping any word of it.

    Only case, punctuation, accents and "&" are folded, so spelling drift still
    lands on one row ("Hollow-Body Hold" and "Hollow Body Hold"). Qualifiers are
    kept: "Box Jump (Max Height)" and "Box Jump (Stick Landing)" are different
    exercises and must never share a video. Two names that really are the same
    movement are joined by an explicit alias on the media row, not by the slug.

    "Romanian Deadlift (RDL)" -> "romanian-deadlift-rdl"
    "Clean & Press" -> "clean-and-press"
    """
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name).lower()).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ")
    return _NON_ALNUM_RE.sub("-", text).strip("-")


def parse_youtube_video_id(value: str | None) -> str | None:
    """Accept a bare ID or any common YouTube URL shape; return the 11-char ID."""
    if not value:
        return None
    raw = value.strip()
    if _VIDEO_ID_RE.match(raw):
        return raw
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate: str | None = None
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "youtube-nocookie.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
                candidate = parts[1]
    return candidate if candidate and _VIDEO_ID_RE.match(candidate) else None


@dataclass(frozen=True)
class _MediaIndex:
    by_key: Mapping[str, ExerciseMedia]
    loaded_at: float
    ttl: float

    def fresh(self, now: float) -> bool:
        return now - self.loaded_at < self.ttl


_index_lock = threading.Lock()
_index: _MediaIndex | None = None


def _media_from_row(row: Mapping[str, Any]) -> ExerciseMedia | None:
    video_id = str(row.get("video_id") or "")
    if not _VIDEO_ID_RE.match(video_id):
        return None
    # Keep YouTube's Made for Kids classification as metadata. Curator-approved
    # videos may serve whether it is true or false, but an unreported status is
    # still excluded as a safety/backstop against stale legacy rows.
    if not isinstance(row.get("made_for_kids"), bool):
        return None
    try:
        start_s = max(0, int(row.get("start_s") or 0))
        end_raw = row.get("end_s")
        end_s = int(end_raw) if end_raw is not None else None
    except (TypeError, ValueError):
        return None
    if end_s is not None and end_s <= start_s:
        end_s = None
    source = "coach" if row.get("source") == "coach" else "curated"
    channel_title = str(row.get("channel_title") or "").strip()[:200] or None
    return ExerciseMedia(
        video_id=video_id,
        start_s=start_s,
        end_s=end_s,
        source=source,
        channel_title=channel_title,
    )


def build_media_index(rows: Iterable[Mapping[str, Any]]) -> dict[str, ExerciseMedia]:
    """Map every exercise_key and alias (normalized) to its media.

    A primary key always wins over another row's alias, so an alias can never
    hijack an exercise that has its own video.
    """
    primary: dict[str, ExerciseMedia] = {}
    aliased: dict[str, ExerciseMedia] = {}
    for row in rows:
        media = _media_from_row(row)
        key = normalize_exercise_key(row.get("exercise_key"))
        if media is None or not key:
            continue
        primary[key] = media
        for alias in row.get("aliases") or []:
            alias_key = normalize_exercise_key(alias)
            if alias_key and alias_key not in aliased:
                aliased[alias_key] = media
    return {**aliased, **primary}


def load_media_index(store: Any, *, now: float | None = None) -> Mapping[str, ExerciseMedia]:
    """Cached index of served media. Never raises."""
    global _index
    current = time.monotonic() if now is None else now
    snapshot = _index
    if snapshot is not None and snapshot.fresh(current):
        return snapshot.by_key
    with _index_lock:
        snapshot = _index
        if snapshot is not None and snapshot.fresh(current):
            return snapshot.by_key
        try:
            by_key = build_media_index(store.list_exercise_media())
            _index = _MediaIndex(by_key=by_key, loaded_at=current, ttl=INDEX_TTL_SECONDS)
        except Exception:  # noqa: BLE001 - media is decoration; the plan must still load
            logger.warning("exercise media index load failed", exc_info=True)
            stale = snapshot.by_key if snapshot is not None else {}
            _index = _MediaIndex(by_key=stale, loaded_at=current, ttl=INDEX_FAILURE_TTL_SECONDS)
        return _index.by_key


def reset_media_index_cache() -> None:
    global _index
    with _index_lock:
        _index = None


def _iter_block_names(structured_plan: Any) -> Iterable[str]:
    for week in getattr(structured_plan, "weeks", None) or []:
        for day in getattr(week, "days", None) or []:
            for session in getattr(day, "sessions", None) or []:
                for block in getattr(session, "blocks", None) or []:
                    name = getattr(block, "display_name", None)
                    if isinstance(name, str) and name.strip():
                        yield name


def resolve_plan_exercise_media(
    structured_plan: Any,
    index: Mapping[str, ExerciseMedia],
) -> dict[str, ExerciseMedia]:
    """Media for every block in the plan that has a video, keyed by display_name."""
    if structured_plan is None or not index:
        return {}
    resolved: dict[str, ExerciseMedia] = {}
    for name in _iter_block_names(structured_plan):
        if name in resolved:
            continue
        media = index.get(normalize_exercise_key(name))
        if media is None:
            # Plans saved before display names were cleaned can still carry the
            # dose in the name; the exercise is the part before it.
            base = strip_dose_suffix(name)
            if base != name:
                media = index.get(normalize_exercise_key(base))
        if media is not None:
            resolved[name] = media
    return resolved


def attach_exercise_media(detail: Any, store: Any) -> Any:
    """Populate ``detail.outputs.exercise_media`` in place. Never raises."""
    try:
        outputs = getattr(detail, "outputs", None)
        structured_plan = getattr(outputs, "structured_plan", None)
        if outputs is None or structured_plan is None:
            return detail
        outputs.exercise_media = resolve_plan_exercise_media(
            structured_plan,
            load_media_index(store),
        )
    except Exception:  # noqa: BLE001
        logger.warning("exercise media attach failed", exc_info=True)
    return detail


# ---------------------------------------------------------------------------
# Availability checks (import tool + daily worker sweep)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoCheck:
    status: str  # "ok" | "unavailable" | "unknown"
    reason: str | None = None
    title: str | None = None
    channel_title: str | None = None
    made_for_kids: bool | None = None


def is_youtube_provider_failure(check: VideoCheck) -> bool:
    """Whether an unknown result came from the Data API, not the video itself."""
    reason = (check.reason or "").lower()
    return check.status == "unknown" and (
        reason.startswith("transport:") or reason.startswith("data api")
    )


def youtube_api_key() -> str | None:
    return (os.getenv(YOUTUBE_API_KEY_ENV) or "").strip() or None


def _classify_video(item: Mapping[str, Any]) -> VideoCheck:
    snippet = item.get("snippet") or {}
    status = item.get("status") or {}
    made_for_kids = status.get("madeForKids")
    found = {
        "title": str(snippet.get("title") or "").strip()[:200] or None,
        "channel_title": str(snippet.get("channelTitle") or "").strip()[:200] or None,
        "made_for_kids": made_for_kids if isinstance(made_for_kids, bool) else None,
    }
    upload_status = status.get("uploadStatus")
    if upload_status is not None and upload_status != "processed":
        return VideoCheck(status="unavailable", reason=f"upload {upload_status}", **found)
    if status.get("privacyStatus") == "private":
        return VideoCheck(status="unavailable", reason="private", **found)
    if status.get("embeddable") is False:
        return VideoCheck(status="unavailable", reason="embedding disabled", **found)
    # A curator may deliberately approve an embeddable Made for Kids demo.
    # We still require YouTube to explicitly report the classification so the
    # stored metadata remains accurate.
    if not isinstance(made_for_kids, bool) or status.get("embeddable") is not True:
        return VideoCheck(status="unknown", reason="status not reported", **found)
    return VideoCheck(status="ok", **found)


def check_youtube_videos(
    video_ids: Iterable[str],
    *,
    api_key: str,
    client: httpx.Client | None = None,
) -> dict[str, VideoCheck]:
    """Check each video through the YouTube Data API (videos.list).

    One call covers up to 50 videos and reports what serving needs: whether
    the video still exists and is public or unlisted, whether embedding is
    allowed, and its Made for Kids status. A video missing from the response
    is deleted or private. Transport errors and non-200 answers (quota, bad
    key) are "unknown": a flaky network must never retire a good video.
    """
    results: dict[str, VideoCheck] = {}
    pending: list[str] = []
    for video_id in dict.fromkeys(video_ids):
        if _VIDEO_ID_RE.match(video_id or ""):
            pending.append(video_id)
        else:
            results[video_id] = VideoCheck(status="unavailable", reason="invalid video id")
    if not pending:
        return results

    owns_client = client is None
    http = client or httpx.Client(timeout=YOUTUBE_API_TIMEOUT_SECONDS)
    try:
        for offset in range(0, len(pending), _VIDEOS_PER_REQUEST):
            batch = pending[offset : offset + _VIDEOS_PER_REQUEST]
            results.update(_check_batch(http, batch, api_key))
    finally:
        if owns_client:
            http.close()
    return results


def _check_batch(http: httpx.Client, batch: list[str], api_key: str) -> dict[str, VideoCheck]:
    def unknown(reason: str) -> dict[str, VideoCheck]:
        return {video_id: VideoCheck(status="unknown", reason=reason) for video_id in batch}

    try:
        # The key goes in a header, not the query string, so request logging
        # never records it.
        response = http.get(
            YOUTUBE_VIDEOS_URL,
            params={
                "part": "snippet,status",
                "id": ",".join(batch),
                "fields": "items(id,snippet(title,channelTitle),status(uploadStatus,privacyStatus,embeddable,madeForKids))",
            },
            headers={"X-Goog-Api-Key": api_key},
        )
    except httpx.HTTPError as exc:
        return unknown(f"transport: {type(exc).__name__}")
    if response.status_code != 200:
        return unknown(f"data api {response.status_code}")
    try:
        items = response.json().get("items") or []
    except ValueError:
        return unknown("data api: invalid json")
    by_id = {str(item.get("id")): item for item in items if isinstance(item, dict)}
    return {
        video_id: _classify_video(by_id[video_id])
        if video_id in by_id
        else VideoCheck(status="unavailable", reason="not found or private")
        for video_id in batch
    }


def check_youtube_video(
    video_id: str,
    *,
    api_key: str,
    client: httpx.Client | None = None,
) -> VideoCheck:
    return check_youtube_videos([video_id], api_key=api_key, client=client)[video_id]


def run_media_verification_sweep(
    store: Any,
    *,
    api_key: str | None = None,
    client: httpx.Client | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Re-check every stored video and record the result. Never raises per row.

    Unavailable rows are re-checked too, so a video that was only briefly
    private or restricted is served again once YouTube reports it as fine.

    Rows go in batches of 50 (one API call each) and ``should_stop`` is asked
    between batches, so a worker shutting down waits for at most one batch.

    The API process picks up the new statuses when its index cache expires
    (INDEX_TTL_SECONDS); this usually runs in the worker, whose cache is not
    the one serving plans.
    """
    counts = {"ok": 0, "unavailable": 0, "unknown": 0, "provider_stopped": 0}
    key = api_key or youtube_api_key()
    if not key:
        logger.warning("exercise media verification skipped: %s is not set", YOUTUBE_API_KEY_ENV)
        return counts
    rows = list(store.list_exercise_media_for_verification())
    owns_client = client is None
    http = client or httpx.Client(timeout=YOUTUBE_API_TIMEOUT_SECONDS)
    try:
        for offset in range(0, len(rows), _VIDEOS_PER_REQUEST):
            if should_stop is not None and should_stop():
                logger.info("exercise media verification stopped early at row %s of %s", offset, len(rows))
                break
            batch = rows[offset : offset + _VIDEOS_PER_REQUEST]
            results = check_youtube_videos(
                (str(row.get("video_id") or "") for row in batch),
                api_key=key,
                client=http,
            )
            provider_failures = [
                result for result in results.values()
                if is_youtube_provider_failure(result)
            ]
            if provider_failures:
                counts["unknown"] += len(provider_failures)
                counts["provider_stopped"] = 1
                logger.warning(
                    "exercise media verification stopped: YouTube Data API unavailable (%s)",
                    provider_failures[0].reason or "unknown provider failure",
                )
                break
            for row in batch:
                _record_check(row, results, store.update_exercise_media_status, counts)
    finally:
        if owns_client:
            http.close()
    logger.info("exercise media verification sweep: %s", counts)
    return counts


def _record_check(
    row: Mapping[str, Any],
    results: Mapping[str, VideoCheck],
    updater: Callable[..., Any],
    counts: dict[str, int],
) -> None:
    exercise_key = str(row.get("exercise_key") or "")
    result = results.get(str(row.get("video_id") or "")) or VideoCheck(status="unknown")
    counts[result.status] = counts.get(result.status, 0) + 1
    if result.status == "unknown":
        return
    try:
        updater(
            exercise_key,
            status=result.status,
            reason=result.reason,
            made_for_kids=result.made_for_kids,
            title=result.title,
            channel_title=result.channel_title,
        )
    except Exception:  # noqa: BLE001
        logger.warning("exercise media status update failed key=%s", exercise_key, exc_info=True)
