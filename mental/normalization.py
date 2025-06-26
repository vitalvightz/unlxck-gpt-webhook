TAG_NORMALIZATION_MAP = {
    "quick_reset": "fast_reset",
}


def normalize_tag(tag: str) -> str:
    """Return canonical tag for a possibly synonymous input."""
    return TAG_NORMALIZATION_MAP.get(tag, tag)


def normalize_tag_dict(tags):
    """Normalize all tag values within a mapping."""
    normalized = {}
    for key, value in tags.items():
        if isinstance(value, list):
            normalized[key] = [normalize_tag(t) for t in value]
        else:
            normalized[key] = normalize_tag(value)
    return normalized
