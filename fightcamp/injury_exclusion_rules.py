INJURY_RULES = {
    "head": {
        "ban_keywords": ["sparring", "hard contact", "head contact", "head impact", "headbutt"],
        "ban_tags": ["contact", "sparring"],
    },
    "neck": {
        "ban_keywords": ["bridge", "wrestler bridge", "neck harness", "neck flexion", "neck extension"],
        "ban_tags": ["neck_loaded", "neck_bridge"],
    },
    "upper_back": {
        "ban_keywords": ["heavy row", "back extension", "yoke", "heavy carry"],
        "ban_tags": ["upper_back_loaded", "axial_heavy"],
    },
    "lower_back": {
        "ban_keywords": [
            "deadlift",
            "good morning",
            "jefferson curl",
            "heavy hinge",
            "back squat",
            "rdl",
        ],
        "ban_tags": ["axial_heavy", "hinge_heavy"],
    },
    "si_joint": {
        "ban_keywords": ["deadlift", "good morning", "rdl", "back squat", "heavy hinge"],
        "ban_tags": ["axial_heavy", "hinge_heavy"],
    },
    "shoulder": {
        "ban_keywords": [
            "overhead",
            "press",
            "bench",
            "dip",
            "snatch",
            "jerk",
            "push press",
            "handstand",
            "kipping",
        ],
        "ban_tags": ["overhead", "upper_push", "shoulder_heavy", "high_cns_upper"],
    },
    "chest": {
        "ban_keywords": ["bench", "fly", "pec deck", "dip", "push-up"],
        "ban_tags": ["upper_push", "horizontal_push"],
    },
    "elbow": {
        "ban_keywords": ["dip", "skullcrusher", "extension", "close-grip", "muscle-up"],
        "ban_tags": ["elbow_extension_heavy"],
    },
    "forearm": {
        "ban_keywords": ["wrist curl", "reverse curl", "farmer", "dead hang", "rope climb"],
        "ban_tags": ["grip_max", "forearm_load_high"],
    },
    "wrist": {
        "ban_keywords": ["push-up", "handstand", "front rack", "clean", "snatch", "bear crawl"],
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
        "ban_keywords": ["hip thrust", "glute bridge", "heavy hinge", "rdl", "deadlift"],
        "ban_tags": ["hinge_heavy", "glute_load_high"],
    },
    "hip_flexor": {
        "ban_keywords": ["hanging leg raise", "high knees", "sprint", "lunge", "split squat"],
        "ban_tags": ["hip_flexion_loaded", "max_velocity"],
    },
    "hamstring": {
        "ban_keywords": ["rdl", "good morning", "nordic", "ham curl", "sprint"],
        "ban_tags": ["hamstring_eccentric_high", "max_velocity"],
    },
    "quad": {
        "ban_keywords": ["heavy squat", "leg extension", "lunge", "split squat"],
        "ban_tags": ["knee_dominant_heavy"],
    },
    "knee": {
        "ban_keywords": [
            "jump",
            "depth jump",
            "plyo",
            "hard landing",
            "heavy squat",
            "lunge",
            "split squat",
        ],
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
    "unspecified": {"ban_keywords": [], "ban_tags": []},
}

INJURY_REGION_KEYWORDS = {
    "head": ["concussion", "head injury", "head", "migraine", "vertigo"],
    "neck": ["neck strain", "whiplash", "cervical", "neck"],
    "upper_back": ["upper back", "thoracic", "t-spine", "mid back"],
    "lower_back": ["low back", "lower back", "lumbar", "disc", "sciatica"],
    "si_joint": ["si joint", "sacroiliac", "sacro-iliac"],
    "shoulder": [
        "shoulder pain",
        "impingement",
        "rotator cuff",
        "labrum",
        "ac joint",
        "biceps tendonitis",
        "shoulder",
    ],
    "chest": ["pec strain", "pectoral", "chest"],
    "elbow": ["elbow", "tennis elbow", "golfer", "golfer's elbow"],
    "forearm": ["forearm", "forearm strain"],
    "wrist": ["wrist", "tfcc", "tendonitis"],
    "hand": ["hand", "finger", "thumb", "boxer"],
    "hip": ["hip pain", "hip impingement", "labral", "bursitis", "hip"],
    "groin": ["groin", "adductor", "sports hernia"],
    "glute": ["glute", "piriformis"],
    "hip_flexor": ["hip flexor", "iliopsoas"],
    "hamstring": ["hamstring"],
    "quad": ["quad", "quadriceps"],
    "knee": [
        "knee pain",
        "meniscus",
        "acl",
        "mcl",
        "lcl",
        "pcl",
        "patellar",
        "quad tendon",
        "knee",
    ],
    "shin": ["shin splints", "tibial", "shin"],
    "calf": ["calf", "soleus"],
    "achilles": ["achilles"],
    "ankle": ["ankle", "ankle sprain", "instability"],
    "foot": ["foot", "plantar", "metatarsal"],
    "toe": ["toe"],
}
