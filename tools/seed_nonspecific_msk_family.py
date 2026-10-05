"""Exact symptom baselines; inventory review never diagnoses or activates itself."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fightcamp.injury_location_registry import canonicalize_location_from_registry  # noqa: E402
from fightcamp.rehab_clinical import compose_policy, content_hash, load_pathway_catalog, policy_review_hash  # noqa: E402
from tools.seed_tendon_family import mark_reviewed  # noqa: E402

SYMPTOMS = {"pain", "soreness", "tightness", "stiffness", "swelling"}
BASE = "https://www.nhs.uk/symptoms/"
JOINT = BASE + "joint-pain/"
SHOULDER = BASE + "shoulder-pain/"
ELBOW = BASE + "elbow-and-arm-pain/"
WRIST = BASE + "hand-pain/wrist-pain/"
NECK = BASE + "neck-pain-and-stiff-neck/"
BACK = "https://www.nhs.uk/conditions/back-pain/"
FLEX = "https://www.nhs.uk/live-well/exercise/flexibility-exercises/"
CSP = "https://www.csp.org.uk/conditions/back-pain/video-exercises-back-pain"
MOVEMENT = "https://www.uhsussex.nhs.uk/resources/elbow-and-wrist-exercises/"

# Selected exact combinations, not a cartesian product of regions and labels.
PROFILES = {
    "shoulder_pain": ("shoulder", "pain", [SHOULDER], "Reduce provoking shoulder activity and heavy gym work. Keep ordinary gentle movement as symptoms allow; support the arm comfortably when resting."),
    "elbow_pain": ("elbow", "pain", [ELBOW, JOINT], "Reduce clearly provoking elbow activity and avoid forceful self-testing. Keep comfortable ordinary movement; seek assessment for ongoing pain or reduced function."),
    "wrist_pain": ("wrist", "pain", [WRIST], "Reduce provoking wrist tasks, heavy lifting and tight gripping. Rest comfortably between activities while retaining gentle ordinary movement as tolerated."),
    "hand_pain": ("hand", "pain", [BASE + "hand-pain/pain-in-the-palm-of-the-hand/"], "Reduce provoking hand tasks, heavy carrying and tight gripping. Rest the hand comfortably and keep ordinary gentle movement as symptoms allow."),
    "fingers_pain": ("fingers", "pain", [BASE + "hand-pain/finger-pain/"], "Reduce provoking finger tasks and heavy gripping. Avoid forcing movement or testing grip strength; follow individual support advice without prescribing taping here."),
    "knee_pain": ("knee", "pain", [BASE + "knee-pain/"], "Reduce provoking knee weight-bearing and prolonged standing. Avoid loaded self-tests; seek assessment for locking, giving way or difficulty using the leg."),
    "hip_pain": ("hip", "pain", [BASE + "hip-pain/"], "Reduce provoking hip activity and heavy carrying. Keep comfortable ordinary movement without overdoing it; avoid forcing end-range stretches."),
    "lower_back_pain": ("lower back", "pain", [BACK, CSP], "Keep comfortable daily activity and change position as needed. Reduce provoking tasks without prolonged bed rest; no cause of the back pain is inferred."),
    "neck_stiffness": ("neck", "stiffness", [NECK, FLEX], "Change position rather than holding the neck still for long periods. Keep gentle ordinary movement; do not force range or remove prescribed protection."),
    "elbow_stiffness": ("elbow", "stiffness", [ELBOW, JOINT], "Keep comfortable ordinary elbow movement without forceful end-range work. Stiffness alone does not establish a movement restriction or its cause."),
    "wrist_stiffness": ("wrist", "stiffness", [WRIST, MOVEMENT], "Keep gentle ordinary wrist movement and reduce clearly provoking tasks. Do not add resistance or force range merely because the wrist feels stiff."),
    "lower_back_stiffness": ("lower back", "stiffness", [BACK, JOINT], "Change positions and keep comfortable ordinary activity. Avoid prolonged bed rest and forced range; no diagnosis or measured mobility deficit is inferred."),
    "neck_tightness": ("neck", "tightness", [NECK], "Change positions and keep gentle ordinary neck movement. Tightness does not prove shortened tissue; avoid forceful stretching, traction or pressure on the neck."),
    "shoulder_tightness": ("shoulder", "tightness", [SHOULDER], "Reduce clearly provoking shoulder tasks while retaining gentle ordinary movement. Tightness does not prove tissue shortening; avoid forced stretches or heavy self-tests."),
    "neck_soreness": ("neck", "soreness", [NECK], "Adjust provoking activity and avoid staying in one position for long periods. Soreness does not establish DOMS; do not use forceful neck self-testing."),
    "shoulder_soreness": ("shoulder", "soreness", [SHOULDER], "Reduce clearly provoking shoulder activity and heavy gym work. Keep gentle ordinary movement as tolerated. Soreness does not establish DOMS or a specific injury."),
}
RESTORE = {
    "lower_back_pain": dict(identity="lower_back_pain_supine_pelvic_tilts", name="Comfortable supine pelvic tilt", equipment=["mat"],
        text="Lie on your back with knees bent and feet resting on the floor. Gently tilt the pelvis to flatten the lower back slightly, then return slowly to neutral. Keep movement small and comfortable, breathe normally, and do not force an arch or hold tension."),
    "neck_stiffness": dict(identity="neck_stiffness_neck_cars_controlled_articular_rotations", name="Comfortable seated neck rotation", equipment=[],
        text="Sit upright with shoulders relaxed. Slowly turn the head a small comfortable amount to one side, then return to the middle. Use unassisted movement only; no neck circles, forced range, resistance, traction or sustained stretch."),
    "wrist_stiffness": dict(identity="wrist_stiffness_stick_roll_wrist_flex_ext", name="Supported unloaded wrist movement", equipment=["table"],
        text="Support the forearm on a table with the empty relaxed hand free beyond the edge. Gently move the wrist a small comfortable amount upwards and downwards. No stick, grip, weight, resistance, forced stretch or pressure through the hand."),
}
REPAIRED = {r["identity"] for r in RESTORE.values()}
STOP = ("Follow clinician restrictions. Stop if activity makes symptoms worse or causes new symptoms. "
        "Seek assessment for persistent or worsening symptoms or reduced everyday function. Get urgent help for major trauma, "
        "deformity, inability to use or bear weight, marked or increasing swelling, a hot/red joint, fever or feeling unwell, "
        "locking/giving way, altered sensation, progressive weakness or circulation changes. "
        "This guidance does not identify the cause, establish healing or provide contact clearance.")


def main():
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    bank, ledger, raw = read("rehab_bank.json"), read("rehab_metadata_review.json"), read("rehab_pathways.json")
    indexed = {d["id"]: (g, d) for g in bank for d in g["drills"]}
    reviewed = {r["drill_id"]: r for r in ledger}
    catalog = load_pathway_catalog()
    profiles = []
    for policy_id, (region, kind, sources, calm) in PROFILES.items():
        groups = [g for g in bank if g["type"] == kind and canonicalize_location_from_registry(g["location"]) == region]
        assert groups, (region, kind)
        group = groups[0]
        for target in groups:
            target["phase_progression"] = "GPP → SPP → TAPER"
        stages = ["calm", "restore"] if policy_id in RESTORE else ["calm"]
        prescriptions = []
        for stage in stages:
            config = RESTORE.get(policy_id, {})
            identity = f"{policy_id}_recovery_support" if stage == "calm" else config["identity"]
            target_group, original = indexed.get(identity, (group, group["drills"][0]))
            drill = deepcopy(original)
            text = (calm if stage == "calm" else config["text"]) + " " + STOP
            drill.update(id=identity, name=f"{region.title()} {kind} activity guidance" if stage == "calm" else config["name"],
                notes=text, rehab_stage=stage, function="recovery_downregulation" if stage == "calm" else "mobility",
                equipment=[] if stage == "calm" else config["equipment"], load="minimal", impact="none", velocity="low",
                target_regions=[target_group["location"]], target_tissues=[f"{region} region; symptom cause unspecified"],
                laterality_applicability="not_applicable" if stage == "calm" else "side_specific",
                contraction_type="unknown" if stage == "calm" else "mixed", sport_specificity="general_rehab", contact_level="none",
                dose=None, pain_ceiling=None, allowed_severities=None, progress_when=None, regress_when=None, stop_when=None,
                evidence_notes="Sources: " + ", ".join(sources) + ". Exact nonspecific symptom baseline. No diagnosis, tissue mechanism, DOMS, numeric dose, pain ceiling, progression or swelling threshold inferred. Comfortable/non-provoking is a conservative baseline restriction, not a universal pain rule. Product low/moderate eligibility and cadence are retained. Sussex supports movement mechanics only; no injury-specific healing/loading protocol imported.")
            for other in bank:
                other["drills"] = [d for d in other["drills"] if d["id"] != identity]
            target_group["drills"].append(drill)
            reviewed[identity] = mark_reviewed(target_group, drill, reviewed.get(identity))
            prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage, instructions=text,
                dose=None, allowed_severities=["low", "moderate"], sources=sources, stop_when=[STOP]))
        profile = dict(policy_id=policy_id, version=1, region=region, injury_type=kind, pathway_family="nonspecific_msk_symptoms",
            evidence_sources=sources, prescriptions=prescriptions, blocked_regions=[region], blocked_tags=[], contact_limit="none",
            live_stages=stages, transition_overrides={})
        draft = compose_policy(catalog, profile)
        profile.update(status="active", activation="live", content_hash=policy_review_hash(draft),
            prescriptions=[p.model_dump() for p in draft.prescriptions])
        profiles.append(profile)
    replacements = {p["policy_id"]: p for p in profiles}
    raw["profiles"] = [replacements.pop(p["policy_id"], p) for p in raw["profiles"]] + list(replacements.values())
    for name, value in [("rehab_bank.json", bank), ("rehab_pathways.json", raw),
        ("rehab_metadata_review.json", [reviewed[d["id"]] for g in bank for d in g["drills"] if d["id"] in reviewed])]:
        (ROOT / "data" / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
