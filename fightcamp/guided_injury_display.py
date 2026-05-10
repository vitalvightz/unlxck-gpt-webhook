from __future__ import annotations

import re
from typing import Mapping

_GUIDED_LATERALITY_PREFIX = re.compile(r"^\s*(left|right)\s+", re.IGNORECASE)
_GUIDED_DISPLAY_MECHANISM_PATTERN = re.compile(
    r"""\b(
        hyperextend(?:ed|s|ing)?|hyperextension|rolled|twisted|sprain(?:ed)?|strain(?:ed)?|pulled|
        pain|sore|soreness|tight|tightness|swollen|swelling|inflamed|inflammation|stiff|stiffness|
        achy|aching|tendonitis|tendinitis|tendinopathy|impingement|instability|unstable|
        rupture|tear|torn|bruise(?:d)?|cut|laceration|graze|abrasion|blister|
        dislocated|fracture|broken|popped|snapped|give\s+way|giving\s+way|gave\s+way|
        locked\s+out|locked\s+back|overextend(?:ed|s|ing)?|overextension|overstretch(?:ed|ing)?
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)


def strip_guided_laterality(area: str, laterality: str | None) -> str:
    cleaned = str(area or "").strip()
    if not cleaned or not laterality:
        return cleaned
    return _GUIDED_LATERALITY_PREFIX.sub("", cleaned, count=1).strip() or cleaned


def is_clean_guided_display_location(area: str, injury_entry: Mapping[str, object]) -> bool:
    normalized_area = str(area or "").strip().lower()
    if not normalized_area:
        return False

    resolved_injury_type = str(injury_entry.get("injury_type") or "").strip().lower().replace("_", " ")
    if (
        resolved_injury_type
        and resolved_injury_type != "unspecified"
        and re.search(rf"\b{re.escape(resolved_injury_type)}\b", normalized_area)
    ):
        return False

    if _GUIDED_DISPLAY_MECHANISM_PATTERN.search(normalized_area):
        return False

    return True
