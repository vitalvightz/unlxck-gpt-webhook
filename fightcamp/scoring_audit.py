"""scoring_audit.py — Unified scoring audit layer for the Unlxck planner.

This module provides:
- A stable per-candidate audit schema (build_candidate_audit)
- A central constants/multipliers registry (SCORING_CONSTANTS, get_constants_snapshot)
- Score-delta helpers (score_deltas)
- A side-by-side candidate comparison utility (compare_candidates)
- A reservoir builder that captures selected + top-rejected candidates
  (build_audit_reservoir)

Enabling debug mode
-------------------
Pass ``debug_scoring=True`` (or ``audit_selector=True``) inside the ``flags``
dict handed to ``generate_strength_block`` or ``generate_conditioning_block``.
Both functions return an ``audit`` key in their result when the flag is active.
No audit data is computed or returned in production paths.

Quick usage
-----------
>>> from fightcamp.scoring_audit import build_candidate_audit, compare_candidates
>>> audit = build_candidate_audit(
...     name="Romanian Deadlift",
...     module="strength",
...     system=None,
...     category="hinge",
...     tags=["posterior_chain", "hinge"],
...     cluster_ids=[],
...     base_score=0.0,
...     goal_score=0.5,
...     weakness_score=1.2,
...     style_score=0.3,
...     cluster_score=0.0,
...     quality_adjustment=0.25,
...     restriction_penalty=0.0,
...     fallback_penalty=0.0,
...     injury_guard_adjustment=0.0,
...     fallback_class="normal",
...     injury_decision="pass",
...     reasons={"goal_hits": 1, "weakness_hits": 2},
...     final_score=2.25,
...     selected=True,
...     selection_stage="primary_scoring",
... )
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Central constants / multipliers registry
# ---------------------------------------------------------------------------

#: All meaningful hardcoded scoring values in the planner, organised by area.
#: Update this dict whenever a weight changes anywhere in the codebase.
SCORING_CONSTANTS: dict[str, Any] = {
    # ── Strength scorer (strength.py / score_exercise) ──────────────────────
    "strength": {
        "weakness_weight": 0.6,         # per tag hit
        "goal_weight": 0.5,             # per tag hit
        "style_weight": 0.3,            # per tag hit (base)
        "style_bonus_2_tags": 0.2,      # bonus when exactly 2 style tags match
        "style_bonus_3plus_tags": 0.1,  # bonus when 3+ style tags match
        "must_have_weight": 0.35,       # per must-have tag hit
        "must_have_bonus_tags_weight": 0.15,  # per bonus-category tag hit
        "multi_tag_synergy_bonus": 0.2, # added when total hits >= 3
        "phase_tag_weight": 0.4,        # per phase tag hit
        "fatigue_penalty_high": -0.75,
        "fatigue_penalty_moderate": -0.35,
        "rehab_penalty_gpp": -0.7,
        "rehab_penalty_spp": -1.0,
        "rehab_penalty_taper": -0.75,
        "equipment_boost": 0.25,        # phase-equipment bonus
        "noise_range": (-0.15, 0.15),   # uniform random noise
        "cluster_bonus_per_hit": 1.2,   # strength cluster bonus
        "boxing_footwork_specific_bonus": 0.6,
        "boxing_footwork_generic_single_leg_penalty": -1.15,
    },

    # ── Conditioning scorer (conditioning.py) ────────────────────────────────
    "conditioning": {
        # main bank weights
        "primary_weakness_weight": 2.75,
        "secondary_weakness_weight": 1.25,
        "primary_goal_weight": 2.1,
        "secondary_goal_weight": 0.9,
        "primary_style_weight": 0.85,
        "secondary_style_weight": 0.35,
        "format_tag_weight": 1.0,
        "cluster_bonus_per_hit": 1.35,
        # style-conditioning bank weights
        "style_base_bonus": 0.75,       # style match already guaranteed
        "style_phase_bonus": 1.0,       # phase match
        "style_top_system_bonus": 0.75,
        "style_equipment_bonus": 0.5,
        "style_primary_weakness_weight": 0.7,
        "style_secondary_weakness_weight": 0.35,
        "style_primary_goal_weight": 0.55,
        "style_secondary_goal_weight": 0.25,
        "style_cluster_bonus_per_hit": 1.35,
        # penalties
        "high_cns_fatigue_high_penalty": -2.0,
        "high_cns_fatigue_moderate_penalty": -1.0,
        "style_high_cns_fatigue_high_penalty": -1.0,
        "style_high_cns_fatigue_moderate_penalty": -0.5,
        "support_flag_high_cns_penalty": -0.4,
    },

    # ── Boxing aerobic priority adjustments ──────────────────────────────────
    "boxing_aerobic": {
        "bike_bonus": 1.5,
        "swim_bonus": 1.1,
        "swim_penalty_upper_body_sensitive": -0.6,
        "shadow_bonus": 0.9,
        "shadow_penalty_lower_limb_or_impact": -0.5,
        "sled_bonus": 0.75,
        "sled_penalty_lower_limb": -0.35,
        "walk_base_bonus": 0.45,
        "walk_bonus_impact_reduced": 0.35,
        "walk_bonus_tissue_irritation": 0.15,
        "walk_penalty_lower_limb": -0.6,
        "partner_tempo_base": 0.55,
        "partner_tempo_bonus_impact": 0.25,
        "partner_tempo_penalty_lower_limb": -0.15,
        "pool_tread_strong_case": 1.15,
        "pool_tread_justified": -0.25,
        "pool_tread_no_case": -2.0,
        "run_base_penalty": -0.1,
        "run_penalty_impact_reduced": -1.0,
        "run_penalty_tissue_irritation": -0.6,
        "run_penalty_lower_limb": -0.35,
    },

    # ── Fallback class penalties (selector_policy.py) ────────────────────────
    "fallback_class_penalties": {
        "normal": 0.0,
        "downranked": -1.25,
        "last_resort": -4.0,
        "blocked_for_profile": -999.0,
    },

    # ── Restriction filtering (restriction_filtering.py) ─────────────────────
    "restriction": {
        "limit_penalty": -0.75,  # max restriction penalty applied per candidate
    },

    # ── Strength quality adjustments (strength_session_quality.py) ───────────
    "quality_classes": {
        "anchor_loaded": {"weight": "high", "fatigue_cost_base": 3.0},
        "anchor_power": {"weight": "high", "fatigue_cost_base": 2.5},
        "anchor_force_isometric": {"weight": "medium", "fatigue_cost_base": 2.0},
        "support_isometric": {"weight": "medium", "fatigue_cost_base": 1.5},
        "support_accessory": {"weight": "low", "fatigue_cost_base": 1.0},
        "rehab_support": {"weight": "minimal", "fatigue_cost_base": 0.5},
    },
    "fatigue_cost_high_volume_add": 1.0,
    "fatigue_cost_explosive_tags_add": 0.5,
    "fatigue_cost_heavy_equipment_add": 0.5,

    # ── Style insertion margins (strength.py) ────────────────────────────────
    "style_insert_score_margin": {
        "GPP": 0.2,
        "SPP": 0.35,
        "TAPER": 0.15,
    },

    # ── Session support cap ───────────────────────────────────────────────────
    "session_support_cap_multiplier": 2,

    # ── Phase system ratios (config.py) ──────────────────────────────────────
    "phase_system_ratios": {
        "GPP": {"aerobic": 0.5, "glycolytic": 0.3, "alactic": 0.2},
        "SPP": {"glycolytic": 0.5, "alactic": 0.3, "aerobic": 0.2},
        "TAPER": {"alactic": 0.7, "aerobic": 0.3, "glycolytic": 0.0},
    },

    # ── Style conditioning ratio (config.py) ─────────────────────────────────
    "style_conditioning_ratio": {
        "GPP": 0.10,
        "SPP": 0.35,
        "TAPER": 0.00,
    },

    # ── Coordination scorer (conditioning.py / select_coordination_drill) ────
    "coordination": {
        "focus_tag_weight": 1.5,   # per coordination/footwork/balance/anti_rot/rot hit
        "boxing_sport_bonus": 1.0,
        "style_key_bonus": 0.8,
        "cluster_bonus_per_hit": 1.0,
    },
}


def get_constants_snapshot() -> dict[str, Any]:
    """Return a deep copy of the full scoring constants registry.

    Use this to record *"what numbers governed this run"* alongside an audit
    report, or to verify weights in tests.

    Returns
    -------
    dict
        A copy of :data:`SCORING_CONSTANTS`.
    """
    import copy
    return copy.deepcopy(SCORING_CONSTANTS)


# ---------------------------------------------------------------------------
# Audit schema builder
# ---------------------------------------------------------------------------

def build_candidate_audit(
    *,
    name: str,
    module: str,
    system: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    cluster_ids: list[str] | None = None,
    # positive contributions
    base_score: float = 0.0,
    goal_score: float = 0.0,
    weakness_score: float = 0.0,
    style_score: float = 0.0,
    cluster_score: float = 0.0,
    quality_adjustment: float = 0.0,
    # negative / contextual adjustments
    support_flag_adjustment: float = 0.0,
    restriction_penalty: float = 0.0,
    fallback_penalty: float = 0.0,
    constraint_adjustment: float = 0.0,
    injury_guard_adjustment: float = 0.0,
    # classification fields
    fallback_class: str = "normal",
    constraint_state: str = "",
    injury_decision: str = "pass",
    # detailed breakdown
    reasons: dict[str, Any] | None = None,
    # final decision
    final_score: float = 0.0,
    selected: bool = False,
    selection_stage: str = "",
    rejection_reason: str = "",
) -> dict[str, Any]:
    """Build a stable per-candidate audit record.

    All arguments are keyword-only to prevent order-dependent bugs when adding
    new fields in future patches.

    Parameters
    ----------
    name:
        Drill / exercise name.
    module:
        ``"strength"``, ``"conditioning"``, or ``"coordination"``.
    system:
        Energy system (conditioning only; ``None`` for strength).
    category:
        Category string from the drill bank entry.
    tags:
        Normalised tag list for the candidate.
    cluster_ids:
        Active cluster IDs that matched this candidate.
    base_score:
        Score before any tag-based contributions (often 0).
    goal_score:
        Total score from goal-tag hits.
    weakness_score:
        Total score from weakness-tag hits.
    style_score:
        Total score from style/tactical-tag hits.
    cluster_score:
        Total score from cluster ID hits.
    quality_adjustment:
        Signed adjustment from strength quality classification.
    support_flag_adjustment:
        Penalty when support flags suppress high-CNS drills.
    restriction_penalty:
        Penalty applied by restriction_filtering.
    fallback_penalty:
        Penalty from fallback class downgrade.
    constraint_adjustment:
        Any additional constraint-sensitivity penalty.
    injury_guard_adjustment:
        Penalty or zero when injury guard acts on this candidate.
    fallback_class:
        ``"normal"``, ``"downranked"``, ``"last_resort"``, or
        ``"blocked_for_profile"``.
    constraint_state:
        Human-readable constraint context (e.g. ``"high_impact_restricted"``).
    injury_decision:
        ``"pass"``, ``"exclude"``, or ``"replaced"``.
    reasons:
        Module-specific detailed score component dict.
    final_score:
        The score used for ranking after all adjustments.
    selected:
        ``True`` if this candidate was chosen.
    selection_stage:
        E.g. ``"primary_scoring"``, ``"style_injection"``,
        ``"universal_fallback"``, ``"injury_replacement"``.
    rejection_reason:
        Concise reason a candidate was not selected (empty when selected).

    Returns
    -------
    dict
        A fully populated audit record conforming to the unified schema.
    """
    positive_contributions = [
        base_score,
        goal_score,
        weakness_score,
        style_score,
        cluster_score,
        max(quality_adjustment, 0.0),
    ]
    negative_contributions = [
        min(quality_adjustment, 0.0),
        support_flag_adjustment if support_flag_adjustment < 0 else 0.0,
        restriction_penalty if restriction_penalty < 0 else 0.0,
        fallback_penalty if fallback_penalty < 0 else 0.0,
        constraint_adjustment if constraint_adjustment < 0 else 0.0,
        injury_guard_adjustment if injury_guard_adjustment < 0 else 0.0,
    ]
    positive_total = round(sum(positive_contributions), 4)
    negative_total = round(sum(negative_contributions), 4)
    net_score = round(positive_total + negative_total, 4)

    return {
        "name": name,
        "module": module,
        "system": system,
        "category": category,
        "tags": list(tags or []),
        "cluster_ids": list(cluster_ids or []),
        # component scores
        "base_score": round(base_score, 4),
        "goal_score": round(goal_score, 4),
        "weakness_score": round(weakness_score, 4),
        "style_score": round(style_score, 4),
        "cluster_score": round(cluster_score, 4),
        "quality_adjustment": round(quality_adjustment, 4),
        # adjustments / penalties
        "support_flag_adjustment": round(support_flag_adjustment, 4),
        "restriction_penalty": round(restriction_penalty, 4),
        "fallback_penalty": round(fallback_penalty, 4),
        "constraint_adjustment": round(constraint_adjustment, 4),
        "injury_guard_adjustment": round(injury_guard_adjustment, 4),
        # classification
        "fallback_class": fallback_class,
        "constraint_state": constraint_state,
        "injury_decision": injury_decision,
        # breakdown
        "reasons": dict(reasons or {}),
        # delta helpers
        "positive_total": positive_total,
        "negative_total": negative_total,
        "net_score": net_score,
        # decision
        "final_score": round(final_score, 4),
        "selected": bool(selected),
        "selection_stage": selection_stage,
        "rejection_reason": rejection_reason,
    }


# ---------------------------------------------------------------------------
# Score-delta helpers
# ---------------------------------------------------------------------------

def score_deltas(audit: dict[str, Any]) -> dict[str, float]:
    """Return a concise delta summary for a single audit record.

    Parameters
    ----------
    audit:
        An audit record produced by :func:`build_candidate_audit`.

    Returns
    -------
    dict with keys:
        ``positive_total``, ``negative_total``, ``net_score``, ``final_score``
    """
    return {
        "positive_total": audit.get("positive_total", 0.0),
        "negative_total": audit.get("negative_total", 0.0),
        "net_score": audit.get("net_score", 0.0),
        "final_score": audit.get("final_score", 0.0),
    }


# ---------------------------------------------------------------------------
# Comparison utility
# ---------------------------------------------------------------------------

_AUDIT_NUMERIC_FIELDS = (
    "base_score",
    "goal_score",
    "weakness_score",
    "style_score",
    "cluster_score",
    "quality_adjustment",
    "support_flag_adjustment",
    "restriction_penalty",
    "fallback_penalty",
    "constraint_adjustment",
    "injury_guard_adjustment",
    "positive_total",
    "negative_total",
    "net_score",
    "final_score",
)


def compare_candidates(
    audit_a: dict[str, Any],
    audit_b: dict[str, Any],
) -> dict[str, Any]:
    """Compare two candidate audit records side by side.

    Parameters
    ----------
    audit_a, audit_b:
        Audit records from :func:`build_candidate_audit`.

    Returns
    -------
    dict containing:
        ``winner``
            Name of the higher-scoring candidate (or ``"tie"``).
        ``loser``
            Name of the lower-scoring candidate.
        ``reason``
            Brief human-readable explanation.
        ``score_components``
            Dict of ``{field: {"a": val, "b": val, "delta": val}}`` for all
            numeric fields that differ between the two records.
        ``all_components``
            Same structure as ``score_components`` but includes fields where
            both values are equal.
        ``classification``
            Dict comparing ``fallback_class``, ``injury_decision``,
            ``selection_stage``, and ``rejection_reason``.
    """
    score_a = audit_a.get("final_score", 0.0)
    score_b = audit_b.get("final_score", 0.0)
    name_a = audit_a.get("name", "A")
    name_b = audit_b.get("name", "B")

    if score_a > score_b:
        winner, loser = name_a, name_b
        reason = (
            f"{name_a} won with final_score={score_a:.4f} vs {score_b:.4f} "
            f"(delta={score_a - score_b:.4f})"
        )
    elif score_b > score_a:
        winner, loser = name_b, name_a
        reason = (
            f"{name_b} won with final_score={score_b:.4f} vs {score_a:.4f} "
            f"(delta={score_b - score_a:.4f})"
        )
    else:
        winner, loser = "tie", "tie"
        reason = f"Both candidates scored equally at {score_a:.4f}."

    all_components: dict[str, dict[str, float]] = {}
    different_components: dict[str, dict[str, float]] = {}
    for field in _AUDIT_NUMERIC_FIELDS:
        val_a = float(audit_a.get(field, 0.0))
        val_b = float(audit_b.get(field, 0.0))
        delta = round(val_a - val_b, 4)
        entry = {"a": round(val_a, 4), "b": round(val_b, 4), "delta": delta}
        all_components[field] = entry
        if val_a != val_b:
            different_components[field] = entry

    classification: dict[str, dict[str, str]] = {}
    for field in ("fallback_class", "injury_decision", "selection_stage", "rejection_reason"):
        val_a = str(audit_a.get(field, ""))
        val_b = str(audit_b.get(field, ""))
        classification[field] = {"a": val_a, "b": val_b, "same": str(val_a == val_b)}

    return {
        "candidate_a": name_a,
        "candidate_b": name_b,
        "winner": winner,
        "loser": loser,
        "reason": reason,
        "score_components": different_components,
        "all_components": all_components,
        "classification": classification,
    }


# ---------------------------------------------------------------------------
# Audit reservoir builder
# ---------------------------------------------------------------------------

def build_audit_reservoir(
    candidates: list[tuple[dict, float, dict]],
    selected_names: set[str],
    *,
    module: str,
    top_n: int = 10,
    gate_excluded: list[dict] | None = None,
    injury_excluded: list[dict] | None = None,
    restriction_blocked: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a ranked audit reservoir for a selector.

    Parameters
    ----------
    candidates:
        Scored candidates as ``(item_dict, score, reasons_dict)`` tuples,
        sorted by descending score.  Each tuple should come directly from the
        internal ``weighted_exercises`` / ``system_drills`` lists.
    selected_names:
        Set of candidate names that were ultimately selected.
    module:
        ``"strength"``, ``"conditioning"``, or ``"coordination"``.
    top_n:
        Maximum number of candidates to include in the reservoir (default 10).
    gate_excluded:
        Items removed before scoring (e.g. sport-context gate, phase gate,
        equipment gate).  Each entry should have at least a ``"name"`` key and
        a ``"gate_reason"`` key.
    injury_excluded:
        Items removed by the injury guard after shortlisting.
    restriction_blocked:
        Items blocked by restriction filtering (hard gate, not just penalised).

    Returns
    -------
    dict with keys:
        ``selected``
            List of audit records for selected candidates.
        ``rejected_top``
            List of audit records for the top-N rejected candidates
            (sorted by final_score descending).
        ``gate_excluded``
            Items removed before scoring.
        ``injury_excluded``
            Items removed by injury guard.
        ``restriction_blocked``
            Items blocked by restriction filtering.
        ``module``
            Module name.
        ``total_scored``
            How many candidates reached the scoring stage.
    """
    selected_records: list[dict] = []
    rejected_records: list[dict] = []

    top_candidates = candidates[:top_n]

    for item, score, reasons in top_candidates:
        name = item.get("name", "<unnamed>")
        is_selected = name in selected_names
        fallback_class = reasons.get("fallback_class", "normal")
        fallback_penalty = float(
            SCORING_CONSTANTS["fallback_class_penalties"].get(fallback_class, 0.0)
        )
        restriction_penalty = float(reasons.get("restriction_penalty", 0.0))
        quality_adjustment = float(reasons.get("quality_adjustment", 0.0))
        cluster_score = float(reasons.get("cluster_hits", 0)) * float(
            SCORING_CONSTANTS.get(module, {}).get("cluster_bonus_per_hit", 0.0)
        )

        # Derive component scores from the reasons breakdown
        if module == "conditioning":
            goal_score = float(
                reasons.get("primary_goal_hits", 0) * SCORING_CONSTANTS["conditioning"]["primary_goal_weight"]
                + reasons.get("secondary_goal_hits", 0) * SCORING_CONSTANTS["conditioning"]["secondary_goal_weight"]
            )
            weakness_score = float(
                reasons.get("primary_weakness_hits", 0) * SCORING_CONSTANTS["conditioning"]["primary_weakness_weight"]
                + reasons.get("secondary_weakness_hits", 0) * SCORING_CONSTANTS["conditioning"]["secondary_weakness_weight"]
            )
            style_score = float(
                reasons.get("primary_style_hits", 0) * SCORING_CONSTANTS["conditioning"]["primary_style_weight"]
                + reasons.get("secondary_style_hits", 0) * SCORING_CONSTANTS["conditioning"]["secondary_style_weight"]
            )
        else:
            # strength / coordination — use simpler per-hit weights
            goal_score = float(reasons.get("goal_hits", 0)) * SCORING_CONSTANTS["strength"]["goal_weight"]
            weakness_score = float(reasons.get("weakness_hits", 0)) * SCORING_CONSTANTS["strength"]["weakness_weight"]
            style_score = float(reasons.get("style_hits", 0)) * SCORING_CONSTANTS["strength"]["style_weight"]

        support_flag_adj = float(reasons.get("support_flag_adjustment", 0.0))
        injection_reason = reasons.get("injection_reason", "")

        audit = build_candidate_audit(
            name=name,
            module=module,
            system=item.get("system"),
            category=item.get("category"),
            tags=list(item.get("tags", [])),
            cluster_ids=list(item.get("cluster_ids", [])),
            base_score=0.0,
            goal_score=round(goal_score, 4),
            weakness_score=round(weakness_score, 4),
            style_score=round(style_score, 4),
            cluster_score=round(cluster_score, 4),
            quality_adjustment=round(quality_adjustment, 4),
            support_flag_adjustment=round(support_flag_adj, 4),
            restriction_penalty=round(restriction_penalty, 4),
            fallback_penalty=round(fallback_penalty, 4),
            injury_guard_adjustment=0.0,
            fallback_class=fallback_class,
            injury_decision="pass",
            reasons=reasons,
            final_score=round(score, 4),
            selected=is_selected,
            selection_stage=injection_reason or ("primary_scoring" if is_selected else ""),
            rejection_reason="" if is_selected else _infer_rejection_reason(reasons, fallback_class),
        )

        if is_selected:
            selected_records.append(audit)
        else:
            rejected_records.append(audit)

    # Ensure rejected list is sorted by score desc
    rejected_records.sort(key=lambda r: r["final_score"], reverse=True)

    return {
        "module": module,
        "total_scored": len(candidates),
        "selected": selected_records,
        "rejected_top": rejected_records,
        "gate_excluded": list(gate_excluded or []),
        "injury_excluded": list(injury_excluded or []),
        "restriction_blocked": list(restriction_blocked or []),
    }


def _infer_rejection_reason(reasons: dict[str, Any], fallback_class: str) -> str:
    """Derive a concise rejection reason from the scoring breakdown."""
    if fallback_class in {"blocked_for_profile", "last_resort"}:
        return f"fallback_class={fallback_class}"
    restriction_hits = reasons.get("restriction_hits", 0)
    if restriction_hits:
        return f"restriction_penalty (hits={restriction_hits})"
    penalty = reasons.get("penalties", 0.0)
    if penalty and penalty < -0.5:
        return f"score_penalty={round(penalty, 4)}"
    return "outscored_by_higher_ranked_candidate"


# ---------------------------------------------------------------------------
# Full debug report
# ---------------------------------------------------------------------------

def build_debug_report(
    *,
    module: str,
    phase: str,
    reservoir: dict[str, Any],
    constants_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bundle a complete debug report for one selector run.

    Parameters
    ----------
    module:
        ``"strength"``, ``"conditioning"``, or ``"coordination"``.
    phase:
        ``"GPP"``, ``"SPP"``, or ``"TAPER"``.
    reservoir:
        Output of :func:`build_audit_reservoir`.
    constants_snapshot:
        Output of :func:`get_constants_snapshot` (lazily computed if omitted).

    Returns
    -------
    dict
        ``{ "module", "phase", "constants", "reservoir" }``
    """
    return {
        "module": module,
        "phase": phase,
        "constants": constants_snapshot if constants_snapshot is not None else get_constants_snapshot(),
        "reservoir": reservoir,
    }
