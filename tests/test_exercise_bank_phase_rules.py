import json
from pathlib import Path


def test_nordic_hamstring_curl_not_available_in_taper():
    bank_path = Path(__file__).resolve().parents[1] / "data" / "exercise_bank.json"
    exercise_bank = json.loads(bank_path.read_text())
    nordic = next(item for item in exercise_bank if item.get("name") == "Nordic Hamstring Curl")
    phases = {str(phase).upper() for phase in nordic.get("phases", [])}
    assert "TAPER" not in phases
    assert {"GPP", "SPP"}.issubset(phases)
