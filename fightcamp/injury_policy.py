from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Iterable, Mapping, Sequence

from .injury_formatting import parse_injuries_and_restrictions
from .restriction_parsing import ParsedRestriction
from .tagging import normalize_tags

DEFAULT_SOFT_PENALTY = -0.6
MAX_TOTAL_SOFT_PENALTY = -1.5

_WORD_PATTERN = re.compile(r"[a-z]+")

_SEVERITY_ORDER = {"mild": 0, "moderate": 1, "severe": 2}
_SEVERITY_ALIAS = {
    "low": "mild",
    "mild": "mild",
    "moderate": "moderate",
    "high": "severe",
    "severe": "severe",
}
_DEFAULT_SEVERITY_BY_TYPE = {
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
    "unspecified": "moderate",
    "swelling": "severe",
    "instability": "severe",
}
_FUNCTIONAL_IMPACT_ORDER = {
    "can_train_fully": 0,
    "can_train_with_modifications": 1,
    "cannot_do_key_movements_properly": 2,
}
_FUNCTIONAL_IMPACT_ALIAS = {
    "can train fully": "can_train_fully",
    "can_train_fully": "can_train_fully",
    "can train with modifications": "can_train_with_modifications",
    "can_train_with_modifications": "can_train_with_modifications",
    "cannot do key movements properly": "cannot_do_key_movements_properly",
    "cannot_do_key_movements_properly": "cannot_do_key_movements_properly",
}
_TREND_ALIAS = {
    "improving": "improving",
    "stable": "stable",
    "worsening": "worsening",
}
_TREND_ADJUST = {"improving": -1, "stable": 0, "worsening": 1}
_PHRASE_SEVERITY_HINTS = {
    "severe": {
        "torn",
        "tear",
        "rupture",
        "ruptured",
        "popped",
        "snap",
        "snapped",
        "fracture",
        "dislocated",
        "severe",
        "swollen",
        "swelling",
    },
    "mild": {
        "mild",
        "minor",
        "slight",
        "tightness",
        "stiffness",
        "soreness",
    },
}

MOVEMENT_KEYWORDS = {
    "deep_knee_flexion": {
        "keywords": {"deep knee flexion", "deep hip flexion", "deep squat", "deep lunge", "ass to grass", "knee flexion"},
        "tags": {"deep_flexion", "deep_knee_flexion_loaded", "knee_dominant_heavy"},
    },
    "heavy_overhead_pressing": {
        "keywords": {
            "overhead press",
            "overhead pressing",
            "push press",
            "jerk",
            "thruster",
            "snatch",
            "overhead carry",
            "overhead slam",
        },
        "tags": {"overhead", "dynamic_overhead", "press_heavy"},
    },
    "high_impact_lower": {
        "keywords": {
            "jump",
            "jumps",
            "depth jump",
            "drop jump",
            "box jump",
            "split jump",
            "hop",
            "bounds",
            "sprint",
            "sprinting",
            "burpee",
            "sprawl",
            "landing",
            "landings",
        },
        "tags": {
            "high_impact",
            "high_impact_plyo",
            "plyometric",
            "jumping",
            "ballistic_lower",
            "mech_lower_jump",
            "mech_landing_impact",
            "landing_stress_high",
            "reactive_rebound_high",
            "impact_rebound_high",
            "foot_impact_high",
            "mech_reactive",
            "mech_ballistic",
        },
    },
    "high_impact_upper": {
        "keywords": {
            "clap pushup",
            "clap push-up",
            "clapping pushup",
            "clapping push-up",
            "plyo pushup",
            "plyo push-up",
            "explosive pushup",
            "explosive push-up",
        },
        "tags": {"ballistic_upper", "upper_push_explosive"},
    },
    "max_velocity": {
        "keywords": {"max sprint", "max velocity", "overspeed", "flying sprint", "sprint"},
        "tags": {"max_velocity", "mech_max_velocity", "running_volume_high", "shin_splints_risk"},
    },
    "loaded_flexion": {
        "keywords": {"loaded flexion", "weighted sit-up", "loaded crunch", "under load"},
        "tags": {"loaded_flexion"},
    },
    "heavy_hinging": {
        "keywords": {"deadlift", "rdl", "hip hinge", "good morning", "heavy hinge"},
        "tags": {"hinge_heavy", "lumbar_loaded", "axial_heavy", "posterior_chain_heavy"},
    },
    "lateral_cutting": {
        "keywords": {"cut", "cutting", "change of direction", "decel", "deceleration", "shuffle"},
        "tags": {"cutting", "deceleration", "lateral", "change_of_direction"},
    },
    "rotation_torque": {
        "keywords": {"rotation", "rotational", "twist", "throw", "torque"},
        "tags": {"rotation", "rotational", "trunk_rotation", "hip_rotation_risk"},
    },
    "grappling_pressure": {
        "keywords": {"clinch", "grappling", "wrestling", "frame", "hand-fight", "tie-up"},
        "tags": {"grappling", "clinch", "neck_loaded", "neck_bridge", "cervical_load"},
    },
    "upper_push_loading": {
        "keywords": {
            "bench press",
            "bench isometric",
            "bench",
            "dip",
            "push-up",
            "push up",
            "floor press",
            "landmine press",
            "press",
        },
        "tags": {"upper_push", "pec_loaded", "press_heavy"},
    },
}

RESTRICTION_KEY_ALIASES = {
    "high_impact": "high_impact_global",
    "high_impact_global": "high_impact_lower",
    "generic_constraint": None,
}

BODY_PART_FAMILY = {
    "shoulder": "shoulder",
    "chest": "shoulder",
    "biceps": "shoulder",
    "triceps": "shoulder",
    "elbow": "wrist_hand",
    "forearm": "wrist_hand",
    "wrist": "wrist_hand",
    "hand": "wrist_hand",
    "neck": "neck",
    "upper_back": "spine",
    "upper back": "spine",
    "lower_back": "spine",
    "lower back": "spine",
    "si_joint": "spine",
    "si joint": "spine",
    "hip": "hip_groin",
    "groin": "hip_groin",
    "hip_flexor": "hip_groin",
    "hip flexor": "hip_groin",
    "glute": "hip_groin",
    "knee": "knee",
    "quad": "knee",
    "hamstring": "posterior_chain",
    "calf": "lower_leg_foot",
    "achilles": "lower_leg_foot",
    "ankle": "lower_leg_foot",
    "foot": "lower_leg_foot",
    "toe": "lower_leg_foot",
    "shin": "lower_leg_foot",
    "heel": "lower_leg_foot",
}

BASELINE_RULE_MATRIX = {
    "shoulder": {
        0: {"soft": ("upper_push_loading",)},
        1: {"hard": ("heavy_overhead_pressing", "upper_push_loading"), "soft": ("high_impact_upper", "grappling_pressure")},
        2: {"hard": ("heavy_overhead_pressing", "upper_push_loading", "high_impact_upper"), "soft": ("grappling_pressure", "rotation_torque")},
        3: {"hard": ("heavy_overhead_pressing", "upper_push_loading", "high_impact_upper", "grappling_pressure", "rotation_torque")},
    },
    "wrist_hand": {
        0: {"soft": ("upper_push_loading", "grappling_pressure")},
        1: {"hard": ("upper_push_loading",), "soft": ("grappling_pressure", "heavy_overhead_pressing")},
        2: {"hard": ("upper_push_loading", "grappling_pressure"), "soft": ("heavy_overhead_pressing",)},
        3: {"hard": ("upper_push_loading", "grappling_pressure", "heavy_overhead_pressing")},
    },
    "neck": {
        0: {"soft": ("grappling_pressure", "rotation_torque")},
        1: {"hard": ("grappling_pressure",), "soft": ("rotation_torque",)},
        2: {"hard": ("grappling_pressure", "rotation_torque")},
        3: {"hard": ("grappling_pressure", "rotation_torque", "loaded_flexion")},
    },
    "spine": {
        0: {"soft": ("heavy_hinging", "loaded_flexion")},
        1: {"hard": ("heavy_hinging", "loaded_flexion"), "soft": ("rotation_torque",)},
        2: {"hard": ("heavy_hinging", "loaded_flexion", "rotation_torque")},
        3: {"hard": ("heavy_hinging", "loaded_flexion", "rotation_torque", "high_impact_lower")},
    },
    "hip_groin": {
        0: {"soft": ("deep_knee_flexion", "lateral_cutting", "heavy_hinging")},
        1: {"hard": ("lateral_cutting",), "soft": ("deep_knee_flexion", "max_velocity", "rotation_torque", "heavy_hinging")},
        2: {"hard": ("deep_knee_flexion", "lateral_cutting"), "soft": ("max_velocity", "high_impact_lower", "rotation_torque", "heavy_hinging")},
        3: {"hard": ("deep_knee_flexion", "lateral_cutting", "max_velocity", "high_impact_lower", "rotation_torque", "heavy_hinging")},
    },
    "knee": {
        0: {"hard": ("high_impact_lower",), "soft": ("deep_knee_flexion",)},
        1: {"hard": ("high_impact_lower",), "soft": ("deep_knee_flexion", "lateral_cutting", "max_velocity")},
        2: {"hard": ("high_impact_lower", "deep_knee_flexion"), "soft": ("lateral_cutting", "max_velocity")},
        3: {"hard": ("high_impact_lower", "deep_knee_flexion", "lateral_cutting", "max_velocity")},
    },
    "posterior_chain": {
        0: {"soft": ("max_velocity", "heavy_hinging")},
        1: {"hard": ("max_velocity",), "soft": ("high_impact_lower", "heavy_hinging")},
        2: {"hard": ("max_velocity", "high_impact_lower"), "soft": ("heavy_hinging", "lateral_cutting")},
        3: {"hard": ("max_velocity", "high_impact_lower", "heavy_hinging", "lateral_cutting")},
    },
    "lower_leg_foot": {
        0: {"soft": ("high_impact_lower",)},
        1: {"hard": ("high_impact_lower",), "soft": ("max_velocity", "lateral_cutting")},
        2: {"hard": ("high_impact_lower", "max_velocity"), "soft": ("lateral_cutting",)},
        3: {"hard": ("high_impact_lower", "max_velocity", "lateral_cutting")},
    },
}

REHAB_FOCUS_BY_FAMILY = {
    "shoulder": ("upper_push_loading", "heavy_overhead_pressing"),
    "wrist_hand": ("upper_push_loading", "grappling_pressure"),
    "neck": ("grappling_pressure", "rotation_torque"),
    "spine": ("heavy_hinging", "loaded_flexion"),
    "hip_groin": ("deep_knee_flexion", "lateral_cutting", "rotation_torque"),
    "knee": ("deep_knee_flexion", "high_impact_lower"),
    "posterior_chain": ("max_velocity", "heavy_hinging"),
    "lower_leg_foot": ("high_impact_lower", "max_velocity"),
}

RETURN_TO_PLAY_BY_STAGE = {
    "protect": {"allowed": (), "blocked": ("high_impact_lower", "max_velocity", "heavy_overhead_pressing", "upper_push_loading", "grappling_pressure")},
    "rebuild": {"allowed": ("loaded_flexion", "heavy_hinging", "upper_push_loading"), "blocked": ("high_impact_lower", "max_velocity")},
    "reintroduce": {"allowed": ("high_impact_lower", "max_velocity", "upper_push_loading", "heavy_overhead_pressing"), "blocked": ()},
    "perform": {"allowed": (), "blocked": ()},
}


@dataclass(frozen=True)
class InjuryCase:
    id: str
    body_part: str
    side: str | None
    injury_type: str | None
    severity: str
    trend: str
    functional_impact: str
    protection_level: int
    aggravating_movements: tuple[str, ...] = ()
    cautious_movements: tuple[str, ...] = ()
    original_phrase: str = ""


@dataclass(frozen=True)
class MovementRule:
    case_id: str
    movement_key: str
    mode: str
    penalty: float | None
    source: str
    body_part: str | None = None
    side: str | None = None
    original_phrase: str = ""


@dataclass(frozen=True)
class RehabDirective:
    case_id: str
    return_stage: str
    focus_keys: tuple[str, ...]
    allowed_exposure_keys: tuple[str, ...]
    blocked_exposure_keys: tuple[str, ...]


@dataclass(frozen=True)
class AuditEntry:
    case_id: str
    step: str
    detail: str


@dataclass(frozen=True)
class InjuryPolicy:
    cases: tuple[InjuryCase, ...] = ()
    movement_rules: tuple[MovementRule, ...] = ()
    rehab_directives: tuple[RehabDirective, ...] = ()
    audit: tuple[AuditEntry, ...] = ()


def _normalize_body_part(value: str | None) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _normalize_case_body_part(value: str | None) -> str:
    normalized = _normalize_body_part(value)
    return normalized.replace(" ", "_")


def _normalize_side(value: str | None) -> str | None:
    lowered = str(value or "").strip().lower()
    return lowered or None


def _normalize_severity_value(entry: Mapping[str, object]) -> str:
    raw = str(entry.get("severity") or "").strip().lower()
    mapped = _SEVERITY_ALIAS.get(raw)
    if mapped:
        return mapped
    phrase = str(entry.get("original_phrase") or "").strip().lower()
    phrase_tokens = set(_WORD_PATTERN.findall(phrase))
    if phrase_tokens & _PHRASE_SEVERITY_HINTS["severe"]:
        return "severe"
    if phrase_tokens & _PHRASE_SEVERITY_HINTS["mild"]:
        return "mild"
    injury_type = str(entry.get("injury_type") or "unspecified").strip().lower()
    return _DEFAULT_SEVERITY_BY_TYPE.get(injury_type, "moderate")


def _normalize_trend(entry: Mapping[str, object]) -> str:
    raw = str(entry.get("trend") or "").strip().lower()
    return _TREND_ALIAS.get(raw, "stable")


def _default_functional_impact(severity: str) -> str:
    if severity == "severe":
        return "cannot_do_key_movements_properly"
    if severity == "mild":
        return "can_train_fully"
    return "can_train_with_modifications"


def _normalize_functional_impact(entry: Mapping[str, object], severity: str) -> str:
    raw = str(entry.get("functional_impact") or "").strip().lower()
    return _FUNCTIONAL_IMPACT_ALIAS.get(raw, _default_functional_impact(severity))


def _compute_protection_level(severity: str, trend: str, functional_impact: str) -> int:
    severity_rank = _SEVERITY_ORDER.get(severity, 1)
    impact_rank = _FUNCTIONAL_IMPACT_ORDER.get(functional_impact, 1)
    trend_adjust = _TREND_ADJUST.get(trend, 0)
    return max(0, min(3, max(severity_rank, impact_rank) + trend_adjust))


def _family_for_body_part(body_part: str) -> str:
    normalized = _normalize_body_part(body_part)
    if normalized in BODY_PART_FAMILY:
        return BODY_PART_FAMILY[normalized]
    underscored = normalized.replace(" ", "_")
    return BODY_PART_FAMILY.get(underscored, "spine")


def _case_id(entry: Mapping[str, object], index: int) -> str:
    seed = "|".join(
        [
            str(entry.get("canonical_location") or entry.get("body_part") or ""),
            str(entry.get("laterality") or entry.get("side") or ""),
            str(entry.get("injury_type") or ""),
            str(entry.get("original_phrase") or ""),
            str(index),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"injury_{digest}"


def _word_boundary_match(keyword: str, text: str) -> bool:
    if not keyword:
        return False
    parts = [re.escape(part) for part in re.split(r"[\s-]+", keyword.strip()) if part]
    if not parts:
        return False
    pattern = r"\b" + r"[\s-]+".join(parts) + r"\b"
    return re.search(pattern, text) is not None


def _extract_movement_keys_from_text(text: str, tags: Iterable[str]) -> set[str]:
    normalized_text = str(text or "").lower()
    normalized_tags = set(normalize_tags(tags or []))
    movement_keys: set[str] = set()
    for movement_key, data in MOVEMENT_KEYWORDS.items():
        if normalized_tags & set(data["tags"]):
            movement_keys.add(movement_key)
            continue
        if any(_word_boundary_match(keyword, normalized_text) for keyword in data["keywords"]):
            movement_keys.add(movement_key)
    return movement_keys


def infer_movement_keys(*, text: str, tags: Iterable[str], extra_text: Iterable[str] | None = None) -> list[str]:
    texts = [text]
    if extra_text:
        texts.extend(extra_text)
    movement_keys: set[str] = set()
    for value in texts:
        movement_keys |= _extract_movement_keys_from_text(value, tags)
    return sorted(movement_keys)


def _normalize_explicit_movement_keys(values: Sequence[str] | None) -> tuple[str, ...]:
    movement_keys: set[str] = set()
    for value in values or ():
        movement_keys |= set(infer_movement_keys(text=value, tags=[]))
    return tuple(sorted(movement_keys))


def _restriction_movement_keys(restriction: Mapping[str, object]) -> tuple[str, ...]:
    restriction_key = str(restriction.get("restriction") or "").strip()
    normalized_key = RESTRICTION_KEY_ALIASES.get(restriction_key, restriction_key)
    movement_keys: set[str] = set()
    if normalized_key:
        movement_keys.add(normalized_key)
    phrase = str(restriction.get("original_phrase") or "")
    movement_keys |= set(infer_movement_keys(text=phrase, tags=[]))
    return tuple(sorted(key for key in movement_keys if key))


def _coerce_injury_entries(
    injuries: Iterable[str | Mapping[str, object]] | str | Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if not injuries:
        return []
    if isinstance(injuries, str):
        parsed_injuries, _ = parse_injuries_and_restrictions(injuries)
        return [dict(entry) for entry in parsed_injuries]
    if isinstance(injuries, Mapping):
        return [dict(injuries)]

    entries: list[dict[str, object]] = []
    for injury in injuries:
        if not injury:
            continue
        if isinstance(injury, str):
            parsed_injuries, _ = parse_injuries_and_restrictions(injury)
            if parsed_injuries:
                entries.extend(dict(entry) for entry in parsed_injuries)
            else:
                entries.append({"original_phrase": injury})
            continue
        entries.append(dict(injury))
    return entries


def _coerce_restrictions(
    restrictions: Iterable[Mapping[str, object]] | None,
) -> list[dict[str, object]]:
    return [dict(restriction) for restriction in (restrictions or []) if restriction]


def compile_injury_policy(
    *,
    parsed_injuries: Iterable[Mapping[str, object]] | None,
    restrictions: Iterable[Mapping[str, object]] | None = None,
) -> InjuryPolicy:
    cases: list[InjuryCase] = []
    movement_rules: list[MovementRule] = []
    rehab_directives: list[RehabDirective] = []
    audit: list[AuditEntry] = []

    for index, raw_entry in enumerate(parsed_injuries or []):
        entry = dict(raw_entry)
        body_part = _normalize_case_body_part(
            str(entry.get("canonical_location") or entry.get("body_part") or entry.get("region") or "").strip()
        )
        if not body_part:
            continue
        severity = _normalize_severity_value(entry)
        trend = _normalize_trend(entry)
        functional_impact = _normalize_functional_impact(entry, severity)
        protection_level = _compute_protection_level(severity, trend, functional_impact)
        case = InjuryCase(
            id=_case_id(entry, index),
            body_part=body_part,
            side=_normalize_side(str(entry.get("side") or entry.get("laterality") or "") or None),
            injury_type=str(entry.get("injury_type") or "").strip().lower() or None,
            severity=severity,
            trend=trend,
            functional_impact=functional_impact,
            protection_level=protection_level,
            aggravating_movements=_normalize_explicit_movement_keys(entry.get("aggravating_movements")),
            cautious_movements=_normalize_explicit_movement_keys(entry.get("cautious_movements")),
            original_phrase=str(entry.get("original_phrase") or ""),
        )
        cases.append(case)
        audit.append(
            AuditEntry(
                case_id=case.id,
                step="compile_case",
                detail=(
                    f"{case.body_part} severity={case.severity} trend={case.trend} "
                    f"impact={case.functional_impact} protection={case.protection_level}"
                ),
            )
        )

        for movement_key in case.aggravating_movements:
            movement_rules.append(
                MovementRule(
                    case_id=case.id,
                    movement_key=movement_key,
                    mode="hard_block",
                    penalty=None,
                    source="explicit_aggravator",
                    body_part=case.body_part,
                    side=case.side,
                    original_phrase=case.original_phrase,
                )
            )
        for movement_key in case.cautious_movements:
            movement_rules.append(
                MovementRule(
                    case_id=case.id,
                    movement_key=movement_key,
                    mode="soft_caution",
                    penalty=DEFAULT_SOFT_PENALTY,
                    source="explicit_caution",
                    body_part=case.body_part,
                    side=case.side,
                    original_phrase=case.original_phrase,
                )
            )

        family = _family_for_body_part(case.body_part)
        baseline = BASELINE_RULE_MATRIX.get(family, {}).get(case.protection_level, {})
        for movement_key in baseline.get("hard", ()):
            if movement_key in case.cautious_movements:
                continue
            movement_rules.append(
                MovementRule(
                    case_id=case.id,
                    movement_key=movement_key,
                    mode="hard_block",
                    penalty=None,
                    source="baseline_region_rule",
                    body_part=case.body_part,
                    side=case.side,
                )
            )
        for movement_key in baseline.get("soft", ()):
            if movement_key in case.aggravating_movements:
                continue
            movement_rules.append(
                MovementRule(
                    case_id=case.id,
                    movement_key=movement_key,
                    mode="soft_caution",
                    penalty=DEFAULT_SOFT_PENALTY,
                    source="baseline_region_rule",
                    body_part=case.body_part,
                    side=case.side,
                )
            )

        stage = {3: "protect", 2: "rebuild", 1: "reintroduce", 0: "perform"}[case.protection_level]
        focus_keys = tuple(REHAB_FOCUS_BY_FAMILY.get(family, ()))
        stage_rules = RETURN_TO_PLAY_BY_STAGE[stage]
        rehab_directives.append(
            RehabDirective(
                case_id=case.id,
                return_stage=stage,
                focus_keys=focus_keys,
                allowed_exposure_keys=tuple(stage_rules["allowed"]),
                blocked_exposure_keys=tuple(stage_rules["blocked"]),
            )
        )
        audit.append(
            AuditEntry(
                case_id=case.id,
                step="compile_rehab",
                detail=f"return_stage={stage} focus={','.join(focus_keys) if focus_keys else 'none'}",
            )
        )
        if stage != "perform":
            for movement_key in stage_rules["allowed"]:
                if movement_key in case.aggravating_movements or movement_key in case.cautious_movements:
                    continue
                movement_rules.append(
                    MovementRule(
                        case_id=case.id,
                        movement_key=movement_key,
                        mode="soft_caution",
                        penalty=DEFAULT_SOFT_PENALTY,
                        source="return_to_play",
                        body_part=case.body_part,
                        side=case.side,
                    )
                )
            for movement_key in stage_rules["blocked"]:
                if movement_key in case.cautious_movements:
                    continue
                movement_rules.append(
                    MovementRule(
                        case_id=case.id,
                        movement_key=movement_key,
                        mode="hard_block",
                        penalty=None,
                        source="return_to_play",
                        body_part=case.body_part,
                        side=case.side,
                    )
                )

    restrictions_list = _coerce_restrictions(restrictions)
    for index, restriction in enumerate(restrictions_list):
        case_id = f"restriction_{index}"
        region = _normalize_case_body_part(
            str(restriction.get("region") or restriction.get("canonical_location") or "").strip()
        )
        side = _normalize_side(str(restriction.get("side") or restriction.get("laterality") or "") or None)
        if region:
            for case in cases:
                if case.body_part != region:
                    continue
                if side and case.side and side != case.side:
                    continue
                case_id = case.id
                break
        strength = str(restriction.get("strength") or "avoid").strip().lower()
        source = "explicit_caution" if strength in {"limit", "reduce"} else "explicit_aggravator"
        mode = "soft_caution" if source == "explicit_caution" else "hard_block"
        penalty = DEFAULT_SOFT_PENALTY if mode == "soft_caution" else None
        movement_keys = _restriction_movement_keys(restriction)
        for movement_key in movement_keys:
            movement_rules.append(
                MovementRule(
                    case_id=case_id,
                    movement_key=movement_key,
                    mode=mode,
                    penalty=penalty,
                    source=source,
                    body_part=region or None,
                    side=side,
                    original_phrase=str(restriction.get("original_phrase") or ""),
                )
            )
        if movement_keys:
            audit.append(
                AuditEntry(
                    case_id=case_id,
                    step="compile_restriction",
                    detail=f"{source} keys={','.join(movement_keys)} phrase={restriction.get('original_phrase', '')}",
                )
            )

    deduped_rules: list[MovementRule] = []
    seen_rules: set[tuple[str, str, str, str]] = set()
    for rule in movement_rules:
        key = (rule.case_id, rule.movement_key, rule.mode, rule.source)
        if key in seen_rules:
            continue
        seen_rules.add(key)
        deduped_rules.append(rule)

    return InjuryPolicy(
        cases=tuple(cases),
        movement_rules=tuple(deduped_rules),
        rehab_directives=tuple(rehab_directives),
        audit=tuple(audit),
    )


def compile_injury_policy_from_inputs(
    *,
    injuries: Iterable[str | Mapping[str, object]] | str | Mapping[str, object] | None,
    restrictions: Iterable[Mapping[str, object]] | None = None,
) -> InjuryPolicy:
    return compile_injury_policy(
        parsed_injuries=_coerce_injury_entries(injuries),
        restrictions=restrictions,
    )


def empty_policy() -> InjuryPolicy:
    return InjuryPolicy()


def summarize_policy_text(policy: InjuryPolicy) -> str:
    if not policy.cases and not policy.movement_rules:
        return "no active injury policy"
    case_parts = [
        f"{case.body_part}:{case.severity}:{case.trend}:L{case.protection_level}"
        for case in policy.cases
    ]
    rule_parts = [
        f"{rule.source}:{rule.mode}:{rule.movement_key}"
        for rule in policy.movement_rules[:10]
    ]
    return "; ".join(case_parts + rule_parts)


def evaluate_injury_policy(
    *,
    policy: InjuryPolicy | None,
    text: str,
    tags: Iterable[str],
    default_soft_penalty: float = DEFAULT_SOFT_PENALTY,
) -> dict[str, object]:
    resolved_policy = policy or empty_policy()
    movement_keys = infer_movement_keys(text=text, tags=tags)
    matched_rules: list[dict[str, object]] = []
    hard_matches: list[dict[str, object]] = []
    soft_by_key: dict[str, float] = {}
    directive_by_case = {directive.case_id: directive for directive in resolved_policy.rehab_directives}
    rehab_relevance = 0.0

    for rule in resolved_policy.movement_rules:
        if rule.movement_key not in movement_keys:
            continue
        detail = {
            "case_id": rule.case_id,
            "movement_key": rule.movement_key,
            "mode": rule.mode,
            "penalty": rule.penalty,
            "source": rule.source,
            "body_part": rule.body_part,
            "side": rule.side,
            "original_phrase": rule.original_phrase,
        }
        matched_rules.append(detail)
        if rule.mode == "hard_block":
            hard_matches.append(detail)
        else:
            soft_by_key[rule.movement_key] = min(
                soft_by_key.get(rule.movement_key, 0.0),
                float(rule.penalty if rule.penalty is not None else default_soft_penalty),
            )
        directive = directive_by_case.get(rule.case_id)
        if directive and rule.movement_key in directive.focus_keys:
            rehab_relevance = max(rehab_relevance, 1.0)
        elif directive and rule.movement_key in directive.allowed_exposure_keys:
            rehab_relevance = max(rehab_relevance, 0.6)

    soft_penalty = round(sum(soft_by_key.values()), 3) if soft_by_key else 0.0
    soft_penalty = max(MAX_TOTAL_SOFT_PENALTY, soft_penalty)
    action = "exclude" if hard_matches else ("modify" if soft_penalty < 0 else "allow")

    trace = [
        {
            "case_id": match["case_id"],
            "movement_key": match["movement_key"],
            "mode": match["mode"],
            "source": match["source"],
        }
        for match in matched_rules
    ]
    return {
        "action": action,
        "movement_keys": movement_keys,
        "matched_rules": matched_rules,
        "hard_matches": hard_matches,
        "score_penalty": soft_penalty,
        "rehab_relevance": rehab_relevance,
        "trace": trace,
    }
