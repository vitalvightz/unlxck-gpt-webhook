"""Bank-backed contusion baselines within the existing family/profile catalog."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fightcamp.injury_location_registry import canonicalize_location_from_registry  # noqa: E402
from fightcamp.rehab_clinical import compose_policy, content_hash, load_pathway_catalog, policy_review_hash  # noqa: E402
from tools.seed_tendon_family import mark_reviewed  # noqa: E402

MUSCLE = "https://www.orthoinfo.org/diseases--conditions/muscle-contusion-bruise/"
MINOR = "https://yourhealth.leicestershospitals.nhs.uk/library/emergency-specialist-medicine/emergency-department/1660-care-after-minor-sprains-strains-or-bruises-soft-tissue-injuries/file"
HEEL = "https://my.clevelandclinic.org/health/diseases/23275-heel-fat-pad-syndrome"
HEEL_DIFFERENTIAL = "https://my.clevelandclinic.org/health/diseases/heel-pain"
SHOULDER = "https://www.leedsth.nhs.uk/patients/resources/early-advice-and-exercises-for-soft-tissue-injuries-of-the-shoulder/"
ELBOW = "https://www.nbt.nhs.uk/our-services/a-z-services/emergency-department/ed-miu-patient-information/elbow-injuries"
WRIST = "https://www.leedsth.nhs.uk/patients/resources/the-hand-and-wrist/"
HAND = "https://www.royalberkshire.nhs.uk/media/opzgt14c/bruised-hand_dec25.pdf"

# No universal contusion exercise protocol. Muscle-specific examination and
# rehabilitation remain clinical decisions; only regional supported baselines
# below are activated. Generic symptoms do not resolve these exact profiles.
PROFILES = {
    "heel": dict(sources=[HEEL, HEEL_DIFFERENTIAL, MINOR], tissue="heel soft tissue region",
        calm="Protect the bruised heel from repeated hard landings, running and direct pressure. Rest the foot comfortably supported and reduce provoking standing or walking. Follow any clinician-advised footwear, heel support or weight-bearing restriction. Do not tap or roll the bruised heel to desensitize it, start barefoot loading or assume that heel tenderness rules out a bone injury. The app does not distinguish heel-pad from deeper heel injury, so automatic exercises remain unavailable."),
    "shin": dict(sources=[MINOR, MUSCLE], tissue="shin soft tissue region",
        calm="Protect the bruised shin from kicks, pad contact and kneeling pressure. Rest the leg comfortably supported and reduce provoking prolonged standing or walking. Follow any clinician-prescribed support or weight-bearing restriction. Do not use sticks, percussion devices or rollers over the bruise, or test contact tolerance. The exact depth of the impact injury is not established, so direct shin loading and automatic exercises remain unavailable."),
    "quads": dict(sources=[MUSCLE, MINOR], tissue="quadriceps muscle region",
        calm="Protect the bruised thigh from further blows, deep squatting, kicking and provoking knee loading. Rest the leg comfortably supported and follow any clinician-prescribed position, wrap, walking support or movement restriction. Do not massage, use a percussion gun, force a thigh stretch or deepen a wall sit. Do not set or remove a bent-knee brace yourself; the extent of the contusion and safe knee movement need individual assessment."),
    "biceps": dict(sources=[MUSCLE, MINOR], tissue="biceps muscle region",
        calm="Protect the bruised front of the upper arm from contact, heavy pulling and repeated resisted elbow bending. Support the arm comfortably at rest and follow individual movement/support restrictions. Avoid direct massage or percussion, forceful stretching and faster arm swings to test tolerance. A muscle bruise label does not exclude deeper muscle or tendon injury; automatic resistance or stretching is not prescribed."),
    "triceps": dict(sources=[MUSCLE, MINOR], tissue="triceps muscle region",
        calm="Protect the bruised back of the upper arm from contact, heavy pressing and resisted elbow straightening. Support the arm comfortably at rest and follow individual movement/support restrictions. Do not apply vibration balls, force an overhead stretch or increase arm-circle range to test recovery. Automatic stretching or resistance work needs an assessed injury and is not prescribed here."),
    "forearm": dict(sources=[MUSCLE, MINOR], tissue="forearm muscle region",
        calm="Protect the bruised forearm from contact, heavy grip work and resisted wrist movement. Support the arm comfortably without pressing on the bruise and follow any prescribed support or movement restriction. Do not roll a ball over the injured tissue or use a band as a recovery flush. Increasing tight swelling, abnormal sensation or circulation needs assessment rather than further loading."),
    "shoulder": dict(sources=[SHOULDER, MUSCLE, MINOR], tissue="shoulder soft tissue region",
        calm="Protect the bruised shoulder from repeated contact, heavy lifting and provoking reaching. Support the arm comfortably when resting and follow any individual sling or movement restriction. Do not press a ball or percussion device into the bruise, hang from a trap bar or add band resistance. This protection guidance does not establish structural healing or readiness for contact.",
        restore_id="shoulder_contusion_passive_arm_hang_trap_bar_support",
        name="Supported unweighted shoulder pendulum", equipment=["stable_support"], load="minimal", contraction="unknown",
        restore="Stand beside a stable support and lean slightly forwards with the uninjured hand supporting you. Let the affected arm hang relaxed, then gently allow a small slow forward-and-back pendulum movement within a comfortable range. Keep the hand empty; do not hang from a bar, pull the shoulder, swing forcefully, add weight or force range. Follow any clinician movement restriction and stop if this provokes the bruised shoulder."),
    "elbow": dict(sources=[ELBOW, MUSCLE, MINOR], tissue="elbow soft tissue region",
        calm="Protect the bruised elbow from contact, leaning on the injured area, heavy carrying and forceful pressing. Support the arm comfortably without pressure on the bruise and follow any individual sling or movement restriction. Do not apply a massage gun or push the elbow against a wall to build contact tolerance.",
        restore_id="elbow_contusion_gentle_elbow_slides_on_wall",
        name="Comfortable unloaded elbow movement", equipment=[], load="minimal", contraction="mixed",
        restore="Sit with the upper arm relaxed by your side and the hand empty. Slowly bend and straighten the affected elbow through a small comfortable range, stopping short of pain. Do not press on a wall, lean on the bruise, force straightening or add resistance. Follow any clinician movement restriction; this is movement only, not pushing or contact preparation."),
    "wrist": dict(sources=[WRIST, MINOR], tissue="wrist soft tissue region",
        calm="Protect the bruised wrist from contact, heavy grip, pushing through the hand and repeated provoking wrist loading. Rest the forearm and hand comfortably supported and follow prescribed splint or movement restrictions. Do not roll or tap the bruise, add glove impact or remove protection because its colour fades.",
        restore_id="wrist_contusion_wrist_flexion_extension_passes",
        name="Supported unloaded wrist movement", equipment=["table"], load="minimal", contraction="mixed",
        restore="Support the forearm on a table with the hand relaxed and free to move beyond the edge. Slowly move the wrist a small amount upwards and downwards within a comfortable non-provoking range. Keep the hand empty and do not grip, stretch with the other hand, press on the bruise or add resistance. Follow individual splint and movement restrictions."),
    "hand": dict(sources=[HAND, WRIST, MINOR], tissue="hand soft tissue region",
        calm="Protect the bruised hand from heavy gripping, carrying, punching and direct pressure. Rest it comfortably supported and follow any individually prescribed hand protection. Do not use contrast heat, ball pressure or a resisted grip squeeze as automatic treatment. New loss of movement or grip, excessive or increasing swelling, or altered sensation needs assessment.",
        restore_id="hand_contusion_reviewed_restore", name="Unloaded comfortable hand opening and closing",
        equipment=[], load="minimal", contraction="mixed",
        restore="With the forearm comfortably supported without pressure on the bruise, gently open and close the affected hand through a small comfortable range. Keep the hand empty; do not squeeze a ball, clench tightly, push fingers with the other hand or massage the bruised tissue. Stop if movement worsens symptoms and follow individual movement restrictions."),
    "fingers": dict(sources=[HAND, WRIST, MINOR], tissue="finger soft tissue region",
        calm="Protect the bruised fingers from catching impacts, punching, heavy grip and direct pressure. Rest the hand comfortably supported and follow any prescribed finger protection or movement restriction. Do not tap the fingers on a pad, grip a cold ball or roll the injured tissue to test contact tolerance.",
        restore_id="fingers_contusion_reviewed_restore", name="Unloaded comfortable finger movement",
        equipment=[], load="minimal", contraction="mixed",
        restore="Keep the hand relaxed and gently bend and straighten the affected fingers through a small comfortable range. Do not make a forceful fist, pull the fingers with the other hand, tap a pad or grip an object. Follow individual protection and movement restrictions and stop if the movement provokes the bruised fingers."),
}
REPAIRED = {p["restore_id"] for p in PROFILES.values() if p.get("restore_id") and not p["restore_id"].endswith("reviewed_restore")}
STOP = ("Stop if symptoms worsen during or after the activity. Seek assessment for increasing or excessive swelling, "
        "an expanding lump or hematoma, inability to use or bear weight on the limb, or major loss of function. "
        "Seek urgent help for severe pain with tense swelling, compartment syndrome concern, altered sensation, "
        "a cold limb or circulation changes, an open wound, or suspected fracture, dislocation or tear. "
        "Follow clinician restrictions; CALM or RESTORE is not return-to-contact clearance.")


def main():
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))

    bank, ledger, raw = read("rehab_bank.json"), read("rehab_metadata_review.json"), read("rehab_pathways.json")
    indexed = {d["id"]: (g, d) for g in bank for d in g["drills"]}
    reviewed = {r["drill_id"]: r for r in ledger}
    catalog = load_pathway_catalog()
    profiles = []
    for region, config in PROFILES.items():
        groups = [g for g in bank if g["type"] == "contusion" and canonicalize_location_from_registry(g["location"]) == region]
        group = groups[0]
        stages = ["calm", "restore"] if "restore_id" in config else ["calm"]
        for target in groups:
            target["phase_progression"] = "GPP → SPP → TAPER"
        prescriptions = []
        for stage in stages:
            identity = f"{region}_contusion_recovery_support" if stage == "calm" else config["restore_id"]
            target_group, original = indexed.get(identity, (group, group["drills"][0]))
            drill = deepcopy(original)
            text = (config["calm"] if stage == "calm" else config["restore"]) + " " + STOP
            drill.update(id=identity, name=f"{region.title()} contusion protection guidance" if stage == "calm" else config["name"],
                         notes=text, rehab_stage=stage, function="recovery_downregulation" if stage == "calm" else "mobility",
                         equipment=[] if stage == "calm" else config["equipment"], load="minimal" if stage == "calm" else config["load"],
                         impact="none", velocity="low", target_regions=[target_group["location"]], target_tissues=[config["tissue"]],
                         laterality_applicability="not_applicable" if stage == "calm" else "side_specific",
                         contraction_type="unknown" if stage == "calm" else config["contraction"],
                         sport_specificity="general_rehab", contact_level="none", dose=None, pain_ceiling=None,
                         allowed_severities=None, progress_when=None, regress_when=None, stop_when=None,
                         evidence_notes="Sources: " + ", ".join(config["sources"]) + ". Protected regional baseline only; not diagnosis, structural healing or contact clearance. No numeric dose, pain ceiling, hematoma size, severity grade, brace duration or progression threshold inferred. Comfortable/non-provoking movement is a conservative baseline restriction. Product low/moderate eligibility and scheduled cadence are retained. Individual restrictions remain authoritative. No time/session-based progression or automatic massage/heat protocol.")
            for other in bank:
                other["drills"] = [d for d in other["drills"] if d["id"] != identity]
            target_group["drills"].append(drill)
            reviewed[identity] = mark_reviewed(target_group, drill, reviewed.get(identity))
            prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage, instructions=text,
                                      dose=None, allowed_severities=["low", "moderate"], sources=config["sources"], stop_when=[STOP]))
        profile = dict(policy_id=f"{region}_contusion", version=1, region=region, injury_type="contusion",
                       pathway_family="contusion", evidence_sources=config["sources"], prescriptions=prescriptions,
                       blocked_regions=[region], blocked_tags=[], contact_limit="none", live_stages=stages, transition_overrides={})
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
