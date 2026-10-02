"""Rebuild the five sourced baseline routines and their policy hashes."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fightcamp.rehab_clinical import ClinicalPolicy, content_hash, policy_review_hash  # noqa: E402
from fightcamp.rehab_schema import PAIN_CEILING_UNRESTRICTED  # noqa: E402

NHS = "https://www.nhs.uk/conditions/sprains-and-strains/"
ANKLE = "https://services.eastcheshire.nhs.uk/physiotherapy-service/self-help/ankle-and-foot-pain-physiotherapy-self-help"
LEAFLET = "https://www.whittington.nhs.uk/mini-apps/leaflet/Default.asp?id=53&print=1"

ROUTINES = [
    ("chest", "chest_strain_recovery_support", "Chest strain recovery support", "calm", "recovery_downregulation",
     "Protect the strained area and avoid movements that aggravate it. During the first 2 to 3 days, rest from exercise that loads it. Use comfortable everyday movement; do not force a stretch or add resisted chest work.", [NHS], 1, 0),
    ("chest", "chest_strain_comfortable_movement", "Comfortable chest-region movement", "restore", "mobility",
     "When pain no longer stops movement, gently move your shoulder and arm through a comfortable range. Go at your own pace and stop before pain prevents movement. Avoid forced chest stretches, resisted chest flies and surgical-repair routines.", [NHS], 1, 5),
    ("ankle", "ankle_sprain_gentle_movement", "Gentle seated ankle movement", "calm", "mobility",
     "Once the ankle is less painful, sit with the foot supported and gently move it up and down or trace the alphabet. Start with a small comfortable amount and build gradually. Keep within a comfortable range; do not force movement.", [NHS, LEAFLET], 1, 0),
    ("ankle", "ankle_sprain_supported_balance", "Supported ankle balance", "restore", "control",
     "When standing and weight bearing are comfortable, practise balancing on the affected leg on firm ground, close to a stable counter for support. Start with a short comfortable attempt and build gradually. Keep support available; do not use a cushion or close your eyes.", [LEAFLET], 1, 5),
    ("ankle", "ankle_sprain_heel_lowering", "Supported heel lowering", "restore", "tendon_loading",
     "When weight bearing and gentle calf movement are comfortable, use a stable support and practise controlled heel lowering as shown in the linked ankle rehabilitation guidance. Work at your own pace, up to 2 sets on alternate days. The source gives no repetition target; stop before symptoms worsen.", [ANKLE], 2, 10),
]


def main():
    path = ROOT / "data/rehab_bank.json"
    bank = json.loads(path.read_text(encoding="utf-8"))
    policies = []
    for region, kind in [("chest", "strain"), ("ankle", "sprain")]:
        group = next(g for g in bank if g.get("location") == region and g.get("type") == kind)
        prescriptions = []
        for area, identity, name, stage, function, instructions, sources, gap, priority in ROUTINES:
            if area != region:
                continue
            stop = ["Stop if pain prevents comfortable movement or symptoms worsen.",
                    "Seek help for severe or worsening pain, swelling or inability to use the area."]
            drill = dict(id=identity, name=name, notes=instructions, rehab_stage=stage, function=function,
                         equipment=[], dose={}, impact="none", load="minimal" if stage == "calm" else "low",
                         velocity="low", pain_ceiling=PAIN_CEILING_UNRESTRICTED, allowed_severities=["low", "moderate"],
                         progress_when=[], regress_when=["Symptoms worsen: return to comfortable movement and recovery support."],
                         stop_when=stop, target_regions=[area],
                         laterality_applicability="side_specific" if area == "ankle" and stage == "restore" else "not_applicable",
                         target_tissues=[area + " region soft tissues"],
                         contraction_type="unknown" if function == "recovery_downregulation" else "mixed",
                         sport_specificity="general_rehab", contact_level="none",
                         evidence_notes="Sources: " + ", ".join(sources) + ". Self-paced; no starting numerical dose is prescribed.")
            group["drills"] = [d for d in group["drills"] if d["id"] != identity] + [drill]
            prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage,
                                      instructions=instructions, dose=None, allowed_severities=["low", "moderate"],
                                      stop_when=stop, frequency="daily", minimum_gap_days=gap, priority=priority, sources=sources))
        draft = ClinicalPolicy.model_validate(dict(policy_id=region + "_" + kind, version=4 if region == "ankle" else 3, region=region,
            injury_type=kind, evidence_sources=list(dict.fromkeys(s for p in prescriptions for s in p["sources"])),
            prescriptions=prescriptions, blocked_regions=[region], contact_limit="none",
            stage_bundles={"restore": ["ankle_sprain_supported_balance", "ankle_sprain_heel_lowering"]} if region == "ankle" else {}))
        policies.append({**draft.model_dump(), "status": "active", "activation": "live", "content_hash": policy_review_hash(draft)})
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "data/rehab_clinical_policies.json").write_text(
        json.dumps(dict(schema_version=2, policies=policies), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
