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
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qs, urlparse

import httpx

from api.models import ExerciseMedia

logger = logging.getLogger(__name__)

INDEX_TTL_SECONDS = 300.0
# After a failed load, retry sooner than the full TTL but not on every request.
INDEX_FAILURE_TTL_SECONDS = 60.0
OEMBED_URL = "https://www.youtube.com/oembed"
OEMBED_TIMEOUT_SECONDS = 8.0

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")
# Trailing qualifiers the planner appends to a bank name
# ("Step-Back Pivot Reset - technical", "Sled Push – light").
_TRAILING_QUALIFIER_RE = re.compile(r"\s+[-–—]\s+[a-z][a-z ]{0,30}$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_exercise_key(name: str | None) -> str:
    """Slug an exercise name so plan wording drift still lands on one row.

    "Romanian Deadlift (RDL)" -> "romanian-deadlift"
    "Step-Back Pivot Reset - technical" -> "step-back-pivot-reset"
    """
    if not name:
        return ""
    # Strip qualifiers before the ASCII fold, which would drop an en/em dash.
    text = str(name).lower().strip()
    text = _PARENTHETICAL_RE.sub(" ", text)
    text = _TRAILING_QUALIFIER_RE.sub("", text.strip())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
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
    try:
        start_s = max(0, int(row.get("start_s") or 0))
        end_raw = row.get("end_s")
        end_s = int(end_raw) if end_raw is not None else None
    except (TypeError, ValueError):
        return None
    if end_s is not None and end_s <= start_s:
        end_s = None
    source = "coach" if row.get("source") == "coach" else "curated"
    return ExerciseMedia(video_id=video_id, start_s=start_s, end_s=end_s, source=source)


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
        reader = getattr(store, "list_exercise_media", None)
        if not callable(reader):
            _index = _MediaIndex(by_key={}, loaded_at=current, ttl=INDEX_TTL_SECONDS)
            return _index.by_key
        try:
            by_key = build_media_index(reader())
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


def check_youtube_video(video_id: str, *, client: httpx.Client | None = None) -> VideoCheck:
    """Ask YouTube oEmbed whether the video can be embedded.

    oEmbed answers 401 when the owner disabled embedding and 404/400 when the
    video is gone or private. Transport errors and 5xx are "unknown": a flaky
    network must never retire a good video.
    """
    if not _VIDEO_ID_RE.match(video_id or ""):
        return VideoCheck(status="unavailable", reason="invalid video id")
    params = {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
    owns_client = client is None
    http = client or httpx.Client(timeout=OEMBED_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        response = http.get(OEMBED_URL, params=params)
    except httpx.HTTPError as exc:
        return VideoCheck(status="unknown", reason=f"transport: {type(exc).__name__}")
    finally:
        if owns_client:
            http.close()
    if response.status_code == 200:
        try:
            title = str(response.json().get("title") or "") or None
        except ValueError:
            title = None
        return VideoCheck(status="ok", title=title)
    if response.status_code == 401:
        return VideoCheck(status="unavailable", reason="embedding disabled")
    if response.status_code in {400, 403, 404}:
        return VideoCheck(status="unavailable", reason=f"oembed {response.status_code}")
    return VideoCheck(status="unknown", reason=f"oembed {response.status_code}")


def run_media_verification_sweep(store: Any, *, client: httpx.Client | None = None) -> dict[str, int]:
    """Re-check every stored video and record the result. Never raises per row."""
    lister = getattr(store, "list_exercise_media_for_verification", None)
    updater = getattr(store, "update_exercise_media_status", None)
    counts = {"ok": 0, "unavailable": 0, "unknown": 0}
    if not callable(lister) or not callable(updater):
        return counts
    owns_client = client is None
    http = client or httpx.Client(timeout=OEMBED_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        for row in lister():
            key = str(row.get("exercise_key") or "")
            result = check_youtube_video(str(row.get("video_id") or ""), client=http)
            counts[result.status] = counts.get(result.status, 0) + 1
            if result.status == "unknown":
                continue
            try:
                updater(key, status=result.status, reason=result.reason)
            except Exception:  # noqa: BLE001
                logger.warning("exercise media status update failed key=%s", key, exc_info=True)
    finally:
        if owns_client:
            http.close()
    if counts["unavailable"]:
        reset_media_index_cache()
    logger.info("exercise media verification sweep: %s", counts)
    return counts
