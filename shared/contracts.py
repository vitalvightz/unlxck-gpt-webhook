"""Load the JSON contracts in ``shared/`` that the backend and the web app both read.

A value both sides must agree on (a cap, a code, a message the client matches)
lives once in ``shared/<name>.json``; the web app imports the same file. A
missing or malformed contract fails the importing module loudly instead of
letting one side fall back to its own idea of the value.

Deliberately dependency-free: ``api`` and ``fightcamp`` both import it, and the
planner package must not be dragged into light ``api`` modules to read a file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SHARED_DIR = Path(__file__).resolve().parent


def load_shared_contract(filename: str) -> dict[str, Any]:
    """The parsed ``shared/<filename>`` object, or ``RuntimeError`` if unusable."""
    path = SHARED_DIR / filename
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Shared contract is missing at {path}. Ensure shared/{filename} is packaged."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Shared contract at {path} is not valid JSON") from exc
    if not isinstance(contract, dict):
        raise RuntimeError(f"Shared contract shared/{filename} must be a JSON object")
    return contract


def require_object(contract: dict[str, Any], key: str, *, source: str) -> dict[str, Any]:
    value = contract.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"{source} {key} must be an object")
    return value


def shared_message(key: str) -> tuple[str, str]:
    """``(code, message)`` for one entry of shared/api-messages.json.

    These are the codes and texts the web app matches on, so a reworded message
    or renamed code reaches both sides together.
    """
    source = "API messages"
    entry = require_object(load_shared_contract("api-messages.json"), key, source=source)
    return require_string(entry, "code", source=f"{source} {key}"), require_string(
        entry, "message", source=f"{source} {key}"
    )


def shared_code(key: str) -> str:
    """The ``code`` of one entry of shared/api-messages.json (entries without a message)."""
    source = "API messages"
    entry = require_object(load_shared_contract("api-messages.json"), key, source=source)
    return require_string(entry, "code", source=f"{source} {key}")


def require_string(contract: dict[str, Any], key: str, *, source: str) -> str:
    value = contract.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{source} {key} must be a non-empty string")
    return value


def require_positive_int(contract: dict[str, Any], key: str, *, source: str, allow_zero: bool = False) -> int:
    value = contract.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1):
        raise RuntimeError(f"{source} {key} must be a {'non-negative' if allow_zero else 'positive'} integer")
    return value


def require_string_list(contract: dict[str, Any], key: str, *, source: str) -> tuple[str, ...]:
    value = contract.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
        or len(set(value)) != len(value)
    ):
        raise RuntimeError(f"{source} {key} must be a non-empty list of distinct non-empty strings")
    return tuple(value)
