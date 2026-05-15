import json
from pathlib import Path

from fightcamp.late_selector_windows import is_active_late_selector_window


def test_exercise_bank_late_windows_use_supported_ranges():
    bank = json.loads(Path('data/exercise_bank.json').read_text())
    invalid = [
        (entry.get("name"), window)
        for entry in bank
        for window in entry.get("late_windows") or []
        if not is_active_late_selector_window(window)
    ]
    assert not invalid, f'Unsupported late_windows found: {invalid}'
