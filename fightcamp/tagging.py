from __future__ import annotations

from typing import Iterable

# Refactored: Import centralized DATA_DIR from config
from .config import DATA_DIR
from .tag_vocabulary import read_tag_vocabulary_items


TAG_SYNONYMS = {
    "muay thai": "muay_thai",
    "muay-thai": "muay_thai",
    "pressure fighter": "pressure_fighter",
    "distance striker": "distance_striker",
    "distance fighter": "distance_striker",
    "distance_fighter": "distance_striker",
    "counter striker": "counter_striker",
    "clinch fighter": "clinch_fighter",
    "clincher": "clinch_fighter",
    "submission hunter": "submission_hunter",
    "skill refinement": "skill_refinement",
    "skill-refinement": "skill_refinement",
    "coordination / proprioception": "coordination",
    "coordination/proprioception": "coordination",
    "quickness": "speed",
    "reactive decision": "reactive",
    "decision speed": "reactive",
    "boxer": "boxing",
    "breathing": "recovery",
    "technical": "skill",
    "rhythm": "coordination",
}

# Structured exercise field names are not semantic tags. Keeping this boundary
# explicit means legacy runtime checks cannot accidentally treat a metadata field
# name placed in an exercise's tags array as authority.
NON_SEMANTIC_TAG_TOKENS = {
    "late_windows",
    "cut_buckets_allowed",
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
        if (
            not canonical
            or canonical in NON_SEMANTIC_TAG_TOKENS
            or canonical in seen
        ):
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
    vocab_path = DATA_DIR / "tag_vocabulary.json"
    if not vocab_path.exists():
        _TAG_VOCAB_CACHE = set()
        return _TAG_VOCAB_CACHE
    vocab = normalize_tags(read_tag_vocabulary_items(vocab_path))
    _TAG_VOCAB_CACHE = set(vocab)
    return _TAG_VOCAB_CACHE
