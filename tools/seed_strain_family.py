"""Reproduce the reviewed baseline strain rollout; preserve legacy source records.

Run only after reviewing docs/strain-family-rollout.md. This is curated content,
not automatic clinical approval. The original variable-demand drills are retained.
"""
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
]


def main():
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    bank, ledger, raw = read("rehab_bank.json"), read("rehab_metadata_review.json"), read("rehab_pathways.json")
    catalog = load_pathway_catalog()
    indexed = {d["id"]: (g, d) for g in bank for d in g["drills"]}
    reviewed = {r["drill_id"]: r for r in ledger}
    profiles = []
    for location, region, original_id, evidence, name, instructions, function, equipment, load, side, contraction, tissue in VARIANTS:
        source_group, original = indexed[original_id]
        original_hash = source_hash(drill_id=original_id, location=source_group["location"],
                                    injury_type=source_group["type"], name=original["name"], notes=original["notes"])
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
            prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage,
                                      instructions=text, dose=None, allowed_severities=["low", "moderate"],
                                      stop_when=["Stop if movement is painful or symptoms worsen during or after the work.",
                                                 "Seek assessment for severe or worsening pain, swelling or inability to use the area."],
                                      sources=sources))
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
    for filename, value in (("rehab_bank.json", bank), ("rehab_pathways.json", raw),
                            ("rehab_metadata_review.json", [reviewed[d["id"]] for g in bank for d in g["drills"] if d["id"] in reviewed])):
        (ROOT / "data" / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
