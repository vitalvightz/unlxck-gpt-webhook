"""Curated ligament-family bank repairs and regional baseline profiles.

No new taxonomy, progression engine, numeric doses or return-to-sport rules.
"""
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

NHS = "https://www.nhs.uk/conditions/sprains-and-strains/"
ANKLE = "https://www.rightdecisions.scot.nhs.uk/patient-information-leaflets/primary-community-services/physiotherapy/ankle-injuries/"
CAI = "https://doi.org/10.2519/jospt.2021.0302"
KNEE = "https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-knee/"
WRIST = "https://www.cuh.nhs.uk/patient-information/hand-therapy-active-wrist-exercises/"
HAND = "https://www.leedsth.nhs.uk/patients/resources/the-hand-and-wrist/"
ELBOW = "https://www.nbt.nhs.uk/our-services/a-z-services/emergency-department/ed-miu-patient-information/elbow-injuries"
SHOULDER = "https://www.leedsth.nhs.uk/patients/resources/early-advice-and-exercises-for-soft-tissue-injuries-of-the-shoulder/"
SHOULDER_INSTABILITY = "https://msk-bexley.nhs.uk/conditions/shoulder-pain/shoulder-instability"

# Region, exact type, source(s), fixed RESTORE instruction, mechanical load.
PROFILES = [
    ("ankle", "instability", [CAI, ANKLE], "Supported balance on firm ground",
     "Only when standing and weight bearing are comfortable, stand beside a stable counter and gently balance on the affected leg on firm, level ground with support available and eyes open. Stop if the ankle gives way or feels unsafe. Do not hop, use a cushion, close your eyes or work to fatigue.", "moderate", "isometric", "control", ["stable_support"]),
    ("knee", "instability", [KNEE], "Supported knee heel slide",
     "Sit or lie with the affected leg supported on a smooth surface. Gently slide the heel towards you to bend the knee, then slide back to straighten within a comfortable pain-free range. Do not force movement, stand on an unstable surface or add resistance. Stop and seek assessment if the knee locks, repeatedly gives way or cannot bear weight.", "minimal", "mixed", "mobility", []),
    ("toe", "sprain", [NHS], "Comfortable seated toe movement",
     "When pain no longer stops comfortable movement, sit with the foot supported and gently bend and straighten the affected toe within a small pain-free range. Do not pull the toe into a stretch, push off through it, hop or add resistance. Follow any clinician-directed protection; a deformed toe or inability to move it needs assessment.", "minimal", "mixed", "mobility", []),
    ("wrist", "sprain", [WRIST], "Supported wrist bend and straighten",
     "Rest the affected forearm on a table with the hand relaxed. Slowly bend and straighten the wrist within a comfortable pain-free range. Do not force end range, grip a weight or push through the hand. Follow any clinician-directed splint or movement restrictions.", "minimal", "mixed", "mobility", ["table"]),
    ("elbow", "sprain", [ELBOW], "Supported elbow bend and straighten",
     "Once pain begins to settle, support the affected elbow with your other hand and slowly bend and straighten it within a comfortable pain-free range. Do not force straightening, carry weights or push through the arm. Follow any clinician-directed movement restrictions.", "minimal", "mixed", "mobility", []),
    ("shoulder", "sprain", [SHOULDER], "Supported shoulder pendulum",
     "Lean forward with your uninjured hand on a stable support and let the affected arm hang relaxed. Allow small gentle forward-and-back and side-to-side swings within a comfortable pain-free range. Do not force overhead movement, add weights or perform presses. Follow any individual restrictions given by your clinician.", "minimal", "mixed", "mobility", ["stable_support"]),
    ("shoulder", "instability", [SHOULDER_INSTABILITY], "Gentle shoulder blade setting",
     "Sit supported with the affected arm relaxed by your side. Gently draw the shoulder blade back and down without forcing the shoulder into end range, then relax. Keep the movement small and comfortable. Stop if the joint feels as though it is slipping. Do not add weights, overhead work or stretching. Suspected dislocation or subluxation needs medical assessment.", "low", "mixed", "control", []),
    ("hand", "sprain", [HAND], "Gentle hand opening and closing",
     "With the forearm supported and wrist comfortable, gently open the affected hand and bend the fingers into a loose fist, then straighten them within a pain-free range. Do not squeeze tightly, use a ball or band, force stiff joints or add impact. Follow any splint or tendon-protection instructions from your clinician.", "minimal", "mixed", "mobility", []),
    ("fingers", "sprain", [HAND], "Gentle finger bend and straighten",
     "Support the affected hand and gently bend and straighten the injured finger within a comfortable pain-free range. Do not push it with the other hand, pull against a band, tap forcefully or add grip resistance. Follow any clinician-directed protection; do not bend a joint that you have been instructed to keep splinted straight.", "minimal", "mixed", "mobility", []),
]

# Each original is explicitly constrained to one movement and demand. Mechanical
# review does not approve the dose/efficacy of the equipment variant or activate it.
# id: instruction, equipment, stage, load, contraction
FIXED = {
    "ankle_sprain_single_leg_balance_on_foam_pad": ("Balance on the affected leg on a fixed foam pad beside stable support with eyes open. Keep the surface and position fixed; do not add perturbations or fatigue work.", ["foam_pad", "stable_support"], "load", "moderate", "isometric"),
    "ankle_sprain_banded_ankle_circles": ("Sit with the leg supported. Move the ankle slowly in a small comfortable circle against one fixed light resistance band; do not increase tension or speed.", ["resistance_band"], "load", "low", "mixed"),
    "ankle_instability_lateral_hop_stick_drill": ("Perform one small lateral hop on firm level ground and settle the landing before the next attempt. Keep distance fixed; no fast repeated hops or contact.", [], "dynamic", "moderate", "mixed"),
    "ankle_instability_foam_pad_jump_stick": ("Perform a small two-foot jump onto a fixed foam pad and settle the landing. Keep the height and surface fixed; no repeated bouncing or perturbation.", ["foam_pad"], "dynamic", "moderate", "mixed"),
    "knee_instability_mini_band_lateral_walks": ("With a fixed light mini-band and knees comfortably bent, take slow small sideways steps on level ground. Keep band tension and step size fixed; no faster steps or fatigue work.", ["mini_band"], "load", "low", "mixed"),
    "knee_instability_reactive_knee_bounces_foam_pad": ("Stand with both feet on a fixed foam pad beside stable support and make small slow knee bends without bouncing or jumping. Keep depth fixed; no partner contact.", ["foam_pad", "stable_support"], "load", "moderate", "mixed"),
    "toe_sprain_double_leg_pogo_jumps": ("On firm level ground, perform small two-foot pogo jumps with a fixed low height. No single-leg work, added weight, increased speed or fatigue progression.", [], "dynamic", "moderate", "mixed"),
    "toe_sprain_toe_off_isometric_presses": ("With the foot supported on level ground, gently press through the affected forefoot without movement, then relax. Keep pressure fixed; no forced toe extension or explosive push-off.", [], "load", "low", "isometric"),
    "wrist_sprain_isometric_wall_wrist_press": ("With the wrist comfortable and the hand against a stable wall, press gently without moving the wrist, then relax. Keep pressure fixed; no punching or forced extension.", ["wall"], "load", "low", "isometric"),
    "wrist_sprain_band_assisted_wrist_flexion_hold": ("Support the forearm and hold the wrist in comfortable mid-range flexion against a fixed light band, then relax. Do not force end range or lengthen the hold to fatigue.", ["resistance_band"], "load", "low", "isometric"),
    "wrist_sprain_wrist_stability_drill_with_dynamometer": ("With the forearm supported and wrist neutral, gently squeeze a dynamometer using one clinician-selected fixed resistance. This is grip loading, not a test of ligament healing or clearance.", ["dynamometer"], "load", "unknown", "isometric"),
    "wrist_sprain_band_stabilization_circles": ("With the forearm supported, slowly move the wrist in a small comfortable circle against one fixed light band. No forced end range, faster movement or resistance increase.", ["resistance_band"], "load", "low", "mixed"),
    "wrist_sprain_isometric_wrist_holds_various_angles": ("Support the forearm with the wrist neutral. Gently resist the other hand without movement, then relax. Use only this fixed neutral position; do not add angles, weight or fatigue holds.", [], "load", "low", "isometric"),
    "wrist_sprain_plank_to_palm_rockbacks": ("From hands and knees on firm ground, gently shift weight back and return while the wrists stay comfortable. Keep the knees down; no full plank, speed work or forced extension.", [], "load", "moderate", "mixed"),
    "elbow_sprain_wrist_wall_slides_elbow_straight": ("Place the affected hand lightly on a stable wall with the elbow comfortably straight. Slowly slide the hand through a small comfortable range; do not lock or force the elbow, press hard or add resistance.", ["wall"], "load", "low", "mixed"),
    "elbow_sprain_overhead_band_triceps_extension": ("Only if the overhead position is comfortable, slowly bend and straighten the elbow against a fixed light band. Do not force straightening, increase resistance or work to fatigue.", ["resistance_band"], "load", "low", "mixed"),
    "shoulder_sprain_isometric_banded_row": ("With the affected arm close to the side, gently draw back against a fixed light band and hold without moving, then relax. No eccentric row, increased tension or fatigue hold.", ["resistance_band"], "load", "low", "isometric"),
    "shoulder_sprain_wall_supported_external_rotation": ("Keep the elbow comfortably bent by the side and gently press the back of the hand into a towel against a stable wall without movement, then relax. No forced range or added resistance.", ["wall", "towel"], "load", "low", "isometric"),
    "shoulder_sprain_90_90_external_rotation_holds": ("Only if the shoulder-height position is comfortable, hold the elbow bent at a right angle and gently resist external rotation with the other hand without movement. No forced position or fatigue hold.", [], "load", "low", "isometric"),
    "shoulder_sprain_overhead_scapular_pull_aparts": ("Only if the overhead position is comfortable, slowly pull a fixed light band apart through a small range and return under control. No increased tension, end-range stretch or faster movement.", ["resistance_band"], "load", "low", "mixed"),
    "shoulder_instability_kb_bottom_up_carry": ("Hold a kettlebell upside down with the elbow bent close to the side and walk slowly on level ground over one fixed short distance. Use an individually selected fixed weight; no overhead carry or perturbations.", ["kettlebell"], "load", "unknown", "isometric"),
    "shoulder_instability_wall_walks_isometric": ("Place the affected hand against a stable wall at a comfortable height and hold gently without moving. No climbing higher, forced overhead position or added resistance.", ["wall"], "load", "low", "isometric"),
    "shoulder_instability_quadruped_weight_shifts_arm_reaches": ("From hands and knees on firm ground, gently shift weight between the hands through a small comfortable range. Keep both hands down; no arm reaches or instability challenge.", [], "load", "moderate", "mixed"),
    "shoulder_instability_banded_overhead_carries": ("Only if individually advised to use an overhead position, hold a fixed light band overhead and walk slowly over a fixed short distance. No oscillations, range increase or fatigue work.", ["resistance_band"], "load", "unknown", "isometric"),
    "hand_sprain_finger_band_extensions": ("Support the hand and slowly open the fingers against a fixed light band, then release. No flicking, increased tension or fatigue work.", ["resistance_band"], "load", "low", "mixed"),
    "hand_sprain_palm_squeeze_with_soft_ball": ("Support the forearm and gently squeeze one soft ball with the wrist comfortable, then relax. Keep pressure fixed; no harder ball or fatigue holds.", ["soft_ball"], "load", "low", "isometric"),
    "hand_sprain_band_resisted_finger_abduction": ("With the hand supported, slowly spread the fingers against one fixed light band and return. No forced joint range, increased tension or faster repetitions.", ["resistance_band"], "load", "low", "mixed"),
    "hand_sprain_hook_grip_plate_pinches": ("With the wrist comfortable, hold one clinician-selected fixed plate using a comfortable hook grip, then release. No carrying, heavier plate or fatigue hold; load depends on the selected weight.", ["plate"], "load", "unknown", "isometric"),
    "fingers_sprain_finger_band_expansions": ("Support the hand and slowly spread the fingers against one fixed light band, then release. Do not force the injured joint, increase resistance or work to fatigue.", ["resistance_band"], "load", "low", "mixed"),
    "fingers_sprain_finger_taps_on_hard_surface": ("With the hand supported, make light slow finger taps onto a firm table. Keep the force and speed fixed; no forceful tapping or grip-release simulation.", ["table"], "dynamic", "unknown", "mixed"),
    "fingers_sprain_tape_assisted_plyo_taps": ("Only if individually advised, perform small quick finger taps onto a firm surface with clinician-directed tape. Keep speed and force fixed. Tape does not establish readiness or protect against every injury.", ["table", "tape"], "dynamic", "unknown", "mixed"),
    "fingers_sprain_mini_band_finger_spread_hold": ("Support the hand and hold the fingers gently spread against one fixed light mini-band, then relax. Do not force joint range, increase tension or extend holds to fatigue.", ["mini_band"], "load", "low", "isometric"),
}


def mark_reviewed(group, drill, prior, *, archetype=None):
    record = _fresh_record(group["location"], group["type"], drill)
    record.update(review_state="reviewed", proposed={f: drill[f] for f in REVIEW_FIELDS})
    if archetype:
        record["movement_archetype"] = archetype
    if prior and prior["source_hash"] != record["source_hash"]:
        record["source_history"] = prior.get("source_history", []) or [
            {f: prior[f] for f in ("source_hash", "name", "notes")}]
    elif prior and prior.get("source_history"):
        record["source_history"] = prior["source_history"]
    return record


def main():
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    bank, ledger, raw = read("rehab_bank.json"), read("rehab_metadata_review.json"), read("rehab_pathways.json")
    catalog = load_pathway_catalog()
    reviewed = {r["drill_id"]: r for r in ledger}
    indexed = {d["id"]: (g, d) for g in bank for d in g["drills"]}
    evidence = {(region, kind): sources for region, kind, sources, *_ in PROFILES}
    evidence[("ankle", "sprain")] = [NHS, ANKLE]
    active_ids = {p["drill_id"] for profile in raw["profiles"] for p in profile["prescriptions"]}
    audit_path = ROOT / "docs/sprain-family-bank-audit.json"
    if not audit_path.exists():
        inventory = []
        for group in bank:
            if group["type"] not in {"sprain", "instability"}:
                continue
            region = canonicalize_location_from_registry(group["location"])
            for drill in group["drills"]:
                repair = drill["id"].removesuffix("_2") in FIXED
                disposition = "existing_live" if drill["id"] in active_ids else "repair_closed_stage" if repair else "dormant"
                reason = "Existing reviewed ankle prescription is preserved." if disposition == "existing_live" else "Fixed mechanics reviewed; clinical progression and required inputs do not exist." if repair else "No sourced regional diagnosis-specific prescription; do not infer a joint from a muscle/head/unspecified label or copy a sprain protocol into unexplained instability."
                inventory.append({"region": region, "bank_location": group["location"], "injury_type": group["type"],
                                  "drill_id": drill["id"], "name": drill["name"], "notes": drill["notes"],
                                  "source_hash": reviewed[drill["id"]]["source_hash"],
                                  "flags": reviewed[drill["id"]]["flags"], "disposition": disposition, "reason": reason})
        audit_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for identity, (group, drill) in indexed.items():
        key = identity.removesuffix("_2")
        if key not in FIXED:
            continue
        instructions, equipment, stage, load, contraction = FIXED[key]
        prior = reviewed[identity]
        region = canonicalize_location_from_registry(group["location"])
        drill.update(notes=instructions + " Stop if pain, giving way or symptoms worsen during or after the work.",
                     rehab_stage=stage, function="control", equipment=equipment,
                     load=load, impact="unknown" if stage == "dynamic" else "none",
                     velocity="high" if "plyo" in key or "pogo" in key else "moderate" if stage == "dynamic" else "low",
                     target_regions=[region], target_tissues=[region + " joint supporting soft tissues"],
                     laterality_applicability="side_specific", contraction_type=contraction,
                     sport_specificity="general_rehab", contact_level="none",
                     dose=None, pain_ceiling=None, allowed_severities=None, progress_when=None, regress_when=None, stop_when=None,
                     evidence_notes="Reviewed fixed exercise mechanics. Regional guidance: " + ", ".join(evidence[(region, group["type"])])
                     + ". This does not establish dose, efficacy or eligibility for the exact equipment variant. "
                     + "Not an active prescription. LOAD/DYNAMIC/RETURN require separately sourced, evaluable transitions. Unknown demand remains unknown.")
        replacements = {
            "knee_instability_reactive_knee_bounces_foam_pad": "Controlled knee bends on foam pad",
            "wrist_sprain_isometric_wrist_holds_various_angles": "Neutral isometric wrist hold",
            "wrist_sprain_plank_to_palm_rockbacks": "Supported hands-and-knees wrist rockback",
            "shoulder_instability_wall_walks_isometric": "Comfortable fixed-height wall hold",
            "shoulder_instability_quadruped_weight_shifts_arm_reaches": "Quadruped weight shift with both hands down",
        }
        drill["name"] = replacements.get(key, drill["name"])
        reviewed[identity] = mark_reviewed(group, drill, prior)
    profiles = []
    for region, kind, sources, name, instructions, load, contraction, function, equipment in PROFILES:
        group = next(g for g in bank if canonicalize_location_from_registry(g["location"]) == region and g["type"] == kind)
        template = deepcopy(group["drills"][0])
        prescriptions = []
        for stage in ("calm", "restore"):
            identity = f"{region}_{kind}_" + ("recovery_support" if stage == "calm" else "reviewed_restore")
            calm = ("Protect the injured joint and avoid exercise or activity that aggravates it. During the first few days of a new sprain, rest from loading it and avoid massage or forced stretching. Follow any clinician-directed support or movement restrictions. Seek assessment for severe or worsening pain, deformity, inability to use the joint or loss of sensation." if kind == "sprain" else
                    "Avoid positions or activities in which the joint feels unsafe or gives way. Keep it comfortably supported and follow any clinician-directed restrictions. Arrange assessment for new or repeated giving way. Suspected dislocation, subluxation, severe pain, deformity or loss of sensation needs medical assessment; do not test the joint with hops, end-range stretches or perturbations.")
            text = calm if stage == "calm" else instructions + " Stop if pain, slipping or symptoms worsen during or after the work."
            drill = deepcopy(template)
            drill.update(id=identity, name=f"{region.title()} {kind} protective guidance" if stage == "calm" else name,
                         notes=text, rehab_stage=stage, function="recovery_downregulation" if stage == "calm" else function,
                         equipment=[] if stage == "calm" else equipment,
                         load="minimal" if stage == "calm" else load, impact="none", velocity="low",
                         target_regions=[region], target_tissues=[region + " joint supporting soft tissues"],
                         laterality_applicability="not_applicable" if stage == "calm" else "side_specific",
                         contraction_type="unknown" if stage == "calm" else contraction,
                         sport_specificity="general_rehab", contact_level="none",
                         dose=None, pain_ceiling=None, allowed_severities=None, progress_when=None, regress_when=None, stop_when=None,
                         evidence_notes="Sources: " + ", ".join([NHS, *sources])
                         + ". Fixed protective baseline only; no numeric dose or return clearance. Low/moderate eligibility and session allocation cadence are existing product safety/scheduling rules, not a clinical diagnosis or exercise dose.")
            group["drills"] = [d for d in group["drills"] if d["id"] != identity] + [drill]
            reviewed[identity] = mark_reviewed(group, drill, reviewed.get(identity), archetype="manual_recovery" if stage == "calm" else "balance_control" if function == "control" else "mobility_rom")
            prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage,
                                      instructions=text, dose=None, allowed_severities=["low", "moderate"],
                                      stop_when=["Stop for pain, giving way, slipping or worsening symptoms.", "Seek assessment for deformity, inability to use the joint or loss of sensation."],
                                      sources=[NHS, *sources]))
        registry = LOCATION_REGISTRY.get(region, {})
        restrictions = list(dict.fromkeys([region, registry.get("exclusion_region", region), *registry.get("secondary_exclusion_regions", [])]))
        if region == "ankle":
            restrictions = next(p for p in raw["profiles"] if p["policy_id"] == "ankle_sprain")["blocked_regions"]
        profile = dict(policy_id=f"{region}_{kind}", version=1, pathway_family="ligament_sprain_or_instability",
                       region=region, injury_type=kind, evidence_sources=[NHS, *sources], prescriptions=prescriptions,
                       blocked_regions=restrictions, blocked_tags=[], contact_limit="none", live_stages=["calm", "restore"], transition_overrides={})
        draft = compose_policy(catalog, profile)
        profile.update(status="active", activation="live", content_hash=policy_review_hash(draft), prescriptions=[p.model_dump() for p in draft.prescriptions])
        profiles.append(profile)
    # Existing ankle doses, bundle, bank hashes and policy hash are immutable here.
    anchor = next(p for p in raw["profiles"] if p["policy_id"] == "ankle_sprain")
    for p in anchor["prescriptions"]:
        group, drill = indexed[p["drill_id"]]
        reviewed[drill["id"]] = mark_reviewed(group, drill, reviewed[drill["id"]])
    ids = {p["policy_id"] for p in profiles}
    raw["profiles"] = [p for p in raw["profiles"] if p["policy_id"] not in ids] + profiles
    debt = read("rehab_bank_duplicate_debt.json")
    for row in debt["duplicates"]:
        if row["location"] == "knee" and row["type"] == "instability":
            identity = "knee_instability_mini_band_lateral_walks" if "Walks" in row["name"] else "knee_instability_reactive_knee_bounces_foam_pad"
            row.update(name=indexed[identity][1]["name"], rehab_stage=indexed[identity][1]["rehab_stage"])
    for filename, value in (("rehab_bank.json", bank), ("rehab_pathways.json", raw),
                            ("rehab_metadata_review.json", [reviewed[d["id"]] for g in bank for d in g["drills"] if d["id"] in reviewed]),
                            ("rehab_bank_duplicate_debt.json", debt)):
        (ROOT / "data" / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
