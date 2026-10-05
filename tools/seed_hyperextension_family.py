"""Protected hyperextension profiles within the existing family catalog.

No injured-joint movement is activated without captured structural stability
and individual protection status. Legacy movements remain unreviewed inventory.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fightcamp.rehab_clinical import compose_policy, content_hash, load_pathway_catalog, policy_review_hash  # noqa: E402
from tools.seed_tendon_family import mark_reviewed  # noqa: E402

NHS = "https://www.nhs.uk/conditions/sprains-and-strains/"
TOE = "https://www.orthoinfo.org/diseases--conditions/turf-toe/"
FINGERS = "https://www.guysandstthomas.nhs.uk/health-information/volar-plate-injuries-finger"
ELBOW = "https://ruh.nhs.uk/patients/patient_information/ORT047_Advice_after_a_soft_tissue_injury_of_the_elbow.pdf"
HAND_WRIST = "https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-wrist-hand/"
SHOULDER = "https://www.gatesheadhealth.nhs.uk/resources/shoulder-injury/"

# Regional advice is intentionally distinct. The big-toe source establishes
# why grading/stability matter; its taping, footwear and return protocol are
# not generalized to every toe in the canonical region.
PROFILES = {
    "toe": dict(source=TOE, tissue="toe joint region",
        guidance="Protect the affected toe from being bent backwards again. Pause provoking push-off, tiptoe work, running and jumping. Rest the foot in a comfortable supported position. Follow any individually prescribed footwear, walking support or weight-bearing restriction without changing it. The affected toe, joint stability and injury grade need assessment before toe curls, stretching or loaded forefoot work; this guidance does not diagnose turf toe."),
    "fingers": dict(source=FINGERS, tissue="finger joint region",
        guidance="Protect the injured finger from being pulled or bent backwards. Avoid gripping against resistance, catching impacts and contact work. Rest the hand comfortably supported. Follow any hand-therapist splint or strapping instructions exactly; do not change the finger position, undo the splint for app exercises or decide when to stop wearing it. Finger exercises need the assessed injury and individual protection plan; no automatic stretching or finger holds are prescribed."),
    "elbow": dict(source=ELBOW, tissue="elbow joint region",
        guidance="Protect the elbow from repeat over-straightening. Pause pressing, throwing, forceful lockout and resisted elbow work. Support the arm comfortably at rest and follow any individually prescribed sling or movement restriction. Do not test stability, push into full extension or begin wall presses. The hospital movement advice assumes an assessed soft-tissue injury without broken bones; an app hyperextension label does not establish that assessment."),
    "wrist": dict(source=HAND_WRIST, tissue="wrist joint region",
        guidance="Protect the wrist from being bent backwards again and from weight through the palm or knuckles. Pause pushing, loaded wrist extension and heavy grip work. Rest the forearm and hand comfortably supported. Follow any individually prescribed splint and movement restriction; do not remove or taper protection because symptoms improve. Assessment of the injured wrist and its stability is needed before stretching, push-ups or resistance work."),
    "hand": dict(source=HAND_WRIST, tissue="hand joint region",
        guidance="Protect the injured hand from repeated backward bending, forceful gripping and contact impacts. Support the hand comfortably at rest and avoid using it to bear body weight. Follow any individually prescribed hand protection and movement restrictions. The exact injured joint and safe movement range need assessment; do not pull fingers backwards, perform backhand wall crawls or follow a generic wrist or finger exercise protocol."),
    "shoulder": dict(source=SHOULDER, tissue="shoulder joint region",
        guidance="Protect the shoulder from repeat backward overstretching. Pause provoking reaching behind the body, bottom-range pressing, heavy lifting and contact work. Support the arm comfortably at rest and follow any individually prescribed sling or movement restriction without changing it. Do not test shoulder stability, force range or introduce band presses. Movement rehabilitation needs the assessed injury and individual restrictions; this guidance does not establish that the joint is stable."),
}
STOP = ("Stop automatic rehab and seek assessment for giving way, locking, suspected instability, deformity, "
        "major swelling or loss of joint use. Seek urgent help for altered sensation, a cold or blue limb, "
        "or symptoms suggesting a fracture, dislocation or tear. Follow clinician restrictions. "
        "If symptoms worsen, stop the provoking activity and seek assessment rather than testing the joint.")


def main():
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))

    bank, ledger, raw = read("rehab_bank.json"), read("rehab_metadata_review.json"), read("rehab_pathways.json")
    reviewed = {r["drill_id"]: r for r in ledger}
    catalog = load_pathway_catalog()
    profiles = []
    for region, config in PROFILES.items():
        groups = [g for g in bank if (g["location"], g["type"]) == (region, "hyperextension")]
        group = groups[0]  # Only real inventory regions may receive a profile.
        identity = f"{region}_hyperextension_recovery_support"
        original = next((d for g in groups for d in g["drills"] if d["id"] == identity), group["drills"][0])
        drill = deepcopy(original)
        instructions = config["guidance"] + " " + STOP
        sources = [config["source"], NHS]
        drill.update(id=identity, name=f"{region.title()} hyperextension protection guidance", notes=instructions,
                     rehab_stage="calm", function="recovery_downregulation", equipment=[], load="minimal",
                     impact="none", velocity="low", target_regions=[region], target_tissues=[config["tissue"]],
                     laterality_applicability="not_applicable", contraction_type="unknown",
                     sport_specificity="general_rehab", contact_level="none", dose=None, pain_ceiling=None,
                     allowed_severities=None, progress_when=None, regress_when=None, stop_when=None,
                     evidence_notes="Sources: " + ", ".join(sources) + ". Protective advice only, not an injured-joint exercise, diagnosis, healing claim or clearance. No dose, pain ceiling, severity grading, support duration, ROM target or progression threshold inferred. Product low/moderate eligibility and scheduled cadence are retained. Structural stability and individual protection status are not captured, so RESTORE and advanced stages remain closed.")
        for target in groups:
            target["phase_progression"] = "GPP → SPP → TAPER"
            target["drills"] = [d for d in target["drills"] if d["id"] != identity]
        group["drills"].append(drill)
        reviewed[identity] = mark_reviewed(group, drill, reviewed.get(identity))
        profile = dict(policy_id=f"{region}_hyperextension", version=1, region=region, injury_type="hyperextension",
                       pathway_family="hyperextension_or_joint_trauma", evidence_sources=sources,
                       prescriptions=[dict(drill_id=identity, bank_hash=content_hash(drill), stage="calm",
                           instructions=instructions, dose=None, allowed_severities=["low", "moderate"],
                           sources=sources, stop_when=[STOP])],
                       blocked_regions=[region], blocked_tags=[], contact_limit="none",
                       live_stages=["calm"], transition_overrides={})
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
