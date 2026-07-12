"""Idempotent screenshot retention and account-deletion cleanup.

Run scheduled retention with ``python -m api.feedback_retention``.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

from api.store import AppStore, SupabaseAppStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupResult:
    deleted: int = 0
    failed: int = 0


def _purge_rows(store: AppStore, rows: list[dict]) -> CleanupResult:
    deleted = 0
    failed = 0
    for row in rows:
        feedback_id = str(row.get("id") or "")
        path = str(row.get("screenshot_path") or "")
        if not feedback_id or not path:
            continue
        try:
            store.delete_feedback_screenshots([path])
            if store.clear_feedback_screenshot(feedback_id, path):
                deleted += 1
                logger.info(
                    "[feedback_cleanup] success feedback_id=%s operation=delete_and_clear",
                    feedback_id,
                )
            else:
                failed += 1
                logger.warning(
                    "[feedback_cleanup] failed feedback_id=%s operation=clear_reference",
                    feedback_id,
                )
        except Exception as exc:
            failed += 1
            logger.error(
                "[feedback_cleanup] failed feedback_id=%s operation=delete_object error_class=%s",
                feedback_id,
                type(exc).__name__,
            )
    return CleanupResult(deleted=deleted, failed=failed)


def cleanup_expired_screenshots(store: AppStore, *, batch_size: int = 100) -> CleanupResult:
    rows = store.list_expired_feedback_screenshots(limit=max(1, min(batch_size, 500)))
    return _purge_rows(store, rows)


def cleanup_profile_screenshots(
    store: AppStore,
    profile_id: str,
    *,
    batch_size: int = 100,
) -> CleanupResult:
    total = CleanupResult()
    while True:
        rows = store.list_profile_feedback_screenshots(profile_id, limit=max(1, min(batch_size, 500)))
        if not rows:
            return total
        result = _purge_rows(store, rows)
        total = CleanupResult(
            deleted=total.deleted + result.deleted,
            failed=total.failed + result.failed,
        )
        if result.failed or not result.deleted:
            return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete expired beta-feedback screenshots")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args(argv)
    store = SupabaseAppStore.from_env()
    try:
        result = cleanup_expired_screenshots(store, batch_size=args.batch_size)
    except Exception as exc:
        logger.error(
            "[feedback_cleanup] failed operation=list_expired error_class=%s",
            type(exc).__name__,
        )
        return 1
    logger.info(
        "[feedback_cleanup] complete operation=retention deleted=%s failed=%s",
        result.deleted,
        result.failed,
    )
    return 1 if result.failed else 0


if __name__ == "__main__":  # pragma: no cover - exercised operationally
    raise SystemExit(main())
