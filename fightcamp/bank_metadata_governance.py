from __future__ import annotations

from pathlib import Path
from typing import Any

from . import bank_schema

_GOVERNED_SOURCES = {
    "conditioning_bank.json",
    "coordination_bank.json",
    "technical_footwork_bank.json",
    "style_conditioning_bank.json",
    "style_taper_conditioning.json",
    "exercise_bank.json",
}
_SUPPORT_ONLY_SOURCES = {
    "coordination_bank.json",
    "technical_footwork_bank.json",
    "style_taper_conditioning.json",
}
_CONDITIONING_SOURCES = {
    "conditioning_bank.json",
    "coordination_bank.json",
    "technical_footwork_bank.json",
    "style_conditioning_bank.json",
    "style_taper_conditioning.json",
}
_GOVERNANCE_ISSUES = {
    "missing_stress_class",
    "missing_cost_class",
    "missing_support_only",
    "missing_meaningful_stress",
}
_OPTIONAL_CONDITIONING_DOSE_ISSUES = {
    "missing_work_sec",
    "missing_rest_sec",
    "missing_rounds",
    "missing_total_minutes",
}
_HIGH_LEVELS = {"high", "very_high", "max"}
_SUPPORT_TAGS = {
    "recovery",
    "cns_freshness",
    "skill_refinement",
    "mobility",
    "rehab",
    "rehab_friendly",
    "prehab",
    "injury_prevention",
}
_SUPPORT_NAME_HINTS = (
    "recovery",
    "primer",
    "reset",
    "mobility",
    "breathing",
    "easy flush",
)


def _source_name(source: str) -> str:
    return Path(str(source or "").replace("\\", "/")).name.lower()


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _effective_rpe(item: dict[str, Any]) -> float | None:
    values = [
        value
        for value in (_number(item.get("rpe")), _number(item.get("rpe_max")))
        if value is not None
    ]
    return max(values) if values else None


def _tokens(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value in (None, ""):
        values = []
    else:
        values = [value]
    return {
        str(token).strip().lower().replace("-", "_").replace(" ", "_")
        for token in values
        if str(token).strip()
    }


def _system(item: dict[str, Any]) -> str:
    raw = str(item.get("system") or "").strip().lower()
    return bank_schema.SYSTEM_ALIASES.get(raw, raw)


def _conditioning_support_only(item: dict[str, Any], source: str) -> bool:
    if item.get("support_only") is True or item.get("meaningful_stress") is False:
        return True
    if item.get("support_only") is False or item.get("meaningful_stress") is True:
        return False
    if source in _SUPPORT_ONLY_SOURCES:
        return True

    system = _system(item)
    raw_system = str(item.get("system") or "").strip().lower()
    if raw_system in bank_schema.SUPPORT_ONLY_SYSTEM_ALIASES:
        return True

    total_minutes = _number(item.get("total_minutes"))
    rpe = _effective_rpe(item)
    tags = _tokens(item.get("tags"))
    name = str(item.get("name") or "").strip().lower()
    lactate = str(item.get("lactate_load") or "").strip().lower()

    # A real continuous aerobic dose is training, even when it is low-impact or
    # recovery-friendly. This keeps 20-40 minute Zone-2 bike/run/row work from
    # being demoted merely because its notes also mention recovery.
    if system == "aerobic" and total_minutes is not None and total_minutes >= 20:
        return False

    # Short easy recovery / primer work is support. RPE is deliberately part of
    # the gate so a 15-minute but genuinely hard conditioning exposure is not
    # mislabeled as filler.
    support_signal = bool(tags & _SUPPORT_TAGS) or any(hint in name for hint in _SUPPORT_NAME_HINTS)
    if support_signal and (rpe is None or rpe <= 5) and lactate in {"", "none", "low"}:
        return True

    if system == "alactic" and (rpe is None or rpe <= 6):
        active_work = None
        work_sec = _number(item.get("work_sec"))
        rounds = _number(item.get("rounds"))
        if work_sec is not None and rounds is not None:
            active_work = work_sec * rounds
        if active_work is not None and active_work <= 60 and bool(tags & {"cns_freshness", "sharpness", "recovery"}):
            return True

    return False


def _strength_support_only(item: dict[str, Any]) -> bool:
    if item.get("support_only") is True or item.get("meaningful_stress") is False:
        return True
    if item.get("support_only") is False or item.get("meaningful_stress") is True:
        return False

    # Import lazily so package initialisation can install this normalizer before
    # strength.py imports the bank validator.
    from .strength_session_quality import classify_strength_item

    return bool(classify_strength_item(item).get("support_only"))


def _meaningful_cost_class(item: dict[str, Any]) -> str:
    rpe = _effective_rpe(item)
    levels = {
        str(item.get(field) or "").strip().lower()
        for field in (
            "impact_cost",
            "movement_cost",
            "lactate_load",
            "cns_load",
            "eccentric_cost",
            "landing_cost",
            "soreness_risk",
        )
    }
    return "high" if (rpe is not None and rpe >= 8) or bool(levels & _HIGH_LEVELS) else "medium"


def _safe_early_aerobic_window(item: dict[str, Any], source: str) -> bool:
    """Opt clearly low-risk base work into D-21..D-14 only.

    Missing late windows remain fail-closed everywhere else. This narrow rule is
    for traditional continuous aerobic work that is already safe by its authored
    dose/cost metadata; it never invents D-13-or-later eligibility.
    """
    if source not in {"conditioning_bank.json", "style_conditioning_bank.json"}:
        return False
    if "late_windows" in item:
        return False
    if _system(item) != "aerobic":
        return False
    phases = {str(value).strip().upper() for value in (item.get("phases") or []) if str(value).strip()}
    if not phases.intersection({"GPP", "SPP"}):
        return False
    total_minutes = _number(item.get("total_minutes"))
    rpe = _effective_rpe(item)
    if total_minutes is None or total_minutes < 20 or rpe is None or rpe > 6:
        return False
    if any(str(item.get(field) or "").strip().lower() not in {"", "none", "low"} for field in ("impact_cost", "movement_cost", "lactate_load")):
        return False
    tags = _tokens(item.get("tags"))
    if tags & {"high_impact", "high_impact_lower", "mech_cns_high", "mech_landing_impact", "glycolytic"}:
        return False
    return True


def apply_bank_metadata(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Complete governance metadata from already-authored bank semantics.

    Explicit values always win. Derived values only fill fields the bank left
    blank, so this is a compatibility migration rather than a second coaching
    authority.
    """
    source_name = _source_name(source)
    if source_name not in _GOVERNED_SOURCES:
        return item

    if source_name == "exercise_bank.json":
        support_only = _strength_support_only(item)
    else:
        support_only = _conditioning_support_only(item, source_name)

    meaningful = not support_only
    item.setdefault("support_only", support_only)
    item.setdefault("meaningful_stress", meaningful)
    item.setdefault("stress_class", "support" if support_only else "meaningful_stress")
    item.setdefault("cost_class", "low" if support_only else _meaningful_cost_class(item))

    if _safe_early_aerobic_window(item, source_name):
        item["late_windows"] = [bank_schema.D21_TO_D14]

    return item


def _clean_runtime_schema_issues(item: dict[str, Any], *, source: str) -> None:
    issues = list(item.get("_schema_issues") or [])
    if not issues:
        return

    source_name = _source_name(source)
    if source_name in _GOVERNED_SOURCES:
        if all(field in item for field in ("stress_class", "cost_class", "support_only", "meaningful_stress")):
            issues = [issue for issue in issues if issue not in _GOVERNANCE_ISSUES]

        if source_name in _CONDITIONING_SOURCES:
            # work_sec/rest_sec/rounds/total_minutes are alternative dose shapes,
            # not four mandatory fields. Technical footwork has its own explicit
            # timed-or-rep dose validator.
            issues = [issue for issue in issues if issue not in _OPTIONAL_CONDITIONING_DOSE_ISSUES]
            if _effective_rpe(item) is not None:
                issues = [issue for issue in issues if issue not in {"missing_rpe", "missing_rpe_max"}]

        if item.get("late_windows"):
            issues = [issue for issue in issues if issue != "missing_late_windows"]

    if issues:
        item["_schema_issues"] = list(dict.fromkeys(issues))
    else:
        item.pop("_schema_issues", None)


def _install_boxing_primary_preference() -> None:
    from . import conditioning_boxing

    current = conditioning_boxing._boxing_aerobic_preference_rank
    if getattr(current, "_bank_governance_installed", False):
        return

    original = current

    def _rank(drill: dict, **kwargs) -> int:
        rank = original(drill, **kwargs)
        # support_only means exactly that: it may fill a support/recovery need,
        # but it must not outrank a meaningful aerobic candidate for the main
        # boxing aerobic slot. If support is all that survives safety filtering,
        # it remains selectable.
        if drill.get("support_only") is True and drill.get("meaningful_stress") is False:
            return max(rank, 50)
        return rank

    _rank._bank_governance_installed = True  # type: ignore[attr-defined]
    conditioning_boxing._boxing_aerobic_preference_rank = _rank


def install() -> None:
    current = bank_schema.validate_training_item
    if getattr(current, "_bank_governance_installed", False):
        _install_boxing_primary_preference()
        return

    original = current

    def _validate_training_item(
        item: dict,
        *,
        source: str,
        require_phases: bool = True,
        require_system: bool = False,
        mode: bank_schema.ValidationMode = "runtime",
    ) -> dict:
        apply_bank_metadata(item, source=source)

        # The legacy validator marks every optional conditioning dose field and
        # both rpe/rpe_max independently. Run its safety checks, then reconcile
        # those false positives against the actual alternative-field contract.
        delegated_mode = "runtime" if mode == "strict" else mode
        result = original(
            item,
            source=source,
            require_phases=require_phases,
            require_system=require_system,
            mode=delegated_mode,
        )
        _clean_runtime_schema_issues(result, source=source)

        if mode == "strict" and result.get("_schema_issues"):
            issues = ", ".join(result["_schema_issues"])
            raise ValueError(
                f"Unsafe bank metadata for '{result.get('name', '<unnamed>')}' in {source}: {issues}."
            )

        if mode == "runtime":
            bank_schema._mark_runtime_safety(result)

        return result

    _validate_training_item._bank_governance_installed = True  # type: ignore[attr-defined]
    bank_schema.validate_training_item = _validate_training_item
    _install_boxing_primary_preference()
