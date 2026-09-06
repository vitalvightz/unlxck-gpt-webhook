"""Stage 2 finalizer packet plus downstream late-fight contract propagation.

The established compaction implementation lives in
``stage2_finalizer_packet_impl``. This compatibility surface preserves planner
contracts that the compact packet must not lose: late-fight tail contracts and
mandatory hard-conditioning dose/intensity owned by the weekly role map.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import stage2_finalizer_packet_impl as _impl
from .prescription_resolver import assert_late_camp_effective_strength_authority
from .stage2_payload_late_fight import _handoff_mode_instructions

for _export_name in dir(_impl):
    if not _export_name.startswith("__"):
        globals()[_export_name] = getattr(_impl, _export_name)


_HARD_CONDITIONING_CONTRACT_KEYS = (
    "combat_pressure_floor",
    "mandatory_hard_conditioning_exposure",
    "prescribed_intensity_rpe",
    "prescribed_dose",
    "floor_purpose",
    "floor_stop_rule",
    "low_impact_preferred",
    "upgraded_from_hard_stimulus_deficit",
)


def _late_fight_tail_contracts(weekly_role_map: Any) -> dict[str, Any]:
    if not isinstance(weekly_role_map, dict):
        return {}
    handoff = weekly_role_map.get("late_fight_tail_handoff")
    if not isinstance(handoff, dict) or not handoff.get("active"):
        return {}

    seen: set[tuple[str, str, int, int]] = set()
    segments: list[dict[str, Any]] = []
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        for raw_segment in week.get("late_fight_tail_segments", []) or []:
            if not isinstance(raw_segment, dict):
                continue
            stage_key = str(raw_segment.get("stage_key") or "").strip()
            payload_mode = str(raw_segment.get("payload_mode") or "").strip()
            span = raw_segment.get("countdown_span")
            if not stage_key or not payload_mode or not isinstance(span, dict):
                continue
            try:
                start_day = int(span.get("start_day"))
                end_day = int(span.get("end_day"))
            except (TypeError, ValueError):
                continue
            key = (stage_key, payload_mode, start_day, end_day)
            if key in seen:
                continue
            seen.add(key)
            contract = _handoff_mode_instructions(payload_mode)
            segments.append(
                {
                    "stage_key": stage_key,
                    "payload_mode": payload_mode,
                    "countdown_span": {
                        "start_day": start_day,
                        "end_day": end_day,
                    },
                    "render_contract": contract,
                }
            )

    if not segments:
        return {}
    segments.sort(
        key=lambda segment: int(
            (segment.get("countdown_span") or {}).get("start_day") or -1
        ),
        reverse=True,
    )
    return {
        "active": True,
        "normal_planner_through_d": handoff.get("normal_planner_through_d", 14),
        "late_fight_planner_from_d": handoff.get("late_fight_planner_from_d", 13),
        "source": handoff.get("source") or "finished_existing_late_fight_path",
        "segments": segments,
    }


def _role_identity(role: dict[str, Any]) -> tuple[Any, str, str]:
    return (
        role.get("session_index"),
        str(role.get("role_key") or "").strip(),
        str(role.get("scheduled_day_hint") or "").strip().lower(),
    )


def _propagate_hard_conditioning_contract(
    *, packet: dict[str, Any], weekly_role_map: dict[str, Any]
) -> bool:
    """Keep planner-owned hard-conditioning dose truth through compaction.

    The compact implementation intentionally drops most internal rationale, but
    RPE/dose/stop-rule on a mandatory hard-conditioning role are execution
    authority, not rationale. Losing them lets the finalizer turn a hard
    repeatability role back into generic/easy conditioning.
    """
    selected_map = (
        (packet.get("selected_plan") or {}).get("weekly_role_map")
        if isinstance(packet.get("selected_plan"), dict)
        else None
    )
    if not isinstance(selected_map, dict):
        return False

    source_weeks = [
        week for week in weekly_role_map.get("weeks", []) or [] if isinstance(week, dict)
    ]
    compact_weeks = [
        week for week in selected_map.get("weeks", []) or [] if isinstance(week, dict)
    ]
    source_by_index = {
        week.get("week_index"): week
        for week in source_weeks
        if week.get("week_index") is not None
    }

    propagated = False
    for position, compact_week in enumerate(compact_weeks):
        source_week = source_by_index.get(compact_week.get("week_index"))
        if source_week is None and position < len(source_weeks):
            source_week = source_weeks[position]
        if not isinstance(source_week, dict):
            continue

        source_roles = [
            role for role in source_week.get("session_roles", []) or [] if isinstance(role, dict)
        ]
        by_identity = {_role_identity(role): role for role in source_roles}
        for compact_role in compact_week.get("session_roles", []) or []:
            if not isinstance(compact_role, dict):
                continue
            source_role = by_identity.get(_role_identity(compact_role))
            if source_role is None:
                source_role = next(
                    (
                        role
                        for role in source_roles
                        if str(role.get("role_key") or "").strip()
                        == str(compact_role.get("role_key") or "").strip()
                        and str(role.get("scheduled_day_hint") or "").strip().lower()
                        == str(compact_role.get("scheduled_day_hint") or "").strip().lower()
                    ),
                    None,
                )
            if not isinstance(source_role, dict):
                continue
            if not (
                source_role.get("mandatory_hard_conditioning_exposure") is True
                or source_role.get("combat_pressure_floor") is True
            ):
                continue
            for key in _HARD_CONDITIONING_CONTRACT_KEYS:
                if key in source_role and source_role.get(key) not in (None, "", []):
                    compact_role[key] = deepcopy(source_role[key])
            propagated = True

    if propagated:
        hard_rules = packet.setdefault("hard_rules", [])
        hard_rule = (
            "A role with mandatory_hard_conditioning_exposure=true is a required "
            "hard physiological exposure, not low-aerobic support. Render its "
            "prescribed_intensity_rpe, prescribed_dose, purpose, and stop rule as "
            "authoritative unless a later deterministic safety/morph contract has "
            "already changed that role. Low-impact preference changes modality only, "
            "never the required intensity."
        )
        if hard_rule not in hard_rules:
            hard_rules.append(hard_rule)
    return propagated


def build_stage2_finalizer_packet(
    *,
    stage2_payload: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the normal compact packet, then preserve execution contracts."""
    source = planning_brief if isinstance(planning_brief, dict) else stage2_payload
    weekly_role_map = (
        source.get("weekly_role_map")
        or stage2_payload.get("weekly_role_map")
        or {}
    )
    candidate_pools = (
        source.get("candidate_pools")
        or stage2_payload.get("candidate_pools")
        or {}
    )
    assert_late_camp_effective_strength_authority(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
    )

    packet = _impl.build_stage2_finalizer_packet(
        stage2_payload=stage2_payload,
        planning_brief=planning_brief,
    )

    if isinstance(weekly_role_map, dict):
        _propagate_hard_conditioning_contract(
            packet=packet,
            weekly_role_map=weekly_role_map,
        )

    tail_contracts = _late_fight_tail_contracts(weekly_role_map)
    if not tail_contracts:
        return packet

    selected_plan = packet.setdefault("selected_plan", {})
    selected_plan["late_fight_tail_handoff"] = deepcopy(tail_contracts)

    hard_rules = packet.setdefault("hard_rules", [])
    hard_rules.append(
        "If selected_plan.late_fight_tail_handoff.active is true, its segments are "
        "authoritative for scheduled D-13 through D-0. Match each countdown D-day "
        "to the segment countdown_span and obey that segment's render_contract in "
        "full. These contracts override normal-camp rendering rules on those tail "
        "days; they never apply to D-14 or further out."
    )
    hard_rules.append(
        "Do not treat late_fight_tail_handoff payload-mode names as labels only. "
        "The attached render_contract text is an executable hard constraint on "
        "session type, dose, equipment, stacking, freshness, and D-0 behaviour."
    )
    return packet
