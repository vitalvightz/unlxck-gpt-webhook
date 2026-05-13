"""Package bootstrap helpers for fightcamp.

This file intentionally stays lightweight. It also installs a temporary
compatibility LOCATION_MAP for injury_synonyms.py, which still references the
old global name during import.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

from .injury_location_registry import build_location_synonym_map


def _load_legacy_location_map() -> dict[str, str]:
    """Read LEGACY_LOCATION_MAP from injury_synonyms.py without importing it."""
    source_path = Path(__file__).with_name("injury_synonyms.py")

    try:
        module_ast = ast.parse(source_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    for node in module_ast.body:
        if not isinstance(node, ast.Assign):
            continue

        has_legacy_target = any(
            isinstance(target, ast.Name) and target.id == "LEGACY_LOCATION_MAP"
            for target in node.targets
        )
        if not has_legacy_target:
            continue

        try:
            value = ast.literal_eval(node.value)
        except Exception:
            return {}

        if isinstance(value, dict):
            return {str(key): str(canonical) for key, canonical in value.items()}

    return {}


def _install_location_map_compat() -> None:
    """Expose LOCATION_MAP for legacy import-time references."""
    if hasattr(builtins, "LOCATION_MAP"):
        return

    location_map: dict[str, str] = {}
    location_map.update(_load_legacy_location_map())
    location_map.update(build_location_synonym_map())
    builtins.LOCATION_MAP = location_map


_install_location_map_compat()
