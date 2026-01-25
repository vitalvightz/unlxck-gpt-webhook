from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable
# Refactored: Import centralized DATA_DIR from config
from .config import DATA_DIR


TAG_SYNONYMS = {
    "muay thai": "muay_thai",
    "muay-thai": "muay_thai",
    "pressure fighter": "pressure_fighter",
    "distance striker": "distance_striker",
    "counter striker": "counter_striker",
    "clinch fighter": "clinch_fighter",
    "submission hunter": "submission_hunter",
    "skill refinement": "skill_refinement",
    "skill-refinement": "skill_refinement",
    "coordination / proprioception": "coordination",
    "coordination/proprioception": "coordination",
    "reactive decision": "reactive_decision",
    "decision speed": "decision_speed",
}

_TAG_VOCAB_CACHE: set[str] | None = None


def normalize_tag(tag: str) -> str | None:
    if not tag:
        return None
    raw = str(tag).strip().lower()
    if not raw:
        return None
    canonical = TAG_SYNONYMS.get(raw)
    if canonical:
        return canonical
    normalized = raw.replace("-", "_").replace(" ", "_")
    return TAG_SYNONYMS.get(normalized, normalized)


def normalize_tags(tags: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        canonical = normalize_tag(tag)
        if not canonical or canonical in seen:
            continue
        normalized.append(canonical)
        seen.add(canonical)
    return normalized


def normalize_item_tags(item: dict) -> list[str]:
    tags = item.get("tags", [])
    normalized = normalize_tags(tags)
    item["tags"] = normalized
    return normalized


def load_tag_vocabulary() -> set[str]:
    global _TAG_VOCAB_CACHE
    if _TAG_VOCAB_CACHE is not None:
        return _TAG_VOCAB_CACHE
    # Refactored: Use centralized DATA_DIR instead of recomputing
    vocab_path = DATA_DIR / "tag_vocabulary.json"
    if not vocab_path.exists():
        _TAG_VOCAB_CACHE = set()
        return _TAG_VOCAB_CACHE
    vocab = normalize_tags(json.loads(vocab_path.read_text()))
    _TAG_VOCAB_CACHE = set(vocab)
    return _TAG_VOCAB_CACHE
