"""Turning a completed rehab drill into an attributable exposure — or refusing to.

PR3 built the evidence model. This module is the gate in front of it: given the
rehab work in a completed session and the athlete's open injuries, it decides
*which* completed drills may become a :class:`RehabExposureEvent`, and says
plainly why the rest may not.

Refusing is the point
---------------------
A rehab exposure asserts "this specific tissue did this specific work". Every
part of that has to be known. When any part is not, the honest output is an
explicit ineligibility code — never a guess, and never a positive observation
with the unknown parts quietly defaulted:

* :data:`REASON_NOT_REHAB_WORK` — the item is not from the rehab bank.
* :data:`REASON_NOT_COMPLETED` — the athlete did not do any of it.
* :data:`REASON_ATTRIBUTION_UNKNOWN` — no open injury matches the drill's region.
* :data:`REASON_MULTIPLE_POSSIBLE_INJURIES` — more than one does, and nothing in
  the record says which the work was for.
* :data:`REASON_LATERALITY_UNKNOWN` — the region matches but the side does not
  resolve on the injury, the drill, or both.
* :data:`REASON_EPISODE_UNKNOWN` — the injury carries no episode identity, so the
  evidence could not be isolated from a previous episode.
* :data:`REASON_DEMAND_UNKNOWN` — the drill's load/impact/velocity are still
  unreviewed in the bank, so the exposure's ``demand`` cannot be stated.

That last one currently applies to **every** drill in the bank: PR3 migrated
``target_regions`` and left the clinical demand fields explicitly unreviewed
("all more specific clinical fields stay explicitly unknown until reviewed").
``ExposureDemand`` requires ``load``/``impact``/``velocity``, so until those are
reviewed no exposure can be written. Inventing them here would be inventing
clinical classification, which is exactly what this pipeline exists to prevent.
The gate therefore reports the gap rather than papering over it, and closing it
is a data question, not a code one.

Scope note (PR 3.5)
-------------------
This module produces observations. It does not interpret them: nothing here
decides whether an exposure was *tolerated*, and nothing here can move a rehab
stage. LOAD / DYNAMIC / RETURN remain unreachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from fightcamp.rehab_schema import (
    CARE_TYPE_WOUND_CARE,
    care_type_for_injury_type,
)

from .rehab_exposure import (
    DemandLevel,
    ExposureDemand,
    ExposureDose,
    ImpactLevel,
    VelocityLevel,
)

# ---------------------------------------------------------------------------
# Ineligibility codes
# ---------------------------------------------------------------------------

REASON_NOT_REHAB_WORK = "not_rehab_work"
REASON_NOT_COMPLETED = "not_completed"
REASON_ATTRIBUTION_UNKNOWN = "attribution_unknown"
REASON_MULTIPLE_POSSIBLE_INJURIES = "multiple_possible_injuries"
REASON_LATERALITY_UNKNOWN = "laterality_unknown"
REASON_EPISODE_UNKNOWN = "episode_unknown"
REASON_DEMAND_UNKNOWN = "demand_unknown"
REASON_SURFACE_PATHWAY = "surface_injury_wound_care_pathway"

#: Injury-flag statuses that describe a live injury rehab work can be logged for.
ACTIVE_FLAG_STATUSES: frozenset[str] = frozenset({"open", "monitoring"})

#: Completion states that mean the athlete did at least part of the work. A
#: session that was never started, or was skipped, is not an exposure.
COMPLETED_STATUSES: frozenset[str] = frozenset({"done", "modified"})

#: The demand fields ``ExposureDemand`` requires and the bank does not yet carry.
REQUIRED_DEMAND_FIELDS: tuple[str, ...] = ("load", "impact", "velocity")

_DEMAND_VALUES: dict[str, frozenset[str]] = {
    "load": frozenset(DemandLevel.__args__),  # type: ignore[attr-defined]
    "impact": frozenset(ImpactLevel.__args__),  # type: ignore[attr-defined]
    "velocity": frozenset(VelocityLevel.__args__),  # type: ignore[attr-defined]
}

#: Drill laterality values that let a side-specific injury claim the work.
_SIDE_SPECIFIC_APPLICABILITY = "side_specific"
_BILATERAL_APPLICABILITY = "bilateral_only"
_NOT_APPLICABLE_APPLICABILITY = "not_applicable"


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RehabExposureCandidate:
    """One completed rehab drill, resolved as far as the record allows.

    ``eligible`` is true only when every identity part is known. When it is
    false, ``reasons`` names each missing part — the caller surfaces or logs
    them, and writes nothing.
    """

    drill_id: str
    eligible: bool
    reasons: tuple[str, ...] = ()
    injury_id: str | None = None
    injury_episode_id: str | None = None
    body_region: str | None = None
    side: str | None = None
    demand: ExposureDemand | None = None
    prescribed_dose: ExposureDose | None = None
    #: Injuries whose region matched, for explaining an ambiguous attribution.
    candidate_injury_ids: tuple[str, ...] = ()

    @property
    def needs_athlete_response(self) -> bool:
        """True when this candidate should raise the injury-specific question."""
        return self.eligible


@dataclass(frozen=True)
class RehabCompletionResolution:
    """Every rehab item in one completed session, eligible or not."""

    candidates: tuple[RehabExposureCandidate, ...] = ()

    @property
    def eligible(self) -> tuple[RehabExposureCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.eligible)

    @property
    def ineligible(self) -> tuple[RehabExposureCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if not candidate.eligible)

    @property
    def has_attributable_rehab(self) -> bool:
        """Whether the injury-specific block should be shown at all.

        The block is shown only for genuinely attributable rehab work, so a
        normal training session never raises it.
        """
        return bool(self.eligible)

    #: The distinct injuries the athlete should be asked about, in a stable order.
    @property
    def injury_ids_to_ask(self) -> tuple[str, ...]:
        seen: list[str] = []
        for candidate in self.eligible:
            if candidate.injury_id and candidate.injury_id not in seen:
                seen.append(candidate.injury_id)
        return tuple(seen)


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _is_active_injury(injury: Mapping[str, Any]) -> bool:
    return _lower(injury.get("status")) in ACTIVE_FLAG_STATUSES


def _is_surface_injury(injury: Mapping[str, Any]) -> bool:
    """Skin injuries are wound care and never carry loading exposures."""
    for key in ("injury_type", "rehab_type", "surface_type"):
        if care_type_for_injury_type(injury.get(key)) == CARE_TYPE_WOUND_CARE:
            return True
    return _lower(injury.get("care_pathway")) == CARE_TYPE_WOUND_CARE


def _drill_regions(drill: Mapping[str, Any]) -> tuple[str, ...]:
    raw = drill.get("target_regions")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(_lower(region) for region in raw if _clean(region))


def _resolve_demand(drill: Mapping[str, Any], body_region: str) -> ExposureDemand | None:
    """Build the exposure demand, or ``None`` when the bank has not stated it.

    Every required level must be a reviewed value from its own enum. A missing
    or unrecognised level yields ``None`` — the caller turns that into
    :data:`REASON_DEMAND_UNKNOWN` rather than substituting a default, because a
    substituted default is a clinical claim nobody made.
    """
    levels: dict[str, str] = {}
    for name in REQUIRED_DEMAND_FIELDS:
        value = _lower(drill.get(name))
        if value not in _DEMAND_VALUES[name]:
            return None
        levels[name] = value

    regions = list(_drill_regions(drill))
    if body_region not in regions:
        regions.append(body_region)

    contraction = _lower(drill.get("contraction_type")) or "unknown"
    return ExposureDemand(
        target_regions=regions,
        target_tissues=list(drill["target_tissues"])
        if isinstance(drill.get("target_tissues"), (list, tuple)) and drill.get("target_tissues")
        else None,
        load=levels["load"],  # type: ignore[arg-type]
        impact=levels["impact"],  # type: ignore[arg-type]
        velocity=levels["velocity"],  # type: ignore[arg-type]
        contraction_type=[contraction],  # type: ignore[list-item]
        sport_specificity=_lower(drill.get("sport_specificity")) or "unknown",  # type: ignore[arg-type]
        contact_level=_lower(drill.get("contact_level")) or "unknown",  # type: ignore[arg-type]
    )


def _resolve_side(injury: Mapping[str, Any], drill: Mapping[str, Any]) -> str | None:
    """The side the exposure happened on, or ``None`` when it does not resolve.

    The injury's own recorded side is authoritative — it is what PR3 stores and
    what the database checks the exposure against. The drill's
    ``laterality_applicability`` can only *disqualify*: a drill explicitly marked
    ``bilateral_only`` cannot evidence one side of a side-specific injury.
    """
    injury_side = _lower(injury.get("side"))
    if injury_side not in {"left", "right", "bilateral"}:
        return None

    applicability = _lower(drill.get("laterality_applicability"))
    if applicability == _BILATERAL_APPLICABILITY and injury_side in {"left", "right"}:
        return None
    if applicability == _NOT_APPLICABLE_APPLICABILITY:
        # The drill is not side-organised at all (a breathing reset, say). It
        # cannot evidence one limb of a side-specific injury.
        return "bilateral" if injury_side == "bilateral" else None
    return injury_side


def _prescribed_dose(prescribed: Mapping[str, Any] | None) -> ExposureDose | None:
    """The prescription as given, or ``None`` when the session states none.

    Only fields the session actually carries are set. Nothing is inferred from
    the drill name or the bank's (unmigrated) default dose.
    """
    if not isinstance(prescribed, Mapping):
        return None
    fields: dict[str, Any] = {}
    for name in ("sets", "reps", "duration_seconds", "external_load_kg", "distance_metres", "hold_seconds"):
        value = prescribed.get(name)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)) and value >= 0:
            fields[name] = value
    if not fields:
        return None
    return ExposureDose(**fields)


def completed_dose_from_session(
    completion: Mapping[str, Any] | None,
    *,
    prescribed: Mapping[str, Any] | None = None,
) -> ExposureDose:
    """The clearest defensible statement of what was actually done.

    The session model records completion, not per-drill dose editing. So a
    "done" marking becomes ``completed_fraction=1.0`` — the athlete confirmed
    the prescribed work — and a "modified" marking becomes a partial completion
    that is left *unquantified* rather than guessed.

    A prescribed ``3x10`` is deliberately never echoed back as a completed
    ``3x10``. Marking a session done is not the athlete confirming every rep,
    and the dose the tissue actually saw is not something this layer knows.
    """
    status = _lower((completion or {}).get("status"))
    stopped_early = bool((completion or {}).get("stopped_early")) or status == "modified"
    if status == "modified":
        # Something changed, and nothing records what. Say only that it was
        # not the full prescription.
        return ExposureDose(stopped_early=True)
    return ExposureDose(completed_fraction=1.0, stopped_early=stopped_early)


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def _matching_injuries(
    regions: Sequence[str], injuries: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """Open musculoskeletal injuries whose recorded region the drill targets."""
    region_set = {region for region in regions if region}
    matches: list[Mapping[str, Any]] = []
    for injury in injuries:
        if not isinstance(injury, Mapping) or not _is_active_injury(injury):
            continue
        if _is_surface_injury(injury):
            continue
        body_region = _lower(injury.get("body_region"))
        if body_region and body_region in region_set:
            matches.append(injury)
    return matches


def resolve_rehab_exposure_candidate(
    drill: Mapping[str, Any],
    injuries: Sequence[Mapping[str, Any]],
    *,
    completion: Mapping[str, Any] | None = None,
    prescribed: Mapping[str, Any] | None = None,
) -> RehabExposureCandidate:
    """Resolve one completed rehab drill against the athlete's open injuries.

    Collects *every* reason the drill cannot be logged rather than stopping at
    the first, so the gap is visible in one pass instead of one PR at a time.
    """
    drill_id = _clean(drill.get("id"))
    reasons: list[str] = []

    if not drill_id or not _drill_regions(drill):
        # Without a canonical id there is nothing stable to attribute, and
        # matching on the display name is exactly what this avoids.
        return RehabExposureCandidate(
            drill_id=drill_id, eligible=False, reasons=(REASON_NOT_REHAB_WORK,)
        )

    if _lower((completion or {}).get("status")) not in COMPLETED_STATUSES:
        return RehabExposureCandidate(
            drill_id=drill_id, eligible=False, reasons=(REASON_NOT_COMPLETED,)
        )

    regions = _drill_regions(drill)
    matches = _matching_injuries(regions, injuries)
    candidate_ids = tuple(_clean(injury.get("id")) for injury in matches if _clean(injury.get("id")))

    if not matches:
        return RehabExposureCandidate(
            drill_id=drill_id, eligible=False, reasons=(REASON_ATTRIBUTION_UNKNOWN,)
        )
    if len(matches) > 1:
        # Two open injuries in the same region. Nothing in the record says which
        # the work was for, and picking one would invent the attribution.
        return RehabExposureCandidate(
            drill_id=drill_id,
            eligible=False,
            reasons=(REASON_MULTIPLE_POSSIBLE_INJURIES,),
            candidate_injury_ids=candidate_ids,
        )

    injury = matches[0]
    body_region = _lower(injury.get("body_region"))
    episode_id = _clean(injury.get("episode_id"))
    side = _resolve_side(injury, drill)
    demand = _resolve_demand(drill, body_region)

    if not episode_id:
        reasons.append(REASON_EPISODE_UNKNOWN)
    if side is None:
        reasons.append(REASON_LATERALITY_UNKNOWN)
    if demand is None:
        reasons.append(REASON_DEMAND_UNKNOWN)

    if reasons:
        return RehabExposureCandidate(
            drill_id=drill_id,
            eligible=False,
            reasons=tuple(reasons),
            injury_id=_clean(injury.get("id")) or None,
            injury_episode_id=episode_id or None,
            body_region=body_region or None,
            side=side,
            demand=demand,
            candidate_injury_ids=candidate_ids,
        )

    return RehabExposureCandidate(
        drill_id=drill_id,
        eligible=True,
        injury_id=_clean(injury.get("id")),
        injury_episode_id=episode_id,
        body_region=body_region,
        side=side,
        demand=demand,
        prescribed_dose=_prescribed_dose(prescribed),
        candidate_injury_ids=candidate_ids,
    )


def resolve_rehab_completion(
    rehab_items: Sequence[Mapping[str, Any]],
    injuries: Sequence[Mapping[str, Any]],
    *,
    completion: Mapping[str, Any] | None = None,
) -> RehabCompletionResolution:
    """Resolve every rehab item in one completed session.

    ``rehab_items`` are the session's rehab entries, each carrying the canonical
    bank ``id`` and (optionally) its prescription. Non-rehab work is not passed
    here and never produces an exposure.
    """
    candidates = tuple(
        resolve_rehab_exposure_candidate(
            item,
            injuries,
            completion=completion,
            prescribed=item.get("prescribed_dose") if isinstance(item, Mapping) else None,
        )
        for item in (rehab_items or ())
        if isinstance(item, Mapping)
    )
    return RehabCompletionResolution(candidates=candidates)


# ---------------------------------------------------------------------------
# The injury-specific question, and what its answers mean
# ---------------------------------------------------------------------------

#: "How did it feel during the rehab work?"
DURING_ANSWERS: tuple[str, ...] = ("better", "same", "worse", "not_sure")

#: "Did you have to reduce or stop because of it?"
LIMIT_ANSWERS: tuple[str, ...] = ("no", "reduced", "stopped")


@dataclass(frozen=True)
class RehabResponsePrompt:
    """One injury's post-rehab question, addressed to that injury by name.

    Raised only for attributable rehab work, so a normal training session never
    shows it. Two questions, fixed vocabularies, no free text: this asks what
    the athlete observed, never what it means. Mechanism, diagnosis and
    interpretation are deliberately absent.
    """

    injury_id: str
    injury_label: str
    body_region: str
    side: str
    drill_ids: tuple[str, ...] = ()

    @property
    def during_question(self) -> str:
        return "How did it feel during the rehab work?"

    @property
    def limit_question(self) -> str:
        return "Did you have to reduce or stop because of it?"


def build_rehab_response_prompts(
    resolution: RehabCompletionResolution,
    injuries: Sequence[Mapping[str, Any]],
) -> tuple[RehabResponsePrompt, ...]:
    """One prompt per injury that actually had attributable rehab work.

    Grouped by injury rather than by drill: the athlete is asked about the
    *injury*, once, however many drills targeted it.
    """
    by_id = {_clean(injury.get("id")): injury for injury in injuries if isinstance(injury, Mapping)}
    prompts: list[RehabResponsePrompt] = []
    for injury_id in resolution.injury_ids_to_ask:
        injury = by_id.get(injury_id, {})
        drill_ids = tuple(
            candidate.drill_id
            for candidate in resolution.eligible
            if candidate.injury_id == injury_id
        )
        side = _lower(injury.get("side"))
        region = _lower(injury.get("body_region"))
        label = _clean(injury.get("label")) or " ".join(
            part for part in (side if side in {"left", "right"} else "", region) if part
        ).strip()
        prompts.append(
            RehabResponsePrompt(
                injury_id=injury_id,
                injury_label=label.upper(),
                body_region=region,
                side=side,
                drill_ids=drill_ids,
            )
        )
    return tuple(prompts)


def exposure_response_from_answers(
    during: str | None,
    limit: str | None,
) -> dict[str, Any]:
    """Map the two answers onto ``ExposureResponse`` fields.

    Only what the athlete actually said is recorded:

    * ``during`` becomes ``during_response`` verbatim. It is NOT converted into
      a ``pain_during`` score — a better/same/worse answer is not a 0-10 reading,
      and manufacturing one would invent precision.
    * ``worsening_reported`` restates a ``worse`` answer, and is ``False`` only
      when the athlete positively said better or same. ``not_sure`` leaves it
      ``None``, because unsure is not "no".
    * ``stopped_due_to_symptoms`` is ``True`` only for ``stopped``. ``reduced``
      is a real but different thing and is carried on the dose instead
      (see :func:`completed_dose_stopped_early`), so "cut it short" is never
      recorded as "stopped".

    An unanswered question stays unanswered: ``during_response`` falls back to
    ``not_reported`` rather than to a neutral-sounding ``same``.
    """
    during_value = _lower(during)
    limit_value = _lower(limit)

    response: dict[str, Any] = {
        "during_response": during_value if during_value in DURING_ANSWERS else "not_reported",
    }
    if during_value in {"better", "same"}:
        response["worsening_reported"] = False
    elif during_value == "worse":
        response["worsening_reported"] = True

    if limit_value in LIMIT_ANSWERS:
        response["stopped_due_to_symptoms"] = limit_value == "stopped"
    return response


def completed_dose_stopped_early(limit: str | None) -> bool | None:
    """Whether the athlete cut the work short, from the limit answer alone.

    ``reduced`` and ``stopped`` both mean the prescription was not completed as
    given; ``no`` means it was. An unrecognised or absent answer yields ``None``
    rather than ``False``.
    """
    limit_value = _lower(limit)
    if limit_value not in LIMIT_ANSWERS:
        return None
    return limit_value in {"reduced", "stopped"}


__all__ = [
    "ACTIVE_FLAG_STATUSES",
    "COMPLETED_STATUSES",
    "REASON_ATTRIBUTION_UNKNOWN",
    "REASON_DEMAND_UNKNOWN",
    "REASON_EPISODE_UNKNOWN",
    "REASON_LATERALITY_UNKNOWN",
    "REASON_MULTIPLE_POSSIBLE_INJURIES",
    "REASON_NOT_COMPLETED",
    "REASON_NOT_REHAB_WORK",
    "REASON_SURFACE_PATHWAY",
    "REQUIRED_DEMAND_FIELDS",
    "DURING_ANSWERS",
    "LIMIT_ANSWERS",
    "RehabCompletionResolution",
    "RehabExposureCandidate",
    "RehabResponsePrompt",
    "build_rehab_response_prompts",
    "completed_dose_from_session",
    "completed_dose_stopped_early",
    "exposure_response_from_answers",
    "resolve_rehab_completion",
    "resolve_rehab_exposure_candidate",
]
