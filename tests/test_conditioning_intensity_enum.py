import json
from pathlib import Path


def test_conditioning_intensity_enum():
    repo_root = Path(__file__).resolve().parents[1]
    allowed = {"low", "moderate", "high", "max", "zone 1", "zone 2"}
    for path in (repo_root / "data").rglob("*.json"):
        text = path.read_text()
        try:
            data = json.loads(text)
        except Exception:
            continue

        def walk(obj):
            if isinstance(obj, dict):
                if "intensity" in obj:
                    assert (
                        obj["intensity"] in allowed
                    ), f"{path} has invalid intensity {obj['intensity']}"
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        walk(data)

