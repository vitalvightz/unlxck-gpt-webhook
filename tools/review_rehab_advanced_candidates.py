"""Render an explicit, source-backed planning review; never change runtime data.

Decisions are curated per identity, not inferred from names. Inventory drift,
missing decisions and invalid ownership fail closed pending a fresh review.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.audit_rehab_bank_rationalisation import build_audit  # noqa: E402

DISPOSITIONS = {
    'A': 'READY_FOR_CLINICAL_GATE_REVIEW',
    'B': 'REPAIR_BEFORE_GATE_REVIEW',
    'C': 'INDICATION_UNCLEAR',
    'D': 'DUPLICATE_OR_REDUNDANT_ADVANCED',
    'E': 'DEFER_LOW_VALUE',
    'F': 'DROP_AS_ADVANCED_CANDIDATE',
}
DECISIONS_PATH = ROOT / 'tools/rehab_advanced_candidate_decisions.json'
PROTECTED_PATHS = (
    'data/rehab_bank.json', 'data/rehab_metadata_review.json', 'data/rehab_pathways.json',
    'data/rehab_bank_duplicate_debt.json', 'data/rehab_archive/exact_duplicates.json',
    'data/safety/surface_wound_review.json', 'fightcamp/surface_wound_safety.py',
    'fightcamp/rehab_duplicate_archive.py', 'api/services/rehab_completion_service.py',
    'api/contracts/rehab_progression.py',
)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def file_hash(path):
    # Match Git's logical text content across Windows/Linux newline handling.
    return hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()


def build_review(bank, ledger, pathways, archive, decisions):
    audit, clusters = build_audit(bank, ledger, pathways)
    if audit['integrity_errors']:
        raise ValueError('Resolve input integrity before planning review')
    inventory = {r['drill_id']: r for r in audit['drills'] if r['classification'] == 'ADVANCED_CANDIDATE'}
    if set(inventory) != set(decisions['candidates']):
        raise ValueError('Advanced inventory changed: every candidate requires an explicit fresh decision')
    current_profiles = {p['policy_id']: p for p in pathways['profiles']}
    supporting_profiles = {p for r in inventory.values() for p in r['matching_active_profile_ids']}
    if supporting_profiles != set(decisions['profiles']):
        raise ValueError('Profile ranking must cover every exact-type candidate owner')
    for identifier, decision in decisions['profiles'].items():
        if decision['tier'] not in {1, 2, 3, 4} or decision['priority'] < 1:
            raise ValueError('Invalid profile ranking: ' + identifier)
        if not set(decision['source_ids']) <= set(decisions['evidence_sources']):
            raise ValueError('Missing profile evidence source: ' + identifier)
        if decision['tier'] <= 2 and not decision['source_ids']:
            raise ValueError('Serious targets require directly inspected evidence: ' + identifier)
    wave_ids = [w['policy_id'] for w in decisions['first_wave']]
    if len(set(wave_ids)) != len(wave_ids) or not 3 <= len(wave_ids) <= 6:
        raise ValueError('First wave must contain 3-6 unique assessed profiles')
    if any(p not in supporting_profiles or decisions['profiles'][p]['tier'] > 2 for p in wave_ids):
        raise ValueError('First wave must stay within Tier 1/2 exact-type owners')
    canonical_archive = {}
    for row in archive['records']:
        canonical_archive.setdefault(row['canonical_id'], []).append(row['retired_id'])
    candidates = []
    for identifier, row in sorted(inventory.items()):
        decision = decisions['candidates'][identifier]
        if decision['disposition'] not in DISPOSITIONS or decision['planning_stage'] not in {'load', 'dynamic', 'restore', 'uncertain'}:
            raise ValueError('Invalid candidate disposition/stage: ' + identifier)
        if decision.get('overlaps'):
            other = inventory.get(decision['overlaps'])
            if other is None or (other['canonical_region'], other['injury_type']) != (row['canonical_region'], row['injury_type']):
                raise ValueError('Redundancy comparison must stay within exact clinical ownership')
        mechanically_fixed = not any(row[k] for k in ('hidden_progression_matches', 'variable_demand_flags', 'variable_equipment_matches'))
        if decision['disposition'] == 'A' and (not mechanically_fixed or row['review_state'] != 'reviewed' or not row['matching_active_profile_ids']):
            raise ValueError('Gate-review readiness requires fixed reviewed exact-type inventory')
        candidates.append({
            **deepcopy(row),
            'primary_disposition': DISPOSITIONS[decision['disposition']],
            'disposition_code': decision['disposition'],
            'clinical_review': deepcopy(decision),
            'mechanically_fixed': mechanically_fixed,
            'mechanically_clean_for_advanced_review': mechanically_fixed and decision['disposition'] not in {'B', 'F'},
            'ownership': 'exact_region_and_type' if row['matching_active_profile_ids'] else 'regional_or_unassigned',
            'duplicate_consolidation': {'canonical_keeper': identifier in canonical_archive,
                                        'archived_surplus_ids': canonical_archive.get(identifier, [])},
            'source_content_repaired_in_this_pass': False,
            'proposed_stage_differs_from_stored': decision['planning_stage'] != row['rehab_stage'],
            'individual_demand_still_unknown': deepcopy(row['unknown_metadata_fields']),
        })
    profiles = []
    for identifier, decision in sorted(decisions['profiles'].items(), key=lambda pair: (pair[1]['tier'], pair[1]['priority'], pair[0])):
        owned = [r for r in candidates if identifier in r['matching_active_profile_ids']]
        profile = current_profiles[identifier]
        profiles.append({
            'policy_id': identifier, 'region': profile['region'], 'injury_type': profile['injury_type'],
            **deepcopy(decision),
            'candidate_ids': [r['drill_id'] for r in owned],
            'exact_type_reviewed_count': len(owned),
            'mechanically_fixed_count': sum(r['mechanically_fixed'] for r in owned),
            'mechanically_clean_count': sum(r['mechanically_clean_for_advanced_review'] for r in owned),
            'requiring_content_repair_count': sum(r['disposition_code'] == 'B' for r in owned),
            'gate_review_ready_count': sum(r['disposition_code'] == 'A' for r in owned),
            'load_shortlist_ids': [r['drill_id'] for r in owned if r['disposition_code'] == 'A' and r['clinical_review']['planning_stage'] == 'load'],
            'disposition_counts': dict(sorted(Counter(r['primary_disposition'] for r in owned).items())),
            'live_stages': deepcopy(profile['live_stages']), 'profile_hash': profile['content_hash'],
            'required_readiness_inputs_captured': False,
            'technically_evaluable': False, 'clinically_promotable': False,
            'transition_must_remain_closed': True,
        })
    return {
        'schema_version': 1, 'reviewed_at': decisions['reviewed_at'], 'base_commit': decisions['base_commit'],
        'scope': 'Planning assessment only. Clinical plausibility and tier placement are review judgments, not activation or clinician clearance.',
        'summary': {
            'advanced_candidate_count_before': len(candidates), 'advanced_candidate_count_after': len(candidates),
            'advanced_planning_candidate_count_after': sum(r['disposition_code'] != 'F' for r in candidates),
            'load_gate_review_shortlist_count': sum(r['disposition_code'] == 'A' and r['clinical_review']['planning_stage'] == 'load' for r in candidates),
            'disposition_counts': {name: sum(r['primary_disposition'] == name for r in candidates) for name in DISPOSITIONS.values()},
            'profile_count_with_candidates': len(profiles), 'active_profile_count': len(pathways['profiles']),
            'live_identity_count': audit['summary']['live_unique_drills'],
            'live_stage_counts': audit['summary']['live_unique_identities_by_stage'],
            'tier_counts': dict(sorted(Counter(p['tier'] for p in profiles).items())),
            'repaired_candidate_ids': [], 'reclassified_out_of_rationalisation_advanced': [],
            'dropped_from_planning_shortlist': [r['drill_id'] for r in candidates if r['disposition_code'] == 'F'],
            'active_profile_ids_changed': [], 'profile_hashes_changed': [], 'stages_activated': [],
            'transitions_newly_evaluable': [], 'transitions_clinically_promotable': [],
        },
        'protected_input_sha256': deepcopy(decisions['protected_input_sha256']),
        'duplicate_cluster_counts': dict(sorted(Counter(c['classification'] for c in clusters['clusters']).items())),
        'first_wave': deepcopy(decisions['first_wave']),
        'capture_assessment': deepcopy(decisions['capture_assessment']),
        'evidence_sources': deepcopy(decisions['evidence_sources']),
        'validation_results': deepcopy(decisions.get('validation_results', [])),
        'profiles': profiles, 'candidates': candidates,
    }


def markdown(report):
    s = report['summary']
    lines = ['# Advanced rehab candidate review', '',
             f"Reviewed {report['reviewed_at']} against Main `{report['base_commit']}` after #2741.", '',
             f"**{s['advanced_candidate_count_before']} audit candidates before / {s['advanced_candidate_count_after']} after; {s['advanced_planning_candidate_count_after']} remain in advanced planning, including {s['load_gate_review_shortlist_count']} ready for clinical LOAD gate review. {s['profile_count_with_candidates']} profiles have exact-type inventory.** No production content, identity, review provenance, profile hash or stage is changed. All 64 profiles and 103 LIVE identities remain CALM/RESTORE only.", '',
             'This is a clinically informed engineering shortlist, not independent clinical sign-off. A means mechanically suitable for the next clinical gate review, not safe to prescribe now. Ranking is a judgment about evidence applicability, current content, safety ambiguity and the size of the missing input work; it is not a candidate-count score.', '',
             '## Recommended first wave', '']
    lines += [f"{i}. **{w['policy_id']}** — {w['reason']}" for i, w in enumerate(report['first_wave'], 1)]
    lines += ['', 'These are targets for scoped clinical/input work, not an activation batch. Start with Achilles and lateral-elbow subtype assessment. Ankle, shoulder and groin are conditional second steps. Tendon loading has the strongest direct guideline support here, but broad tendon labels cannot supply diagnosis or resistance selection; calf strain is not promoted just because tendon criteria exist.', '',
              '## Dispositions and scope', '', '| Code | Disposition | Count |', '| --- | --- | ---: |']
    lines += [f'| {code} | {name} | {s["disposition_counts"][name]} |' for code, name in DISPOSITIONS.items()]
    lines += ['', 'No candidate was repaired: the high-value instructions are already fixed. Unknown external resistance is an honest individual assessment gap, not a value to invent. Lower-priority misleading names, equipment constraints and restaging questions stay explicit follow-up work. F removes an item from this planning shortlist only; the rationalisation inventory still contains 57. D records functional overlap without merging/removing any near or uncertain duplicate. No candidate is deleted, restaged or newly approved.', '',
              'Group GPP/SPP/TAPER labels survive as historical context; candidate instructions contain no affirmative camp-driven progression. The JSON records full current instructions, every mechanical field, review/source hashes and history, exact-type profile references and #2741 keeper links. Fixed mechanics does not imply a measured load, dose, disease-specific indication or adequate variety.', '',
              '## Profile ranking', '',
              '| Profile | Tier / priority | Exact reviewed | Fixed | Clean | Repair | LOAD shortlist | Variety / main reason |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for p in report['profiles']:
        lines.append(f"| {p['policy_id']} | {p['tier']} / {p['priority']} | {p['exact_type_reviewed_count']} | {p['mechanically_fixed_count']} | {p['mechanically_clean_count']} | {p['requiring_content_repair_count']} | {len(p['load_shortlist_ids'])} | {p['variety']} {p['ranking_reason']} |")
    lines += ['', 'Tier 1 = best next gate-review targets; Tier 2 = promising with one principal additional prerequisite beyond the shared capture/prescription work; Tier 3 = substantial evidence/input/content gaps; Tier 4 = do not pursue LOAD from this set yet. Fixed counts assess one bounded execution; clean counts additionally exclude B content defects and F advanced-stage mismatches. Unknown individual resistance is listed separately and never counted as known. A single useful anchor can justify investigating a profile, but none of the Tier 1/2 sets is a complete published LOAD programme.', '',
              '## Captured data and shared blockers', '']
    capture = report['capture_assessment']
    for key in ('already_captured', 'not_currently_captured', 'history_can_supply', 'history_cannot_supply', 'small_product_addition', 'clinical_boundary'):
        lines += [f"**{key.replace('_', ' ').capitalize()}:** {capture[key]}", '']
    lines += ['The model may store numeric symptoms or demand, but storage is not capture. Current answers are categorical and cannot become numeric pain, ROM, strength or movement-quality measurements. `CAPTURED_FUNCTIONAL_CHECKPOINTS` is empty and the evaluator has no implemented checkpoint reader. This review adds neither reader nor requirements. Zero transitions become technically evaluable or clinically promotable. LOAD/DYNAMIC/RETURN stay closed.', '',
              '## Tier 1 / Tier 2 clinical and product review', '']
    sources = report['evidence_sources']
    for p in report['profiles']:
        if p['tier'] > 2:
            continue
        links = ', '.join(f"[{sources[k]['title']}]({sources[k]['url']})" for k in p['source_ids'])
        lines += [f"### {p['policy_id']} — Tier {p['tier']}", '',
                  f"**Evidence and movement fit:** {p['evidence_review']} {links}", '',
                  f"**Missing minimum inputs:** {p['missing_inputs']}", '',
                  f"**Capture route:** {p['capture_route']}", '',
                  f"**Safety and transition:** {p['safety_ambiguity']} {p['transition_review']}", '']
    lines += ['## Evidence inspection and limitations', '']
    for key, source in sources.items():
        lines += [f"- **{key}:** [{source['title']}]({source['url']}) — {source['evidence_type']}; {source['inspected_sections']}. {source['limitation']}"]
    lines += ['', 'Sources justify movement families and assessment domains, not an app-defined RESTORE→LOAD threshold. Published return-to-sport milestones are not imported as LOAD entry rules. No new checkpoint names, numbers, dose or thresholds are prescribed here. Each selected profile still needs a reviewed exact-variant dose, defined symptom/setback policy and clinician-approved transition specification. Tier 3/4 is conservative deferral where the inspected evidence does not establish the exact ownership; it is not proof that exercise is ineffective.', '',
              '## Every candidate decision', '',
              '| ID | Profile | Stored → planning stage | Decision | Rationale / follow-up |',
              '| --- | --- | --- | --- | --- |']
    for r in report['candidates']:
        d = r['clinical_review']
        lines.append(f"| {r['drill_id']} | {', '.join(r['matching_active_profile_ids']) or 'unassigned'} | {r['rehab_stage']} → {d['planning_stage']} | {r['disposition_code']} | {d['reason']} |")
    lines += ['', 'LOAD means controlled resistance/loading; DYNAMIC means impact/reactive/faster work; RETURN means sport/contact integration. No candidate in this set supports RETURN-specific approval. Planning-stage differences above are recommendations, not bank mutations. Source names may describe retired execution variants; current notes and mechanics, not names, drive these decisions.', '',
              '## Reproduction, changed files and validation', '',
              'Production files are protected by the committed Main fingerprints in the curated decision source. The review tool consumes the freshly recomputed rationalisation audit and fails if candidate coverage or profile ownership drifts. The dedicated JSON and Markdown are deterministic. The three rationalisation documents were regenerated through their own audit tool and remain byte-identical because inventory is unchanged.', '',
              'Changed files: `tools/rehab_advanced_candidate_decisions.json` (explicit review judgments and baseline), `tools/review_rehab_advanced_candidates.py` (read-only renderer), `docs/rehab-advanced-candidate-review.json`, this Markdown report, and `tests/test_rehab_advanced_candidate_review.py`.', '',
              'Run `python tools/review_rehab_advanced_candidates.py --check`, `python tools/audit_rehab_bank_rationalisation.py --check`, and `python -m pytest tests/test_rehab_advanced_candidate_review.py tests/test_rehab_bank_rationalisation.py tests/test_rehab_exact_duplicate_cleanup.py tests/test_surface_wound_safety.py -q`. Existing bank/clinical/metadata/vocabulary validators and progression/Today/completion suites validate the protected production contracts. No database migration, deployment or frontend change is required.', '']
    lines += ['### Validation results', '']
    lines += ['- ' + result for result in report['validation_results']]
    lines += ['', 'No full-repository suite, production-history query or independent clinician sign-off was performed. Existing HTTP 422 deprecation warnings remain. The 1,149 general REPAIR entries, 22 near and 27 uncertain clusters remain untouched.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'docs')
    args = parser.parse_args(argv)
    decisions = read(DECISIONS_PATH)
    if any(file_hash(ROOT / p) != h for p, h in decisions['protected_input_sha256'].items()):
        print('Protected production inputs changed; review must be renewed.')
        return 1
    report = build_review(*(read(ROOT / p) for p in ('data/rehab_bank.json', 'data/rehab_metadata_review.json',
                         'data/rehab_pathways.json', 'data/rehab_archive/exact_duplicates.json')), decisions)
    outputs = {'rehab-advanced-candidate-review.json': json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
               'rehab-advanced-candidate-review.md': markdown(report)}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in outputs.items():
        path = args.output_dir / name
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != value:
                print('Stale review output: ' + name)
                return 1
        else:
            path.write_text(value, encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
