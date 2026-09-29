"""Curate exercise demo videos (public.exercise_media).

Requires service-role credentials (the same ones the backend uses):

    SUPABASE_URL=...
    SUPABASE_SERVICE_ROLE_KEY=...

Workflow:
    # 1. Export the most-prescribed exercises that have no video yet.
    python tools/exercise_media.py candidates --limit 100 --out media.csv

    # 2. Fill youtube_url (+ start_s / end_s for the loop segment) in the CSV.

    # 3. Validate every URL through YouTube oEmbed and upsert. Dry-run first.
    python tools/exercise_media.py import media.csv --dry-run
    python tools/exercise_media.py import media.csv

    # Re-check every stored video now (the worker also does this daily).
    python tools/exercise_media.py verify

CSV columns: exercise_key, example_name, block_type, occurrences, youtube_url,
start_s, end_s, source, aliases, notes. Rows without youtube_url are skipped.
aliases is a "|"-separated list of other names that should share the video.

Exit codes: 0 success / 1 some rows rejected / 2 usage or operational error.
"""

from __future__ import annotations

import argparse
import csv
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
    OEMBED_TIMEOUT_SECONDS,
    check_youtube_video,
    normalize_exercise_key,
    parse_youtube_video_id,
    run_media_verification_sweep,
)

CSV_COLUMNS = (
    "exercise_key",
    "example_name",
    "block_type",
    "occurrences",
    "youtube_url",
    "start_s",
    "end_s",
    "source",
    "aliases",
    "notes",
)

# Blocks with nothing to demonstrate on camera.
_NO_DEMO_BLOCK_TYPES = {"mindset", "cooldown_recovery"}


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


def parse_import_row(row: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    """Validate one CSV row into an exercise_media payload (status not yet set)."""
    url = (row.get("youtube_url") or "").strip()
    if not url:
        return None, None
    key = normalize_exercise_key(row.get("exercise_key") or row.get("example_name"))
    if not key:
        return None, "missing exercise_key"
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
    media_response = store.client.table("exercise_media").select("exercise_key,aliases").execute()
    existing: set[str] = set()
    for row in media_response.data or []:
        existing.add(str(row.get("exercise_key") or ""))
        existing.update(str(alias) for alias in row.get("aliases") or [])
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


def _cmd_import(args: argparse.Namespace) -> int:
    with open(args.csv, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    store = None if args.dry_run else _build_store()
    rejected = 0
    written = 0
    with httpx.Client(timeout=OEMBED_TIMEOUT_SECONDS, follow_redirects=True) as http:
        for line_no, row in enumerate(rows, start=2):
            payload, error = parse_import_row(row)
            if error:
                rejected += 1
                print(f"line {line_no}: rejected - {error}")
                continue
            if payload is None:
                continue
            check = check_youtube_video(payload["video_id"], client=http)
            if check.status != "ok":
                rejected += 1
                print(f"line {line_no}: {payload['exercise_key']} rejected - {check.reason}")
                continue
            label = f"{payload['exercise_key']} -> {payload['video_id']} ({check.title or 'untitled'})"
            if store is None:
                print(f"line {line_no}: ok (dry run) {label}")
                continue
            store.upsert_exercise_media(
                {
                    **payload,
                    "status": "ok",
                    "status_reason": None,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            written += 1
            print(f"line {line_no}: saved {label}")
    print(f"done: {written} saved, {rejected} rejected")
    return 1 if rejected else 0


def _cmd_verify(_: argparse.Namespace) -> int:
    counts = run_media_verification_sweep(_build_store())
    print(f"ok={counts.get('ok', 0)} unavailable={counts.get('unavailable', 0)} unknown={counts.get('unknown', 0)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    candidates = sub.add_parser("candidates", help="export top exercises without a video")
    candidates.add_argument("--limit", type=int, default=100)
    candidates.add_argument("--plans", type=int, default=200, help="recent plans to scan")
    candidates.add_argument("--out", default="exercise_media_candidates.csv")
    candidates.set_defaults(func=_cmd_candidates)

    importer = sub.add_parser("import", help="validate and upsert videos from a CSV")
    importer.add_argument("csv")
    importer.add_argument("--dry-run", action="store_true")
    importer.set_defaults(func=_cmd_import)

    verify = sub.add_parser("verify", help="re-check every stored video now")
    verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
