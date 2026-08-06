from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"Expected exactly one {label} block in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


gap_path = Path("fightcamp/gap_fill_inserts.py")
replace_once(
    gap_path,
    """        existing_watches = _segment_watch_roles(combined, segment)
        if existing_watches:
            _promote_mandatory_tactical_watch(
                existing_watches[0], athlete_model, countdown_map
            )
            continue
""",
    """        existing_watches = _segment_watch_roles(combined, segment)
        if existing_watches:
            keeper = existing_watches[0]
            _promote_mandatory_tactical_watch(keeper, athlete_model, countdown_map)
            for duplicate in existing_watches[1:]:
                duplicate["suppressed"] = True
                duplicate["reasons"] = list(
                    dict.fromkeys(
                        [
                            *clean_list(duplicate.get("reasons")),
                            (
                                "Only one Tactical Watch is allowed per seven-day "
                                "fight segment."
                            ),
                        ]
                    )
                )
                duplicate["reason_codes"] = list(
                    dict.fromkeys(
                        [
                            *clean_list(duplicate.get("reason_codes")),
                            "duplicate_weekly_tactical_watch",
                        ]
                    )
                )
                ordered[:] = [role for role in ordered if role is not duplicate]
                inserts[:] = [role for role in inserts if role is not duplicate]
            combined = ordered + inserts
            continue
""",
    "late-fight existing-watch promotion",
)

camp_path = Path("fightcamp/camp_week_fillers.py")
replace_once(
    camp_path,
    """            if not _has_renderable_countdown_day(week):
                continue
""",
    """            if not _has_renderable_countdown_day(week):
                raise RuntimeError(
                    "Fight-dated GPP/SPP/TAPER week has no positive countdown calendar day"
                )
""",
    "malformed fight-week calendar guard",
)

test_path = Path("tests/test_mandatory_weekly_tactical_watch.py")
test_text = test_path.read_text(encoding="utf-8")
if "import pytest\n" not in test_text:
    test_text = test_text.replace(
        "from __future__ import annotations\n\n",
        "from __future__ import annotations\n\nimport pytest\n\n",
        1,
    )

marker = "def test_duplicate_existing_late_fight_watches_are_suppressed_to_one():"
if marker not in test_text:
    test_text += """


def test_duplicate_existing_late_fight_watches_are_suppressed_to_one():
    first = {
        **_session(6, "tactical_watch"),
        "category": "support_insert",
        "stress_class": "support",
        "governance": {"meaningful_stress": False},
    }
    duplicate = {
        **_session(4, "tactical_watch"),
        "category": "support_insert",
        "stress_class": "support",
        "governance": {"meaningful_stress": False},
    }

    sequence = apply_gap_fill_inserts(
        [first, duplicate],
        _athlete(days_until_fight=7),
    )

    watches = _watches(sequence)
    assert len(watches) == 1
    assert watches[0]["mandatory_tactical_watch"] is True
    assert watches[0]["weekly_requirement"] == "fight_tactical_watch"
    assert watches[0]["governance"]["authority"] == "gap_fill_support_insert"


def test_malformed_fight_dated_normal_week_raises_generation_error():
    week = _week("SPP", 0)
    week["calendar_days"] = [
        {"weekday": "monday", "d_day": 0},
        {"weekday": "wednesday", "d_day": -2},
    ]

    with pytest.raises(RuntimeError, match="no positive countdown calendar day"):
        apply_camp_week_fillers(
            {"weeks": [week]},
            _athlete(days_until_fight=28),
        )
"""

test_path.write_text(test_text, encoding="utf-8")

legacy_test_path = Path("tests/test_gap_fill_inserts.py")
replace_once(
    legacy_test_path,
    """def test_exact_same_role_key_does_not_repeat_within_seven_days():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6, "fight_week_freshness_day")],
        _athlete(days_until_fight=21),
    )

    inserts = _insert_roles(sequence)
    for index, insert in enumerate(inserts):
        for other in inserts[index + 1 :]:
            if abs(insert["countdown_offset"] - other["countdown_offset"]) <= 7:
                assert insert["role_key"] != other["role_key"]
""",
    """def test_only_mandatory_watch_may_repeat_within_seven_days():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6, "fight_week_freshness_day")],
        _athlete(days_until_fight=21),
    )

    inserts = _insert_roles(sequence)
    for index, insert in enumerate(inserts):
        for other in inserts[index + 1 :]:
            if (
                abs(insert["countdown_offset"] - other["countdown_offset"]) <= 7
                and insert["role_key"] == other["role_key"]
            ):
                assert insert["role_key"] == "tactical_watch"
                assert insert.get("mandatory_tactical_watch") is True
                assert other.get("mandatory_tactical_watch") is True
""",
    "exact-role repetition regression",
)
replace_once(
    legacy_test_path,
    """def test_gap_fill_existing_low_cost_insert_does_not_occupy_declared_day():
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
    assert len(support_roles) >= 2
    assert all(role["role_key"] not in PHYSICAL_INSERTS for role in d1_roles)
""",
    """def test_existing_d1_tactical_watch_is_promoted_without_extra_support():
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
    assert all(role["role_key"] not in PHYSICAL_INSERTS for role in d1_roles)
""",
    "D-1 existing Watch regression",
)
