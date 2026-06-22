from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from .injury_scoring import score_injury_phrase
from .injury_negation import remove_negated_phrases
from .injury_synonyms import parse_injury_phrase, split_injury_text
from .input_parsing import GuidedInjury
from .injury_danger_terms import detect_danger_term_routes


@dataclass(frozen=True)
class TriageFeatures:
    high_risk_diagnoses: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    structural_severe_signals: list[str] = field(default_factory=list)
    function_loss_signals: list[str] = field(default_factory=list)
    clinician_restriction_signals: list[str] = field(default_factory=list)
    urgent_flags: list[str] = field(default_factory=list)
    raw_evidence: dict[str, list[str]] = field(default_factory=dict)


# ── Shared regex fragments ─────────────────────────────────────────────

_TEAR_SYNONYM_PATTERN = r"(?:tears?|torn)"
_RUPTURE_OR_TEAR_PATTERN = rf"(?:ruptured?|{_TEAR_SYNONYM_PATTERN})"

_CANNOT_OR_UNABLE = r"(?:cannot|can'?t|unable\s+to|not\s+able\s+to)"
_CANNOT_BEAR_WEIGHT = (
    rf"\b{_CANNOT_OR_UNABLE}\s+bear\s+weight\b"
    rf"|\b{_CANNOT_OR_UNABLE}\s+bare\s+weight\b"
    rf"|\b(?:unable\s+to|cannot|can'?t)\s+walk\b"
)
_AFFIRMATIVE_DEFORMITY = (
    r"\b(?:visible|obvious)\s+deformit(?:y|ies)\b"
    r"|\bdeformit(?:y|ies)\s+present\b"
    r"|\b(?:looks\s+)?deformed\b"
    r"|\bbone\s+looks\s+out\s+of\s+place\b"
)

_NEGATION_SPLIT_PATTERN = re.compile(
    r"\b(?:but|however|although|though|except)\b",
    re.IGNORECASE,
)


# ── Red flag and function-loss negation guards ─────────────────────────

_SIGNAL_NEGATION_PATTERNS: dict[str, tuple[str, ...]] = {
    "numbness": (
        r"\b(?:no|not|without|denies?|denied|negative\s+for)\s+(?:\w+\s+){0,4}numb(?:ness)?\b",
    ),
    "tingling": (
        r"\b(?:no|not|without|denies?|denied|negative\s+for)\s+(?:\w+\s+){0,4}tingl(?:e|ing)\b",
    ),
    "weakness": (
        r"\b(?:no|not|without|denies?|denied|negative\s+for)\s+(?:\w+\s+){0,4}weak(?:ness)?\b",
    ),
    "cannot_bear_weight": (
        r"\bcan\s+bear\s+weight\b",
        r"\bable\s+to\s+bear\s+weight\b",
        r"\bcan\s+walk\b",
        r"\bcan\s+still\s+walk\b",
        r"\bstill\s+walk(?:ing)?\b",
        r"\bwalking\s+(?:fine|okay|ok)\b",
    ),
    "deformity": (
        r"\b(?:no|not|without|denies?|denied|negative\s+for)\s+(?:\w+\s+){0,4}(?:visible\s+|obvious\s+)?deformit(?:y|ies)\b",
        r"\bdeformit(?:y|ies)\s+(?:absent|not\s+present)\b",
        r"\bno\s+obvious\s+deformit(?:y|ies)\b",
        r"\bno\s+visible\s+deformit(?:y|ies)\b",
    ),
    "shortness_of_breath": (
        r"\b(?:no|not|without|denies?|denied|negative\s+for)\s+(?:\w+\s+){0,4}short(?:ness)?\s+of\s+breath\b",
    ),
    "coughing_blood": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}(?:cough(?:ing)?\s+blood|hemoptysis)\b",
    ),
    "loss_of_consciousness": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}loss\s+of\s+consciousness\b",
        r"\bdid\s+not\s+(?:pass\s+out|black\s+out|get\s+knocked\s+out)\b",
    ),
    "confusion": (
        r"\b(?:no|not|without|denies?|denied|negative\s+for)\s+(?:\w+\s+){0,4}confus(?:ed|ion)\b",
    ),
    "chest_pain": (
        r"\b(?:no|not|without|denies?|denied|negative\s+for)\s+(?:\w+\s+){0,4}chest\s+(?:pain|pressure)\b",
    ),
    "breathing_pain": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}pain\s+(?:when|with)?\s*breath(?:ing)?\b",
        r"\bbreath(?:ing)?\s+(?:is\s+)?(?:not\s+)?pain[-\s]?free\b",
    ),
    "vomiting_after_head_impact": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}vomit(?:ing|ed)?\b",
    ),
    "severe_headache_after_head_impact": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}severe\s+headache\b",
    ),
    "seizure_or_convulsion": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}(?:seizure|convulsion)s?\b",
    ),
    "amnesia_or_memory_loss": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}(?:amnesia|memory\s+loss)\b",
    ),
    "blurred_or_double_vision": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}(?:blurred\s+vision|double\s+vision|diplopia)\b",
    ),
    "slurred_speech": (
        r"\b(?:no|not|without|denies?|denied)\s+(?:\w+\s+){0,4}slurred\s+speech\b",
    ),
}


def _label_is_negated(text: str, label: str) -> bool:
    """Return True only when the same local text segment negates this label.

    Splitting on contrast words prevents suppressing real positives in phrases like:
    "no numbness but weakness".
    """
    patterns = _SIGNAL_NEGATION_PATTERNS.get(label)
    if not patterns:
        return False

    lowered = str(text or "").lower()
    for segment in _NEGATION_SPLIT_PATTERN.split(lowered):
        if any(re.search(pattern, segment) for pattern in patterns):
            return True
    return False


# ── Main triage patterns ───────────────────────────────────────────────

_RED_FLAG_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bnumb(?:ness)?\b", "numbness"),
    (r"\btingl(?:e|ing)\b", "tingling"),
    (r"\bweak(?:ness)?\b", "weakness"),
    (_CANNOT_BEAR_WEIGHT, "cannot_bear_weight"),
    (r"\brapid(?:ly)?\s+worsening\s+swelling\b", "rapid_swelling"),
    (_AFFIRMATIVE_DEFORMITY, "deformity"),
    (r"\bshort(?:ness)?\s+of\s+breath\b", "shortness_of_breath"),
    (r"\bcough(?:ing)?\s+blood\b|\bhemoptysis\b", "coughing_blood"),
    (r"\bloss\s+of\s+consciousness\b|\bpassed\s+out\b|\bknocked\s+out\b", "loss_of_consciousness"),
    (r"\bconfus(?:ed|ion)\b", "confusion"),
    (r"\bchest\s+pain\b|\bchest\s+pressure\b", "chest_pain"),
    (r"\bpain\s+(?:when|with)?\s*breath(?:ing)?\b|\bpainful\s+breath(?:ing)?\b", "breathing_pain"),
    (
        r"\bvomit(?:ing|ed)?\b[\w\s-]{0,40}\b(?:head|concussion|impact|hit)\b"
        r"|\b(?:head|concussion|impact|hit)\b[\w\s-]{0,40}\bvomit(?:ing|ed)?\b",
        "vomiting_after_head_impact",
    ),
    (
        r"\bsevere\s+headache\b[\w\s-]{0,40}\b(?:head|concussion|impact|hit)\b"
        r"|\b(?:head|concussion|impact|hit)\b[\w\s-]{0,40}\bsevere\s+headache\b",
        "severe_headache_after_head_impact",
    ),
    (r"\bseizure(?:s)?\b|\bconvulsion(?:s)?\b", "seizure_or_convulsion"),
    (r"\bamnesi(?:a|c)\b|\bmemory\s+loss\b", "amnesia_or_memory_loss"),
    (r"\bblurred\s+vision\b|\bdouble\s+vision\b|\bdiplopia\b", "blurred_or_double_vision"),
    (r"\bunequal\s+pupil(?:s)?\b|\bone\s+pupil\s+(?:larger|bigger)\b", "unequal_pupils"),
    (
        r"\bworsening\s+drows(?:y|iness)\b"
        r"|\bcannot\s+wake\b"
        r"|\bcan(?:not|'t)\s+wake(?:\s+up)?\b"
        r"|\bhard\s+to\s+wake\b",
        "worsening_drowsiness_or_cannot_wake",
    ),
    (r"\bslurred\s+speech\b", "slurred_speech"),
    (
        r"\bneck\s+pain\b[\w\s-]{0,40}\b(?:after|from)\s+(?:trauma|fall|impact|collision|hit)\b"
        r"|\b(?:trauma|fall|impact|collision|hit)\b[\w\s-]{0,40}\bneck\s+pain\b",
        "neck_pain_after_trauma",
    ),
    (
        r"\b(?:bowel|bladder)\s+(?:changes?|issues?|dysfunction|incontinence)\b[\w\s-]{0,40}\b(?:back|spine|spinal)\b"
        r"|\b(?:back|spine|spinal)\b[\w\s-]{0,40}\b(?:bowel|bladder)\s+(?:changes?|issues?|dysfunction|incontinence)\b",
        "bowel_or_bladder_changes_after_back_injury",
    ),
)

_HIGH_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bopen\s+fracture\b", "open_fracture"),
    (r"\bstress\s+fracture\b", "stress_fracture"),
    (r"\brib\s+fracture\b|\bbroken\s+rib\b", "broken_rib"),
    (
        r"\bfracture\b"
        r"|\b(?:broke|broken)\s+(?:my\s+)?(?:bone|ankle|leg|arm|rib|wrist|hand|foot|jaw|nose|finger|toe)\b",
        "fracture",
    ),
    (r"\bdislocat(?:ion|e|ed|es|ing)\b|\bsublux(?:ation|ing|ed)?\b|\bpartial\s+dislocation\b", "dislocation"),
    (r"\bsuspected\s+concussion\b", "suspected_concussion"),
    (r"\bconcussion\b", "concussion"),
    (
        rf"\bachilles\b[\w\s-]{{0,30}}\b(?:{_RUPTURE_OR_TEAR_PATTERN}|avulsion)\b"
        rf"|\b(?:{_RUPTURE_OR_TEAR_PATTERN}|avulsion)\b[\w\s-]{{0,30}}\bachilles\b",
        "achilles_rupture",
    ),
    (rf"\bfull[-\s]?thickness\s+rotator\s+cuff\s+{_TEAR_SYNONYM_PATTERN}\b", "full_thickness_rotator_cuff_tear"),
    (
        rf"\btendon\s+(?:{_RUPTURE_OR_TEAR_PATTERN}|avulsion|pop|snap|failure)\b"
        rf"|\b(?:{_RUPTURE_OR_TEAR_PATTERN}|avulsion|pop|snap|failure)\s+tendon\b",
        "tendon_rupture_or_avulsion",
    ),
    (
        rf"\bcomplete\s+ligament\s+{_TEAR_SYNONYM_PATTERN}\b"
        rf"|\bligament\s+{_TEAR_SYNONYM_PATTERN}\s+complete\b"
        r"|\b(?:ruptured|torn|blown)\s+ligament\b"
        rf"|\bgrade\s*(?:3|iii)\b[\w\s-]{{0,20}}\b(?:ligament|mcl|lcl|acl|pcl|ucl)\b[\w\s-]{{0,20}}\b(?:{_RUPTURE_OR_TEAR_PATTERN}|sprain|injury)?\b"
        r"|\b(?:ligament|mcl|lcl|acl|pcl|ucl)\b[\w\s-]{0,20}\bgrade\s*(?:3|iii)\b",
        "complete_ligament_tear",
    ),
    (r"\bacl\b", "acl_mention"),
    (
        rf"\bacl\b[\w\s-]{{0,30}}\b(?:{_RUPTURE_OR_TEAR_PATTERN}|reconstruction|injury|surgery)\b"
        rf"|\b(?:{_RUPTURE_OR_TEAR_PATTERN}|injury)\b[\w\s-]{{0,30}}\bacl\b",
        "acl_tear",
    ),
    (
        rf"\bpcl\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b"
        rf"|\b{_RUPTURE_OR_TEAR_PATTERN}\b[\w\s-]{{0,30}}\bpcl\b",
        "pcl_tear",
    ),
    (
        rf"\bmcl\b[\w\s-]{{0,30}}\b(?:grade\s*(?:3|iii)|complete)\b[\w\s-]{{0,20}}\b{_RUPTURE_OR_TEAR_PATTERN}\b"
        rf"|\b(?:grade\s*(?:3|iii)|complete)\s+mcl\s+{_TEAR_SYNONYM_PATTERN}\b",
        "mcl_grade3_tear",
    ),
    (
        rf"\blcl\b[\w\s-]{{0,30}}\b(?:grade\s*(?:3|iii)|complete)\b[\w\s-]{{0,20}}\b{_RUPTURE_OR_TEAR_PATTERN}\b"
        rf"|\b(?:grade\s*(?:3|iii)|complete)\s+lcl\s+{_TEAR_SYNONYM_PATTERN}\b",
        "lcl_grade3_tear",
    ),
    (
        rf"\bbucket[\s-]?handle\s+{_TEAR_SYNONYM_PATTERN}\b[\w\s-]{{0,20}}\bmeniscus\b"
        rf"|\bmeniscus\b[\w\s-]{{0,30}}\bbucket[\s-]?handle\s+{_TEAR_SYNONYM_PATTERN}\b",
        "meniscus_bucket_handle_tear",
    ),
    (
        rf"\bpatellar\s+tendon\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b"
        r"|\bjumper'?s\s+knee\s+rupture\b",
        "patellar_tendon_rupture",
    ),
    (rf"\bquadriceps\s+tendon\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b", "quadriceps_tendon_rupture"),
    (
        rf"\bdistal\s+biceps\s+tendon\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b"
        r"|\bdistal\s+biceps\s+rupture\b",
        "distal_biceps_tendon_rupture",
    ),
    (
        rf"\btriceps\s+tendon\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b"
        r"|\btriceps\s+rupture\b",
        "triceps_tendon_rupture",
    ),
    (rf"\bpec(?:toralis)?\s+major\b[\w\s-]{{0,30}}\b{_RUPTURE_OR_TEAR_PATTERN}\b", "pec_major_tear"),
    (r"\bpatellar\s+dislocation\b|\bdislocated\s+patella\b", "patellar_dislocation"),
    (
        r"\brecurrent\s+shoulder\s+dislocation\b"
        r"|\bshoulder\s+dislocat(?:ion|ed)\b[\w\s-]{0,20}\brecurrent\b",
        "recurrent_shoulder_dislocation",
    ),
    (
        rf"\blabral\s+{_TEAR_SYNONYM_PATTERN}\b[\w\s-]{{0,40}}\binstability\b"
        rf"|\binstability\b[\w\s-]{{0,40}}\blabral\s+{_TEAR_SYNONYM_PATTERN}\b",
        "labral_tear_with_instability",
    ),
    (rf"\bhip\s+labral\s+{_TEAR_SYNONYM_PATTERN}\b", "hip_labral_tear"),
    (
        r"\bsyndesmotic\s+high\s+ankle\s+sprain\b"
        r"|\bhigh\s+ankle\s+sprain\b[\w\s-]{0,20}\b(?:grade\s*(?:3|iii)|severe)\b",
        "syndesmotic_high_ankle_sprain_severe",
    ),
    (r"\blisfranc\s+(?:injury|fracture|sprain)\b", "lisfranc_injury"),
    (r"\btibial\s+plateau\s+fracture\b", "tibial_plateau_fracture"),
    (r"\bscaphoid\s+fracture\b", "scaphoid_fracture"),
    (r"\bspinal\s+fracture\b|\bvertebral\s+fracture\b", "spinal_fracture"),
    (r"\borbital\s+fracture\b", "orbital_fracture"),
    (r"\bjaw\s+fracture\b|\bmandib(?:le|ular)\s+fracture\b", "jaw_fracture"),
    (r"\bfacial\s+fracture\b|\bzygoma(?:tic)?\s+fracture\b|\bmaxillary\s+fracture\b", "facial_fracture"),
    (r"\bretinal\s+detach(?:ment|ed)\b|\beye\s+trauma\b|\bocular\s+trauma\b", "retinal_detachment_or_eye_trauma"),
    (r"\bpneumothorax\b|\bcollapsed\s+lung\b", "pneumothorax"),
    (r"\bhemothorax\b|\bhaemothorax\b", "hemothorax"),
    (r"\b(?:spleen|splenic|liver|hepatic)\s+(?:injury|laceration|rupture)\b", "spleen_or_liver_injury"),
    (r"\bcervical\s+spine\s+injury\b|\bc[-\s]?spine\s+injury\b|\bneck\s+fracture\b", "cervical_spine_injury"),
    (
        r"\bpost[-\s]?op\b[\w\s-]{0,40}\b(?:acl|pcl|mcl|lcl|labral|meniscus|reconstruction)\b"
        r"|\brecent\s+reconstruction\b",
        "post_op_reconstruction_active",
    ),
    (
        r"\bpost[-\s]?op\b[\w\s-]{0,40}\b(?:tendon|repair)\b"
        r"|\brecent\s+tendon\s+repair\b",
        "post_op_tendon_repair_active",
    ),
    (
        r"\bpost[-\s]?op\b[\w\s-]{0,40}\b(?:orif|fixation|fracture\s+repair)\b"
        r"|\brecent\s+fracture\s+fixation\b",
        "post_op_fracture_fixation_active",
    ),
    (r"\bseptic\s+(?:joint|arthritis|bursitis|bone)\b|\bosteomyelitis\b", "septic_joint_or_bone_infection"),
)

_STRUCTURAL_SEVERE_TERMS = (
    "tear",
    "torn",
    "rupture",
    "full thickness",
    "full-thickness",
    "grade 3",
    "grade iii",
    "reconstruction",
    "post-op",
    "post op",
    "postoperative",
    "snapped",
    "complete",
    "avulsion",
)

_STRUCTURAL_TISSUE_TERMS = (
    "ligament",
    "tendon",
    "acl",
    "pcl",
    "mcl",
    "lcl",
    "meniscus",
    "labrum",
    "rotator cuff",
    "achilles",
    "hamstring",
    "patellar tendon",
    "bicep tendon",
    "quadriceps tendon",
    "triceps tendon",
    "pec major",
    "lisfranc",
    "syndesmotic",
)

_NEGATED_SEVERE_PATTERNS = (
    rf"\b(?:no|not|without|denies?|denied)\s+(?:an?\s+)?(?:fracture|stress\s+fracture|dislocation|concussion|acl\s+{_TEAR_SYNONYM_PATTERN}|pcl\s+{_TEAR_SYNONYM_PATTERN}|{_TEAR_SYNONYM_PATTERN}|{_RUPTURE_OR_TEAR_PATTERN}|pneumothorax|hemothorax|vomit(?:ing)?)\b",
    # 'not broken'/'no broken' is the lay equivalent of 'no fracture' for the
    # body parts the structural regex (line ~188) treats as fracture indicators.
    r"\b(?:no|not|without|denies?|denied|did\s+not)\s+(?:\w+\s+){0,3}(?:broke|broken)\b",
    rf"\bruled\s+out\s+(?:an?\s+)?(?:fracture|dislocation|concussion|{_TEAR_SYNONYM_PATTERN}|{_RUPTURE_OR_TEAR_PATTERN}|pneumothorax|hemothorax)\b",
    # 'ruled out broken X' / 'scan ruled out fracture' / 'thought i broke it'
    r"\bruled\s+out\s+(?:\w+\s+){0,3}(?:broke|broken|fracture)\b",
    r"\b(?:acl|pcl)\s+intact\b",
    r"\bno\s+fracture\s+seen\b",
)

_ACL_HISTORY_TERMS = (
    "history of",
    "hx of",
    "old acl",
    "prior acl",
    "previous acl",
    "post acl",
    "status post acl",
    "s/p acl",
    "acl rehab history",
    "now cleared",
    "cleared",
)

_ACL_CURRENT_CONCERN_TERMS = (
    "reinjur",
    "new injury",
    "fresh",
    "acute",
    "swelling",
    "instability",
    "giving way",
    "buckl",
    "popped",
    "pop",
    "pain",
)

_HISTORY_TERMS = (
    "history of",
    "hx of",
    "old",
    "prior",
    "previous",
    "years ago",
    "status post",
    "s/p",
    "rehab history",
    "now cleared",
    "cleared",
    "healed",
    "resolved",
    "fully recovered",
    "recovered",
    "past injury",
)

_CURRENT_CONCERN_TERMS = (
    "reinjur",
    "new injury",
    "fresh",
    "acute",
    "current",
    "currently",
    "today",
    "ongoing",
    "worse",
    "worsening",
    "swelling",
    "instability",
    "giving way",
    "buckl",
    "popped",
    "pop",
    "pain",
    "cannot",
    "unable",
)

_HISTORY_SUPPRESSIBLE_LABELS = {
    "acl_tear",
    "complete_ligament_tear",
    "tendon_rupture_or_avulsion",
    "dislocation",
}

_STRUCTURED_HIGH_RISK_INJURY_TYPES = {
    "fracture",
    "dislocation",
    "post_surgery",
    "tendon_rupture_or_avulsion",
    "complete_ligament_tear",
    "patellar_tendon_rupture",
    "achilles_rupture",
    "quadriceps_tendon_rupture",
    "distal_biceps_tendon_rupture",
    "triceps_tendon_rupture",
    "pec_major_tear",
    "acl_tear",
    "pcl_tear",
    "mcl_grade3_tear",
    "lcl_grade3_tear",
    "meniscus_bucket_handle_tear",
    "labral_tear_with_instability",
    "concussion",
    "suspected_concussion",
    "open_fracture",
    "spinal_fracture",
    "orbital_fracture",
    "facial_fracture",
    "retinal_detachment_or_eye_trauma",
    "pneumothorax",
    "hemothorax",
    "spleen_or_liver_injury",
    "cervical_spine_injury",
    "septic_joint_or_bone_infection",
}

_URGENT_STRUCTURED_INJURY_TYPES = {
    "concussion",
    "suspected_concussion",
    "open_fracture",
    "spinal_fracture",
    "orbital_fracture",
    "facial_fracture",
    "retinal_detachment_or_eye_trauma",
    "pneumothorax",
    "hemothorax",
    "spleen_or_liver_injury",
    "cervical_spine_injury",
    "septic_joint_or_bone_infection",
}

_STRUCTURAL_HIGH_RISK_INJURY_TYPES = {
    "tendon_rupture_or_avulsion",
    "complete_ligament_tear",
    "patellar_tendon_rupture",
    "achilles_rupture",
    "quadriceps_tendon_rupture",
    "distal_biceps_tendon_rupture",
    "triceps_tendon_rupture",
    "pec_major_tear",
    "acl_tear",
    "pcl_tear",
    "mcl_grade3_tear",
    "lcl_grade3_tear",
    "meniscus_bucket_handle_tear",
    "labral_tear_with_instability",
    "post_surgery",
}

_FUNCTION_LOSS_PATTERNS: tuple[tuple[str, str], ...] = (
    (_CANNOT_BEAR_WEIGHT, "cannot_bear_weight"),
    (rf"\b{_CANNOT_OR_UNABLE}\s+lift\s+(?:my\s+)?arm\b", "cannot_lift_arm"),
    (r"\bgiving\s+way\b|\bbuckled\b", "instability_event"),
    (rf"\b{_CANNOT_OR_UNABLE}\s+(?:fully\s+)?straighten\s+(?:my\s+)?knee\b", "cannot_straighten_knee"),
    (rf"\b{_CANNOT_OR_UNABLE}\s+(?:raise|lift)\s+(?:my\s+)?arm\b", "cannot_raise_arm"),
    (rf"\b{_CANNOT_OR_UNABLE}\s+push\s+off\s+(?:my\s+)?foot\b", "cannot_push_off_foot"),
    (rf"\b{_CANNOT_OR_UNABLE}\s+(?:grip|hold)\b", "cannot_grip_or_hold"),
    (r"\blocked\s+knee\b|\bknee\s+is\s+locked\b", "locked_knee"),
    (r"\bjoint\s+gives\s+way\b|\bgives\s+way\s+repeatedly\b|\brecurrent\s+giving\s+way\b", "joint_gives_way_repeatedly"),
)

_CLINICIAN_RESTRICTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bavoid\s+(?:contact|spar|impact|loaded|weight\s*bearing)\b", "avoid_high_load"),
    (r"\bno\s+spar(?:ring)?\b", "no_sparring"),
    (r"\bpost[-\s]?op\b|\breconstruction\b|\bsurgery\b", "post_op_or_reconstruction"),
    (r"\bnon[-\s]?weight\s*bearing\b|\bnwb\b", "non_weight_bearing"),
    (r"\bin\s+(?:a\s+)?(?:walking\s+)?(?:boot|cast)\b|\bwearing\s+(?:a\s+)?(?:boot|cast)\b", "in_a_boot_or_cast"),
    (r"\bon\s+crutches\b|\busing\s+crutches\b", "on_crutches"),
    (
        r"\b(?:doctor|dr\.?|physio|physical\s+therap(?:ist|y))\b[\w\s-]{0,40}\b(?:no\s+contact|no\s+spar(?:ring)?)\b",
        "doctor_or_physio_said_no_contact_or_no_sparring",
    ),
)


def _guided_injury_text_chunks(
    guided: GuidedInjury | None, *, include_diagnosis_fields: bool = True
) -> list[str]:
    if guided is None:
        return []

    chunks = [
        # When a parsed injury supersedes the guided card (diagnosis fields
        # excluded), the resolved injury owns the location, so the raw guided
        # area must not drive red flags on its own (e.g. an area of "chest pain"
        # must not raise the chest_pain emergency once resolved to benign pain).
        str(guided.area or "").strip() if include_diagnosis_fields else "",
        str(guided.severity or "").strip(),
        str(guided.trend or "").strip(),
        str(guided.avoid or "").strip(),
        str(guided.notes or "").strip(),
    ]

    if include_diagnosis_fields and guided.injury_type:
        chunks.append(f"injury_type:{guided.injury_type}")
    if include_diagnosis_fields and guided.surface_type:
        chunks.append(f"surface_type:{guided.surface_type}")
    if guided.timeframe:
        chunks.append(f"timeframe:{guided.timeframe}")
    if guided.cleared:
        chunks.append(f"cleared:{guided.cleared}")
    if guided.open_wound:
        chunks.append(f"open_wound:{guided.open_wound}")
    if guided.bleeding_status:
        chunks.append(f"bleeding_status:{guided.bleeding_status}")
    if guided.infection_signs:
        chunks.append(f"infection_signs:{','.join(guided.infection_signs)}")
    if guided.impact_related:
        chunks.append(f"impact_related:{guided.impact_related}")
    if guided.sensitive_area:
        chunks.append(f"sensitive_area:{guided.sensitive_area}")

    return [chunk for chunk in chunks if chunk]


def _guided_injuries_text_chunks(
    guided_injuries: list[GuidedInjury] | None,
    *,
    include_diagnosis_fields: bool = True,
) -> list[str]:
    chunks: list[str] = []
    for guided in guided_injuries or []:
        chunks.extend(
            _guided_injury_text_chunks(
                guided,
                include_diagnosis_fields=include_diagnosis_fields,
            )
        )
    return chunks


def _restriction_text_chunks(restrictions: list[dict[str, Any]]) -> list[str]:
    chunks: list[str] = []
    for item in restrictions or []:
        if not isinstance(item, dict):
            continue

        parts = [
            str(item.get("original_phrase") or "").strip(),
            str(item.get("restriction") or "").replace("_", " ").strip(),
            str(item.get("strength") or "").strip(),
            str(item.get("region") or "").strip(),
        ]
        chunks.extend([part for part in parts if part])

    return chunks


def _injury_text_chunks(injuries: str) -> list[str]:
    text = str(injuries or "").strip()
    if not text:
        return []

    chunks = [chunk.strip() for chunk in split_injury_text(text) if chunk.strip()]
    return list(dict.fromkeys([text, *chunks]))


def _parsed_injury_chunks(parsed_injuries: list[dict[str, Any]] | None) -> list[str]:
    chunks: list[str] = []

    for item in parsed_injuries or []:
        if not isinstance(item, dict):
            continue

        original_phrase = str(item.get("original_phrase") or "").strip()
        if original_phrase:
            chunks.append(original_phrase)

        canonical_location = str(item.get("canonical_location") or item.get("region") or "").strip()
        display_location = str(item.get("display_location") or "").strip()
        injury_type = str(item.get("injury_type") or "").strip()
        severity = str(item.get("severity") or "").strip()
        trend = str(item.get("trend") or "").strip()
        avoid = str(item.get("avoid") or "").strip()
        notes = str(item.get("notes") or "").strip()

        # Join location and type with a sentence break so this structured
        # re-serialization cannot masquerade as a free-text emergency phrase
        # (e.g. location "chest" + type "pain" must not read as "chest pain").
        # Individual words are still scanned for danger terms.
        normalized = ". ".join(part for part in (canonical_location, injury_type) if part)
        if normalized:
            chunks.append(normalized)

        contextual = " ".join(
            part for part in (display_location, severity, trend, avoid, notes) if part
        ).strip()
        if contextual:
            chunks.append(contextual)

    return chunks


def _collect_matches(
    text: str,
    patterns: tuple[tuple[str, str], ...],
    *,
    raw_text: str | None = None,
    respect_negation: bool = False,
) -> set[str]:
    lowered = str(text or "").lower()
    raw = raw_text if raw_text is not None else text

    matches: set[str] = set()
    for pattern, label in patterns:
        if not re.search(pattern, lowered):
            continue
        if respect_negation and _label_is_negated(raw, label):
            continue
        matches.add(label)

    return matches


def parse_guided_note_tags(text: str) -> dict[str, set[str]]:
    parsed: dict[str, set[str]] = {}
    if not text:
        return parsed

    for match in re.finditer(r"\[\s*([a-z0-9_]+)\s*:\s*([^\]]*)\]", text.lower()):
        category = (match.group(1) or "").strip()
        if not category:
            continue

        category_tokens = parsed.setdefault(category, set())
        tokens_text = (match.group(2) or "").strip()
        if not tokens_text:
            continue

        for token in tokens_text.split(","):
            normalized = token.strip()
            if normalized:
                category_tokens.add(normalized)

    return parsed


def _contains_any_term(text: str, terms: tuple[str, ...]) -> bool:
    if not terms:
        return False

    pattern = rf"(?<!\w)(?:{'|'.join(re.escape(t) for t in terms)})(?!\w)"
    return bool(re.search(pattern, text))


def _is_structural_severe_signal(*, text: str, scored_injury_type: str) -> bool:
    lowered = str(text or "").lower()
    injury_type = str(scored_injury_type or "").lower()

    has_severe_term = any(term in lowered for term in _STRUCTURAL_SEVERE_TERMS)
    if not has_severe_term:
        return False

    if injury_type in {"sprain", "strain", "instability"}:
        return True

    return any(term in lowered for term in _STRUCTURAL_TISSUE_TERMS)


def _is_negated_severe_chunk(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(re.search(pattern, lowered) for pattern in _NEGATED_SEVERE_PATTERNS)


def _is_acl_history_only_chunk(text: str) -> bool:
    lowered = str(text or "").lower()
    if "acl" not in lowered:
        return False

    has_history = _contains_any_term(lowered, _ACL_HISTORY_TERMS)
    has_current_concern = _contains_any_term(lowered, _ACL_CURRENT_CONCERN_TERMS)
    return has_history and not has_current_concern


def _is_history_only_chunk(text: str) -> bool:
    lowered = str(text or "").lower()
    has_history = _contains_any_term(lowered, _HISTORY_TERMS)
    has_current_concern = _contains_any_term(lowered, _CURRENT_CONCERN_TERMS)
    return has_history and not has_current_concern


def _has_resolved_parsed_injuries(parsed_injuries: list[dict[str, Any]] | None) -> bool:
    return any(
        isinstance(item, dict) and str(item.get("injury_type") or "").strip()
        for item in parsed_injuries or []
    )


def _apply_structured_parsed_injury_signals(
    parsed_injuries: list[dict[str, Any]] | None,
    *,
    high_risk_diagnoses: set[str],
    structural_severe_signals: set[str],
    urgent_flags: set[str],
    high_risk_evidence: set[str],
    structural_evidence: set[str],
    urgent_evidence: set[str],
) -> None:
    for item in parsed_injuries or []:
        if not isinstance(item, dict):
            continue

        resolved_injury_type = str(item.get("injury_type") or "").strip().lower()
        if not resolved_injury_type:
            continue

        if resolved_injury_type not in _STRUCTURED_HIGH_RISK_INJURY_TYPES:
            continue

        evidence = str(item)

        high_risk_diagnoses.add(resolved_injury_type)
        high_risk_evidence.add(evidence)

        if resolved_injury_type in _URGENT_STRUCTURED_INJURY_TYPES:
            urgent_flags.add(f"structured_{resolved_injury_type}")
            urgent_evidence.add(evidence)

        if resolved_injury_type in _STRUCTURAL_HIGH_RISK_INJURY_TYPES:
            structural_severe_signals.add("structured_high_risk_injury_type")
            structural_evidence.add(evidence)


def build_triage_features(
    *,
    injuries: str,
    parsed_injuries: list[dict[str, Any]] | None,
    guided_injury: GuidedInjury | None = None,
    guided_injuries: list[GuidedInjury] | None = None,
    restrictions: list[dict[str, Any]] | None,
) -> TriageFeatures:
    raw_chunks: list[str] = []
    raw_chunks.extend(_injury_text_chunks(injuries))
    raw_chunks.extend(_parsed_injury_chunks(parsed_injuries))

    has_resolved_parsed_injuries = _has_resolved_parsed_injuries(parsed_injuries)
    effective_guided_injuries = (
        guided_injuries
        if guided_injuries is not None
        else ([guided_injury] if guided_injury is not None else [])
    )
    raw_chunks.extend(
        _guided_injuries_text_chunks(
            effective_guided_injuries,
            include_diagnosis_fields=not has_resolved_parsed_injuries,
        )
    )
    raw_chunks.extend(_restriction_text_chunks(restrictions or []))
    raw_chunks = list(dict.fromkeys(chunk for chunk in raw_chunks if chunk))

    cleaned_chunks: list[str] = []

    high_risk_diagnoses: set[str] = set()
    red_flags: set[str] = set()
    structural_severe_signals: set[str] = set()
    function_loss_signals: set[str] = set()
    clinician_restriction_signals: set[str] = set()
    urgent_flags: set[str] = set()

    high_risk_evidence: set[str] = set()
    red_flag_evidence: set[str] = set()
    structural_evidence: set[str] = set()
    function_loss_evidence: set[str] = set()
    clinician_evidence: set[str] = set()
    urgent_evidence: set[str] = set()

    _apply_structured_parsed_injury_signals(
        parsed_injuries,
        high_risk_diagnoses=high_risk_diagnoses,
        structural_severe_signals=structural_severe_signals,
        urgent_flags=urgent_flags,
        high_risk_evidence=high_risk_evidence,
        structural_evidence=structural_evidence,
        urgent_evidence=urgent_evidence,
    )

    for raw_chunk in raw_chunks:
        cleaned_chunk = remove_negated_phrases(raw_chunk).strip().lower()
        if not cleaned_chunk:
            continue

        parsed_type, parsed_location = parse_injury_phrase(cleaned_chunk)
        # Break location/type so the re-serialized canonical form cannot form a
        # free-text emergency phrase (e.g. "chest" + "pain" must not read as the
        # "chest pain" cardiac red flag); danger terms are still scanned per word.
        canonical_chunk = ". ".join(
            piece
            for piece in (
                str(parsed_location or "").strip(),
                str(parsed_type or "").strip(),
            )
            if piece
        ).strip()
        enriched_chunk = " ".join(piece for piece in (cleaned_chunk, canonical_chunk) if piece)

        cleaned_chunks.append(cleaned_chunk)
        history_only_chunk = _is_history_only_chunk(cleaned_chunk)

        danger_routes = detect_danger_term_routes(cleaned_chunk)
        for route in danger_routes:
            category = str(route.get("category") or "").strip()
            route_mode = str(route.get("route") or "").strip()
            term = str(route.get("term") or "").strip()
            if category == "dislocation":
                high_risk_diagnoses.add("dislocation")
                high_risk_evidence.add(raw_chunk)
            elif category == "functional_red_flag":
                function_loss_signals.add("danger_term_function_loss")
                function_loss_evidence.add(raw_chunk)
            elif category in {"instability_event", "structural_event"} and route_mode == "restricted_rehab_only":
                clinician_restriction_signals.add(f"danger_term:{category}")
                clinician_evidence.add(raw_chunk)
            if term:
                structural_severe_signals.add(f"danger_term:{term}")
                structural_evidence.add(raw_chunk)

        chunk_red_flags = _collect_matches(
            enriched_chunk,
            _RED_FLAG_PATTERNS,
            raw_text=raw_chunk,
            respect_negation=True,
        )
        if chunk_red_flags:
            red_flags.update(chunk_red_flags)
            red_flag_evidence.add(raw_chunk)

        chunk_function_loss = _collect_matches(
            enriched_chunk,
            _FUNCTION_LOSS_PATTERNS,
            raw_text=raw_chunk,
            respect_negation=True,
        )
        if chunk_function_loss:
            function_loss_signals.update(chunk_function_loss)
            function_loss_evidence.add(raw_chunk)

        chunk_clinician_signals: set[str] = set()
        if not history_only_chunk:
            chunk_clinician_signals = _collect_matches(
                enriched_chunk,
                _CLINICIAN_RESTRICTION_PATTERNS,
            )
        if chunk_clinician_signals:
            clinician_restriction_signals.update(chunk_clinician_signals)
            clinician_evidence.add(raw_chunk)

        if _is_negated_severe_chunk(raw_chunk):
            continue

        chunk_high_risk = _collect_matches(enriched_chunk, _HIGH_RISK_PATTERNS)

        if "acl_mention" in chunk_high_risk:
            chunk_high_risk.discard("acl_mention")
            if not _is_acl_history_only_chunk(cleaned_chunk):
                chunk_high_risk.add("acl_tear")

        if "acl_tear" in chunk_high_risk and _is_acl_history_only_chunk(cleaned_chunk):
            chunk_high_risk.discard("acl_tear")

        if history_only_chunk:
            chunk_high_risk.difference_update(_HISTORY_SUPPRESSIBLE_LABELS)

        if chunk_high_risk:
            high_risk_diagnoses.update(chunk_high_risk)
            high_risk_evidence.add(raw_chunk)

        if history_only_chunk:
            continue

        scored = score_injury_phrase(cleaned_chunk)
        scored_type = str(scored.get("injury_type") or "")

        if _is_structural_severe_signal(text=cleaned_chunk, scored_injury_type=scored_type):
            structural_severe_signals.add("structural_severe_signal")
            structural_evidence.add(raw_chunk)

        for flag in scored.get("flags", []):
            if str(flag).startswith("urgent"):
                urgent_flags.add(str(flag))
                urgent_evidence.add(raw_chunk)

    return TriageFeatures(
        high_risk_diagnoses=sorted(high_risk_diagnoses),
        red_flags=sorted(red_flags),
        structural_severe_signals=sorted(structural_severe_signals),
        function_loss_signals=sorted(function_loss_signals),
        clinician_restriction_signals=sorted(clinician_restriction_signals),
        urgent_flags=sorted(urgent_flags),
        raw_evidence={
            "all_input": sorted(set(raw_chunks)),
            "cleaned_input": sorted(set(cleaned_chunks)),
            "high_risk_diagnoses": sorted(high_risk_evidence),
            "red_flags": sorted(red_flag_evidence),
            "structural_severe_signals": sorted(structural_evidence),
            "function_loss_signals": sorted(function_loss_evidence),
            "clinician_restriction_signals": sorted(clinician_evidence),
            "urgent_flags": sorted(urgent_evidence),
            "structured_parsed_injury": sorted(
                {str(item) for item in parsed_injuries or [] if isinstance(item, dict)}
            ),
        },
    )
