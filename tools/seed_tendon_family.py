"""Curated tendonitis regional baselines within the existing profile architecture."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fightcamp.injury_location_registry import LOCATION_REGISTRY, canonicalize_location_from_registry  # noqa: E402
from fightcamp.rehab_clinical import compose_policy, content_hash, load_pathway_catalog, policy_review_hash  # noqa: E402
from tools.generate_rehab_metadata_review import _fresh_record  # noqa: E402
from tools.rehab_metadata_review_lib import REVIEW_FIELDS  # noqa: E402

NHS = "https://www.nhs.uk/conditions/tendonitis/"
ACHILLES = "https://myjointhealthhub.bnssg.nhs.uk/foot-ankle-pain/achilles-tendinopathy/"
INSERTIONAL = "https://www.kentcht.nhs.uk/leaflet/achilles-insertional-tendinopathy/"
SHOULDER = "https://www.rjah.nhs.uk/our-services/therapy/supported-self-care/rotator-cuff-related-shoulder-pain/"
BICEPS = "https://msk-bexley.nhs.uk/conditions/shoulder-pain/biceps-tendinopathy"
ELBOW = "https://msk-bexley.nhs.uk/conditions/elbow-pain/tennis-elbow"
WRIST = "https://www.cuh.nhs.uk/patient-information/hand-therapy-active-wrist-exercises/"
TENOSYNOVITIS = "https://www.mskdorset.nhs.uk/hand-and-wrist-pain/hand-and-wrist-pain-de-quervains-tenosynovitis/"
HAND = "https://www.nth.nhs.uk/resources/hand-therapy-trigger-finger/"
GLIDING = "https://www.nth.nhs.uk/resources/hand-therapy-tendon-gliding-exercises/"

# Exact bank-backed region identities. Sources support a protected baseline;
# subtype-specific resistance/return protocols are deliberately not inherited.
# Region, sources, RESTORE name, instructions, equipment, demand, target tissue.
PROFILES = [
    ("achilles", [ACHILLES, INSERTIONAL], "Seated Achilles heel movement",
     "Sit with the affected foot flat on the floor and the knee bent. Slowly lift the heel within a comfortable pain-free range, then lower it to floor level with the forefoot resting on the floor. Do not add weight, stand on a step, drop below floor level or bounce. This is seated movement, not a strength test or a required isometric-first protocol.", [], "low", "Achilles tendon"),
    ("shoulder", [SHOULDER], "Comfortable unloaded shoulder rotation",
     "Sit upright with the affected elbow comfortably bent and tucked by your side. Gently turn the forearm outwards within a small comfortable pain-free range, then return. Keep the upper arm by your side; do not force rotation, raise the arm overhead or add a weight or band.", [], "minimal", "shoulder tendons"),
    ("biceps", [BICEPS], "Comfortable unloaded elbow movement",
     "With the upper arm comfortably by your side, gently bend and straighten the affected elbow within a pain-free range. Keep the shoulder relaxed and the hand empty. Do not stretch the arm behind the body, force forearm rotation, use an incline bench or add resistance. This maintains comfortable arm movement; it does not select a proximal or distal biceps strengthening protocol.", [], "minimal", "biceps tendons"),
    ("forearm", [ELBOW, WRIST], "Supported unloaded wrist movement",
     "Sit with the affected forearm supported on a table and the hand relaxed. Gently bend and straighten the wrist within a small comfortable pain-free range. Do not grip tightly, force a stretch or add a weight or band. This maintains comfortable movement without choosing a flexor or extensor strengthening protocol.", ["table"], "minimal", "forearm flexor and extensor tendons"),
    ("elbow", [ELBOW], "Comfortable unloaded elbow movement",
     "Keep the affected upper arm comfortably by your side and slowly bend and straighten the elbow within a pain-free range with the hand empty. Do not force end range, squeeze a ball, perform wrist curls or add resistance. A red, hot or swollen elbow needs assessment before exercise. This baseline does not diagnose lateral, medial or posterior tendon involvement.", [], "minimal", "elbow tendons"),
    ("wrist", [WRIST, TENOSYNOVITIS], "Supported unresisted forearm turn",
     "Sit with the affected elbow by your side and the forearm comfortably supported. With the hand empty and wrist relaxed, slowly turn the palm upwards and downwards within a small pain-free range. Do not force twisting, hold a weight, add a band or use rapid pulses. Follow any clinician-directed splint or movement restriction.", [], "minimal", "wrist and forearm tendons"),
    ("hand", [HAND, GLIDING], "Comfortable unloaded hand tendon glide",
     "Support the affected hand with the wrist comfortable. Start with the fingers straight, gently bend the middle and end joints into a small hook while keeping the knuckles straight, then return. Stay within a comfortable pain-free range; do not force a fist, squeeze a ball or add putty, bands or grip resistance. Stop if a finger catches or locks; follow any clinician-directed splint restrictions.", [], "minimal", "hand flexor tendons"),
    ("fingers", [HAND, GLIDING], "Comfortable unloaded finger movement",
     "Support the affected hand with the wrist comfortable. Gently bend and straighten the injured finger within a small pain-free range, then relax. Do not force a locked finger, pull it with the other hand, use putty or squeeze a ball. Stop if the finger catches or locks; follow any clinician-directed splint restrictions.", [], "minimal", "finger tendons"),
]

# Only useful identifiable originals are repaired. Duplicated copies and vague
# variants are not marked reviewed. Unknown external resistance stays unknown.
FIXED = {
    "achilles_tendonitis_eccentric_calf_drops_on_step": ("Floor-level controlled Achilles lowering", "Beside stable support on firm level ground, raise both heels, then transfer weight to the affected leg and slowly lower its heel only to the floor. Do not use a step, lower into deep dorsiflexion, increase depth or add speed or weight.", ["stable_support"], "moderate", "eccentric", "Achilles tendon"),
    "shoulder_tendonitis_banded_scaption_holds": ("Fixed-range banded scaption hold", "With one fixed clinician-selected band, raise the affected arm in the scapular plane only to an individually advised comfortable height below shoulder level and hold without movement, then lower. Do not increase height, band tension or hold to fatigue. This does not isolate one tendon.", ["resistance_band"], "unknown", "isometric", "shoulder tendons"),
    "bicep_tendonitis_incline_db_curl_eccentric_focus": ("Seated supported biceps curl", "Sit upright with the upper arm by your side and one fixed clinician-selected dumbbell. Bend the elbow and lower under control within the individually advised range. Do not use an incline stretch position, increase weight or work to fatigue. The selected weight and tendon site require individual assessment.", ["dumbbell"], "unknown", "mixed", "biceps tendons"),
    "forearm_tendonitis_eccentric_wrist_extensions": ("Supported eccentric wrist extension", "Support the affected forearm palm-down on a table with the wrist over the edge and one fixed clinician-selected dumbbell in the hand. Use the other hand to assist the lift, then slowly lower the wrist within the individually advised range. Do not force end range or increase weight, speed or volume.", ["table", "dumbbell"], "unknown", "eccentric", "forearm extensor tendons"),
    "elbow_tendonitis_eccentric_reverse_wrist_curls": ("Supported eccentric wrist extension", "Support the affected forearm palm-down on a table with the wrist over the edge and one fixed clinician-selected dumbbell in the hand. Assist the lift with the other hand, then slowly lower within the individually advised range. Do not increase speed or load. This extensor exercise does not apply automatically to medial or posterior elbow pain.", ["table", "dumbbell"], "unknown", "eccentric", "common wrist extensor tendon at elbow"),
    "wrist_tendonitis_eccentric_wrist_flexion_with_dumbbell": ("Supported eccentric wrist flexion", "Support the affected forearm palm-up on a table with the wrist over the edge and one fixed clinician-selected dumbbell. Assist the lift with the other hand, then slowly lower within the individually advised range. Do not force a stretch, increase weight or add faster work. This flexor exercise does not apply automatically to thumb-side tenosynovitis.", ["table", "dumbbell"], "unknown", "eccentric", "wrist flexor tendons"),
}
RESTORE_ID = {"wrist": "wrist_tendonitis_pronation_supination_twists"}


def mark_reviewed(group, drill, prior):
    record = _fresh_record(group["location"], group["type"], drill)
    record.update(review_state="reviewed", proposed={f: drill[f] for f in REVIEW_FIELDS},
                  movement_archetype="manual_recovery" if drill["rehab_stage"] == "calm" else "mobility_rom" if drill["function"] == "mobility" else "bodyweight_strength" if drill["rehab_stage"] == "restore" else "isometric" if drill["contraction_type"] == "isometric" else "eccentric_loading" if drill["contraction_type"] == "eccentric" else "external_load_strength")
    if prior and prior["source_hash"] != record["source_hash"]:
        record["source_history"] = prior.get("source_history", []) or [
            {f: prior[f] for f in ("source_hash", "name", "notes")}]
    elif prior and prior.get("source_history"):
        record["source_history"] = prior["source_history"]
    return record


def mechanics(drill, region, tissue, *, stage, equipment, load, contraction):
    drill.update(rehab_stage=stage, function="recovery_downregulation" if stage == "calm" else "mobility" if stage == "restore" else "control",
                 equipment=equipment, load=load, impact="none", velocity="low", target_regions=[region],
                 target_tissues=[tissue], laterality_applicability="not_applicable" if stage == "calm" else "side_specific",
                 contraction_type=contraction, sport_specificity="general_rehab", contact_level="none",
                 dose=None, pain_ceiling=None, allowed_severities=None, progress_when=None, regress_when=None, stop_when=None)


def main():
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    bank, ledger, raw = read("rehab_bank.json"), read("rehab_metadata_review.json"), read("rehab_pathways.json")
    catalog = load_pathway_catalog()
    reviewed = {r["drill_id"]: r for r in ledger}
    indexed = {d["id"]: (g, d) for g in bank for d in g["drills"]}
    sources_by_region = {region: list(dict.fromkeys([NHS, *sources])) for region, sources, *_ in PROFILES}
    for identity, (name, text, equipment, load, contraction, tissue) in FIXED.items():
        group, drill = indexed[identity]
        region = canonicalize_location_from_registry(group["location"])
        prior = reviewed[identity]
        drill.update(name=name, notes=text + " Stop if symptoms worsen during or after the work.")
        mechanics(drill, region, tissue, stage="load", equipment=equipment, load=load, contraction=contraction)
        drill["evidence_notes"] = "Fixed mechanics reviewed; sources: " + ", ".join(sources_by_region[region]) + ". Dormant LOAD content, not an active prescription. External load remains unknown where not measured. Tendon site, individual resistance, functional tolerance and a sourced evaluable transition are required before activation. Eccentrics are not assumed superior."
        reviewed[identity] = mark_reviewed(group, drill, prior)
    profiles = []
    for region, sources, name, restore, equipment, load, tissue in PROFILES:
        sources = sources_by_region[region]
        group = next(g for g in bank if g["type"] == "tendonitis" and canonicalize_location_from_registry(g["location"]) == region)
        prescriptions = []
        for stage in ("calm", "restore"):
            identity = f"{region}_tendonitis_recovery_support" if stage == "calm" else RESTORE_ID.get(region, f"{region}_tendonitis_reviewed_restore")
            prior = reviewed.get(identity)
            drill = deepcopy(indexed[identity][1] if identity in indexed else group["drills"][0])
            calm = "Reduce activities that aggravate the affected tendon and keep the area comfortably supported. Avoid heavy lifting, strong gripping or twisting that worsens symptoms; do not repeatedly test the painful tendon. Keep ordinary comfortable movement as symptoms allow rather than applying a universal prolonged-rest timetable. Follow any clinician-directed restrictions. Sudden severe pain, a snap or pop with loss of function, suspected rupture, a hot red swollen area, fever or altered sensation needs medical assessment."
            if region == "achilles":
                calm += " Reduce provocative running, hopping and forceful push-off; do not stretch into deep dorsiflexion or use heel drops below floor level when insertional status is unknown."
            elif region in {"shoulder", "biceps"}:
                calm += " Reduce provocative overhead work and end-range loading; do not force the arm behind the body."
            else:
                calm += " Reduce provocative grip and repetitive hand loading; follow any individual splint advice without changing prescribed protection."
            text = calm if stage == "calm" else restore + " Stop if pain or symptoms worsen during or after the movement. This conservative baseline does not establish readiness for resistance or sport."
            drill.update(id=identity, name=f"{region.title()} tendon load-management guidance" if stage == "calm" else name, notes=text)
            mechanics(drill, region, tissue, stage=stage, equipment=[] if stage == "calm" else equipment,
                      load="minimal" if stage == "calm" else load, contraction="unknown" if stage == "calm" else "mixed")
            if region == "achilles" and stage == "restore":
                drill["function"] = "tendon_loading"
            drill["evidence_notes"] = "Sources: " + ", ".join(sources) + ". Protected regional baseline, not a subtype diagnosis or complete tendon-loading protocol. No numeric dose or pain threshold inferred. Pain-free range is a conservative product constraint, not a universal assertion that pain during tendon exercise is unsafe. Existing low/moderate eligibility and scheduling cadence remain product rules."
            target_group = indexed[identity][0] if identity in indexed else group
            for existing_group in bank:
                existing_group["drills"] = [d for d in existing_group["drills"] if d["id"] != identity]
            target_group["drills"].append(drill)
            reviewed[identity] = mark_reviewed(target_group, drill, prior)
            prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage, instructions=text,
                                      dose=None, allowed_severities=["low", "moderate"], sources=sources,
                                      stop_when=["Stop for pain or worsening symptoms during or after the work.", "Seek assessment for suspected rupture, loss of function, altered sensation, a hot red swollen area or fever."]))
        registry = LOCATION_REGISTRY.get(region, {})
        restrictions = list(dict.fromkeys([region, registry.get("exclusion_region", region), *registry.get("secondary_exclusion_regions", [])]))
        profile = dict(policy_id=f"{region}_tendonitis", version=1, region=region, injury_type="tendonitis",
                       pathway_family="tendon_rehab", evidence_sources=sources, prescriptions=prescriptions,
                       blocked_regions=restrictions, blocked_tags=[], contact_limit="none", live_stages=["calm", "restore"], transition_overrides={})
        draft = compose_policy(catalog, profile)
        profile.update(status="active", activation="live", content_hash=policy_review_hash(draft), prescriptions=[p.model_dump() for p in draft.prescriptions])
        profiles.append(profile)
    ids = {p["policy_id"] for p in profiles}
    raw["profiles"] = [p for p in raw["profiles"] if p["policy_id"] not in ids] + profiles
    debt = read("rehab_bank_duplicate_debt.json")
    # The reviewed floor-level variant no longer duplicates the untouched step
    # variant; retire that exact allowance without approving/removing its copy.
    debt["duplicates"] = [row for row in debt["duplicates"] if not (
        row["location"] == "achilles" and row["type"] == "tendonitis"
        and row["name"] == "Eccentric Calf Drops on Step")]
    for name, value in [("rehab_bank.json", bank), ("rehab_pathways.json", raw),
                        ("rehab_bank_duplicate_debt.json", debt),
                        ("rehab_metadata_review.json", [reviewed[d["id"]] for g in bank for d in g["drills"] if d["id"] in reviewed])]:
        (ROOT / "data" / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
