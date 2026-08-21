#!/usr/bin/env python3
"""Shared, deterministic primitives for the rehab clinical-metadata review pipeline.

One canonical home for the pieces the generator, applicator, validator and
coverage reporter all need, so the movement-archetype vocabulary, the source
hash, the conservative auto-proposal rules and the variable-demand flags can
never drift between tools.

Design invariants
-----------------
* ``null`` means "not clinically migrated yet"; ``"unknown"`` means "reviewed
  and could not be defensibly classified". This module never turns one into the
  other, and never turns either into a low/none/safe claim.
* Automated proposals are *candidates*, not truth. They use only mechanical
  facts that hold for every variant of an archetype (a static hold has no
  impact and no velocity, by definition). Anything ambiguous — load level, exact
  impact of a jump, rehab stage, severities, dose, clinical rules — is left
  ``null`` for a human reviewer. Honest incompleteness beats fabricated
  precision.
* Everything here is pure and deterministic: same bank in, byte-identical
  ledger out.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator, Mapping

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.rehab_schema import (  # noqa: E402
    CARE_TYPE_WOUND_CARE,
    care_type_for_injury_type,
)

DEFAULT_BANK = REPO_ROOT / "data" / "rehab_bank.json"
DEFAULT_LEDGER = REPO_ROOT / "data" / "rehab_metadata_review.json"

LEDGER_VERSION = 1

# Review provenance is owned by the ledger, never inferred from the bank: the
# schema migration already wrote "unknown" into several fields without a human
# ever reviewing them, so a bank value proves nothing about review.
REVIEW_STATE_NEEDS_REVIEW = "needs_review"
REVIEW_STATE_REVIEWED = "reviewed"
REVIEW_STATES: tuple[str, ...] = (REVIEW_STATE_NEEDS_REVIEW, REVIEW_STATE_REVIEWED)
#: Derived, never stored: a reviewed record whose source hash no longer matches
#: the drill it was reviewed against. Reported by the reporter and honoured by
#: the applicator (a stale review is not applied).
REVIEW_STATE_STALE = "stale"

# ---------------------------------------------------------------------------
# Movement archetypes — the one canonical vocabulary
# ---------------------------------------------------------------------------

MOVEMENT_ARCHETYPES: tuple[str, ...] = (
    "mobility_rom",
    "manual_recovery",
    "isometric",
    "activation",
    "balance_control",
    "banded_resistance",
    "bodyweight_strength",
    "external_load_strength",
    "eccentric_loading",
    "locomotion",
    "hop_jump_landing",
    "change_of_direction",
    "combat_specific_non_contact",
    "controlled_contact",
    "full_sport_demand",
    "unknown",
)

# The clinical fields the review ledger proposes / applies. Deliberately excludes
# the high-risk prescription fields (dose, pain_ceiling, allowed_severities,
# progress_when, regress_when, stop_when) — those belong to a later clinical
# criteria PR, not this mechanical-classification pipeline.
REVIEW_FIELDS: tuple[str, ...] = (
    "rehab_stage",
    "function",
    "equipment",
    "impact",
    "load",
    "velocity",
    "target_regions",
    "laterality_applicability",
    "target_tissues",
    "contraction_type",
    "sport_specificity",
    "contact_level",
    "evidence_notes",
)

# Variable-demand flag reason codes (stable).
FLAG_VARIABLE_DEMAND = "VARIABLE_DEMAND_PROGRESSION"
FLAG_LOAD_PROGRESSION = "LOAD_PROGRESSION_IN_NOTES"
FLAG_SPEED_PROGRESSION = "SPEED_PROGRESSION_IN_NOTES"
FLAG_IMPACT_PROGRESSION = "IMPACT_PROGRESSION_IN_NOTES"
FLAG_CONTACT_PROGRESSION = "CONTACT_PROGRESSION_IN_NOTES"
FLAG_POSSIBLE_DRILL_SPLIT = "POSSIBLE_DRILL_SPLIT"
FLAG_CODES: tuple[str, ...] = (
    FLAG_VARIABLE_DEMAND,
    FLAG_LOAD_PROGRESSION,
    FLAG_SPEED_PROGRESSION,
    FLAG_IMPACT_PROGRESSION,
    FLAG_CONTACT_PROGRESSION,
    FLAG_POSSIBLE_DRILL_SPLIT,
)


def _text(value: Any) -> str:
    return str(value or "").lower()


# Ordered most-specific / highest-demand first: the first match wins, so a
# "single-leg hop" is a hop, not a balance drill. Each entry is (archetype,
# word-boundary keyword patterns).
_ARCHETYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("full_sport_demand", ("sparring", "spar ", "live round", "full contact", "full-contact", "fight simulation")),
    ("controlled_contact", ("controlled contact", "partner contact", "controlled clinch", "wrestling control", "takedown control")),
    ("combat_specific_non_contact", ("shadow", "pad work", "padwork", "focus mitt", "bag work", "bagwork", "heavy bag", "striking drill")),
    ("hop_jump_landing", ("hop", "jump", "bound", "plyo", "depth drop", "depth jump", "landing", "pogo", "leap", "skater")),
    ("change_of_direction", ("change of direction", "cutting", "cut and", "agility", "zig-zag", "zigzag", "shuttle", "lateral shuffle", "carioca")),
    ("locomotion", ("walk", "jog", "run", "march", "gait", "sprint", "tread", "cycling", "cycle", "rowing", "row erg", "swim", "sled")),
    ("eccentric_loading", ("eccentric", "negative", "slow lower", "tempo lower", "lowering phase", "controlled lower")),
    ("external_load_strength", ("barbell", "dumbbell", "kettlebell", "weighted", "loaded carry", "cable", "machine", "plate", "external load", "goblet", "trap bar")),
    ("banded_resistance", ("band", "banded", "theraband", "resistance band", "monster walk")),
    ("isometric", ("isometric", "iso hold", "iso-hold", " hold", "wall sit", "plank", "static hold", "isometrics")),
    ("activation", ("activation", "activate", "clam", "clamshell", "glute bridge", "bird dog", "dead bug", "wake up", "priming")),
    ("balance_control", ("balance", "propriocept", "stability", "single-leg stance", "single leg stance", "tandem stance", "foam pad", "bosu", "wobble", "control")),
    ("manual_recovery", ("massage", "foam roll", "foam-roll", "soft tissue", "self-release", "trigger point", "mobilisation", "mobilization", "manual therapy", "compression")),
    ("mobility_rom", ("mobility", "stretch", "range of motion", "rom ", "circles", "rotation", "flexion", "extension", "glide", "mobilise", "mobilize", "cars", "dynamic stretch", "opener")),
)

# Archetypes whose mechanical demand is non-impact and low-velocity for every
# variant: a static hold, a passive stretch, a massage, a bodyweight activation
# or a static balance never involve ground impact or fast movement. These are
# the only impact/velocity values this module proposes automatically.
_STATIC_NON_IMPACT = frozenset(
    {"mobility_rom", "manual_recovery", "isometric", "activation", "balance_control"}
)
# Non-contact by nature (general rehab), so a contact_level of "none" is a
# mechanical fact, not a clinical judgement.
_NON_CONTACT_REHAB = _STATIC_NON_IMPACT | frozenset(
    {"banded_resistance", "bodyweight_strength", "external_load_strength", "eccentric_loading"}
)


def classify_movement_archetype(name: Any, notes: Any) -> str:
    """Deterministically classify a drill's movement archetype, or ``"unknown"``.

    Keyword-based and conservative: no match means ``"unknown"`` rather than a
    forced guess. Used only to seed *proposals*, which a human then reviews.
    """
    text = f" {_text(name)} {_text(notes)} "
    text = text.replace("-", " ")
    for archetype, patterns in _ARCHETYPE_PATTERNS:
        for pattern in patterns:
            if pattern.replace("-", " ") in text:
                return archetype
    return "unknown"


_LOAD_CUES = ("add load", "add resistance", "increase load", "increase resistance",
              "add weight", "heavier", "progress load", "load progression", "progressively load")
_SPEED_CUES = ("increase speed", "faster", "add speed", "speed progression",
               "accelerate", "explosive progression", "under fatigue", "at speed")
_IMPACT_CUES = ("hop", "jump", "bound", "plyo", "add impact", "landing", "pogo", "leap")
_CONTACT_CUES = ("progress to contact", "add contact", "progress to striking",
                 "progress to sparring", "controlled contact", "clinch progression",
                 "partner resistance", "progress to partner")

_PHASE_ARROW_RE = re.compile(r"→|->|â†’")


def detect_variable_demand_flags(notes: Any) -> list[str]:
    """Flag notes that appear to describe several mechanical exposures at once.

    A flag never means "split this drill". It means the entry's mechanical
    demand is not a single value and must be reviewed (and possibly split)
    before its metadata can be trusted. Deterministic and stable.
    """
    text = _text(notes)
    flags: list[str] = []
    cue_hits = 0
    if any(cue in text for cue in _LOAD_CUES):
        flags.append(FLAG_LOAD_PROGRESSION)
        cue_hits += 1
    if any(cue in text for cue in _SPEED_CUES):
        flags.append(FLAG_SPEED_PROGRESSION)
        cue_hits += 1
    if any(cue in text for cue in _IMPACT_CUES):
        flags.append(FLAG_IMPACT_PROGRESSION)
        cue_hits += 1
    if any(cue in text for cue in _CONTACT_CUES):
        flags.append(FLAG_CONTACT_PROGRESSION)
        cue_hits += 1

    has_phase_arrow = bool(_PHASE_ARROW_RE.search(str(notes or "")))
    # Materially different exposures hidden behind one identity: a phase arrow
    # that carries a mechanical-demand change, or two different demand changes.
    if (has_phase_arrow and cue_hits >= 1) or cue_hits >= 2:
        flags.append(FLAG_VARIABLE_DEMAND)
    # A phase arrow crossing a load/impact/contact change is the strongest
    # "this may really be two drills" signal.
    strong = {FLAG_LOAD_PROGRESSION, FLAG_IMPACT_PROGRESSION, FLAG_CONTACT_PROGRESSION}
    if has_phase_arrow and strong.intersection(flags):
        flags.append(FLAG_POSSIBLE_DRILL_SPLIT)
    # Stable order, de-duplicated.
    return [code for code in FLAG_CODES if code in flags]


def _laterality_from_name(name: Any) -> str | None:
    text = _text(name).replace("-", " ")
    if any(token in text for token in ("single leg", "one leg", "single arm", "one arm", "single-sided", "unilateral")):
        return "side_specific"
    if any(token in text for token in ("bilateral", "double leg", "both legs", "both arms")):
        return "bilateral_only"
    return None


def propose_metadata(
    *,
    archetype: str,
    name: Any,
    location: str,
    drill: Mapping[str, Any],
) -> dict[str, Any]:
    """Conservative candidate classifications from mechanical facts only.

    Every field defaults to ``null`` (a reviewer must classify it). Only values
    that hold for every variant of the archetype are proposed:

    * impact/velocity for archetypes that are static and non-impact by nature;
    * contraction_type for isometric / eccentric archetypes;
    * contact_level and sport_specificity where the archetype fixes them;
    * laterality where the drill name states single- or bilateral execution;
    * target_regions inherited from the canonical group (already the bank's own
      convention), and the existing keyword ``function`` preserved.

    Ambiguous, high-stakes fields — ``load``, ``rehab_stage``, dose, severities,
    clinical rules — are never guessed here.
    """
    proposed: dict[str, Any] = {field: None for field in REVIEW_FIELDS}

    # Region identity is the bank's existing convention (group owns the region).
    existing_regions = drill.get("target_regions")
    if isinstance(existing_regions, list) and existing_regions:
        proposed["target_regions"] = list(existing_regions)
    elif location:
        proposed["target_regions"] = [location]

    # Preserve an already-derived keyword function rather than re-deriving it.
    if isinstance(drill.get("function"), str) and drill.get("function"):
        proposed["function"] = drill["function"]

    if archetype in _STATIC_NON_IMPACT:
        proposed["impact"] = "none"
        proposed["velocity"] = "low"
    if archetype == "isometric":
        proposed["contraction_type"] = "isometric"
    elif archetype == "eccentric_loading":
        proposed["contraction_type"] = "eccentric"

    if archetype in _NON_CONTACT_REHAB:
        proposed["contact_level"] = "none"
        proposed["sport_specificity"] = "general_rehab"
    elif archetype == "combat_specific_non_contact":
        proposed["contact_level"] = "none"
        proposed["sport_specificity"] = "combat_sport"
    elif archetype == "controlled_contact":
        proposed["contact_level"] = "controlled"
        proposed["sport_specificity"] = "combat_sport"
    elif archetype == "full_sport_demand":
        proposed["contact_level"] = "full"
        proposed["sport_specificity"] = "combat_sport"

    laterality = _laterality_from_name(name)
    if laterality is not None:
        proposed["laterality_applicability"] = laterality

    return proposed


# ---------------------------------------------------------------------------
# Source hash and bank iteration
# ---------------------------------------------------------------------------


def source_hash(*, drill_id: str, location: str, injury_type: str, name: Any, notes: Any) -> str:
    """Deterministic hash of the clinically-relevant source identity of a drill.

    If any of these change, a prior review is no longer trustworthy: the hash
    changes, and the applicator treats the review as stale rather than applying
    it against different source material.
    """
    payload = json.dumps(
        {
            "drill_id": str(drill_id),
            "location": str(location),
            "injury_type": str(injury_type),
            "name": str(name or ""),
            "notes": str(notes or ""),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_bank(path: Path = DEFAULT_BANK) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_bank(entries: list[dict]) -> str:
    """Match the byte formatting the migration tool writes."""
    return json.dumps(entries, indent=2, ensure_ascii=False) + "\n"


def render_ledger(records: list[dict]) -> str:
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def load_ledger(path: Path = DEFAULT_LEDGER) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def is_surface_group(injury_type: Any) -> bool:
    return care_type_for_injury_type(str(injury_type or "")) == CARE_TYPE_WOUND_CARE


def iter_msk_drills(entries: list[dict]) -> Iterator[tuple[int, int, str, str, dict]]:
    """Yield ``(group_index, drill_index, location, injury_type, drill)`` for MSK only.

    Surface / wound-care groups are integumentary and never enter the loading
    pathway, so they are skipped entirely.
    """
    for group_index, entry in enumerate(entries):
        injury_type = str(entry.get("type") or "")
        if is_surface_group(injury_type):
            continue
        location = str(entry.get("location") or "")
        for drill_index, drill in enumerate(entry.get("drills", [])):
            if isinstance(drill, dict):
                yield group_index, drill_index, location, injury_type, drill
