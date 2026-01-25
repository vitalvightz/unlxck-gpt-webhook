from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable, Iterable

from .injury_exclusion_rules import INJURY_REGION_KEYWORDS
from .injury_filtering import injury_match_details, match_forbidden, normalize_injury_regions
from .injury_synonyms import parse_injury_phrase, remove_negated_phrases, split_injury_text
from .tagging import normalize_tags

logger = logging.getLogger(__name__)

INJURY_TYPE_SEVERITY = {
    "tightness": "mild",
    "soreness": "mild",
    "stiffness": "mild",
    "pain": "mild",
    "contusion": "mild",
    "sprain": "moderate",
    "strain": "moderate",
    "tendonitis": "moderate",
    "impingement": "moderate",
    "hyperextension": "moderate",
    "swelling": "severe",
    "instability": "severe",
    "unspecified": "moderate",
}

SEVERITY_WEIGHTS = {"mild": 0.7, "moderate": 1.0, "severe": 1.35}
SEVERITY_RANK = {"mild": 0, "moderate": 1, "severe": 2}
RISK_LEVEL_WEIGHTS = {"exclude": 1.0, "flag": 0.65}

REGION_RISK_WEIGHTS = {
    "shoulder": 1.2,
    "knee": 1.2,
    "ankle": 1.1,
    "shin": 1.0,
    "lower_back": 1.1,
    "upper_back": 1.05,
    "wrist": 1.0,
    "neck": 1.15,
    "hip": 1.05,
}

MATCH_RISK_MULTIPLIERS = [
    ({"high_impact_plyo", "landing_stress_high", "reactive_rebound_high", "impact_rebound_high", "foot_impact_high"}, 1.5),
    ({"max_velocity", "running_volume_high", "shin_splints_risk"}, 1.3),
    ({"overhead", "dynamic_overhead", "press_heavy"}, 1.1),
    ({"hinge_heavy", "lumbar_loaded", "axial_heavy", "posterior_chain_heavy"}, 1.2),
    ({"knee_dominant_heavy", "deep_flexion", "deep_knee_flexion_loaded"}, 1.15),
]

MODS_BY_REGION = {
    "shoulder": ["reduce_overhead", "limit_range", "slow_tempo"],
    "knee": ["reduce_impact", "shorten_range", "tempo_control"],
    "ankle": ["reduce_impact", "stable_surface", "short_stride"],
    "shin": ["reduce_impact", "swap_low_impact"],
    "lower_back": ["reduce_load", "neutral_spine", "short_range"],
    "upper_back": ["reduce_load", "support_chest"],
    "wrist": ["neutral_wrist", "reduced_extension"],
    "neck": ["no_load", "range_only"],
    "hip": ["reduce_depth", "tempo_control"],
}

FALLBACK_TAG_ORDER: dict[str, dict[str, list[list[str]]]] = {
    "shoulder": {
        "overhead": [["upper_pull", "row_heavy"], ["core", "stability"], ["mobility", "rehab_friendly"]],
        "press": [["upper_pull", "row_heavy"], ["core", "stability"], ["mobility", "rehab_friendly"]],
        "default": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
    },
    "knee": {
        "impact": [["low_impact", "aerobic"], ["mobility", "rehab_friendly"], ["core", "stability"]],
        "knee_load": [["hinge_heavy", "posterior_chain_heavy"], ["core", "stability"], ["mobility", "rehab_friendly"]],
        "default": [["low_impact", "aerobic"], ["core", "stability"], ["mobility", "rehab_friendly"]],
    },
    "ankle": {
        "impact": [["low_impact", "aerobic"], ["mobility", "rehab_friendly"], ["core", "stability"]],
        "default": [["low_impact", "aerobic"], ["mobility", "rehab_friendly"], ["core", "stability"]],
    },
    "shin": {
        "impact": [["low_impact", "aerobic"], ["mobility", "rehab_friendly"], ["core", "stability"]],
        "default": [["low_impact", "aerobic"], ["mobility", "rehab_friendly"], ["core", "stability"]],
    },
    "lower_back": {
        "hinge": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
        "default": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
    },
    "upper_back": {
        "hinge": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
        "default": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
    },
    "wrist": {
        "wrist_load": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
        "default": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
    },
    "neck": {
        "neck_load": [["mobility", "rehab_friendly"], ["core", "stability"], ["low_impact", "aerobic"]],
        "default": [["mobility", "rehab_friendly"], ["core", "stability"], ["low_impact", "aerobic"]],
    },
    "hip": {
        "hip_irritant": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
        "default": [["core", "stability"], ["mobility", "rehab_friendly"], ["low_impact", "aerobic"]],
    },
}

_INJURY_DECISION_LOGGED: set[tuple] = set()
_INJURY_DECISION_CACHE: dict[tuple[str, str, str, str], dict[str, object]] = {}


@dataclass(frozen=True)
class Decision:
    action: str
    risk_score: float
    threshold: float
    matched_tags: list[str]
    mods: list[str]
    reason: dict


def _normalize_injury_list(injuries: Iterable[str] | str | None) -> list[str]:
    if not injuries:
        return []
    if isinstance(injuries, str):
        return [injuries]
    return [str(i) for i in injuries if i]


def _map_text_to_region(text: str) -> str | None:
    for region, keywords in INJURY_REGION_KEYWORDS.items():
        if match_forbidden(text, keywords):
            return region
    return None


def _injury_context(injuries: Iterable[str]) -> dict[str, str]:
    region_severity: dict[str, str] = {}
    for injury in injuries:
        if not injury:
            continue
        for phrase in split_injury_text(str(injury)):
            cleaned = remove_negated_phrases(phrase)
            if not cleaned:
                continue
            itype, loc = parse_injury_phrase(phrase)
            itype = itype or ("unspecified" if loc else None)
            severity = INJURY_TYPE_SEVERITY.get(itype or "", "moderate")
            for candidate in (loc, itype, phrase):
                if not candidate:
                    continue
                region = _map_text_to_region(str(candidate))
                if region:
                    current = region_severity.get(region)
                    if current is None or SEVERITY_RANK[severity] > SEVERITY_RANK[current]:
                        region_severity[region] = severity
                    break
    for region in normalize_injury_regions(injuries):
        region_severity.setdefault(region, "moderate")
    return region_severity


def _thresholds(phase: str | None, fatigue: str | None) -> tuple[float, float]:
    modify_band = 0.85
    threshold = 1.2
    fatigue_key = (fatigue or "moderate").lower()
    if fatigue_key == "high":
        modify_band -= 0.1
        threshold -= 0.1
    elif fatigue_key == "low":
        modify_band += 0.05
    if (phase or "").upper() == "TAPER":
        threshold += 0.05
    return modify_band, threshold


def _bucket_from_match(tags: Iterable[str], patterns: Iterable[str]) -> str:
    tag_set = {t.lower() for t in tags}
    pattern_text = " ".join(patterns).lower()
    if tag_set & {"overhead", "dynamic_overhead", "press_heavy"} or "overhead" in pattern_text:
        return "overhead"
    if tag_set & {"high_impact_plyo", "landing_stress_high", "running_volume_high", "foot_impact_high"}:
        return "impact"
    if tag_set & {"knee_dominant_heavy", "deep_flexion", "deep_knee_flexion_loaded"} or "knee" in pattern_text:
        return "knee_load"
    if tag_set & {"hinge_heavy", "lumbar_loaded", "posterior_chain_heavy"} or "deadlift" in pattern_text:
        return "hinge"
    if tag_set & {"wrist_loaded_extension", "wrist_extension_high"} or "wrist" in pattern_text:
        return "wrist_load"
    if tag_set & {"neck_loaded", "neck_bridge", "cervical_load"} or "neck" in pattern_text:
        return "neck_load"
    if tag_set & {"hip_impingement_risk", "hip_irritant", "deep_flexion"} or "hip" in pattern_text:
        return "hip_irritant"
    if tag_set & {"press_heavy", "upper_push", "pec_loaded"} or "press" in pattern_text:
        return "press"
    return "default"


def _match_tags_from_detail(detail: dict) -> list[str]:
    tags = [t for t in detail.get("tags", []) if t]
    patterns = [p for p in detail.get("patterns", []) if p]
    keyword_tags = [f"keyword:{p}" for p in patterns]
    return sorted({*tags, *keyword_tags})


def _match_multiplier(tags: Iterable[str]) -> float:
    tag_set = {t.lower() for t in tags}
    multiplier = 1.0
    for tag_group, weight in MATCH_RISK_MULTIPLIERS:
        if tag_set & tag_group:
            multiplier = max(multiplier, weight)
    return multiplier


def _log_decision(
    *,
    item_name: str,
    region: str,
    severity: str,
    risk: float,
    threshold: float,
    matched_tags: list[str],
    action: str,
) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    log_key = (item_name, region, severity, round(risk, 3), round(threshold, 3), action, tuple(matched_tags))
    if log_key in _INJURY_DECISION_LOGGED:
        return
    _INJURY_DECISION_LOGGED.add(log_key)
    logger.debug(
        "[injury-guard] item='%s' region=%s severity=%s risk=%.2f threshold=%.2f matched_tags=%s action=%s",
        item_name,
        region,
        severity,
        risk,
        threshold,
        matched_tags,
        action,
    )


def injury_decision(exercise: dict, injuries: Iterable[str], phase: str, fatigue: str) -> Decision:
    injuries_list = _normalize_injury_list(injuries)
    if not injuries_list:
        return Decision(
            action="allow",
            risk_score=0.0,
            threshold=_thresholds(phase, fatigue)[1],
            matched_tags=[],
            mods=[],
            reason={"region": None, "severity": None, "bucket": "default", "matches": []},
        )

    name = str(exercise.get("name", "") or "") or "Unnamed"
    item_id = str(exercise.get("id") or name or id(exercise))
    region_severity = _injury_context(injuries_list)
    modify_band, threshold = _thresholds(phase, fatigue)
    threshold_version = f"{modify_band:.2f}:{threshold:.2f}"

    details = injury_match_details(
        exercise,
        injuries_list,
        risk_levels=("exclude", "flag"),
    )
    if not details:
        return Decision(
            action="allow",
            risk_score=0.0,
            threshold=threshold,
            matched_tags=[],
            mods=[],
            reason={"region": None, "severity": None, "bucket": "default", "matches": []},
        )

    max_detail_meta: dict[str, object] | None = None
    max_risk = 0.0
    details_by_region: dict[str, list[dict]] = {}
    for detail in details:
        details_by_region.setdefault(detail["region"], []).append(detail)

    for region, region_details in details_by_region.items():
        severity = region_severity.get(region, "moderate")
        cache_key = (item_id, region, severity, threshold_version)
        cached = _INJURY_DECISION_CACHE.get(cache_key)
        if cached:
            risk = float(cached["risk"])
            matched_tags = list(cached["matched_tags"])
            bucket = str(cached["bucket"])
            action = str(cached["action"])
        else:
            region_weight = REGION_RISK_WEIGHTS.get(region, 1.0)
            severity_weight = SEVERITY_WEIGHTS.get(severity, 1.0)
            max_region_detail = None
            max_region_risk = 0.0
            for detail in region_details:
                risk_level_weight = RISK_LEVEL_WEIGHTS.get(detail["risk_level"], 0.8)
                match_multiplier = _match_multiplier(detail.get("tags", []))
                risk = region_weight * severity_weight * risk_level_weight * match_multiplier
                if risk > max_region_risk:
                    max_region_risk = risk
                    max_region_detail = detail
            if not max_region_detail:
                continue
            matched_tags = _match_tags_from_detail(max_region_detail)
            bucket = _bucket_from_match(max_region_detail.get("tags", []), max_region_detail.get("patterns", []))
            if max_region_risk > threshold:
                action = "exclude"
            elif max_region_risk >= modify_band:
                action = "modify"
            else:
                action = "allow"
            _log_decision(
                item_name=name,
                region=region,
                severity=severity,
                risk=max_region_risk,
                threshold=threshold,
                matched_tags=matched_tags,
                action=action,
            )
            _INJURY_DECISION_CACHE[cache_key] = {
                "risk": max_region_risk,
                "matched_tags": matched_tags,
                "bucket": bucket,
                "action": action,
            }
            risk = max_region_risk

        if risk > max_risk:
            max_risk = risk
            max_detail_meta = {"region": region, "severity": severity, "bucket": bucket, "matched_tags": matched_tags}

    if not max_detail_meta:
        return Decision(
            action="allow",
            risk_score=0.0,
            threshold=threshold,
            matched_tags=[],
            mods=[],
            reason={"region": None, "severity": None, "bucket": "default", "matches": details},
        )

    region = str(max_detail_meta["region"])
    severity = str(max_detail_meta["severity"])
    matched_tags = list(max_detail_meta["matched_tags"])
    bucket = str(max_detail_meta["bucket"])
    if max_risk > threshold:
        action = "exclude"
    elif max_risk >= modify_band:
        action = "modify"
    else:
        action = "allow"

    mods = MODS_BY_REGION.get(region, []) if action == "modify" else []
    return Decision(
        action=action,
        risk_score=round(max_risk, 3),
        threshold=threshold,
        matched_tags=matched_tags,
        mods=mods,
        reason={
            "region": region,
            "severity": severity,
            "bucket": bucket,
            "matches": details,
        },
    )


def choose_injury_replacement(
    *,
    excluded_item: dict,
    candidates: list[dict],
    injuries: Iterable[str],
    phase: str,
    fatigue: str,
    score_fn: Callable[[dict], float] | None = None,
) -> dict | None:
    if not candidates:
        return None
    decision = injury_decision(excluded_item, injuries, phase, fatigue)
    region = decision.reason.get("region") if isinstance(decision.reason, dict) else None
    bucket = decision.reason.get("bucket") if isinstance(decision.reason, dict) else None
    fallback_groups = FALLBACK_TAG_ORDER.get(region or "", {}).get(bucket or "", [])
    if not fallback_groups:
        fallback_groups = FALLBACK_TAG_ORDER.get(region or "", {}).get("default", [])

    def sort_key(cand: dict) -> tuple:
        name = cand.get("name") or ""
        score = score_fn(cand) if score_fn else 0.0
        return (-score, name)

    sorted_candidates = sorted(candidates, key=sort_key)

    def is_safe(cand: dict) -> bool:
        cand_decision = injury_decision(cand, injuries, phase, fatigue)
        return cand_decision.action != "exclude"

    safe_candidates = [cand for cand in sorted_candidates if is_safe(cand)]
    if not safe_candidates:
        return None

    if fallback_groups:
        for group in fallback_groups:
            group_set = {t.lower() for t in group}
            for cand in safe_candidates:
                cand_tags = {t.lower() for t in normalize_tags(cand.get("tags", []))}
                if cand_tags & group_set:
                    return cand

    return safe_candidates[0]


def pick_safe_replacement(
    original: dict,
    candidates: Iterable[dict],
    injuries_ctx: dict,
    fallback_candidates: Iterable[dict] | None = None,
) -> tuple[dict | None, Decision | None]:
    injuries = injuries_ctx.get("injuries", [])
    phase = injuries_ctx.get("phase", "")
    fatigue = injuries_ctx.get("fatigue", "")

    def _first_safe(items: Iterable[dict]) -> tuple[dict | None, Decision | None]:
        for cand in items:
            decision = injury_decision(cand, injuries, phase, fatigue)
            if decision.action in {"allow", "modify"}:
                return cand, decision
        return None, None

    replacement, decision = _first_safe(candidates)
    if replacement:
        return replacement, decision

    if fallback_candidates:
        return _first_safe(fallback_candidates)

    return None, None
