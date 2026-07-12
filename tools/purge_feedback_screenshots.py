"""Purge a profile's feedback screenshots before existing account deletion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.feedback_retention import cleanup_profile_screenshots  # noqa: E402
from api.store import SupabaseAppStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("--confirm is required")
    try:
        result = cleanup_profile_screenshots(SupabaseAppStore.from_env(), args.profile_id)
    except Exception as exc:
        print(f"cleanup failed: {type(exc).__name__}")
        return 1
    print(f"deleted={result.deleted} failed={result.failed}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
