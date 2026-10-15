"""Reproducible, read-only per-record conditioning audit; no media approval.

Run: python tools/audit_conditioning_programming.py --out reports/conditioning_programming_audit.csv
Use --ref db8d855e to inspect the exact pre-change bank instead.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fightcamp.config import conditioning_dose_active_work_seconds, conditioning_work_is_timed  # noqa: E402
from fightcamp.exercise_identity import normalize_exercise_key  # noqa: E402


def audit(ref: str | None = None) -> list[dict]:
    paths = [ROOT / 'data' / f for f in (
        'conditioning_bank.json', 'style_conditioning_bank.json',
        'style_taper_conditioning.json', 'coordination_bank.json')]
    paths += sorted((ROOT / 'data/coordination').glob('*.json'))
    rows = []
    for path in paths:
        relative = str(path.relative_to(ROOT))
        text = subprocess.check_output(['git', 'show', f'{ref}:{relative}'], cwd=ROOT, text=True) if ref else path.read_text()
        entries = json.loads(text)
        if isinstance(entries, dict):
            entries = [e for group in entries.values() if isinstance(group, list) for e in group]
        for e in entries:
            name = e.get('name', '')
            dose = str(e.get('duration') or e.get('timing') or '')
            system = str(e.get('system') or '')
            flags = []
            timed = conditioning_work_is_timed(e)
            active = conditioning_dose_active_work_seconds(e)
            work, rest, rounds, total = (e.get(k) for k in ('work_sec', 'rest_sec', 'rounds', 'total_minutes'))
            if not timed:
                flags.append('reps_or_distance_not_seconds')
            if total is not None and timed and work and rounds and rest is not None:
                expected = (work * rounds + max(0, rounds-1) * rest) / 60
                if abs(total-expected) > .02:
                    flags.append('elapsed_total_disagrees_with_interval_arithmetic')
            if rounds and rounds > 1 and rest is None:
                flags.append('recovery_not_structured')
            if timed and work and work <= 12 and rest and rest >= 60 and system == 'glycolytic':
                flags.append('short_full_recovery_misclassified_glycolytic')
            if e.get('manual_review_required'):
                flags.append('manual_review_excluded_from_runtime')
            if e.get('support_only') or e.get('placement', 'conditioning') != 'conditioning':
                flags.append('support_or_non_conditioning_placement')
            if not e.get('equipment') and re.search(r'\b(?:harness|reaction ball|rower|heavy bag)\b', name, re.I):
                flags.append('equipment_requires_review')
            rows.append({
                'source': relative, 'id_or_key': e.get('id') or e.get('key') or '',
                'name': name, 'media_key': normalize_exercise_key(name),
                'system': system, 'adaptation': e.get('primary_adaptation') or '',
                'phases': '|'.join(e.get('phases') or []), 'prescription': dose,
                'work_unit_status': 'time_or_unresolved' if timed else 'reps_or_metres',
                'work_sec_legacy': work, 'rest_sec': rest, 'rounds': rounds,
                'active_work_seconds': active, 'elapsed_minutes_legacy': total,
                'rpe': e.get('rpe'), 'equipment': '|'.join(e.get('equipment') or []),
                'sports': '|'.join(e.get('sports') or []), 'tags': '|'.join(e.get('tags') or []),
                'impact': e.get('impact_cost'), 'fatigue_cost': e.get('movement_cost'),
                'lactate_load': e.get('lactate_load'), 'support_only': e.get('support_only'),
                'meaningful_stress': e.get('meaningful_stress'), 'flags': '|'.join(flags),
            })
    keys = Counter(r['media_key'] for r in rows)
    for row in rows:
        row['same_media_key_count'] = keys[row['media_key']]
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    records = audit(args.ref)
    with args.out.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps({'records': len(records), 'sources': Counter(r['source'] for r in records),
                      'flags': Counter(f for r in records for f in r['flags'].split('|') if f)}, indent=2))
