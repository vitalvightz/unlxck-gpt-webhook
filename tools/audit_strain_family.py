"""Read-only inventory of the entire strain family, including legacy demand debt."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fightcamp.injury_location_registry import canonicalize_location_from_registry  # noqa: E402


def audit(bank, ledger, profiles):
    records = {r["drill_id"]: r for r in ledger}
    regions = defaultdict(list)
    for group in bank:
        if group["type"] != "strain":
            continue
        region = canonicalize_location_from_registry(group["location"])
        for drill in group["drills"]:
            review = records[drill["id"]]
            regions[region].append({
                "drill_id": drill["id"], "bank_location": group["location"],
                "name": drill["name"], "notes": drill["notes"],
                "source_hash": review["source_hash"], "review_state": review["review_state"],
                "flags": review["flags"],
                # The existing heuristic misses many explicit camp progressions.
                "mixed_camp_demand": "→" in drill["notes"],
            })
    result = {}
    for region, drills in sorted(regions.items()):
        duplicate_keys = defaultdict(list)
        for drill in drills:
            duplicate_keys[(drill["name"], drill["notes"])].append(drill["drill_id"])
        result[region] = {
            "count": len(drills),
            "review_states": dict(Counter(d["review_state"] for d in drills)),
            "live_profiles": [p["policy_id"] for p in profiles
                              if p["injury_type"] == "strain" and p.get("activation") == "live"
                              and canonicalize_location_from_registry(p["region"]) == region],
            "exact_duplicates": [ids for ids in duplicate_keys.values() if len(ids) > 1],
            "drills": drills,
        }
    return result


if __name__ == "__main__":
    def read(name):
        return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    print(json.dumps(audit(read("rehab_bank.json"), read("rehab_metadata_review.json"),
                           read("rehab_pathways.json")["profiles"]), indent=2))
