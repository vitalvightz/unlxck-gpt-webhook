from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "shared" / "stage2-policy.json"
_POLICY_PATH = Path(os.getenv("STAGE2_POLICY_PATH", str(_DEFAULT_POLICY_PATH)))


@lru_cache(maxsize=1)
def _load_stage2_policy() -> dict[str, Any]:
    try:
        with _POLICY_PATH.open(encoding="utf-8") as handle:
            policy = json.load(handle)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Stage 2 policy file not found at {_POLICY_PATH}. "
            "Ensure shared/stage2-policy.json is present, or set STAGE2_POLICY_PATH."
        ) from exc
    if not isinstance(policy, dict):
        raise ValueError("stage2 policy must be a JSON object")
    return policy


@lru_cache(maxsize=2)
def _code_set(key: str) -> frozenset[str]:
    value = _load_stage2_policy().get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"stage2 policy {key} must be a list of non-empty strings")
    return frozenset(value)


HARD_STAGE2_BLOCKER_CODES: frozenset[str]
CARD_RESCUABLE_SOFT_CODES: frozenset[str]


def __getattr__(name: str) -> Any:
    if name == "HARD_STAGE2_BLOCKER_CODES":
        return _code_set("hard_stage2_blocker_codes")
    if name == "CARD_RESCUABLE_SOFT_CODES":
        return _code_set("card_rescuable_soft_codes")
    raise AttributeError(f"module {__name__} has no attribute {name}")


def is_hard_stage2_blocker(code: str) -> bool:
    return str(code or "").strip() in _code_set("hard_stage2_blocker_codes")


def is_card_rescuable_soft_code(code: str) -> bool:
    return str(code or "").strip() in _code_set("card_rescuable_soft_codes")


def hard_blocker_findings(validator_report: dict) -> list[dict]:
    findings: list[dict] = []
    for key in ("errors", "blocking_warnings"):
        for item in validator_report.get(key, []) or []:
            if not isinstance(item, dict):
                continue
            if is_hard_stage2_blocker(str(item.get("code") or "")):
                findings.append(item)
    return findings


def prompt_safe_validator_report(validator_report: dict) -> dict:
    errors = [
        item
        for item in validator_report.get("errors", []) or []
        if isinstance(item, dict) and is_hard_stage2_blocker(str(item.get("code") or ""))
    ]
    blocking_warnings = [
        item
        for item in validator_report.get("blocking_warnings", []) or []
        if isinstance(item, dict) and is_hard_stage2_blocker(str(item.get("code") or ""))
    ]
    hard_codes = {str(item.get("code") or "").strip() for item in [*errors, *blocking_warnings]}
    restricted_hits = (
        list(validator_report.get("restricted_hits", []) or [])
        if "restriction_violation" in hard_codes
        else []
    )
    return {
        "errors": errors,
        "blocking_warnings": blocking_warnings,
        "restricted_hits": restricted_hits,
    }
