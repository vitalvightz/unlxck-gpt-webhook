from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from typing import Callable, Iterable

from .injury_exclusion_rules import INJURY_REGION_KEYWORDS
from .injury_filtering import injury_match_details, match_forbidden, normalize_injury_regions
from .injury_formatting import parse_injury_entry
from .restriction_parsing import is_restriction_phrase
from .injury_synonyms import parse_injury_phrase, remove_negated_phrases, split_injury_text
from .tagging import normalize_tags
# Import injury rules version for cache invalidation
from .config import INJURY_RULES_VERSION

logger = logging.getLogger(__name__)

INJURY_DEBUG = os.environ.get("INJURY_DEBUG", "0") == "1"


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

SEVERITY_SYNONYMS = {
    "high": [
        "pop",
        "popped",
        "snap",
        "snapped",
        "crack",
        "cracked",
        "crunch",
        "rupture",
        "ruptured",
        "tear",
        "torn",
        "complete tear",
        "full tear",
        "grade 3",
        "fracture",
        "broken",
        "bone",
        "dislocated",
        "out of socket",
        "separation",
        "detached",
        "blown out",
        "swelling",
        "swollen",
        "ballooned",
        "puffy",
        "inflammation",
        "inflamed",
        "hot",
        "heat",
        "bruise",
        "bruised",
        "bruising",
        "black and blue",
        "hematoma",
        "discoloration",
        "limp",
        "limping",
        "cannot walk",
        "cant walk",
        "can't walk",
        "painful to walk",
        "cannot stand",
        "cant stand",
        "can't stand",
        "cannot move",
        "cant move",
        "can't move",
        "cannot extend",
        "cant extend",
        "can't extend",
        "cannot bend",
        "cant bend",
        "can't bend",
        "giving way",
        "gave way",
        "buckled",
        "collapsed",
        "locked",
        "stuck",
        "frozen",
        "cannot sprint",
        "cant sprint",
        "can't sprint",
        "no power",
        "leg went",
        "knee went",
        "totally gone",
        "dead leg",
        "cannot rotate",
        "cant rotate",
        "can't rotate",
        "sharp",
        "stabbing",
        "shooting",
        "electric",
        "shocker",
        "agonizing",
        "screaming",
        "unbearable",
        "intense",
        "10/10",
        "9/10",
        "8/10",
        "severe",
        "extreme",
    ],
    "moderate": [
        "pull",
        "pulled",
        "strain",
        "strained",
        "grade 2",
        "partial tear",
        "fibers",
        "fibres",
        "torn slightly",
        "torn a bit",
        "meat tear",
        "muscle pull",
        "really tight",
        "very tight",
        "proper tight",
        "super tight",
        "dead tight",
        "locked up",
        "clamped",
        "seized",
        "spasm",
        "cramp",
        "cramping",
        "knot",
        "knotted",
        "limited rom",
        "limited range",
        "cannot fully",
        "cant fully",
        "can't fully",
        "painful to load",
        "painful to press",
        "painful to hinge",
        "hurts to",
        "restricted",
        "restriction",
        "heavy",
        "stodgy",
        "burning",
        "nerve pain",
        "cannot go 100",
        "cant go 100",
        "can't go 100",
        "half speed",
        "70%",
        "80%",
        "throbbing",
        "aching",
        "constant pain",
        "always there",
        "recurring",
        "always comes back",
        "aggravated",
        "flared up",
        "acting up",
        "nagging",
        "7/10",
        "6/10",
        "5/10",
        "4/10",
    ],
    "low": [
        "niggle",
        "niggling",
        "twinge",
        "tweak",
        "tweaked",
        "bit sore",
        "slight",
        "mild",
        "minor",
        "stiff",
        "stiffness",
        "tightness",
        "tightish",
        "bit tight",
        "feels a bit",
        "feels off",
        "feels funny",
        "awareness",
        "annoying",
        "bit of a",
        "touch of",
        "doms",
        "workout soreness",
        "training soreness",
        "post workout",
        "tender",
        "tenderness",
        "dull",
        "manageable",
        "little bit",
        "small",
        "achy",
        "fatigued",
        "tired",
        "1/10",
        "2/10",
        "3/10",
        "just a bit",
        "okay but",
        "stable",
        "fine but",
    ],
}

SEVERITY_WEIGHTS = {"low": 0.7, "moderate": 1.0, "high": 1.35}
SEVERITY_RANK = {"low": 0, "moderate": 1, "high": 2}
RISK_LEVEL_WEIGHTS = {"exclude": 1.0, "flag": 0.65}

REGION_RISK_WEIGHTS = {
    "shoulder": 1.2,
    "knee": 1.2,
    "achilles": 1.2,
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
    ({"max_velocity", "mech_max_velocity", "running_volume_high", "shin_splints_risk"}, 1.3),
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

# Enhanced cache with comprehensive key including all decision factors
# Cache key format: (item_id, region, severity, threshold_version, rules_version, tags_hash, module, bank)
# This ensures cache invalidation when:
# - Injury rules change (rules_version)
# - Exercise tags change (tags_hash)
# - Scoring thresholds change (threshold_version)
# - Item identity changes (item_id)
_INJURY_DECISION_CACHE: dict[tuple[str, ...], dict[str, object]] = {}
_INJURY_SEVERITY_DEBUGGED = False
_INJURY_PARSED_DEBUGGED = False


def _compute_tags_hash(tags: Iterable[str]) -> str:
    """
    Compute a stable hash of exercise/drill tags for cache key.
    
    Tags are sorted to ensure consistent hash regardless of order.
    This allows cache invalidation when tags change.
    
    Args:
        tags: List of tags to hash
        
    Returns:
        Hex digest of SHA256 hash (first 16 chars for brevity)
    """
    normalized = sorted(str(t).lower() for t in tags if t)
    tags_str = ",".join(normalized)
    return hashlib.sha256(tags_str.encode()).hexdigest()[:16]


def clear_injury_decision_cache() -> int:
    """
    Clear the injury decision cache.
    
    Call this when injury rules, exclusion maps, or tag vocabularies change
    to ensure stale safety decisions are not reused.
    
    Returns:
        Number of cache entries cleared
    """
    global _INJURY_DECISION_CACHE
    count = len(_INJURY_DECISION_CACHE)
    _INJURY_DECISION_CACHE.clear()
    if count > 0:
        logger.info("[injury-guard] Cache cleared: %d entries invalidated", count)
    return count


@dataclass(frozen=True)
class Decision:
    action: str
    risk_score: float
    threshold: float
    matched_tags: list[str]
    mods: list[str]
    reason: dict


def _normalize_injury_list(injuries: Iterable[str | dict] | str | dict | None) -> list[str | dict]:
    if not injuries:
        return []
    if isinstance(injuries, (str, dict)):
        return [injuries]
    return [item for item in injuries if item]


def normalize_severity(text: str) -> tuple[str, list[str]]:
    if not text:
        return "moderate", []
    lowered = text.lower()
    hits: list[str] = []
    severity = None
    for level in ("high", "moderate", "low"):
        for synonym in SEVERITY_SYNONYMS[level]:
            if synonym in lowered:
                hits.append(synonym)
                if severity is None:
                    severity = level
    return severity or "moderate", hits


def _normalize_phrase_severity(text: str) -> tuple[str, list[str]]:
    if not text:
        return "moderate", []
    for phrase in split_injury_text(str(text)):
        if is_restriction_phrase(phrase):
            continue
        return normalize_severity(phrase)
    return "moderate", []


def _build_parsed_injury_dump(injuries: Iterable[str | dict]) -> list[dict]:
    parsed: list[dict] = []
    for injury in injuries:
        if not injury:
            continue
        if isinstance(injury, dict):
            severity, _ = _normalize_dict_severity(injury)
            parsed.append(
                {
                    "region": injury.get("region") or injury.get("canonical_location"),
                    "side": injury.get("side") or injury.get("laterality"),
                    "injury_type": injury.get("injury_type"),
                    "severity": severity,
                    "original_phrase": injury.get("original_phrase") or injury.get("raw"),
                }
            )
            continue
        raw_text = str(injury)
        for phrase in split_injury_text(raw_text):
            entry = parse_injury_entry(phrase)
            if not entry:
                continue
            severity, _ = normalize_severity(phrase)
            parsed.append(
                {
                    "region": entry.get("canonical_location"),
                    "side": entry.get("side"),
                    "injury_type": entry.get("injury_type"),
                    "severity": severity,
                    "original_phrase": phrase,
                }
            )
    return parsed


def _strictest_severity(current: str | None, candidate: str) -> str:
    if current is None:
        return candidate
    if SEVERITY_RANK[candidate] > SEVERITY_RANK[current]:
        return candidate
    return current


def _normalize_dict_severity(injury: dict) -> tuple[str, list[str]]:
    raw_text = injury.get("original_phrase") or injury.get("raw")
    if raw_text:
        phrase_severity, hits = _normalize_phrase_severity(str(raw_text))
        if hits:
            return phrase_severity, hits
    severity_raw = injury.get("severity")
    if severity_raw:
        severity_text = str(severity_raw).lower()
        if severity_text in SEVERITY_RANK:
            return severity_text, []
        return normalize_severity(severity_text)
    return "moderate", []


def _map_text_to_region(text: str) -> str | None:
    for region, keywords in INJURY_REGION_KEYWORDS.items():
        if match_forbidden(text, keywords):
            return region
    return None


def _injury_context(injuries: Iterable[str | dict], debug_entries: list[dict] | None = None) -> dict[str, str]:
    region_severity: dict[str, str] = {}
    for injury in injuries:
        if not injury:
            continue
        if isinstance(injury, dict):
            region = injury.get("region")
            severity_raw = injury.get("severity")
            if severity_raw:
                severity_text = str(severity_raw).lower()
                severity = severity_text if severity_text in SEVERITY_RANK else "moderate"
            else:
                severity, _ = _normalize_dict_severity(injury)
            if region:
                region_severity[region] = _strictest_severity(region_severity.get(region), severity)
            continue

        raw_text = str(injury)
        regions: set[str] = set()
        injury_phrases: list[str] = []
        for phrase in split_injury_text(raw_text):
            if is_restriction_phrase(phrase):
                continue
            injury_phrases.append(phrase)
            severity, hits = normalize_severity(phrase)
            cleaned = remove_negated_phrases(phrase)
            if not cleaned:
                continue
            itype, loc = parse_injury_phrase(phrase)
            itype = itype or ("unspecified" if loc else None)
            for candidate in (loc, itype, phrase):
                if not candidate:
                    continue
                region = _map_text_to_region(str(candidate))
                if region:
                    regions.add(region)
                    region_severity[region] = _strictest_severity(region_severity.get(region), severity)
                    break

        if injury_phrases:
            fallback_regions = normalize_injury_regions([" ".join(injury_phrases)])
            for region in fallback_regions:
                regions.add(region)
                if region not in region_severity:
                    region_severity[region] = "moderate"

        if debug_entries is not None:
            if regions:
                for region in sorted(regions):
                    debug_entries.append(
                        {"raw": raw_text, "region": region, "severity": region_severity[region], "hits": []}
                    )
            else:
                debug_entries.append({"raw": raw_text, "region": None, "severity": "moderate", "hits": []})
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
    """
    Log injury decision details when INJURY_DEBUG=1.
    Only logs 'exclude' actions to reduce spam.
    'allow' and 'modify' actions are not logged.
    """
    if not INJURY_DEBUG:
        return
    # Only log exclude actions to avoid "allowed=True" spam
    if action != "exclude":
        return
    log_key = (item_name, region, severity, round(risk, 3), round(threshold, 3), action, tuple(matched_tags))
    if log_key in _INJURY_DECISION_LOGGED:
        return
    _INJURY_DECISION_LOGGED.add(log_key)
    injury_rule = "banned" if action == "exclude" else "allowed"
    logger.info(
        "[injury-guard] item='%s' region=%s severity=%s injury_rule=%s action=%s risk=%.2f threshold=%.2f matched_tags=%s",
        item_name,
        region,
        severity,
        injury_rule,
        action,
        risk,
        threshold,
        matched_tags,
    )


def injury_guard(
    item: dict,
    injuries: Iterable[str | dict] | str | dict,
    restrictions: Iterable[dict] | None = None,
    *,
    ignore_restrictions: bool = False,
    stage: str | None = None,
    phase: str | None = None,
    fatigue: str | None = None,
) -> Decision:
    if ignore_restrictions:
        restrictions = None
    if INJURY_DEBUG:
        logger.info(
            "[injury-guard-call] ignore_restrictions=%s restrictions_in=%s",
            ignore_restrictions,
            bool(restrictions),
        )
    resolved_phase = phase or item.get("phase") or ""
    resolved_fatigue = fatigue or item.get("fatigue") or ""
    return injury_decision(item, injuries, resolved_phase, resolved_fatigue)


def injury_decision(exercise: dict, injuries: Iterable[str | dict] | str | dict, phase: str, fatigue: str) -> Decision:
    """
    Make injury-based decision for an exercise.
    
    Args:
        exercise: Exercise dictionary with 'name', 'tags', etc.
        injuries: Can be:
            - List of injury strings (e.g., ["shoulder pain", "knee injury"])
            - List of injury dictionaries with 'region' and 'severity' keys
            - Single injury string
            - Single injury dictionary
            - Mixed list of strings and dictionaries
        phase: Training phase (e.g., "GPP", "SPP", "TAPER")
        fatigue: Fatigue level (e.g., "low", "moderate", "high")
        
    Returns:
        Decision object with action, risk_score, matched_tags, mods, and reason
    """
    injuries_list = _normalize_injury_list(injuries)
    debug_entries: list[dict] | None = None
    global _INJURY_SEVERITY_DEBUGGED, _INJURY_PARSED_DEBUGGED
    if INJURY_DEBUG and not _INJURY_PARSED_DEBUGGED:
        parsed_dump = _build_parsed_injury_dump(injuries_list)
        print("[injury-parse] parsed=%s" % json.dumps(parsed_dump, sort_keys=True))
        _INJURY_PARSED_DEBUGGED = True
    if INJURY_DEBUG and not _INJURY_SEVERITY_DEBUGGED:
        debug_entries = []
    for inj in injuries_list:
        if isinstance(inj, dict):
            raw_snapshot = dict(inj)
            severity, hits = _normalize_dict_severity(inj)
            inj["severity"] = severity
            if debug_entries is not None:
                debug_entries.append(
                    {
                        "raw": raw_snapshot,
                        "region": raw_snapshot.get("region"),
                        "severity": severity,
                        "hits": hits,
                    }
                )
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
    region_severity = _injury_context(injuries_list, debug_entries=debug_entries)
    if debug_entries is not None:
        for entry in debug_entries:
            print(
                "[injury-severity] raw=%r normalized={'region': %r, 'severity': %r} hits=%s"
                % (entry["raw"], entry["region"], entry["severity"], entry["hits"])
            )
        _INJURY_SEVERITY_DEBUGGED = True
    modify_band, threshold = _thresholds(phase, fatigue)
    threshold_version = f"{modify_band:.2f}:{threshold:.2f}"

    # For injury_match_details, we need to pass string representations
    # Extract strings from both string and dict injuries
    string_injuries_for_matching: list[str] = []
    for injury in injuries_list:
        if isinstance(injury, dict):
            # For dictionary injuries, use the region as the injury string for matching
            region = injury.get("region")
            if region:
                string_injuries_for_matching.append(region)
        else:
            string_injuries_for_matching.append(str(injury))
    
    details = injury_match_details(
        exercise,
        string_injuries_for_matching,
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
    
    # Extract module/bank information for cache key
    module = exercise.get("placement", "").lower() or "unknown"
    bank = exercise.get("bank", "") or exercise.get("source", "") or "unknown"
    
    # Compute tags hash for cache invalidation when tags change
    exercise_tags = exercise.get("tags", [])
    tags_hash = _compute_tags_hash(exercise_tags)

    for region, region_details in details_by_region.items():
        severity = region_severity.get(region, "moderate")
        # Enhanced cache key includes:
        # - item_id: unique exercise identifier
        # - region: injury region being evaluated
        # - severity: injury severity level
        # - threshold_version: scoring thresholds (changes with phase/fatigue)
        # - rules_version: injury rules version (from config)
        # - tags_hash: hash of exercise tags (detects tag changes)
        # - module: strength vs conditioning
        # - bank: which bank the exercise came from
        cache_key = (item_id, region, severity, threshold_version, INJURY_RULES_VERSION, tags_hash, module, bank)
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
            # Conservative safety approach: exclude when risk >= threshold
            if max_region_risk >= threshold:
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
    # Conservative safety approach: exclude when risk >= threshold (not just >)
    # This ensures borderline cases are excluded rather than modified
    if max_risk >= threshold:
        action = "exclude"
    elif max_risk >= modify_band:
        action = "modify"
    else:
        action = "allow"

    mods = MODS_BY_REGION.get(region, []) if action == "modify" else []
    
    decision = Decision(
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
    
    return decision


def make_guarded_decision_factory(
    injuries: Iterable[str | dict] | str | dict,
    phase: str,
    fatigue: str,
    guard_pool: set[str],
    guard_list: list[dict] | None = None,
    *,
    restrictions: Iterable[dict] | None = None,
    ignore_restrictions: bool = False,
    stage: str | None = None,
) -> Callable[[dict], Decision]:
    """
    Refactored: Create a closure factory for guarded injury decisions.
    
    This factory function replaces duplicate implementations of _guarded_injury_decision
    that were previously defined separately in strength.py and conditioning.py.
    
    The returned function ensures candidates are added to the guard pool
    (and optionally to a guard list) before making an injury decision.
    
    Args:
        injuries: Injury list to check against
        phase: Training phase (GPP, SPP, TAPER)
        fatigue: Fatigue level (low, medium, high)
        guard_pool: Set of exercise/drill names already in guard list (for deduplication)
        guard_list: Optional list to append new candidates to (used in strength.py)
    
    Returns:
        A function that takes an item dict and returns a Decision,
        while also ensuring the item is added to the guard pool.
    """
    def _guarded_injury_decision(item: dict) -> Decision:
        # Add item name to guard pool if not already present
        name = item.get("name")
        if name and name not in guard_pool:
            guard_pool.add(name)
            # Also add to list if one was provided
            if guard_list is not None:
                guard_list.append(item)
        # Make and return the injury decision
        return injury_guard(
            item,
            injuries,
            restrictions=restrictions,
            ignore_restrictions=ignore_restrictions,
            stage=stage,
            phase=phase,
            fatigue=fatigue,
        )
    
    return _guarded_injury_decision


def choose_injury_replacement(
    *,
    excluded_item: dict,
    candidates: list[dict],
    injuries: Iterable[str | dict],
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


def filter_safe_candidates(
    candidates: list[dict],
    injuries: Iterable[str | dict],
    phase: str,
    fatigue: str,
    *,
    min_pool: int | None = None,
    max_k: int | None = None,
    initial_k: int | None = None,
) -> tuple[list[dict], dict]:
    """
    Filter candidates through injury guard with Top-K shortlisting and starvation safeguard.
    
    This implements the Top-K shortlist logic with automatic K-widening when the candidate
    pool falls below the minimum threshold (starvation safeguard).
    
    Algorithm:
    1. Start with initial_k candidates (defaults to INJURY_GUARD_SHORTLIST)
    2. Filter out excluded candidates
    3. If pool size < min_pool, double K and retry (up to max_k)
    4. If still starved at max_k, fall back to full candidate scan
    
    Args:
        candidates: Scored/sorted list of candidate exercises or drills
        injuries: List of injury strings or dicts
        phase: Training phase (GPP, SPP, TAPER)
        fatigue: Fatigue level (low, moderate, high)
        min_pool: Minimum acceptable pool size (defaults to MIN_CANDIDATE_POOL from config)
        max_k: Maximum K value when widening (defaults to MAX_INJURY_GUARD_SHORTLIST)
        initial_k: Initial shortlist size (defaults to INJURY_GUARD_SHORTLIST)
        
    Returns:
        Tuple of (safe_candidates, stats_dict) where stats contains:
        - 'k_used': Final K value used
        - 'k_iterations': Number of K-widening iterations
        - 'total_evaluated': Total candidates evaluated
        - 'excluded_count': Number of candidates excluded
        - 'used_fallback': Whether full scan fallback was used
    """
    # Import here to avoid circular imports
    from .config import INJURY_GUARD_SHORTLIST, MIN_CANDIDATE_POOL, MAX_INJURY_GUARD_SHORTLIST
    
    if min_pool is None:
        min_pool = MIN_CANDIDATE_POOL
    if max_k is None:
        max_k = MAX_INJURY_GUARD_SHORTLIST
    if initial_k is None:
        initial_k = INJURY_GUARD_SHORTLIST
    
    k = initial_k
    iterations = 0
    total_evaluated = 0
    excluded_count = 0
    used_fallback = False
    safe = []
    
    # Top-K shortlisting with starvation safeguard
    while k <= max_k:
        iterations += 1
        shortlist = candidates[:k]
        total_evaluated = len(shortlist)
        
        safe = []
        for cand in shortlist:
            decision = injury_decision(cand, injuries, phase, fatigue)
            if decision.action != "exclude":
                safe.append(cand)
            else:
                excluded_count += 1
        
        # Check if we have enough safe candidates
        if len(safe) >= min_pool or k >= len(candidates):
            break
        
        # Starvation detected: widen K and retry
        if INJURY_DEBUG:
            logger.info(
                "[injury-guard-topk] Starvation safeguard: pool=%d < min_pool=%d, widening K from %d to %d",
                len(safe), min_pool, k, min(k * 2, max_k)
            )
        k = min(k * 2, max_k)
    
    # Fallback: if still starved after reaching max_k, scan all remaining candidates
    if len(safe) < min_pool and k < len(candidates):
        if INJURY_DEBUG:
            logger.info(
                "[injury-guard-topk] Full scan fallback: pool=%d < min_pool=%d after K=%d",
                len(safe), min_pool, k
            )
        used_fallback = True
        remaining = candidates[k:]
        for cand in remaining:
            decision = injury_decision(cand, injuries, phase, fatigue)
            if decision.action != "exclude":
                safe.append(cand)
            else:
                excluded_count += 1
            total_evaluated += 1
    
    stats = {
        "k_used": k,
        "k_iterations": iterations,
        "total_evaluated": total_evaluated,
        "excluded_count": excluded_count,
        "used_fallback": used_fallback,
        "final_pool_size": len(safe),
    }
    
    return safe, stats
