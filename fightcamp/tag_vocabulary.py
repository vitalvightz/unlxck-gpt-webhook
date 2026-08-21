from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_tag_vocabulary_payload(data: Any) -> list[str]:
    """Return validated raw tag strings from supported vocabulary schemas."""
    items: Any = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("items", "data"):
            if isinstance(data.get(key), list):
                items = data[key]
                break

    if (
        not isinstance(items, list)
        or not items
        or any(not isinstance(tag, str) or not tag.strip() for tag in items)
    ):
        raise ValueError(
            "tag vocabulary must be a non-empty list of strings "
            "or an object containing an 'items'/'data' string list"
        )

    return [tag.strip() for tag in items]


def read_tag_vocabulary_items(path: Path) -> list[str]:
    """Read and validate tag_vocabulary.json without canonicalizing aliases."""
    return parse_tag_vocabulary_payload(
        json.loads(path.read_text(encoding="utf-8"))
    )
