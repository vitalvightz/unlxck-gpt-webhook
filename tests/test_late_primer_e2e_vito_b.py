"""End-to-end late-camp coverage: the Vito B regression plus a safety sweep.

Runs the real Stage 1 entry point with a pinned clock and fixed seed (no model
call). Vito B is a low-fatigue, uninjured-in-effect amateur kickboxer (speed
primary, power secondary, counter striker, 5 sessions/week, hard sparring
Thursday, light combat Monday, non-limiting blister, no weight target), fight on
26 October 2026. Before this change every countdown primer (D-13, D-7, D-5) of
a long camp shipped as a single ``Pull-Counter-Reset 2 x 5 s`` while Stage 1
held legal speed/power anchors.

Nothing here is specific to Vito B in the generator; the sweep checks the same
invariants for high fatigue, an aggressive cut, a limiting injury, two hard
sparring days and other combat sports.
"""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from api.models import PlanRequest
from fightcamp.main import generate_plan_sync
from fightcamp.stage2_payload import LATE_PRIMER_MAX_MEMBERS, LATE_PRIMER_ROLE_KEYS
from planner_clock import pin_planner_clock

_FIGHT = dt.datetime(2026, 10, 26, 10)
_BLISTER = {
    "area": "Core", "zone": "core", "avoid": "", "notes": "[training_impact:not_limiting]", "trend": "stable",
    "cleared": "", "severity": "low", "timeframe": "", "open_wound": "yes", "injury_type": "surface_injury",
    "surface_type": "blister", "impact_related": "", "sensitive_area": "", "bleeding_status": "",
    "infection_signs": [], "injury_subtypes": ["surface_injury:blister"],
}
_VITO_B = {
    "notes": "", "athlete": {"age": 23, "sex": "male", "record": "4-2", "stance": "Orthodox", "full_name": "Vito B",
                             "height_cm": 190, "weight_kg": 80, "athlete_locale": "", "tactical_style": ["counter_striker"],
                             "technical_style": ["kickboxing"], "athlete_timezone": "Europe/London",
                             "target_weight_kg": None, "professional_status": "amateur"},
    "injuries": "Core (low, stable). Type: surface_injury. Surface: blister. Open wound: yes. Notes: [training_impact:not_limiting]",
    "key_goals": ["speed", "power"], "fight_date": "2026-10-26", "weak_areas": ["speed"], "primary_goal": "speed",
    "fatigue_level": "low", "guided_injury": _BLISTER, "rounds_format": "3 x 3", "guided_injuries": [_BLISTER],
    "open_camp_weeks": 12,
    "equipment_access": ["trap_bar", "sled", "barbell", "heavy_bag", "bench", "foam_roller", "plate", "bosu_ball",
                         "atlas_stone", "log", "step_mill", "sledgehammer", "pool", "agility_ladder", "jump_rope", "trx",
                         "pullup_bar", "weight_belt", "water_jug", "bulgarian_bag"],
    "primary_weak_area": "speed", "support_work_days": ["Monday"], "hard_sparring_days": ["Thursday"],
    "mindset_challenges": "", "no_scheduled_fight": False, "training_preference": "",
    "training_availability": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    "reduced_contact_requested": False, "weekly_training_frequency": 5,
    "goal_weakness_collision_tags": ["speed"], "goal_weakness_collision_detail": "",
    "goal_weakness_collision_details": [{"tag": "speed", "label": "Speed", "detail": ""}],
}
_VARIANTS = {
    "vito_b": {},
    "high_fatigue": {"fatigue_level": "high"},
    "aggressive_cut": {"athlete": {"target_weight_kg": 72}},
    "limiting_knee": {"injuries": "", "guided_injury": None, "guided_injuries": [
        {"area": "Left knee", "severity": "moderate", "trend": "stable", "injury_type": "pain", "timeframe": "last_month"}]},
    "two_hard_days": {"hard_sparring_days": ["Tuesday", "Thursday"]},
    "mma": {"athlete": {"technical_style": ["mma"]}},
    "muay_thai": {"athlete": {"technical_style": ["muay_thai"]}},
}
_CACHE: dict[tuple[str, int], dict] = {}


def _brief(variant: str, days_out: int) -> dict:
    key = (variant, days_out)
    if key not in _CACHE:
        intake = copy.deepcopy(_VITO_B)
        for field, value in _VARIANTS[variant].items():
            if field == "athlete":
                intake["athlete"].update(value)
            else:
                intake[field] = value
        payload = PlanRequest(**intake).to_payload()
        payload["random_seed"] = 7
        payload["_triage_resume_override"] = {"approved": True, "allowed_modes": ["needs_review", "restricted_rehab_only"]}
        mp = pytest.MonkeyPatch()
        pin_planner_clock(mp, _FIGHT - dt.timedelta(days=days_out))
        try:
            _CACHE[key] = generate_plan_sync(payload)["planning_brief"]
        finally:
            mp.undo()
    return _CACHE[key]


def _roles(brief: dict) -> list[dict]:
    if "late_fight_session_sequence" in brief:
        return list(brief["late_fight_session_sequence"])
    return [role for week in brief["weekly_role_map"]["weeks"] for role in week["session_roles"]]


def _primers(brief: dict) -> dict[int, dict]:
    out = {}
    for role in _roles(brief):
        if role.get("role_key") in LATE_PRIMER_ROLE_KEYS and role.get("selected_exercise_assignments"):
            label = str(role.get("scheduled_countdown_label") or "")
            if label.startswith("D-"):
                out[int(label[2:])] = role
    return out


def _members(role: dict) -> list[dict]:
    return [m for m in role.get("selected_exercise_assignments") or [] if isinstance(m, dict)]


def _stage1_names(brief: dict, phase: str) -> set[str]:
    pool = brief["candidate_pools"].get(phase) or {}
    names = set()
    for group in ("strength_slots", "conditioning_slots", "late_tail_candidates"):
        for slot in pool.get(group) or []:
            for option in [slot.get("selected") or {}, *(slot.get("alternates") or [])]:
                if option.get("name"):
                    names.add(option["name"])
    return names


def _assert_primer_invariants(brief: dict) -> None:
    for d_day, role in _primers(brief).items():
        members = _members(role)
        names = [m["name"] for m in members]
        assert 1 <= len(members) <= LATE_PRIMER_MAX_MEMBERS, (d_day, names)
        assert len(set(names)) == len(names), (d_day, names)
        # Membership authority: every member is a Stage 1 candidate (or its
        # authorised alternate) of the phase that owns the scheduled day.
        for member in members:
            assert member["name"] in _stage1_names(brief, member["source_phase"]), (d_day, member)
        # Every strength member carries the resolver's effective dose.
        resolved = {item["name"] for item in role.get("effective_strength_prescriptions") or []}
        for member in members:
            if member.get("slot_group") == "strength_slots":
                assert member["name"] in resolved, (d_day, member["name"])
        loaded = [item for item in role.get("effective_strength_prescriptions") or [] if item.get("effective_loaded")]
        assert len(loaded) <= 1, (d_day, loaded)
        # Complements are a single set.
        complements = {m["name"] for m in members if m.get("primer_complement")}
        for item in role.get("effective_strength_prescriptions") or []:
            if item["name"] in complements and isinstance(item.get("effective_max_sets"), int):
                assert item["effective_max_sets"] == 1, item
        # A measured session is stamped and never above moderate. A session the
        # measurement cannot see keeps its planned vector and takes no
        # complement: unknown is never evidence that more work fits.
        stamp = role.get("calendar_stress")
        if stamp:
            assert stamp["authority"] == "realised_session_composition", d_day
            assert stamp["neural_mechanical"] <= 2, (d_day, stamp)
        else:
            assert len(members) == 1, (d_day, names)
        # Nothing heavy reaches the last two days.
        assert d_day >= 2, (d_day, names)


@pytest.mark.parametrize("days_out", [21, 17, 14, 13, 10, 7, 5, 2, 1, 0])
def test_vito_b_countdown_primers_keep_their_invariants(days_out):
    brief = _brief("vito_b", days_out)
    _assert_primer_invariants(brief)
    # D-1 and D-0 never carry a primer session.
    assert not {d for d in _primers(brief) if d <= 1}


@pytest.mark.parametrize("days_out", [14, 13])
def test_vito_b_d13_session_leads_with_meaningful_goal_relevant_power(days_out):
    """The reported failure: D-13 shipped Pull-Counter-Reset alone."""
    role = _primers(_brief("vito_b", days_out))[13]
    members = _members(role)
    assert members[0]["name"] == "Jump-in-Place (Max Frequency)"
    assert len(members) >= 2
    assert not role.get("support_only_fill")
    dose = {item["name"]: item for item in role["effective_strength_prescriptions"]}
    assert dose["Jump-in-Place (Max Frequency)"]["effective_prescription"].startswith("2 x 2")


@pytest.mark.parametrize("days_out", [14, 13])
def test_vito_b_no_primer_day_repeats_one_drill_alone(days_out):
    primers = _primers(_brief("vito_b", days_out))
    assert {13, 6, 5} <= set(primers)
    for d_day in (13, 6, 5):
        assert [m["name"] for m in _members(primers[d_day])] != ["Pull-Counter-Reset"], d_day


def _suppressed(brief: dict) -> list[dict]:
    if "late_fight_session_sequence" in brief:
        return list((brief.get("late_fight_plan_spec") or {}).get("suppressed_roles") or [])
    return [r for week in brief["weekly_role_map"]["weeks"] for r in week.get("suppressed_roles") or []]


@pytest.mark.parametrize("days_out", [21, 17, 14, 13, 10])
def test_vito_b_d7_primer_moves_off_the_light_combat_day_instead_of_disappearing(days_out):
    """The neural primer was placed on Monday's declared light combat (D-7).

    The policy forbids that stack and the primer is a small stimulus, so it moves
    to the adjacent training day the policy allows (Tuesday, D-6), taking the
    day from a subordinate occupancy filler. It is neither shipped forbidden nor
    silently dropped, and no conflict is left on the final calendar.
    """
    brief = _brief("vito_b", days_out)
    primers = _primers(brief)
    assert 7 not in primers
    primer = primers[6]
    assert primer["role_key"] == "neural_primer_day"
    resolution = primer["late_load_resolution"]
    assert resolution["action"] == "relocated_to_adjacent_day"
    assert resolution["from_d_day"] == 7 and resolution["to_d_day"] == 6
    assert resolution["conflict_reason_code"] == "exclusive_physical_slot_conflict"
    assert str(primer["scheduled_day_hint"]).lower() == "tuesday"
    # The filler it displaced is gone from D-6; light combat still owns D-7.
    roles = _roles(brief)
    assert not [r for r in roles if r.get("role_key") == "joint_prep" and r.get("scheduled_countdown_label") == "D-6"]
    assert [r for r in roles if r.get("role_key") == "light_combat_day" and r.get("scheduled_countdown_label") == "D-7"]
    revalidation = (brief.get("weekly_role_map") or {}).get("realised_load_revalidation") or {}
    assert not revalidation.get("residual_conflicts")


@pytest.mark.parametrize("days_out", [14, 13])
def test_vito_b_power_is_retained_when_legal(days_out):
    entry = next(e for e in _brief("vito_b", days_out)["goal_preservation"] if e["goal"] == "power")
    assert entry["satisfied"] is True
    assert any(item["d_day"] == 13 and "ballistic_power" in item["intents"] for item in entry["evidence"])


@pytest.mark.parametrize("days_out", [14, 13])
def test_vito_b_contact_spine_is_untouched(days_out):
    roles = _roles(_brief("vito_b", days_out))
    hard = sorted(r["scheduled_countdown_label"] for r in roles if r.get("role_key") == "hard_sparring_day")
    light = sorted(r["scheduled_countdown_label"] for r in roles if r.get("role_key") == "light_combat_day")
    assert hard == ["D-11", "D-4"]
    assert "D-7" in light


@pytest.mark.parametrize("variant", sorted(set(_VARIANTS) - {"vito_b"}))
@pytest.mark.parametrize("days_out", [14, 10])
def test_safety_sweep_keeps_primer_invariants(variant, days_out):
    _assert_primer_invariants(_brief(variant, days_out))


@pytest.mark.parametrize("variant", ["high_fatigue", "aggressive_cut", "limiting_knee"])
@pytest.mark.parametrize("days_out", [14, 10])
def test_risk_signals_take_one_complement_off_every_primer(variant, days_out):
    """Relaxing redundant restrictions must not make a riskier athlete's tail heavier.

    The dose owner's single readiness step removes one complement, so an
    at-risk athlete's primer holds at most two exercises.
    """
    for d_day, role in _primers(_brief(variant, days_out)).items():
        assert len(_members(role)) <= LATE_PRIMER_MAX_MEMBERS - 1, (d_day, [m["name"] for m in _members(role)])


_SPORT_OF = {"vito_b": "kickboxing", "muay_thai": "muay_thai", "mma": "mma"}


@pytest.mark.parametrize("variant", sorted(_SPORT_OF))
@pytest.mark.parametrize("days_out", [14, 13])
def test_non_boxing_strikers_get_their_own_weapons_in_the_tail(variant, days_out):
    """A kickboxer's primers are not a boxer's: kick / clinch work is represented."""
    from fightcamp.style_taper_governance import SPORT_TAGS  # noqa: F401  (bank vocabulary)
    import json
    from pathlib import Path

    bank = {item["name"]: item for item in json.loads(
        (Path(__file__).resolve().parents[1] / "data/style_taper_conditioning.json").read_text())}
    sport = _SPORT_OF[variant]
    specific = [
        member["name"]
        for role in _primers(_brief(variant, days_out)).values()
        for member in _members(role)
        if member["name"] in bank and sport in bank[member["name"]]["tags"]
        and "boxing" not in bank[member["name"]]["tags"]
    ]
    assert specific, variant
