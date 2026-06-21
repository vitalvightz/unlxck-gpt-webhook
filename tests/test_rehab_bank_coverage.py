from __future__ import annotations

from fightcamp.injury_scoring import CANONICAL_TYPES
from fightcamp.rehab_protocols import get_rehab_bank


REHAB_COVERAGE_EXCEPTIONS = {
    "fracture": "restricted_rehab_or_medical_hold",
    "dislocation": "restricted_rehab_or_medical_hold",
    "concussion": "medical_hold",
    "suspected_concussion": "medical_hold",
    "tendon_rupture_or_avulsion": "restricted_rehab_or_medical_hold",
    "complete_ligament_tear": "restricted_rehab_or_medical_hold",
    "acl_tear": "restricted_rehab_or_medical_hold",
    "pneumothorax": "medical_hold",
    "hemothorax": "medical_hold",
    "septic_joint_or_bone_infection": "medical_hold",
    # NOTE: surface injuries (cut/laceration/abrasion/graze/blister) now carry
    # their own wound-care entries in the rehab bank, so they are covered
    # directly and no longer need an exception here.
}

GENERIC_REHAB_FALLBACK_TYPES = {"unspecified"}


def test_parser_injury_types_have_rehab_coverage_or_explicit_exception():
    rehab_types = {
        str(entry.get("type") or "").strip().lower()
        for entry in get_rehab_bank()
        if isinstance(entry, dict) and str(entry.get("type") or "").strip()
    }
    parser_types = {t.strip().lower() for t in CANONICAL_TYPES if t.strip()}

    uncovered = sorted(
        injury_type
        for injury_type in parser_types
        if injury_type not in rehab_types
        and injury_type not in REHAB_COVERAGE_EXCEPTIONS
        and injury_type not in GENERIC_REHAB_FALLBACK_TYPES
    )
    assert not uncovered, f"Parser injury types missing rehab coverage/exception: {uncovered}"
