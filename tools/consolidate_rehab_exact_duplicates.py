"""Consolidate strictly equal same-pair inventory, retaining historical identity.

One bounded migration. Subsequent runs verify the archive and do not select new
cleanup work. Clinical profiles and retained content are never rewritten.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.audit_rehab_bank_rationalisation import build_audit, input_digest  # noqa: E402
from tools.rehab_metadata_review_lib import source_hash, pathway_inventory_snapshot  # noqa: E402
from tools.validate_rehab_metadata_review import validate as validate_reviews  # noqa: E402

ARCHIVE_PATH = Path('rehab_archive/exact_duplicates.json')


def text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def digest(value):
    return hashlib.sha256(text(value).encode()).hexdigest()


def without_identity(drill):
    return {k: v for k, v in drill.items() if k != 'id'}


def review_semantics(record):
    return {k: v for k, v in record.items() if k not in {'drill_id', 'source_hash', 'source_history'}}


def history_semantics(record):
    return [{k: v for k, v in row.items() if k != 'source_hash'} for row in record.get('source_history', [])]


def exactly_interchangeable(members, review_records):
    context = [{k: v for k, v in g.items() if k != 'drills'} for _, _, g, _ in members]
    return (all(without_identity(d) == without_identity(members[0][3]) for _, _, _, d in members)
            and all(g == context[0] for g in context)
            and all(review_semantics(r) == review_semantics(review_records[0]) for r in review_records)
            and all(history_semantics(r) == history_semantics(review_records[0]) for r in review_records))


def reconstruct_original(bank, ledger, archive):
    """Recover the complete pre-migration JSON objects from retained + archived rows."""
    original_bank, original_ledger = deepcopy(bank), deepcopy(ledger)
    removed_groups = {r['original_group_index']: r['group'] for r in archive['records'] if r['group_removed']}
    for position, group in sorted(removed_groups.items()):
        original_bank.insert(position, {**deepcopy(group), 'drills': []})
    for row in sorted(archive['records'], key=lambda r: (r['original_group_index'], r['original_drill_index'])):
        original_bank[row['original_group_index']]['drills'].insert(row['original_drill_index'], deepcopy(row['drill']))
    for row in sorted(archive['records'], key=lambda r: r['original_review_index']):
        original_ledger.insert(row['original_review_index'], deepcopy(row['metadata_review']))
    return original_bank, original_ledger


def consolidate(bank, ledger, pathways, debt, *, referenced_ids=()):
    report, clusters = build_audit(bank, ledger, pathways)
    if report['integrity_errors'] or validate_reviews(bank, ledger):
        raise ValueError('Source bank/review/profile integrity must pass before consolidation')
    index = {d['id']: (gi, di, g, d) for gi, g in enumerate(bank) for di, d in enumerate(g['drills'])}
    reviews = {r['drill_id']: (i, r) for i, r in enumerate(ledger)}
    references = {rx['drill_id'] for profile in pathways['profiles'] for rx in profile['prescriptions']}
    live_ids = {r['drill_id'] for r in report['drills'] if r['referenced_by_active_profile']}
    records, rejected = [], []
    for cluster in clusters['clusters']:
        if cluster['classification'] != 'exact_duplicate':
            continue
        members = [index[i] for i in cluster['drill_ids']]
        review_records = [reviews[d['id']][1] for _, _, _, d in members]
        # Compare every drill field, complete group context, review semantics
        # and historical instruction revisions, not names or keyword matches.
        equal = exactly_interchangeable(members, review_records)
        if not equal or len(set(cluster['drill_ids']) & live_ids) > 1:
            rejected.append({'cluster_id': cluster['cluster_id'], 'classification': 'uncertain',
                             'drill_ids': cluster['drill_ids'], 'reason': 'Context/review/history differs or multiple live identities'})
            continue
        def rank(identifier):
            record = reviews[identifier][1]
            return (identifier not in live_ids, record['review_state'] != 'reviewed',
                    not bool(record.get('source_history')), identifier not in set(referenced_ids) | references,
                    bool(re.search(r'_\d+$', identifier)), identifier)
        keeper = min(cluster['drill_ids'], key=rank)
        if keeper in live_ids:
            reason = 'Retain the existing LIVE prescription identity.'
        elif reviews[keeper][1]['review_state'] == 'reviewed':
            reason = 'Equal reviewed provenance/history; retain the established unsuffixed identity.'
        else:
            reason = 'Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement.'
        for identifier in sorted(set(cluster['drill_ids']) - {keeper}):
            if identifier in references:
                raise ValueError('Never retire a profile-referenced identity: ' + identifier)
            gi, di, group, drill = index[identifier]
            records.append(dict(cluster_id=cluster['cluster_id'], canonical_id=keeper, retired_id=identifier,
                selection_reason=reason, original_group_index=gi, original_drill_index=di,
                group={k: v for k, v in group.items() if k != 'drills'}, drill=deepcopy(drill),
                original_review_index=reviews[identifier][0], metadata_review=deepcopy(reviews[identifier][1]),
                canonical_metadata_review_before=deepcopy(reviews[keeper][1]),
                active_profile_references=[], original_cluster=deepcopy(cluster)))
    retired = {r['retired_id'] for r in records}
    new_bank = [{**deepcopy(g), 'drills': [deepcopy(d) for d in g['drills'] if d['id'] not in retired]}
                for g in bank if any(d['id'] not in retired for d in g['drills'])]
    for row in records:
        row['group_removed'] = all(d['id'] in retired for d in bank[row['original_group_index']]['drills'])
    new_ledger = [deepcopy(r) for r in ledger if r['drill_id'] not in retired]
    combinations = {(g['location'], g['type'], d.get('rehab_stage'), d['name']) for g in new_bank for d in g['drills']}
    # Only shrink declared debt; preserve any combination still repeated.
    counts = {key: sum((g['location'], g['type'], d.get('rehab_stage'), d['name']) == key
                      for g in new_bank for d in g['drills']) for key in combinations}
    new_debt = {**deepcopy(debt), 'duplicates': [r for r in debt['duplicates']
        if counts.get((r['location'], r['type'], r.get('rehab_stage'), r['name']), 0) > 1]}
    if not new_debt['duplicates']:
        new_debt['note'] = 'Exact duplicate debt resolved. Original debt, retired identities and full review/source provenance are preserved in rehab_archive/exact_duplicates.json. Archived IDs are historical compatibility only, never selectable inventory. Keep this ledger empty unless separately reviewed debt is explicitly authorised.'
    archive = dict(schema_version=1, scope='Historical compatibility only; never selectable inventory or ID remapping.',
        source_input_sha256={'rehab_bank.json': digest(bank), 'rehab_metadata_review.json': digest(ledger),
                             'rehab_pathways.json': digest(pathways)},
        duplicate_debt_before=deepcopy(debt), summary_before=deepcopy(report['summary']),
        reclassified_clusters=rejected, records=sorted(records, key=lambda r: r['retired_id']))
    return new_bank, new_ledger, new_debt, archive


def validate_archive(bank, ledger, pathways, archive):
    errors, seen = [], set()
    current = {d['id']: (g, d) for g in bank for d in g['drills']}
    reviews = {r['drill_id']: r for r in ledger}
    references = {rx['drill_id'] for p in pathways['profiles'] for rx in p['prescriptions']}
    if archive.get('schema_version') != 1:
        errors.append('Unknown archive version')
    for row in archive['records']:
        identifier, keeper = row['retired_id'], row['canonical_id']
        if identifier in seen or identifier in current or identifier in references or keeper not in current:
            errors.append('Archive/current ownership collision or missing keeper: ' + identifier)
            continue
        seen.add(identifier)
        group, drill = current[keeper]
        if row['drill']['id'] != identifier or without_identity(drill) != without_identity(row['drill']):
            errors.append('Archived content no longer exact: ' + identifier)
        if {k: v for k, v in group.items() if k != 'drills'} != row['group']:
            errors.append('Archived clinical/phase context mismatch: ' + identifier)
        if reviews.get(keeper) != row['canonical_metadata_review_before']:
            errors.append('Keeper review provenance changed: ' + keeper)
        if row['metadata_review']['source_hash'] != source_hash(drill_id=identifier,
                location=row['group']['location'], injury_type=row['group']['type'],
                name=row['drill']['name'], notes=row['drill']['notes']):
            errors.append('Archived source hash mismatch: ' + identifier)
    old_bank, old_ledger = reconstruct_original(bank, ledger, archive)
    for name, value in [('rehab_bank.json', old_bank), ('rehab_metadata_review.json', old_ledger),
                        ('rehab_pathways.json', pathway_inventory_snapshot(pathways))]:
        if digest(value) != archive['source_input_sha256'][name]:
            errors.append('Cannot reconstruct original source: ' + name)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    paths = [args.data_dir / (name + '.json') for name in ('rehab_bank', 'rehab_metadata_review', 'rehab_pathways', 'rehab_bank_duplicate_debt')]
    bank, ledger, pathways, debt = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    archive_path = args.data_dir / ARCHIVE_PATH
    if archive_path.exists():
        archive = json.loads(archive_path.read_text(encoding='utf-8'))
        errors = validate_archive(bank, ledger, pathways, archive)
        if errors:
            print('\n'.join(errors))
            return 1
        print(f"Exact-duplicate migration already applied; {len(archive['records'])} historical identities verified. No writes.")
        return 0
    if args.check:
        print('Exact-duplicate migration has not been applied')
        return 1
    referenced = {identifier for p in (ROOT / 'tests').glob('*.py')
                  for identifier in re.findall(r'[a-z]+_[a-z0-9_]+', p.read_text(encoding='utf-8'))}
    new_bank, new_ledger, new_debt, archive = consolidate(bank, ledger, pathways, debt, referenced_ids=referenced)
    archive['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # Source formatting is part of historical reconstruction, not an assumed hash.
    if any(archive['source_input_sha256'][p.name] != input_digest(p) for p in paths[:3]):
        raise ValueError('Source JSON formatting differs from reconstruction format; stop before writing')
    errors = validate_archive(new_bank, new_ledger, pathways, archive)
    if errors:
        raise ValueError('\n'.join(errors))
    after, _ = build_audit(new_bank, new_ledger, pathways)
    if after['integrity_errors'] or validate_reviews(new_bank, new_ledger):
        raise ValueError('Post-consolidation integrity failure')
    print(f"Retire {len(archive['records'])} exact surplus identities; leave {len(archive['reclassified_clusters'])} uncertain clusters untouched.")
    if args.write:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(text(archive), encoding='utf-8', newline='\n')
        for path, value in [(paths[0], new_bank), (paths[1], new_ledger), (paths[3], new_debt)]:
            path.write_text(text(value), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
