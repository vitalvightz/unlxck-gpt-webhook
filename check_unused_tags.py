import json
from pathlib import Path

TAGS_FILE = Path('tags.txt')
DRILLS_FILE = Path('mental/Drills_bank.json')


def load_tags(path: Path) -> set:
    data = json.load(path.open())
    tags = set()
    for values in data.get('theme_tags', {}).values():
        tags.update(values)
    return tags


def load_used_tags(path: Path) -> set:
    data = json.load(path.open())
    used = set()
    for drill in data.get('drills', []):
        used.update(drill.get('theme_tags', []))
    return used


if __name__ == '__main__':
    all_tags = load_tags(TAGS_FILE)
    used_tags = load_used_tags(DRILLS_FILE)
    unused = sorted(all_tags - used_tags)
    print(unused)
