"""Daily injury check-in reconciliation (Block 4 §6 follow-up).

The Today check-in carries a single ``active_injury`` flag (none/stable/worse).
That can't say *which* injury, and it can't tell a resolved injury from a brand
new one. This contract reconciles the athlete's declared injuries for a training
day against their existing open ``injury_flags`` so every injury keeps identity
over time:

* a report with no ``flag_id`` opens a new flag,
* an ``improving`` report parks the flag in ``monitoring``,
* a ``resolved`` report closes it (``resolved``), and
* an ``ongoing`` / ``worse`` report keeps it ``open`` (severity may change).

Pure and deterministic: this computes the create/update plan; the service
applies it to storage and stamps ``resolved_at``. Capturing per-injury state now
is exactly what lets a later PR make plans dynamic when an injury clears or a new
one appears — this PR only persists it and feeds the risk watch.
"""

from __future__ import annotations

import re
from typing import Iterable, Literal, Mapping, Sequence

from pydantic import BaseModel, Field, model_validator

from .command_view import RiskWatchItem, make_risk

InjuryFlagSeverity = Literal["mild", "moderate", "severe"]
InjuryFlagStatus = Literal["open", "monitoring", "resolved"]
# What the athlete reports about an injury on a given day.
InjuryCheckinStatus = Literal["ongoing", "improving", "worse", "resolved"]

# Reported day-state -> persisted flag status. "improving" parks the flag in
# monitoring; "resolved" closes it; "ongoing"/"worse" keep it open.
_FLAG_STATUS_BY_REPORT: dict[str, InjuryFlagStatus] = {
    "ongoing": "open",
    "worse": "open",
    "improving": "monitoring",
    "resolved": "resolved",
}

# Open/active statuses for risk-watch purposes (resolved flags are silent).
ACTIVE_FLAG_STATUSES: frozenset[str] = frozenset({"open", "monitoring"})

# Structured surface (skin) safety answers. The vocabulary is deliberately the
# guided injury intake's own (``open_wound`` -> skin_integrity, ``bleeding_status``,
# ``infection_signs``), so the daily check-in and the guided intake never carry two
# names for the same fact. Every field is OPTIONAL: an existing client that posts
# only ``{flag_id, status}`` stays valid, and the classifier treats a missing
# answer as "unknown", never as "clear".
# How many infection signs one report may carry (a bounded checkbox list, not
# free-form input). Defined here, next to the vocabulary it belongs to, and
# reused by every layer above so the API contract, the response model and the
# injury_flags column constraint can never disagree about the bound.
MAX_INFECTION_SIGNS = 8

SkinIntegrity = Literal["intact", "open", "unknown"]
BleedingStatus = Literal["none", "controlled", "uncontrolled"]
Drainage = Literal["none", "present", "unknown"]
Coverable = Literal["yes", "no", "unknown"]
FrictionOrContactProblem = Literal["yes", "no", "unknown"]

# The columns a surface follow-up persists, so a later day's check-in can be
# evaluated without re-asking or parsing free text.
SURFACE_SAFETY_FIELDS: tuple[str, ...] = (
    "skin_integrity",
    "bleeding_status",
    "drainage",
    "infection_signs",
    "coverable",
    "friction_or_contact_problem",
)


class DeclaredInjury(BaseModel):
    """One injury as reported on a daily check-in.

    ``flag_id`` references an existing open flag being updated; without it the
    report is a new injury and needs a ``body_area`` or ``description`` to
    identify it.

    The surface-safety fields are the structured follow-up asked only when a
    known skin injury is marked worse. They are what routes the wound (local
    friction restriction / no contact / medical review) instead of the blanket
    "active injury worse" stop, so they are persisted rather than read once.
    """

    flag_id: str | None = None
    body_area: str = ""
    description: str = ""
    severity: InjuryFlagSeverity | None = None
    status: InjuryCheckinStatus = "ongoing"
    skin_integrity: SkinIntegrity | None = None
    bleeding_status: BleedingStatus | None = None
    drainage: Drainage | None = None
    # Bounded to the same limit the injury_flags column enforces. A list this
    # contract accepted but the database rejected would surface as a write
    # failure at persist time rather than a validation error at the edge.
    infection_signs: list[str] | None = Field(default=None, max_length=MAX_INFECTION_SIGNS)
    coverable: Coverable | None = None
    friction_or_contact_problem: FrictionOrContactProblem | None = None

    @model_validator(mode="after")
    def _check_identifiable(self) -> "DeclaredInjury":
        if not self.flag_id and not (self.body_area.strip() or self.description.strip()):
            raise ValueError("a new injury needs a body_area or description")
        return self

    def surface_safety_fields(self) -> dict[str, object]:
        """Only the surface answers this report actually carried.

        Absent answers are left out entirely so a plain daily update can never
        blank a previously recorded one.
        """
        fields: dict[str, object] = {}
        for name in SURFACE_SAFETY_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            fields[name] = list(value) if isinstance(value, list) else value
        return fields


class FlagUpdate(BaseModel):
    flag_id: str
    fields: dict[str, object] = Field(default_factory=dict)


class ReconciliationPlan(BaseModel):
    """Storage-agnostic plan: flags to create, and existing flags to update."""

    creates: list[dict[str, object]] = Field(default_factory=list)
    updates: list[FlagUpdate] = Field(default_factory=list)


# Canonical injury-type key (from the shared injury synonym logic) -> the short
# athlete-facing noun we display. Everything not listed maps to itself, so only
# the keys whose canonical name reads oddly to an athlete need an entry.
_CONDITION_DISPLAY_NOUN = {"contusion": "bruise"}

# Structural / urgent injuries deliberately carry injury_type "unspecified" (they
# are routed by the triage category, not by ordinary rehab typing), but they
# still have an obvious display noun. When the scorer nulls injury_type, the label
# recovers the noun from the triage category so a tear/rupture/fracture never
# loses its type — "knee tendon tear" reads "Knee tendon tear", "acl tear"
# reads "ACL tear", "broken collarbone" reads "Collarbone fracture".
_TRIAGE_DISPLAY_NOUN = {
    "fracture": "fracture",
    "dislocation": "dislocation",
    "concussion": "concussion",
    "tendon_rupture": "rupture",
    "muscle_rupture": "tear",
    "ligament_tear": "tear",
    "acl_tear": "ACL tear",
    "mcl_tear": "MCL tear",
    "pcl_tear": "PCL tear",
    "lcl_tear": "LCL tear",
    "hernia": "hernia",
    "infection": "infection",
    "nerve_involvement": "nerve issue",
}

# A reported *tear* is not a *rupture*. The ``tendon_rupture`` triage category is a
# safety bucket that deliberately catches BOTH an honest "bicep tear" and a genuine
# "achilles rupture" so both route to clinical clearance (see TRIAGE_CATEGORY_MAP).
# That conflation is correct for routing, but the athlete-facing label must not put
# the louder word in the athlete's mouth: relabelling "Left bicep tear" as "Left
# bicep rupture" over-states a partial tear as a complete one. So the "rupture"
# noun is earned only by explicit evidence of a COMPLETE tear: a rupture/avulsion,
# a detached or snapped tendon, or a "complete"/"full-thickness" tear. A tear being
# clinically *confirmed* proves it exists, not that it is complete — "confirmed
# achilles tear" is still a tear — so "confirmed" is deliberately NOT evidence on
# its own ("confirmed rupture" already matches via the bare "rupture" token). The
# underlying triage — and its clearance requirement — is unchanged.
_RUPTURE_EVIDENCE_PATTERN = re.compile(
    r"\b(?:rupture[d]?|avuls(?:ion|ed)|detached|snap(?:ped)?|"
    r"complete\s+(?:tear|rupture)|full[-\s]thickness(?:\s+tear)?|full\s+tear)\b",
    re.IGNORECASE,
)


def _triage_display_noun(triage_category: str, injury_text: str) -> str:
    """Athlete-facing type noun for a structural triage category.

    Mirrors ``_TRIAGE_DISPLAY_NOUN`` except that a ``tendon_rupture`` with no
    explicit rupture evidence in the athlete's own words is honestly labelled a
    "tear" rather than escalated to "rupture".
    """
    noun = _TRIAGE_DISPLAY_NOUN.get(triage_category, "")
    if triage_category == "tendon_rupture" and not _RUPTURE_EVIDENCE_PATTERN.search(
        injury_text or ""
    ):
        return "tear"
    return noun

# Triage categories whose name already implies the body part (a named knee
# ligament, or a head/brain injury), so the label shows the type alone rather
# than pinning it to a body region — "ACL tear", not "Knee ACL tear".
_LOCATIONLESS_TRIAGE = {"acl_tear", "mcl_tear", "pcl_tear", "lcl_tear", "concussion"}

# Prefix nouns forced to their conventional casing in the final label.
_LABEL_ABBREVIATIONS = ("acl", "mcl", "pcl", "lcl", "mtss", "it band", "ac joint")

# Bare dizziness / lightheadedness with no head-impact context is a soft,
# non-urgent monitor note (commonly a weight-cut symptom, not a head injury), so
# it is NOT routed to concussion. It carries no injury type or location, so give
# it a clean standalone noun label.
_SOFT_SYMPTOM_LABELS = {
    "dizzy": "Dizziness",
    "dizziness": "Dizziness",
    "feeling dizzy": "Dizziness",
    "feel dizzy": "Dizziness",
    "lightheaded": "Lightheadedness",
    "light headed": "Lightheadedness",
    "light-headed": "Lightheadedness",
}

# Curated condition words (with their common inflections) stripped out of the
# body-location text so a label never reads "wrist tightness tightness". This is
# deliberately a small, safe list — NOT the full synonym map, whose looser
# entries ("full", "hit", "point"...) would eat real location words.
_CONDITION_STRIP = re.compile(
    r"\b(?:bruis(?:e|ed|ing)|contusion|hyperextend(?:ed|ing|s)?|hyperextension|"
    r"disloc(?:ate|ated|ation)|fractur(?:e|ed)|broke(?:n)?|break|crack(?:ed)?|shattered|"
    r"ruptur(?:e|ed)|tears?|torn|tore|snap(?:ped)?|pop(?:ped)?|blown|"
    r"sprain(?:ed|ing)?|strain(?:ed|ing)?|pulled|tendon[ai]tis|tendinopathy|"
    r"imping(?:ed|ement)|instability|unstable|inflam(?:ed|mation|matory)|"
    r"swollen|swelling|stiff(?:ness)?|tight(?:ness)?|sore(?:ness)?|"
    r"ach(?:e|es|ing|y)|pain(?:ful)?|hurts?|hurting|abrasion|graz(?:e|ed|ing)|"
    r"blister(?:s|ed)?|lacerat(?:e|ed|ion)|cuts?|wound(?:s|ed)?)\b",
    re.I,
)

# Connective/filler words removed once the condition is stripped, leaving only
# the body location. Laterality (left/right) is deliberately kept. Clinical
# qualifiers (confirmed/suspected/possible/likely) are stripped too — they modify
# the diagnosis, not the body part, so "confirmed achilles tear" must not read
# "Confirmed achilles tear".
_LOCATION_FILLER = re.compile(
    r"\b(?:is|are|was|were|been|be|has|have|had|got|getting|gets|feels?|feeling|felt|"
    r"seems?|it|this|that|a|an|the|my|some|really|quite|very|bit|of|in|on|with|and|"
    r"confirmed|suspected|possible|likely)\b",
    re.I,
)
_LOCATION_SIDE_WORDS = {"left", "right", "both", "bilateral"}


def _clean_location(text: str) -> str:
    """Reduce a body-area string to just the location words (no condition/filler)."""
    text = _CONDITION_STRIP.sub(" ", text)
    text = _LOCATION_FILLER.sub(" ", text)
    # Keep unicode letters (non-English body-area input), spaces, slashes and
    # hyphens; drop digits/underscores and punctuation so parser debris cannot
    # leak in. \w keeps letters+digits+underscore, then the second pass removes
    # the digits and underscores it let through.
    text = re.sub(r"[^\w\s/-]", " ", text)
    text = re.sub(r"[\d_]", " ", text)
    words = [w for w in text.lower().split() if w]
    seen: list[str] = []
    for word in words:
        if word not in seen:
            seen.append(word)
    return " ".join(seen)


def _strip_type_synonyms(location: str, synonyms: Sequence[str], condition_key: str) -> str:
    """Remove the DETECTED injury type's own synonyms from the location text.

    The scorer already told us which type matched, so the synonym list for that
    exact type is the authoritative set of condition/descriptor words to strip —
    "rolled" for a sprain, "cramp" for a strain, "pinch" for an impingement,
    "frozen" for stiffness. This is why it can't eat unrelated body words: it only
    ever removes phrasing that belongs to the type that actually matched. Longer
    phrases go first so "mat burn" is removed before a bare "burn" would be.
    """
    if not location or not condition_key or condition_key == "unspecified":
        return location
    phrases = sorted({*synonyms, condition_key}, key=len, reverse=True)
    text = f" {location.lower()} "
    for phrase in phrases:
        phrase = phrase.strip().lower()
        if not phrase:
            continue
        text = re.sub(rf"(?<!\S){re.escape(phrase)}(?!\S)", " ", text)
    return " ".join(text.split())


def _has_scored_body_location(canonical_location: str) -> bool:
    return any(word not in _LOCATION_SIDE_WORDS for word in canonical_location.lower().split())


# Lazily-built, module-level caches of the normalized body-location vocabulary.
# The location map is the same object on every call, so its derived phrase/token
# sets are computed once on first use and reused thereafter — this keeps the
# deferred import cheap while making per-label lookups O(1).
_KNOWN_LOCATION_VOCAB: tuple[set[str], set[str]] | None = None


def _location_vocabulary(location_map: Mapping[str, str]) -> tuple[set[str], set[str]]:
    """Return the cached (phrases, tokens) vocabulary, building it on first use."""
    global _KNOWN_LOCATION_VOCAB
    if _KNOWN_LOCATION_VOCAB is None:
        phrases = {
            re.sub(r"[_/-]+", " ", str(phrase).lower()).strip()
            for phrase in (*location_map.keys(), *location_map.values())
            if str(phrase).strip()
        }
        # Body-map combined labels and common singulars that the scorer may route to
        # another region but should still display cleanly as typed.
        phrases.update({"head", "head neck", "rib"})
        tokens: set[str] = set()
        for phrase in phrases:
            tokens.update(phrase.split())
        _KNOWN_LOCATION_VOCAB = (phrases, tokens)
    return _KNOWN_LOCATION_VOCAB


def _looks_like_location_only(location: str, location_map: Mapping[str, str]) -> bool:
    """True when cleaned no-condition text is only body-location words."""
    normalized = re.sub(r"[_/-]+", " ", location.lower())
    normalized = " ".join(word for word in normalized.split() if word not in _LOCATION_SIDE_WORDS)
    if not normalized:
        return False

    known_phrases, known_tokens = _location_vocabulary(location_map)
    if normalized in known_phrases:
        return True

    return all(word in known_tokens for word in normalized.split())


def build_injury_label(body_area: object, description: object) -> str:
    """Build a short, athlete-facing injury label using the injury synonym logic.

    The condition is identified with the shared deterministic injury scorer rather
    than parsing the athlete's exact words, so a flag stored as "left wrist" with a
    "tightness" intake type reads as "Left wrist tightness", and colourful phrasing
    ("dead leg", "corked", "black and blue") still resolves to the right noun.

    Location comes from the clean structured ``body_area`` when present. When it is
    empty we fall back to the scorer's *structured* side + location (e.g. "left" +
    "knee") rather than cleaning the free-text description, so athlete notes like
    "hurts when squatting" can never leak into the label.
    """
    # Deferred import: keeps the fightcamp NLP/synonym stack from loading eagerly
    # for every importer of api.contracts, which only some code paths ever need.
    from fightcamp.injury_scoring import score_injury_phrase
    from fightcamp.injury_synonyms import INJURY_SYNONYM_MAP, LOCATION_MAP, TRIAGE_CATEGORY_MAP

    body = str(body_area or "").strip()
    desc = str(description or "").strip()
    if not (body or desc):
        return "injury"

    score = score_injury_phrase(f"{body} {desc}")
    condition_key = str(score.get("injury_type") or "") if score else ""
    triage_category = str(score.get("triage_category") or "") if score else ""
    # Structural injuries (fracture / tear / rupture / dislocation / concussion)
    # deliberately null out injury_type, so recover the display noun from the
    # triage category. condition_key becomes the display noun; triage_category is
    # kept separately to drive synonym stripping and location handling. The noun is
    # resolved from the athlete's own words so a reported tear is not escalated to a
    # rupture (see _triage_display_noun).
    if condition_key in ("", "unspecified"):
        condition_key = _triage_display_noun(triage_category, f"{body} {desc}") or condition_key
    condition = (
        _CONDITION_DISPLAY_NOUN.get(condition_key, condition_key)
        if condition_key and condition_key != "unspecified"
        else ""
    )

    # Bare dizziness/lightheadedness (no injury type resolved) is a soft note, not
    # a concussion — surface a clean noun and stop before the location machinery.
    if not condition:
        normalized = " ".join(f"{body} {desc}".lower().split())
        for phrase, soft_label in _SOFT_SYMPTOM_LABELS.items():
            if re.search(rf"(?<!\S){re.escape(phrase)}(?!\S)", normalized):
                return soft_label

    # The scorer's canonical side + location, used both as the no-body fallback and
    # to recover a location when synonym stripping empties the athlete's own words
    # (e.g. "jumpers knee" -> the synonym is stripped, "knee" comes from here).
    side = str(score.get("side") or "") if score else ""
    scored_location = str(score.get("location") or "") if score else ""
    canonical_location = " ".join(
        part
        for part in (
            side if side and side != "unspecified" else "",
            scored_location.replace("_", " ") if scored_location and scored_location != "unspecified" else "",
        )
        if part
    ).strip()

    # Strip set = the matched rehab type's synonyms plus, for a structural injury,
    # the triage surface phrases that map to this category. Both come from the
    # shared maps (source of truth), so descriptor phrasing — "rolled", "pinch",
    # "frozen", "jumpers knee", "subluxation", "got rocked" — never pads the label.
    strip_phrases = list(INJURY_SYNONYM_MAP.get(condition_key, []))
    if triage_category:
        strip_phrases += [phrase for phrase, cat in TRIAGE_CATEGORY_MAP.items() if cat == triage_category]

    if body:
        location = _clean_location(body)
        if condition:
            # Fall back to the scorer's canonical location if stripping leaves
            # nothing, then to the raw cleaned location so a colloquialism is
            # never blanked.
            stripped = _strip_type_synonyms(location, strip_phrases, condition_key or triage_category)
            location = stripped or canonical_location or location
        elif (
            location
            and canonical_location
            and _has_scored_body_location(canonical_location)
            and not _looks_like_location_only(location, LOCATION_MAP)
        ):
            location = canonical_location
    else:
        location = canonical_location

    # Some categories name their own region (a knee ligament, or a head/brain
    # injury) or carry only colloquial phrasing with no usable location, so the
    # label shows the type alone — "ACL tear", "Concussion".
    if triage_category in _LOCATIONLESS_TRIAGE:
        location = ""

    # Safety net: drop any location token that IS the condition — canonical noun or
    # matched key — so the condition is only ever appended once, wherever it sits.
    if condition and location:
        drop = {condition.lower(), condition_key.lower()}
        location = " ".join(word for word in location.split() if word.lower() not in drop).strip()

    if condition and location and not location.endswith(condition):
        label = f"{location} {condition}"
    elif condition and not location:
        label = condition
    else:
        # No condition and no structured location: fall back to the cleaned
        # body-area (never the raw free-text description).
        label = location or _clean_location(body)

    label = label.strip()
    if not label:
        return "injury"
    label = (label[0].upper() + label[1:])[:60]
    # Force conventional casing on abbreviations that survive as location words
    # ("acl gone" -> location "acl" -> "ACL gone").
    for abbr in _LABEL_ABBREVIATIONS:
        label = re.sub(rf"(?<!\S){re.escape(abbr)}(?!\S)", abbr.upper(), label, flags=re.IGNORECASE)
    return label


def _flag_label(flag: Mapping[str, object]) -> str:
    label = str(flag.get("label") or "").strip()
    if label:
        return label[:60]
    return build_injury_label(flag.get("body_area"), flag.get("description"))


# Coarse injury "consequence" tier consumed by the daily Today readiness engine so
# the decision can scale restriction by injury TYPE, not severity alone:
#   * "neuro"          — head / neck / nerve / concussion: brain & nerve tissue,
#                        restrict on any session.
#   * "structural"     — fracture / tear / rupture / dislocation / rib / infection /
#                        post-surgery: restrict hard & moderate exposure.
#   * "load_sensitive" — tendon (tendonitis) / joint (impingement, instability):
#                        restrict high-load / high-impact exposure.
#   * None             — surface / soft-tissue (bruise) / symptom (soreness,
#                        stiffness): minor, do NOT restrict by default.
# Derived from the shared injury taxonomy (single source of truth) so it never
# drifts from the plan-generation triage.
_CONSEQUENCE_NEURO_TRIAGE = frozenset({"concussion", "nerve_involvement"})
_CONSEQUENCE_STRUCTURAL_TRIAGE = frozenset(
    {
        "fracture",
        "dislocation",
        "tendon_rupture",
        "muscle_rupture",
        "ligament_tear",
        "acl_tear",
        "mcl_tear",
        "pcl_tear",
        "lcl_tear",
        "hernia",
        "infection",
    }
)
_CONSEQUENCE_NEURO_CATEGORIES = frozenset({"neurological"})
_CONSEQUENCE_STRUCTURAL_CATEGORIES = frozenset({"structural", "medical", "post_op"})
_CONSEQUENCE_LOAD_SENSITIVE_CATEGORIES = frozenset({"overuse", "mechanical"})
# Rib / lower-torso structural area: even a "bruised rib" needs rotation, contact,
# clinch and heavy-brace protection, so it is never treated as a plain bruise.
_RIB_LOCATION_RE = re.compile(
    r"\b(?:ribs?|rib\s*cage|ribcage|costal|sternum|floating\s+rib)\b", re.I
)


def injury_consequence_tier(
    body_area: object,
    description: object,
    *,
    severity: object = None,
) -> str | None:
    """Return the coarse consequence tier for an injury, or ``None`` for minor
    (surface / soft-tissue / symptom) injuries that should not restrict training by
    default. Pure classification off the shared taxonomy — see the tier notes above.
    """
    # Deferred import: keeps the fightcamp NLP/synonym stack out of the eager import
    # graph for callers that never classify an injury.
    from fightcamp.injury_registry import get_registry_category
    from fightcamp.injury_scoring import score_injury_phrase

    text = f"{str(body_area or '').strip()} {str(description or '').strip()}".strip()
    if not text:
        return None
    score = score_injury_phrase(text) or {}
    triage_category = str(score.get("triage_category") or "")
    if triage_category in _CONSEQUENCE_NEURO_TRIAGE:
        return "neuro"
    if triage_category in _CONSEQUENCE_STRUCTURAL_TRIAGE:
        return "structural"

    category = get_registry_category(str(score.get("injury_type") or ""))
    if category in _CONSEQUENCE_NEURO_CATEGORIES:
        tier: str | None = "neuro"
    elif category in _CONSEQUENCE_STRUCTURAL_CATEGORIES:
        tier = "structural"
    elif category in _CONSEQUENCE_LOAD_SENSITIVE_CATEGORIES:
        tier = "load_sensitive"
    else:
        tier = None

    # A rib injury of any non-structural type is still torso-structural for exposure
    # purposes (rotation / contact / bracing), never a harmless bruise.
    if tier in (None, "load_sensitive") and _RIB_LOCATION_RE.search(text):
        tier = "structural"
    return tier


def reconcile_injury_checkin(
    *,
    declared: Sequence[DeclaredInjury],
    open_flag_ids: Iterable[str],
) -> ReconciliationPlan:
    """Build the create/update plan for a day's declared injuries.

    A ``flag_id`` is only honoured when it belongs to the athlete's current open
    flags (``open_flag_ids``) — anything else is treated as a new injury, so a
    stale or foreign id can never mutate another athlete's flag.
    """
    known = {str(flag_id) for flag_id in open_flag_ids}
    creates: list[dict[str, object]] = []
    updates: list[FlagUpdate] = []

    for injury in declared:
        flag_status = _FLAG_STATUS_BY_REPORT[injury.status]
        if injury.flag_id and injury.flag_id in known:
            fields: dict[str, object] = {
                "status": flag_status,
                "latest_reported_status": injury.status,
            }
            if injury.severity is not None:
                fields["severity"] = injury.severity
            if injury.body_area.strip():
                fields["body_area"] = injury.body_area.strip()
            if injury.description.strip():
                fields["description"] = injury.description.strip()
            fields.update(injury.surface_safety_fields())
            updates.append(FlagUpdate(flag_id=injury.flag_id, fields=fields))
            continue

        # A brand-new injury reported as already resolved is a no-op — there is
        # nothing to track. Otherwise open (or monitor) a fresh flag.
        if flag_status == "resolved":
            continue
        if not (injury.body_area.strip() or injury.description.strip()):
            raise ValueError("a new injury needs a body_area or description")
        description = injury.description.strip() or injury.body_area.strip()
        creates.append(
            {
                "source": "checkin",
                "body_area": injury.body_area.strip(),
                "description": description,
                "severity": injury.severity or "moderate",
                "status": flag_status,
                "latest_reported_status": injury.status,
                **injury.surface_safety_fields(),
            }
        )

    return ReconciliationPlan(creates=creates, updates=updates)


def open_injury_flag_risks(
    open_flags: Sequence[Mapping[str, object]],
) -> list[RiskWatchItem]:
    """Surface tracked open injuries as a single risk-watch item.

    Any active (non-resolved) severe injury reads as a stop-level "keep load off
    it" item; otherwise a softer "training around it" reminder so the badge stays
    live for as long as any injury is open and clears the moment they are all
    resolved. The severe stop is driven by SEVERITY, not day-status: an easing
    (monitoring) severe injury is still severe, so it must not quietly drop to the
    soft reminder — that mirrors the Today/Overview injury hold and closes the
    "mark it easing to bypass" gap.
    """
    active = [f for f in open_flags if str(f.get("status") or "") in ACTIVE_FLAG_STATUSES]
    if not active:
        return []

    severe = [f for f in active if str(f.get("severity") or "") == "severe"]
    if severe:
        return [
            make_risk(
                "active_injury_worse",
                text=f"Active severe injury: {_flag_label(severe[0])}. Keep load off it until cleared.",
            )
        ]

    labels = ", ".join(_flag_label(f) for f in active[:2])
    count = len(active)
    noun = "injury" if count == 1 else "injuries"

    # Stable skin injuries stay VISIBLE, but they are a hygiene constraint, not
    # something to train around: "train around it" would read as a dosage
    # instruction for an intact blister. Uses the canonical classification, never
    # a second copy of the rules.
    from api.contracts.readiness_message import classify_injury_surface

    if all(classify_injury_surface(flag) == "stable_surface" for flag in active):
        skin_noun = "skin injury" if count == 1 else "skin injuries"
        return [
            make_risk(
                "reminder",
                text=f"Tracking {count} {skin_noun}: {labels}. Keep it clean and covered.",
            )
        ]

    return [
        make_risk(
            "reminder",
            text=f"Tracking {count} open {noun}: {labels}. Train around it.",
        )
    ]
