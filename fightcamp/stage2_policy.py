from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "shared" / "stage2-policy.json"
_POLICY_PATH = Path(os.getenv("STAGE2_POLICY_PATH", str(_DEFAULT_POLICY_PATH)))
_REPAIR_PROMPT_EXCLUDED_CODES = frozenset(
    {
        "generic_filler_phrase",
        "sport_language_leak",
        "true_internal_system_leak",
    }
)
_RELEASE_COLLECTION_FIELDS = (
    "errors",
    "warnings",
    "review_flags",
    "blocking_warnings",
)


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


@lru_cache(maxsize=4)
def _code_set(key: str) -> frozenset[str]:
    value = _load_stage2_policy().get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"stage2 policy {key} must be a list of non-empty strings")
    return frozenset(value)


HARD_STAGE2_BLOCKER_CODES: frozenset[str]
ATHLETE_RELEASE_WITH_FLAGS_CODES: frozenset[str]
ADMIN_REVIEW_BLOCKING_CODES: frozenset[str]
CARD_RESCUABLE_SOFT_CODES: frozenset[str]


def __getattr__(name: str) -> Any:
    if name == "HARD_STAGE2_BLOCKER_CODES":
        return _code_set("hard_stage2_blocker_codes")
    if name == "ATHLETE_RELEASE_WITH_FLAGS_CODES":
        return _code_set("athlete_release_with_flags_codes")
    if name == "ADMIN_REVIEW_BLOCKING_CODES":
        return _code_set("admin_review_blocking_codes")
    if name == "CARD_RESCUABLE_SOFT_CODES":
        return _code_set("card_rescuable_soft_codes")
    raise AttributeError(f"module {__name__} has no attribute {name}")


def is_hard_stage2_blocker(code: str) -> bool:
    return str(code or "").strip() in _code_set("hard_stage2_blocker_codes")


def is_card_rescuable_soft_code(code: str) -> bool:
    return str(code or "").strip() in _code_set("card_rescuable_soft_codes")


def is_athlete_release_with_flags_code(code: str) -> bool:
    return str(code or "").strip() in _code_set("athlete_release_with_flags_codes")


def is_admin_review_blocking_code(code: str) -> bool:
    return str(code or "").strip() in _code_set("admin_review_blocking_codes")


def _finding_identity(item: dict) -> tuple:
    return (
        str(item.get("code") or "").strip(),
        str(item.get("phase") or "").strip(),
        str(item.get("week_index") or "").strip(),
        str(item.get("session_index") or "").strip(),
        str(item.get("requirement") or "").strip(),
        str(item.get("line") or "").strip(),
    )


def _dedupe_findings(findings: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple] = set()
    for item in findings:
        key = _finding_identity(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _policy_findings(validator_report: dict, codes: frozenset[str]) -> list[dict]:
    findings: list[dict] = []
    for key in ("blocking_warnings", "review_flags", "warnings"):
        for item in validator_report.get(key, []) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("code") or "").strip() in codes:
                findings.append(dict(item))
    return _dedupe_findings(findings)


def athlete_release_with_flags_findings(validator_report: dict) -> list[dict]:
    return _policy_findings(validator_report, _code_set("athlete_release_with_flags_codes"))


def admin_review_blocking_findings(validator_report: dict) -> list[dict]:
    return _policy_findings(validator_report, _code_set("admin_review_blocking_codes"))


def apply_stage2_release_policy(validator_report: dict) -> dict:
    """Attach one release decision whose fields agree with the saved status.

    Low-risk allowlisted findings move to ``quality_review_flags`` and remain
    athlete-releasable. Admin-review and hard-blocker warnings are promoted to
    ``blocking_warnings``. Any other pre-existing blocking warning is preserved,
    so an unknown blocker fails closed instead of silently reaching an athlete.

    Release-relevant collections must be lists when present. Malformed persisted
    reports fail closed before policy findings are inspected, preventing a dict,
    string, or arbitrary object from being treated as an empty warning list.
    """

    malformed_fields = [
        key
        for key in _RELEASE_COLLECTION_FIELDS
        if key in validator_report and not isinstance(validator_report.get(key), list)
    ]
    if malformed_fields:
        return {
            **validator_report,
            "quality_review_flags": [],
            "quality_review_flag_count": 0,
            "admin_review_blocking_flags": [],
            "admin_review_blocking_flag_count": 0,
            "release_policy_malformed_fields": malformed_fields,
            "release_decision": "hold",
            "is_athlete_releasable": False,
            "is_publishable": False,
        }

    quality_findings = athlete_release_with_flags_findings(validator_report)
    admin_findings = admin_review_blocking_findings(validator_report)
    existing_blocking = [
        dict(item)
        for item in validator_report.get("blocking_warnings", []) or []
        if isinstance(item, dict)
        and not is_athlete_release_with_flags_code(str(item.get("code") or ""))
    ]
    hard_warning_findings = [
        dict(item)
        for key in ("warnings", "review_flags")
        for item in validator_report.get(key, []) or []
        if isinstance(item, dict)
        and is_hard_stage2_blocker(str(item.get("code") or ""))
    ]
    blocking_warnings = _dedupe_findings(
        [*existing_blocking, *admin_findings, *hard_warning_findings]
    )
    errors = validator_report.get("errors")
    malformed_errors = not isinstance(errors, list)
    has_errors = malformed_errors or bool(errors)
    is_athlete_releasable = not has_errors and not blocking_warnings
    release_decision = (
        "hold"
        if not is_athlete_releasable
        else ("publish_with_flags" if quality_findings else "publish")
    )
    return {
        **validator_report,
        "blocking_warnings": blocking_warnings,
        "blocking_warning_count": len(blocking_warnings),
        "quality_review_flags": quality_findings,
        "quality_review_flag_count": len(quality_findings),
        "admin_review_blocking_flags": admin_findings,
        "admin_review_blocking_flag_count": len(admin_findings),
        "release_decision": release_decision,
        "is_athlete_releasable": is_athlete_releasable,
        "is_publishable": is_athlete_releasable,
    }


def _is_repair_prompt_code(code: str) -> bool:
    normalized = str(code or "").strip()
    if not normalized or normalized in _REPAIR_PROMPT_EXCLUDED_CODES:
        return False
    return (
        is_hard_stage2_blocker(normalized)
        or is_admin_review_blocking_code(normalized)
        or is_athlete_release_with_flags_code(normalized)
        or is_card_rescuable_soft_code(normalized)
    )


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
        dict(item)
        for item in validator_report.get("errors", []) or []
        if isinstance(item, dict) and _is_repair_prompt_code(str(item.get("code") or ""))
    ]
    blocking_warnings = [
        dict(item)
        for item in validator_report.get("blocking_warnings", []) or []
        if isinstance(item, dict) and is_hard_stage2_blocker(str(item.get("code") or ""))
    ]
    admin_blocking_findings = admin_review_blocking_findings(validator_report)
    quality_findings = athlete_release_with_flags_findings(validator_report)
    repair_warnings = _dedupe_findings(
        [
            dict(item)
            for item in validator_report.get("warnings", []) or []
            if isinstance(item, dict)
            and _is_repair_prompt_code(str(item.get("code") or ""))
        ]
        + admin_blocking_findings
        + quality_findings
    )
    hard_codes = {str(item.get("code") or "").strip() for item in [*errors, *blocking_warnings]}
    restricted_hits = (
        list(validator_report.get("restricted_hits", []) or [])
        if "restriction_violation" in hard_codes
        else []
    )
    return {
        "errors": errors,
        "warnings": repair_warnings,
        "blocking_warnings": _dedupe_findings([*blocking_warnings, *admin_blocking_findings]),
        "missing_required_elements": list(validator_report.get("missing_required_elements", []) or []),
        "restricted_hits": restricted_hits,
    }
