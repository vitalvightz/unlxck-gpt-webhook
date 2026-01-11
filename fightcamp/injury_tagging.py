INFERRED_TAG_RULES = {
    "overhead": ["overhead", "push press", "push-press", "jerk", "snatch", "handstand"],
    "upper_push": ["bench", "press", "push-up", "pushup", "dip"],
    "elbow_extension_heavy": ["dip", "skullcrusher", "extension", "close-grip", "muscle-up"],
    "wrist_loaded_extension": ["push-up", "pushup", "handstand", "bear crawl", "front rack", "clean", "snatch"],
    "front_rack": ["front rack", "clean", "front squat"],
    "grip_max": ["rope climb", "towel", "thick grip", "plate pinch", "farmer", "dead hang"],
    "hand_crush": ["plate pinch", "towel", "thick grip", "farmer", "rope climb"],
    "axial_heavy": ["back squat", "front squat", "deadlift", "good morning"],
    "hinge_heavy": ["deadlift", "rdl", "romanian deadlift", "good morning"],
    "deep_flexion": ["deep squat", "pistol", "cossack"],
    "hip_irritant": ["hip airplane", "pistol", "cossack", "wide stance"],
    "adductor_load_high": ["cossack", "lateral lunge", "wide stance", "adductor machine"],
    "hamstring_eccentric_high": ["nordic", "ham curl", "rdl", "good morning"],
    "knee_dominant_heavy": ["heavy squat", "back squat", "front squat", "split squat", "lunge"],
    "high_impact_plyo": ["depth jump", "drop jump", "plyo", "hard landing"],
    "impact_rebound_high": ["jump rope", "pogo", "repeated hops", "bounds"],
    "calf_rebound_high": ["pogo", "bounds", "sprint", "repeated jumps"],
    "achilles_high_risk_impact": ["depth jump", "drop jump", "hard bounds", "max sprint"],
    "ankle_lateral_impact_high": ["hard cuts", "lateral bounds", "uneven surface", "depth jump"],
    "foot_impact_high": ["barefoot sprints", "jump rope", "pogo", "repeated hops"],
    "max_velocity": ["sprint", "max sprint", "all-out sprint"],
    "contact": ["sparring", "hard contact", "hard-contact"],
}


def infer_tags_from_name(name: str) -> list[str]:
    name_lower = name.lower()
    inferred = set()
    for tag, keywords in INFERRED_TAG_RULES.items():
        if any(keyword in name_lower for keyword in keywords):
            inferred.add(tag)
    return sorted(inferred)
