PHASE_EQUIPMENT_BOOST = {
    "GPP": {"barbell", "trap_bar", "sled", "pullup_bar"},
    "SPP": {"landmine", "cable", "medicine_ball", "bands"},
    "TAPER": {"medicine_ball", "bodyweight", "bands", "partner"},
}

PHASE_TAG_BOOST = {
    "GPP": {"triphasic": 1, "tempo": 1, "eccentric": 1},
    "SPP": {"contrast": 1.5, "explosive": 1.5},
    "TAPER": {"neural_primer": 2, "cluster": 2, "speed": 2},
}

PHASE_SYSTEM_RATIOS = {
    "GPP": {"aerobic": 0.5, "glycolytic": 0.3, "alactic": 0.2},
    "SPP": {"glycolytic": 0.5, "alactic": 0.3, "aerobic": 0.2},
    "TAPER": {"alactic": 0.7, "aerobic": 0.3, "glycolytic": 0.0},
}

STYLE_CONDITIONING_RATIO = {
    "GPP": 0.20,
    "SPP": 0.60,
    "TAPER": 0.05,
}

STRENGTH_PER_DAY = {"GPP": 7, "SPP": 6, "TAPER": 4}
CONDITIONING_PER_DAY = {"GPP": 4, "SPP": 3, "TAPER": 3}
