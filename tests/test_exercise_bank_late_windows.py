import json
from pathlib import Path


def test_exercise_bank_late_windows_use_supported_ranges():
    bank = json.loads(Path('data/exercise_bank.json').read_text())
    allowed = {'d21_to_d14', 'd13_to_d8', 'd7', 'd6_to_d5', 'd4_to_d2', 'd1'}
    invalid = []
    for entry in bank:
        for window in entry.get('late_windows') or []:
            if window not in allowed:
                invalid.append((entry.get('name'), window))
    assert not invalid, f'Unsupported late_windows found: {invalid}'
