"""Fight Tactical Watch: JSON bank integrity, selection, and placement.

The athlete-facing Tactical Watch library lives in ``data/tactical_watch_bank.json``.
These tests protect the JSON itself (structure, and genuine task differentiation
rather than renamed titles) and the small amount of Python that reads, selects
and carries the chosen watch through Stage 1 -> Stage 2.
"""

from __future__ import annotations

import json
from itertools import combinations

import pytest

from fightcamp.camp_phases import BASE_PHASE_RATIOS, calculate_phase_weeks
from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.config import DATA_DIR
from fightcamp.gap_fill_inserts import apply_gap_fill_inserts
from fightcamp.stage2_finalizer_packet import _compact_role
from fightcamp.stage2_payload import build_planning_brief
from fightcamp import tactical_watch_library as library
from fightcamp.tactical_watch_library import (
    PHASES,
    STYLE_FAMILIES,
    TacticalWatchBankExhausted,
    all_watches,
    canonical_watch_signature,
    extract_tactical_style,
    normalize_tactical_style,
    ordered_phase_bank,
    select_tactical_watch,
)

BANK_PATH = DATA_DIR / "tactical_watch_bank.json"
MINDSET_FIELDS = ("intent", "focus", "reset", "anchor", "context")


def _raw_bank() -> list[dict]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def _entry_style(entry: dict) -> str:
    return next(family for family in STYLE_FAMILIES if family in set(entry.get("tags") or []))


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "days_until_fight": 49,
        "plan_creation_weekday": "monday",
        "hard_sparring_days": [],
        "fatigue": "low",
        "fatigue_level": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": [],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
    }
    athlete.update(overrides)
    return athlete


def _week(phase: str, d_day: int) -> dict:
    return {
        "phase": phase,
        "session_roles": [
            {
                "role_key": "primary_strength_day",
                "category": "strength",
                "scheduled_day_hint": "Monday",
            }
        ],
        "calendar_days": [
            {"weekday": "monday", "d_day": d_day},
            {"weekday": "wednesday", "d_day": d_day - 2},
            {"weekday": "friday", "d_day": d_day - 4},
        ],
        "intentionally_unused_days": [
            {"day": "Wednesday", "role": "recovery_only_day"},
            {"day": "Friday", "role": "off_day"},
        ],
        "declared_training_days": ["Monday", "Wednesday", "Friday"],
    }


def _late_role(offset: int, role_key: str = "strength_touch_day") -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": role_key,
        "scheduled_day_hint": "monday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def _camp_watches(role_map: dict) -> list[dict]:
    return [
        role
        for week in role_map["weeks"]
        for role in week["session_roles"]
        if role.get("role_key") == "tactical_watch"
    ]


def _visible_fingerprint(role: dict) -> tuple:
    """The whole athlete-visible card, not just its title."""
    watch = role["tactical_watch"]
    return (
        watch["name"],
        watch["why"],
        *(watch["mindset"][field] for field in MINDSET_FIELDS),
        tuple(watch["instructions"]),
        watch["progress"],
    )


# --- the JSON bank is the source of truth: validate the file itself ----------


def test_bank_json_entries_are_structurally_complete():
    entries = _raw_bank()
    assert isinstance(entries, list) and entries

    keys: list[str] = []
    for entry in entries:
        key = entry.get("key")
        assert isinstance(key, str) and key.strip(), f"blank key: {entry!r}"
        keys.append(key)

        assert str(entry.get("name") or "").strip(), f"{key}: missing name"
        assert entry.get("phases") in ([phase] for phase in PHASES), (
            f"{key}: phases must be exactly one of {PHASES}, got {entry.get('phases')!r}"
        )

        tags = set(entry.get("tags") or [])
        assert "tactical_watch" in tags, f"{key}: missing tactical_watch tag"
        style_tags = tags & set(STYLE_FAMILIES)
        assert len(style_tags) == 1, f"{key}: needs exactly one style-family tag, got {style_tags}"

        expected_prefix = f"{_entry_style(entry)}.{entry['phases'][0].lower()}."
        assert key.startswith(expected_prefix), f"{key}: key must start with {expected_prefix!r}"

        mindset = entry.get("mindset")
        assert isinstance(mindset, dict), f"{key}: missing mindset"
        for field in MINDSET_FIELDS:
            assert str(mindset.get(field) or "").strip(), f"{key}: blank mindset.{field}"

        assert str(entry.get("why") or "").strip(), f"{key}: blank why"
        assert str(entry.get("progress") or "").strip(), f"{key}: blank progress"

        instructions = entry.get("instructions") or []
        assert len(instructions) >= 3, f"{key}: needs at least 3 instructions"
        assert all(str(line).strip() for line in instructions), f"{key}: blank instruction"

        assert int(entry.get("duration_min") or 0) > 0, f"{key}: missing duration_min"

    assert len(set(keys)) == len(keys), "duplicate Tactical Watch keys in the bank"


def test_bank_json_tasks_are_genuinely_different_not_renamed():
    """A renamed title must never pass for a new watch."""
    entries = _raw_bank()

    names = [entry["name"] for entry in entries]
    assert len(set(names)) == len(names), "duplicate Tactical Watch names"

    fingerprints = [
        (
            entry["name"],
            entry["why"],
            tuple(entry["mindset"][field] for field in MINDSET_FIELDS),
            tuple(entry["instructions"]),
            entry["progress"],
        )
        for entry in entries
    ]
    assert len(set(fingerprints)) == len(fingerprints), "duplicate athlete-visible fingerprints"

    # The actual task lives in the instructions: two watches that ask for the
    # same work are the same watch no matter what they are called.
    instruction_sets = [tuple(entry["instructions"]) for entry in entries]
    assert len(set(instruction_sets)) == len(instruction_sets), "duplicate instruction sets"

    for left, right in combinations(entries, 2):
        assert set(left["instructions"]) != set(right["instructions"]), (
            f"{left['key']} and {right['key']} ask for the same work"
        )
        assert left["why"] != right["why"], f"{left['key']} and {right['key']} share a Why"
        assert left["progress"] != right["progress"], (
            f"{left['key']} and {right['key']} share a Progress"
        )


def test_bank_covers_the_longest_supported_camp_for_every_style():
    """Selection raises when a bank runs dry, so the JSON must outlast any camp."""
    longest = {phase: 0 for phase in PHASES}
    for sport in sorted(next(iter(BASE_PHASE_RATIOS.values()))):
        for days in range(14, 400, 7):
            weeks = calculate_phase_weeks(days // 7, sport, days_until_fight=days)
            for phase in PHASES:
                longest[phase] = max(longest[phase], int(weeks.get(phase, 0) or 0))

    for style in STYLE_FAMILIES:
        for phase in PHASES:
            available = len(ordered_phase_bank(style, phase))
            assert available > longest[phase], (
                f"{style}/{phase} bank holds {available} watches but a camp can have "
                f"{longest[phase]} {phase} weeks — add JSON entries, not Python fallbacks"
            )


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (lambda e: e.update(key=""), "blank"),
        (lambda e: e.update(name=""), "identity"),
        (lambda e: e.update(phases=["OFFSEASON"]), "identity"),
        (lambda e: e.update(phases=["GPP", "SPP"]), "identity"),
        (lambda e: e.update(tags=["generic"]), "tactical_watch tag"),
        (lambda e: e["mindset"].pop("anchor"), "mindset"),
        (lambda e: e["mindset"].update(focus="  "), "mindset"),
        (lambda e: e.update(instructions=[]), "instructions"),
        (lambda e: e.update(why=""), "visible content"),
        (lambda e: e.update(progress=""), "visible content"),
    ],
)
def test_loader_rejects_a_malformed_bank_entry(tmp_path, monkeypatch, mutation, expected):
    entries = _raw_bank()[:1]
    mutation(entries[0])
    (tmp_path / "tactical_watch_bank.json").write_text(json.dumps(entries), encoding="utf-8")

    monkeypatch.setattr(library, "DATA_DIR", tmp_path)
    all_watches.cache_clear()
    try:
        with pytest.raises(ValueError, match=expected):
            all_watches()
    finally:
        all_watches.cache_clear()


def test_loader_rejects_duplicate_keys(tmp_path, monkeypatch):
    entries = _raw_bank()[:1] * 2
    (tmp_path / "tactical_watch_bank.json").write_text(json.dumps(entries), encoding="utf-8")

    monkeypatch.setattr(library, "DATA_DIR", tmp_path)
    all_watches.cache_clear()
    try:
        with pytest.raises(ValueError, match="duplicate"):
            all_watches()
    finally:
        all_watches.cache_clear()


# --- style normalisation -----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("out-boxer", "distance_striker"),
        ("distance striker", "distance_striker"),
        ("range fighter", "distance_striker"),
        ("long-range striker", "distance_striker"),
        ("outside fighter", "distance_striker"),
        ("brawler", "brawler"),
        ("pressure fighter", "brawler"),
        ("inside fighter", "brawler"),
        ("swarmer", "brawler"),
        ("volume pressure", "brawler"),
        ("counter striker", "counter_striker"),
        ("counter puncher", "counter_striker"),
        ("reactive counter fighter", "counter_striker"),
        ("wrestler", "generic"),
        ("", "generic"),
        (None, "generic"),
    ],
)
def test_style_normalization(raw, expected):
    assert normalize_tactical_style(raw) == expected


@pytest.mark.parametrize("sport", ["boxing", "mma", "muay thai", "kickboxing"])
def test_sport_never_implies_a_tactical_style(sport):
    assert extract_tactical_style({"sport": sport}) == "generic"


def test_declared_tactical_style_wins_over_sport():
    assert extract_tactical_style({"sport": "boxing", "tactical_styles": ["swarmer"]}) == "brawler"


# --- selection ---------------------------------------------------------------


@pytest.mark.parametrize(
    "style, expected",
    [
        ("distance_striker", ("Range Map", "Intercept the Entry", "First-Round Range Script")),
        ("brawler", ("Pressure Route Scan", "Pocket Exchange Map", "First-Round Pressure Script")),
        ("counter_striker", ("Trigger Library", "First Beat or Second Beat", "First-Round Patience Script")),
        ("generic", ("Opponent Pattern Scan", "Trigger-Response Builder", "Familiar Round-One Rehearsal")),
    ],
)
def test_first_watch_is_style_and_phase_specific(style, expected):
    assert tuple(select_tactical_watch(style, phase).name for phase in PHASES) == expected


@pytest.mark.parametrize("style", [family for family in STYLE_FAMILIES if family != "generic"])
@pytest.mark.parametrize("phase", PHASES)
def test_style_watches_come_before_the_generic_fallback(style, phase):
    bank = ordered_phase_bank(style, phase)
    styles = [watch.style for watch in bank]
    assert set(styles) == {style, "generic"}
    assert styles == sorted(styles, key=lambda value: value == "generic")


@pytest.mark.parametrize("phase", PHASES)
def test_a_phase_bank_never_borrows_another_phase(phase):
    for style in STYLE_FAMILIES:
        assert {watch.phase for watch in ordered_phase_bank(style, phase)} == {phase}


def test_bank_never_silently_repeats_after_exhaustion():
    for style in STYLE_FAMILIES:
        for phase in PHASES:
            used: set[str] = set()
            bank = ordered_phase_bank(style, phase)
            for _ in bank:
                watch = select_tactical_watch(style, phase, used)
                assert watch.key not in used
                used.add(watch.key)
            with pytest.raises(TacticalWatchBankExhausted):
                select_tactical_watch(style, phase, used)


def test_every_bank_entry_has_unique_athlete_visible_content():
    watches = all_watches()
    assert len({watch.key for watch in watches}) == len(watches)
    assert len({canonical_watch_signature(watch) for watch in watches}) == len(watches)
    assert len({watch.instructions for watch in watches}) == len(watches)


# --- mandatory weekly placement (normal fight-dated camp) --------------------


def _fight_camp_role_map() -> dict:
    return {
        "weeks": [
            _week("GPP", 49),
            _week("GPP", 42),
            _week("GPP", 35),
            _week("SPP", 28),
            _week("SPP", 21),
            _week("SPP", 14),
            _week("TAPER", 7),
        ]
    }


def test_normal_fight_camp_gets_one_named_watch_every_week():
    role_map = _fight_camp_role_map()
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["out-boxer"]))

    for week in role_map["weeks"]:
        watches = [
            role for role in week["session_roles"] if role.get("role_key") == "tactical_watch"
        ]
        assert len(watches) == 1, f"{week['phase']} week has {len(watches)} Tactical Watches"

    watches = _camp_watches(role_map)
    assert [watch["tactical_watch_name"] for watch in watches] == [
        "Range Map",
        "Lead-Hand Battle",
        "Exit Discipline",
        "Intercept the Entry",
        "Exit Lane Audit",
        "Rope and Corner Escape",
        "First-Round Range Script",
    ]
    assert all(watch["mandatory_tactical_watch"] is True for watch in watches)
    assert all(watch["weekly_requirement"] == "fight_tactical_watch" for watch in watches)
    assert all(watch["athlete_facing_label"] == "Fight Tactical Watch" for watch in watches)


def test_consecutive_weeks_change_the_whole_visible_card_not_just_the_title():
    role_map = _fight_camp_role_map()
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["out-boxer"]))
    watches = _camp_watches(role_map)

    fingerprints = [_visible_fingerprint(watch) for watch in watches]
    assert len(set(fingerprints)) == len(fingerprints)
    assert len({watch["tactical_watch_key"] for watch in watches}) == len(watches)
    assert len({watch["display_text"] for watch in watches}) == len(watches)

    for left, right in combinations(watches, 2):
        left_watch, right_watch = left["tactical_watch"], right["tactical_watch"]
        assert left_watch["instructions"] != right_watch["instructions"]
        assert left_watch["why"] != right_watch["why"]
        assert left_watch["progress"] != right_watch["progress"]
        for field in MINDSET_FIELDS:
            assert left_watch["mindset"][field] != right_watch["mindset"][field], (
                f"{left_watch['name']} and {right_watch['name']} share mindset.{field}"
            )


@pytest.mark.parametrize(
    "style, expected",
    [
        ("out-boxer", ("Range Map", "Intercept the Entry", "First-Round Range Script")),
        ("pressure fighter", ("Pressure Route Scan", "Pocket Exchange Map", "First-Round Pressure Script")),
        ("counter puncher", ("Trigger Library", "First Beat or Second Beat", "First-Round Patience Script")),
        (None, ("Opponent Pattern Scan", "Trigger-Response Builder", "Familiar Round-One Rehearsal")),
    ],
)
def test_each_style_family_gets_its_own_first_watch_per_phase(style, expected):
    role_map = {"weeks": [_week("GPP", 35), _week("SPP", 21), _week("TAPER", 7)]}
    athlete = _athlete() if style is None else _athlete(tactical_styles=[style])
    apply_camp_week_fillers(role_map, athlete)
    assert tuple(watch["tactical_watch_name"] for watch in _camp_watches(role_map)) == expected


def test_taper_never_uses_gpp_analysis_and_gpp_never_uses_taper_compression():
    role_map = _fight_camp_role_map()
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["counter puncher"]))
    for week in role_map["weeks"]:
        watch = next(
            role for role in week["session_roles"] if role.get("role_key") == "tactical_watch"
        )
        assert watch["tactical_watch_phase"] == week["phase"]


def test_compressed_fight_week_keeps_zero_load_tactical_watch():
    week = _week("SPP", 21)
    week["intentional_compression"] = {"active": True, "reason": "high fatigue"}
    role_map = {"weeks": [week]}
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["counter puncher"], fatigue="high"))
    watches = [role for role in week["session_roles"] if role.get("role_key") == "tactical_watch"]
    assert len(watches) == 1
    assert watches[0]["tactical_watch_name"] == "First Beat or Second Beat"
    assert watches[0]["governance"]["meaningful_stress"] is False
    assert watches[0]["stress_class"] == "support"
    # Compression still blocks every non-watch filler.
    assert not [
        role
        for role in week["session_roles"]
        if role.get("camp_week_filler") and role.get("role_key") != "tactical_watch"
    ]


def test_support_caps_hold_per_phase():
    role_map = {"weeks": [_week("GPP", 35), _week("SPP", 21), _week("TAPER", 7)]}
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["out-boxer"]))
    caps = {"GPP": 1, "SPP": 2, "TAPER": 1}
    for week in role_map["weeks"]:
        fillers = [role for role in week["session_roles"] if role.get("camp_week_filler")]
        assert len(fillers) <= caps[week["phase"]]


def test_mandatory_watch_shares_a_scheduled_day_and_never_takes_a_rest_day():
    role_map = _fight_camp_role_map()
    unused_before = {
        id(week): {
            str(entry["day"]).strip().lower()
            for entry in week["intentionally_unused_days"]
        }
        for week in role_map["weeks"]
    }
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["out-boxer"]))

    for week in role_map["weeks"]:
        watch = next(
            role for role in week["session_roles"] if role.get("role_key") == "tactical_watch"
        )
        day = str(watch["scheduled_day_hint"]).strip().lower()
        assert day not in unused_before[id(week)], "watch converted an off/recovery-only day"
        assert any(
            not role.get("camp_week_filler")
            and str(role.get("scheduled_day_hint") or "").strip().lower() == day
            for role in week["session_roles"]
        ), "watch created a new training day instead of sharing one"


def test_d0_is_never_used_for_mandatory_normal_camp_watch():
    week = {
        "phase": "TAPER",
        "session_roles": [
            {
                "role_key": "fight_day",
                "category": "fight",
                "scheduled_day_hint": "Friday",
            }
        ],
        "calendar_days": [{"weekday": "friday", "d_day": 0}],
        "intentionally_unused_days": [],
        "declared_training_days": ["Friday"],
    }
    role_map = {"weeks": [week]}
    apply_camp_week_fillers(role_map, _athlete(days_until_fight=1))
    assert not any(role.get("role_key") == "tactical_watch" for role in week["session_roles"])


def test_plans_without_a_fight_date_gain_no_mandatory_watch():
    role_map = {"weeks": [_week("GPP", 35), _week("SPP", 21), _week("TAPER", 7)]}
    apply_camp_week_fillers(role_map, _athlete(days_until_fight=None))

    # No fight date -> nothing is mandatory, and GPP keeps its legacy no-filler
    # behaviour. A tactical_watch may still turn up as an ordinary adaptive
    # filler in SPP/TAPER, exactly as it did before this feature.
    assert not any(role.get("mandatory_tactical_watch") for role in _camp_watches(role_map))
    gpp_week = role_map["weeks"][0]
    assert not [role for role in gpp_week["session_roles"] if role.get("camp_week_filler")]
    assert any(
        role.get("camp_week_filler")
        for week in role_map["weeks"][1:]
        for role in week["session_roles"]
    )


def test_selected_drill_identity_survives_finalizer_compaction():
    role_map = {"weeks": [_week("SPP", 28)]}
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["out-boxer"]))
    role = next(
        role
        for role in role_map["weeks"][0]["session_roles"]
        if role.get("role_key") == "tactical_watch"
    )
    compact = _compact_role(role)
    assert compact["role_key"] == "tactical_watch"
    assert compact["athlete_facing_label"] == "Fight Tactical Watch"
    assert compact["preferred_exercise_names"] == ["Intercept the Entry"]
    # Outer shell first, then the selected watch as the inner activity card.
    lines = compact["display_text"].splitlines()
    assert lines[0] == "Fight Tactical Watch"
    assert lines[1].startswith("Why: ")
    assert "Intercept the Entry" in lines
    assert lines.index("Intercept the Entry") > lines.index("Mindset:")
    assert any(line.startswith("Duration: ") for line in lines)
    assert any(line.startswith("Progress: ") for line in lines)
    assert compact["mandatory_tactical_watch"] is True
    assert compact["governance"]["selected_drill_locked"] is True
    assert compact["governance"]["selected_drill_name"] == "Intercept the Entry"
    assert compact["governance"]["render_selected_drill_exactly"] is True
    assert compact["governance"]["do_not_reselect_or_generalize"] is True
    for instruction in role["tactical_watch"]["instructions"]:
        assert instruction in compact["display_text"]


# --- end to end through the real Stage 1 planning brief ----------------------

_E2E_PHASE_BRIEF = {
    "objective": "build the phase",
    "emphasize": [],
    "deprioritize": [],
    "risk_flags": [],
    "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
    "selection_guardrails": {},
}
_E2E_POOL = {
    "strength_slots": [
        {"role": "primary_strength", "selected": {"name": "Trap Bar Deadlift"}, "alternates": []}
    ],
    "conditioning_slots": [{"role": "aerobic", "selected": {"name": "Tempo Run"}, "alternates": []}],
    "rehab_slots": [],
}


def _real_camp_brief(style: str | None, days: int) -> dict:
    """Build a planning brief the way the live pipeline does.

    Uses the real week builder (and therefore the real ``calendar_days`` spine)
    instead of a hand-written week, so a Tactical Watch that only works against
    synthetic fixtures cannot pass.
    """
    athlete = _athlete(days_until_fight=days, camp_length_weeks=days // 7)
    athlete.update(
        status="amateur",
        rounds_format="3x3",
        training_preference="balanced",
        training_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        key_goals=["conditioning"],
        weaknesses=["gas_tank"],
        equipment=["bodyweight", "bands"],
    )
    if style is not None:
        athlete["tactical_styles"] = [style]

    weeks = calculate_phase_weeks(days // 7, "boxing", days_until_fight=days)
    phase_briefs = {
        phase: {**_E2E_PHASE_BRIEF, "weeks": weeks[phase], "days": weeks["days"][phase]}
        for phase in PHASES
        if weeks.get(phase)
    }
    return build_planning_brief(
        athlete_model=athlete,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools={phase: _E2E_POOL for phase in phase_briefs},
        omission_ledger={},
        rewrite_guidance={},
    )


@pytest.mark.parametrize("style", ["out-boxer", "pressure fighter", "counter puncher", None])
@pytest.mark.parametrize("days", [84, 112])
def test_real_fight_dated_camp_carries_one_unrepeated_watch_every_week(style, days):
    role_map = _real_camp_brief(style, days)["weekly_role_map"]
    weeks = [week for week in role_map["weeks"] if week.get("phase") in PHASES]
    assert weeks

    keys: list[str] = []
    fingerprints: list[tuple] = []
    for week in weeks:
        watches = [
            role for role in week["session_roles"] if role.get("role_key") == "tactical_watch"
        ]
        assert len(watches) == 1, (
            f"week {week.get('week_index')} ({week.get('phase')}) has {len(watches)} watches"
        )
        watch = watches[0]
        assert watch["tactical_watch_phase"] == week["phase"]
        keys.append(watch["tactical_watch_key"])
        fingerprints.append(_visible_fingerprint(watch))

        day = str(watch["scheduled_day_hint"]).strip().lower()
        d_days = {
            str(entry["weekday"]).strip().lower(): entry["d_day"]
            for entry in week["calendar_days"]
        }
        assert d_days.get(day, 0) > 0, "mandatory watch landed on D-0 or an unmapped day"
        assert any(
            not role.get("camp_week_filler")
            and str(role.get("scheduled_day_hint") or "").strip().lower() == day
            for role in week["session_roles"]
        ), "mandatory watch created its own training day"

    assert len(set(keys)) == len(keys), "a Tactical Watch key repeated inside one camp"
    assert len(set(fingerprints)) == len(fingerprints), "two weeks shared a visible card"


# --- late-fight countdown path ----------------------------------------------


def test_late_fight_tactical_watch_inserts_come_from_the_bank_and_never_repeat():
    sequence = apply_gap_fill_inserts(
        [_late_role(21), _late_role(16), _late_role(11), _late_role(6), _late_role(1)],
        _athlete(days_until_fight=21, tactical_styles=["pressure fighter"]),
    )
    watches = [role for role in sequence if role.get("role_key") == "tactical_watch"]
    assert watches, "late-fight sequence lost its tactical support"
    assert all(role["tactical_watch_style"] == "brawler" for role in watches)
    assert all(role["preferred_exercise_names"] == [role["tactical_watch_name"]] for role in watches)
    assert all(
        role["tactical_watch_name"] in role["display_text"] for role in watches
    )
    keys = [role["tactical_watch_key"] for role in watches]
    assert len(set(keys)) == len(keys), "a Tactical Watch key repeated inside one plan"



def test_late_fight_watch_is_never_scheduled_on_fight_day():
    sequence = apply_gap_fill_inserts(
        [_late_role(14), _late_role(9), _late_role(4)],
        _athlete(days_until_fight=14, tactical_styles=["out-boxer"]),
    )
    assert all(
        int(role["countdown_offset"]) > 0
        for role in sequence
        if role.get("role_key") == "tactical_watch"
    )
