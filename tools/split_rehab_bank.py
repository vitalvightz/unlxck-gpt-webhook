import json
import re
import sys
from pathlib import Path

phase_split = re.compile(r"\s*→\s*|\s*,\s*")
phase_label = re.compile(r"\s*(GPP|SPP|TAPER|PEAK|DELOAD|BASE|UNLISTED)\s*:\s*(.*)")

in_path = Path('data/rehab_bank.json')

with in_path.open() as f:
    lines = f.readlines()

# remove comment lines that start with '//'
lines = [ln for ln in lines if not re.match(r'^\s*//', ln)]
text = ''.join(lines)

try:
    data = json.loads(text)
except json.JSONDecodeError as e:
    sys.stderr.write(f'Failed to parse JSON: {e}\n')
    sys.exit(1)

out = []
for obj in data:
    phases = [p.strip() for p in phase_split.split(obj.get('phase_progression', '')) if p.strip()]
    if not phases:
        phases = ['']
    phase_objs = {ph: {
        'location': obj['location'],
        'type': obj['type'],
        'phase_progression': ph,
        'drills': []
    } for ph in phases}

    for drill in obj.get('drills', []):
        parts = [p.strip() for p in drill.get('notes', '').split('→')]
        for part in parts:
            m = phase_label.match(part)
            if m:
                phase, note = m.group(1), m.group(2).strip()
            else:
                phase = phases[0]
                note = part
            entry = {
                'name': drill['name'],
                'phase': phase,
                'notes': note
            }
            if phase not in phase_objs:
                phase_objs[phase] = {
                    'location': obj['location'],
                    'type': obj['type'],
                    'phase_progression': phase,
                    'drills': []
                }
            phase_objs[phase]['drills'].append(entry)

    for ph in phases:
        out.append(phase_objs[ph])

out_path = Path('data/rehab_bank_split.json')
with out_path.open('w') as f:
    json.dump(out, f, indent=2)

print(f"Wrote {len(out)} entries to {out_path}")
