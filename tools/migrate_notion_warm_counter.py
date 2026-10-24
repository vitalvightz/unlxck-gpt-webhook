"""Migrate the warm follow-up formulas to one shared signup nudge counter.

Only remove the legacy onboarding counter from expressions that double-count it.
The worker owns scheduling and sendable copy; cold/Activated formulas stay intact.
"""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError

import sync_notion_followups as sync

FIELDS = ("Warm Next DM", "Next DM to Copy", "Outreach Next Step")

# The two actual existing formula variants differ in whitespace.
LEGACY_TERMS = (
    '+ if(prop("Onboarding Nudges Sent") == "1", 1, if(prop("Onboarding Nudges Sent") == "2", 2, 0))',
    '+if(prop("Onboarding Nudges Sent") == "1",1,if(prop("Onboarding Nudges Sent") == "2",2,0))',
)


def formula_changes(properties):
    changes = {}
    for name in FIELDS:
        original = properties[name]["formula"]["expression"]
        updated = original
        for legacy in LEGACY_TERMS:
            updated = updated.replace(legacy, "")
        if updated != original:
            changes[name] = {"formula": {"expression": updated}}
    return changes


def migrate(apply=False, backup=None):
    path = f"/data_sources/{sync.DATA_SOURCE_ID}"
    schema = sync.request("GET", path)
    changes = formula_changes(schema["properties"])
    print("Formula migration fields: " + (", ".join(changes) if changes else "none"))
    if not apply or not changes:
        return
    if not backup:
        raise ValueError("--backup is required when applying")
    # Allow the existing backup from a failed attempt, but never overwrite it.
    snapshot = Path(backup)
    if snapshot.exists():
        saved = json.loads(snapshot.read_text())
        if not all(name in saved for name in changes):
            raise ValueError("Existing backup is incomplete; use a new backup path")
        if any(saved[name]["formula"] != schema["properties"][name]["formula"] for name in changes):
            raise ValueError("Existing backup does not match live formulas; use a new backup path")
        print("Reusing existing verified backup")
    else:
        with snapshot.open("x") as target:
            json.dump({name: schema["properties"][name] for name in FIELDS}, target, indent=2)
    fresh = sync.request("GET", path)
    if any(fresh["properties"][name]["formula"] != schema["properties"][name]["formula"] for name in changes):
        raise RuntimeError("Formulas changed since preview; aborting")
    try:
        sync.request("PATCH", path, {"properties": changes})
    except HTTPError as exc:
        # Notion's JSON error body identifies the rejected property/expression.
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion rejected formula update (HTTP {exc.code}): {body[:3000]}") from exc
    verified = sync.request("GET", path)
    if any(verified["properties"][name]["formula"] != patch["formula"] for name, patch in changes.items()):
        raise RuntimeError("Formula read-back differs; keep 3B sends disabled")
    print("Verified formula migration")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup")
    args = parser.parse_args()
    migrate(args.apply, args.backup)
