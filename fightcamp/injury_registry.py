from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .injury_taxonomy import INJURY_TAXONOMY, derive_injury_type_severity_map


def _normalize_injury_type(injury_type: str | None) -> str:
    return str(injury_type or "").strip().lower().replace("-", "_").replace(" ", "_")


ALL_INJURY_TYPES = frozenset(INJURY_TAXONOMY.keys())
REHAB_SAFE_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if bool(rule.get("rehab_allowed", True)))
REHAB_BLOCKED_TYPES = frozenset(ALL_INJURY_TYPES - REHAB_SAFE_TYPES)
URGENT_INJURY_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if bool(rule.get("urgent")))
CLINICAL_CLEARANCE_TYPES = frozenset(
    k for k, rule in INJURY_TAXONOMY.items() if bool(rule.get("requires_clinical_clearance"))
)
STRUCTURAL_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if str(rule.get("category") or "") == "structural")
SYMPTOM_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if str(rule.get("category") or "") == "symptom")
UNKNOWN_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if str(rule.get("category") or "") == "unknown")
SURFACE_TISSUE_TYPES = frozenset(
    k for k, rule in INJURY_TAXONOMY.items() if str(rule.get("category") or "") == "surface"
)
INJURY_TYPE_SEVERITY = MappingProxyType(derive_injury_type_severity_map())

# Surface skin injuries that get the *calm* train-through note (vs the more
# cautious wound-care note). These are the low-risk skin types where "train
# normally, keep it clean" is the right message. ``cut``/``laceration`` are
# absent here on purpose: they train through too (see
# ``is_stable_train_through_surface_injury``), but their note is the wound-care
# note (infection/reopen warnings), not this calm one. "scrape" is not here
# because the parser canonicalizes scrapes to ``abrasion``. Bruises/contusions
# are not surface skin at all — they are soft-tissue and route normally.
MINOR_SURFACE_TRAIN_THROUGH_TYPES = frozenset(
    {"graze", "abrasion", "blister"}
)

# Calm, coach-facing note for a minor surface (skin) injury that trains through.
# This is deliberately NOT medical-panic language: it treats the athlete as fit
# to train and only asks for basic site protection. Surfaced once by the rehab
# formatter in place of a wound-care drill list, not repeated per drill.
SURFACE_MINOR_TRAIN_THROUGH_NOTE = (
    "Training may continue while the area remains closed, stable and non-infected. "
    "Avoid friction or contact over the site, and stop if it worsens."
)

# Flag markers that pull a surface injury back onto the existing danger gates
# (infection, uncontrolled bleeding, needs-review, worsening, clinical clearance,
# any red flag). If a parsed surface injury carries one of these, it is NOT a
# train-through skin constraint and must keep its normal urgent/red-flag routing.
_SURFACE_TRAIN_THROUGH_RED_FLAG_MARKERS = (
    "red_flag",
    "urgent",
    "review",
    "clearance",
    "infection",
    "infected",
    "suspected",
    "bleed",
    "stitch",
    "worsen",
)


# ---------------------------------------------------------------------------
# Canonical surface-injury classification (single source of truth)
#
# Every consumer — the Today readiness engine, the daily check-in contract, the
# camp-plan train-through gates and the rendering layers — routes a skin injury
# through ``classify_surface_injury``. Duplicating this anywhere else is what let
# an intact blister read as a musculoskeletal injury in one layer and a hygiene
# note in another.
#
# The five classes, weakest to strongest:
#   * ``non_surface``               — not a skin injury; normal injury routing.
#   * ``stable_surface``            — intact, non-severe, no red flag, no session
#                                     conflict. Never changes readiness or dosage.
#   * ``surface_local_restriction`` — worse-but-intact, or friction/contact is the
#                                     problem. Local protection only, when today's
#                                     session actually exposes the area.
#   * ``surface_no_contact``        — open, not safely coverable, or likely to
#                                     reopen. Contact work only is blocked.
#   * ``surface_medical_review``    — infection signs, uncontrolled bleeding,
#                                     drainage, or a severe/red-flagged wound.
#                                     Existing medical-risk rules own the escalation.
# ---------------------------------------------------------------------------

SURFACE_CLASS_NON_SURFACE = "non_surface"
SURFACE_CLASS_STABLE = "stable_surface"
SURFACE_CLASS_LOCAL_RESTRICTION = "surface_local_restriction"
SURFACE_CLASS_NO_CONTACT = "surface_no_contact"
SURFACE_CLASS_MEDICAL_REVIEW = "surface_medical_review"

SURFACE_CLASSES = (
    SURFACE_CLASS_NON_SURFACE,
    SURFACE_CLASS_STABLE,
    SURFACE_CLASS_LOCAL_RESTRICTION,
    SURFACE_CLASS_NO_CONTACT,
    SURFACE_CLASS_MEDICAL_REVIEW,
)

# Strength order, used when several surface injuries are open at once.
SURFACE_CLASS_RANK: dict[str, int] = {
    SURFACE_CLASS_NON_SURFACE: 0,
    SURFACE_CLASS_STABLE: 1,
    SURFACE_CLASS_LOCAL_RESTRICTION: 2,
    SURFACE_CLASS_NO_CONTACT: 3,
    SURFACE_CLASS_MEDICAL_REVIEW: 4,
}

# Structured follow-up vocabulary. Reused verbatim from the guided injury intake
# (``open_wound`` / ``bleeding_status`` / ``infection_signs``) so the daily
# check-in and the guided intake never disagree about what a value means.
SKIN_INTEGRITY_VALUES = frozenset({"intact", "open", "unknown"})
BLEEDING_STATUS_VALUES = frozenset({"none", "controlled", "uncontrolled"})
DRAINAGE_VALUES = frozenset({"none", "present", "unknown"})
COVERABLE_VALUES = frozenset({"yes", "no", "unknown"})
FRICTION_PROBLEM_VALUES = frozenset({"yes", "no", "unknown"})

# ``open_wound`` (guided intake) is a yes/no answer; map it onto skin_integrity.
_OPEN_WOUND_TO_SKIN_INTEGRITY = {
    "yes": "open",
    "true": "open",
    "open": "open",
    "burst": "open",
    "no": "intact",
    "false": "intact",
    "closed": "intact",
    "intact": "intact",
}

# Values that mean "the athlete answered nothing here".
_EMPTY_ANSWERS = frozenset({"", "none", "no", "nil", "n/a", "na", "unknown", "unsure", "not_sure"})


@dataclass(frozen=True)
class SurfaceInjuryAssessment:
    """The canonical routing decision for one injury.

    ``classification`` is authoritative; ``reason`` is a stable machine code (never
    prose to be parsed) naming which rule fired.
    """

    classification: str
    reason: str = ""

    @property
    def is_surface(self) -> bool:
        return self.classification != SURFACE_CLASS_NON_SURFACE

    @property
    def is_stable(self) -> bool:
        return self.classification == SURFACE_CLASS_STABLE

    @property
    def blocks_contact(self) -> bool:
        """True when contact work — and only contact work — is unsafe."""
        return self.classification in {SURFACE_CLASS_NO_CONTACT, SURFACE_CLASS_MEDICAL_REVIEW}

    @property
    def needs_medical_review(self) -> bool:
        return self.classification == SURFACE_CLASS_MEDICAL_REVIEW


def _surface_answer(injury: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = injury.get(name)
        if isinstance(value, bool):
            return "yes" if value else "no"
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text:
            return text
    return ""


def _infection_signs(injury: Mapping[str, Any]) -> list[str]:
    """Reported infection signs, with the "nothing to report" answers removed."""
    raw = injury.get("infection_signs")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return []
    signs: list[str] = []
    for item in raw:
        token = str(item or "").strip().lower().replace("-", "_").replace(" ", "_")
        if token and token not in _EMPTY_ANSWERS:
            signs.append(token)
    return signs


def _surface_flag_red_flag(injury: Mapping[str, Any]) -> bool | None:
    """``True``/``False`` for the legacy ``flags`` red-flag scan; ``None`` if the
    field is malformed (which callers treat as a red flag, never as "clear")."""
    flags = injury.get("flags")
    if isinstance(flags, str):
        flags = [flags]
    elif not isinstance(flags, (list, tuple, set, frozenset)) and flags is not None:
        return None
    for flag in flags or []:
        token = str(flag or "").strip().lower()
        if token and any(marker in token for marker in _SURFACE_TRAIN_THROUGH_RED_FLAG_MARKERS):
            return True
    return False


def _resolved_surface_type(injury: Mapping[str, Any], injury_type: str | None) -> str:
    """Canonical taxonomy type for a possible surface injury, or ``""``.

    ``injury_type`` is the caller's already-resolved type (the Today engine scores
    it from stored text). Otherwise the structured fields are read in order of
    authority, including the guided intake's ``surface_type`` subtype.
    """
    candidates = [injury_type] if injury_type else []
    candidates.extend(
        injury.get(field) for field in ("injury_type", "rehab_type", "surface_type", "guided_surface_type")
    )
    for candidate in candidates:
        normalized = _normalize_injury_type(candidate)
        if normalized in SURFACE_TISSUE_TYPES:
            return normalized
        if normalized in ALL_INJURY_TYPES:
            # A known non-surface type is authoritative: stop before a weaker
            # field (a stray guided subtype) can pull a real injury into the
            # skin path.
            return ""
    return ""


def classify_surface_injury(
    injury: Mapping[str, Any] | None,
    *,
    injury_type: str | None = None,
) -> SurfaceInjuryAssessment:
    """Classify one injury into the canonical surface routing class.

    Deterministic and structured-first: it reads the check-in's follow-up answers
    (``skin_integrity`` / ``open_wound``, ``bleeding_status``, ``drainage``,
    ``infection_signs``, ``coverable``, ``friction_or_contact_problem``) and never
    interprets free text. Anything that is not a taxonomy surface type is
    ``non_surface`` so existing injury routing is untouched.
    """
    if not isinstance(injury, Mapping):
        return SurfaceInjuryAssessment(SURFACE_CLASS_NON_SURFACE, "not_an_injury")

    resolved_type = _resolved_surface_type(injury, injury_type)
    if not resolved_type:
        return SurfaceInjuryAssessment(SURFACE_CLASS_NON_SURFACE, "not_surface_tissue")

    # Severe skin wounds keep their existing review/escalation routing — the
    # caller's severe-injury gates still own the decision.
    severity = str(injury.get("severity") or "").strip().lower()
    if severity in {"high", "severe"}:
        return SurfaceInjuryAssessment(SURFACE_CLASS_MEDICAL_REVIEW, "severe_surface_injury")

    flag_red_flag = _surface_flag_red_flag(injury)
    if flag_red_flag is not False:
        # True (a real red-flag marker) or None (malformed flags) both keep the
        # cautious route; a malformed field is never read as "clear".
        return SurfaceInjuryAssessment(SURFACE_CLASS_MEDICAL_REVIEW, "surface_red_flag")

    if _infection_signs(injury):
        return SurfaceInjuryAssessment(SURFACE_CLASS_MEDICAL_REVIEW, "infection_signs")

    bleeding = _surface_answer(injury, "bleeding_status")
    if bleeding == "uncontrolled":
        return SurfaceInjuryAssessment(SURFACE_CLASS_MEDICAL_REVIEW, "uncontrolled_bleeding")

    drainage = _surface_answer(injury, "drainage")
    if drainage == "present":
        return SurfaceInjuryAssessment(SURFACE_CLASS_MEDICAL_REVIEW, "drainage")

    skin_integrity = _surface_answer(injury, "skin_integrity")
    if skin_integrity not in SKIN_INTEGRITY_VALUES:
        skin_integrity = _OPEN_WOUND_TO_SKIN_INTEGRITY.get(_surface_answer(injury, "open_wound"), "")

    coverable = _surface_answer(injury, "coverable")
    friction_problem = _surface_answer(injury, "friction_or_contact_problem")
    reported_worse = _surface_answer(injury, "latest_reported_status", "reported_status") == "worse"

    if skin_integrity == "open":
        if coverable == "no":
            return SurfaceInjuryAssessment(SURFACE_CLASS_NO_CONTACT, "open_not_coverable")
        return SurfaceInjuryAssessment(SURFACE_CLASS_NO_CONTACT, "open_wound")

    if coverable == "no":
        # It cannot be kept sealed, so contact will reopen or contaminate it.
        return SurfaceInjuryAssessment(SURFACE_CLASS_NO_CONTACT, "not_coverable")

    if reported_worse and skin_integrity != "intact":
        # Marked worse with no structured skin answer: keep contact off it until
        # the follow-up is answered, but never stop the whole session.
        return SurfaceInjuryAssessment(SURFACE_CLASS_NO_CONTACT, "worse_integrity_unknown")

    if friction_problem == "yes":
        return SurfaceInjuryAssessment(SURFACE_CLASS_LOCAL_RESTRICTION, "friction_or_contact_problem")

    if reported_worse:
        return SurfaceInjuryAssessment(SURFACE_CLASS_LOCAL_RESTRICTION, "worse_but_intact")

    return SurfaceInjuryAssessment(SURFACE_CLASS_STABLE, "stable_surface")


def surface_injury_class(
    injury: Mapping[str, Any] | None, *, injury_type: str | None = None
) -> str:
    """The canonical class string for one injury (see ``classify_surface_injury``)."""
    return classify_surface_injury(injury, injury_type=injury_type).classification


def is_stable_surface_only_injury(injury: dict | None) -> bool:
    """True for a stable surface (skin) injury that should train through.

    ANY surface/skin injury — graze, abrasion, blister, cut, or laceration — is
    integumentary, not musculoskeletal. When it is not high severity and carries
    no red-flag signal it is a skin/friction *hygiene* constraint, not injured
    tissue: it must not drive rehab drills, anatomical exercise/region blocking,
    hard-work suppression, or compression. It surfaces only as a single note
    (calm note for graze/abrasion/blister, wound-care note for cut/laceration).

    Returns False (so existing danger gates stay unchanged) for anything that is
    not a surface type, any high/severe surface injury, or a surface injury
    carrying a red-flag / needs-review / clearance / infection / bleeding /
    needs-stitches / worsening flag. Those deep-wound/danger cases keep their
    normal urgent/red-flag routing (and are routed to review upstream).

    Thin wrapper over :func:`classify_surface_injury` so this gate and the Today
    readiness engine can never disagree about what "stable" means.
    """
    return classify_surface_injury(injury).classification == SURFACE_CLASS_STABLE


def is_stable_train_through_surface_injury(injury: dict | None) -> bool:
    """Backward-compatible alias for stable surface-only injury handling."""
    return is_stable_surface_only_injury(injury)


def all_stable_train_through_surface(parsed_injuries) -> bool:
    """True when there is ≥1 parsed injury and every one is a stable, train-through
    surface (skin) injury.

    Used by callers that must decide whether the athlete's *entire* injury picture
    is skin/friction hygiene (no rehab, no load suppression). Requires a non-empty
    list of dicts; a missing, empty, or malformed list returns False so the caller
    keeps normal active-injury handling. A real injury alongside a graze fails this
    check (not every entry qualifies).
    """
    try:
        items = list(parsed_injuries or [])
    except TypeError:
        return False
    if not items or not all(isinstance(item, dict) for item in items):
        return False
    return all(is_stable_surface_only_injury(item) for item in items)


def is_known_injury_type(injury_type: str | None) -> bool:
    return _normalize_injury_type(injury_type) in ALL_INJURY_TYPES


def is_rehab_safe_type(injury_type: str | None) -> bool:
    normalized = _normalize_injury_type(injury_type)
    return normalized in REHAB_SAFE_TYPES


def is_rehab_blocked_type(injury_type: str | None) -> bool:
    normalized = _normalize_injury_type(injury_type)
    return normalized in REHAB_BLOCKED_TYPES


def is_urgent_type(injury_type: str | None) -> bool:
    normalized = _normalize_injury_type(injury_type)
    return normalized in URGENT_INJURY_TYPES


def requires_clinical_clearance_type(injury_type: str | None) -> bool:
    normalized = _normalize_injury_type(injury_type)
    return normalized in CLINICAL_CLEARANCE_TYPES


def get_registry_category(injury_type: str | None) -> str:
    rule = INJURY_TAXONOMY.get(_normalize_injury_type(injury_type)) or INJURY_TAXONOMY["unspecified"]
    return str(rule.get("category") or "unknown")


def get_registry_default_severity(injury_type: str | None) -> str:
    rule = INJURY_TAXONOMY.get(_normalize_injury_type(injury_type)) or INJURY_TAXONOMY["unspecified"]
    return str(rule.get("default_severity") or "moderate")
