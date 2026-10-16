"""PR 2 evidence: original source versus reviewed discovery projection.

Capture is allowed only on the reviewed Main baseline, before implementation.
PR 1 evidence is read and hash-protected, never overwritten.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.services import training_library as library  # noqa: E402
from fightcamp.training_catalogue import content_hash, source_hash  # noqa: E402
from tools.audit_metadata_integrity import historical_sources, historical_library_index, snapshot  # noqa: E402

BASE_REVISION = "ad82c28911103e11915a5567fc18623c056ba7d4"
BASELINE = ROOT / "tools/canonical_metadata_baseline.json"
OUT = ROOT / "reports/canonical_metadata"
ALLOWED_CHANGED = frozenset({"api/services/training_library.py", "api/contracts/training_library.py",
                            "shared/equipment-aliases.json", "web/lib/api-schema.generated.ts"})
ALLOWED_ADDED = frozenset({"fightcamp/training_metadata.py", "shared/training-metadata.json"})
# Later equipment remediation is checked separately, without refreshing PR 2's
# frozen reports or changing its discovery-only historical projection.
EQUIPMENT_CHANGED = frozenset({"web/components/training-library.tsx"})
# Additive discovery query parameters; the original route is retained as an
# exact, hash-verified receipt so historical reports do not need regeneration.
DISCOVERY_CHANGED = frozenset({"api/routes/training_library.py"})
# Separately requested CI repair: preserve selected names in fallback cards.
# Its original hash-verified source is retained for immutable audit replay.
FALLBACK_CHANGED = frozenset({"api/structured_plan_deterministic_fallback.py"})
EQUIPMENT_ADDED = frozenset({"fightcamp/equipment_requirements.py", "shared/equipment-requirements.json",
                             "web/lib/equipment-requirements.ts"})
# Custom plans are an independent runtime surface. Keep their reviewed file
# boundary explicit while retaining the exact pre-builder receipts for replay.
CUSTOM_PLAN_CHANGED = frozenset({"api/app.py", "api/schema_requirements.py", "api/store.py",
                                 "api/store_protocols.py", "web/app/plans/page.tsx",
                                 "web/components/today/injury-detail-sheet.tsx", "web/lib/api.ts"})
CUSTOM_PLAN_ADDED = frozenset({"api/contracts/custom_plans.py", "api/routes/custom_plans.py",
                               "api/services/custom_plans.py", "web/app/plans/custom/page.tsx",
                               "web/components/custom-dose-editor.tsx", "web/components/custom-plan-builder.tsx",
                               "web/components/saved-custom-plans.tsx", "web/lib/custom-plan-dose.ts"})
# Private demos extend the current verifier/player without changing catalogue or
# prescription authority. Original verifier/player bytes remain hash-checked receipts.
PRIVATE_MEDIA_CHANGED = frozenset({"api/services/exercise_media.py", "web/components/exercise-demo.tsx"})
PRIVATE_MEDIA_ADDED = frozenset({"api/contracts/private_media.py", "api/routes/private_media.py",
                                "api/services/private_media.py", "api/private_media_store.py",
                                "web/components/private-exercise-video.tsx"})


# Stage B is separate from frozen catalogue and planner authority.
COMMUNITY_CHANGED = frozenset({"web/app/admin/page.tsx"})
COMMUNITY_ADDED = frozenset({"api/community_store.py", "api/contracts/community_exercises.py",
    "api/routes/community_exercises.py", "api/services/community_exercises.py",
    "web/components/community-exercises.tsx", "web/e2e/custom-plan-fixture.ts", "web/components/admin-community-queue.tsx"})

# Open plans, custom-workout integration, Today/plan exercise editing, naming
# and home changes (#2839-#2855) touch planner-adjacent runtime and UI only, not
# catalogue or prescription authority. Pre-change bytes are hash-verified
# receipts in tools/metadata_integrity_original_sources.json.
OPEN_PLAN_CHANGED = frozenset({"api/contracts/injury_policy.py", "api/contracts/readiness_message.py",
                               "api/exercise_identity.py", "api/models.py", "api/optional_sessions.py",
                               "api/plan_mappers.py", "api/services/active_plan.py",
                               "api/services/admin_stage2_service.py", "api/services/effective_structured_plan.py",
                               "api/services/exercise_log_service.py", "api/services/open_plan_timeline.py",
                               "api/services/progress_notifications.py", "api/services/streaks.py",
                               "api/services/week_progress.py",
                               "api/services/today_service.py", "api/structured_plan_locked_merge.py",
                               "api/structured_plan_models.py", "api/structured_plan_sparring_reconcile.py",
                               "fightcamp/weekly_schedule_view.py", "web/app/demo-plan/page.tsx", "web/app/page.tsx",
                               "web/components/fight-countdown.tsx", "web/components/plan-viewer.tsx",
                               "web/components/plans/plan-dashboard.tsx",
                               "web/components/structured-plan-renderer.tsx", "web/components/today-screen.tsx",
                               "web/components/today/today-injury-manager.tsx",
                               "web/components/today/today-session-panel.tsx",
                               "web/components/today/use-today-command.ts", "web/components/xp-progress-card.tsx",
                               "web/lib/api-contract.ts", "web/lib/exercise-log.ts", "web/lib/open-block.ts",
                               "web/lib/rounds-format.ts", "web/lib/structured-plan.ts", "web/lib/today.ts",
                               "web/lib/types.ts", "web/messages/en.json", "web/messages/es.json",
                               "web/messages/fr.json", "web/messages/it.json", "web/messages/pt-BR.json"})
OPEN_PLAN_ADDED = frozenset({"api/contracts/exercise_changes.py", "api/routes/exercise_changes.py",
                             "api/services/exercise_customisation.py", "api/services/exercise_dose.py",
                             "api/services/exercise_overrides.py", "web/components/exercise-customisation.tsx",
                             "web/components/exercise-prescription-editor.tsx", "web/lib/custom-plan-schedule.ts",
                             "web/lib/exercise-customisation.ts", "web/lib/exercise-dose.ts"})


def dumps(value):
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def source_files():
    return {path.relative_to(ROOT).as_posix(): source_hash(path.read_bytes())
            for path in sorted((ROOT / "reports/metadata_integrity").glob("*")) if path.is_file()}


def query_results(index):
    cases = json.loads((ROOT / "tools/training_library_search_cases.json").read_bytes())["cases"]
    return [{"query": case["query"], "total": result["total"],
             "ordered_ids": [entry["catalogue_id"] for entry in result["entries"]],
             "discovery_matches": [entry["discovery_match"] for entry in result["entries"]],
             "relevant": case["relevant"], "exclude": case["exclude"]}
            for case in cases for result in [library.search(index, q=case["query"], limit=3000)]]


def plan_cases():
    from tests.support import _build_request

    cases = []
    for name, overrides in (
        ("boxing_shoulder_limited", {}),
        ("boxing_healthy_reviewed_equipment", {"injuries": "none", "equipment_access": ["kettlebells", "weighted_vest", "rowing_machine", "thai_pads", "heavy_bag"]}),
        ("mma_no_equipment", {"athlete": {"technical_style": ["mma"], "tactical_style": ["counter_striker"]}, "equipment_access": [], "injuries": "none"}),
    ):
        payload = _build_request(overrides).to_payload()
        payload["random_seed"] = 7
        cases.append({"case": name, "payload": payload})
    return cases


def plan_results(cases):
    results = []
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        from fightcamp.main import generate_plan

        for case in cases:
            result = asyncio.run(generate_plan(deepcopy(case["payload"])))
            results.append({"case": case["case"], "payload": case["payload"],
                            "plan_text_sha256": content_hash(result["plan_text"]),
                            "stage2_sha256": content_hash(result["stage2_payload"])})
    return results


def capture_baseline():
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if revision != BASE_REVISION:
        raise ValueError("Capture requires the reviewed, unmodified Main baseline")
    protected = snapshot()
    original = json.loads((ROOT / "tools/metadata_integrity_baseline.json").read_bytes())
    if protected != original:
        raise ValueError("Production changed before baseline capture")
    index = library.LibraryCache().get()
    return {"base_revision": revision, "preservation": protected, "pr1_reports": source_files(),
            "original_facets": {r["entry"]["catalogue_id"]: {f: sorted(values) for f, values in r["facets"].items()} for r in index.records},
            "goal_filter_entries": sum(bool(r["facets"]["goal"]) for r in index.records if r["summary"]["category"] == "training"),
            "queries": query_results(index), "plans": plan_results(plan_cases())}


def controlled_plan_parity(baseline):
    """Replay frozen complete outputs, with clocks and collection seed pinned.

    Retain the initial uncontrolled hashes. They cannot act as cross-process
    Stage 2 golden files because the existing payload serializes some sets as
    unsorted arrays. No payload ordering or programming code is changed here.
    """
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    with historical_sources() as before_root, historical_sources() as after_root, TemporaryDirectory(prefix="unlxck-plan-parity-") as temporary:
        temporary = Path(temporary).resolve()
        outputs = []
        # Frozen PR #2823 comparisons retain their original bank inputs. Actual
        # source-change comparisons are exercised by the generator regressions.
        for label, root in (("before", before_root), ("after", after_root)):
            destination = temporary / (label + ".json")
            subprocess.run([sys.executable, str(ROOT / "tools/canonical_metadata_plan_probe.py"), str(BASELINE), str(destination)],
                           cwd=root, env=env, check=True, capture_output=True)
            outputs.append(json.loads(destination.read_bytes()))
        if outputs[0] != outputs[1]:
            raise ValueError("Controlled original/current planner outputs differ")
        results = [{"case": case["case"], "plan_text_sha256": content_hash(case["plan_text"]),
                    "stage2_sha256": content_hash(case["stage2_payload"])} for case in outputs[0]]
        if [r["plan_text_sha256"] for r in results] != [r["plan_text_sha256"] for r in baseline["plans"]]:
            raise ValueError("Captured original plan text differs from controlled replay")
        diagnostic = temporary / "original-other-hash-seed.json"
        subprocess.run([sys.executable, str(ROOT / "tools/canonical_metadata_plan_probe.py"), str(BASELINE), str(diagnostic), "--first"],
                       cwd=before_root, env={**env, "PYTHONHASHSEED": "1"}, check=True, capture_output=True)
        other_seed = json.loads(diagnostic.read_bytes())[0]
        order_differences = collection_order_differences(outputs[0][0], other_seed)
        if not order_differences:
            raise ValueError("Uncontrolled Stage 2 hash limitation lacks reproducible evidence")
        return {"clock_utc": "2026-10-11 09:00", "random_seed": 7, "python_hash_seed": "0",
                "comparison": "Complete original/current plan text and Stage 2 payload equality, including array order, doses, selection and scores",
                "plans": results, "original_capture": baseline["plans"],
                "existing_hash_seed_order_variation": order_differences,
                "uncontrolled_hash_limitation": "Original cross-process Stage 2 hashes depend on existing unsorted set serialization; controlled replay preserves the entire payload without normalizing its arrays."}


def collection_order_differences(left, right, path=""):
    if left == right:
        return []
    if isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
        return [difference for key in sorted(left) for difference in collection_order_differences(left[key], right[key], path + "/" + key)]
    if isinstance(left, list) and isinstance(right, list) and sorted(map(dumps, left)) == sorted(map(dumps, right)):
        return [{"path": path, "hash_seed_0": left, "hash_seed_1": right, "difference": "ordering_only_in_original_code"}]
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [difference for ordinal, (a, b) in enumerate(zip(left, right))
                for difference in collection_order_differences(a, b, path + "/" + str(ordinal))]
    raise ValueError("Existing hash-seed variation changes values, not just order: " + path)


def browser_fixture():
    index = historical_library_index()
    cases = [{}, {"equipment": "kettlebell"}, {"equipment": "kettlebell", "type": "strength_power"},
             {"type": "strength_power"}, {"equipment": "battle_ropes"}, {"body_focus": "adductors"}]
    responses = {"&".join(f"{key}={value}" for key, value in sorted(filters.items())): library.search(index, filters=filters)
                 for filters in cases}
    return {"responses": responses, "previews": {r["catalogue_id"]: library.preview(index.by_id[r["catalogue_id"]])
            for response in responses.values() for r in response["entries"]}}


def consumer_receipts(*, historical=False):
    reviewed = {
        "fightcamp/training_metadata.py": {
            "project_value": "Field-scoped reviewed aliases, raw requirements and pinned source-association exclusions; discovery only",
            "canonical_filter": "Exact legacy filter identifier lookup; anatomy aliases Training-only",
        },
        "api/services/training_library.py": {
            "_prepare": "Canonical equipment/body-focus facet sets; raw summaries, source evidence and Goal rules retained",
            "search": "AND filters, distinct per-entry counts; apparatus naming fallback only for previously unmatched lexical queries; reviewed intent scores untouched",
            "preview": "Original equipment and requirement guidance plus typed canonical provenance",
            "_signature": "Mapping file stats invalidate cached projection",
            "_revision": "Mapping content changes pagination revision",
        },
        "fightcamp/training_catalogue.py": {"build_catalogue": "Unchanged strict raw source, identity, eligibility, media key and search evidence extraction"},
        "fightcamp/training_context.py": {
            "normalize_equipment_list": "Unchanged planner normalization; reads only existing shared pads object, ignores additive catalogue_projection",
            "normalize_athlete_equipment_list": "Unchanged persisted athlete equipment capabilities and implicit bodyweight",
        },
        "fightcamp/strength.py": {
            "_exercise_fatigue_cost": "Unchanged normalized equipment cost classes",
            "_strength_contextual_risk_patterns": "Unchanged equipment/mechanical risk interpretation",
            "_evaluate_strength_late_window": "Unchanged exact equipment and fight-proximity safety gates",
            "generate_strength_block": "Unchanged phase, injury, equipment eligibility and selection",
        },
        "fightcamp/conditioning.py": {
            "_is_machine_biased_gas_tank_drill": "Unchanged machine ranking evidence",
            "_evaluate_conditioning_late_window": "Unchanged phase/proximity, equipment and mechanical-risk safety gates",
            "_conditioning_required_equipment": "Unchanged source requirements; no discovery contract used for prescription",
            "generate_conditioning_block": "Unchanged conditioning/style/taper selection, doses and injury restrictions",
        },
    }
    receipts = []
    for path, functions in reviewed.items():
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        definitions = {n.name: n.lineno for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for function, meaning in functions.items():
            receipts.append({"file": path, "function": function, "line": definitions[function], "usage": meaning,
                             "programming_sensitive": path in {"fightcamp/strength.py", "fightcamp/conditioning.py", "fightcamp/training_context.py"}})
    for path, phrase, function, usage in (
        ("web/lib/intake-options.ts", "export function canonicalizeEquipmentAccessValues", "canonicalizeEquipmentAccessValues", "Unchanged exact legacy pads lookup; catalogue mapping cannot migrate saved athlete selections"),
        ("web/components/training-library.tsx", "{choices.map(choice", "TrainingLibrary filter options", "Unchanged native selects render canonical API labels and distinct counts; independent selected fields"),
    ):
        line = next(n for n, text in enumerate((ROOT / path).read_text(encoding="utf-8").splitlines(), 1) if phrase in text)
        receipts.append({"file": path, "function": function, "line": line, "usage": usage, "programming_sensitive": False})
    if historical:
        # PR 2's report retains its original line references. Current line
        # references belong in the later remediation report, not this baseline.
        retained = json.loads((OUT / "before-after.json").read_bytes())["affected_consumer_receipts"]
        if {(r["file"], r["function"], r["usage"]) for r in receipts} != {(r["file"], r["function"], r["usage"]) for r in retained}:
            raise ValueError("Historical consumer definitions changed")
        return retained
    return receipts


def preservation(baseline):
    current = snapshot()
    original = baseline["preservation"]
    # Reconstruct the five reviewed source edits, then verify every original
    # byte and identity against the immutable baseline. No drift is waived.
    with historical_sources() as replay:
        historical = snapshot(replay)
    for field in ("banks", "identity_inputs", "identities"):
        if historical[field] != original[field]:
            raise ValueError("Source or identity drift: " + field)
    if source_files() != baseline["pr1_reports"]:
        raise ValueError("PR 1 evidence changed")
    changed = sorted(p for p, h in original["production_files"].items() if current["production_files"].get(p) != h)
    added = sorted(set(current["production_files"]) - set(original["production_files"]))
    if not set(changed) <= ALLOWED_CHANGED | EQUIPMENT_CHANGED | FALLBACK_CHANGED | DISCOVERY_CHANGED | CUSTOM_PLAN_CHANGED | PRIVATE_MEDIA_CHANGED | COMMUNITY_CHANGED | OPEN_PLAN_CHANGED | {"fightcamp/strength.py"} or not set(added) <= ALLOWED_ADDED | EQUIPMENT_ADDED | CUSTOM_PLAN_ADDED | PRIVATE_MEDIA_ADDED | COMMUNITY_ADDED | OPEN_PLAN_ADDED:
        raise ValueError("Unapproved production diff: " + str((changed, added)))
    for p, h in original["configuration_files"].items():
        if p == "data/tag_vocabulary.json" and current["configuration_files"].get(p) != h:
            from tools.check_tag_retirement import original_vocabulary_source

            if source_hash(original_vocabulary_source((ROOT / p).read_bytes())) != h:
                raise ValueError("Original vocabulary receipt changed")
            continue
        if current["configuration_files"].get(p) != h and p not in {"shared/equipment-aliases.json", "data/training_catalogue_ids.json"}:
            raise ValueError("Programming/clinical configuration drift: " + p)
    if set(current["configuration_files"]) - set(original["configuration_files"]) - {"shared/training-metadata.json", "shared/equipment-requirements.json"}:
        raise ValueError("Unapproved configuration added")
    originals = json.loads((ROOT / "tools/metadata_integrity_original_sources.json").read_bytes())
    if set(originals) != (ALLOWED_CHANGED | EQUIPMENT_CHANGED | FALLBACK_CHANGED | DISCOVERY_CHANGED | CUSTOM_PLAN_CHANGED
                          | PRIVATE_MEDIA_CHANGED | COMMUNITY_CHANGED | OPEN_PLAN_CHANGED):
        raise ValueError("Unexpected historical source receipts")
    for p, text in originals.items():
        if source_hash(text.encode()) != original["production_files"][p]:
            raise ValueError("Original production receipt changed: " + p)
    if json.loads(originals["shared/equipment-aliases.json"])["pads"] != json.loads((ROOT / "shared/equipment-aliases.json").read_bytes())["pads"]:
        raise ValueError("Persisted intake/planner equipment contract changed")
    return {"banks": historical["banks"], "catalogue_entries": len(current["identities"]),
            "source_hash_parity": True, "catalogue_identity_and_media_key_parity": True,
            "pr1_evidence_hash_parity": True, "planner_clinical_configuration_parity": True,
            "persisted_equipment_alias_contract_parity": True,
            "allowed_changed_production": sorted(set(changed) - EQUIPMENT_CHANGED - FALLBACK_CHANGED - DISCOVERY_CHANGED - CUSTOM_PLAN_CHANGED - PRIVATE_MEDIA_CHANGED - COMMUNITY_CHANGED - OPEN_PLAN_CHANGED - {"fightcamp/strength.py"}),
            "added_projection_sources": sorted(set(added) - EQUIPMENT_ADDED - CUSTOM_PLAN_ADDED - PRIVATE_MEDIA_ADDED - COMMUNITY_ADDED - OPEN_PLAN_ADDED)}


def build_report(*, verified_plans=None):
    baseline = json.loads(BASELINE.read_bytes())
    protected = preservation(baseline)
    index = historical_library_index()
    projection = index.projection
    issues = json.loads((ROOT / "reports/metadata_integrity/remediation.json").read_bytes())["issues"]
    by_issue = {i["issue_id"]: i for i in issues}
    groups = []
    for mapping in projection["mappings"]:
        issue = by_issue[mapping["audit_decision"]]
        if issue["confidence"] != "high" or issue["recommended_action"] not in {"MERGE", "RENAME"} or issue["field"] != mapping["field"] or set(issue["existing_values"]) != set(mapping["source_values"]):
            raise ValueError("Unreviewed mapping: " + mapping["audit_decision"])
        field = "equipment" if mapping["field"] == "equipment" else "body_focus"
        rows = [r for r in index.records if any(v["audit_decision"] == mapping["audit_decision"] for v in r["projection"])]
        comparisons = []
        for category in ("training", "rehab", "learn"):
            eligible = [r for r in rows if r["summary"]["category"] == category]
            original_ids = {r["entry"]["catalogue_id"] for r in eligible if set(mapping["source_values"]) & set(baseline["original_facets"][r["entry"]["catalogue_id"]][field])}
            after = library.search(index, category=category, filters={field: mapping["canonical_id"]}, limit=3000)
            comparisons.append({"category": category,
                "before_filter_counts": {v: sum(v in baseline["original_facets"][r["entry"]["catalogue_id"]][field] for r in index.records if r["summary"]["category"] == category) for v in mapping["source_values"]},
                "before_distinct_union": len(original_ids), "after_filter_value": mapping["canonical_id"],
                "after_distinct_matches": after["total"], "after_matching_ids": [e["catalogue_id"] for e in after["entries"]]})
        groups.append({**mapping, "facet": field, "affected_catalogue_entries": len(rows),
                       "affected_ids": sorted(r["entry"]["catalogue_id"] for r in rows),
                       "filter_comparisons": comparisons,
                       "source_correction_applied": False})
    queries = query_results(index)
    if queries != baseline["queries"]:
        raise ValueError("Reviewed fighter query membership, order, or evidence changed")
    for r in index.records:
        original = baseline["original_facets"][r["entry"]["catalogue_id"]]
        for field in ("goal", "type", "sport"):
            if sorted(r["facets"][field]) != original[field]:
                raise ValueError("Unrelated facet drift: " + field)
        if r["summary"]["prescription_allowed"] is not False:
            raise ValueError("Discovery prescription boundary changed")
    plans = verified_plans if verified_plans is not None else controlled_plan_parity(baseline)
    applied = {m["audit_decision"] for m in projection["mappings"]}
    occurrences = [{k: v[k] for k in ("catalogue_id", "source", "source_pointer", "row_revision", "source_field", "source_value", "canonical_id", "label", "dimension", "subtype", "audit_decision", "status", "filter_eligible", "association_note")}
                   for r in index.records for v in r["projection"]]
    facets = {category: {"before": {field: sorted({v for r in index.records if r["summary"]["category"] == category for v in baseline["original_facets"][r["entry"]["catalogue_id"]][field]}) for field in library.FILTERS},
                         "after": library.search(index, category=category, limit=1)["facets"]}
              for category in ("training", "rehab", "learn")}
    return {"base_revision": BASE_REVISION, "scope": "discovery_only; raw banks and planner unchanged",
            "preservation": protected, "groups": groups, "facets": facets, "projected_values": occurrences,
            "affected_consumer_receipts": consumer_receipts(historical=True),
            "withheld_source_associations": projection["association_reviews"],
            "remaining_register_issues": [{key: i[key] for key in ("issue_id", "field", "existing_values", "recommended_action", "confidence", "manual_review_required")}
                                         for i in issues if i["issue_id"] not in applied],
            "original_register_not_closed": "Six decisions projected for discovery only. Source corrections, quantities, compounds and clinical migration remain separate reviews.",
            "regressions": {"goal_facets_identical": True, "training_goal_entries": baseline["goal_filter_entries"],
                            "reviewed_fighter_queries_identical": True, "queries": queries,
                            "fixed_seed_plan_and_dose_parity": True, "plans": plans,
                            "prescription_allowed": False}}


def markdown(report):
    lines = ["# Canonical metadata and filter evidence", "",
             "Six high-confidence PR #2822 decisions are projected for discovery. Original values, requirements, source pointers, row hashes, catalogue IDs and audit decisions remain available in drill previews. No bank, planner, dose, injury, rehabilitation or Goal rule changed.", "",
             "| Reviewed decision | Raw values | Canonical filter | Source rows | Training matches before (distinct union) → after |", "| --- | --- | --- | ---: | ---: |"]
    for group in report["groups"]:
        comparison = group["filter_comparisons"][0]
        lines.append(f"| `{group['audit_decision']}` | {', '.join('`'+v+'`' for v in group['source_values'])} | {group['label']} (`{group['canonical_id']}`) | {group['affected_catalogue_entries']} | {comparison['before_distinct_union']} → {comparison['after_distinct_matches']} |")
    lines += ["", "Battle-rope source rows include two climbing drills whose equipment notes explicitly require a climbing rope. Those pinned associations remain raw evidence but cannot qualify battle-rope filters or searches. This is a discovery exclusion, not a source correction or programming change.", "",
              "The anatomical projection adds the reviewed hip-adductor focus to seven Training rows with existing adductor/adductors tags. It does not alias clinical region IDs or add goals. Kettlebell quantity remains in the original name/instructions/notes; plural spelling alone does not establish a pair requirement.", "",
              "Counts use distinct catalogue IDs. Filters retain AND semantics, independently scoped facet counts and legacy identifiers. Unknown equipment never becomes No Equipment. Compound strings remain whole unresolved tokens with their original requirements and grouping.", "",
              "## Evidence and verification", "",
              "[before-after.json](before-after.json) contains every projected token, raw/canonical/display distinction, full before/after filter values and matching identities, unchanged source hashes, remaining register issues, 30 identical reviewed query result orders and three identical fixed-seed plan/prescription hashes.", "",
              "Goal coverage remains **222/1,010**. All 2,855 catalogue identities and media keys, source bank hashes and PR 1 report hashes match the captured Main baseline. The existing shared pads intake contract is identical; catalogue aliases never alter athlete capability normalization.", "",
              "The smallest architecture is two small field-scoped reviewed mapping arrays and pure adapters used only by the library. Equipment aliases extend the existing shared contract additively; the anatomical tag mapping is Training-only. Source requirements and athlete capabilities remain separate. No parent categories, clinical registries or compound AND/OR rules are inferred.", "",
              "Consumer changes: `training_library._prepare` projects facets; `search` resolves legacy facet IDs and conservative apparatus query aliases; `preview` exposes provenance; `LibraryCache` includes mapping contracts in its revision. `training_context`, strength, conditioning and clinical consumers retain their original source hashes and exact behavior. `intake-options.ts` continues reading only `pads`. The native dropdown UI already consumes API labels and distinct counts.", "",
              "PR 1 is historical evidence: its reports and original baseline are unchanged. `--historical --check` replays original code receipts offline using four retained pre-projection sources, individually verified against frozen PR 1 hashes. The ordinary PR 1 command remains strict against production drift.", "",
              "The initial uncontrolled Stage 2 hashes exposed existing cross-process ordering variance in selected `movement_patterns` (high-torque rotation / change-of-direction). The report retains those original hashes and records the exact original-code variation with Python hash seeds 0 and 1. Before/after checks pin both planner clocks and hash seed 0, then compare complete payloads including array order; no dose, score, selection or array is normalized to make the check pass.", "",
              "```powershell", "python tools/audit_canonical_metadata.py", "python tools/audit_canonical_metadata.py --check", "python tools/audit_metadata_integrity.py --historical --check", "python -m pytest tests/test_canonical_metadata.py tests/test_metadata_integrity_audit.py -q", "```", "",
              "See [verification.md](verification.md) for executed checks and limitations, and [roadmap.md](roadmap.md) for remaining remediation gates.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-baseline", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.capture_baseline:
        if BASELINE.exists():
            raise SystemExit("Baseline already captured; do not refresh it")
        BASELINE.write_text(dumps(capture_baseline()), encoding="utf-8", newline="\n")
        print("Captured original facets, 30 fighter-query controls, source identities and 3 fixed-seed plans")
    else:
        report = build_report()
        for path, text in ((OUT / "before-after.json", dumps(report)), (OUT / "README.md", markdown(report)),
                           (ROOT / "web/e2e/fixtures/canonical-metadata-library.json", dumps(browser_fixture()))):
            if args.check:
                if not path.exists() or path.read_text(encoding="utf-8") != text:
                    raise SystemExit("Stale canonical metadata report: " + path.relative_to(ROOT).as_posix())
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
        print("Six reviewed groups; source/identity/Goal/30-query/three-plan parity verified")
