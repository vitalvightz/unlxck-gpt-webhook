"""Reproduce curated strain prescriptions and fixed-demand bank repairs."""
import json
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fightcamp.rehab_clinical import compose_policy, content_hash, load_pathway_catalog, policy_review_hash  # noqa: E402
from fightcamp.injury_location_registry import LOCATION_REGISTRY  # noqa: E402
from tools.generate_rehab_metadata_review import _fresh_record  # noqa: E402
from tools.rehab_metadata_review_lib import REVIEW_FIELDS, source_hash  # noqa: E402

NHS = "https://www.nhs.uk/conditions/sprains-and-strains/"
HAM = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2867336/"
CALF = "https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-calf-strain/"
GROIN = "https://pmc.ncbi.nlm.nih.gov/articles/PMC10569248/"
QUADS = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2941577/"
ELBOW = "https://www.nbt.nhs.uk/our-services/a-z-services/emergency-department/ed-miu-patient-information/elbow-injuries"
SHOULDER = "https://www.leedsth.nhs.uk/patients/resources/early-advice-and-exercises-for-soft-tissue-injuries-of-the-shoulder/"

# bank region, canonical profile region, existing movement, source, fixed variant.
VARIANTS = [
    ("hamstrings", "hamstring", "hamstrings_strain_isometric_hamstring_bridge", HAM,
     "Bent-knee double-leg hamstring bridge",
     "When comfortable movement is possible, lie on your back with both knees bent and feet supported close to your hips. Gently lift into a double-leg bridge and hold briefly at a comfortable height, then lower. Keep the work pain-free and self-paced. Do not walk the feet out, straighten the knees, add resistance or work to fatigue.",
     "activation", [], "moderate", "not_applicable", "isometric", "hamstring muscles"),
    ("calf", "calf", "calf_strain_double_leg_calf_raises", CALF,
     "Supported double-leg calf raise",
     "Begin only once pain has settled, you no longer need crutches and you can stand on your toes without pain. Hold a stable chair, share your weight equally over both feet and gently rise onto your toes, then lower slowly. Work at your own pace and stop if painful. Keep both feet on level ground; do not add weight, single-leg work, a step or fatigue progressions.",
     "activation", ["chair"], "moderate", "not_applicable", "mixed", "gastrocnemius and soleus muscles"),
    ("groin", "groin", "groin_strain_side_lying_hip_adduction", GROIN,
     "Unresisted side-lying hip adduction",
     "Once symptoms have settled enough for comfortable movement, lie on the affected side with the upper leg supported out of the way. Slowly lift and lower the lower leg through a small comfortable range. Keep the work pain-free and self-paced. Stop if groin pain increases during or after the work. Do not add ankle weights, cables, fast repetitions or fatigue work.",
     "activation", [], "low", "side_specific", "mixed", "hip adductor muscles"),
    ("quads", "quads", "quads_unspecified_sliding_leg_extensions_towel_under_foot", QUADS,
     "Supported knee movement with towel",
     "When pain no longer prevents comfortable movement, sit with your foot supported on a towel on a smooth floor. Gently slide the foot to bend and straighten the affected knee within a pain-free range. Keep the movement slow and self-paced. Do not force knee flexion, add resistance or increase speed. Stop if movement becomes painful or symptoms worsen.",
     "mobility", ["towel"], "minimal", "side_specific", "mixed", "quadriceps muscles"),
    ("bicep", "biceps", "bicep_strain_isometric_bicep_curl_hold_mid_range", ELBOW,
     "Supported elbow bend and straighten for biceps strain",
     "Once pain begins to settle, support the affected elbow with your other hand. Slowly bend and straighten the elbow within a comfortable pain-free range. Do not force straightening, carry weights or add curl resistance. Stop if pain or swelling increases. This is gentle movement for an uncomplicated muscle strain, not a tendon tear or repair protocol.",
     "mobility", [], "minimal", "side_specific", "mixed", "biceps muscle"),
    ("triceps", "triceps", "triceps_strain_isometric_wall_triceps_press", ELBOW,
     "Supported elbow bend and straighten for triceps strain",
     "Once pain begins to settle, support the affected elbow with your other hand. Slowly bend and straighten the elbow within a comfortable pain-free range. Do not force the elbow straight, push against a wall or add resistance. Stop if pain or swelling increases. This is gentle movement for an uncomplicated muscle strain, not a tendon tear or repair protocol.",
     "mobility", [], "minimal", "side_specific", "mixed", "triceps muscle"),
    ("shoulder", "shoulder", "shoulder_strain_wall_slides_with_foam_roller", SHOULDER,
     "Supported shoulder pendulum",
     "Lean forward with your uninjured hand on a stable support and let the affected arm hang relaxed. Gently allow small, comfortable forward-and-back and side-to-side swings. Keep the movement pain-free. Do not add weights, force the range or perform presses. Stop if symptoms worsen. Follow any individual movement restrictions given by your treating clinician.",
     "mobility", [], "minimal", "side_specific", "mixed", "shoulder muscles"),
]

# Explicitly reviewed, fixed versions of the existing bank exercises. These are
# mechanical classifications, not permission to bypass the live pathway ladder.
# Equipment/load variants and fight-camp progression are not embedded in a drill.
FIXED = {
    "calf_strain_isometric_wall_push_hold": ("Keep both feet on level ground. Lean into a stable wall and gently press through the forefeet without moving the ankles. Hold only while comfortable, then relax. No band, single-leg variant or fatigue work.", ["wall"], "moderate", "not_applicable", "isometric"),
    "calf_strain_isometric_tip_toe_wall_press": ("Use a stable wall for support. Rise onto both forefeet on level ground and hold a comfortable heel height, then lower. No external load, single-leg variant or fatigue work.", ["wall"], "moderate", "not_applicable", "isometric"),
    "calf_strain_active_band_calf_pumps": ("Sit with the leg supported and a resistance band around the forefoot. Slowly point and release the foot within a comfortable range against a fixed light band. No increase in band tension or speed within this drill.", ["resistance_band"], "low", "side_specific", "mixed"),
    "hamstrings_strain_massage_gun_biceps_femoris_sweep": ("After the acute period, only if your treating clinician has advised self-massage, use gentle superficial pressure over comfortable hamstring tissue. Avoid the injured or bruised area. Stop for pain. Do not use a massage gun on an acute strain or treat massage as clearance to run or kick.", ["massage_gun"], "unknown", "side_specific", "unknown"),
    "quads_strain_isometric_wall_sit_mid_range": ("With your back supported against a stable wall and both feet planted, lower only into a comfortable partial squat and hold, then stand. Keep the knee angle and bodyweight demand fixed. No deeper squat, ball squeeze, added load or fatigue work.", ["wall"], "moderate", "not_applicable", "isometric"),
    "quads_strain_foam_roller_quad_sweep": ("After the acute period, only if your treating clinician has advised self-massage, gently roll comfortable quadriceps tissue. Avoid bruised or painful tissue and stop for pain. Do not roll an acute strain or treat rolling as readiness for loading.", ["foam_roller"], "unknown", "side_specific", "unknown"),
    "groin_strain_standing_cable_adduction": ("Hold stable support and move the affected leg slowly inward against a fixed light cable resistance through a comfortable range. Keep the trunk still. No speed, resistance increase or fatigue progression within this drill.", ["cable_machine"], "low", "side_specific", "mixed"),
    "chest_strain_isometric_wall_push_chest_height": ("Place both hands against a stable wall at chest height and gently press without moving the shoulders. Release between comfortable holds. Do not increase force, extend the hold to fatigue or add resisted movement within this drill.", ["wall"], "low", "not_applicable", "isometric"),
    "chest_strain_resistance_band_chest_fly": ("With a securely anchored light resistance band, slowly bring the arms together in front of the chest through a comfortable range, then return under control. Keep resistance and speed fixed. Avoid a forced chest stretch, increased tension or fatigue work.", ["resistance_band"], "low", "not_applicable", "mixed"),
    "shoulder_strain_wall_slides_with_foam_roller": ("Place the forearms on a foam roller against a wall. Slowly slide only through a comfortable range and return under control. Use no additional band or weight; do not force overhead range.", ["wall", "foam_roller"], "low", "side_specific", "mixed"),
    "shoulder_strain_landmine_shoulder_press": ("With a securely anchored landmine bar and an individually selected fixed load, slowly press through a comfortable range and lower under control. No load, tempo or range progression within this drill. This is resisted loading, not an early movement exercise.", ["landmine", "barbell"], "unknown", "side_specific", "mixed"),
    "shoulder_strain_isometric_wall_press_90_abduction": ("With the arm at shoulder height only if that position is comfortable, gently press against a stable wall without movement, then relax. Keep pressure fixed. Do not force the position or add resistance.", ["wall"], "low", "side_specific", "isometric"),
    "shoulder_strain_banded_y_raise": ("Using a fixed light resistance band, slowly raise the arms into a comfortable Y position and lower under control. Do not force overhead range, increase band tension or work to fatigue.", ["resistance_band"], "low", "side_specific", "mixed"),
    "bicep_strain_isometric_bicep_curl_hold_mid_range": ("Support the upper arm and hold the elbow in comfortable mid-flexion against gentle resistance from the other hand, then relax. Keep pressure fixed. No weights, dynamic curls or fatigue progression within this drill.", [], "low", "side_specific", "isometric"),
    "bicep_strain_band_resisted_eccentric_curl": ("With the upper arm supported and a fixed light band, use the other hand to help bend the elbow, then slowly lower against the band through a comfortable range. Keep band tension fixed. No extra repetitions to fatigue or speed work.", ["resistance_band"], "low", "side_specific", "eccentric"),
    "bicep_strain_cable_curl_with_fat_grip": ("With a fixed cable load and thick grip attachment, slowly bend and straighten the elbow through a comfortable range. Keep the upper arm still. Do not increase resistance, accelerate the movement or work to fatigue. Demand depends on the individually selected cable load.", ["cable_machine", "fat_grip"], "unknown", "side_specific", "mixed"),
    "bicep_strain_supinated_isometric_elbow_hold": ("Keep the upper arm supported, palm facing up and elbow in comfortable mid-flexion. Resist gently with the other hand without movement, then relax. Keep pressure fixed; no added load or fatigue work.", [], "low", "side_specific", "isometric"),
    "triceps_strain_isometric_wall_triceps_press": ("With the elbow comfortably bent and hand against a stable wall, gently try to straighten the elbow without movement, then relax. Keep pressure fixed. No longer fatigue holds or punching progression within this drill.", ["wall"], "low", "side_specific", "isometric"),
    "triceps_strain_overhead_band_triceps_extensions": ("Only if the overhead position is comfortable, slowly straighten and bend the elbow against a fixed light resistance band. Do not force end range, increase band resistance or work to fatigue. This is resisted loading, not early movement.", ["resistance_band"], "low", "side_specific", "mixed"),
    "triceps_strain_push_up_to_tabletop_flow": ("Place both hands on a stable raised table and perform a slow supported incline push-up through a comfortable elbow range, then return. Keep the support height fixed. Do not transition to floor work, a reverse tabletop or speed work.", ["table"], "moderate", "not_applicable", "mixed"),
    "triceps_strain_kettlebell_crush_press_light": ("Lie supported on your back and hold a fixed individually selected kettlebell with both hands. Slowly press and lower through a comfortable range while maintaining a gentle inward grip. No load increase or fatigue work; demand depends on the selected weight.", ["kettlebell"], "unknown", "not_applicable", "mixed"),
}


def repair_existing(bank, reviewed):
    """Keep identity/history, refresh review hashes after authorised source edits."""
    region_sources = {"calf": CALF, "hamstrings": HAM, "groin": GROIN, "quads": QUADS,
                      "chest": NHS, "bicep": ELBOW, "triceps": ELBOW, "shoulder": SHOULDER}
    tissues = {location: tissue for location, _, _, _, _, _, _, _, _, _, _, tissue in VARIANTS}
    tissues["chest"] = "pectoral muscles"
    for group in bank:
        if group["type"] != "strain":
            continue
        for drill in group["drills"]:
            key = drill["id"].removesuffix("_2")
            if key not in FIXED:
                continue
            old = reviewed[drill["id"]]
            history = old.get("source_history", [])
            if not history:
                history = [{field: old[field] for field in ("source_hash", "name", "notes")}]
            instructions, equipment, load, side, contraction = FIXED[key]
            drill.update(notes=instructions + " Stop if pain or symptoms worsen during or after the work.",
                         rehab_stage="load", equipment=equipment, impact="none", load=load,
                         velocity="low", target_regions=[group["location"]],
                         laterality_applicability=side, contraction_type=contraction,
                         sport_specificity="general_rehab", contact_level="none",
                         target_tissues=[tissues[group["location"]]],
                         function="recovery_downregulation" if contraction == "unknown" else "activation",
                         dose=None, pain_ceiling=None, allowed_severities=None,
                         progress_when=None, regress_when=None, stop_when=None,
                         evidence_notes="Manual review of fixed exercise mechanics. General injury guidance: "
                         + region_sources[group["location"]]
                         + ". This source does not establish a dose or efficacy for this exact equipment variant. "
                         + "Not an active prescription; LOAD requires separately sourced and evaluable pathway transitions. "
                         + "Unknown load remains unknown when external weight or manual pressure is not specified.")
            if key == "triceps_strain_push_up_to_tabletop_flow":
                drill["name"] = "Supported incline push-up"
            record = _fresh_record(group["location"], "strain", drill)
            record.update(review_state="reviewed", source_history=history,
                          proposed={field: drill[field] for field in REVIEW_FIELDS})
            reviewed[drill["id"]] = record


def main():
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    bank, ledger, raw = read("rehab_bank.json"), read("rehab_metadata_review.json"), read("rehab_pathways.json")
    catalog = load_pathway_catalog()
    indexed = {d["id"]: (g, d) for g in bank for d in g["drills"]}
    reviewed = {r["drill_id"]: r for r in ledger}
    repair_existing(bank, reviewed)
    profiles = []
    for location, region, original_id, evidence, name, instructions, function, equipment, load, side, contraction, tissue in VARIANTS:
        source_group, original = indexed[original_id]
        original_hash = source_hash(drill_id=original_id, location=source_group["location"],
                                    injury_type=source_group["type"], name=original["name"], notes=original["notes"])
        history = reviewed[original_id].get("source_history", [])
        if history:
            original_hash = history[0]["source_hash"]
        group = next(g for g in bank if g["location"] == location and g["type"] == "strain")
        calm_instructions = (
            "Protect the strained area and avoid activity that aggravates it. During the first 2 to 3 days, rest from exercise that loads it. Use comfortable everyday movement without forcing a stretch. Avoid massage and heat in the early period. Seek assessment for severe or worsening pain, swelling or inability to use the area."
        )
        prescriptions = []
        for stage in ("calm", "restore"):
            identity = f"{region}_strain_recovery_support" if stage == "calm" else f"{region}_strain_reviewed_restore"
            sources = [NHS] if stage == "calm" else [NHS, evidence]
            text = calm_instructions if stage == "calm" else instructions
            drill = deepcopy(original)
            drill.update(
                id=identity, name=f"{region.title()} strain recovery support" if stage == "calm" else name,
                notes=text, rehab_stage=stage,
                function="recovery_downregulation" if stage == "calm" else function,
                equipment=[] if stage == "calm" else equipment,
                impact="none", load="minimal" if stage == "calm" else load, velocity="low",
                target_regions=list(dict.fromkeys([location, region])),
                target_tissues=[tissue], laterality_applicability="not_applicable" if stage == "calm" else side,
                contraction_type="unknown" if stage == "calm" else contraction,
                sport_specificity="general_rehab", contact_level="none",
                # No numerical dose, pain ceiling, recovery criterion or diagnosis grade inferred.
                dose=None, pain_ceiling=None, allowed_severities=None,
                progress_when=None, regress_when=None, stop_when=None,
                evidence_notes="Sources: " + ", ".join(sources) + ". Fixed baseline variant; no numeric dose. "
                    + (f"Movement derived from {original_id}; original source hash {original_hash}. " if stage == "restore" else "")
                    + "Low/moderate eligibility is the existing product safety gate, not a diagnosed clinical grade. Scheduling is product allocation cadence, not a clinical dose.",
            )
            group["drills"] = [d for d in group["drills"] if d["id"] != identity] + [drill]
            record = _fresh_record(location, "strain", drill)
            record.update(review_state="reviewed", movement_archetype="manual_recovery" if stage == "calm" else "isometric" if contraction == "isometric" else "mobility_rom" if function == "mobility" else "bodyweight_strength",
                          proposed={field: drill[field] for field in REVIEW_FIELDS})
            reviewed[identity] = record
            # Use the repaired, existing exercises where their actual movement
            # matches the sourced baseline, preserving its original identity.
            if stage == "restore" and region in {"hamstring", "calf", "groin"}:
                history = reviewed[original_id].get("source_history", [])
                if not history:
                    history = [{field: reviewed[original_id][field] for field in ("source_hash", "name", "notes")}]
                original.update({k: deepcopy(v) for k, v in drill.items() if k != "id"})
                original["evidence_notes"] = "Sources: " + ", ".join(sources) + ". Reviewed fixed baseline; no numerical dose or automatic advanced-stage clearance."
                record = _fresh_record(source_group["location"], "strain", original)
                record.update(review_state="reviewed", source_history=history,
                              proposed={field: original[field] for field in REVIEW_FIELDS})
                reviewed[original_id] = record
                if region == "calf":
                    duplicate_id = original_id + "_2"
                    duplicate_group, duplicate = indexed[duplicate_id]
                    previous = reviewed[duplicate_id]
                    duplicate_history = previous.get("source_history", []) or [
                        {field: previous[field] for field in ("source_hash", "name", "notes")}]
                    duplicate.update({k: deepcopy(v) for k, v in original.items() if k != "id"})
                    duplicate_record = _fresh_record(duplicate_group["location"], "strain", duplicate)
                    duplicate_record.update(review_state="reviewed", source_history=duplicate_history,
                                            proposed={field: duplicate[field] for field in REVIEW_FIELDS})
                    reviewed[duplicate_id] = duplicate_record
            prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage,
                                      instructions=text, dose=None, allowed_severities=["low", "moderate"],
                                      stop_when=["Stop if movement is painful or symptoms worsen during or after the work.",
                                                 "Seek assessment for severe or worsening pain, swelling or inability to use the area."],
                                      sources=sources))
            if stage == "restore" and region in {"hamstring", "calf", "groin"}:
                prescriptions[-1].update(drill_id=original_id, bank_hash=content_hash(original))
                # These aliases were introduced only in this unmerged rollout.
                # Prefer the repaired original bank identity instead of duplicating it.
                group["drills"] = [d for d in group["drills"] if d["id"] != identity]
        registry = LOCATION_REGISTRY.get(region, {})
        restrictions = list(dict.fromkeys([location, region, registry.get("exclusion_region", region),
                                          *registry.get("secondary_exclusion_regions", [])]))
        profile = dict(policy_id=f"{region}_strain", version=1, pathway_family="muscle_strain", region=region,
                       injury_type="strain", evidence_sources=[NHS, evidence], prescriptions=prescriptions,
                       blocked_regions=restrictions, blocked_tags=[], contact_limit="none",
                       live_stages=["calm", "restore"], transition_overrides={})
        draft = compose_policy(catalog, profile)
        profile.update(status="active", activation="live", content_hash=policy_review_hash(draft),
                       prescriptions=[p.model_dump() for p in draft.prescriptions])
        profiles.append(profile)
    # Review the already sourced chest routines without changing their bank or policy hashes.
    chest = next(p for p in raw["profiles"] if p["policy_id"] == "chest_strain")
    for prescription in chest["prescriptions"]:
        identity = prescription["drill_id"]
        drill = indexed[identity][1]
        reviewed[identity] = {**reviewed[identity], "review_state": "reviewed",
                              "proposed": {field: drill[field] for field in REVIEW_FIELDS}}
    ids = {p["policy_id"] for p in profiles}
    raw["profiles"] = [p for p in raw["profiles"] if p["policy_id"] not in ids] + profiles
    debt = read("rehab_bank_duplicate_debt.json")
    # Preserve the four pre-existing calf duplicate allowances, with their new
    # stage/name keys. No new duplicate or extra copy is grandfathered.
    for row in debt["duplicates"]:
        if row["location"] == "calf" and row["type"] == "strain":
            drill = next(d for g in bank for d in g["drills"]
                         if d["id"].startswith("calf_strain_")
                         and (d["name"] == row["name"] or
                              row["name"] == "Double-Leg Calf Raises" and d["id"] == "calf_strain_double_leg_calf_raises"))
            row.update(name=drill["name"], rehab_stage=drill["rehab_stage"])
    for filename, value in (("rehab_bank.json", bank), ("rehab_pathways.json", raw),
                            ("rehab_metadata_review.json", [reviewed[d["id"]] for g in bank for d in g["drills"] if d["id"] in reviewed]),
                            ("rehab_bank_duplicate_debt.json", debt)):
        (ROOT / "data" / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
