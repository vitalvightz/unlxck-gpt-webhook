from __future__ import annotations

import re


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
