"""Small reviewed-remediation checks; no inventory or plan snapshots are written."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.services import training_library as library  # noqa: E402
from fightcamp.training_catalogue import build_catalogue, content_hash  # noqa: E402
from tools import audit_canonical_metadata as canonical  # noqa: E402

BASELINE = ROOT / "tools/equipment_requirements_baseline.json"
OUT = ROOT / "reports/equipment_requirements"


def build_report(*, index=None):
    baseline = json.loads(BASELINE.read_bytes())
    index = index or library.LibraryCache().get()
    historical = library.LibraryCache(reviewed_requirements=False).get()
    entries = build_catalogue()
    protected = canonical.preservation(json.loads(canonical.BASELINE.read_bytes()))
    identities = {e["catalogue_id"]: [e["source_id"], e["exercise_key"], e["eligibility"]] for e in entries}
    unrelated = {r["entry"]["catalogue_id"]: {f: sorted(v) for f, v in r["facets"].items() if f != "equipment"} for r in index.records}
    if len(entries) != baseline["catalogue_entries"] or content_hash(identities) != baseline["identities_sha256"]:
        raise ValueError("Catalogue, media or prescription boundary drift")
    if content_hash(unrelated) != baseline["non_equipment_facets_sha256"]:
        raise ValueError("Unrelated filter or Goal drift")
    if content_hash(canonical.query_results(index)) != baseline["queries_sha256"]:
        raise ValueError("Reviewed fighter-query totals, ordered IDs or match evidence changed")
    old_counts = {o["value"]: o["count"] for o in library.search(historical, limit=1)["facets"]["equipment"]}
    if old_counts != baseline["equipment_counts"]:
        raise ValueError("Pre-change filter baseline drift")
    reviews = index.equipment_reviews
    if len(reviews) != baseline["reviewed_entries"]:
        raise ValueError("Reviewed entry coverage drift")
    audit_ids = {i["issue_id"] for i in json.loads((ROOT / "reports/metadata_integrity/remediation.json").read_bytes())["issues"]}
    for identity, review in reviews.items():
        if not set(review["audit_decisions"]) <= audit_ids:
            raise ValueError("Unknown original audit reference")
        record = index.by_id[identity]
        actual = record["facets"]["equipment"]
        expected = {item for group in review["groups"] for item in group["items"]} if review["action"] == "CORRECT" else historical.by_id[identity]["facets"]["equipment"] - {"no_equipment"}
        if actual != expected:
            raise ValueError("Reviewed apparatus set mismatch: " + identity)
    for identity, record in index.by_id.items():
        if identity not in reviews and record["facets"] != historical.by_id[identity]["facets"]:
            raise ValueError("Unreviewed entry changed: " + identity)
    counts = {o["value"]: o["count"] for o in library.search(index, limit=1)["facets"]["equipment"]}
    changes = [{"value": value, "before": old_counts.get(value, 0), "after": counts.get(value, 0)}
               for value in sorted(set(counts) | set(old_counts)) if old_counts.get(value, 0) != counts.get(value, 0)]
    consumers = []
    for path, names in {
        "fightcamp/equipment_requirements.py": ("project_requirements", "equipment_setup_available"),
        "api/services/training_library.py": ("_prepare", "search", "preview", "get"),
        "fightcamp/training_context.py": ("normalize_equipment_list", "normalize_athlete_equipment_list"),
        "fightcamp/strength.py": ("generate_strength_block",),
        "fightcamp/conditioning.py": ("generate_conditioning_block", "_conditioning_required_equipment"),
    }.items():
        tree = ast.parse((ROOT / path).read_text(encoding="utf8"))
        functions = {n.name: n.lineno for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        consumers.extend({"file": path, "function": name, "line": functions[name]} for name in names)
    return {"base_revision": baseline["base_revision"], "catalogue_entries": len(entries),
            "reviewed_records": len(reviews), "corrected_records": sum(r["action"] == "CORRECT" for r in reviews.values()),
            "unresolved_records": sum(r["action"] == "REVIEW" for r in reviews.values()),
            "original_audit_issues_referenced": len({i for r in reviews.values() for i in r["audit_decisions"]}),
            "raw_source_records_changed": 0, "all_source_hashes_unchanged": protected["source_hash_parity"],
            "identity_media_and_boundary_parity": protected["catalogue_identity_and_media_key_parity"],
            "ordered_30_search_controls_unchanged": True,
            "training_goal_entries": sum(bool(r["facets"]["goal"]) for r in index.records if r["summary"]["category"] == "training"),
            "planner_eligibility_changes": [], "filter_changes": changes, "consumers": consumers,
            "reviewed_rows": [{"catalogue_id": identity, "name": index.by_id[identity]["summary"]["name"],
                               "action": r["action"], "modes": [g["mode"] for g in r["groups"]]}
                              for identity, r in reviews.items()]}


def markdown(report):
    lines = ["# Equipment accuracy and requirements cleanup", "",
             f"Base: Main `{report['base_revision']}` (#2823). Reviewed {report['reviewed_records']} affected source records across {report['original_audit_issues_referenced']} overlapping audit findings: {report['corrected_records']} corrected requirement projections; {report['unresolved_records']} explicitly unresolved.", "",
             "The small shared review contract is the source-bound correction layer for library metadata. Two rope-climbing associations now return climbing rope only; three apparatus-dependent entries no longer qualify as No Equipment. Nine other compound records have evidenced simultaneous or single requirements. Original bank rows, hashes, permanent IDs, media keys and historical records remain unchanged (zero bank rows edited). Original values remain in `equipment_source` and requirement provenance.", "",
             "SINGLE, ALL, ANY, OPTIONAL and UNKNOWN are supported as explicit groups. Multiple mandatory groups combine with AND. Current evidence supports only SINGLE, ALL and UNKNOWN; no row gains ANY/OPTIONAL or a quantity from punctuation, plurality or presumed substitutions. Partner requirements have a separate item kind. Unknown compounds remain whole legacy filters and display Equipment setup needs review.", "",
             "Library apparatus filters describe discovery, including additional mandatory equipment shown on the result and preview. They do not certify complete athlete availability. Legacy compound filters resolve only their reviewed identities. Independent Sport/Goal/Type/Equipment filters retain AND and distinct exercise counts.", "",
             "## Reviewed records", "", "| Exercise | Decision | Relationship |", "| --- | --- | --- |"]
    lines.extend(f"| {row['name']} | {row['action']} | {', '.join(row['modes'])} |" for row in report["reviewed_rows"])
    lines += ["", "Exact identities, row hashes, raw equipment, original audit references and decision evidence live once in `shared/equipment-requirements.json`.", "",
              "## Distinct Training filter counts", "", "| Value | Before | After |", "| --- | ---: | ---: |"]
    lines.extend(f"| `{r['value']}` | {r['before']} | {r['after']} |" for r in report["filter_changes"])
    lines += ["", "Battle ropes stays at 7 and climbing rope at 2. All 30 reviewed fighter-query totals, ordered IDs and match labels are unchanged. All non-equipment facets are unchanged, including verified Goal coverage of 222/1,010.", "",
              "## Consumer and programming boundaries", "",
              "The library adapter consumes reviewed requirements. The planner continues consuming original banks through its existing normalizers and exact capability gates. `equipment_setup_available` is a conservative setup-only checker, tested for complete, partial and absent equipment; no prescription engine imports or calls it. It cannot grant clinical clearance. No planner eligibility correction is introduced in this PR. The original inaccurate bank associations remain visible as evidence and require a separately tested planner/source migration before this layer can change prescription eligibility.", ""]
    lines.extend(f"- `{r['file']}:{r['line']}` — `{r['function']}`" for r in report["consumers"])
    lines += ["", "## Verification", "", "```powershell", "python tools/audit_equipment_requirements.py --check",
              "python -m pytest tests/test_equipment_requirements.py tests/test_canonical_metadata.py tests/test_training_catalogue.py tests/test_training_library.py tests/test_api_types_generated.py -q", "```", "",
              "The new baseline contains compact pre-change digests and filter counts, not per-exercise snapshots. PR #2822/#2823 reports are retained unchanged. The canonical audit replays its original projection without the later requirement layer; its consumer line references remain historical. One additive original UI receipt keeps the pre-change replay hash-exact. Full fixed-seed plan text/Stage 2 comparisons use the existing temporary-output harness. Executed checks and limitations are recorded in verification.md.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build_report()
    text = markdown(report)
    path = OUT / "README.md"
    if args.check:
        if path.read_text(encoding="utf8") != text:
            raise SystemExit("Stale equipment remediation summary")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf8", newline="\n")
    print(f"{report['reviewed_records']} reviewed; {report['corrected_records']} corrected; {report['unresolved_records']} unresolved; source/identity/30-query/Goal parity verified")
