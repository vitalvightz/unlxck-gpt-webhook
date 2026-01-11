INJURY_RULES = {
    "head": {
        "ban_keywords": ["sparring", "hard contact", "hard-contact"],
        "ban_tags": ["contact"],
    },
    "neck": {
        "ban_keywords": ["bridges", "wrestler bridge", "neck harness"],
        "ban_tags": ["neck_loaded"],
    },
    "upper_back": {
        "ban_keywords": ["deadlift", "good morning", "back squat", "rdl", "heavy hinge"],
        "ban_tags": ["axial_heavy", "hinge_heavy"],
    },
    "lower_back": {
        "ban_keywords": ["deadlift", "good morning", "jefferson curl", "heavy hinge", "back squat", "rdl"],
        "ban_tags": ["axial_heavy", "hinge_heavy"],
    },
    "si_joint": {
        "ban_keywords": ["deadlift", "good morning", "back squat", "front squat", "rdl"],
        "ban_tags": ["axial_heavy", "hinge_heavy", "knee_dominant_heavy"],
    },
    "shoulder": {
        "ban_keywords": ["overhead", "press", "bench", "dip", "snatch", "jerk", "push press", "handstand", "kipping"],
        "ban_tags": ["overhead", "upper_push", "shoulder_heavy", "high_cns_upper"],
    },
    "chest": {
        "ban_keywords": ["bench", "push-up", "pushup", "dip", "fly"],
        "ban_tags": ["upper_push"],
    },
    "elbow": {
        "ban_keywords": ["dip", "skullcrusher", "extension", "close-grip", "muscle-up"],
        "ban_tags": ["elbow_extension_heavy"],
    },
    "forearm": {
        "ban_keywords": ["towel", "thick grip", "wrist roller", "farmer", "dead hang"],
        "ban_tags": ["grip_max"],
    },
    "wrist": {
        "ban_keywords": ["push-up", "pushup", "handstand", "front rack", "clean", "snatch", "bear crawl"],
        "ban_tags": ["wrist_loaded_extension", "front_rack"],
    },
    "hand": {
        "ban_keywords": ["rope climb", "towel", "thick grip", "plate pinch", "farmer", "dead hang"],
        "ban_tags": ["grip_max", "hand_crush"],
    },
    "hip": {
        "ban_keywords": ["deep squat", "cossack", "pistol", "wide stance", "hip airplane"],
        "ban_tags": ["deep_flexion", "hip_irritant"],
    },
    "groin": {
        "ban_keywords": ["cossack", "lateral lunge", "wide stance", "adductor machine"],
        "ban_tags": ["adductor_load_high"],
    },
    "glute": {
        "ban_keywords": ["hip thrust", "glute bridge", "deadlift", "good morning"],
        "ban_tags": ["hinge_heavy"],
    },
    "hip_flexor": {
        "ban_keywords": ["high knees", "mountain climber", "hanging knee", "hanging leg raise", "sprint"],
        "ban_tags": ["max_velocity"],
    },
    "hamstring": {
        "ban_keywords": ["rdl", "good morning", "nordic", "ham curl", "sprint"],
        "ban_tags": ["hamstring_eccentric_high", "max_velocity"],
    },
    "quad": {
        "ban_keywords": ["heavy squat", "front squat", "back squat", "lunge", "split squat"],
        "ban_tags": ["knee_dominant_heavy"],
    },
    "knee": {
        "ban_keywords": ["jump", "depth jump", "plyo", "hard landing", "heavy squat", "lunge", "split squat"],
        "ban_tags": ["high_impact_plyo", "knee_dominant_heavy"],
    },
    "shin": {
        "ban_keywords": ["jump rope", "pogo", "repeated hops", "high volume running"],
        "ban_tags": ["impact_rebound_high"],
    },
    "calf": {
        "ban_keywords": ["pogo", "sprints", "bounds", "repeated jumps"],
        "ban_tags": ["calf_rebound_high"],
    },
    "achilles": {
        "ban_keywords": ["depth jump", "drop jump", "max sprint", "hard bounds"],
        "ban_tags": ["achilles_high_risk_impact", "max_velocity"],
    },
    "ankle": {
        "ban_keywords": ["hard cuts", "lateral bounds", "uneven surface", "depth jump"],
        "ban_tags": ["ankle_lateral_impact_high"],
    },
    "foot": {
        "ban_keywords": ["barefoot sprints", "jump rope", "pogo", "repeated hops"],
        "ban_tags": ["foot_impact_high"],
    },
    "toe": {
        "ban_keywords": ["barefoot sprints", "jump rope", "pogo", "repeated hops"],
        "ban_tags": ["foot_impact_high"],
    },
    "unspecified": {
        "ban_keywords": [],
        "ban_tags": [],
    },
}

INJURY_REGION_KEYWORDS = {
    "head": ["concussion", "head injury", "head", "migraine", "vertigo"],
    "neck": ["neck", "cervical", "whiplash"],
    "upper_back": ["upper back", "thoracic", "t-spine", "mid back"],
    "lower_back": ["low back", "lower back", "lumbar", "disc", "sciatica"],
    "si_joint": ["si joint", "sacroiliac"],
    "shoulder": ["shoulder", "rotator cuff", "labrum", "ac joint", "biceps tendon"],
    "chest": ["pec", "pectoral", "chest"],
    "elbow": ["elbow", "tennis elbow", "golfer"],
    "forearm": ["forearm"],
    "wrist": ["wrist", "tfc", "tfcc"],
    "hand": ["hand", "finger", "thumb"],
    "hip": ["hip", "labral", "impingement", "bursitis"],
    "groin": ["groin", "adductor", "sports hernia"],
    "glute": ["glute", "piriformis"],
    "hip_flexor": ["hip flexor"],
    "hamstring": ["hamstring"],
    "quad": ["quad", "quadriceps"],
    "knee": ["knee", "acl", "mcl", "lcl", "pcl", "meniscus", "patellar"],
    "shin": ["shin", "tibial"],
    "calf": ["calf"],
    "achilles": ["achilles"],
    "ankle": ["ankle"],
    "foot": ["foot", "plantar", "metatarsal"],
    "toe": ["toe"],
}
