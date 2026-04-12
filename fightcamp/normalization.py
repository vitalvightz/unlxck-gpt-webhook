"""Shared text normalisation and collection utilities.

This is the single source of truth for helpers that were previously
copy-pasted across stage2_payload, stage2_payload_late_fight,
stage2_repair, stage2_validator, sparring_advisories,
sparring_dose_planner, injury_filtering, and restriction_parsing.

Import from here. Do not redefine locally.
"""
from __future__ import annotations

import re
from typing import Any


# ── String normalisation ──────────────────────────────────────────────────────

def collapse_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_lower_text(value: str | None) -> str:
    return collapse_whitespace(str(value or "").lower())


def strip_surrounding_punctuation(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"^[\W_]+|[\W_]+$", "", str(text).strip())


def normalize_label(label: str | None) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", str(label or "").lower())
    return collapse_whitespace(cleaned)


def normalize_injury_marker(value: str | None) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", str(value or "").lower())
    return collapse_whitespace(cleaned)


def normalize_text(value: str | None) -> str:
    """Lowercase + collapse whitespace. Canonical form of _normalize_text."""
    return normalize_lower_text(value)


def slugify(value: str) -> str:
    """Convert a string to a lowercase underscore slug."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower())
    return cleaned.strip("_") or "slot"


# ── Substring / phrase matching ───────────────────────────────────────────────

def phrase_in_text(text: str, phrase: str) -> bool:
    """Return True if *phrase* appears as a whole token sequence in *text*.

    Case-insensitive. Splits on whitespace and hyphens so 'hip flexor'
    matches 'hip-flexor'.
    """
    if not text or not phrase:
        return False
    parts = [re.escape(p) for p in re.split(r"[\s-]+", phrase.strip().lower()) if p]
    if not parts:
        return False
    pattern = r"\b" + r"[\s-]+".join(parts) + r"\b"
    return re.search(pattern, text.lower()) is not None


# ── Collection helpers ────────────────────────────────────────────────────────

def clean_list(values: Any) -> list[str]:
    """Coerce *values* to a flat list of non-empty stripped strings."""
    if values is None:
        return []
    if isinstance(values, (list, tuple, set)):
        return [str(v).strip() for v in values if str(v).strip()]
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    s = str(values).strip()
    return [s] if s else []


def dedupe_preserve_order(values: list[str]) -> list[str]:
    """Remove duplicates while preserving insertion order."""
    seen: set[str] = set()
    result: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


# ── Private aliases (backwards-compat for in-package callers) ────────────────
# Modules that imported the local private copies will continue to work
# while we migrate them. Remove these once all callers import directly.

_clean_list = clean_list
_normalize_text = normalize_text
_phrase_in_text = phrase_in_text
_slugify = slugify
_dedupe_preserve_order = dedupe_preserve_order


def normalize_text_for_matching(text: str) -> str:
    """Normalize text for injury/pattern matching.

    Strips punctuation and parentheses (unlike normalize_text which preserves
    them). Used by injury_filtering for word-boundary substring matching.
    """
    cleaned = text.lower().replace("-", " ").replace("_", " ")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


# Private alias used by injury_filtering callers
_normalize_text_for_matching = normalize_text_for_matching
