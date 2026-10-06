"""Curate exercise demo videos (public.exercise_media).

Requires service-role credentials (the same ones the backend uses) and a
YouTube Data API v3 key for the video checks (import and verify):

    SUPABASE_URL=...
    SUPABASE_SERVICE_ROLE_KEY=...
    YOUTUBE_DATA_API_KEY=...

Workflow:
    # 1a. Export the most-prescribed exercises that have no video yet.
    python tools/exercise_media.py candidates --limit 100 --out media.csv

    # 1b. Or export every uncovered exercise from a canonical bank. Existing
    #     served exercise_media keys and aliases are omitted automatically.
    python tools/exercise_media.py bank data/exercise_bank.json --out exercise_bank_media.csv

    # 2. Fill youtube_url (+ start_s / end_s for the loop segment) in the CSV.
    #    Rows with the same `family` are variants of one base name ("Box Jump",
    #    "Box Jump (Max Height)"). Each keeps its own key; give a variant the
    #    same video only by listing it in `aliases` when it is genuinely the
    #    same movement.

    # 3. Check every video through the YouTube Data API (exists, embeddable,
    #    record its Made for Kids classification and portrait/landscape
    #    orientation) and upsert. Dry-run first.
    python tools/exercise_media.py import media.csv --dry-run
    python tools/exercise_media.py import media.csv

    # Optional, between 1 and 3: let Gemini watch each suggested video, confirm
    # it shows the exercise and pre-fill start_s / end_s. Needs GEMINI_API_KEY.
    # Candidate discovery defaults to yt-dlp. DataForSEO and the YouTube API
    # are available through --search-provider when configured.
    # With --no-search, input needs suggested_url (plus optional candidate_urls,
    # '|'-separated, and plan_cue). Saves after every video and row; re-running
    # the same command, with or
    # without --out, resumes. Exits 1 if any row failed or a provider/quota
    # stop left the run incomplete. A person still approves each row by copying the URL into
    # youtube_url.
    python tools/exercise_media.py review media.csv --out media.reviewed.csv

    # Check saved progress without API keys, discovery or Gemini charges.
    python tools/exercise_media.py review-status media.reviewed.csv
    # Edit/approve rows in the reviewed CSV; it is authoritative on resume.

    # With a configured search provider, weak results trigger bounded candidate searches.
    # Revisit weak/partial rows while keeping strong reviewed matches:
    python tools/exercise_media.py review media.csv --redo-weak --max-candidates 3
    # --no-search uses supplied URLs only. Unresolved rows get needs_manual_video=true.
    # A strong result also needs a usable loop. --redo-weak skips video IDs
    # recorded in ai_reviewed_video_ids and judges only new candidates.

    # Re-check every stored video now (the worker also does this daily). This
    # also fills exercise_media.orientation for rows that do not have one yet.
    python tools/exercise_media.py verify

CSV columns: exercise_key, family, example_name, block_type, occurrences,
youtube_url, start_s, end_s, source, aliases, notes, plus public review_sport,
review_context and review_context_required metadata for discovery/review. Rows
without youtube_url are skipped. aliases is a "|"-separated list of other names
that should share the video. family is a curation hint only and is never used
for matching.

Exit codes: 0 success / 1 some rows rejected, failed review or left unreviewed / 2 usage or operational error.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx  # noqa: E402

from api.services.exercise_media import (  # noqa: E402
    YOUTUBE_API_KEY_ENV,
    YOUTUBE_API_TIMEOUT_SECONDS,
    check_youtube_videos,
    is_youtube_provider_failure,
    normalize_exercise_key,
    parse_youtube_video_id,
    run_media_verification_sweep,
    youtube_api_key,
)

CSV_COLUMNS = (
    "exercise_key",
    "family",
    "example_name",
    "block_type",
    "occurrences",
    "youtube_url",
    "start_s",
    "end_s",
    "source",
    "aliases",
    "notes",
    "review_sport",
    "review_context",
    "review_context_required",
)

# Blocks with nothing to demonstrate on camera.
_NO_DEMO_BLOCK_TYPES = {"mindset", "cooldown_recovery"}
# Matches the exercise_key check constraint.
_MAX_KEY_LENGTH = 120

_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")
# Trailing qualifiers the planner appends to a bank name
# ("Step-Back Pivot Reset - technical", "Sled Push – light").
_TRAILING_QUALIFIER_RE = re.compile(r"\s+[-–—]\s+[a-z][a-z ]{0,30}$")


def family_key(name: str | None) -> str:
    """Base name with qualifiers stripped, to group variants for a curator.

    "Box Jump (Max Height)" and "Box Jump (Stick Landing)" share the family
    box-jump. This is a sorting hint in the candidates CSV only: videos match
    on normalize_exercise_key, which keeps the qualifiers.
    """
    text = str(name or "").lower()
    text = _PARENTHETICAL_RE.sub(" ", text)
    text = _TRAILING_QUALIFIER_RE.sub("", text.strip())
    return normalize_exercise_key(text)


def _require_api_key() -> str:
    key = youtube_api_key()
    if not key:
        print(
            f"error: {YOUTUBE_API_KEY_ENV} is not set. Videos are checked through the "
            "YouTube Data API (embeddable, Made for Kids) before they can be served.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return key


def _build_store():
    from api.store import SupabaseAppStore

    try:
        return SupabaseAppStore.from_env()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _iter_blocks(structured_plan: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(structured_plan, dict):
        return
    for week in structured_plan.get("weeks") or []:
        for day in (week or {}).get("days") or []:
            for session in (day or {}).get("sessions") or []:
                for block in (session or {}).get("blocks") or []:
                    if isinstance(block, dict):
                        yield block


def rank_candidates(
    plans: Iterable[Any],
    *,
    existing_keys: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Most frequent demo-able exercises across plans that still lack a video."""
    counts: Counter[str] = Counter()
    example: dict[str, tuple[str, str]] = {}
    for structured_plan in plans:
        for block in _iter_blocks(structured_plan):
            block_type = str(block.get("block_type") or "")
            if block_type in _NO_DEMO_BLOCK_TYPES:
                continue
            name = str(block.get("display_name") or "").strip()
            key = normalize_exercise_key(name)
            if not key or key in existing_keys:
                continue
            counts[key] += 1
            example.setdefault(key, (name, block_type))
    rows = []
    for key, occurrences in counts.most_common(limit):
        name, block_type = example[key]
        rows.append(
            {
                "exercise_key": key,
                "family": family_key(name),
                "example_name": name,
                "block_type": block_type,
                "occurrences": occurrences,
                "youtube_url": "",
                "start_s": "",
                "end_s": "",
                "source": "curated",
                "aliases": "",
                "notes": "",
            }
        )
    return rows


def _served_media_keys(store: Any) -> set[str]:
    """Keys and aliases that already have a currently served video."""
    existing: set[str] = set()
    for row in store.list_exercise_media_for_verification():
        if row.get("status") != "ok":
            continue
        key = normalize_exercise_key(row.get("exercise_key"))
        if key:
            existing.add(key)
        existing.update(
            alias_key
            for alias in row.get("aliases") or []
            if (alias_key := normalize_exercise_key(alias))
        )
    return existing


_REVIEW_COMBAT_SPORTS = {"boxing", "kickboxing", "muay_thai", "mma", "wrestling", "bjj", "combat"}
_REVIEW_COMBAT_TAG_PREFIXES = (
    "boxer_",
    "boxing_",
    "kickboxing_",
    "muay_thai_",
    "mma_",
    "wrestling_",
    "bjj_",
    "grappl",
    "combat_",
)


def _review_context_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _review_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _bank_review_context(record: dict[str, Any]) -> tuple[str, str, str]:
    """Preserve public canonical sport context for media discovery/review.

    Generic S&C exercises stay sport-agnostic. Combat context becomes required
    only when the bank explicitly marks it via sport_specific or combat-technique
    tags such as boxer_footwork / boxer_stance.
    """
    tags = _review_list(record.get("tags"))
    tag_tokens = [_review_context_token(tag) for tag in tags]
    context_tags = [
        tag for tag, token in zip(tags, tag_tokens)
        if token.startswith(_REVIEW_COMBAT_TAG_PREFIXES)
    ]

    raw_sports = [
        *_review_list(record.get("sport")),
        *_review_list(record.get("sports")),
        *_review_list(record.get("tactical_styles")),
    ]
    sports: list[str] = []
    for value in raw_sports:
        token = _review_context_token(value)
        if token in _REVIEW_COMBAT_SPORTS and token not in sports:
            sports.append(token)

    for token in tag_tokens:
        inferred = None
        if token.startswith(("boxer_", "boxing_")):
            inferred = "boxing"
        elif token.startswith("kickboxing_"):
            inferred = "kickboxing"
        elif token.startswith("muay_thai_"):
            inferred = "muay_thai"
        elif token.startswith("mma_"):
            inferred = "mma"
        elif token.startswith("wrestling_"):
            inferred = "wrestling"
        elif token.startswith("bjj_"):
            inferred = "bjj"
        elif token.startswith(("grappl", "combat_")):
            inferred = "combat"
        if inferred and inferred not in sports:
            sports.append(inferred)

    required = bool(sports) and (
        record.get("sport_specific") is True or bool(context_tags)
    )
    if not required:
        return "", "", "false"

    parts = [f"required combat context: {', '.join(sports)}"]
    if context_tags:
        parts.append("context tags: " + ", ".join(context_tags))
    movement = str(record.get("movement") or "").strip()
    method = str(record.get("method") or "").strip()
    if movement:
        parts.append(f"movement: {movement}")
    if method:
        parts.append(f"method: {method}")
    return " ".join(sports), "; ".join(parts), "true"


def bank_rows(
    records: Iterable[Any],
    *,
    existing_keys: set[str],
) -> list[dict[str, Any]]:
    """Turn canonical bank rows into media-review rows, excluding covered keys."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        name = str(record.get("name") or "").strip()
        key = normalize_exercise_key(name)
        if not key or key in existing_keys or key in seen:
            continue
        seen.add(key)
        block_type = str(
            record.get("category")
            or record.get("type")
            or record.get("modality")
            or ""
        ).strip()
        review_sport, review_context, review_context_required = _bank_review_context(record)
        rows.append(
            {
                "exercise_key": key,
                "family": family_key(name),
                "example_name": name,
                "block_type": block_type,
                "occurrences": "",
                "youtube_url": "",
                "start_s": "",
                "end_s": "",
                "source": "curated",
                "aliases": "",
                "notes": "",
                "review_sport": review_sport,
                "review_context": review_context,
                "review_context_required": review_context_required,
            }
        )
    return rows


def _resolve_bank_path(value: str) -> Path:
    path = Path(value)
    if path.exists():
        return path
    repo_path = _REPO_ROOT / path
    return repo_path if repo_path.exists() else path


def _cmd_bank(args: argparse.Namespace) -> int:
    path = _resolve_bank_path(args.bank_json)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: bank file not found: {args.bank_json}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in {path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, list):
        print(
            f"error: bank JSON must be a top-level list of exercise rows: {path}",
            file=sys.stderr,
        )
        return 2

    existing = _served_media_keys(_build_store())
    rows = bank_rows(payload, existing_keys=existing)
    if args.limit is not None:
        rows = rows[: args.limit]

    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"wrote {len(rows)} uncovered exercises from {path} "
        f"({len(payload)} bank rows, {len(existing)} served keys/aliases) -> {args.out}"
    )
    return 0


def parse_import_row(row: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    """Validate one CSV row into an exercise_media payload (status not yet set)."""
    url = (row.get("youtube_url") or "").strip()
    if not url:
        return None, None
    key = normalize_exercise_key(row.get("exercise_key") or row.get("example_name"))
    if not key:
        return None, "missing exercise_key"
    if len(key) > _MAX_KEY_LENGTH:
        return None, f"exercise_key longer than {_MAX_KEY_LENGTH} characters"
    video_id = parse_youtube_video_id(url)
    if not video_id:
        return None, f"not a YouTube video URL: {url}"
    try:
        start_s = int((row.get("start_s") or "0").strip() or 0)
        end_raw = (row.get("end_s") or "").strip()
        end_s = int(end_raw) if end_raw else None
    except ValueError:
        return None, "start_s / end_s must be whole seconds"
    if start_s < 0 or (end_s is not None and end_s <= start_s):
        return None, "end_s must be after start_s"
    source = (row.get("source") or "curated").strip().lower() or "curated"
    if source not in {"curated", "coach"}:
        return None, f"source must be curated or coach, got {source!r}"
    aliases = sorted(
        {
            alias_key
            for alias in (row.get("aliases") or "").split("|")
            if (alias_key := normalize_exercise_key(alias)) and alias_key != key
        }
    )
    example = normalize_exercise_key(row.get("example_name"))
    if example and example != key and example not in aliases:
        aliases.append(example)
    return (
        {
            "exercise_key": key,
            "aliases": aliases,
            "provider": "youtube",
            "video_id": video_id,
            "start_s": start_s,
            "end_s": end_s,
            "source": source,
            "notes": (row.get("notes") or "").strip()[:500],
        },
        None,
    )


# The Gemini review writes "vertical" / "landscape" (ai_orientation); the
# database stores "portrait" / "landscape".
_REVIEW_ORIENTATIONS = {"vertical": "portrait", "landscape": "landscape"}


def review_orientation(row: dict[str, str], video_id: str) -> str | None:
    """Gemini's orientation for the video being imported, in database terms.

    A fallback only: YouTube's reported dimensions win whenever they exist.
    ai_orientation describes the reviewed video (suggested_url), so it is
    ignored when a curator approved a different one in youtube_url.
    """
    if parse_youtube_video_id(row.get("suggested_url")) != video_id:
        return None
    return _REVIEW_ORIENTATIONS.get((row.get("ai_orientation") or "").strip().lower())


def _cmd_candidates(args: argparse.Namespace) -> int:
    store = _build_store()
    plans_response = (
        store.client.table("plans")
        .select("structured_plan")
        .not_.is_("structured_plan", "null")
        .order("created_at", desc=True)
        .limit(args.plans)
        .execute()
    )
    # Only served rows count as covered: an exercise whose video was retired
    # or never verified comes back as a candidate for re-curation.
    existing = _served_media_keys(store)
    rows = rank_candidates(
        (row.get("structured_plan") for row in plans_response.data or []),
        existing_keys=existing,
        limit=args.limit,
    )
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} candidates from {len(plans_response.data or [])} plans to {args.out}")
    return 0


def alias_conflict(
    payload: dict[str, Any],
    owners: dict[str, str],
) -> str | None:
    """Why this row's key or aliases would take a name another row owns, if so.

    ``owners`` maps every claimed name (key or alias) to the key of the row
    that claims it. The media index lets a primary key beat another row's
    alias and keeps the first of two equal aliases, so either kind of overlap
    would silently send an exercise to the wrong video.
    """
    key = payload["exercise_key"]
    for name in [key, *payload["aliases"]]:
        owner = owners.get(name)
        if owner is not None and owner != key:
            return f"{name} already belongs to {owner}"
    return None


def _claim_names(owners: dict[str, str], key: str, aliases: Iterable[str]) -> None:
    for name in [key, *aliases]:
        owners.setdefault(str(name), key)


def _cmd_import(args: argparse.Namespace) -> int:
    with open(args.csv, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        headers = set(reader.fieldnames or [])
    if "youtube_url" not in headers or not headers & {"exercise_key", "example_name"}:
        print(
            "error: the CSV needs a youtube_url column and an exercise_key or example_name "
            f"column (found: {', '.join(sorted(headers)) or 'none'})",
            file=sys.stderr,
        )
        return 2
    api_key = _require_api_key()
    store = None if args.dry_run else _build_store()
    # Names already taken by stored rows (a dry run has no store, so it only
    # catches overlaps within the CSV). A row re-imported under its own key
    # replaces its old aliases, so its own names are not held against it.
    owners: dict[str, str] = {}
    stored = store.list_exercise_media_for_verification() if store is not None else []
    stored_video: dict[str, str] = {}
    for row in stored:
        _claim_names(owners, str(row.get("exercise_key") or ""), row.get("aliases") or [])
        stored_video[str(row.get("exercise_key") or "")] = str(row.get("video_id") or "")
    rejected = 0
    written = 0
    parsed: list[tuple[int, dict[str, Any]]] = []
    review_fallback: dict[int, str | None] = {}
    for line_no, row in enumerate(rows, start=2):
        payload, error = parse_import_row(row)
        if payload is not None and not error:
            error = alias_conflict(payload, owners)
        if error:
            rejected += 1
            print(f"line {line_no}: rejected - {error}")
        elif payload is not None:
            _claim_names(owners, payload["exercise_key"], payload["aliases"])
            parsed.append((line_no, payload))
            review_fallback[line_no] = review_orientation(row, payload["video_id"])

    with httpx.Client(timeout=YOUTUBE_API_TIMEOUT_SECONDS) as http:
        checks = check_youtube_videos(
            (payload["video_id"] for _, payload in parsed),
            api_key=api_key,
            client=http,
        )
    provider_failures = [
        check for check in checks.values()
        if is_youtube_provider_failure(check)
    ]
    if provider_failures:
        reason = provider_failures[0].reason or "unknown provider failure"
        print(
            f"error: YouTube Data API unavailable during import ({reason}). "
            "No rows were written; retry the same command when the API is available.",
            file=sys.stderr,
        )
        return 2
    for line_no, payload in parsed:
        check = checks[payload["video_id"]]
        if check.status != "ok":
            rejected += 1
            print(f"line {line_no}: {payload['exercise_key']} rejected - {check.reason}")
            continue
        # YouTube's dimensions win; Gemini's answer only fills a gap.
        orientation = check.orientation or review_fallback.get(line_no)
        label = (
            f"{payload['exercise_key']} -> {payload['video_id']} "
            f"({check.title or 'untitled'} / {check.channel_title or 'unknown channel'}"
            f" / {orientation or 'orientation unknown'})"
        )
        if store is None:
            print(f"line {line_no}: ok (dry run) {label}")
            continue
        record = {
            **payload,
            "status": "ok",
            "status_reason": None,
            "made_for_kids": check.made_for_kids,
            "title": check.title,
            "channel_title": check.channel_title,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        # Unknown orientation leaves the column out, so re-importing the same
        # video keeps what is stored. A different video must not inherit the
        # old one's shape, so that case clears it until a sweep detects it.
        if orientation is not None:
            record["orientation"] = orientation
        elif stored_video.get(payload["exercise_key"], payload["video_id"]) != payload["video_id"]:
            record["orientation"] = None
        store.upsert_exercise_media(record)
        written += 1
        print(f"line {line_no}: saved {label}")
    print(f"done: {written} saved, {rejected} rejected")
    return 1 if rejected else 0


def _cmd_verify(_: argparse.Namespace) -> int:
    counts = run_media_verification_sweep(_build_store(), api_key=_require_api_key())
    print(
        f"ok={counts.get('ok', 0)} "
        f"unavailable={counts.get('unavailable', 0)} "
        f"unknown={counts.get('unknown', 0)} "
        f"provider_stopped={counts.get('provider_stopped', 0)}"
    )
    return 2 if counts.get("provider_stopped") else 0


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


COST_SAFE_MAX_CANDIDATES = 3


def _cmd_review_status(args: argparse.Namespace) -> int:
    from tools.exercise_media_review import inspect_checkpoint

    state = inspect_checkpoint(args.csv)
    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print(f"checkpoint: {state['checkpoint']}")
        print(f"review code: {state['review_code']}")
        print(f"checkpoint state: {state['completed']} completed, {state['errors']} errors, {state['pending']} pending (no verdict)")
        print(f"{state['strong']} strong matches; {state['completed'] - state['strong']} weak completed results; all videos require human approval")
        print(f"next eligible exercise: {state['next_exercise_key'] or 'none; normal resume is complete'}")
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    from tools.exercise_media_review import ReviewInputError, build_reviewer, run_review
    from tools.exercise_media_search import CandidateSearchError, build_candidate_search

    out = args.out or args.csv
    # The engine selects and merges checkpoint state while holding its lock.
    searcher = None
    if not args.no_search:
        try:
            searcher = build_candidate_search(
                provider=args.search_provider,
                youtube_api_key=youtube_api_key(),
            )
        except CandidateSearchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if searcher is None:
            print(
                "candidate discovery disabled: install yt-dlp or choose an explicit configured provider."
            )
        else:
            print(f"candidate discovery: {searcher.label}")

    reviewer = build_reviewer(args.model)
    effective_max_candidates = min(args.max_candidates, COST_SAFE_MAX_CANDIDATES)
    if args.max_candidates > COST_SAFE_MAX_CANDIDATES:
        print(
            f"cost guard: capping --max-candidates {args.max_candidates} "
            f"to {COST_SAFE_MAX_CANDIDATES}"
        )
    print(f"Gemini reviewer: {reviewer.model} (agentic video)")
    try:
        counts = run_review(
            args.csv,
            out,
            reviewer=reviewer,
            limit=args.limit,
            redo=args.redo,
            redo_weak=args.redo_weak,
            max_candidates=effective_max_candidates,
            delay_s=args.delay,
            search=searcher.search if searcher else None,
        )
    except ReviewInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        reviewer.close()
        if searcher is not None:
            searcher.close()
    print(
        f"done: {counts['reviewed']} reviewed, {counts['errors']} errors, "
        f"{counts['skipped']} already reviewed -> {out}"
    )
    # Non-zero when any row failed or a provider/quota stop left rows
    # unreviewed, so a script never treats a partial run as complete.
    return 1 if (
        counts["errors"]
        or counts.get("quota_stopped")
        or counts.get("search_stopped")
        or counts.get("gemini_stopped")
    ) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("review-status", help="inspect a reviewed CSV without API calls or CSV changes")
    status.add_argument("csv", help="the reviewed checkpoint CSV")
    status.add_argument("--json", action="store_true", help="print machine-readable checkpoint state")
    status.set_defaults(func=_cmd_review_status)

    candidates = sub.add_parser("candidates", help="export top exercises without a video")
    candidates.add_argument("--limit", type=int, default=100)
    candidates.add_argument("--plans", type=int, default=200, help="recent plans to scan")
    candidates.add_argument("--out", default="exercise_media_candidates.csv")
    candidates.set_defaults(func=_cmd_candidates)

    bank = sub.add_parser("bank", help="export uncovered exercises from a canonical JSON bank")
    bank.add_argument("bank_json", help="bank JSON path, e.g. data/exercise_bank.json")
    bank.add_argument("--out", default="exercise_media_bank.csv")
    bank.add_argument("--limit", type=_positive_int, help="export at most N uncovered bank rows")
    bank.set_defaults(func=_cmd_bank)

    importer = sub.add_parser("import", help="validate and upsert videos from a CSV")
    importer.add_argument("csv")
    importer.add_argument("--dry-run", action="store_true")
    importer.set_defaults(func=_cmd_import)

    review = sub.add_parser("review", help="AI pre-review of suggested videos with Gemini")
    review.add_argument("csv")
    review.add_argument("--out", help="output CSV (default: update the input in place)")
    review.add_argument("--limit", type=int, help="review at most N rows this run")
    review.add_argument("--redo", action="store_true", help="re-review rows that already have a verdict")
    review.add_argument("--redo-weak", action="store_true", help="improve partial, weak, vertical or loopless results with new videos; skip watched IDs")
    review.add_argument("--no-search", action="store_true", help="use supplied URLs only, without candidate discovery")
    review.add_argument(
        "--search-provider",
        choices=("auto", "ytdlp", "dataforseo", "youtube"),
        help=(
            "candidate discovery backend (default: $EXERCISE_MEDIA_SEARCH_PROVIDER or auto; "
            "auto uses yt-dlp direct YouTube search)"
        ),
    )
    review.add_argument(
        "--max-candidates",
        type=_positive_int,
        choices=range(1, 6),
        default=3,
        help="requested Gemini-reviewed videos per exercise; cost guard enforces a maximum of 3 (default: 3)",
    )
    review.add_argument("--delay", type=float, default=4.0, help="seconds between Gemini calls")
    review.add_argument("--model", help="Gemini model (default: $GEMINI_MODEL or gemini-3.5-flash-lite)")
    review.set_defaults(func=_cmd_review)

    verify = sub.add_parser("verify", help="re-check every stored video now")
    verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 - operational failure: exit 2, not 1 (rejected rows)
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
