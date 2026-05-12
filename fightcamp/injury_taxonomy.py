from __future__ import annotations

from typing import Any

INJURY_TAXONOMY: dict[str, dict[str, Any]] = {
    "sprain": {"display": "Sprain", "category": "soft_tissue", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "strain": {"display": "Strain", "category": "soft_tissue", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "tightness": {"display": "Tightness", "category": "symptom", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "contusion": {"display": "Contusion", "category": "soft_tissue", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "swelling": {"display": "Swelling", "category": "symptom", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "tendonitis": {"display": "Tendonitis", "category": "overuse", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "impingement": {"display": "Impingement", "category": "mechanical", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "instability": {"display": "Instability", "category": "mechanical", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "stiffness": {"display": "Stiffness", "category": "symptom", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "pain": {"display": "Pain", "category": "symptom", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "soreness": {"display": "Soreness", "category": "symptom", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "hyperextension": {"display": "Hyperextension", "category": "soft_tissue", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "abrasion": {"display": "Abrasion", "category": "surface", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "cut": {"display": "Cut", "category": "surface", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "laceration": {"display": "Laceration", "category": "surface", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "graze": {"display": "Graze", "category": "surface", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "blister": {"display": "Blister", "category": "surface", "default_severity": "low", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "unspecified": {"display": "Unspecified", "category": "unknown", "default_severity": "moderate", "urgent": False, "rehab_allowed": True, "flags": [], "blocked_training_tags": [], "blocked_rehab_terms": [], "requires_clinical_clearance": False, "red_flag_message": ""},
    "acl_tear": {"display": "ACL Tear", "category": "structural", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_ligament_tear"], "blocked_training_tags": ["contact", "sparring", "high_impact_plyo", "landing_stress_high", "reactive_rebound_high", "max_velocity", "hard_cutting", "decel_high", "knee_dominant_heavy", "deep_knee_flexion_loaded"], "blocked_rehab_terms": ["pogo", "jump", "hop", "depth", "reactive", "sprint", "cutting", "spanish squat", "step-down"], "requires_clinical_clearance": True, "red_flag_message": "Do not train this injury normally until medically cleared."},
    "ligament_tear": {"display": "Ligament Tear", "category": "structural", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_ligament_tear"], "blocked_training_tags": ["contact", "sparring", "hard_cutting", "decel_high", "high_impact_plyo"], "blocked_rehab_terms": ["jump", "hop", "sprint", "cutting", "depth"], "requires_clinical_clearance": True, "red_flag_message": "Suspected ligament tear requires clinical clearance before return to loading."},
    "tendon_rupture": {"display": "Tendon Rupture", "category": "structural", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_tendon_rupture"], "blocked_training_tags": ["high_impact_plyo", "reactive_rebound_high", "max_velocity", "running_volume_high", "calf_rebound_high", "forefoot_load_high", "explosive_lower"], "blocked_rehab_terms": ["eccentric calf drops", "pogo", "hop", "jump", "sprint", "depth"], "requires_clinical_clearance": True, "red_flag_message": "Suspected tendon rupture requires medical clearance before return to loading."},
    "muscle_rupture": {"display": "Muscle Rupture", "category": "structural", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_muscle_rupture"], "blocked_training_tags": ["max_velocity", "explosive_lower", "hard_cutting"], "blocked_rehab_terms": ["sprint", "jump", "explosive"], "requires_clinical_clearance": True, "red_flag_message": "Suspected muscle rupture requires clinical clearance before return to high-load activity."},
    "fracture": {"display": "Fracture", "category": "structural", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_fracture"], "blocked_training_tags": ["contact", "sparring", "high_impact_plyo"], "blocked_rehab_terms": ["jump", "impact", "loaded"], "requires_clinical_clearance": True, "red_flag_message": "Suspected fracture requires immediate clinical assessment and clearance."},
    "dislocation": {"display": "Dislocation", "category": "structural", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_dislocation"], "blocked_training_tags": ["contact", "sparring", "overhead", "dynamic_overhead", "press_heavy", "explosive_upper_push"], "blocked_rehab_terms": ["overhead", "press", "push press", "snatch", "jerk", "dip", "explosive"], "requires_clinical_clearance": True, "red_flag_message": "Suspected dislocation requires clinical clearance before loading or contact."},
    "concussion": {"display": "Concussion", "category": "neurological", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_concussion"], "blocked_training_tags": ["contact", "sparring", "head_impact", "hard_contact", "live_rounds", "high_cns", "max_velocity", "explosive_conditioning"], "blocked_rehab_terms": [], "requires_clinical_clearance": True, "red_flag_message": "No contact, sparring, high-CNS conditioning, or return-to-play progression until medically cleared."},
    "post_surgery": {"display": "Post Surgery", "category": "post_op", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "post_surgery"], "blocked_training_tags": ["contact", "sparring"], "blocked_rehab_terms": [], "requires_clinical_clearance": True, "red_flag_message": "Post-surgery injuries require clinician-led return-to-training clearance."},
    "infection": {"display": "Infection", "category": "medical", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_infection"], "blocked_training_tags": ["contact", "sparring", "high_intensity"], "blocked_rehab_terms": [], "requires_clinical_clearance": True, "red_flag_message": "Possible infection requires urgent medical review before training."},
    "acute_nerve_issue": {"display": "Acute Nerve Issue", "category": "neurological", "default_severity": "high", "urgent": True, "rehab_allowed": False, "flags": ["urgent", "structural_red_flag", "suspected_acute_nerve_issue"], "blocked_training_tags": ["contact", "sparring", "max_velocity"], "blocked_rehab_terms": [], "requires_clinical_clearance": True, "red_flag_message": "Acute nerve symptoms require clinical review before loading."},
}


def get_injury_rule(key: str | None) -> dict:
    normalized = str(key or "").strip().lower().replace("-", "_").replace(" ", "_")
    return dict(INJURY_TAXONOMY.get(normalized, INJURY_TAXONOMY["unspecified"]))

def get_default_severity(key: str | None) -> str:
    return str(get_injury_rule(key).get("default_severity") or "moderate")

def is_urgent_injury(key: str | None) -> bool:
    return bool(get_injury_rule(key).get("urgent"))

def rehab_allowed(key: str | None) -> bool:
    return bool(get_injury_rule(key).get("rehab_allowed", True))

def get_required_flags(key: str | None) -> list[str]:
    return list(get_injury_rule(key).get("flags") or [])

def get_blocked_training_tags(key: str | None) -> set[str]:
    return set(get_injury_rule(key).get("blocked_training_tags") or [])

def get_blocked_rehab_terms(key: str | None) -> set[str]:
    return set(get_injury_rule(key).get("blocked_rehab_terms") or [])

def get_red_flag_message(key: str | None) -> str:
    return str(get_injury_rule(key).get("red_flag_message") or "")

def derive_injury_type_severity_map() -> dict[str, str]:
    return {k: str(v.get("default_severity") or "moderate") for k, v in INJURY_TAXONOMY.items()}

def derive_urgent_injury_tokens() -> set[str]:
    out: set[str] = set()
    for key, rule in INJURY_TAXONOMY.items():
        if not rule.get("urgent"):
            continue
        out.add(key)
        out.add(key.replace("_", "-"))
        out.add(key.replace("_", " "))
        out.add(key.split("_")[-1])
    return out

def derive_red_flag_types() -> list[str]:
    return sorted([key for key, rule in INJURY_TAXONOMY.items() if rule.get("urgent") or "structural_red_flag" in (rule.get("flags") or [])])
