"""Explicit surface inventory approval; archived bank content is not advice."""
from functools import lru_cache
import hashlib
import json
from collections.abc import Mapping

from .config import DATA_DIR


SURFACE_WOUND_CARE_NOTE = (
    "Skin/surface injury, so no loading rehab is needed. Keep it clean and covered, "
    "avoid friction or contact that could reopen it, and monitor for infection "
    "(spreading redness, heat, swelling, pus, or fever). Do not burst blisters or "
    "remove their skin. Seek medical help for infection, increasing pain or swelling, "
    "bites, punctures, very painful or recurring blisters, or contamination that "
    "remains after rinsing. Get urgent help "
    "for uncontrolled bleeding, deep/gaping wounds, embedded objects, or changes in "
    "feeling, movement or circulation; do not remove embedded objects yourself. "
    "No contact with an open wound or an area that cannot be safely protected. "
    "Covering, low pain or wound closure alone does not clear contact; existing "
    "clinician and contact restrictions still apply."
)
SURFACE_CONTACT_BOUNDARY = " Covering does not clear contact; existing clinician/contact restrictions still apply."


def surface_content_hash(drill: Mapping) -> str:
    text = json.dumps({k: drill.get(k, "") for k in ("name", "notes")},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


@lru_cache(maxsize=1)
def surface_review() -> dict:
    return json.loads((DATA_DIR / "safety" / "surface_wound_review.json").read_text(encoding="utf-8"))


def approved_surface_drill(drill: Mapping) -> bool:
    record = surface_review().get(str(drill.get("id") or ""), {})
    return (record.get("classification") == "SAFE_AS_IS"
            and record.get("content_hash") == surface_content_hash(drill))


def is_surface_inventory_id(identifier: str) -> bool:
    return identifier in surface_review()


@lru_cache(maxsize=1)
def _withdrawn_text() -> tuple[str, ...]:
    # Include phase text for old snapshots that lost their stable identity.
    return tuple(sorted({text.casefold() for identifier, row in surface_review().items()
                         if row["classification"] != "SAFE_AS_IS"
                         for text in [identifier, row["name"], *row["phase_text"]] if text}))


def sanitize_surface_guidance(value):
    """Copy legacy payloads, replacing withdrawn identities AND their saved text.

    No medical inference: this only recognises the exact reviewed inventory.
    Stored history is untouched. Callers hold changed accepted prescriptions.
    """
    if isinstance(value, str):
        return SURFACE_WOUND_CARE_NOTE if any(t in value.casefold() for t in _withdrawn_text()) else value
    if isinstance(value, list):
        return [sanitize_surface_guidance(item) for item in value]
    if isinstance(value, Mapping):
        # Withdraw the entire block, including stale cues, when its identity is
        # withdrawn. Keep occurrence identity, but never its rehab ownership.
        identity_fields = ("rehab_drill_id", "drill_id", "id", "name", "title", "display_name")
        withdrawn = any(isinstance(value.get(k), str) and any(t in value[k].casefold() for t in _withdrawn_text())
                        for k in identity_fields)
        for key in ("rehab_drill_id", "drill_id", "id"):
            identifier = value.get(key)
            if isinstance(identifier, str) and identifier in surface_review():
                # Current source approval overrides old accepted metadata.
                from .rehab_protocols import rehab_drill_by_id
                withdrawn = withdrawn or rehab_drill_by_id(identifier) is None
                if key == "id" and "name" in value and "notes" in value:
                    withdrawn = withdrawn or not approved_surface_drill(value)
        saved_drill = value.get("drill_snapshot")
        if isinstance(saved_drill, Mapping) and is_surface_inventory_id(str(saved_drill.get("id") or "")):
            withdrawn = withdrawn or not approved_surface_drill(saved_drill)
        if withdrawn:
            return {**({"block_id": value["block_id"]} if "block_id" in value else {}),
                    "block_type": "guidance", "title": "Wound care",
                    "instructions": SURFACE_WOUND_CARE_NOTE}
        result = {k: sanitize_surface_guidance(v) for k, v in value.items()}
        if isinstance(result.get("blocks"), list):
            blocks = result["blocks"]
            retained = [b for b in blocks if not (isinstance(b, Mapping) and b.get("block_type") == "guidance"
                                                 and b.get("instructions") == SURFACE_WOUND_CARE_NOTE)]
            if len(retained) != len(blocks):
                result["blocks"] = retained
                result["objective"] = " ".join(filter(None, [result.get("objective"), SURFACE_WOUND_CARE_NOTE]))
        return result
    return value
