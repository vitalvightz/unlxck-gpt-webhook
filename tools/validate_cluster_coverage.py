#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.cluster_coverage import validate_cluster_manifest_coverage


def main() -> int:
    errors = validate_cluster_manifest_coverage()
    if errors:
        print("Cluster coverage validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Cluster coverage validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())