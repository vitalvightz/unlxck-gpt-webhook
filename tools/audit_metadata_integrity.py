"""Investigation only: raw metadata, dependency evidence, and review candidates.

python tools/audit_metadata_integrity.py [--check]
No bank loader, normaliser, writer, database, or inferred goal is used to extract
metadata. The existing strict catalogue supplies immutable source identities.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from contextlib import contextmanager
from difflib import SequenceMatcher
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fightcamp.training_catalogue import (  # noqa: E402
    ALIASES_FILE, MANIFEST_FILE, PHYSICAL_CLASSES, SOURCE_CLASSES,
    build_catalogue, content_hash, source_hash,
)

OUT = Path("reports/metadata_integrity")
BASELINE = ROOT / "tools/metadata_integrity_baseline.json"
REVIEW = ROOT / "tools/metadata_integrity_review.json"
PROSE = frozenset({
    "name", "notes", "description", "instructions", "why", "cue", "cue_source",
    "pro_tip", "combat_carryover", "equipment_note", "evidence_notes", "progress",
    "progress_when", "regress_when", "stop_when", "quality_stop_rule", "duration",
    "contraindications", "avoid_if", "id", "key", "mindset", "phase_progression",
})
CLASSIFICATION = frozenset({
    "tags", "goals", "qualities", "movement", "method", "modality", "category",
    "type", "system", "body_region", "target_regions", "target_tissues", "sports",
    "styles", "tactical_styles", "sport_specific", "sport_specificity", "function",
    "tactical_function", "weaknesses", "footwork_pattern", "directionality",
    "stance_transition", "side_rule", "subfamily", "primer_family", "phase_role",
    "contraction_type", "execution_intent",
})
SAFETY = frozenset({
    "mechanical_risk_tags", "contraindications", "avoid_if", "rehab_stage",
    "allowed_severities", "pain_ceiling", "progress_when", "regress_when",
    "stop_when", "quality_stop_rule", "contact_level", "block_if_fight_within_days",
    "target_regions", "target_tissues", "impact", "load", "velocity",
    "laterality_applicability", "late_windows", "cut_buckets_allowed",
})


def dumps(value):
    return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n"


def report_json(report):
    """Readable top-level sections, compact records to avoid duplicated whitespace."""
    def compact(value):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    sections = []
    for key, value in sorted(report.items()):
        prefix = "  " + compact(key) + ": "
        if isinstance(value, list) and value:
            sections.append(prefix + "[\n" + ",\n".join("    " + compact(v) for v in value) + "\n  ]")
        elif isinstance(value, dict) and value:
            sections.append(prefix + "{\n" + ",\n".join("    " + compact(k) + ": " + compact(v) for k, v in sorted(value.items())) + "\n  }")
        else:
            sections.append(prefix + compact(value))
    return "{\n" + ",\n".join(sections) + "\n}\n"


def code_literal(value):
    """Lossless JSON representation of Python-only policy literal containers.

    Bank JSON never passes through this adapter. Non-string dict keys and
    tuple/set semantics remain typed rather than silently becoming JSON keys.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return [code_literal(v) for v in value]
    if isinstance(value, tuple):
        return {"python_tuple": [code_literal(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        return {"python_set": [code_literal(v) for v in sorted(value, key=repr)]}
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value):
            return {k: code_literal(v) for k, v in value.items()}
        return {"python_dict_items": [{"key": code_literal(k), "key_type": type(k).__name__, "value": code_literal(v)} for k, v in value.items()]}
    return {"python_literal_type": type(value).__name__, "representation": repr(value)}


def family(field):
    key = field.split(".")[-1] if field.startswith("config.") else field.removeprefix("group.").split(".")[0]
    if key.startswith("equipment"):
        return "equipment"
    if key in SAFETY or key in {"location", "care_type", "phase_progression"}:
        return "safety"
    if key in CLASSIFICATION:
        return "classification"
    if key in PROSE:
        return "identity" if key in {"id", "key", "name"} else "guidance/evidence"
    return "programming/additional"


def leaves(value, field="", pointer=""):
    """Lists are traversed but strings (including compounds) are never split.

    Raw containers are also retained on every entry/configuration record, so
    empty/null/absent, array grouping, list order, numeric types and prose survive.
    """
    if isinstance(value, dict):
        if not value:
            yield field, pointer, value
        for key, child in sorted(value.items()):
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from leaves(child, f"{field}.{key}".strip("."), f"{pointer}/{escaped}")
    elif isinstance(value, list):
        if not value:
            yield field, pointer, value
        for i, child in enumerate(value):
            yield from leaves(child, field, f"{pointer}/{i}")
    else:
        yield field, pointer, value


def tracked(root):
    replay = root / ".audit-tracked.json"
    if replay.exists():
        return json.loads(replay.read_bytes())
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True)
    return sorted(result.stdout.decode().rstrip("\0").split("\0"))


def production_paths(root):
    return [p for p in tracked(root) if (
        p.startswith(("fightcamp/", "api/", "web/", "shared/")) or "/" not in p
    ) and p.endswith((".py", ".ts", ".tsx", ".json", ".sql"))
        and not re.search(r"(?:^|/)(?:tests?|cases|fixtures|__pycache__|node_modules)(?:/)|\.(?:test|spec)\.", p)]


def snapshot(root=ROOT):
    entries = build_catalogue(root / "data")
    return {
        "source_revision": "a91b0be3593b6887162866c19712ab087392d459",
        "hash_contract": "SHA256 bytes with CRLF->LF only; raw-byte immutability checked around execution",
        "banks": {source: {"sha256": source_hash((root / "data" / source).read_bytes()),
                           "entries": sum(e["source"] == source for e in entries)} for source in SOURCE_CLASSES},
        "identity_inputs": {s: source_hash((root / "data" / s).read_bytes()) for s in (MANIFEST_FILE, ALIASES_FILE)},
        "identities": {e["catalogue_id"]: {"row_sha256": e["row_sha256"], "exercise_key": e["exercise_key"]} for e in entries},
        "production_files": {p: source_hash((root / p).read_bytes()) for p in production_paths(root)},
        "configuration_files": {p: source_hash((root / p).read_bytes()) for p in tracked(root)
                                if p.startswith(("data/", "shared/")) and p.endswith(".json") and p not in {"data/" + s for s in SOURCE_CLASSES}},
    }


def enclosing(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return node.name
    return "<module>"


def scan_code(root, fields, extra_names=()):
    """AST reads are syntactic evidence, not an interprocedural proof of use.

    Exact literals are reported independently: a string occurring in a module
    does not prove it is compared to a bank field. Reviewed workflows below
    provide the semantic bridge, including dynamic getters and policy models.
    """
    names = {f.removeprefix("group.").split(".")[-1] for f in fields} | set(extra_names)
    names.discard("*")
    name_pattern = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b")
    refs, literals, constants, dynamic, imports, contracts = [], defaultdict(list), [], [], [], []
    for path in production_paths(root):
        text = (root / path).read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        if not path.endswith(".py"):
            for number, line in enumerate(lines, 1):
                for token in re.findall(r"[\"']([^\"'\n]+)[\"']", line):
                    literals[token].append({"file": path, "line": number, "function": "<text>"})
                for name in sorted(set(name_pattern.findall(line))):
                    refs.append({"field": name, "file": path, "line": number, "function": "<text>",
                                 "operation": "text_reference_requires_review", "evidence": line.strip()[:350]})
            continue
        tree = ast.parse(text, filename=path)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            fn = enclosing(node, parents)
            loc = {"file": path, "line": node.lineno if hasattr(node, "lineno") else 0, "function": fn}
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals[node.value].append(loc)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append({**loc, "statement": ast.unparse(node)})
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                contracts.append({**loc, "field": node.target.id, "annotation": ast.unparse(node.annotation),
                                  "default_or_constraint": ast.unparse(node.value) if node.value else None,
                                  "literal_values": [code_literal(n.value) for n in ast.walk(node.annotation) if isinstance(n, ast.Constant)]})
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and fn == "<module>":
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        try:
                            value = ast.literal_eval(node.value)
                        except (ValueError, TypeError):
                            continue
                        # Record inspectable constants without executing modules.
                        constants.append({**loc, "symbol": target.id, "raw": code_literal(value),
                                          "literal_source": ast.get_source_segment(text, node.value)})
            name, op = None, None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "pop", "setdefault"} and node.args:
                if isinstance(node.args[0], ast.Constant):
                    name, op = node.args[0].value, node.func.attr
                else:
                    dynamic.append({**loc, "expression": ast.unparse(node)[:350]})
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                name, op = node.slice.value, "subscript_read" if isinstance(node.ctx, ast.Load) else "subscript_write"
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                name, op = node.args[1].value, "getattr"
            elif isinstance(node, ast.Attribute) and node.attr in names:
                name, op = node.attr, "attribute_read" if isinstance(node.ctx, ast.Load) else "attribute_write"
            if name in names:
                refs.append({**loc, "field": name, "operation": op, "evidence": lines[node.lineno - 1].strip()[:350]})
    refs = sorted({dumps(r): r for r in refs}.values(), key=lambda r: (r["field"], r["file"], r["line"], r["operation"]))
    return refs, literals, constants, sorted(dynamic, key=lambda r: (r["file"], r["line"])), imports, contracts


def configuration_records(root):
    bank_paths = {"data/" + p for p in SOURCE_CLASSES}
    excluded = {"data/training_catalogue_ids.json", "data/rehab_archive/exact_duplicates.json"}
    records = []
    for path in tracked(root):
        if not path.endswith(".json") or not path.startswith(("data/", "shared/")) or path in bank_paths | excluded or "/cases/" in path:
            continue
        raw_bytes = (root / path).read_bytes()
        payload = json.loads(raw_bytes)
        digest = source_hash(raw_bytes)
        # A review array/ID-keyed policy needs bounded field names, not 1,499
        # artificial dimensions. Identity remains on each separate record.
        if isinstance(payload, list):
            rows = [(f"/{i}", row) for i, row in enumerate(payload)]
        elif path == "data/safety/surface_wound_review.json":
            rows = [("/" + identity, row) for identity, row in sorted(payload.items())]
        else:
            rows = [("", payload)]
        for pointer, row in rows:
            records.append({"record_id": path + pointer, "source": path, "pointer": pointer,
                            "sha256": digest, "raw": row})
    return records


def field_inventory(records, *, config=False):
    index = defaultdict(lambda: defaultdict(list))
    root_states = defaultdict(Counter)
    for record in records:
        ident = record["record_id"] if config else record["catalogue_id"]
        for field, pointer, raw in leaves(record["raw"]):
            index[field][dumps(raw)].append({"identity": ident, "pointer": pointer, "source": record["source"]})
        if not config:
            for field, pointer, raw in leaves(record["raw_group"] or {}, "group"):
                if field != "group":
                    index[field][dumps(raw)].append({"identity": ident, "pointer": pointer, "source": record["source"]})
    for field in index:
        if "." in field:
            continue
        for record in records:
            row = record["raw"]
            if not isinstance(row, dict) or field not in row:
                state = "absent"
            elif row[field] is None:
                state = "null"
            elif row[field] in ([], {}, ""):
                state = "explicit_empty"
            elif isinstance(row[field], str) and row[field] in {"unknown", "unreviewed", "unspecified"}:
                state = "explicit_unknown"
            else:
                state = "populated"
            root_states[field][state] += 1
    result = {}
    for field, values in sorted(index.items()):
        result[field] = {
            "family": family(field), "distinct_raw_values": len(values),
            "distinct_nonempty_values": sum(json.loads(v) not in (None, [], {}, "") for v in values),
            "states": dict(sorted(root_states[field].items())),
            "values": [{"raw": json.loads(v), "frequency": len(refs),
                        "affected_identity_count": len({r["identity"] for r in refs}),
                        "source_frequencies": dict(sorted(Counter(r["source"] for r in refs).items())),
                        "occurrences": [{"identity": r["identity"], "pointer": r["pointer"]} for r in refs]}
                       for v, refs in sorted(values.items())],
        }
    return result


def word_key(value):
    return re.sub(r"[\s\-]+", "_", value.strip().casefold())


def singular_key(value):
    return "_".join(word[:-1] if word.endswith("s") and not word.endswith(("ss", "us")) else word for word in word_key(value).split("_"))


def candidates(fields):
    result = []
    for field, record in fields.items():
        root = field.removeprefix("group.").split(".")[0]
        if root in PROSE or root in {"evidence", "source"}:
            continue
        values = sorted({v["raw"] for v in record["values"] if isinstance(v["raw"], str) and 0 < len(v["raw"]) <= 70})
        for a, b in itertools.combinations(values, 2):
            reason = None
            if word_key(a) == word_key(b):
                reason = "separator/case/whitespace"
            elif singular_key(a) == singular_key(b):
                reason = "singular/plural"
            elif sorted(word_key(a).split("_")) == sorted(word_key(b).split("_")):
                reason = "word_order"
            elif min(len(a), len(b)) >= 5 and SequenceMatcher(None, a, b).ratio() >= .88:
                reason = "spelling_or_overlapping_name"
            if reason:
                result.append({"field": field, "values": [a, b], "candidate_reason": reason})
        for value in values:
            if re.search(r"[,/+|&]", value):
                result.append({"field": field, "values": [value], "candidate_reason": "compound_or_separator",
                               "raw_preserved": True})
    return result


def tokens(row, field):
    value = row.get(field)
    if isinstance(value, str):
        return {value}
    return {v for v in value if isinstance(v, str)} if isinstance(value, list) else set()


def accuracy(entries):
    findings = []
    cue_words = re.compile(r"cue|signal|random|unpredict|partner|react to|response|respond|call|visual|tactile|command|coach|light", re.I)
    for entry in entries:
        row = entry["raw"]
        tags = tokens(row, "tags")
        risks = tags | tokens(row, "mechanical_risk_tags")
        text = " ".join(str(row.get(f) or "") for f in ("name", "description", "instructions", "notes", "cue", "modality", "why", "pro_tip", "combat_carryover"))
        checks = []
        if ("reaction" in tags or "reaction" in tokens(row, "qualities")) and not cue_words.search(text):
            checks.append(("reaction_without_explicit_cue", "REVIEW", "Reaction label has no explicit external cue in supplied guidance. Absence is not proof of an incorrect label."))
        if "grip" in tags and not re.search(r"grip|pinch|squeeze|towel|hang|carry|hold|climb|gi\b|rope|wrist", text, re.I):
            checks.append(("grip_objective_vs_requirement", "REVIEW", "Grip tag may describe a demand rather than intended adaptation; inspect complete source evidence."))
        low = row.get("low_impact") is True or "low_impact" in tags
        if low and row.get("impact_cost") == "high":
            checks.append(("low_impact_vs_high_cost", "CORRECT", "Explicit low-impact flag/tag and explicit high impact_cost disagree; direction of correction needs review."))
        if row.get("low_eccentric") is True and row.get("eccentric_cost") == "high":
            checks.append(("low_eccentric_vs_high_cost", "CORRECT", "Explicit low-eccentric flag and high eccentric cost disagree."))
        if row.get("support_only") is True and row.get("meaningful_stress") is True:
            checks.append(("support_vs_meaningful_stress", "REVIEW", "Support-only and meaningful stress are both true; check anchor governance semantics."))
        if row.get("system") in {"hypertrophy", "cognitive"}:
            checks.append(("non_energy_system", "RECLASSIFY", "This system describes an adaptation or activity domain, not an energy system; runtime support-alias rules must be preserved."))
        if "mech_reactive" in risks and not re.search(r"jump|bound|hop|sprint|run|footwork|shuffle|skip|rebound|pogo|landing|sprawl|shuttle", text, re.I):
            checks.append(("reactive_mechanics_without_loading_evidence", "REVIEW", "Reactive loading tag lacks an explicit lower-body rebound/loading description. Cognitive reaction cannot establish it."))
        if "mech_landing_impact" in risks and re.search(r"rope|bike|rower|swim|pool", text, re.I) and not re.search(r"jump|bound|hop|sprint|run|skip|landing|sprawl", text, re.I):
            checks.append(("landing_tag_without_landing_description", "REVIEW", "Stationary/low-impact modality has landing risk without described landing; tag provenance requires review."))
        if row.get("movement") == "eccentric" and row.get("low_eccentric") is True:
            checks.append(("eccentric_method_low_eccentric_claim", "REVIEW", "Eccentric movement paired with low_eccentric; dose may justify low cost but evidence is missing."))
        if row.get("system") == "aerobic" and "glycolytic" in tags or row.get("system") == "glycolytic" and "aerobic" in tags:
            checks.append(("mixed_energy_signals", "REVIEW", "System and tag declare different energy emphasis; mixed programming may be valid."))
        if row.get("cns_freshness") is True and row.get("cns_load") == "high":
            checks.append(("freshness_vs_high_cns", "REVIEW", "Freshness flag and high CNS load coexist; dose may make a primer legitimate, so intent is not proof of low demand."))
        if type(row.get("rpe")) in {int, float} and type(row.get("rpe_max")) in {int, float} and row["rpe"] > row["rpe_max"]:
            checks.append(("rpe_exceeds_ceiling", "CORRECT", "Declared RPE exceeds explicit rpe_max; resolve the authoritative dose before changing either."))
        if all(type(row.get(f)) in {int, float} and row[f] > 0 for f in ("work_sec", "rounds", "total_minutes")) and row["work_sec"] * row["rounds"] / 60 > row["total_minutes"] + .02:
            checks.append(("duration_less_than_active_work", "REVIEW", "total_minutes is shorter than work_sec times rounds. Check units, per-side structure and whether duration means active or elapsed time; do not infer a replacement."))
        equipment = tokens(row, "equipment")
        if (row.get("equipment") == [] or equipment <= {"bodyweight", "none"} and equipment) and re.search(r"pull.up|towel|barbell|dumbbell|kettlebell|medicine ball|band.resisted|weighted", row["name"], re.I):
            checks.append(("no_equipment_vs_named_setup", "REVIEW", "Explicit no-equipment/bodyweight classification conflicts with named setup; bodyweight loading is not absence of apparatus."))
        for field, value in row.items():
            if isinstance(value, list) and field in CLASSIFICATION | SAFETY | {"equipment", "phases"}:
                duplicate = [json.loads(v) for v, n in Counter(dumps(v) for v in value).items() if n > 1]
                if duplicate:
                    checks.append(("repeated_array_value:" + field, "CORRECT", "Repeated identical raw values in one array: " + json.dumps(duplicate)))
        if entry["content_class"] == "rehabilitation":
            for field in ("rehab_stage", "function", "dose", "pain_ceiling", "contact_level"):
                if row.get(field) is None:
                    checks.append(("unresolved_clinical_metadata:" + field, "REVIEW", "Null/absent clinical declaration remains unresolved; do not infer permissive defaults."))
        for rule, action, explanation in checks:
            findings.append({"rule": rule, "catalogue_id": entry["catalogue_id"], "source": entry["source"],
                             "name": entry["name"], "recommendation": action, "explanation": explanation,
                             "confidence": "high" if action in {"CORRECT", "RECLASSIFY"} else "screening_only",
                             "manual_review_required": True, "evidence_pointer": entry["source_pointer"],
                             "row_sha256": entry["row_sha256"]})
    return sorted(findings, key=lambda r: (r["rule"], r["catalogue_id"]))


def dependencies(fields, root, review):
    workflows = review["consumer_workflows"]
    refs, literals, constants, dynamic, imports, contracts = scan_code(root, fields, {f for w in workflows for f in w["fields"]})
    for workflow in workflows:
        text = (root / workflow["file"]).read_text(encoding="utf-8")
        if workflow["file"].endswith(".py"):
            tree = ast.parse(text)
            locations = [n.lineno for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == workflow["function"]]
        else:
            # Reviewed TS functions get precise receipts; the automated text
            # scan still makes no claim of TypeScript dataflow analysis.
            pattern = r"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?function\s+" + re.escape(workflow["function"]) + r"\b"
            locations = [text.count("\n", 0, m.start()) + 1 for m in re.finditer(pattern, text)]
        if not locations:
            raise ValueError("Stale reviewed consumer: " + str(workflow))
        workflow["line"] = locations[0]
    definition_records = [{"record_id": c["file"] + ":" + c["symbol"], "source": c["file"], "pointer": str(c["line"]), "raw": {c["symbol"]: c["raw"]}}
                          for c in constants if c["file"].startswith("fightcamp/") or c["file"] in {w["file"] for w in workflows if w["safety_sensitive"]}]
    definition_fields = field_inventory(definition_records, config=True)
    fields = {**fields, **{"definition." + f: v for f, v in definition_fields.items()}}
    mapping = {}
    used_literal_tokens = {v["raw"] for record in fields.values() for v in record["values"] if isinstance(v["raw"], str)}
    used_literal_tokens.update(f.split(".")[-1] for f in fields)
    ref_ids = defaultdict(list)
    for i, ref in enumerate(refs):
        ref_ids[ref["field"]].append(i)
    for field, values in fields.items():
        name = field.removeprefix("group.").split(".")[-1]
        reads = ref_ids[name]
        bridge = [i for i, w in enumerate(workflows) if name in w["fields"]]
        generic = [i for i, w in enumerate(workflows) if "*" in w["fields"]] if not field.startswith(("config.", "definition.")) else []
        mapping[field] = {"reference_ids": reads, "reviewed_workflow_ids": bridge, "generic_retention_workflow_ids": generic,
                          "comparison_modes": sorted({mode for i in bridge for mode in workflows[i]["usage"]}),
                          "status": "reviewed_family_consumer" if bridge else "syntactic_references_require_review" if reads else "retained_or_configured_semantic_use_unresolved",
                          "values": [{"raw": v["raw"], "exact_literal_reference_token": v["raw"] if isinstance(v["raw"], str) else None,
                                      "usage": "field_consumer_applies; absence_of_literal_does_not_mean_unused"} for v in values["values"]]}
    paths = production_paths(root)
    source_refs = {}
    config_sources = sorted({r["source"].removeprefix("data/") for r in configuration_records(root)})
    for source in (*SOURCE_CLASSES, *config_sources, "rehab_archive/exact_duplicates.json", "footwork_conditioning_bank.json"):
        basename = Path(source).name
        source_refs[source] = [{"file": p, "line": i, "evidence": line.strip()[:350]} for p in paths
                               for i, line in enumerate((root / p).read_text(encoding="utf-8-sig").splitlines(), 1) if basename in line]
    return {"method": "AST literal getters/subscripts/attributes + text receipts + reviewed workflows; not whole-program dataflow",
            "fields": mapping, "references": refs, "reviewed_workflows": workflows,
            "literal_reference_index": {token: sorted(literals.get(token, []), key=lambda x: (x["file"], x["line"])) for token in sorted(used_literal_tokens)},
            "dynamic_getters": dynamic, "policy_constants": constants, "source_references": source_refs,
            "production_files_scanned": paths, "imports": imports, "schema_contracts": contracts,
            "definition_records": definition_records, "definition_fields": definition_fields,
            "limitations": ["A syntactic read may refer to an athlete/event rather than a bank row; inspect its evidence and reviewed workflow.",
                            "Literal occurrences alone do not establish an exact comparison. Reviewed workflows specify comparison/normalisation/ranking behaviour.",
                            "All catalogue fields are retained/hashed; no value is declared unused from absence in literal comparisons."]}


def goal_report(entries, fields):
    # Invoke the existing search adapter only to observe current facets. It never
    # writes sources. This is intentionally separate from raw extraction.
    from api.services.training_library import _prepare
    training = [e for e in entries if e["content_class"] in PHYSICAL_CLASSES]
    rows = []
    for source in SOURCE_CLASSES:
        selected = [e for e in training if e["source"] == source]
        if not selected:
            continue
        rows.append({"source": source, "entries": len(selected),
                     "explicit_goals": sum(bool(tokens(e["raw"], "goals")) for e in selected),
                     "usable_goal_facets": sum(bool(_prepare(e)["facets"]["goal"]) for e in selected),
                     "other_evidence": {f: sum(bool(tokens(e["raw"], f)) for e in selected) for f in ("method", "system", "qualities", "tactical_function", "weaknesses", "tags")}})
    evidence = [{"catalogue_id": e["catalogue_id"], "name": e["name"],
                 "explicit": sorted(tokens(e["raw"], "goals")), "current_facets": sorted(_prepare(e)["facets"]["goal"]),
                 "source_evidence": {f: e["raw"][f] for f in ("method", "system", "qualities", "tactical_function", "weaknesses") if f in e["raw"]}}
                for e in training]
    return {"training_entries": len(training), "usable_goal_facets": sum(r["usable_goal_facets"] for r in rows),
            "explicit_goal_entries": sum(r["explicit_goals"] for r in rows),
            "explicit_values": [{"raw": v["raw"], "frequency": v["frequency"]} for v in fields["goals"]["values"]],
            "by_source": rows, "entries": evidence,
            "evidence_policy": ["Explicit goals are declarations, not clinical/performance certification.",
                                "Reviewed aliases and context conjunctions explain current facets; discovery CONCEPTS do not create goals.",
                                "Method/system/qualities/tactical_function can support a reviewed candidate goal, never automatic assignment.",
                                "Equipment, mech_* risks, phase, intensity and generic grip/reaction labels alone do not verify goals.",
                                "injury_prevention requires qualified review; readiness/mobility/balance on generic support rows needs per-row evidence."]}


def make_issue(field, values, reason, entries, deps, *, action="REVIEW", canonical=None, confidence="screening_only", evidence=None, ids=None, risk=None):
    if ids is None:
        ids = sorted({e["catalogue_id"] for e in entries if any(v in tokens(e["raw_group"] or {}, field[6:]) if field.startswith("group.") else v in tokens(e["raw"], field) for v in values)})
    by_id = {e["catalogue_id"]: e for e in entries}
    affected = [by_id[i] for i in ids]
    consumer = deps["fields"].get(field, {})
    workflows = consumer.get("reviewed_workflow_ids", [])
    safety = any(deps["reviewed_workflows"][i]["safety_sensitive"] for i in workflows)
    return {"issue_id": "MI-" + content_hash([field, values, reason, ids])[:12],
            "metadata_family": family(field), "field": field, "existing_values": values,
            "affected_source_files": sorted({e["source"] for e in affected}), "affected_entries": len(affected),
            "affected_entry_ids": ids, "example_exercise_ids": ids[:6], "current_meaning": reason,
            "consumer_dependencies": {"reference_ids": consumer.get("reference_ids", []), "reviewed_workflow_ids": workflows},
            "proposed_canonical_representation": canonical, "recommended_action": action,
            "risk_level": risk or ("high" if safety or field in SAFETY else "medium"),
            "supporting_evidence": evidence or [{"catalogue_id": e["catalogue_id"], "pointer": e["source_pointer"], "row_sha256": e["row_sha256"]} for e in affected[:6]],
            "confidence": confidence, "manual_review_required": field in {"target_regions", "target_tissues", "group.location", "group.type"} or action not in {"MERGE", "RENAME", "PRESERVE"} or confidence != "high",
            "verification": "Resolve dependencies, preserve IDs through reviewed manifest rebinding, compare eligibility/score/phase/clinical outputs before and after; no change authorised by this report."}


def build_reports(root=ROOT):
    before = snapshot(root)
    baseline = json.loads((root / "tools" / BASELINE.name).read_bytes())
    if before != baseline:
        raise ValueError("Baseline banks, identities, or production sources changed; audit against a reviewed new baseline")
    review = json.loads(REVIEW.read_bytes())
    entries = build_catalogue(root / "data")
    records = [{k: e[k] for k in ("catalogue_id", "source", "source_pointer", "name", "content_class", "row_sha256", "raw", "raw_group")} for e in entries]
    fields = field_inventory(records)
    configs = configuration_records(root)
    cfg_fields = field_inventory(configs, config=True)
    deps = dependencies({**fields, **{"config." + f: v for f, v in cfg_fields.items()}}, root, review)
    alias_collisions = []
    for constant in deps["policy_constants"]:
        value = constant["raw"]
        if not any(term in constant["symbol"] for term in ("NORMALIZER", "ALIASES", "SYNONYMS")) or not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            continue
        aliases = defaultdict(dict)
        for key, target in value.items():
            aliases[word_key(key)][key] = target
        for key, targets in aliases.items():
            if len(set(targets.values())) > 1:
                alias_collisions.append({"file": constant["file"], "line": constant["line"], "symbol": constant["symbol"],
                                         "input_comparison_key": key, "raw_mapping": targets, "recommendation": "REVIEW"})
    pairs = candidates(fields)
    config_pairs = candidates({f: v for f, v in cfg_fields.items() if f.split(".")[-1] in CLASSIFICATION | SAFETY | {"equipment"}})
    accuracy_rows = accuracy(entries)
    issues = []
    for source, meaning in (
        ("coordination_bank.json", "Empty compatibility shim is still referenced by conditioning, injury-bank collection and Stage 2 identity lookup. Preserve it until every reader has a tested replacement."),
        ("rehab_archive/exact_duplicates.json", "Historical completion identity recovery still reads archived drills. Exclude archive rows from the live inventory while preserving their original IDs and evidence."),
    ):
        issue = make_issue("source_file", [source], meaning, entries, deps, action="PRESERVE",
                           canonical="retain existing compatibility/history binding", confidence="high", ids=[], risk="high",
                           evidence=deps["source_references"][source])
        issue.update({"affected_source_files": ["data/" + source], "manual_review_required": True,
                      "consumer_dependencies": {"source_reference_key": source, "report": "consumers.json"},
                      "count_scope": "zero live entries; compatibility envelope or excluded historical evidence"})
        issues.append(issue)
    for collision in alias_collisions:
        issue = make_issue("goals" if "GOAL" in collision["symbol"] else "tags", list(collision["raw_mapping"]),
                           "Case/separator-equivalent normaliser inputs map to different targets; current behaviour may be intentional and needs consumer review.",
                           entries, deps, ids=[], evidence=[collision], confidence="high")
        issue.update({"affected_source_files": [collision["file"]], "affected_configuration_records": 1,
                      "normaliser_symbol": collision["symbol"], "manual_review_required": True})
        issues.append(issue)
    for pair in pairs:
        reviewed = next((r for r in review["value_decisions"] if r["field"] == pair["field"] and sorted(r["values"]) == sorted(pair["values"])), None)
        issues.append(make_issue(pair["field"], pair["values"], (reviewed or {}).get("meaning", pair["candidate_reason"]), entries, deps,
                                 action=(reviewed or {}).get("action", "SPLIT" if pair["candidate_reason"] == "compound_or_separator" else "REVIEW"),
                                 canonical=(reviewed or {}).get("canonical"), confidence=(reviewed or {}).get("confidence", "screening_only"),
                                 evidence=(reviewed or {}).get("evidence")))
    for decision in review["value_decisions"]:
        if not any(i["field"] == decision["field"] and sorted(i["existing_values"]) == sorted(decision["values"]) for i in issues):
            issues.append(make_issue(decision["field"], decision["values"], decision["meaning"], entries, deps,
                                     action=decision["action"], canonical=decision.get("canonical"), confidence=decision["confidence"], evidence=decision["evidence"]))
    for pair in config_pairs:
        field = "config." + pair["field"]
        value_refs = [v for v in cfg_fields[pair["field"]]["values"] if v["raw"] in pair["values"]]
        record_ids = sorted({o["identity"] for v in value_refs for o in v["occurrences"]})
        sources = sorted({s for v in value_refs for s in v["source_frequencies"]})
        issue = make_issue(field, pair["values"], "Configuration/review evidence " + pair["candidate_reason"], entries, deps, ids=[])
        issue.update({"affected_source_files": sources, "affected_configuration_records": len(record_ids),
                      "affected_configuration_record_ids": record_ids,
                      "supporting_evidence": [{"field": field, "raw_values_preserved": True, "source_records": record_ids[:6]}]})
        issues.append(issue)
    grouped = defaultdict(list)
    for finding in accuracy_rows:
        grouped[finding["rule"]].append(finding)
    for rule, findings in sorted(grouped.items()):
        field = rule.split(":", 1)[1] if ":" in rule else {
            "reaction_without_explicit_cue": "tags", "grip_objective_vs_requirement": "tags",
            "low_impact_vs_high_cost": "impact_cost", "low_eccentric_vs_high_cost": "eccentric_cost",
            "support_vs_meaningful_stress": "meaningful_stress", "non_energy_system": "system",
            "reactive_mechanics_without_loading_evidence": "mechanical_risk_tags",
            "landing_tag_without_landing_description": "mechanical_risk_tags", "eccentric_method_low_eccentric_claim": "low_eccentric",
            "mixed_energy_signals": "system", "no_equipment_vs_named_setup": "equipment",
            "freshness_vs_high_cns": "cns_load", "rpe_exceeds_ceiling": "rpe_max",
            "duration_less_than_active_work": "total_minutes",
        }[rule]
        ids = sorted({f["catalogue_id"] for f in findings})
        values = sorted({dumps(e["raw"].get(field)) for e in entries if e["catalogue_id"] in ids})
        issues.append(make_issue(field, [json.loads(v) for v in values], findings[0]["explanation"], entries, deps,
                                 action=findings[0]["recommendation"], confidence=findings[0]["confidence"],
                                 ids=ids, evidence=[{"rule": rule, "accuracy_report": "accuracy.json", "findings": len(findings)}]))
    goals = goal_report(entries, fields)
    for source in SOURCE_CLASSES:
        missing = [e for e in entries if e["source"] == source and e["content_class"] in PHYSICAL_CLASSES
                   and not tokens(e["raw"], "goals")]
        if not missing:
            continue
        evidence_fields = [f for f in ("method", "system", "qualities", "tactical_function", "weaknesses")
                           if any(tokens(e["raw"], f) for e in missing)]
        issues.append(make_issue("goals", [], "Missing explicit Goal in " + source + "; source evidence supports review candidates, not automatic assignment.",
                                 entries, deps, ids=[e["catalogue_id"] for e in missing],
                                 evidence=[{"source": source, "candidate_evidence_fields": evidence_fields, "entry_evidence_report": "goals.json",
                                            "excluded_evidence": "equipment, anatomical region, mech_* and discovery synonyms alone"}]))
    for field in ("avoid_if", "contraindications", "block_if_fight_within_days", "priority_score", "late_fight_score"):
        if field in fields and not deps["fields"][field]["reference_ids"]:
            affected = [e["catalogue_id"] for e in entries if field in e["raw"]]
            issues.append(make_issue(field, [v["raw"] for v in fields[field]["values"]],
                                     "Present in source rows but no named semantic reader found after production/configuration scan. Generic catalogue retention and dynamic use remain possible; enforcement or ranking is not established.",
                                     entries, deps, ids=affected,
                                     evidence=[{"field": field, "scan_report": "consumers.json", "generic_retention": True, "unused_claim": False}]))
    # Registry-only values may be generated/inferred or consumed by runtime
    # constants. Never equate absent source occurrence with an unused value.
    from fightcamp.tagging import normalize_tag
    registry = json.loads((root / "data/tag_vocabulary.json").read_bytes())
    raw_tags = {v["raw"] for v in fields["tags"]["values"] if isinstance(v["raw"], str)}
    canonical_tags = {normalize_tag(v) for v in raw_tags}
    vocabulary_candidates = [{"raw": v, "normalised_by_current_runtime": normalize_tag(v),
                              "has_normalised_live_equivalent": normalize_tag(v) in canonical_tags,
                              "status": "not_declared_in_live_rows; inferred/dynamic/configuration use still possible"}
                             for v in registry if v not in raw_tags]
    if vocabulary_candidates:
        issue = make_issue("tags", [v["raw"] for v in vocabulary_candidates],
                           "Vocabulary declarations without an exact raw live-row occurrence; not proven unused. Inspect normalised aliases, inference rules, scoring maps and historical consumers before any retirement.",
                           entries, deps, ids=[], evidence=[{"source": "data/tag_vocabulary.json", "candidate_report": "redundancy.json:vocabulary_candidates"}])
        issue["affected_source_files"] = ["data/tag_vocabulary.json"]
        issue["affected_configuration_records"] = len(vocabulary_candidates)
        issues.append(issue)
    confirmed = [i for i in issues if i["recommended_action"] == "MERGE" and i["confidence"] == "high"]
    suspected = [p for p in pairs if p["candidate_reason"] != "compound_or_separator" and any(
        i["field"] == p["field"] and i["existing_values"] == p["values"] and i["recommended_action"] == "REVIEW" for i in issues)]
    summary = {
        "live_entries": len(entries), "banks": before["banks"], "metadata_fields_including_identity_guidance_group_nested": len(fields),
        "entry_root_fields": len({k for e in entries for k in e["raw"]}),
        "training_distinct_tags": len({v for e in entries if e["content_class"] in PHYSICAL_CLASSES for v in tokens(e["raw"], "tags")}),
        "distinct_values_by_field": {f: v["distinct_raw_values"] for f, v in fields.items()},
        "configuration_records": len(configs), "configuration_fields": len(cfg_fields),
        "policy_definition_records": len(deps["definition_records"]), "policy_definition_value_paths": len(deps["definition_fields"]),
        "normaliser_alias_collisions": len(alias_collisions),
        "confirmed_synonym_groups": len(confirmed), "suspected_duplicate_groups": len(suspected),
        "confirmed_format_variant_groups": sum(i["recommended_action"] == "RENAME" and i["confidence"] == "high" for i in issues),
        "entries_with_exact_repeated_array_tokens": len({f["catalogue_id"] for f in accuracy_rows if f["rule"].startswith("repeated_array_value:")}),
        "compound_or_separator_values": sum(p["candidate_reason"] == "compound_or_separator" for p in pairs),
        "configuration_duplicate_or_compound_candidates": len(config_pairs),
        "accuracy_findings": len(accuracy_rows),
        "questionable_exercise_assignments_unique_entries": len({f["catalogue_id"] for f in accuracy_rows if not f["rule"].startswith("unresolved_clinical_metadata:")}),
        "clinical_missing_unique_entries": len({f["catalogue_id"] for f in accuracy_rows if f["rule"].startswith("unresolved_clinical_metadata:")}),
        "accuracy_by_rule": dict(sorted(Counter(f["rule"] for f in accuracy_rows).items())),
        "confirmed_unused_values": 0,
        "vocabulary_without_exact_live_source_occurrence": len(vocabulary_candidates),
        "fields_without_reviewed_semantic_consumer": [f for f in fields if not deps["fields"][f]["reviewed_workflow_ids"]],
        "unused_status": "No unused claim made: generic/dynamic consumers preserve values; constant-only or missing reads require review.",
        "obsolete_sources_still_referenced": ["coordination_bank.json (zero-row compatibility shim)", "rehab_archive/exact_duplicates.json (historical completion identity; excluded from live inventory)"],
        "safety_critical_reviewed_dependencies": sum(w["safety_sensitive"] for w in deps["reviewed_workflows"]),
        "remediation_issues": len(issues), "actions": dict(sorted(Counter(i["recommended_action"] for i in issues).items())),
        "goal_coverage": {k: goals[k] for k in ("training_entries", "explicit_goal_entries", "usable_goal_facets", "by_source", "explicit_values")},
        "limitations": ["Semantic rules are screens; rows not flagged are not certified accurate.",
                        "Static scans plus reviewed consumer families are evidence, not a proof that every dynamic branch executes.",
                        "No live database, clinician assessment, production deployment or exhaustive sport-specific efficacy ground truth was queried."]}
    reports = {
        "inventory.json": {"method": "raw values, no splitting/normalisation; frequencies count occurrences, identities deduplicate affected entries",
                           "entries": records, "fields": fields, "configuration_records": configs, "configuration_fields": cfg_fields,
                           "source_envelope_metadata": {"coordination_bank.json": json.loads((root / "data/coordination_bank.json").read_bytes())},
                           "excluded_sources": review["excluded_sources"]},
        "redundancy.json": {"candidate_policy": "Naming similarity never establishes equivalence; every candidate has a register decision.", "candidates": pairs,
                            "configuration_candidates": config_pairs,
                            "normaliser_alias_collisions": alias_collisions,
                            "vocabulary_candidates": vocabulary_candidates,
                            "confirmed_synonym_issue_ids": [i["issue_id"] for i in confirmed]},
        "consumers.json": deps,
        "accuracy.json": {"method": "Evidence screens, not automatic corrections; full raw evidence in inventory.json", "findings": accuracy_rows},
        "remediation.json": {"investigation_only": True, "issues": sorted(issues, key=lambda i: (i["field"], i["issue_id"]))},
        "goals.json": goals, "summary.json": summary,
    }
    if before != snapshot(root):
        raise ValueError("Audit mutated banks, identities, or production files")
    return reports


def markdown(reports):
    s = reports["summary.json"]
    lines = ["# Unlxck metadata integrity — PR 1", "", "Investigation only. Baseline: Main `a91b0be3593b6887162866c19712ab087392d459`, after #2816, #2818 and #2820. No catalogue identity, source bank, generator, search rule, injury rule, schema or environment is changed.", "",
             f"All **{s['live_entries']:,} entries** are accounted for across 14 explicitly enumerated live sources. The zero-row coordination shim is retained in the source inventory. "
             f"Extraction audits **{s['entry_root_fields']} row fields**, **{s['metadata_fields_including_identity_guidance_group_nested']} field paths including group context/nested dose**, "
             f"and **{s['configuration_fields']} configuration field paths** in **{s['configuration_records']} records**. Prose, identity and evidence are included, not treated as taxonomy tokens.", "",
             f"The policy trace additionally retains **{s['policy_definition_records']} code-definition records** and **{s['policy_definition_value_paths']} definition value paths**, plus typed model annotations and constraints. Those paths include definition names/keys and are not extra exercise fields. Training has {s['training_distinct_tags']} distinct raw tags; all catalogue content has {s['distinct_values_by_field']['tags']}.", "",
             "| Finding | Count | Meaning |", "| --- | ---: | --- |",
             f"| Confirmed synonym groups | {s['confirmed_synonym_groups']} | High-confidence reviewed MERGE decisions; not approval to edit consumers |",
             f"| Confirmed format variants | {s['confirmed_format_variant_groups']} | High-confidence RENAME groups; clinical joins still need migration review |",
             f"| Repeated identical risk/list tokens | {s['entries_with_exact_repeated_array_tokens']} | Affected entries; dose ranges are not deduplicated |",
             f"| Suspected duplicate groups | {s['suspected_duplicate_groups']} | Similar spelling/order/plurality only; unresolved |",
             f"| Compound/separator values | {s['compound_or_separator_values']} | Raw string retained; separators do not establish AND/OR |",
             f"| Questionable assignments | {s['questionable_exercise_assignments_unique_entries']} | Unique flagged rows excluding missing clinical metadata; screens require review |",
             f"| Incomplete clinical declarations | {s['clinical_missing_unique_entries']} | Unique rehab rows with at least one screened null clinical field |",
             f"| Confirmed unused values | {s['confirmed_unused_values']} | No unsupported unused claim |",
             f"| Vocabulary without raw live occurrence | {s['vocabulary_without_exact_live_source_occurrence']} | May be inferred/normalised/configured; requires review |",
             f"| Normaliser alias collisions | {s['normaliser_alias_collisions']} | Equivalent-looking inputs map to different targets; semantics require review |",
             f"| Referenced obsolete/historical sources | {len(s['obsolete_sources_still_referenced'])} | Compatibility and historical identity still consumed |",
             f"| Safety-critical dependencies | {s['safety_critical_reviewed_dependencies']} | Reviewed workflow/function boundaries, not number of token mentions |",
             f"| Register issues | {s['remediation_issues']} | {json.dumps(s['actions'], sort_keys=True)} |", "",
             "## Live sources", "", "| Source | Entries | SHA256 (LF-normalised) |", "| --- | ---: | --- |"]
    for source, bank in s["banks"].items():
        lines.append(f"| {source} | {bank['entries']} | `{bank['sha256']}` |")
    lines += ["", "## Distinct raw values by field", "", "Counts include explicit null/empty sentinels as values; `inventory.json` also separates nonempty counts and states. Group values count affected drills, not independent exercises. Configuration counts are separate, so policy arrays cannot inflate the 2,855 entry baseline.", "", "| Field | Distinct raw values | Family |", "| --- | ---: | --- |"]
    for field, values in reports["inventory.json"]["fields"].items():
        lines.append(f"| {field} | {values['distinct_raw_values']} | {values['family']} |")
    lines += ["", "## Goal coverage", "", f"Existing usable Goal facets are **{s['goal_coverage']['usable_goal_facets']}/1,010**. Only **{s['goal_coverage']['explicit_goal_entries']} entries** declare `goals`. The remainder of current facets come from reviewed source aliases and the lower-body/explosive and defensive-function conjunctions in `training_library._prepare`. The 57 discovery concepts are separate and do not create goals.", "",
              "| Bank | Training rows | Explicit goals | Current Goal facets |", "| --- | ---: | ---: | ---: |"]
    for row in s["goal_coverage"]["by_source"]:
        lines.append(f"| {row['source']} | {row['entries']} | {row['explicit_goals']} | {row['usable_goal_facets']} |")
    lines += ["", "Existing explicit goals: " + ", ".join(f"`{v['raw']}` ({v['frequency']})" for v in s["goal_coverage"]["explicit_values"]) + ".",
              "", "`method` can support strength/power candidates, `system` endurance emphasis, `qualities` cue-response/control candidates, and `tactical_function` specific movement intent. These need exercise instructions and dose/context review. A keyword, equipment requirement, mechanical risk, broad sport tag or synonym alone cannot verify a goal. `injury_prevention` needs qualified review. Unknown is preferable to unsupported completeness.", "",
              "## Confirmed decisions and safeguards", ""]
    for issue in reports["remediation.json"]["issues"]:
        if issue["confidence"] == "high" and issue["recommended_action"] in {"MERGE", "RENAME", "PRESERVE", "PARENT/SUBTYPE", "RECLASSIFY"}:
            lines.append(f"- `{issue['issue_id']}` **{issue['recommended_action']}** `{issue['field']}` {json.dumps(issue['existing_values'])}: {issue['current_meaning']} ({issue['affected_entries']} rows).")
    lines += ["", "`accuracy.json` retains every screened association with a stable identity, raw row hash and source pointer. Read it alongside the full raw row/group in `inventory.json`; no screen repairs a tag. Reaction cue omissions, grip demand, low-cost eccentric work and mixed energy emphasis may be legitimate. Landing/reactive risk on stationary rope drills and no-equipment pull-ups need priority review because they can affect eligibility and restrictions.", "",
              "## Consumer evidence", "", "`consumers.json` provides file/function/line receipts, reviewed workflow semantics, exact raw literal occurrences, dynamic getters, policy constants, source references and production import receipts. Register issues refer to those arrays by index. A literal mention is not automatically an exact comparison, and a missing literal is not unused: catalogue retention, generic ranking and dynamic getters still consume values.", "",
              "The legacy coordination shim remains referenced by conditioning, injury-bank collection and Stage 2 identity lookup. The historical rehab archive is used by completion evidence recovery; removal would break historical identities. Old footwork-conditioning sources are excluded; current source-reference receipts show whether any active code still names them.", "",
              "Source `avoid_if`, `contraindications`, `block_if_fight_within_days`, `priority_score` and `late_fight_score` have no named semantic reader in the scanned baseline. Generic raw retention/hash consumers remain. The register flags enforcement/ranking as unestablished rather than declaring these values unused. Case-sensitive GOAL_NORMALIZER lookup also maps `Speed` and `speed` differently before lowercasing the result; any canonicalisation must explicitly review that existing programming distinction.", "",
              "## Reproduce and verify", "", "```powershell", "python tools/audit_metadata_integrity.py", "python tools/audit_metadata_integrity.py --check", "python -m pytest tests/test_metadata_integrity_audit.py tests/test_training_catalogue.py -q", "```", "",
              "Reports contain no timestamps or absolute paths. Extraction preserves original types, strings, list order and compound values. Source hashes normalise only checkout CRLF; tests independently check raw-byte immutability around execution. Frozen source, production-file, identity and media-key baselines prevent this investigation from changing runtime behaviour. The generator comparison exercises deterministic plan text and Stage 2 before/after audit use.", "",
              "See [roadmap](roadmap.md) for ordered remediation and required before/after gates. See [verification](verification.md) for executed checks and limitations. The static scan and evidence screens do not certify every exercise scientifically or clinically; unresolved entries are explicit REVIEW decisions.", ""]
    return "\n".join(lines)


@contextmanager
def historical_sources():
    """Replay PR 1 offline, with original code receipts and reviewed bank history.

    Retained receipts preserve sources that have since evolved, including the
    custom-plan runtime and UI. Those receipts were recovered from the original
    audit commit ad82c28911103e11915a5567fc18623c056ba7d4, not current code.
    Every replay byte is checked against the original frozen hashes before extraction.
    Current production auditing remains strict and never refreshes its baseline.
    """
    baseline = json.loads(BASELINE.read_bytes())
    originals = json.loads((ROOT / "tools/metadata_integrity_original_sources.json").read_bytes())
    expected = {**baseline["production_files"], **baseline["configuration_files"],
                **{"data/" + p: v["sha256"] for p, v in baseline["banks"].items()},
                **{"data/" + p: v for p, v in baseline["identity_inputs"].items()}}
    with TemporaryDirectory(prefix="unlxck-pr1-replay-") as temporary:
        replay = Path(temporary).resolve()
        for relative, digest in sorted(expected.items()):
            target = (replay / relative).resolve()
            if not target.is_relative_to(replay):
                raise ValueError("Invalid historical source path")
            data = originals[relative].encode("utf-8") if relative in originals else original_equipment_source(relative)
            if source_hash(data) != digest:
                raise ValueError("Historical source drift: " + relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (replay / ".audit-tracked.json").write_text(dumps(sorted(expected)), encoding="utf-8")
        (replay / "tools").mkdir(exist_ok=True)
        (replay / "tools" / BASELINE.name).write_bytes(BASELINE.read_bytes())
        # The resolved directory is the explicitly created temporary workspace;
        # TemporaryDirectory cleans up only this verified directory.
        yield replay


def original_equipment_source(relative):
    """Reverse only reviewed equipment/hash edits; frozen file hashes verify bytes.

    This is audit replay, never a planner input or an identity authority.
    Unknown edits still fail the existing historical digest checks.
    """
    from tools.replay_combat_round_metadata import pre_combat_round_source
    data = reverse_mechanical_source(relative, pre_combat_round_source(relative, (ROOT / relative).read_bytes()))
    if relative == "api/contracts/external_training.py":
        # #2921 adds one response-only provenance field. Reverse only those
        # exact bytes for historical replay; historical_sources still verifies
        # the entire reconstructed file against the immutable original digest.
        field = b'    completion_origin: Literal["reported", "day_credit"] | None = None\n'
        if data.count(field) > 1:
            raise ValueError("Completion provenance contract history drift")
        return data.replace(field, b"", 1)
    if relative == "data/tag_vocabulary.json":
        from tools.check_tag_retirement import original_vocabulary_source

        # Exact reviewed retirement only; historical_sources still verifies the
        # reconstructed bytes against PR 1's immutable vocabulary digest.
        return original_vocabulary_source(data)
    if relative == "fightcamp/strength.py":
        fallback_gate = '''            if not ignore_restrictions and not evaluate_restriction_impact(
                restrictions,
                text=" ".join(str(ex.get(field, "") or "") for field in ("name", "movement", "method", "notes")),
                tags=tags,
                limit_penalty=-0.75,
            ).get("allowed", True):
                continue
'''.encode()
        if data.count(fallback_gate) != 1:
            raise ValueError("Strength fallback history drift")
        return data.replace(fallback_gate, b"")
    reviews = json.loads((ROOT / "shared/equipment-requirements.json").read_bytes())["reviews"]
    mechanical = {c["catalogue_id"]: c for c in reviewed_mechanical_changes()}
    for review in reviews:
        if review["catalogue_id"] in mechanical:
            review["row_sha256"] = mechanical[review["catalogue_id"]]["before_sha256"]
        history = review.get("source_history", [])
        if not history:
            continue
        source = review["catalogue_id"].split(":", 1)[0]
        prior = history[0]
        if relative == "data/" + source:
            rows = json.loads(data)
            row = next((r for r in rows if content_hash(r) == review["row_sha256"]), None)
            if row is None or row.get("equipment") != review["source_value"]:
                raise ValueError("Equipment source history drift: " + review["catalogue_id"])
            original = {**row, "equipment": prior["source_value"]}
            if content_hash(original) != prior["row_sha256"]:
                raise ValueError("Equipment history changes non-equipment fields")
            def encoded(value):
                return ("  " + json.dumps(value, ensure_ascii=False, indent=2).replace("\n", "\n  ")).encode()
            current_bytes = encoded(row)
            if data.count(current_bytes) != 1:
                raise ValueError("Ambiguous equipment source history")
            data = data.replace(current_bytes, encoded(original))
        elif relative == "data/training_catalogue_ids.json":
            data = data.replace(review["row_sha256"].encode(), prior["row_sha256"].encode())
    return data


def reviewed_mechanical_changes():
    """Seven explicit field deltas for historical replay, never runtime policy."""
    path = ROOT / "tools/mechanical_metadata_changes.json"
    return json.loads(path.read_bytes())["changes"] if path.exists() else []


def reverse_mechanical_source(relative, data):
    """Reconstruct Main's exact pre-correction rows; reject unrelated drift."""
    for change in reviewed_mechanical_changes():
        if relative == "data/" + change["catalogue_id"].split(":", 1)[0]:
            row = next((r for r in json.loads(data) if content_hash(r) == change["after_sha256"]), None)
            if row is None or any(row.get(k) != v for k, v in change["after"].items()):
                raise ValueError("Mechanical source history drift: " + change["catalogue_id"])
            original = {**row, **change["before"]}
            if content_hash(original) != change["before_sha256"]:
                raise ValueError("Mechanical history changes unrelated fields")
            def encoded(value):
                return ("  " + json.dumps(value, ensure_ascii=False, indent=2).replace("\n", "\n  ")).encode()
            if data.count(encoded(row)) != 1:
                raise ValueError("Ambiguous mechanical source history")
            data = data.replace(encoded(row), encoded(original))
        elif relative == "data/training_catalogue_ids.json":
            if data.count(change["after_sha256"].encode()) != 1:
                raise ValueError("Mechanical manifest history drift")
            data = data.replace(change["after_sha256"].encode(), change["before_sha256"].encode())
    return data


@contextmanager
def mechanical_baseline_sources():
    """Temporary Main inputs for complete plan comparisons, without plan dumps."""
    with TemporaryDirectory(prefix="unlxck-mechanical-before-") as temporary:
        replay = Path(temporary).resolve()
        for directory in ("fightcamp", "api", "data", "shared"):
            shutil.copytree(ROOT / directory, replay / directory,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for relative in ("data/exercise_bank.json", "data/conditioning_bank.json",
                         "data/training_catalogue_ids.json"):
            path = replay / relative
            path.write_bytes(reverse_mechanical_source(relative, path.read_bytes().replace(b"\r\n", b"\n")))
        for name in ("equipment-requirements.json", "training-metadata.json"):
            path = replay / "shared" / name
            text = path.read_text(encoding="utf8")
            for change in reviewed_mechanical_changes():
                text = text.replace(change["after_sha256"], change["before_sha256"])
            path.write_text(text, encoding="utf8")
        yield replay


def historical_library_index(*, reviewed_requirements=False):
    """Replay the frozen discovery contracts against hash-verified original rows."""
    from unittest.mock import patch
    from api.services import training_library as library
    from fightcamp.training_metadata import load_projection

    projection = load_projection()
    # PR #2822/#2823 replay predates per-entry Goal curation. Keep those frozen
    # facets and reports reproducible; live Goal corrections have their own tests.
    projection["goal_reviews"] = []
    projection["discovery_filters"] = []
    projection["facet_aliases"] = []
    projection["mappings"] = [m for m in projection["mappings"] if not m.get("discovery_expansion")]
    reviews = json.loads((ROOT / "shared/equipment-requirements.json").read_bytes())["reviews"]
    mechanical = {c["catalogue_id"]: c for c in reviewed_mechanical_changes()}
    for review in reviews:
        current_hash = review["row_sha256"]
        if review.get("source_history"):
            review.update(review.pop("source_history")[0])
        elif review["catalogue_id"] in mechanical:
            review["row_sha256"] = mechanical[review["catalogue_id"]]["before_sha256"]
        for association in projection["association_reviews"]:
            if association["row_sha256"] == current_hash:
                association["row_sha256"] = review["row_sha256"]
    with historical_sources() as replay, patch.object(library, "load_projection", return_value=projection), patch.object(
        library, "load_equipment_reviews", return_value={r["catalogue_id"]: r for r in reviews}
    ):
        paths = []
        for path in (*library.CONTRACT_FILES, library.REQUIREMENTS_FILE):
            text = path.read_text(encoding="utf8")
            if path.name == "training-metadata.json":
                text = text.split(',\n    "goal_reviews":')[0] + "\n  }\n}\n"
                # Later anatomy labels share the existing adapter, while this
                # replay must retain the exact original contract bytes.
                for mapping in load_projection()["mappings"]:
                    if mapping.get("discovery_expansion"):
                        text = text.replace(',\n      ' + json.dumps(mapping, separators=(",", ":")), "")
            for current in json.loads((ROOT / "shared/equipment-requirements.json").read_bytes())["reviews"]:
                if not current.get("source_history"):
                    continue
                prior = current["source_history"][0]
                if path == library.REQUIREMENTS_FILE:
                    old = {k: v for k, v in current.items() if k != "source_history"}
                    old.update(prior)
                    def compact(value):
                        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                    text = text.replace(compact(current), compact(old))
                else:
                    text = text.replace(current["row_sha256"], prior["row_sha256"])
            for change in mechanical.values():
                text = text.replace(change["after_sha256"], change["before_sha256"])
            target = replay / "shared" / path.name
            target.write_text(text, encoding="utf8", newline="\n")
            paths.append(target)
        with patch.object(library, "CONTRACT_FILES", tuple(paths[:-1])), patch.object(library, "REQUIREMENTS_FILE", paths[-1]):
            return library.LibraryCache(replay / "data", reviewed_requirements=reviewed_requirements).get()


def historical_reports():
    with historical_sources() as replay:
        return build_reports(replay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--historical", action="store_true", help="Replay immutable PR 1 evidence; requires --check")
    args = parser.parse_args()
    if args.historical and not args.check:
        parser.error("Historical evidence is read-only; use --historical --check")
    reports = historical_reports() if args.historical else build_reports()
    outputs = {OUT / name: report_json(report) for name, report in reports.items()}
    outputs[OUT / "README.md"] = markdown(reports)
    outputs[OUT / "roadmap.md"] = (ROOT / "tools/metadata_integrity_roadmap.md").read_text(encoding="utf-8")
    for relative, text in outputs.items():
        path = ROOT / relative
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise SystemExit("Stale audit report: " + relative.as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    s = reports["summary.json"]
    print(json.dumps({k: s[k] for k in ("live_entries", "metadata_fields_including_identity_guidance_group_nested",
                                       "configuration_fields", "confirmed_synonym_groups", "suspected_duplicate_groups",
                                       "compound_or_separator_values", "questionable_exercise_assignments_unique_entries",
                                       "remediation_issues")}, indent=2))


if __name__ == "__main__":
    main()
