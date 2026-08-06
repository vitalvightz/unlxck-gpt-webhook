from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).with_name("fix_pr_2221.py")
spec = importlib.util.spec_from_file_location("fix_pr_2221", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load PR 2221 repair module")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def sequence(indent: int, expression: str, roles: list[str]) -> str:
    prefix = " " * indent
    item_prefix = " " * (indent + 4)
    lines = [f"{prefix}{expression} == ["]
    lines.extend(f'{item_prefix}"{role}",' for role in roles)
    lines.append(f"{prefix}]")
    return "\n".join(lines)


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    text = repair.read(path)
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    repair.write(path, text[:start_index] + replacement.rstrip() + "\n\n" + text[end_index:])


def patch_existing_contract_tests() -> None:
    modes = "tests/test_stage2_payload_modes.py"
    repair.replace_once(
        modes,
        sequence(
            8,
            'assert [entry["role_key"] for entry in app_sequence]',
            ["fight_week_freshness_day", "tactical_cue_card"],
        ),
        sequence(
            8,
            'assert [entry["role_key"] for entry in app_sequence]',
            ["fight_week_freshness_day", "tactical_watch"],
        ),
    )
    repair.replace_once(
        modes,
        '        assert [entry["role_key"] for entry in app_sequence] == ["tactical_cue_card"]',
        '        assert [entry["role_key"] for entry in app_sequence] == ["tactical_watch"]',
    )
    repair.replace_once(
        modes,
        sequence(
            8,
            'assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]]',
            ["fight_week_freshness_day", "neural_primer_day"],
        ),
        sequence(
            8,
            'assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]]',
            ["fight_week_freshness_day", "tactical_watch", "neural_primer_day"],
        ),
    )
    repair.replace_once(
        modes,
        sequence(
            8,
            'assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]]',
            ["neural_primer_day"],
        ),
        sequence(
            8,
            'assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]]',
            ["neural_primer_day", "tactical_watch"],
        ),
    )

    brief = "tests/test_stage2_planning_brief.py"
    repair.replace_once(
        brief,
        sequence(
            4,
            "assert roles_from_seq",
            ["tactical_cue_card", "fight_week_freshness_day", "neural_primer_day"],
        ),
        sequence(
            4,
            "assert roles_from_seq",
            ["tactical_watch", "fight_week_freshness_day", "neural_primer_day"],
        ),
    )
    repair.replace_once(
        brief,
        "\n".join(
            [
                "    support_entries = [",
                "        entry",
                '        for entry in brief["late_fight_session_sequence"]',
                '        if entry["role_key"] == "tactical_cue_card"',
                "    ]",
            ]
        ),
        "\n".join(
            [
                "    support_entries = [",
                "        entry",
                '        for entry in brief["late_fight_session_sequence"]',
                '        if entry["role_key"] == "tactical_watch"',
                "    ]",
            ]
        ),
    )
    repair.replace_once(
        brief,
        sequence(
            4,
            'assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]]',
            ["fight_week_freshness_day", "neural_primer_day"],
        ),
        sequence(
            4,
            'assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]]',
            ["fight_week_freshness_day", "tactical_watch", "neural_primer_day"],
        ),
    )


repair.patch_existing_contract_tests = patch_existing_contract_tests
repair.main()


# Normal-camp guarantee only applies once Stage 2 has produced a renderable
# countdown calendar. Direct unit fixtures often exercise the role-map builder
# with days_until_fight present but intentionally omit calendar_days; those are
# not complete athlete-facing weeks and must not be treated as impossible plans.
camp_path = "fightcamp/camp_week_fillers.py"
camp_calendar_guard = '''def _has_renderable_countdown_day(week: dict[str, Any]) -> bool:
    for entry in week.get("calendar_days") or []:
        if not isinstance(entry, dict):
            continue
        if not _canonical_day(entry.get("weekday")):
            continue
        try:
            if int(entry.get("d_day")) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False
'''
camp_text = repair.read(camp_path)
camp_marker = "def _ensure_weekly_tactical_watch("
camp_index = camp_text.index(camp_marker)
camp_text = camp_text[:camp_index] + camp_calendar_guard + "\n\n" + camp_text[camp_index:]
camp_text = camp_text.replace(
    '''        if has_future_fight:
            cap = _PHASE_FILLER_CAPS.get(phase)
            if not cap:
                continue
            _ensure_weekly_tactical_watch(week, athlete_model, usage_ledger, cap)
''',
    '''        if has_future_fight:
            cap = _PHASE_FILLER_CAPS.get(phase)
            if not cap:
                continue
            if not _has_renderable_countdown_day(week):
                continue
            _ensure_weekly_tactical_watch(week, athlete_model, usage_ledger, cap)
''',
    1,
)
repair.write(camp_path, camp_text)


# A mandatory zero-cost Watch should share the least costly existing day when a
# segment has no genuinely spaced empty day. This prevents D-15 beside D-16 and
# avoids inventing extra D-2/D-3 micro-taper days merely to satisfy the rule.
gap_path = "fightcamp/gap_fill_inserts.py"
segment_offset = '''def _segment_watch_offset(
    sequence: list[dict[str, Any]],
    *,
    segment: int,
    days_until_fight: int,
) -> int | None:
    lower, upper = _watch_segment_bounds(segment, days_until_fight)
    if lower > upper:
        return None

    target = _watch_target_offset(segment, days_until_fight)
    roles_by_offset: dict[int, list[dict[str, Any]]] = {}
    for role in sequence:
        offset = _role_offset(role)
        if offset is not None and offset > 0:
            roles_by_offset.setdefault(offset, []).append(role)

    offsets = list(range(lower, upper + 1))
    fully_spaced = [
        offset
        for offset in offsets
        if offset not in roles_by_offset
        and all(abs(existing - offset) > 1 for existing in roles_by_offset)
    ]
    if fully_spaced:
        return min(fully_spaced, key=lambda offset: (abs(offset - target), -offset))

    occupied = [offset for offset in offsets if offset in roles_by_offset]
    if occupied:
        def shared_day_priority(offset: int) -> tuple[int, int, int, int]:
            roles = roles_by_offset[offset]
            categories = {
                str(role.get("category") or "").strip().lower()
                for role in roles
            }
            role_keys = {
                str(role.get("role_key") or "").strip().lower()
                for role in roles
            }
            if categories & {"support_insert", "recovery", "technical"}:
                load_priority = 0
            elif "hard_sparring_day" in role_keys or "sparring" in categories:
                load_priority = 1
            else:
                load_priority = 2
            return (load_priority, len(roles), abs(offset - target), -offset)

        return min(occupied, key=shared_day_priority)

    role_counts = {offset: len(roles) for offset, roles in roles_by_offset.items()}
    return min(
        offsets,
        key=lambda offset: (
            sum(count for existing, count in role_counts.items() if abs(existing - offset) == 1),
            sum(count for existing, count in role_counts.items() if abs(existing - offset) == 2),
            abs(offset - target),
            -offset,
        ),
        default=None,
    )
'''
replace_between(
    gap_path,
    "def _segment_watch_offset(",
    "def _mandatory_watch_guidance(",
    segment_offset,
)


# Weekly mandatory Watches are the deliberate exception to the old generic
# no-repeat filler rule. They may repeat across distinct seven-day segments.
gap_tests = "tests/test_gap_fill_inserts.py"
repeat_test = '''def test_exact_same_role_key_does_not_repeat_within_seven_days():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6, "fight_week_freshness_day")],
        _athlete(days_until_fight=21),
    )

    inserts = _insert_roles(sequence)
    for index, insert in enumerate(inserts):
        for other in inserts[index + 1 :]:
            if abs(insert["countdown_offset"] - other["countdown_offset"]) > 7:
                continue
            if insert["role_key"] != other["role_key"]:
                continue
            assert insert["role_key"] == "tactical_watch"
            assert insert.get("mandatory_tactical_watch") is True
            assert other.get("mandatory_tactical_watch") is True
            assert insert.get("tactical_watch_segment") != other.get("tactical_watch_segment")
'''
replace_between(
    gap_tests,
    "def test_exact_same_role_key_does_not_repeat_within_seven_days():",
    "def test_tactical_category_can_repeat_with_different_role_key():",
    repeat_test,
)

existing_watch_test = '''def test_gap_fill_existing_low_cost_insert_does_not_occupy_declared_day():
    sequence = apply_gap_fill_inserts(
        [_support_insert_session(1, "tactical_watch", "tuesday")],
        _athlete(
            days_until_fight=1,
            plan_creation_weekday="tuesday",
            hard_sparring_days=["tuesday"],
        ),
    )

    d1_roles = [role for role in sequence if role.get("countdown_offset") == 1]
    support_roles = [role for role in d1_roles if role.get("category") == "support_insert"]
    assert len(support_roles) == 1
    assert support_roles[0]["role_key"] == "tactical_watch"
    assert support_roles[0]["mandatory_tactical_watch"] is True
    assert support_roles[0]["governance"]["authority"] == "gap_fill_support_insert"
    assert all(role["role_key"] not in PHYSICAL_INSERTS for role in d1_roles)
'''
replace_between(
    gap_tests,
    "def test_gap_fill_existing_low_cost_insert_does_not_occupy_declared_day():",
    "def test_apply_gap_fill_inserts_is_wired_into_live_stage2_payload_path",
    existing_watch_test,
)


# The D-16 rule protects meaningful training-day spacing. A mandatory zero-cost
# Watch may coexist on an already scheduled day, but must not create a new
# adjacent day in the countdown.
modes_path = "tests/test_stage2_payload_modes.py"
d16_test = '''    def test_bridge_d16_practical_spacing_avoids_adjacent_app_owned_sessions(self):
        brief = _build_brief_for(
            16,
            athlete_overrides={
                "plan_creation_weekday": "monday",
                "hard_sparring_days": [],
            },
        )
        visible_sequence = brief["late_fight_plan_spec"]["visible_session_sequence"]
        non_watch_offsets = [
            entry["countdown_offset"]
            for entry in visible_sequence
            if isinstance(entry.get("countdown_offset"), int)
            and not entry.get("mandatory_tactical_watch")
        ]
        watch_offsets = [
            entry["countdown_offset"]
            for entry in visible_sequence
            if entry.get("mandatory_tactical_watch")
        ]

        assert all(
            first - second > 1
            for first, second in zip(non_watch_offsets, non_watch_offsets[1:])
        )
        assert watch_offsets
        assert all(offset in non_watch_offsets for offset in watch_offsets)
'''
replace_between(
    modes_path,
    "    def test_bridge_d16_practical_spacing_avoids_adjacent_app_owned_sessions(self):",
    "    def test_bridge_d16_avoids_meaningful_app_owned_work_on_declared_hard_days(self):",
    d16_test,
)


# Lock in the no-new-day fallback for the outer D-15..D-16 segment.
mandatory_path = "tests/test_mandatory_weekly_tactical_watch.py"
mandatory_text = repair.read(mandatory_path)
mandatory_text += '''\n\ndef test_late_fight_watch_shares_existing_day_when_no_spaced_day_exists():
    sequence = apply_gap_fill_inserts(
        [_session(16), _session(14), _session(9), _session(4)],
        _athlete(days_until_fight=16),
    )
    outer_watch = next(
        role
        for role in sequence
        if role.get("mandatory_tactical_watch")
        and role.get("tactical_watch_segment") == 2
    )
    assert outer_watch["countdown_offset"] == 16
    assert not any(
        role.get("mandatory_tactical_watch") and role.get("countdown_offset") == 15
        for role in sequence
    )
'''
repair.write(mandatory_path, mandatory_text)
