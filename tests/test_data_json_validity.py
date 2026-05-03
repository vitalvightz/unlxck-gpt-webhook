import json
from pathlib import Path


def test_all_data_json_files_are_valid():
    data_dir = Path(__file__).resolve().parents[1] / "data"
    json_files = sorted(data_dir.glob("*.json"))

    assert json_files, "Expected JSON files in data/."

    for json_file in json_files:
        json.loads(json_file.read_text(encoding="utf-8"))
