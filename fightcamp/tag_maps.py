"""Shared tag mapping definitions for training plan generation.

Scoring-map values must be canonical bank tags with real bank coverage. Input
aliases belong in the normalizer maps, not in the scoring values themselves.
"""

# Legacy labels resolve to the intake form's own values (web/lib/intake-options.ts),
# so a label and its form value build the same programme: consumers key on
# "speed" and "power" (e.g. the primary-speed alactic bonus, power guidance).
GOAL_NORMALIZER = {
    "power": "power",
    "strength": "strength",
    "conditioning": "conditioning",
    "explosive": "explosive",
    "speed": "speed",
    "reactive": "reactive",
    "skill_refinement": "skill_refinement",
    "mobility": "mobility",
    "recovery": "recovery",
    "weight_cut": "weight_cut",
    "Power & Explosiveness": "power",
    "Conditioning / Endurance": "conditioning",
    "Maximal Strength": "strength",
    "Maximal Strength Maintenance": "maximal_strength_maintenance",
    "maximal_strength_maintenance": "maximal_strength_maintenance",
    "Mobility": "mobility",
    "Speed": "speed",
    "Agility": "lateral",
    "Core Stability": "core",
    "CNS Fatigue": "cns",
    "Speed / Reaction": "speed",
    "Lateral Movement": "lateral",
    "Rotation": "rotational",
    "Balance": "balance",
    "Shoulders": "shoulders",
    "Shoulder": "shoulders",
    "Hip Mobility": "hip",
    "Grip Strength": "grip",
    "Posterior Chain": "posterior_chain",
    "Knees": "quad_dominant",
    "Neck": "neck",
    "Coordination / Proprioception": "coordination",
    "Coordination/Proprioception": "coordination",
    "Grappling": "grappler",
    "Striking": "striking",
    "Injury Prevention": "injury_prevention",
    "Mental Resilience": "mental_resilience",
    "Skill Refinement": "skill_refinement",
}

WEAKNESS_NORMALIZER = {
    "gas_tank": ["gas_tank"],
    "strength": ["strength"],
    "power": ["power"],
    "speed": ["speed"],
    "footwork": ["footwork"],
    "balance": ["balance"],
    "mobility": ["mobility"],
    "coordination": ["coordination"],
    "trunk_strength": ["trunk_strength"],
    "coordination / proprioception": ["coordination"],
    "coordination/proprioception": ["coordination"],
    "coordination_proprioception": ["coordination"],
    "shoulder": ["shoulders"],
    "shoulders": ["shoulders"],
    "core": ["core stability"],
    "core strength": ["core stability"],
    "trunk strength": ["core stability"],
    "grip strength": ["grip"],
    "grip_strength": ["grip"],
    "adductor groin": ["adductors", "lateral movement"],
    "adductor_groin": ["adductors", "lateral movement"],
    "cns fatigue": ["cns_freshness"],
    "cns_fatigue": ["cns_freshness"],
}

_STYLE_TAG_BASE = {
    "brawler": ["brawler", "compound", "posterior_chain", "power", "rate_of_force", "grip", "core"],
    "pressure_fighter": [
        "pressure_fighter",
        "conditioning",
        "core",
        "rate_of_force",
        "endurance",
        "mental_toughness",
        "ballistic_low_volume",
    ],
    "clinch_fighter": [
        "clinch_fighter",
        "grip",
        "core",
        "unilateral",
        "shoulders",
        "rotational",
        "balance",
        "isometric",
    ],
    "counter_striker": [
        "counter_striker",
        "reactive",
        "core",
        "anti_rotation",
        "cognitive",
        "visual_processing",
        "balance",
        "coordination",
        "skill_refinement",
    ],
    "distance_striker": [
        "distance_striker",
        "explosive",
        "reactive",
        "balance",
        "footwork",
        "coordination",
        "visual_processing",
        "speed",
        "ballistic_low_volume",
    ],
    "submission_hunter": ["submission_hunter", "grip", "mobility", "core", "stability", "anti_rotation", "rotational"],
    "kicker": ["kicker", "posterior_chain", "balance", "mobility", "unilateral", "hip_dominant", "adductors"],
    "scrambler": ["scrambler", "core", "rotational", "balance", "endurance", "agility", "reactive", "coordination", "grip"],
    "grappler": ["grappler", "grip", "core", "rotational", "balance", "unilateral"],
    "wrestler": ["wrestler", "grip", "posterior_chain", "core", "unilateral", "balance"],
    "clincher": ["clinch_fighter", "grip", "core", "unilateral", "shoulders", "rotational", "balance", "isometric"],
    "distance_fighter": [
        "distance_striker",
        "explosive",
        "reactive",
        "balance",
        "footwork",
        "coordination",
        "visual_processing",
        "speed",
        "ballistic_low_volume",
    ],
}

STYLE_TAG_MAP = {
    **_STYLE_TAG_BASE,
    "pressure fighter": _STYLE_TAG_BASE["pressure_fighter"],
    "clinch fighter": _STYLE_TAG_BASE["clinch_fighter"],
    "counter striker": _STYLE_TAG_BASE["counter_striker"],
    "distance striker": _STYLE_TAG_BASE["distance_striker"],
    "submission hunter": _STYLE_TAG_BASE["submission_hunter"],
    "distance fighter": _STYLE_TAG_BASE["distance_fighter"],
}

GOAL_TAG_MAP = {
    "power": [
        "explosive", "rate_of_force", "triple_extension", "horizontal_power",
        "plyometric", "elastic", "lateral_power",
    ],
    "strength": [
        "posterior_chain", "quad_dominant", "upper_body", "core", "pull", "hamstring",
        "hip_dominant", "eccentric", "compound", "isometric", "late_strength_touch",
        "maximal_strength_maintenance", "low_eccentric", "cns_freshness",
    ],
    "maximal_strength_maintenance": [
        "maximal_strength_maintenance",
        "late_strength_touch",
        "isometric",
        "posterior_chain",
        "quad_dominant",
        "grip",
        "cns_freshness",
        "low_eccentric",
    ],
    "endurance": [
        "aerobic", "glycolytic", "work_capacity", "mental_toughness",
        "conditioning", "improvised",
    ],
    "speed": [
        "speed", "agility", "reactive", "acceleration", "visual_processing",
    ],
    "mobility": [
        "mobility", "hip_dominant", "balance", "eccentric", "unilateral", "adductors",
        "stability", "movement_quality", "rehab_friendly",
    ],
    "grappler": [
        "wrestler", "bjj", "grip", "rotational", "core", "unilateral", "tactical",
    ],
    "grappling": [
        "wrestler", "bjj", "grip", "rotational", "core", "unilateral", "tactical",
    ],
    "striking": [
        "striking", "boxing", "muay_thai", "shoulders", "rate_of_force",
        "coordination", "visual_processing",
    ],
    "injury_prevention": [
        "recovery", "balance", "eccentric", "zero_impact", "parasympathetic",
        "cns_freshness", "unilateral", "movement_quality", "stability", "neck",
    ],
    "mental_resilience": [
        "mental_toughness", "cognitive", "parasympathetic", "visual_processing", "environmental",
    ],
    "skill_refinement": [
        "coordination", "skill", "footwork", "cognitive", "reactive", "skill_refinement",
    ],
    "coordination": ["coordination"],
    "recovery": ["recovery", "cns_freshness", "parasympathetic"],
    "weight_cut": ["recovery", "low_impact", "cns_freshness"],
}

GOAL_TAG_MAP["conditioning"] = list(GOAL_TAG_MAP["endurance"])
GOAL_TAG_MAP["explosive"] = list(GOAL_TAG_MAP["power"])
GOAL_TAG_MAP["reactive"] = list(GOAL_TAG_MAP["speed"])

WEAKNESS_TAG_MAP = {
    "core stability": ["core", "anti_rotation"],
    "cns_freshness": ["cns_freshness", "parasympathetic"],
    "cns fatigue": ["cns_freshness", "parasympathetic"],
    "cns_fatigue": ["cns_freshness", "parasympathetic"],
    "speed / reaction": ["speed", "reaction", "reactive", "coordination"],
    "lateral": ["lateral", "lateral_movement", "balance", "movement_quality"],
    "lateral movement": ["lateral", "lateral_movement", "balance", "movement_quality"],
    "conditioning": ["aerobic", "glycolytic", "work_capacity"],
    "gas_tank": ["aerobic", "glycolytic", "conditioning", "work_capacity"],
    "strength": ["posterior_chain", "quad_dominant", "upper_body", "core"],
    "power": ["explosive", "rate_of_force", "plyometric"],
    "speed": ["speed", "reaction", "reactive", "coordination"],
    "footwork": [
        "footwork",
        "coordination",
        "lateral",
        "lateral_movement",
        "ringcraft",
        "angles",
        "pivot",
        "stance",
        "balance",
        "movement_quality",
        "stance_reset",
        "angle_exit",
    ],
    "rotation": ["rotational", "anti_rotation"],
    "balance": ["balance", "stability", "unilateral"],
    "mobility": ["mobility", "hip_dominant", "movement_quality"],
    "coordination": ["coordination", "balance", "reactive"],
    "trunk_strength": ["core", "anti_rotation", "stability"],
    "explosiveness": ["explosive", "rate_of_force", "plyometric"],
    "shoulders": ["shoulders", "upper_body"],
    "shoulder": ["shoulders", "upper_body"],
    "hip mobility": ["hip_dominant", "mobility"],
    "grip": ["grip", "pull"],
    "grip strength": ["grip", "pull"],
    "grip_strength": ["grip", "pull"],
    "posterior_chain": ["posterior_chain", "hip_dominant"],
    "posterior chain": ["posterior_chain", "hip_dominant"],
    "quad_dominant": ["quad_dominant", "eccentric"],
    "knees": ["quad_dominant", "eccentric"],
    "coordination / proprioception": ["coordination"],
    "coordination/proprioception": ["coordination"],
    "coordination_proprioception": ["coordination", "balance"],
    "adductors": ["adductors", "balance", "lateral_power"],
    "adductor groin": ["adductors", "balance", "lateral_power"],
    "adductor_groin": ["adductors", "balance", "lateral_power"],
}


# --- Anatomical involvement versus adaptation --------------------------------
#
# The maps above describe which bank tags an intake term touches. Some of those
# tags only say which body parts an exercise uses: swimming carries
# ``upper_body`` and a sled push carries ``core``. That is anatomical
# involvement, not evidence that the exercise's training method develops
# strength, power, speed, conditioning or trunk strength. When the athlete's
# selected priority names an adaptation, such a tag may describe the exercise
# but never earns the priority match. Regional priorities (shoulders, posterior
# chain, grip, adductors, ...) keep their anatomical tags: there the region is
# the point.
ANATOMICAL_INVOLVEMENT_TAGS = frozenset(
    {
        "upper_body",
        "lower_body",
        "core",
        "posterior_chain",
        "quad_dominant",
        "hamstring",
        "hip_dominant",
        "glute_load_high",
        "shoulders",
        "adductors",
        "pull",
        "push",
    }
)

# Selected priority wording -> the adaptation it names. Strength-bank items
# evidence these through ``strength_session_quality.strength_adaptation_relevance``.
PRIORITY_ADAPTATIONS = {
    "strength": "strength",
    "maximal_strength_maintenance": "strength",
    "power": "power",
    "explosive": "power",
    "explosiveness": "power",
    "explosive_power": "power",
    "speed": "speed",
    "reactive": "speed",
    "speed / reaction": "speed",
    "speed_reaction": "speed",
    "trunk_strength": "trunk_strength",
    "core stability": "trunk_strength",
    "core_stability": "trunk_strength",
    "core_strength": "trunk_strength",
}

ADAPTATION_PRIORITY_KEYS = frozenset(
    {
        *PRIORITY_ADAPTATIONS,
        "conditioning",
        "endurance",
        "gas_tank",
        "mobility",
    }
)


# Strength is a method-and-load adaptation. No single bank tag establishes it:
# ``compound`` or ``isometric`` describe a plank as well as a heavy squat, and
# ``low_eccentric``/``cns_freshness`` describe low cost. A strength priority is
# therefore matched only by the item's own adaptation evidence.
_EVIDENCE_ONLY_PRIORITIES = frozenset({"strength"})


def _priority_match_map(tag_map: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        key: []
        if key in _EVIDENCE_ONLY_PRIORITIES
        else [
            tag
            for tag in tags
            if key not in ADAPTATION_PRIORITY_KEYS or tag not in ANATOMICAL_INVOLVEMENT_TAGS
        ]
        for key, tags in tag_map.items()
    }


# The maps scoring uses to decide whether a bank tag MATCHES a selected
# priority. Identical to the maps above except that adaptation priorities do not
# match on anatomical involvement, and strength matches on evidence only.
GOAL_PRIORITY_TAG_MAP = _priority_match_map(GOAL_TAG_MAP)
WEAKNESS_PRIORITY_TAG_MAP = _priority_match_map(WEAKNESS_TAG_MAP)


def priority_adaptation(value: str) -> str:
    """The adaptation a selected goal/weakness names, or "" for a regional one."""
    key = str(value or "").strip().lower()
    return PRIORITY_ADAPTATIONS.get(key) or PRIORITY_ADAPTATIONS.get(key.replace(" ", "_"), "")
