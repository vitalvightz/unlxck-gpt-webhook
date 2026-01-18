"""Shared tag mapping definitions for training plan generation."""

GOAL_NORMALIZER = {
    "Power & Explosiveness": "explosive",
    "Conditioning / Endurance": "conditioning",
    "Maximal Strength": "strength",
    "Mobility": "mobility",
    "Speed": "reactive",
    "Agility": "lateral",
    "Core Stability": "core",
    "CNS Fatigue": "cns",
    "Speed / Reaction": "reactive",
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
    "coordination / proprioception": ["coordination"],
    "coordination/proprioception": ["coordination"],
    "shoulder": ["shoulders"],
    "shoulders": ["shoulders"],
}

STYLE_TAG_MAP = {
    "brawler": ["compound", "posterior_chain", "power", "rate_of_force", "grip", "core"],
    "pressure fighter": ["conditioning", "core", "rate_of_force", "endurance", "mental_toughness", "anaerobic_alactic"],
    "clinch fighter": ["grip", "core", "unilateral", "shoulders", "rotational", "balance"],
    "distance striker": ["explosive", "reactive", "balance", "footwork", "coordination", "visual_processing"],
    "counter striker": ["reactive", "core", "anti_rotation", "cognitive", "visual_processing", "balance"],
    "submission hunter": ["grip", "mobility", "core", "stability", "anti_rotation", "rotational"],
    "kicker": ["hinge", "posterior_chain", "balance", "mobility", "unilateral", "hip_dominant"],
    "scrambler": ["core", "rotational", "balance", "endurance", "agility", "reactive"],
}

GOAL_TAG_MAP = {
    "power": [
        "explosive", "rate_of_force", "triple_extension", "horizontal_power",
        "plyometric", "elastic", "lateral_power", "deadlift",
        "ATP-PCr", "anaerobic_alactic", "speed_strength",
    ],
    "strength": [
        "posterior_chain", "quad_dominant", "upper_body", "core", "pull", "hamstring",
        "hip_dominant", "eccentric", "deadlift", "compound", "manual_resistance", "isometric",
    ],
    "endurance": [
        "aerobic", "glycolytic", "anaerobic_lactic", "work_capacity", "mental_toughness",
        "conditioning", "improvised", "volume_tolerance",
    ],
    "speed": [
        "speed", "agility", "footwork", "reactive", "acceleration", "ATP-PCr", "anaerobic_alactic",
        "visual_processing", "reactive_decision",
    ],
    "mobility": [
        "mobility", "hip_dominant", "balance", "eccentric", "unilateral", "adductors",
        "stability", "movement_quality", "range", "rehab_friendly",
    ],
    "grappler": [
        "wrestler", "bjj", "grip", "rotational", "core", "unilateral", "tactical",
        "manual_resistance", "positioning",
    ],
    "grappling": [
        "wrestler", "bjj", "grip", "rotational", "core", "unilateral", "tactical",
        "manual_resistance", "positioning",
    ],
    "striking": [
        "striking", "boxing", "muay_thai", "shoulders", "rate_of_force",
        "coordination", "visual_processing", "rhythm", "timing",
    ],
    "injury_prevention": [
        "recovery", "balance", "eccentric", "zero_impact", "parasympathetic",
        "cns_freshness", "unilateral", "movement_quality", "stability", "neck",
    ],
    "mental_resilience": [
        "mental_toughness", "cognitive", "parasympathetic", "visual_processing",
        "focus", "environmental", "pressure_tolerance",
    ],
    "skill_refinement": [
        "coordination", "skill", "footwork", "cognitive", "focus", "reactive", "decision_speed", "skill_refinement",
    ],
    "coordination": ["coordination"],
}

WEAKNESS_TAG_MAP = {
    "core stability": ["core", "anti_rotation"],
    "cns fatigue": ["cns_freshness", "parasympathetic"],
    "speed / reaction": ["speed", "reaction", "reactive", "coordination"],
    "lateral movement": ["lateral_power", "agility", "balance"],
    "conditioning": ["aerobic", "glycolytic", "work_capacity"],
    "rotation": ["rotational", "anti_rotation"],
    "balance": ["balance", "stability", "unilateral"],
    "explosiveness": ["explosive", "rate_of_force", "plyometric"],
    "shoulders": ["shoulders", "upper_body"],
    "shoulder": ["shoulders", "upper_body"],
    "hip mobility": ["hip_dominant", "mobility"],
    "grip strength": ["grip", "pull"],
    "posterior chain": ["posterior_chain", "hip_dominant"],
    "knees": ["quad_dominant", "eccentric"],
    "coordination / proprioception": ["coordination"],
    "coordination/proprioception": ["coordination"],
}
