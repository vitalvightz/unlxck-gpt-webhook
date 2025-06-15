import json
from pathlib import Path

PREFIX = {
    'GPP': 'Focus on stability and mobility. ',
    'SPP': 'Add progressive load and dynamic movement. ',
    'TAPER': 'Reduce volume while keeping speed and precision. ',
}

in_path = Path('data/rehab_bank_split.json')
out_path = Path('data/rehab_bank_split.json')

data = json.loads(in_path.read_text())
for entry in data:
    for drill in entry.get('drills', []):
        phase = drill.get('phase')
        prefix = PREFIX.get(phase)
        if prefix and not drill['notes'].startswith(prefix):
            drill['notes'] = prefix + drill['notes']

out_path.write_text(json.dumps(data, indent=2))
print(f'Updated notes for {len(data)} entries')
