"""Retirement contract for the legacy Universal GPP Strength bank.

`data/universal_gpp_strength.json` was a second, post-selection strength
library used only to backfill missing GPP base categories. The main selector
now owns base-category promotion (`_promote_base_categories`) sourced from
`exercise_bank.json`, so the Universal bank and every loader/cache/insertion
that fed it have been retired. These tests pin that retirement so the second
library cannot silently reappear.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp import strength

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# Directories that hold live runtime code and data. Historical reports under
# docs/notes (e.g. EXPANSION_REPORT.md) may still describe the old architecture
# and are intentionally excluded — they cannot be mistaken for current
# behavior, and this contract only guards executable/loadable surfaces.
_LIVE_DIRS = ("fightcamp", "tools", "data", "tests")
_RETIRED_TOKEN = "universal_gpp_strength"


def test_universal_gpp_strength_bank_file_is_deleted():
    assert not (DATA_DIR / "universal_gpp_strength.json").exists()


def test_strength_module_exposes_no_universal_helpers_or_caches():
    for attribute in (
        "get_universal_strength",
        "get_universal_strength_names",
        "_universal_strength_cache",
        "_universal_strength_names_cache",
    ):
        assert not hasattr(strength, attribute), (
            f"fightcamp.strength must not expose retired attribute {attribute!r}"
        )


def _iter_live_files():
    for sub in _LIVE_DIRS:
        base = ROOT / sub
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            # This contract test itself names the retired token deliberately.
            if path.resolve() == Path(__file__).resolve():
                continue
            if path.suffix in {".py", ".json"}:
                yield path


def test_no_live_repo_reference_to_universal_gpp_strength():
    offenders = []
    for path in _iter_live_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _RETIRED_TOKEN in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "Retired token still referenced by live code/data: " + ", ".join(sorted(offenders))
    )


def test_gpp_generation_works_using_only_the_main_exercise_bank():
    # No monkeypatching: this drives the real exercise_bank.json through the
    # canonical path and proves generation still produces a populated strength
    # block without the retired Universal bank.
    block = strength.generate_strength_block(
        flags={
            "phase": "GPP",
            "fatigue": "low",
            "fight_format": "mma",
            "sport": "mma",
            "key_goals": [],
            "training_days": ["Mon", "Wed", "Fri"],
            "training_frequency": 3,
            "days_available": 3,
            "days_until_fight": 60,
            "equipment": ["barbell", "dumbbells", "rack", "bench", "bodyweight"],
            "injuries": [],
            "prev_exercises": [],
            "recent_exercises": [],
            "restrictions": [],
            "ignore_restrictions": False,
            "random_seed": 11,
        },
        weaknesses=[],
        mindset_cue=None,
    )
    exercises = block["exercises"]
    assert exercises, "GPP strength generation must still yield exercises"
    assert all(entry.get("name") for entry in exercises)
