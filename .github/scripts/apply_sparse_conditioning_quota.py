from pathlib import Path

# 1) Weekly stress-intent owner: raise the conditioning quota by exactly one.
p = Path("fightcamp/stage2_planning_brief.py")
s = p.read_text()

helper_anchor = "def _cap_session_counts_to_frequency(session_counts: dict, training_context: TrainingContext) -> dict:\n"
helper = '''def _declared_combat_gym_day_count(training_context: TrainingContext) -> int:
    days = {
        str(day).strip().lower()
        for values in (
            training_context.hard_sparring_days,
            training_context.support_work_days,
            training_context.technical_skill_days,
        )
        for day in clean_list(values)
        if str(day).strip()
    }
    return len(days)


def _sparse_conditioning_quota_boost_requested(
    training_context: TrainingContext, phase: str
) -> bool:
    if str(phase or "").upper() not in {"GPP", "SPP"}:
        return False

    goals = _normalize_limiter_tokens(clean_list(training_context.key_goals))
    weaknesses = _normalize_limiter_tokens(clean_list(training_context.weaknesses))
    conditioning_priority = bool(
        goals & {"conditioning", "conditioning_endurance"}
        or weaknesses
        & {"gas_tank", "conditioning", "conditioning_endurance", "endurance", "work_capacity"}
    )
    return conditioning_priority and _declared_combat_gym_day_count(training_context) <= 1


def _apply_sparse_conditioning_quota_boost(
    session_counts: dict, training_context: TrainingContext, phase: str
) -> tuple[dict, bool]:
    adjusted = dict(session_counts)
    active = _sparse_conditioning_quota_boost_requested(training_context, phase)
    if active:
        adjusted["conditioning"] = int(adjusted.get("conditioning", 0) or 0) + 1
    return adjusted, active


'''
if helper not in s:
    if helper_anchor not in s:
        raise SystemExit("planning brief helper anchor not found")
    s = s.replace(helper_anchor, helper + helper_anchor, 1)

old = '''        session_counts = _cap_session_counts_to_frequency(
            _apply_conditioning_priority_session_shift(
                allocate_sessions(training_context.training_frequency, phase),
                training_context,
            ),
            training_context,
        )
        risk_flags: list[str] = []
'''
new = '''        session_counts = _cap_session_counts_to_frequency(
            _apply_conditioning_priority_session_shift(
                allocate_sessions(training_context.training_frequency, phase),
                training_context,
            ),
            training_context,
        )
        session_counts, sparse_conditioning_quota_boost = _apply_sparse_conditioning_quota_boost(
            session_counts, training_context, phase
        )
        selection_guardrails = _build_phase_selection_guardrails(phase, training_context)
        if sparse_conditioning_quota_boost:
            selection_guardrails["conditioning_quota_boost"] = {
                "count": 1,
                "required_system": "glycolytic",
            }
        risk_flags: list[str] = []
'''
if old not in s:
    raise SystemExit("phase brief quota anchor not found")
s = s.replace(old, new, 1)

old = '            "selection_guardrails": _build_phase_selection_guardrails(phase, training_context),\n'
if old not in s:
    raise SystemExit("selection guardrails anchor not found")
s = s.replace(old, '            "selection_guardrails": selection_guardrails,\n', 1)
p.write_text(s)

# 2) Role-budget owner: carry that intent, let exactly +1 survive the normal
# frequency cap when a real training day exists, and make the extra exposure
# non-aerobic. Placement/safety/taper owners remain untouched.
p = Path("fightcamp/stage2_role_map.py")
s = p.read_text()

old = '''                    "conditioning_sequence": list(stress.get("conditioning_sequence", [])),
                    "highest_neural_day": stress.get("highest_neural_day", ""),
'''
new = '''                    "conditioning_sequence": list(stress.get("conditioning_sequence", [])),
                    "conditioning_quota_boost": dict(guardrails.get("conditioning_quota_boost") or {}),
                    "highest_neural_day": stress.get("highest_neural_day", ""),
'''
if old not in s:
    raise SystemExit("week progression guardrail anchor not found")
s = s.replace(old, new, 1)

old = '''    sessions_per_week = int(athlete_model.get("training_frequency") or len(training_days))
    weekly_cap = min(sessions_per_week, len(training_days))
'''
new = '''    sessions_per_week = int(athlete_model.get("training_frequency") or len(training_days))
    quota_boost = week_entry.get("conditioning_quota_boost") or {}
    if isinstance(quota_boost, dict) and int(quota_boost.get("count") or 0) > 0:
        sessions_per_week += int(quota_boost.get("count") or 0)
    weekly_cap = min(sessions_per_week, len(training_days))
'''
if old not in s:
    raise SystemExit("weekly cap anchor not found")
s = s.replace(old, new, 1)

old = '''        if sport_key == "boxing" and week_entry.get("phase", "").upper() in {"GPP", "SPP"}:
            conditioning_sequence = _prioritize_required_conditioning_systems(
                conditioning_sequence,
                week_entry,
            )
        session_roles: list[dict] = []
'''
new = '''        if sport_key == "boxing" and week_entry.get("phase", "").upper() in {"GPP", "SPP"}:
            conditioning_sequence = _prioritize_required_conditioning_systems(
                conditioning_sequence,
                week_entry,
            )
        quota_boost = week_entry.get("conditioning_quota_boost") or {}
        required_boost_system = (
            str(quota_boost.get("required_system") or "").strip().lower()
            if isinstance(quota_boost, dict)
            else ""
        )
        if required_boost_system in {"glycolytic", "alactic"}:
            conditioning_sequence = [required_boost_system] + [
                system for system in conditioning_sequence if system != required_boost_system
            ]
        session_roles: list[dict] = []
'''
if old not in s:
    raise SystemExit("conditioning priority anchor not found")
s = s.replace(old, new, 1)
p.write_text(s)

# 3) Focused regressions in a new file only.
t = Path("tests/test_sparse_conditioning_quota_plus_one.py")
t.write_text('''from types import SimpleNamespace

from fightcamp.stage2_planning_brief import (
    _apply_sparse_conditioning_quota_boost,
    _sparse_conditioning_quota_boost_requested,
)
from fightcamp.stage2_role_map import _build_weekly_role_map


def _context(*, goals=None, weaknesses=None, hard=None, support=None, technical=None):
    return SimpleNamespace(
        key_goals=goals or [],
        weaknesses=weaknesses or [],
        hard_sparring_days=hard or [],
        support_work_days=support or [],
        technical_skill_days=technical or [],
    )


def test_sparse_conditioning_goal_adds_exactly_one_quota_slot():
    context = _context(goals=["conditioning"])
    counts, active = _apply_sparse_conditioning_quota_boost(
        {"strength": 1, "conditioning": 2, "recovery": 1}, context, "GPP"
    )
    assert active is True
    assert counts == {"strength": 1, "conditioning": 3, "recovery": 1}


def test_gas_tank_weakness_triggers_but_two_gym_days_do_not():
    sparse = _context(weaknesses=["gas_tank"], support=["monday"])
    assert _sparse_conditioning_quota_boost_requested(sparse, "SPP") is True

    not_sparse = _context(
        weaknesses=["gas_tank"], hard=["tuesday"], technical=["thursday"]
    )
    assert _sparse_conditioning_quota_boost_requested(not_sparse, "SPP") is False


def test_taper_never_receives_sparse_conditioning_quota_boost():
    context = _context(goals=["conditioning"])
    assert _sparse_conditioning_quota_boost_requested(context, "TAPER") is False


def test_quota_boost_survives_role_cap_and_is_non_aerobic():
    athlete_model = {
        "sport": "boxing",
        "training_frequency": 4,
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "saturday"],
        "fight_date": "2027-07-18",
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "injury_mode": "full_plan",
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "technical_skill_days": [],
    }
    progression = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 3, "recovery": 0},
                "conditioning_sequence": ["aerobic", "glycolytic", "alactic"],
                "conditioning_quota_boost": {"count": 1, "required_system": "glycolytic"},
            },
            {
                "week_index": 2,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["aerobic", "glycolytic"],
            },
            {
                "week_index": 3,
                "phase": "SPP",
                "stage_key": "fight_specific",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["glycolytic", "alactic"],
            },
            {
                "week_index": 4,
                "phase": "TAPER",
                "stage_key": "taper",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 1},
                "conditioning_sequence": ["alactic"],
            },
        ]
    }

    role_map = _build_weekly_role_map(
        athlete_model, progression, {"key": "conditioning_endurance"}
    )
    first_week = role_map["weeks"][0]
    systems = [
        role.get("preferred_system")
        for role in first_week["session_roles"]
        if role.get("category") == "conditioning"
    ]
    assert len(systems) == 3
    assert systems[0] == "glycolytic"
    assert systems[0] != "aerobic"
    assert len(first_week["session_roles"]) <= len(athlete_model["training_days"])
''')
