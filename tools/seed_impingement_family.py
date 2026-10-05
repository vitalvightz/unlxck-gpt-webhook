"""Bank-backed regional impingement baselines in the existing profile catalog."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fightcamp.rehab_clinical import compose_policy, content_hash, load_pathway_catalog, policy_review_hash  # noqa: E402
from tools.seed_tendon_family import mark_reviewed  # noqa: E402

SHOULDER = "https://www.rjah.nhs.uk/our-services/therapy/supported-self-care/rotator-cuff-related-shoulder-pain/"
HIP = "https://leedscommunityhealthcare.nhs.uk/our-services-a-z/musculoskeletal-msk/hip-problems/known-diagnosed-hip-problems/hip-femoroacetabular-impingement-fai/"
HIP_CONSENSUS = "https://pmc.ncbi.nlm.nih.gov/articles/PMC8349584/"
ANTERIOR_ANKLE = "https://msk-bexley.nhs.uk/conditions/foot-and-ankle-pain/anterior-front-ankle-impingement"
POSTERIOR_ANKLE = "https://msk-bexley.nhs.uk/conditions/foot-and-ankle-pain/posterior-back-ankle-impingement"
ELBOW = "https://med.uth.edu/ortho/posterior-impingement-of-the-elbow/"
WRIST = "https://pmc.ncbi.nlm.nih.gov/articles/PMC9036339/"

# Region-specific advice, not a shared impingement protocol or diagnosis rule.
# Original IDs remain stable where a fixed movement can be repaired.
PROFILES = {
    "shoulder": dict(sources=[SHOULDER], tissue="shoulder joint and rotator cuff region",
        calm="Reduce provoking overhead reaching, heavy pressing and movement behind the body. Keep ordinary comfortable activity rather than immobilizing the shoulder routinely. Support the arm comfortably when resting. Follow individual movement restrictions.",
        restore_id="shoulder_impingement_scapular_wall_slides_with_chin_tuck",
        name="Supported comfortable shoulder wall slide", equipment=["wall", "cloth"], load="low",
        restore="Stand facing a smooth wall with a cloth under the affected hand. Gently slide the hand upwards only through a comfortable range no higher than shoulder level, then return. Do not lean body weight heavily into the arm, force a painful arc, add resistance or lift overhead. Keep the neck comfortable; no forced chin tuck or posture correction is required."),
    "hip": dict(sources=[HIP, HIP_CONSENSUS], tissue="hip joint region",
        calm="Reduce provoking deep squats, twisting, crossing the leg into an uncomfortable position and high-impact activity. Pace everyday activities and avoid prolonged positions that reproduce the pinch. Follow individually advised weight-bearing and movement restrictions; do not use band traction to force range.",
        restore_id="hip_impingement_90_90_hip_switches",
        name="Supported small-range hip rotation", equipment=[], load="minimal",
        restore="Lie on your back with the affected knee comfortably bent and the foot resting on the surface. Slowly let the knee move a small amount outwards, then return to the starting position within a pain-free range. Keep the pelvis supported. Do not cross the knee inward, pull it towards the chest, force a deep rotation position or add a band. This replaces the extreme seated hip-switch positions with protected rotation."),
    "ankle": dict(sources=[ANTERIOR_ANKLE, POSTERIOR_ANKLE], tissue="ankle joint region",
        calm="Reduce provoking impact, hill running, deep loaded ankle bending and forceful tiptoe work. Pace ordinary walking and use individually advised supportive footwear. The app does not distinguish front from back ankle impingement, so do not force either end of ankle range or use band traction to clear a pinch.",
        restore_id="ankle_impingement_reviewed_restore",
        name="Supported comfortable ankle movement", equipment=[], load="minimal",
        restore="Sit with the affected lower leg supported and the foot free to move. Slowly move the ankle a small amount upwards and downwards around a comfortable middle range. Do not force pointing the toes, deep upward bending, a loaded knee-over-toe lunge or a stretch into a pinch. Keep the movement unweighted and controlled; follow any clinician-directed movement restriction."),
    "elbow": dict(sources=[ELBOW], tissue="elbow joint region",
        calm="Reduce provoking forceful elbow straightening, repetitive throwing, heavy triceps work and pressing. Rest from activities that reproduce the pinch and follow individual restrictions. Persistent catching, locking or a mechanical block needs assessment rather than repeated attempts to force movement.",
        restore_id="elbow_impingement_elbow_cars",
        name="Supported comfortable elbow movement", equipment=[], load="minimal",
        restore="Sit with the affected upper arm by your side and the forearm comfortably supported. With the hand empty, slowly bend and straighten the elbow through a small comfortable range. Stop short of a pinch and do not force full straightening, rotate against resistance, perform a large end-range CAR or add weight. Stop and seek assessment for catching, locking or a blocked movement."),
    "wrist": dict(sources=[WRIST], tissue="wrist joint region",
        calm="Reduce provoking grip, pushing through the hand, loaded wrist extension and repetitive wrist compression. Rest the wrist in a comfortable supported position and follow clinician-directed splint or immobilization advice without changing it. Do not perform band distraction, push-ups, resisted side-to-side holds or force range to clear a pinch. The subtype and safe release from protection are not captured, so automatic wrist movement and loading remain unavailable."),
}
REPAIRED = {p["restore_id"] for p in PROFILES.values() if p.get("restore_id")
            and p["restore_id"] != "ankle_impingement_reviewed_restore"}
STOP = "Stop if symptoms worsen during or after the movement. Seek assessment for catching, locking, loss of function, altered sensation, a hot swollen joint or fever."


def main():
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))

    bank, ledger, raw = read("rehab_bank.json"), read("rehab_metadata_review.json"), read("rehab_pathways.json")
    indexed = {d["id"]: (g, d) for g in bank for d in g["drills"]}
    reviewed = {r["drill_id"]: r for r in ledger}
    catalog = load_pathway_catalog()
    profiles = []
    for region, config in PROFILES.items():
        group = next(g for g in bank if (g["location"], g["type"]) == (region, "impingement"))
        stages = ["calm", "restore"] if "restore_id" in config else ["calm"]
        prescriptions = []
        for stage in stages:
            identity = f"{region}_impingement_recovery_support" if stage == "calm" else config["restore_id"]
            target_group, original = indexed.get(identity, (group, group["drills"][0]))
            drill = deepcopy(original)
            text = (config["calm"] if stage == "calm" else config["restore"]) + " " + STOP
            drill.update(id=identity, name=f"{region.title()} impingement protection guidance" if stage == "calm" else config["name"],
                         notes=text, rehab_stage=stage, function="recovery_downregulation" if stage == "calm" else "mobility",
                         equipment=[] if stage == "calm" else config["equipment"], load="minimal" if stage == "calm" else config["load"],
                         impact="none", velocity="low", target_regions=[region], target_tissues=[config["tissue"]],
                         laterality_applicability="not_applicable" if stage == "calm" else "side_specific",
                         contraction_type="unknown" if stage == "calm" else "mixed", sport_specificity="general_rehab", contact_level="none",
                         dose=None, pain_ceiling=None, allowed_severities=None, progress_when=None, regress_when=None, stop_when=None,
                         evidence_notes="Sources: " + ", ".join(config["sources"]) + ". Protected regional baseline only; not a diagnosis or return-to-sport protocol. No numeric dose, clinical severity rule or universal pain threshold inferred. Comfortable/non-provoking movement is a conservative baseline constraint. Existing low/moderate eligibility and cadence are product rules. Individual restrictions remain authoritative."
                         + (" Pain-free hip ROM is supported by the non-operative ISHA consensus." if region == "hip" else ""))
            # Camp availability is separate from tissue readiness. Baselines
            # are available in every camp phase; profile live stages gate use.
            target_group["phase_progression"] = "GPP → SPP → TAPER"
            for other in bank:
                other["drills"] = [d for d in other["drills"] if d["id"] != identity]
            target_group["drills"].append(drill)
            reviewed[identity] = mark_reviewed(target_group, drill, reviewed.get(identity))
            prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage, instructions=text,
                                      dose=None, allowed_severities=["low", "moderate"], sources=config["sources"], stop_when=[STOP]))
        profile = dict(policy_id=f"{region}_impingement", version=1, region=region, injury_type="impingement",
                       pathway_family="joint_irritation_or_impingement", evidence_sources=config["sources"],
                       prescriptions=prescriptions, blocked_regions=[region], blocked_tags=[], contact_limit="none",
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
