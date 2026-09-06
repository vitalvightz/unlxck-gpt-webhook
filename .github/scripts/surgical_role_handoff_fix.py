from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match in {path}, found {count}")
    file.write_text(text.replace(old, new, 1))


role_map = "fightcamp/stage2_role_map.py"
replace_once(
    role_map,
    "def _preferred_boxer_conditioning_sequence(phase: str, conditioning_sequence: list[str]) -> list[str]:\n",
    '''def _prioritize_must_keep_conditioning_systems(
    conditioning_sequence: list[str],
    week_entry: dict,
) -> list[str]:
    """Give existing must-keep conditioning systems first claim on finite slots.

    This does not choose a universal SPP/GPP pair. It only reorders the existing
    phase/limiter sequence so systems the canonical weekly rule state already
    marks must-keep are represented before optional systems.
    """
    sequence = [
        str(system).strip().lower()
        for system in conditioning_sequence
        if str(system).strip()
    ]
    resolved_rule_state = dict(week_entry.get("resolved_rule_state") or {})
    must_keep = resolved_rule_state.get("must_keep", week_entry.get("must_keep", []))
    required = [
        str(system).strip().lower()
        for system in (must_keep or [])
        if str(system).strip().lower() in {"aerobic", "glycolytic", "alactic"}
    ]
    return dedupe_preserve_order([*required, *sequence])


def _preferred_boxer_conditioning_sequence(phase: str, conditioning_sequence: list[str]) -> list[str]:
''',
)
replace_once(
    role_map,
    '''            conditioning_sequence = _preferred_boxer_conditioning_sequence(
                week_entry.get("phase", ""),
                conditioning_sequence,
            )
        session_roles: list[dict] = []
''',
    '''            conditioning_sequence = _preferred_boxer_conditioning_sequence(
                week_entry.get("phase", ""),
                conditioning_sequence,
            )
        conditioning_sequence = _prioritize_must_keep_conditioning_systems(
            conditioning_sequence,
            week_entry,
        )
        session_roles: list[dict] = []
''',
)

fillers = "fightcamp/camp_week_fillers.py"
replace_once(
    fillers,
    '''    if not weeks or _week_for_d_day(weeks, 13) is None:
        return False

    finished_tail = build_finished_late_fight_tail(
        days_until_fight,
        athlete_model,
        start_day=13,
    )
''',
    '''    handoff_week = _week_for_d_day(weeks, 13) if weeks else None
    if handoff_week is None:
        return False

    resolved_rule_state = dict(handoff_week.get("resolved_rule_state") or {})
    must_keep = resolved_rule_state.get("must_keep", handoff_week.get("must_keep", []))
    if not isinstance(must_keep, (list, tuple, set)):
        must_keep = []
    parent_required_conditioning_systems = []
    for raw_system in must_keep:
        system = str(raw_system).strip().lower()
        if (
            system in {"aerobic", "glycolytic", "alactic"}
            and system not in parent_required_conditioning_systems
        ):
            parent_required_conditioning_systems.append(system)

    tail_athlete_model = dict(athlete_model)
    if parent_required_conditioning_systems:
        # Handoff context only: the existing D-13 allocator remains the owner of
        # role legality/placement and may still reject work its countdown rules ban.
        tail_athlete_model["handoff_required_conditioning_systems"] = (
            parent_required_conditioning_systems
        )

    finished_tail = build_finished_late_fight_tail(
        days_until_fight,
        tail_athlete_model,
        start_day=13,
    )
''',
)

late = "fightcamp/stage2_payload_late_fight.py"
replace_once(
    late,
    "def _late_fight_candidate_roles(\n",
    '''def _handoff_required_alactic_labels(
    legal_countdown_labels: list[str],
    athlete_model: dict[str, Any],
) -> list[str]:
    """Keep a parent-required alactic touch inside the D-13..D-8 handoff band.

    The parent week can require alactic work, but D-13 inward remains owned by
    the late-fight allocator. Narrow only that already-legal alactic candidate
    to the parent SPP sub-window; never resurrect glycolytic work or bypass
    countdown safety.
    """
    required = {
        str(system).strip().lower()
        for system in clean_list(
            athlete_model.get("handoff_required_conditioning_systems", [])
        )
    }
    if "alactic" not in required:
        return legal_countdown_labels

    scoped: list[str] = []
    for label in legal_countdown_labels:
        text = str(label or "").strip().upper()
        if not text.startswith("D-"):
            continue
        try:
            offset = int(text[2:])
        except ValueError:
            continue
        if 8 <= offset <= 13:
            scoped.append(label)
    return scoped or legal_countdown_labels


def _late_fight_candidate_roles(
''',
)
replace_once(
    late,
    '''                    selection_rule="Use one alactic sharpness exposure instead of a normal conditioning build.",
                    placement_rule="Keep this brief and crisp; do not turn it into density work.",
                    selection_priority=106,
                    required=True,
                    legal_countdown_labels=legal_countdown_labels,
''',
    '''                    selection_rule="Use one alactic sharpness exposure instead of a normal conditioning build.",
                    placement_rule="Keep this brief and crisp; do not turn it into density work.",
                    selection_priority=106,
                    required=True,
                    legal_countdown_labels=_handoff_required_alactic_labels(
                        legal_countdown_labels,
                        athlete_model,
                    ),
''',
)

finalizer = "fightcamp/stage2_finalizer_packet.py"
replace_once(
    finalizer,
    "def build_stage2_finalizer_packet(\n",
    '''def _lock_weekly_session_spine(packet: dict[str, Any]) -> None:
    """Expose the compact role map as an exact render spine for the finalizer."""
    selected_plan = packet.get("selected_plan")
    if not isinstance(selected_plan, dict):
        return
    compact_map = selected_plan.get("weekly_role_map")
    if not isinstance(compact_map, dict):
        return

    spine: list[dict[str, Any]] = []
    for week in compact_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        sessions: list[dict[str, Any]] = []
        for role in week.get("session_roles", []) or []:
            if not isinstance(role, dict) or role.get("render_mandatory") is False:
                continue
            if (
                role.get("coach_owned")
                and str(role.get("category") or "").lower() == "sparring"
            ):
                continue
            session = {
                "role_key": role.get("role_key"),
                "category": role.get("category"),
                "athlete_facing_label": role.get("athlete_facing_label"),
                "scheduled_day_hint": role.get("scheduled_day_hint"),
                "scheduled_countdown_label": (
                    role.get("scheduled_countdown_label")
                    or role.get("countdown_label")
                ),
            }
            sessions.append(
                {
                    key: value
                    for key, value in session.items()
                    if value not in (None, "")
                }
            )
        if sessions:
            spine.append(
                {
                    "week_index": week.get("week_index"),
                    "phase": week.get("phase"),
                    "sessions": sessions,
                }
            )

    if not spine:
        return
    selected_plan["deterministic_session_spine"] = spine
    packet.setdefault("hard_rules", []).append(
        "selected_plan.deterministic_session_spine is the exact athlete-visible "
        "week/day/session structure produced by deterministic planning. Render every "
        "listed session exactly once at its supplied day/countdown. Do not drop, merge, "
        "move, or invent session roles. Exercise wording may vary only inside the "
        "selected assignments and downstream safety/render contracts."
    )


def build_stage2_finalizer_packet(
''',
)
replace_once(
    finalizer,
    '''    _lock_sparse_hard_conditioning_contract(packet)

    tail_contracts = _late_fight_tail_contracts(weekly_role_map)
''',
    '''    _lock_sparse_hard_conditioning_contract(packet)
    _lock_weekly_session_spine(packet)

    tail_contracts = _late_fight_tail_contracts(weekly_role_map)
''',
)

Path("tests/test_d14_d13_role_handoff_surgical.py").write_text(
    r'''from __future__ import annotations

import fightcamp.camp_week_fillers as fillers
from fightcamp.camp_week_fillers import _splice_late_fight_tail
from fightcamp.late_fight_tail import build_finished_late_fight_tail
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_role_map import _prioritize_must_keep_conditioning_systems


def _role(role_key: str, d_day: int, weekday: str, category: str = "conditioning") -> dict:
    return {
        "role_key": role_key,
        "category": category,
        "scheduled_countdown_label": f"D-{d_day}",
        "countdown_label": f"D-{d_day}",
        "countdown_offset": d_day,
        "scheduled_day_hint": weekday,
        "athlete_facing_label": role_key.replace("_", " ").title(),
    }


def test_must_keep_conditioning_gets_first_claim_without_fixed_spp_pair() -> None:
    week = {
        "must_keep": ["rehab", "glycolytic", "alactic", "primary_strength"],
        "resolved_rule_state": {
            "must_keep": ["rehab", "glycolytic", "alactic", "primary_strength"]
        },
    }
    assert _prioritize_must_keep_conditioning_systems(
        ["aerobic", "glycolytic", "alactic"], week
    ) == ["glycolytic", "alactic", "aerobic"]

    aerobic_week = {"resolved_rule_state": {"must_keep": ["aerobic", "glycolytic"]}}
    assert _prioritize_must_keep_conditioning_systems(
        ["alactic", "glycolytic", "aerobic"], aerobic_week
    ) == ["aerobic", "glycolytic", "alactic"]


def test_d13_splice_passes_parent_required_systems_to_existing_tail_owner(monkeypatch) -> None:
    weekly_role_map = {
        "weeks": [
            {
                "week_index": 2,
                "phase": "SPP",
                "calendar_days": [
                    {"weekday": "monday", "d_day": 14},
                    {"weekday": "tuesday", "d_day": 13},
                ],
                "resolved_rule_state": {
                    "must_keep": ["rehab", "glycolytic", "alactic", "primary_strength"]
                },
                "session_roles": [_role("normal_d13", 13, "tuesday")],
                "intentionally_unused_days": [],
            }
        ]
    }
    captured: dict = {}

    def fake_finished_tail(days_until_fight, model, *, start_day):
        captured["systems"] = model.get("handoff_required_conditioning_systems")
        return {
            "session_sequence": [_role("late_d13", 13, "tuesday")],
            "day_metadata": {
                13: {
                    "stage_key": "d13_to_d8",
                    "payload_mode": "pre_fight_compressed_payload",
                }
            },
            "segments": [
                {
                    "stage_key": "d13_to_d8",
                    "payload_mode": "pre_fight_compressed_payload",
                    "countdown_span": {"start_day": 13, "end_day": 8},
                }
            ],
        }

    monkeypatch.setattr(fillers, "build_finished_late_fight_tail", fake_finished_tail)
    assert _splice_late_fight_tail(
        weekly_role_map,
        {"days_until_fight": 22, "training_days": ["monday", "tuesday"]},
    ) is True
    assert captured["systems"] == ["glycolytic", "alactic"]


def test_production_shaped_d22_handoff_keeps_required_alactic_inside_d13_to_d8() -> None:
    athlete = {
        "sport": "boxing",
        "fight_format": "boxing",
        "days_until_fight": 22,
        "fight_date": "2026-09-28",
        "next_fight_date": "2026-09-28",
        "plan_creation_weekday": "sunday",
        "training_frequency": 4,
        "weekly_training_frequency": 4,
        "days_available": 4,
        "training_days": ["monday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "fatigue": "moderate",
        "fatigue_level": "moderate",
        "readiness_flags": [],
        "injuries": [],
        "restrictions": [],
        "weight_cut_risk": False,
        "cut_severity_bucket": "low",
        "key_goals": ["conditioning", "speed"],
        "weaknesses": ["conditioning"],
        "equipment": [
            "bodyweight",
            "bands",
            "medicine_ball",
            "assault_bike",
            "rower",
        ],
        "handoff_required_conditioning_systems": ["glycolytic", "alactic"],
    }
    tail = build_finished_late_fight_tail(22, athlete, start_day=13)
    alactic_offsets = [
        int(role.get("countdown_offset"))
        for role in tail.get("session_sequence", [])
        if isinstance(role, dict)
        and role.get("role_key") == "alactic_sharpness_day"
        and isinstance(role.get("countdown_offset"), int)
    ]
    assert alactic_offsets
    assert any(8 <= offset <= 13 for offset in alactic_offsets)

    hard_glycolytic_keys = {
        "fight_pace_repeatability_day",
        "main_fight_pace_day",
        "highest_glycolytic_day",
        "controlled_repeatability_day",
    }
    assert not any(
        isinstance(role, dict)
        and role.get("role_key") in hard_glycolytic_keys
        and isinstance(role.get("countdown_offset"), int)
        and 8 <= role["countdown_offset"] <= 13
        for role in tail.get("session_sequence", [])
    )


def test_finalizer_packet_exposes_exact_compact_session_spine() -> None:
    weekly_role_map = {
        "weeks": [
            {
                "week_index": 2,
                "phase": "SPP",
                "session_roles": [
                    _role("alactic_sharpness_day", 12, "wednesday"),
                    _role("tactical_watch", 10, "friday", category="support_insert"),
                ],
            }
        ]
    }
    packet = build_stage2_finalizer_packet(
        stage2_payload={"weekly_role_map": weekly_role_map},
        planning_brief={
            "weekly_role_map": weekly_role_map,
            "candidate_pools": {},
            "athlete_snapshot": {},
        },
    )
    spine = packet["selected_plan"]["deterministic_session_spine"]
    assert [session["role_key"] for session in spine[0]["sessions"]] == [
        "alactic_sharpness_day",
        "tactical_watch",
    ]
    assert spine[0]["sessions"][0]["scheduled_countdown_label"] == "D-12"
    assert any(
        "Do not drop, merge, move, or invent session roles" in rule
        for rule in packet["hard_rules"]
    )
'''
)
