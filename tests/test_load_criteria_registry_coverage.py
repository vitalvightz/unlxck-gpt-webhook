"""Guard: a production LOAD criterion is only valid if the bank can satisfy it.

PR4's interpreter is complete, but a RESTORE -> LOAD criterion is meaningless
unless a real, reviewed rehab-bank drill can actually supply the loading demand
it requires. Every bank drill currently reports ``load/impact/velocity`` as
``unknown`` (the clinical demand metadata is not yet migrated), so
``RehabExposureEvent.has_unknown_demand`` excludes every exposure from LOAD
qualification. Adding criteria before that migration would create rules that can
never fire — dead code that misrepresents the system as evidence-based.

The dependency the product owner set out is therefore:

    clinical demand taxonomy
      -> classify each drill's real load/impact/velocity
      -> migrate the reviewed values into the bank
      -> validate coverage (this file)
      -> only then enable injury-specific LOAD criteria
      -> the interpreter can finally distinguish supports / does-not-support /
         insufficient

These tests encode the "validate coverage" gate so a criterion can never be
enabled ahead of the reviewed data that would let it fire, and so nobody has to
weaken the conservative ``insufficient_evidence`` behaviour to make a rule
"work". Unknown stays unknown.
"""

from __future__ import annotations

from api.contracts.load_eligibility import LOAD_CRITERIA_REGISTRY
from api.contracts.rehab_completion import _resolve_demand
from fightcamp.rehab_protocols import get_rehab_bank


def _bank_drills_by_type() -> dict[str, list[tuple[str, dict]]]:
    """Every bank drill grouped by its entry's injury type, with a body region."""
    grouped: dict[str, list[tuple[str, dict]]] = {}
    for entry in get_rehab_bank():
        injury_type = str(entry.get("type") or "")
        region = str(entry.get("location") or "")
        for drill in entry.get("drills", []):
            body_region = region or next(iter(drill.get("target_regions") or []), "")
            grouped.setdefault(injury_type, []).append((body_region, drill))
    return grouped


def _reviewed_demand(body_region: str, drill: dict):
    """The demand a real exposure of this drill would carry, or None if it errors.

    Uses the exact write-path resolver so this guard can never drift from what
    production actually records.
    """
    try:
        return _resolve_demand(drill, body_region or "ankle")
    except Exception:
        return None


def test_every_production_load_criterion_is_backed_by_reviewed_bank_demand():
    """A criterion with no qualifying real-bank drill is a dead rule.

    Passes trivially while the registry is empty, and becomes a hard gate the
    instant a criterion is added: that injury type must have at least one drill
    whose fully-reviewed demand (``has_unknown_demand`` False) carries a load in
    the criterion's ``qualifying_loads``. This mirrors the interpreter's own
    ``known_loading`` filter, so a criterion that passes here can genuinely fire.
    """
    drills_by_type = _bank_drills_by_type()
    for injury_type, criteria in LOAD_CRITERIA_REGISTRY.items():
        qualifying = [
            drill.get("id")
            for body_region, drill in drills_by_type.get(injury_type, [])
            if (demand := _reviewed_demand(body_region, drill)) is not None
            and not demand.has_unknown_level
            and demand.load in criteria.qualifying_loads
        ]
        assert qualifying, (
            f"LOAD_CRITERIA_REGISTRY[{injury_type!r}] requires demand.load in "
            f"{set(criteria.qualifying_loads)} with fully-reviewed demand, but no "
            f"reviewed bank drill of type {injury_type!r} supplies it, so the "
            f"criterion can never return eligible. Migrate the bank's clinical "
            f"demand metadata for this injury type before enabling the criterion."
        )


def test_production_registry_stays_empty_until_bank_demand_is_migrated():
    """Documents the production-readiness blocker as an executable checkpoint.

    While no bank drill carries reviewed demand, the only honest production
    registry is empty. When drills gain reviewed demand this assertion flips,
    prompting whoever migrated the data to add matching criteria — which the
    coverage guard above then holds to real evidence.
    """
    reviewed = [
        (injury_type, drill.get("id"))
        for injury_type, drills in _bank_drills_by_type().items()
        for body_region, drill in drills
        if (demand := _reviewed_demand(body_region, drill)) is not None
        and not demand.has_unknown_level
    ]
    if reviewed:
        assert dict(LOAD_CRITERIA_REGISTRY), (
            "Rehab-bank drills now carry reviewed clinical demand metadata "
            f"(e.g. {reviewed[:5]}), but LOAD_CRITERIA_REGISTRY is still empty. "
            "Add injury-specific LOAD criteria for the migrated types (the "
            "coverage guard keeps them backed by real evidence) rather than "
            "leaving reviewed data unused."
        )
    else:
        assert dict(LOAD_CRITERIA_REGISTRY) == {}, (
            "No bank drill carries reviewed demand metadata yet, so no LOAD "
            "criterion can ever fire. The registry must stay empty until the "
            "clinical demand migration lands — do not add criteria that cannot "
            "be satisfied, and do not weaken the interpreter to make them pass."
        )
