"""Deterministic-first authority + safety auditing for structured plans (PR-5).

Authority model (deterministic-first):

* Stage 1 ``computed_support`` owns deterministic truth — macros, hydration,
  weight-cut risk, recovery rules, and mindset classification.
* Stage 2 / the structured_plan conversion own *contextual wording and
  placement* only, never the numbers/safety/risk/classification.
* The frontend displays cleanly and must NOT resolve truth conflicts.
* ``coach_gated`` content (acute weight-cut + supplement dosing) must never be
  athlete-facing.

These helpers are DEBUG-ONLY. They never mutate the plan and never resolve a
conflict; they only surface leakage / conflicts / duplicates as warning strings
so regressions are visible in the structured debug metadata. Conflict resolution
stays with the deterministic layer, never here and never the frontend.
"""
from __future__ import annotations

import re
from typing import Any

# Warning prefixes so findings are greppable in debug metadata.
LEAKAGE = "LEAKAGE"
CONFLICT = "CONFLICT"
DUPLICATE = "DUPLICATE"

# High-signal coach/medical dosing tokens. Only flagged when they actually
# appear in the computed_support ``coach_gated`` payload (so generic plan wording
# is never falsely flagged), then matched against athlete-facing text.
_SENTINEL_TOKEN_RES = {
    "bicarbonate": re.compile(r"\bbicarbonate\b", re.I),
    "magnesium": re.compile(r"\bmagnesium\b", re.I),
    "taurine": re.compile(r"\btaurine\b", re.I),
    "mmol": re.compile(r"\bmmol\b", re.I),
    "g/kg": re.compile(r"\d+(?:\.\d+)?\s*g\s*/\s*kg", re.I),
    "refeed": re.compile(r"\brefeed\b", re.I),
}


def _normalize(text: Any) -> str:
    """Lowercase, collapse whitespace — for substring/equality comparisons."""
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _string_leaves(node: Any) -> list[str]:
    """All non-empty string leaf values in a nested dict/list structure."""
    out: list[str] = []
    if isinstance(node, str):
        if node.strip():
            out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_string_leaves(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_string_leaves(item))
    return out


# --- athlete-facing text collection ----------------------------------------


def _mindset_lines(anchor: Any) -> list[str]:
    anchor = _as_dict(anchor)
    return [
        str(anchor.get(key) or "")
        for key in ("intent", "focus_cue", "reset_cue", "confidence_anchor", "context")
        if anchor.get(key)
    ]


def athlete_facing_strings(structured_plan: dict) -> list[str]:
    """Every string an athlete could see in the structured plan.

    Deliberately excludes ``raw_markdown_fallback`` (a verbatim copy of the
    source plan, audited separately) and machine-only fields.
    """
    plan = _as_dict(structured_plan)
    strings: list[str] = []

    nutrition = _as_dict(plan.get("nutrition"))
    for key in ("summary", "daily_focus", "training_day_guidance", "fight_week_guidance"):
        if nutrition.get(key):
            strings.append(str(nutrition[key]))
    wcw = _as_dict(nutrition.get("weight_cut_warning"))
    if wcw.get("display_text"):
        strings.append(str(wcw["display_text"]))

    for rule in _as_list(plan.get("red_flag_rules")):
        rule = _as_dict(rule)
        for key in ("display_text", "action"):
            if rule.get(key):
                strings.append(str(rule[key]))

    for week in _as_list(plan.get("weeks")):
        for day in _as_list(_as_dict(week).get("days")):
            day = _as_dict(day)
            card = _as_dict(day.get("today_card"))
            for key in ("headline", "primary_warning", "nutrition_summary", "weight_cut_warning"):
                if card.get(key):
                    strings.append(str(card[key]))
            strings.extend(_mindset_lines(card.get("mindset_anchor")))
            for session in _as_list(day.get("sessions")):
                session = _as_dict(session)
                strings.extend(_mindset_lines(session.get("mindset_anchor")))
                for block in _as_list(session.get("blocks")):
                    block = _as_dict(block)
                    if block.get("purpose"):
                        strings.append(str(block["purpose"]))
                    for key in ("coaching_cues", "regression_options", "substitutions"):
                        strings.extend(str(x) for x in _as_list(block.get(key)) if x)
                    if block.get("progression_rule"):
                        strings.append(str(block["progression_rule"]))
    return strings


# --- coach_gated leakage ----------------------------------------------------


def _coach_gated_payloads(computed_support: dict) -> list[Any]:
    support = _as_dict(computed_support)
    payloads: list[Any] = []
    for section in ("nutrition", "recovery"):
        by_phase = _as_dict(_as_dict(support.get(section)).get("by_phase"))
        for phase_block in by_phase.values():
            gated = _as_dict(phase_block).get("coach_gated")
            if gated:
                payloads.append(gated)
    return payloads


def detect_coach_gated_leakage(structured_plan: dict, computed_support: dict | None) -> list[str]:
    """Flag coach/medical-gated dosing copied into athlete-facing fields."""
    payloads = _coach_gated_payloads(_as_dict(computed_support))
    if not payloads:
        return []

    athlete_blob = _normalize(" || ".join(athlete_facing_strings(structured_plan)))
    if not athlete_blob:
        return []

    warnings: list[str] = []
    seen: set[str] = set()

    # 1) Whole gated phrases copied through verbatim.
    for payload in payloads:
        for leaf in _string_leaves(payload):
            norm = _normalize(leaf)
            if len(norm) >= 12 and norm in athlete_blob and norm not in seen:
                seen.add(norm)
                snippet = leaf if len(leaf) <= 60 else leaf[:57] + "..."
                warnings.append(f"{LEAKAGE}: coach_gated text surfaced athlete-facing: {snippet!r}")

    # 2) High-signal dosing tokens that exist in coach_gated and leaked through.
    gated_blob = _normalize(" ".join(leaf for p in payloads for leaf in _string_leaves(p)))
    for token, pattern in _SENTINEL_TOKEN_RES.items():
        if pattern.search(gated_blob) and pattern.search(athlete_blob) and token not in seen:
            seen.add(token)
            warnings.append(f"{LEAKAGE}: coach_gated dosing token {token!r} surfaced athlete-facing")
    return warnings


# --- duplicate rendered strings --------------------------------------------


def detect_duplicate_rendered_strings(structured_plan: dict) -> list[str]:
    """Flag obvious exact-duplicate normalized strings across rendered fields.

    The frontend suppresses duplicates, but the conversion should not emit
    identical day/session mindset anchors or echo the plan nutrition summary
    into every day card.
    """
    plan = _as_dict(structured_plan)
    warnings: list[str] = []

    plan_nutrition_summary = _normalize(_as_dict(plan.get("nutrition")).get("summary"))

    for week in _as_list(plan.get("weeks")):
        for day in _as_list(_as_dict(week).get("days")):
            day = _as_dict(day)
            date = day.get("date", "?")
            card = _as_dict(day.get("today_card"))
            day_anchor = tuple(_normalize(x) for x in _mindset_lines(card.get("mindset_anchor")))

            if plan_nutrition_summary and _normalize(card.get("nutrition_summary")) == plan_nutrition_summary:
                warnings.append(
                    f"{DUPLICATE}: today_card.nutrition_summary duplicates plan nutrition.summary on {date}"
                )

            for session in _as_list(day.get("sessions")):
                session = _as_dict(session)
                session_anchor = tuple(
                    _normalize(x) for x in _mindset_lines(session.get("mindset_anchor"))
                )
                if day_anchor and session_anchor and session_anchor == day_anchor:
                    warnings.append(
                        f"{DUPLICATE}: session mindset_anchor identical to day mindset_anchor on {date}"
                    )
    return warnings


# --- computed_support vs structured_plan conflicts -------------------------


def _macro_envelope(computed_support: dict, macro_key: str, unit_key: str = "min") -> tuple[float, float] | None:
    """Acceptable [min, max] envelope for a macro across all computed phases."""
    by_phase = _as_dict(_as_dict(_as_dict(computed_support).get("nutrition")).get("by_phase"))
    mins: list[float] = []
    maxs: list[float] = []
    for phase_block in by_phase.values():
        macro = _as_dict(_as_dict(phase_block).get(macro_key))
        lo, hi = macro.get("min"), macro.get("max")
        if isinstance(lo, (int, float)):
            mins.append(float(lo))
        if isinstance(hi, (int, float)):
            maxs.append(float(hi))
    if not mins and not maxs:
        return None
    lo = min(mins) if mins else 0.0
    hi = max(maxs) if maxs else float("inf")
    return lo, hi


def _stated_values(text: str, anchor: str, unit: str) -> list[tuple[float, float]]:
    """Pull ``<a>[-<b>] <unit>`` numbers stated near an anchor word."""
    out: list[tuple[float, float]] = []
    pattern = re.compile(
        rf"{anchor}[^.\n]{{0,40}}?(\d+(?:\.\d+)?)\s*(?:[-–]\s*(\d+(?:\.\d+)?))?\s*{unit}",
        re.I,
    )
    for match in pattern.finditer(text):
        lo = float(match.group(1))
        hi = float(match.group(2)) if match.group(2) else lo
        out.append((min(lo, hi), max(lo, hi)))
    return out


def _ranges_overlap(a: tuple[float, float], b: tuple[float, float], tol: float = 0.1) -> bool:
    lo = b[0] * (1 - tol)
    hi = b[1] * (1 + tol)
    return not (a[1] < lo or a[0] > hi)


_BAND_RANK = {"none": 0, "green": 0, "moderate": 1, "amber": 1, "high": 2, "severe": 2, "red": 2}


def _max_computed_band(computed_support: dict) -> str:
    by_phase = _as_dict(_as_dict(_as_dict(computed_support).get("nutrition")).get("by_phase"))
    best = "none"
    for phase_block in by_phase.values():
        band = str(_as_dict(_as_dict(phase_block).get("weight_cut")).get("risk_band", "none"))
        if _BAND_RANK.get(band, 0) > _BAND_RANK.get(best, 0):
            best = band
    return best


def detect_computed_support_conflicts(structured_plan: dict, computed_support: dict | None) -> list[str]:
    """Flag structured_plan values that contradict deterministic computed truth.

    Covers macros, hydration, and weight-cut risk band. Only the dangerous
    direction (structured contradicts / under-states the deterministic value) is
    flagged; matching values produce nothing.
    """
    support = _as_dict(computed_support)
    if not support:
        return []
    plan = _as_dict(structured_plan)
    warnings: list[str] = []

    nutrition = _as_dict(plan.get("nutrition"))
    nutrition_text = " \n ".join(
        str(nutrition.get(k) or "")
        for k in ("summary", "daily_focus", "training_day_guidance", "fight_week_guidance")
    )
    for week in _as_list(plan.get("weeks")):
        for day in _as_list(_as_dict(week).get("days")):
            card = _as_dict(_as_dict(day).get("today_card"))
            if card.get("nutrition_summary"):
                nutrition_text += " \n " + str(card["nutrition_summary"])

    # Macros.
    for macro_key, anchor in (
        ("protein_g_per_day", "protein"),
        ("carbs_g_per_day", r"carb\w*"),
        ("fats_g_per_day", r"fat\w*"),
    ):
        envelope = _macro_envelope(support, macro_key)
        if not envelope:
            continue
        for stated in _stated_values(nutrition_text, anchor, "g"):
            if not _ranges_overlap(stated, envelope):
                warnings.append(
                    f"{CONFLICT}: {macro_key} stated {stated} contradicts computed_support {envelope}"
                )
                break

    # Hydration (ml).
    hydration_env = _macro_envelope(support, "hydration_ml_per_day")
    if hydration_env:
        for stated in _stated_values(nutrition_text, r"(?:hydration|fluid|water|drink)", "ml"):
            if not _ranges_overlap(stated, hydration_env):
                warnings.append(
                    f"{CONFLICT}: hydration_ml_per_day stated {stated} contradicts computed_support {hydration_env}"
                )
                break

    # Weight-cut risk band.
    computed_band = _max_computed_band(support)
    expected_rank = _BAND_RANK.get(computed_band, 0)
    wcw = _as_dict(nutrition.get("weight_cut_warning"))
    structured_level = str(wcw.get("risk_level", "")) if wcw else ""
    if expected_rank >= 1:
        if not wcw:
            warnings.append(
                f"{CONFLICT}: computed weight-cut risk band {computed_band!r} but structured plan has no weight_cut_warning"
            )
        else:
            structured_rank = _BAND_RANK.get(structured_level, 0)
            if structured_rank < expected_rank:
                warnings.append(
                    f"{CONFLICT}: weight-cut risk understated — computed {computed_band!r} vs structured {structured_level!r}"
                )
    return warnings


def audit_structured_plan(structured_plan: dict, computed_support: dict | None = None) -> list[str]:
    """Run all debug-only safety audits, returning prefixed warning strings.

    Empty list means clean. Never raises (auditing must never break the plan).
    """
    try:
        findings: list[str] = []
        findings.extend(detect_coach_gated_leakage(structured_plan, computed_support))
        findings.extend(detect_computed_support_conflicts(structured_plan, computed_support))
        findings.extend(detect_duplicate_rendered_strings(structured_plan))
        return findings
    except Exception:  # auditing is best-effort and must never block a plan
        return []
