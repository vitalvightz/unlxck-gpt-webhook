from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_POLICY_PATH = Path(__file__).resolve().parents[1] / "shared" / "stage2-policy.json"


@lru_cache(maxsize=1)
def _load_stage2_policy() -> dict[str, Any]:
    with _POLICY_PATH.open(encoding="utf-8") as handle:
        policy = json.load(handle)
    if not isinstance(policy, dict):
        raise ValueError("stage2 policy must be a JSON object")
    return policy


def _code_set(key: str) -> frozenset[str]:
    value = _load_stage2_policy().get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"stage2 policy {key} must be a list of non-empty strings")
    return frozenset(value)


HARD_STAGE2_BLOCKER_CODES = _code_set("hard_stage2_blocker_codes")
CARD_RESCUABLE_SOFT_CODES = _code_set("card_rescuable_soft_codes")


def is_hard_stage2_blocker(code: str) -> bool:
    return str(code or "").strip() in HARD_STAGE2_BLOCKER_CODES


def is_card_rescuable_soft_code(code: str) -> bool:
    return str(code or "").strip() in CARD_RESCUABLE_SOFT_CODES


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
    hard_codes = {str(item.get("code") or "") for item in [*errors, *blocking_warnings]}
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
