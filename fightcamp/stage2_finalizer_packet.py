"""Stage 2 finalizer packet plus downstream late-fight contract propagation.

The established compaction implementation lives in
``stage2_finalizer_packet_impl``. This compatibility surface adds one thing the
long-camp D-13 handoff needs: the actual existing payload-mode contracts, not
just their names, survive into the finalizer packet as hard rendering authority.
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
    shared, segments = _hoist_shared_contract(segments)
    contracts = {
        "active": True,
        "normal_planner_through_d": handoff.get("normal_planner_through_d", 14),
        "late_fight_planner_from_d": handoff.get("late_fight_planner_from_d", 13),
        "source": handoff.get("source") or "finished_existing_late_fight_path",
        "segments": segments,
    }
    if shared:
        contracts["shared_render_contract"] = shared
    return contracts


def _hoist_shared_contract(
    segments: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Lift the paragraphs every segment repeats into one shared contract.

    ``_handoff_mode_instructions`` composes each payload mode's contract from a
    common countdown preamble plus that window's own rules, so the six tail
    segments carried the same ~3.3k of common text six times (~16.5k duplicated
    on a real late camp). The model was reading one rule six times and had to
    infer that the copies were identical rather than subtly different.

    Only lines present in EVERY segment are hoisted, and each segment keeps its
    own remaining lines in their original order, so no window loses a rule.
    """
    contracts = [str(segment.get("render_contract") or "") for segment in segments]
    if len(contracts) < 2 or not all(contracts):
        return "", segments

    line_sets = [set(contract.splitlines()) for contract in contracts]
    shared_lines = set.intersection(*line_sets)
    # A blank line is not a rule; hoisting it would only strip the formatting.
    shared_lines = {line for line in shared_lines if line.strip()}
    if not shared_lines:
        return "", segments

    # Preserve the order the first segment states them in.
    shared = "\n".join(
        line for line in contracts[0].splitlines() if line in shared_lines
    )
    trimmed: list[dict[str, Any]] = []
    for segment, contract in zip(segments, contracts):
        remaining = "\n".join(
            line for line in contract.splitlines() if line not in shared_lines
        ).strip()
        trimmed.append({**segment, "render_contract": remaining})
    return shared, trimmed


def build_stage2_finalizer_packet(
    *,
    stage2_payload: dict[str, Any],
    planning_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the normal compact packet, then preserve tail render contracts."""
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

    tail_contracts = _late_fight_tail_contracts(weekly_role_map)
    if not tail_contracts:
        return packet

    selected_plan = packet.setdefault("selected_plan", {})
    selected_plan["late_fight_tail_handoff"] = deepcopy(tail_contracts)

    hard_rules = packet.setdefault("hard_rules", [])
    if tail_contracts.get("shared_render_contract"):
        hard_rules.append(
            "selected_plan.late_fight_tail_handoff.shared_render_contract applies to "
            "EVERY tail segment. Each segment's own render_contract carries only the "
            "rules specific to its countdown window; read the shared contract plus "
            "that segment's rules together."
        )
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
