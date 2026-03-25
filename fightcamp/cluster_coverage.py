from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .config import DATA_DIR

_CLUSTER_MANIFEST_CACHE: list[dict] | None = None


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def get_cluster_coverage_manifest() -> list[dict]:
    global _CLUSTER_MANIFEST_CACHE
    if _CLUSTER_MANIFEST_CACHE is None:
        path = DATA_DIR / "cluster_coverage_manifest.json"
        _CLUSTER_MANIFEST_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return _CLUSTER_MANIFEST_CACHE


def active_cluster_rows(
    *,
    sport: str,
    goal_keys: Iterable[str],
    weakness_keys: Iterable[str],
    style_keys: Iterable[str],
) -> list[dict]:
    goal_set = set(_dedupe_preserve_order(goal_keys))
    weakness_set = set(_dedupe_preserve_order(weakness_keys))
    style_set = set(_dedupe_preserve_order(style_keys))
    normalized_sport = str(sport or "").strip().lower()
    matched: list[dict] = []
    for row in get_cluster_coverage_manifest():
        sports = {str(value).strip().lower() for value in row.get("sports", []) if str(value).strip()}
        if sports and normalized_sport not in sports:
            continue
        if not set(row.get("goal_keys", [])) <= goal_set:
            continue
        if not set(row.get("weakness_keys", [])) <= weakness_set:
            continue
        style_requirements = set(row.get("style_keys", []))
        if style_requirements and not style_requirements <= style_set:
            continue
        matched.append(row)
    return matched


def active_cluster_ids(
    *,
    sport: str,
    goal_keys: Iterable[str],
    weakness_keys: Iterable[str],
    style_keys: Iterable[str],
) -> list[str]:
    return _dedupe_preserve_order(
        row.get("cluster_id", "")
        for row in active_cluster_rows(
            sport=sport,
            goal_keys=goal_keys,
            weakness_keys=weakness_keys,
            style_keys=style_keys,
        )
    )


def validate_cluster_manifest_coverage(*, data_dir: Path | None = None) -> list[str]:
    root = data_dir or DATA_DIR
    manifest = get_cluster_coverage_manifest()
    bank_paths = [
        root / "exercise_bank.json",
        root / "conditioning_bank.json",
        root / "style_conditioning_bank.json",
        root / "coordination_bank.json",
        root / "rehab_bank.json",
    ]
    coverage_by_cluster: dict[str, set[str]] = {}
    for path in bank_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items: list[dict] = []
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    items.extend(value)
        for item in items:
            cluster_ids = [str(value).strip() for value in item.get("cluster_ids", []) if str(value).strip()]
            categories = {
                str(value).strip()
                for value in item.get("coverage_categories", [])
                if str(value).strip()
            }
            for cluster_id in cluster_ids:
                coverage_by_cluster.setdefault(cluster_id, set()).update(categories)

    errors: list[str] = []
    seen_cluster_ids: set[str] = set()
    valid_cluster_types = {"repeatability", "balance_transfer", "rehab_return", "style_completion"}
    for row in manifest:
        cluster_id = str(row.get("cluster_id", "")).strip()
        if not cluster_id:
            errors.append("Manifest row missing cluster_id.")
            continue
        if cluster_id in seen_cluster_ids:
            errors.append(f"Duplicate cluster_id '{cluster_id}'.")
            continue
        seen_cluster_ids.add(cluster_id)
        cluster_type = str(row.get("cluster_type", "")).strip()
        if cluster_type not in valid_cluster_types:
            errors.append(f"Cluster '{cluster_id}' has invalid cluster_type '{cluster_type}'.")
        mandatory = set(row.get("mandatory_categories", []))
        forbidden = set(row.get("forbidden_categories", []))
        present = coverage_by_cluster.get(cluster_id, set())
        missing = mandatory - present
        if missing:
            errors.append(
                f"Cluster '{cluster_id}' is missing mandatory coverage categories: {sorted(missing)}."
            )
        present_forbidden = forbidden & present
        if present_forbidden:
            errors.append(
                f"Cluster '{cluster_id}' includes forbidden coverage categories: {sorted(present_forbidden)}."
            )
        if row.get("rehab_required") and not {"rehab_progression", "return_bridge"} <= present:
            errors.append(
                f"Cluster '{cluster_id}' requires rehab coverage but is missing rehab_progression or return_bridge."
            )
    orphan_cluster_ids = set(coverage_by_cluster.keys()) - seen_cluster_ids
    for orphan_id in sorted(orphan_cluster_ids):
        errors.append(
            f"Bank entry references cluster_id '{orphan_id}' which has no manifest row (orphan)."
        )
    return errors
