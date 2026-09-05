from __future__ import annotations

import json
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, Iterable

from .config import DATA_DIR
from .late_selector_windows import late_window_allowed


_CANONICAL_PHASES = ("GPP", "SPP", "TAPER")

PLANNER_AUTHORITY_BLOCKER_CODES = frozenset(
    {
        "selected_exercise_phase_unresolved",
        "selected_exercise_phase_ineligible",
        "selected_exercise_late_window_ineligible",
        "selected_loaded_exercise_forbidden",
    }
)

# Clearly external-loaded strength equipment. This intentionally does not include
# bands: late-camp support work may legitimately use light band resistance even
# when loaded lifting is disabled.
_LOADED_STRENGTH_EQUIPMENT = frozenset(
    {
        "barbell",
        "dumbbell",
        "dumbbells",
        "kettlebell",
        "kettlebells",
        "trap_bar",
        "trap bar",
        "landmine",
        "sandbag",
        "log",
        "atlas_stone",
        "atlas stone",
        "weighted_vest",
        "weighted vest",
        "cable",
        "cables",
        "machine",
        "plate",
        "plates",
        "weight_plate",
        "weight plate",
        "smith_machine",
        "smith machine",
    }
)


def _normalise_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalise_phase(value: object) -> str:
    phase = str(value or "").strip().upper()
    return phase if phase in _CANONICAL_PHASES else ""


def _normalise_phase_list(value: object) -> set[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return {
        phase
        for phase in (_normalise_phase(item) for item in values)
        if phase
    }


def _normalise_tokens(value: object) -> set[str]:
    """Normalise scalar/list metadata into comma-safe lower-case tokens."""
    if value is None:
        return set()

    values = list(value) if isinstance(value, (list, tuple, set)) else [value]
    raw: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        raw.extend(text.replace(",", " ").split())

    return {
        " ".join(token.strip().lower().replace("-", "_").split())
        for token in raw
        if token.strip()
    }


def _iter_training_items(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_training_items(item)
        return
    if not isinstance(value, dict):
        return

    if str(value.get("name") or "").strip() and value.get("phases") is not None:
        yield value

    for nested in value.values():
        if isinstance(nested, (dict, list)):
            yield from _iter_training_items(nested)


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


@lru_cache(maxsize=1)
def _bank_indexes() -> dict[str, dict[str, list[dict[str, Any]]]]:
    indexes: dict[str, dict[str, list[dict[str, Any]]]] = {
        "strength_slots": {},
        "conditioning_slots": {},
    }
    sources: dict[str, list[Path]] = {
        "strength_slots": [DATA_DIR / "exercise_bank.json"],
        "conditioning_slots": [
            DATA_DIR / "conditioning_bank.json",
            DATA_DIR / "style_conditioning_bank.json",
        ],
    }

    coordination_dir = DATA_DIR / "coordination"
    if coordination_dir.exists():
        sources["conditioning_slots"].extend(sorted(coordination_dir.rglob("*.json")))

    for slot_group, paths in sources.items():
        index = indexes[slot_group]
        for path in paths:
            for item in _iter_training_items(_load_json(path)):
                key = _normalise_name(item.get("name"))
                if key:
                    index.setdefault(key, []).append(item)
    return indexes


def original_bank_entries(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve original bank rows, using source_phase only as a provenance hint.

    ``source_phase`` is never allowed to decide scheduled legality, but when the
    same display name exists in more than one original bank row it can identify
    which row the candidate actually came from and prevents an unrelated row
    with broader phase permissions from masking a violation.
    """
    slot_group = str(assignment.get("slot_group") or "").strip()
    if slot_group not in _bank_indexes():
        return []

    entries = list(
        _bank_indexes()[slot_group].get(
            _normalise_name(assignment.get("name")),
            [],
        )
    )
    source_phase = _normalise_phase(assignment.get("source_phase"))
    if not source_phase or not entries:
        return entries

    narrowed = [
        item
        for item in entries
        if source_phase in _normalise_phase_list(item.get("phases"))
    ]
    return narrowed or entries


def _athlete_model(planning_brief: dict[str, Any]) -> dict[str, Any]:
    for key in ("athlete_model", "athlete_snapshot"):
        value = planning_brief.get(key)
        if isinstance(value, dict) and value:
            return value
    return {}


def _role_countdown_offset(role: dict[str, Any]) -> int | None:
    for key in (
        "countdown_offset",
        "scheduled_d_day",
        "scheduled_countdown_label",
        "countdown_label",
    ):
        value = role.get(key)
        if isinstance(value, int):
            return value if value >= 0 else None
        text = str(value or "").strip().upper()
        if text.startswith("D-"):
            try:
                return int(text[2:])
            except ValueError:
                continue
    return None


def _stage1_phase_for_offset(athlete_model: dict[str, Any], offset: int) -> str:
    """Independently resolve Stage 1 phase ownership for a D-day.

    Do not call the late-selector helper here. The release gate intentionally
    recomputes the mapping from the canonical Stage 1 ``phase_weeks.days`` data
    so a defect in selector phase resolution cannot automatically be repeated by
    the validator that is supposed to catch it.
    """
    phase_weeks = athlete_model.get("phase_weeks")
    if not isinstance(phase_weeks, dict):
        return ""
    phase_days = phase_weeks.get("days")
    if not isinstance(phase_days, dict):
        return ""

    normalised_days: dict[str, int] = {}
    for phase in _CANONICAL_PHASES:
        try:
            normalised_days[phase] = max(0, int(phase_days.get(phase, 0) or 0))
        except (TypeError, ValueError):
            return ""

    if not any(normalised_days.values()):
        return ""

    remaining = max(1, int(offset))
    for phase in ("TAPER", "SPP", "GPP"):
        days = normalised_days[phase]
        if days <= 0:
            continue
        if remaining <= days:
            return phase
        remaining -= days
    return ""


def _scheduled_phase(
    role: dict[str, Any],
    *,
    athlete_model: dict[str, Any],
    week_phase: object,
) -> str:
    offset = _role_countdown_offset(role)
    if offset is not None:
        # Dated roles are fail-closed. Never fall back to a stale week/role phase
        # when Stage 1 phase authority is missing or cannot own this D-day.
        return _stage1_phase_for_offset(athlete_model, offset)
    return _normalise_phase(week_phase) or _normalise_phase(role.get("phase"))


def _role_envelope(role: dict[str, Any]) -> dict[str, Any]:
    envelope = role.get("effective_strength_envelope")
    if isinstance(envelope, dict):
        return envelope
    cap = role.get("strength_dose_cap")
    return cap if isinstance(cap, dict) else {}


def _is_clearly_loaded_strength_item(
    item: dict[str, Any],
    *,
    role: dict[str, Any],
    assignment: dict[str, Any],
) -> bool:
    slot_group = str(assignment.get("slot_group") or "").strip()
    category = str(role.get("category") or "").strip().lower()
    if slot_group != "strength_slots" and category != "strength":
        return False
    equipment = _normalise_tokens(item.get("equipment"))
    return bool(equipment & _LOADED_STRENGTH_EQUIPMENT)


def _phase_compatible_entries(
    entries: list[dict[str, Any]],
    *,
    phase: str,
) -> list[dict[str, Any]]:
    return [
        item
        for item in entries
        if phase in _normalise_phase_list(item.get("phases"))
    ]


def _iter_scheduled_roles(
    planning_brief: dict[str, Any],
) -> Iterable[tuple[str, dict[str, Any]]]:
    role_map = planning_brief.get("weekly_role_map")
    if not isinstance(role_map, dict):
        return
    for week in role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        week_phase = _normalise_phase(week.get("phase"))
        for role in week.get("session_roles", []) or []:
            if isinstance(role, dict):
                yield week_phase, role


def planner_authority_findings(planning_brief: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate selected physical assignments against original bank authority."""
    if not isinstance(planning_brief, dict):
        return []

    athlete_model = _athlete_model(planning_brief)
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for week_phase, role in _iter_scheduled_roles(planning_brief):
        assignments = role.get("selected_exercise_assignments")
        if not isinstance(assignments, list) or not assignments:
            continue

        offset = _role_countdown_offset(role)
        scheduled_phase = _scheduled_phase(
            role,
            athlete_model=athlete_model,
            week_phase=week_phase,
        )
        envelope = _role_envelope(role)
        loaded_allowed = envelope.get("loaded_allowed") is not False
        countdown_label = str(
            role.get("scheduled_countdown_label")
            or role.get("countdown_label")
            or (f"D-{offset}" if offset is not None else "")
        ).strip()

        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            name = str(assignment.get("name") or "").strip()
            if not name:
                continue

            entries = original_bank_entries(assignment)
            if not entries:
                # Only original-bank-backed physical assignments are in scope.
                continue

            identity = (
                countdown_label,
                str(role.get("role_key") or ""),
                name,
            )
            if identity in seen:
                continue
            seen.add(identity)

            if offset is not None and not scheduled_phase:
                findings.append(
                    {
                        "code": "selected_exercise_phase_unresolved",
                        "severity": "blocker",
                        "message": "A dated selected exercise could not be mapped to the canonical Stage 1 phase allocation.",
                        "exercise": name,
                        "countdown_label": countdown_label,
                        "role_key": role.get("role_key"),
                        "source_phase": assignment.get("source_phase"),
                    }
                )
                continue

            allowed_phases = sorted(
                {
                    phase
                    for item in entries
                    for phase in _normalise_phase_list(item.get("phases"))
                }
            )
            phase_entries = (
                _phase_compatible_entries(entries, phase=scheduled_phase)
                if scheduled_phase
                else entries
            )

            if scheduled_phase and allowed_phases and not phase_entries:
                findings.append(
                    {
                        "code": "selected_exercise_phase_ineligible",
                        "severity": "blocker",
                        "message": "Selected exercise is not permitted by its original bank metadata for the scheduled Stage 1 phase.",
                        "exercise": name,
                        "scheduled_phase": scheduled_phase,
                        "allowed_phases": allowed_phases,
                        "countdown_label": countdown_label,
                        "role_key": role.get("role_key"),
                        "source_phase": assignment.get("source_phase"),
                    }
                )
                continue

            if (
                offset is not None
                and phase_entries
                and not late_window_allowed(phase_entries, offset=offset)
            ):
                findings.append(
                    {
                        "code": "selected_exercise_late_window_ineligible",
                        "severity": "blocker",
                        "message": "Selected exercise is outside every explicit late-window permission declared by its original bank metadata.",
                        "exercise": name,
                        "scheduled_phase": scheduled_phase,
                        "countdown_label": countdown_label,
                        "role_key": role.get("role_key"),
                    }
                )

            if not loaded_allowed and any(
                _is_clearly_loaded_strength_item(
                    item,
                    role=role,
                    assignment=assignment,
                )
                for item in phase_entries
            ):
                findings.append(
                    {
                        "code": "selected_loaded_exercise_forbidden",
                        "severity": "blocker",
                        "message": "A clearly loaded strength exercise was selected while the scheduled strength envelope forbids loaded work.",
                        "exercise": name,
                        "scheduled_phase": scheduled_phase,
                        "countdown_label": countdown_label,
                        "role_key": role.get("role_key"),
                    }
                )

    return findings


def _authority_findings_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for field in ("errors", "blocking_warnings", "warnings", "review_flags"):
        for item in report.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if code not in PLANNER_AUTHORITY_BLOCKER_CODES:
                continue
            identity = (
                code,
                str(item.get("exercise") or ""),
                str(item.get("countdown_label") or ""),
            )
            if identity in seen:
                continue
            seen.add(identity)
            findings.append(dict(item))
    return findings


def install() -> None:
    """Add an independent planner-authority gate before athlete release."""
    from . import stage2_pipeline as pipeline
    from . import stage2_policy as policy

    if getattr(pipeline, "_PLANNER_AUTHORITY_INTEGRITY_INSTALLED", False):
        return

    original_report_builder = pipeline._validator_report_with_required_countdown_sessions
    original_release_policy = policy.apply_stage2_release_policy
    original_build_retry = pipeline.build_stage2_retry

    @wraps(original_report_builder)
    def authority_report_builder(*, planning_brief: dict, final_plan_text: str):
        report = original_report_builder(
            planning_brief=planning_brief,
            final_plan_text=final_plan_text,
        )
        findings = planner_authority_findings(planning_brief)
        if not findings:
            return report

        errors = [
            dict(item)
            for item in report.get("errors", []) or []
            if isinstance(item, dict)
        ]
        existing = {
            (
                str(item.get("code") or ""),
                str(item.get("exercise") or ""),
                str(item.get("countdown_label") or ""),
            )
            for item in errors
        }
        for finding in findings:
            identity = (
                str(finding.get("code") or ""),
                str(finding.get("exercise") or ""),
                str(finding.get("countdown_label") or ""),
            )
            if identity not in existing:
                errors.append(finding)
                existing.add(identity)

        return {
            **report,
            "errors": errors,
            "is_valid": False,
            "planner_authority_integrity_findings": findings,
            "planner_authority_integrity_finding_count": len(findings),
        }

    @wraps(original_release_policy)
    def authority_release_policy(validator_report: dict):
        # Capture integrity blockers before the ordinary policy transforms the
        # report, then also inspect its result. This gate must not depend on the
        # observational policy preserving a particular field layout.
        blockers = _authority_findings_from_report(validator_report)
        report = original_release_policy(validator_report)
        if not blockers:
            blockers = _authority_findings_from_report(report)
        if not blockers:
            return report

        return {
            **report,
            "planner_authority_integrity_findings": blockers,
            "planner_authority_integrity_finding_count": len(blockers),
            "planner_authority_integrity_hold": True,
            "release_decision": "hold",
            "is_athlete_releasable": False,
            "is_publishable": False,
        }

    @wraps(original_build_retry)
    def authority_build_stage2_retry(*args, **kwargs):
        result = original_build_retry(*args, **kwargs)
        report = result.get("validator_report") if isinstance(result, dict) else None
        blockers = (
            _authority_findings_from_report(report)
            if isinstance(report, dict)
            else []
        )
        if not blockers:
            return result

        # Renderer/LLM repair cannot make an upstream illegal candidate legal.
        # Keep the plan held and require deterministic planner regeneration.
        return {
            **result,
            "needs_retry": False,
            "requires_planner_regeneration": True,
            "repair_prompt": None,
            "summary": "FAIL: selected exercise authority requires deterministic planner regeneration.",
            "summary_lines": [
                str(item.get("message") or "Planner authority violation.")
                for item in blockers
            ],
        }

    pipeline._validator_report_with_required_countdown_sessions = authority_report_builder
    policy.apply_stage2_release_policy = authority_release_policy
    # stage2_pipeline imported the policy function by value, so replace that
    # module-local reference as well. Later API imports resolve the patched attr.
    pipeline.apply_stage2_release_policy = authority_release_policy
    pipeline.build_stage2_retry = authority_build_stage2_retry
    pipeline._PLANNER_AUTHORITY_INTEGRITY_INSTALLED = True
