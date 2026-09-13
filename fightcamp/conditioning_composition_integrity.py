from __future__ import annotations

from functools import wraps
from typing import Any


_POLICY_FLAG = "_CONDITIONING_COMPOSITION_INTEGRITY_INSTALLED"
_UNDERFILL_REASON = "phase_system_workload_unmet"
_UNDERFILL_CODE = "conditioning_role_workload_underfilled"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _selected_option_by_slot(
    candidate_pools: dict[str, Any], *, phase: str, slot_id: object
) -> dict[str, Any] | None:
    pool = candidate_pools.get(phase) if isinstance(candidate_pools, dict) else None
    slots = pool.get("conditioning_slots", []) if isinstance(pool, dict) else []
    for slot in slots:
        if not isinstance(slot, dict) or slot.get("slot_id") != slot_id:
            continue
        selected = slot.get("selected")
        return selected if isinstance(selected, dict) else None
    return None


def _assignment_active_work_seconds(
    composition_module,
    assignment: dict[str, Any],
    *,
    candidate_pools: dict[str, Any],
    phase: str,
) -> float:
    work_sec = _number(assignment.get("work_sec"))
    rounds = _number(assignment.get("effective_rounds"))
    if rounds is None or rounds <= 0:
        rounds = _number(assignment.get("rounds"))
    if work_sec is not None and work_sec > 0 and rounds is not None and rounds > 0:
        return work_sec * rounds

    option = _selected_option_by_slot(
        candidate_pools,
        phase=phase,
        slot_id=assignment.get("slot_id"),
    )
    if option is None:
        return 0.0
    active = composition_module._conditioning_active_work_seconds(option)
    return max(0.0, float(active or 0.0))


def _enforce_conditioning_workload_before_support(
    composition_module,
    *,
    weekly_role_map: dict[str, Any],
    candidate_pools: dict[str, Any],
    only_roles: set[int] | None,
) -> None:
    athlete_model = composition_module.get_planner_athlete_model()
    rounds_format = (
        athlete_model.get("rounds_format")
        if isinstance(athlete_model, dict)
        else None
    )

    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles", []) or []:
            if (
                not isinstance(role, dict)
                or role.get("late_fight_tail_owned")
                or str(role.get("category") or "").strip().lower() != "conditioning"
                or (only_roles is not None and id(role) not in only_roles)
            ):
                continue

            phase = composition_module._conditioning_phase_for_role(week, role)
            preferred_system = str(role.get("preferred_system") or "").strip().lower()
            target_active_work, _elapsed_cap = (
                composition_module._conditioning_phase_workload_envelope(
                    phase=phase,
                    system=preferred_system,
                    rounds_format=rounds_format,
                )
            )
            if target_active_work is None:
                continue

            policy = role.get("conditioning_composition_policy")
            if not isinstance(policy, dict):
                policy = {}
                role["conditioning_composition_policy"] = policy

            adjacent_hard_spar = bool(
                policy.get("hard_sparring_adjacent")
                or composition_module._conditioning_role_is_hard_spar_adjacent(week, role)
            )
            if adjacent_hard_spar:
                # Adjacency deliberately reduces the normal conditioning minimum;
                # embedded trunk support is already prohibited by the composer.
                continue

            assignments = [
                item
                for item in (role.get("selected_exercise_assignments") or [])
                if isinstance(item, dict)
            ]
            conditioning_assignments = [
                item
                for item in assignments
                if str(item.get("slot_group") or "").strip().lower()
                == "conditioning_slots"
                and not item.get("embedded_support")
            ]
            delivered_active_work = sum(
                _assignment_active_work_seconds(
                    composition_module,
                    item,
                    candidate_pools=candidate_pools,
                    phase=phase,
                )
                for item in conditioning_assignments
            )
            workload_met = delivered_active_work + 1e-9 >= float(target_active_work)

            policy["conditioning_selected_count"] = len(conditioning_assignments)
            policy["conditioning_target_active_work_seconds"] = float(target_active_work)
            policy["conditioning_active_work_seconds"] = round(delivered_active_work, 4)
            policy["conditioning_workload_met"] = workload_met

            if workload_met:
                # Support is genuinely optional only after the conditioning job is done.
                policy["workload_limited"] = False
                if policy.get("underfill_reason") == _UNDERFILL_REASON:
                    policy["underfill_reason"] = None
                continue

            # A TGU / trunk microdose is support, never evidence that an aerobic or
            # fight-pace role is complete. Strip embedded support from an underfilled
            # conditioning role so it cannot satisfy count-based completion logic.
            retained = [item for item in assignments if not item.get("embedded_support")]
            removed_support = len(assignments) - len(retained)
            role["selected_exercise_assignments"] = retained

            policy["selected_count"] = len(retained)
            policy["workload_limited"] = True
            if not policy.get("underfill_reason"):
                policy["underfill_reason"] = _UNDERFILL_REASON
            if removed_support:
                policy["embedded_trunk_support"] = False
                policy["embedded_trunk_support_count"] = 0
                policy["embedded_trunk_support_skip_reason"] = (
                    "conditioning_workload_unmet"
                )


def _underfilled_conditioning_errors(planning_brief: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    weekly_role_map = planning_brief.get("weekly_role_map") or {}
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles", []) or []:
            if not isinstance(role, dict):
                continue
            if str(role.get("category") or "").strip().lower() != "conditioning":
                continue
            policy = role.get("conditioning_composition_policy")
            if not isinstance(policy, dict):
                continue
            if policy.get("hard_sparring_adjacent"):
                continue
            if policy.get("conditioning_workload_met") is not False:
                continue
            errors.append(
                {
                    "code": _UNDERFILL_CODE,
                    "message": (
                        f"{str(role.get('athlete_facing_label') or role.get('role_key') or 'Conditioning session')} "
                        "does not contain enough genuine conditioning work to satisfy its phase/system workload."
                    ),
                    "phase": week.get("phase"),
                    "week_index": week.get("week_index"),
                    "role_key": role.get("role_key"),
                    "scheduled_day_hint": role.get("scheduled_day_hint"),
                    "preferred_system": role.get("preferred_system"),
                    "target_active_work_seconds": policy.get(
                        "conditioning_target_active_work_seconds"
                    ),
                    "delivered_active_work_seconds": policy.get(
                        "conditioning_active_work_seconds"
                    ),
                    "blocking": True,
                }
            )
    return errors


def _report_has_underfill(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return False
    return any(
        isinstance(item, dict) and str(item.get("code") or "") == _UNDERFILL_CODE
        for field in ("errors", "blocking_warnings", "warnings")
        for item in report.get(field, []) or []
    )


def install() -> None:
    """Require real conditioning workload before optional embedded support counts."""
    from . import session_composition as composition_module
    from . import stage2_validator as validator_module

    if getattr(composition_module, _POLICY_FLAG, False):
        return

    original = composition_module.compose_normal_conditioning_assignments

    @wraps(original)
    def compose_normal_conditioning_assignments(
        *,
        weekly_role_map: dict[str, Any],
        candidate_pools: dict[str, Any],
        only_roles: set[int] | None = None,
    ) -> dict[str, Any]:
        result = original(
            weekly_role_map=weekly_role_map,
            candidate_pools=candidate_pools,
            only_roles=only_roles,
        )
        _enforce_conditioning_workload_before_support(
            composition_module,
            weekly_role_map=result,
            candidate_pools=candidate_pools,
            only_roles=only_roles,
        )
        return result

    composition_module.compose_normal_conditioning_assignments = (
        compose_normal_conditioning_assignments
    )

    original_validate = validator_module.validate_stage2_output

    @wraps(original_validate)
    def validate_stage2_output(*, planning_brief: dict, final_plan_text: str) -> dict:
        report = original_validate(
            planning_brief=planning_brief,
            final_plan_text=final_plan_text,
        )
        extra_errors = _underfilled_conditioning_errors(planning_brief)
        if not extra_errors:
            return report

        errors = list(report.get("errors", []) or [])
        existing = {
            (item.get("code"), item.get("week_index"), item.get("role_key"))
            for item in errors
            if isinstance(item, dict)
        }
        for error in extra_errors:
            identity = (
                error.get("code"),
                error.get("week_index"),
                error.get("role_key"),
            )
            if identity not in existing:
                errors.append(error)
                existing.add(identity)
        return {**report, "errors": errors, "is_valid": False}

    validator_module.validate_stage2_output = validate_stage2_output

    # Import the release path only after the validator wrapper is installed so
    # stage2_pipeline binds the wrapped validator rather than the stale original.
    from . import stage2_pipeline as pipeline_module
    from . import stage2_policy as policy_module

    original_release_policy = policy_module.apply_stage2_release_policy
    original_build_retry = pipeline_module.build_stage2_retry

    @wraps(original_release_policy)
    def conditioning_release_policy(validator_report: dict):
        underfilled = _report_has_underfill(validator_report)
        report = original_release_policy(validator_report)
        if not underfilled:
            underfilled = _report_has_underfill(report)
        if not underfilled:
            return report
        # This is an upstream deterministic composition failure. Do not let the
        # ordinary observational release policy publish it with flags.
        return {
            **report,
            "conditioning_workload_integrity_hold": True,
            "release_decision": "hold",
            "is_athlete_releasable": False,
            "is_publishable": False,
        }

    @wraps(original_build_retry)
    def conditioning_build_stage2_retry(*args, **kwargs):
        result = original_build_retry(*args, **kwargs)
        report = result.get("validator_report") if isinstance(result, dict) else None
        if not _report_has_underfill(report):
            return result
        # Renderer repair cannot invent planner-owned conditioning volume. Route
        # the failure back to the deterministic planner instead of asking the LLM
        # to rewrite an under-dosed closed session.
        return {
            **result,
            "status": "FAIL",
            "needs_retry": False,
            "requires_planner_regeneration": True,
            "repair_prompt": None,
            "summary": "FAIL: conditioning workload requires deterministic planner regeneration.",
            "summary_lines": [
                str(item.get("message") or "Conditioning workload is underfilled.")
                for item in (report.get("errors", []) if isinstance(report, dict) else [])
                if isinstance(item, dict) and item.get("code") == _UNDERFILL_CODE
            ],
        }

    policy_module.apply_stage2_release_policy = conditioning_release_policy
    # stage2_pipeline imported the policy function by value.
    pipeline_module.apply_stage2_release_policy = conditioning_release_policy
    pipeline_module.build_stage2_retry = conditioning_build_stage2_retry
    setattr(composition_module, _POLICY_FLAG, True)
