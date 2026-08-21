from __future__ import annotations

from collections.abc import Iterable

from fightcamp.injury_filtering import (
    AUTO_TAG_RULES,
    INFERRED_TAG_RULES,
    INJURY_TAG_ALIASES,
    MECH_KEYWORDS,
)
from fightcamp.tagging import normalize_tag


def _canonical(values: Iterable[str]) -> set[str]:
    tags: set[str] = set()
    for value in values:
        canonical = normalize_tag(value)
        if canonical:
            tags.add(canonical)
    return tags


def collect_generated_injury_tags() -> set[str]:
    """Return every tag the injury inference/expansion layer can emit or expand."""
    raw: set[str] = {tag for tag, _keywords in MECH_KEYWORDS}

    for rule in (*INFERRED_TAG_RULES, *AUTO_TAG_RULES):
        values = rule.get("tags") or []
        raw.update(str(value) for value in values if str(value).strip())

    # Keys are source tags that participate in the expansion contract; values are
    # the safety tags the injury matcher can add to an exercise.
    for source_tag, expanded in INJURY_TAG_ALIASES.items():
        raw.add(str(source_tag))
        raw.update(str(value) for value in expanded if str(value).strip())

    return _canonical(raw)
