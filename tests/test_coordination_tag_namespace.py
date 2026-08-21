import json

from fightcamp.config import DATA_DIR
from fightcamp.coordination_support_library import (
    all_coordination_drills,
    coordination_support_metadata,
)
from fightcamp.tagging import normalize_tag


def _global_tag_vocabulary() -> set[str]:
    raw = json.loads((DATA_DIR / "tag_vocabulary.json").read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    return {tag for value in raw if (tag := normalize_tag(str(value)))}


def test_coordination_preferred_tags_stay_in_global_vocabulary():
    vocabulary = _global_tag_vocabulary()
    for drill in all_coordination_drills():
        metadata = coordination_support_metadata(drill)
        assert set(metadata["preferred_tags"]) <= vocabulary, drill.key


def test_coordination_qualities_stay_separate_from_global_preferred_tags():
    for drill in all_coordination_drills():
        metadata = coordination_support_metadata(drill)
        assert metadata["coordination_qualities"] == list(drill.qualities)
        local_only = set(drill.qualities) - set(_global_tag_vocabulary())
        assert not local_only.intersection(metadata["preferred_tags"]), drill.key
