import ast
import json
from pathlib import Path

from fightcamp.injury_exclusion_rules import INJURY_RULES
from fightcamp.injury_tagging import infer_tags_from_name


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_json(path: Path):
    return json.loads(path.read_text())


def _load_style_specific_exercises(path: Path) -> list[dict]:
    text = path.read_text()
    start = text.find("[")
    end = text.rfind("}")
    snippet = text[start:end + 1] + "]" if start != -1 and end != -1 else "[]"
    try:
        return ast.literal_eval(snippet)
    except Exception:
        return []


def _flatten_coordination_bank(path: Path) -> list[dict]:
    data = _load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        flattened = []
        for val in data.values():
            if isinstance(val, list):
                flattened.extend(val)
        return flattened
    return []


def collect_bank_items() -> list[dict]:
    items = []

    def add_item(bank_name: str, entry: dict):
        name = entry.get("name")
        if not name:
            return
        explicit_tags = [t.lower() for t in entry.get("tags", [])]
        inferred_tags = infer_tags_from_name(name)
        items.append(
            {
                "bank": bank_name,
                "item_id": name,
                "name": name,
                "explicit_tags": explicit_tags,
                "inferred_tags": inferred_tags,
            }
        )

    for entry in _load_json(DATA_DIR / "exercise_bank.json"):
        add_item("exercise_bank", entry)

    for entry in _load_json(DATA_DIR / "conditioning_bank.json"):
        add_item("conditioning_bank", entry)

    for entry in _load_json(DATA_DIR / "style_conditioning_bank.json"):
        add_item("style_conditioning_bank", entry)

    for entry in _flatten_coordination_bank(DATA_DIR / "coordination_bank.json"):
        add_item("coordination_bank", entry)

    for entry in _load_json(DATA_DIR / "universal_gpp_strength.json"):
        add_item("universal_gpp_strength", entry)

    for entry in _load_json(DATA_DIR / "universal_gpp_conditioning.json"):
        add_item("universal_gpp_conditioning", entry)

    for entry in _load_json(DATA_DIR / "style_taper_conditioning.json"):
        add_item("style_taper_conditioning", entry)

    for entry in _load_style_specific_exercises(DATA_DIR / "style_specific_exercises"):
        add_item("style_specific_exercises", entry)

    return items


def build_exclusion_map(items: list[dict]) -> dict:
    exclusion_map: dict[str, list[str]] = {region: [] for region in INJURY_RULES}
    for item in items:
        name_lower = item["name"].lower()
        tags = set(item["explicit_tags"]) | set(item["inferred_tags"])
        for region, rule in INJURY_RULES.items():
            if any(keyword in name_lower for keyword in rule.get("ban_keywords", [])):
                exclusion_map.setdefault(region, []).append(item["item_id"])
                continue
            if tags & set(rule.get("ban_tags", [])):
                exclusion_map.setdefault(region, []).append(item["item_id"])

    for region, names in exclusion_map.items():
        exclusion_map[region] = sorted(set(names))
    return exclusion_map


def main() -> None:
    items = collect_bank_items()
    inferred_path = DATA_DIR / "bank_inferred_tags.json"
    inferred_path.write_text(json.dumps(items, indent=2, sort_keys=True))

    exclusion_map = build_exclusion_map(items)
    exclusion_path = DATA_DIR / "injury_exclusion_map.json"
    exclusion_path.write_text(json.dumps(exclusion_map, indent=2, sort_keys=True))

    print(f"Wrote {inferred_path}")
    print(f"Wrote {exclusion_path}")


if __name__ == "__main__":
    main()
