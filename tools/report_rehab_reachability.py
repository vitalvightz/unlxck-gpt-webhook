"""Reproduce runtime content reachability, reusing the completed clinical audit.

Read-only. Stage content compatibility is NOT permission to enter that stage.
No literature re-audit, generated dose, metadata repair or clinical activation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fightcamp.injury_location_registry import canonicalize_location_from_registry, get_rehab_location_candidates  # noqa: E402
from fightcamp.rehab_clinical import load_clinical_policies, validate_clinical_bank  # noqa: E402
from fightcamp.rehab_selector import filter_rehab_candidates, select_rehab_candidate  # noqa: E402
from fightcamp.rehab_schema import is_surface_injury_type  # noqa: E402
from tools.rehab_metadata_review_lib import source_hash  # noqa: E402
from tools.validate_rehab_metadata_review import validate as validate_ledger  # noqa: E402

STAGES = ("calm", "restore", "load", "dynamic", "return")
INPUTS = ("data/rehab_bank.json", "data/rehab_pathways.json", "data/rehab_metadata_review.json",
          "docs/rehab-advanced-candidate-review.json")
MECHANICS = ("rehab_stage", "function", "equipment", "load", "impact", "velocity",
             "target_regions", "laterality_applicability")


def build_report():
    bank, pathways, ledger, audit = [json.loads((ROOT / p).read_text(encoding="utf-8")) for p in INPUTS]
    policies = [p for p in load_clinical_policies() if p.status == "active" and p.activation == "live"]
    errors = [*validate_clinical_bank(policies, bank), *validate_ledger(bank, ledger)]
    if errors:
        raise ValueError(errors)
    reviews = {r["drill_id"]: r for r in ledger}
    past = {r["drill_id"]: r for r in audit["candidates"]}
    inventory = {}
    for group in bank:
        for drill in group["drills"]:
            identity = drill["id"]
            if identity in inventory:
                raise ValueError("duplicate identity: " + identity)
            review = reviews.get(identity, {})
            current_hash = source_hash(drill_id=identity, location=group["location"],
                injury_type=group.get("type", "unspecified"), name=drill["name"], notes=drill["notes"])
            reviewed = review.get("review_state") == "reviewed" and review.get("source_hash") == current_hash
            inventory[identity] = dict(drill=drill, region=canonicalize_location_from_registry(group["location"]),
                injury_type=group.get("type", "unspecified"), reviewed=reviewed)
    apparatus = sorted({e for r in inventory.values() for e in (r["drill"].get("equipment") or [])})
    profiles, surfaced_all = [], set()
    for policy in sorted(policies, key=lambda p: p.policy_id):
        own = {p.drill_id: p for p in policy.prescriptions}
        candidates = [{**inventory[p.drill_id]["drill"], "injury_type": policy.injury_type,
                       "allowed_severities": p.allowed_severities} for p in policy.prescriptions]
        subject = dict(id="profile-probe", episode_id="episode-probe", athlete_id="athlete-probe",
            body_region=policy.region, body_region_aliases=get_rehab_location_candidates(policy.region),
            injury_type=policy.injury_type, side="left", severity="low")
        stages = {}
        for stage in STAGES:
            def compatible(severity="low", equipment=apparatus, side="left"):
                eligible, rejected = filter_rehab_candidates(injury={**subject, "severity": severity, "side": side},
                    rehab_stage=stage, candidates=candidates, available_equipment=equipment,
                    activated_stages=policy.live_stages)
                return eligible, rejected
            eligible_by_severity = {s: sorted(d["id"] for d in compatible(s)[0]) for s in ("low", "moderate", "high", "unknown")}
            eligible = {d["id"]: d for severity in ("low", "moderate") for d in compatible(severity)[0]}
            exact_ids = sorted(p.drill_id for p in policy.prescriptions if p.stage == stage)
            bundle = policy.stage_bundles.get(stage)
            selected_by_severity = {}
            def surfaced_options(allowed, severity, equipment):
                if bundle and set(bundle) <= {d["id"] for d in allowed}:
                    return list(bundle)
                if bundle:
                    allowed = [d for d in allowed if d["id"] not in bundle and d.get("rehab_stage") == stage]
                if not allowed:
                    return []
                priority = max(own[d["id"]].priority for d in allowed)
                ranked = select_rehab_candidate(injury={**subject, "severity": severity}, rehab_stage=stage,
                    candidates=[d for d in allowed if own[d["id"]].priority == priority],
                    available_equipment=equipment, activated_stages=policy.live_stages)
                return [ranked.selected_drill_id] if ranked.selected_drill_id else []
            for severity in ("low", "moderate"):
                allowed = compatible(severity)[0]
                surfaced = surfaced_options(allowed, severity, apparatus)
                selected_by_severity[severity] = surfaced
                surfaced_all.update(surfaced)
            # Alternative content can require different props. Full apparatus
            # alone only demonstrates the preferred option, not reachability.
            equipment_probes = []
            setups = sorted({tuple(sorted(d.get("equipment") or [])) for d in candidates})
            for setup in setups:
                ids = surfaced_options(compatible(equipment=setup)[0], "low", setup)
                surfaced_all.update(ids)
                equipment_probes.append(dict(equipment=list(setup), surfaced_ids=ids))
            incoming = next((t for t in policy.transitions if t.to_stage == stage), None)
            from api.contracts.rehab_progression import _permission_entry
            permission_entry = bool(incoming and _permission_entry(incoming, policy))
            stages[stage] = dict(
                availability="conditional_on_episode_requirements" if stage in policy.live_stages and stage == "load"
                    else "baseline_reachable" if stage in policy.live_stages else "closed",
                gate_reasons=([incoming.closed_reason] if incoming and incoming.closed_reason else
                    ["target_stage_not_activated"] if stage not in policy.live_stages else []),
                declared_requirements=[r.model_dump(exclude_none=True) for r in incoming.requirements] if incoming else [],
                permission_entry_supported=permission_entry,
                recovery_rule="improvement_then_reviewed_response" if permission_entry else "hold",
                approved_exact_ids=exact_ids, eligible_exact_ids=sorted(set(exact_ids) & eligible.keys()),
                eligible_including_protective_fallback_ids=sorted(eligible),
                eligible_by_severity=eligible_by_severity, surfaced_by_severity=selected_by_severity,
                **({"surfaced_by_equipment": equipment_probes} if setups else {}),
                bundle_ids=list(bundle or []), empty_equipment_ids=sorted(d["id"] for d in compatible(equipment=[])[0]),
                unknown_side_ids=sorted(d["id"] for d in compatible(side="unknown")[0]),
                rejections=[dict(drill_id=r.drill_id, reasons=list(r.reason_codes)) for r in compatible()[1]],
                alternative_exact_count=max(0, len(set(exact_ids) & eligible.keys()) - len(bundle or [None])))
        exact_bank = {i: r for i, r in inventory.items() if (r["region"], r["injury_type"]) == (policy.region, policy.injury_type)}
        dormant = []
        for identity, row in sorted(exact_bank.items()):
            if identity in own and own[identity].stage in policy.live_stages:
                continue
            drill, previous = row["drill"], past.get(identity, {})
            missing = [f for f in MECHANICS if drill.get(f) is None]
            blockers = ["no_approved_live_prescription"]
            if not row["reviewed"]:
                blockers.append("clinical_metadata_not_reviewed")
            if drill.get("rehab_stage") not in policy.live_stages:
                blockers.append("stage_not_authorised")
            if missing:
                blockers.append("missing_mechanical_metadata")
            if not drill.get("dose"):
                blockers.append("dose_or_self_paced_prescription_needs_approval")
            if drill.get("equipment") is None:
                blockers.append("equipment_not_defined")
            if previous.get("individual_demand_still_unknown"):
                blockers.append("individual_resistance_or_demand_not_defined")
            dormant.append(dict(drill_id=identity, reviewed=row["reviewed"], stored_stage=drill.get("rehab_stage"),
                blockers=blockers, missing_metadata=missing, equipment=drill.get("equipment"),
                prior_review_disposition=previous.get("primary_disposition"),
                prior_review_reason=previous.get("clinical_review", {}).get("reason"),
                prior_review_next_action=previous.get("recommended_next_action")))
        profiles.append(dict(policy_id=policy.policy_id, region=policy.region, injury_type=policy.injury_type,
            live_stages=list(policy.live_stages), reviewed_exact_type_count=sum(r["reviewed"] for r in exact_bank.values()),
            live_prescription_count=len(own), exact_bank_count=len(exact_bank), dormant_count=len(dormant),
            stages=stages, dormant_candidates=dormant,
            unassigned_regional_ids=sorted(i for i,r in inventory.items() if r["region"] == policy.region and r["injury_type"] == "unspecified")))
    live = {p.drill_id for policy in policies for p in policy.prescriptions if p.stage in policy.live_stages}
    exact_profile_pairs = {(p.region, p.injury_type) for p in policies}
    outside = {}
    for identity, row in inventory.items():
        if (row["region"], row["injury_type"]) in exact_profile_pairs:
            continue
        category = ("legacy_surface_inventory" if is_surface_injury_type(row["injury_type"]) else
                    "unassigned_regional_type" if row["injury_type"] == "unspecified" else "no_active_exact_profile")
        outside.setdefault(category, []).append(identity)
    return dict(schema_version=1, scope="Content compatibility with exact source apparatus, known side and supported severity; episode permission, symptoms, history and stage authorisation remain separate mandatory gates.",
        input_sha256={p: hashlib.sha256((ROOT / p).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in INPUTS},
        summary=dict(total_drills=len(inventory), reviewed=sum(r["reviewed"] for r in inventory.values()),
            active_profiles=len(profiles), live_unique_identities=len(live), dormant_unique_identities=len(inventory)-len(live),
            reviewed_dormant=sum(r["reviewed"] and i not in live for i,r in inventory.items()),
            live_by_stage=dict(Counter(p.stage for policy in policies for p in policy.prescriptions if p.stage in policy.live_stages)),
            surfaced_unique_identities=len(surfaced_all), approved_never_surfaced_ids=sorted(live-surfaced_all),
            dormant_exact_active_profile_count=sum(p["dormant_count"] for p in profiles),
            outside_active_profile_counts={k:len(v) for k,v in sorted(outside.items())},
            dormant_blocker_counts=dict(sorted(Counter(b for p in profiles for d in p["dormant_candidates"] for b in d["blockers"]).items()))),
        profiles=profiles, outside_active_profile_ids={k:sorted(v) for k,v in sorted(outside.items())})


def markdown(report):
    s = report["summary"]
    lines = ["# Runtime rehab bank reachability", "", "Generated by `python tools/report_rehab_reachability.py`; verify with `--check`.", "",
        f"{s['total_drills']} bank drills; {s['reviewed']} current reviewed identities; {s['active_profiles']} active profiles; "
        f"{s['live_unique_identities']} live prescribed identities; {s['reviewed_dormant']} reviewed but dormant. "
        f"{s['surfaced_unique_identities']} identities surface under the supported-severity/full-apparatus content probes.", "",
        "A probe tests the actual compatibility filter and selector, including priority and atomic bundles. It does not override or certify clinical stage eligibility. The published LOAD prescriptions support shared reported-clinician entry without mandatory RESTORE logs; known unresolved responses and setbacks still hold loading. DYNAMIC/RETURN and groin LOAD remain closed. Exact IDs below are current prescription IDs, not the wider bank. JSON includes derived entry/recovery support, fallbacks, severity/equipment/side results, requirements, rejection codes and each dormant candidate's missing information. Empty dose on approved self-paced baselines is intentional.", "",
        "The historical advanced review supplies planning reasons only. Current bank classification and the live catalog determine present inventory. All live profiles admit complete bank prescriptions with explicit injury compatibility; an unspecified group alone never assigns a diagnosis. Equipment probes include each routine's actual props so alternatives are not mistaken for unreachable content.", "",
        "| Profile | Reviewed / exact bank | Live / dormant | CALM IDs | RESTORE IDs | LOAD IDs | Alternatives C/R/L | Presentation |",
        "| --- | ---: | ---: | --- | --- | --- | --- | --- |"]
    for p in report["profiles"]:
        stages = p["stages"]
        ids = [", ".join(f"`{i}`" for i in stages[t]["approved_exact_ids"]) or "Closed" for t in STAGES[:3]]
        alternatives = "/".join(str(stages[t]["alternative_exact_count"]) for t in STAGES[:3])
        presentation = "Atomic RESTORE bundle" if stages["restore"]["bundle_ids"] else "One option per stage"
        lines.append(f"| {p['policy_id']} | {p['reviewed_exact_type_count']} / {p['exact_bank_count']} | {p['live_prescription_count']} / {p['dormant_count']} | " + " | ".join(ids) + f" | {alternatives} | {presentation} |")
    lines += ["", "All 64 profiles: DYNAMIC and RETURN have zero approved IDs and are closed.", "",
        "## What limits variety", "",
        "Most profiles have one published identity at a live stage. Ankle sprain retains an atomic standing RESTORE combination and now has a complete seated alternative when its support is unavailable. Chest strain has one self-paced RESTORE movement. Missing classification, a usable prescription or a supported stage keeps other bank identities dormant. The shared selector deterministically applies compatibility, priority and continuity. Frozen started/completed occurrences retain their accepted IDs and prescriptions.", "",
        f"Approved identities never surfaced by these content probes: `{s['approved_never_surfaced_ids']}`. "
        "This does not establish availability for every severity, side, equipment setup or injury episode.", "",
        "See [investigation and validation](rehab-progression-investigation.md) and [activation backlog](rehab-activation-backlog.md) for journey proof, integration defects and next work.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build_report()
    outputs = {"docs/rehab-bank-reachability.json": json.dumps(report, indent=2, sort_keys=True) + "\n",
               "docs/rehab-bank-reachability.md": markdown(report)}
    for name, value in outputs.items():
        if args.check:
            if not (ROOT / name).exists() or (ROOT / name).read_text(encoding="utf-8") != value:
                raise SystemExit("Stale reachability report: " + name)
        else:
            (ROOT / name).write_text(value, encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
