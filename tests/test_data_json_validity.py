import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
JSON_FILES = sorted(DATA_DIR.glob("*.json"))


def test_data_directory_contains_json_files():
    assert JSON_FILES, f"No JSON files found in {DATA_DIR}"


@pytest.mark.parametrize("json_file", JSON_FILES, ids=lambda p: p.name)
def test_json_file_validity(json_file):
    json.loads(json_file.read_text(encoding="utf-8"))
