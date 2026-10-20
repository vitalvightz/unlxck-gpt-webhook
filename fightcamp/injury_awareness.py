"""Awareness-only copy for injuries the athlete marked as not limiting.

PR #2867 removes a ``training_impact: not_limiting`` injury from every planning
path (selection, rehab, restrictions, Stage 2 context) once triage clears the
plan, so it can never change loading or scoring. That also removed the only
route by which the athlete was reminded of it: the plan lost its injury
"Active notes" entry and the re-injury stop rule.

This module restores that reminder deterministically and *only* as display
copy. It reads the stripped entries, never feeds back into planning, and is
merged onto the finished structured plan after the safety audit (see
``api.structured_plan_generation``), so the conversion model never sees it and
cannot turn it into restrictions.
"""

from __future__ import annotations

import re
from typing import Any

NOT_LIMITING = "not_limiting"
AWARENESS_SCHEMA_VERSION = "injury_awareness.v1"
_RULE_ID_PREFIX = "non_limiting_injury_reinjury"

_GENERIC_TYPES = {"", "unspecified", "unknown", "general", "pain", "injury", "none"}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ")).strip()


def _area_label(entry: dict[str, Any]) -> str:
    location = _clean(entry.get("guided_area")) or _clean(entry.get("canonical_location"))
    if not location or location.lower() in {"unspecified", "unknown"}:
        return ""
    # Guided areas can already carry the side ("left bicep"); strip it so the
    # side prefix below is never doubled ("left left bicep").
    side = _clean(entry.get("side") or entry.get("laterality")).lower()
    if side in {"left", "right", "bilateral"}:
        location = re.sub(r"^(?:left|right|both|bilateral)\s+", "", location, flags=re.IGNORECASE) or location
    if side in {"left", "right"}:
        return f"{side} {location}".lower()
    if side == "bilateral":
        return f"both {location}s".lower() if not location.endswith("s") else f"both {location}".lower()
    return location.lower()


def build_injury_awareness(entries: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Reduce non-limiting parsed injuries to display-only area/type records."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("training_impact") or "").strip().lower() != NOT_LIMITING:
            continue
        area = _area_label(entry)
        if not area or area in seen:
            continue
        seen.add(area)
        injury_type = _clean(entry.get("injury_type")).lower()
        if injury_type in _GENERIC_TYPES:
            injury_type = ""
        out.append({"area": area, "injury_type": injury_type})
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _describe(record: dict[str, str]) -> str:
    area = record["area"]
    injury_type = record.get("injury_type") or ""
    return f"{area} {injury_type}".strip() if injury_type else area


def awareness_plan_note(records: list[dict[str, str]]) -> dict[str, str] | None:
    """One calm injury note covering every non-limiting injury."""
    if not records:
        return None
    described = [_describe(r) for r in records]
    subject = described[0] if len(described) == 1 else ", ".join(described[:-1]) + f" and {described[-1]}"
    subject = subject[:1].upper() + subject[1:]
    plural = len(described) > 1 or records[0]["area"].startswith("both ")
    verb = "are" if plural else "is"
    return {
        "category": "injury",
        "label": "Injury - not limiting",
        "text": (
            f"{subject} {verb} logged as not limiting, so {'they do' if plural else 'it does'} not change your "
            f"loading or session choices. Warm {'them' if plural else 'it'} up properly, keep an eye on {'them' if plural else 'it'}, "
            "and log any change in your check-in."
        ),
    }


def awareness_red_flags(records: list[dict[str, str]]) -> list[dict[str, Any]]:
    """One re-injury stop rule per non-limiting injury area."""
    rules: list[dict[str, Any]] = []
    for record in records:
        area = record["area"]
        rules.append(
            {
                "rule_id": f"{_RULE_ID_PREFIX}_{_slug(area)}",
                "metric": "pain",
                "metric_group": "injury",
                "when": "during_session",
                "operator": ">",
                "threshold": 3.0,
                "severity": "amber",
                "applies_to": [],
                "display_text": (
                    f"If your {area} flares up - sharp pain, swelling, giving way, "
                    "or pain above 3/10 that builds during training - stop that work "
                    "and report it to your coach."
                ),
                "action": "Stop the aggravating work and log it in your check-in.",
                "needs_human_review": False,
            }
        )
    return rules


def build_injury_awareness_support(entries: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Deterministic awareness bundle carried on ``computed_support``."""
    records = build_injury_awareness(entries)
    if not records:
        return None
    return {
        "schema_version": AWARENESS_SCHEMA_VERSION,
        "training_impact": NOT_LIMITING,
        "injuries": records,
        "plan_note": awareness_plan_note(records),
        "red_flag_rules": awareness_red_flags(records),
    }


def _normalize(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def merge_injury_awareness(plan: dict[str, Any], awareness: dict[str, Any] | None) -> dict[str, Any]:
    """Add the awareness note / re-injury rules to a structured plan dict.

    Never removes or rewrites existing content. Skips an injury note when the
    plan already carries an injury note naming the same area, and skips a rule
    when one with the same id or an injury rule naming the area already exists.
    """
    if not isinstance(plan, dict) or not isinstance(awareness, dict):
        return plan
    records = [r for r in awareness.get("injuries") or [] if isinstance(r, dict) and r.get("area")]
    if not records:
        return plan

    notes = [n for n in plan.get("plan_notes") or [] if isinstance(n, dict)]
    injury_note_text = " ".join(
        _normalize(n.get("text")) for n in notes if n.get("category") == "injury"
    )
    note = awareness.get("plan_note")
    if isinstance(note, dict) and not all(
        _normalize(r["area"]) in injury_note_text for r in records
    ):
        notes = [*notes, dict(note)]

    rules = [r for r in plan.get("red_flag_rules") or [] if isinstance(r, dict)]
    existing_ids = {str(r.get("rule_id") or "") for r in rules}
    existing_texts = [_normalize(r.get("display_text")) for r in rules]
    for rule in awareness.get("red_flag_rules") or []:
        if not isinstance(rule, dict):
            continue
        if rule.get("rule_id") in existing_ids:
            continue
        area = next(
            (r["area"] for r in records if str(rule.get("rule_id", "")).endswith(_slug(r["area"]))),
            "",
        )
        area_norm = _normalize(area)
        if area_norm and any(
            area_norm in text and re.search(r"\b(stop|report)\b", text) for text in existing_texts
        ):
            continue
        rules.append(dict(rule))

    return {**plan, "plan_notes": notes, "red_flag_rules": rules}


# --- Athlete-reported functional impact ---------------------------------------
#
# The three athlete-facing choices (web/lib/injury-impact.ts) describe training
# impact, not a diagnosis. Their low/moderate/high and mild/moderate/severe
# bands are compatibility mappings; the marker below is the provenance.
LIMITING = "limiting"
CANT_TRAIN = "cant_train"
TRAINING_IMPACTS = frozenset({NOT_LIMITING, LIMITING, CANT_TRAIN})
_IMPACT_MARKER = re.compile(r"\[training_impact:(not_limiting|limiting|cant_train)\]", re.IGNORECASE)
_MEDICAL_MARKERS = ("medical_hold", "restriction_hold", "rehab_medical_gate", "progression_assessment_medical_hold",
                    "open_wound")


def reported_training_impact(record: dict[str, Any] | Any) -> str:
    """The athlete's own impact choice, or "" when missing/legacy."""
    if not hasattr(record, "get"):
        return ""
    explicit = str(record.get("training_impact") or "").strip().lower()
    if explicit in TRAINING_IMPACTS:
        return explicit
    for key in ("description", "notes"):
        match = _IMPACT_MARKER.search(str(record.get(key) or ""))
        if match:
            return match.group(1).lower()
    return ""


def has_independent_medical_override(record: dict[str, Any]) -> bool:
    """Safety evidence the athlete's impact choice can never override."""
    from .injury_registry import SURFACE_TISSUE_TYPES
    from .injury_triage import current_report_medical_hold_reasons

    if any(record.get(key) for key in _MEDICAL_MARKERS):
        return True
    if str(record.get("consequence") or "").strip().lower() in {"structural", "neuro"}:
        return True
    if str(record.get("latest_reported_status") or "").strip().lower() == "worse":
        return True
    types = {str(record.get(key) or "").strip().lower() for key in ("injury_type", "rehab_type", "surface_class")}
    if types & SURFACE_TISSUE_TYPES or any(t.startswith("surface_") for t in types):
        return True  # wound/contact restrictions stay with the surface pathway
    return bool(current_report_medical_hold_reasons(record))


def is_awareness_only(record: dict[str, Any]) -> bool:
    """A not-limiting injury that must not restrict normal training.

    Generation already removes these after triage (plan_pipeline_runtime);
    Today and the exercise editor use the same rule. Any independent medical
    evidence, a "worse" report or a severe/high band keeps it restrictive.
    """
    return (
        reported_training_impact(record) == NOT_LIMITING
        and str(record.get("severity") or "").strip().lower() not in {"severe", "high"}
        and not has_independent_medical_override(record)
    )


def is_functional_cant_train(record: dict[str, Any]) -> bool:
    """A severe band that only encodes the athlete's "can't train normally".

    It restricts normal training but is not medical severity: without other
    medical evidence it must not trigger a medical-review hold.
    """
    return (
        reported_training_impact(record) == CANT_TRAIN
        and str(record.get("severity") or "").strip().lower() in {"severe", "high"}
        and not has_independent_medical_override(record)
    )


def injury_stop_phrase(record: dict[str, Any], label: str) -> str:
    """Stop copy that keeps functional inability apart from medical severity."""
    if is_functional_cant_train(record):
        return f"Can't train normally: {label}"
    return f"Active severe injury: {label}"
