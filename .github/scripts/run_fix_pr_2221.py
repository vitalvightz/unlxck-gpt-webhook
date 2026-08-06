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
