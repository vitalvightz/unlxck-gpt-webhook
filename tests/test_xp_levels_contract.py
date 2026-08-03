from __future__ import annotations

import json
from pathlib import Path

from api.services import progress_notifications
from api.xp_levels import XP_LEVELS, resolve_xp_level


EXPECTED_LEVELS = (
    (1, "Rookie", 0),
    (2, "Prospect", 250),
    (3, "Amateur", 750),
    (4, "Challenger", 1_500),
    (5, "Ranked", 2_750),
    (6, "Contender", 4_500),
    (7, "Elite", 7_000),
    (8, "Champion", 10_000),
)


def test_backend_and_web_load_the_neutral_shared_level_contract():
    raw = json.loads(Path("shared/xp-levels.json").read_text(encoding="utf-8"))
    assert tuple(
        (item["level"], item["title"], item["threshold"])
        for item in raw
    ) == EXPECTED_LEVELS
    assert XP_LEVELS == EXPECTED_LEVELS
    assert progress_notifications.XP_LEVELS is XP_LEVELS

    web_source = Path("web/lib/xp.ts").read_text(encoding="utf-8")
    assert 'from "../../shared/xp-levels.json"' in web_source
    assert "web/lib/xp-levels.json" not in web_source


def test_backend_image_build_smokes_the_shared_contract_in_deployed_layout():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "test -f /app/shared/xp-levels.json" in dockerfile
    assert "from api.xp_levels import XP_LEVELS" in dockerfile
    assert "COPY --chown=appuser:appuser . ." in dockerfile

    dockerignore = Path(".dockerignore").read_text(encoding="utf-8").splitlines()
    assert not any(
        line.strip().rstrip("/") == "shared"
        for line in dockerignore
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_existing_xp_totals_are_remapped_without_mutation():
    assert resolve_xp_level(1_700) == (4, "Challenger", 1_500)
    assert resolve_xp_level(2_750) == (5, "Ranked", 2_750)
    assert resolve_xp_level(9_999) == (7, "Elite", 7_000)
    assert resolve_xp_level(10_000) == (8, "Champion", 10_000)
