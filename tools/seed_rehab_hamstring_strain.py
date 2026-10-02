"""Review two existing hamstring drills and rebuild the hamstring strain policy.

Deterministic and idempotent. Only the two drills named below are marked
``reviewed`` in the metadata ledger; every other hamstring entry stays
``needs_review``. Drill identity, name and notes are preserved, so each record
keeps the source hash it was reviewed against. Reviewed mechanical fields are
written through the existing applicator. The bank-side criteria fields mirror
the policy prescription exactly (self-paced, no numerical pain ceiling), the
same convention as the chest/ankle pilot. Other policies are left untouched.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fightcamp.rehab_clinical import ClinicalPolicy, content_hash, policy_review_hash  # noqa: E402
from fightcamp.rehab_schema import PAIN_CEILING_UNRESTRICTED  # noqa: E402
from tools.apply_rehab_metadata_review import apply_reviews  # noqa: E402
from tools.rehab_metadata_review_lib import (  # noqa: E402
    FLAG_VARIABLE_DEMAND, REVIEW_STATE_REVIEWED, iter_msk_drills, render_bank, render_ledger,
    source_hash,
)

NHS = "https://www.nhs.uk/conditions/hamstring-injury/"
CPG = "https://www.jospt.org/doi/10.2519/jospt.2022.0301"
HEIDERSCHEIT = "https://pubmed.ncbi.nlm.nih.gov/20118524/"
ERICKSON_SHERRY = "https://pmc.ncbi.nlm.nih.gov/articles/PMC6189266/"

POLICY_ID, VERSION = "hamstring_strain", 1
STOP = ["Stop if pain prevents comfortable movement or symptoms worsen.",
        "Seek help for severe or worsening pain, a pop at the time of injury, heavy bruising or difficulty walking."]
REGRESS = ["Symptoms worsen: return to comfortable movement and recovery support."]

# (drill_id, stage, archetype, flags, mechanical review, instructions, sources, gap, priority)
REVIEWS = [
    ("hamstring_unspecified_standing_bent_knee_stretch_active_rom", "calm", "mobility_rom", [FLAG_VARIABLE_DEMAND],
     dict(function="mobility", load="minimal", laterality_applicability="side_specific", contraction_type="mixed"),
     "After the first 2 to 3 days, once pain has started to settle, stand with support and gently move the affected "
     "leg through a comfortable bent-knee hamstring range. Move slowly; do not bounce, swing, force the stretch or add "
     "rotation. Stop well before pain.",
     [NHS, CPG], 1, 0),
    ("hamstring_unspecified_standing_hamstring_isometric_against_wall", "restore", "isometric", [FLAG_VARIABLE_DEMAND],
     dict(function="isometric_analgesia", load="low", laterality_applicability="side_specific", contraction_type="isometric"),
     "When walking is comfortable, stand with support and gently press the affected heel back into a wall at a "
     "comfortable knee angle, then relax. Use a light, pain-free effort only. Do not add opposite-leg movements.",
     [HEIDERSCHEIT, ERICKSON_SHERRY, CPG], 3, 5),
]
# No bundle: the only complementary RESTORE candidate, the double-leg bridge
# hold, is bilateral_only. The exposure contract cannot attribute its
# completion to a one-sided hamstring, so it stays needs_review.
BUNDLE = {}


def _review_record(record: dict, stage: str, archetype: str, flags: list, mechanical: dict, sources: list) -> dict:
    proposed = dict(record["proposed"], rehab_stage=stage, equipment=[], impact="none", velocity="low",
                    target_regions=["hamstring"], target_tissues=["hamstring muscle group"],
                    sport_specificity="general_rehab", contact_level="none",
                    evidence_notes="Reviewed for hamstring strain " + stage.upper() + " only. Sources: " + ", ".join(sources)
                    + ". Base movement only; the progression in the legacy notes is not reviewed. Self-paced; no numerical dose.",
                    **mechanical)
    return {**record, "movement_archetype": archetype, "proposed": proposed, "flags": flags,
            "review_state": REVIEW_STATE_REVIEWED}


def main():
    bank_path, ledger_path = ROOT / "data/rehab_bank.json", ROOT / "data/rehab_metadata_review.json"
    policy_path = ROOT / "data/rehab_clinical_policies.json"
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    drills = {str(d.get("id")): (loc, kind, d) for _g, _i, loc, kind, d in iter_msk_drills(bank)}
    by_id = {r["drill_id"]: i for i, r in enumerate(ledger)}
    prescriptions = []
    for identity, stage, archetype, flags, mechanical, instructions, sources, gap, priority in REVIEWS:
        location, kind, drill = drills[identity]
        if (location, kind) != ("hamstring", "unspecified"):
            raise ValueError(f"unexpected group for {identity}")
        record = ledger[by_id[identity]]
        current = source_hash(drill_id=identity, location=location, injury_type=kind, name=drill.get("name"),
                              notes=drill.get("notes", ""))
        if record["source_hash"] != current:
            raise ValueError(f"source changed since review: {identity}")
        ledger[by_id[identity]] = _review_record(record, stage, archetype, flags, mechanical, sources)
    bank, _applied, stale = apply_reviews(bank, ledger)
    if stale:
        raise ValueError(f"stale reviews: {stale}")
    drills = {str(d.get("id")): d for _g, _i, _loc, _kind, d in iter_msk_drills(bank)}
    for identity, stage, _archetype, _flags, _mechanical, instructions, sources, gap, priority in REVIEWS:
        drill = drills[identity]
        drill.update(dose={}, pain_ceiling=PAIN_CEILING_UNRESTRICTED, allowed_severities=["low", "moderate"],
                     progress_when=[], regress_when=REGRESS, stop_when=STOP)
        prescriptions.append(dict(drill_id=identity, bank_hash=content_hash(drill), stage=stage, instructions=instructions,
                                  dose=None, allowed_severities=["low", "moderate"], stop_when=STOP, frequency="daily",
                                  minimum_gap_days=gap, priority=priority, sources=sources))
    draft = ClinicalPolicy.model_validate(dict(
        policy_id=POLICY_ID, version=VERSION, region="hamstring", injury_type="strain",
        evidence_sources=list(dict.fromkeys(s for p in prescriptions for s in p["sources"])),
        prescriptions=prescriptions, blocked_regions=["hamstring"], contact_limit="none", stage_bundles=BUNDLE))
    policy = {**draft.model_dump(), "status": "active", "activation": "live", "content_hash": policy_review_hash(draft)}
    existing = json.loads(policy_path.read_text(encoding="utf-8"))["policies"] if policy_path.exists() else []
    policies = [p for p in existing if p["policy_id"] != POLICY_ID] + [policy]
    bank_path.write_text(render_bank(bank), encoding="utf-8")
    ledger_path.write_text(render_ledger(ledger), encoding="utf-8")
    policy_path.write_text(json.dumps(dict(schema_version=2, policies=policies), ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()
