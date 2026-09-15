"""The production Week 1 regression: five Stage 1 roles, four rendered.

Stage 1's Week 1 (SPP, D-14 to D-8) held five roles. Stage 2 rendered four — the
D-14 Recovery Reset disappeared — the validator correctly reported
``late_camp_session_incomplete`` (expected 5, actual 4), and deterministic source
repair still could not restore it, reporting "Canonical week is not rendered"
against a plan whose week headers were the contract-valid plain form
``SPP — Week 1 (D-14 to D-8) — Objective``.

Both halves are covered here: the first-pass locked render projection must carry
every deterministic role, and repair must be able to put one back under either
header style.
"""

import copy

import pytest

from fightcamp.combat_render_authority import (
    CANONICAL_HARD_SPARRING_BAN_LABEL,
    CANONICAL_HARD_SPARRING_NOTE,
    CANONICAL_TECHNICAL_ONLY_NOTE,
)
from fightcamp.gap_fill_inserts import _INSERT_META
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import _closed_membership_render_manifest
from fightcamp.stage2_pipeline import repair_stage2_structural_text
from fightcamp.tactical_watch_library import (
    build_watch_display_text,
    select_tactical_watch,
    watch_metadata,
)


def _support_insert_role(role_key, *, day, d_day, label=None):
    meta = _INSERT_META[role_key]
    return {
        "category": "support_insert",
        "role_key": role_key,
        "athlete_facing_label": label or meta["label"],
        "display_text": meta["display_text"],
        "duration_min": list(meta["duration_min"]),
        "rpe_max": int(meta["rpe_max"]),
        "scheduled_day_hint": day,
        "real_weekday": day,
        "countdown_offset": d_day,
        "countdown_label": f"D-{d_day}",
        "scheduled_countdown_label": f"D-{d_day}",
        "countdown_display_label": f"D-{d_day} ({day.title()})",
        "stress_class": "support",
        "cost_class": "low",
        "governance": {
            "authority": "gap_fill_support_insert",
            "meaningful_stress": False,
        },
    }


def _tactical_watch_role():
    watch = select_tactical_watch("pressure", "SPP", set())
    metadata = watch_metadata(watch)
    governance = dict(metadata.pop("governance"))
    role = {
        "category": "support_insert",
        "role_key": "tactical_watch",
        "athlete_facing_label": "Tactical Focus",
        "scheduled_day_hint": "sunday",
        "real_weekday": "sunday",
        "countdown_offset": 11,
        "countdown_label": "D-11",
        "scheduled_countdown_label": "D-11",
        "countdown_display_label": "D-11 (Sunday)",
        "support_insert_category": "tactical",
        "support_insert_cost_category": "zero_cost",
        "mandatory_tactical_watch": True,
        "camp_week_filler": True,
        "stress_class": "support",
        "cost_class": "low",
        **metadata,
        "display_text": build_watch_display_text(watch),
        "governance": {**governance, "meaningful_stress": False},
    }
    return role, watch


def _week_one_planning_brief():
    watch_role, watch = _tactical_watch_role()
    return {
        "athlete_snapshot": {"sport": "boxing", "days_until_fight": 14},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "calendar_days": [
                        {"weekday": "thursday", "d_day": 14},
                        {"weekday": "saturday", "d_day": 12},
                        {"weekday": "sunday", "d_day": 11},
                        {"weekday": "tuesday", "d_day": 9},
                    ],
                    "session_roles": [
                        _support_insert_role("recovery_reset", day="thursday", d_day=14),
                        {
                            "category": "strength",
                            "role_key": "strength_touch_day",
                            "athlete_facing_label": "Strength touch",
                            "scheduled_day_hint": "saturday",
                            "scheduled_countdown_label": "D-12",
                            "selected_exercise_assignments": [
                                {
                                    "slot_id": "strength-1",
                                    "name": "Trap Bar Deadlift",
                                    "effective_prescription": "3 x 3; RPE 6-7",
                                }
                            ],
                        },
                        {
                            "category": "sparring",
                            "role_key": "hard_sparring_day",
                            "coach_owned": True,
                            "scheduled_day_hint": "sunday",
                            "scheduled_countdown_label": "D-11",
                            "hard_sparring_status": "hard_as_planned",
                            "hard_sparring_class": "primary_hard",
                            "hard_sparring_reason_codes": [],
                        },
                        watch_role,
                        _support_insert_role("breathing_reset", day="tuesday", d_day=9),
                    ],
                }
            ]
        },
    }, watch


def _finalizer_packet(planning_brief):
    return build_stage2_finalizer_packet(
        stage2_payload={
            "athlete_model": {"sport": "boxing"},
            "render_mode": "camp_plan",
            "rewrite_guidance": {"render_guards": {"render_mode": "camp_plan"}},
            "weekly_role_map": copy.deepcopy(planning_brief["weekly_role_map"]),
        },
        planning_brief=planning_brief,
    )


def test_first_pass_projection_carries_every_deterministic_week_one_role():
    planning_brief, watch = _week_one_planning_brief()
    packet = _finalizer_packet(planning_brief)

    manifest = _closed_membership_render_manifest(packet, planning_brief=planning_brief)
    by_role = {entry["role_key"]: entry for entry in manifest}

    # All five Stage 1 roles reach the first pass — not just the one with
    # selected_exercise_assignments.
    assert set(by_role) == {
        "recovery_reset",
        "strength_touch_day",
        "hard_sparring_day",
        "tactical_watch",
        "breathing_reset",
    }

    # 2 + 3. A support insert cannot disappear for lacking closed membership.
    for role_key in ("recovery_reset", "breathing_reset"):
        entry = by_role[role_key]
        assert entry["authority"] == "deterministic_display_text"
        assert entry["exact_body_lines"] == [_INSERT_META[role_key]["display_text"]]
        assert entry["athlete_facing_label"] == _INSERT_META[role_key]["label"]
    assert by_role["recovery_reset"]["scheduled_countdown_label"] == "D-14"
    assert by_role["recovery_reset"]["phase"] == "SPP"
    assert by_role["recovery_reset"]["week_index"] == 1

    # 4. Tactical Watch stays locked on its selected drill, with its exact body
    # recovered from Stage 1 even though the packet compacts it away.
    watch_entry = by_role["tactical_watch"]
    assert watch_entry["authority"] == "deterministic_display_text"
    assert any(watch.name in line for line in watch_entry["exact_body_lines"])
    packet_watch = next(
        role
        for role in packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_roles"]
        if role.get("role_key") == "tactical_watch"
    )
    assert packet_watch["governance"]["selected_drill_locked"] is True
    assert "display_text" not in packet_watch

    # 6. The watch stays zero-load: it must not read as physical training.
    assert watch_entry["zero_physical_load"] is True
    assert watch_entry.get("selected_count") is None

    # 5. Combat wording comes from resolved canonical truth, not from the raw
    # declaration: D-11 sits inside the hard-contact cutoff, so the declared hard
    # day resolves to technical-only and must never carry the hard-sparring note.
    combat = by_role["hard_sparring_day"]
    assert combat["authority"] == "canonical_combat"
    assert combat["athlete_facing_label"] == CANONICAL_HARD_SPARRING_BAN_LABEL
    assert combat["exact_body_lines"] == [CANONICAL_TECHNICAL_ONLY_NOTE]
    assert combat["contact_load"] == "technical"
    assert CANONICAL_HARD_SPARRING_NOTE not in combat["exact_body_lines"]
    # No dose, rounds, RPE or work:rest is ever emitted for a combat day.
    assert not combat.get("exercise_lines")

    # Closed membership keeps its existing shape.
    strength = by_role["strength_touch_day"]
    assert strength["authority"] == "closed_selected_assignments"
    assert strength["selected_count"] == 1
    assert strength["exercise_lines"] == ["- Trap Bar Deadlift: 3 x 3; RPE 6-7"]


_PLAIN_WEEK_ONE = (
    "SPP — Week 1 (D-14 to D-8) — Objective: sharpen fight-specific output.\n"
    "D-12 (Saturday) — Strength touch\n"
    "- Trap Bar Deadlift — 3 x 3; RPE 6-7\n"
    "D-11 (Sunday) — Technical-only combat\n"
    "- Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority.\n"
    "D-11 (Sunday) — Tactical Focus\n"
    "- Tactical review only.\n"
    "D-9 (Tuesday) — Breathing Reset\n"
    "- Nasal breathing if comfortable.\n"
    "TAPER — Week 2 (D-7 to D-0) — Objective: arrive fresh.\n"
    "D-0 (Saturday) — Fight day\n"
)

_MARKDOWN_WEEK_ONE = "\n".join(
    ("## " + line) if ("Week 1 " in line or "Week 2 " in line) else line
    for line in _PLAIN_WEEK_ONE.split("\n")
)


@pytest.mark.parametrize(
    "rendered_plan", [_PLAIN_WEEK_ONE, _MARKDOWN_WEEK_ONE], ids=["plain", "markdown"]
)
def test_dropped_recovery_reset_is_restored_under_either_week_header_form(rendered_plan):
    """8 + 9. Stage 2 dropped the D-14 Recovery Reset; repair restores it."""
    planning_brief, _ = _week_one_planning_brief()
    report = {
        "blocking_warnings": [
            {
                "code": "late_camp_session_incomplete",
                "phase": "SPP",
                "week_index": 1,
                "expected_session_count": 5,
                "actual_session_count": 4,
            }
        ],
        "review_flags": [],
        "errors": [],
    }

    repaired = repair_stage2_structural_text(
        planning_brief=planning_brief,
        final_plan_text=rendered_plan,
        validator_report=report,
    )

    assert [entry["role_key"] for entry in repaired["applied"]] == ["recovery_reset"]
    assert repaired["unresolved"] == []
    assert _INSERT_META["recovery_reset"]["display_text"] in repaired["text"]
    # Restored in place, inside week 1's own section — never appended as a
    # second schedule after the taper week.
    assert repaired["text"].index("Recovery Reset") < repaired["text"].index("Week 2")
    # 7. Everything Stage 2 did render survives untouched.
    for surviving in ("Trap Bar Deadlift", "Tactical Focus", "Breathing Reset"):
        assert repaired["text"].count(surviving) == rendered_plan.count(surviving)


def test_repair_does_not_duplicate_roles_stage2_already_rendered():
    planning_brief, _ = _week_one_planning_brief()
    report = {
        "blocking_warnings": [
            {"code": "late_camp_session_incomplete", "phase": "SPP", "week_index": 1}
        ],
        "review_flags": [],
        "errors": [],
    }
    complete = _PLAIN_WEEK_ONE.replace(
        "D-12 (Saturday) — Strength touch",
        "D-14 (Thursday) — Recovery Reset\n- Breathing reset, easy tissue work.\n"
        "D-12 (Saturday) — Strength touch",
    )

    repaired = repair_stage2_structural_text(
        planning_brief=planning_brief,
        final_plan_text=complete,
        validator_report=report,
    )

    assert repaired["applied"] == []
    assert repaired["unresolved"] == []
    assert repaired["text"].count("Recovery Reset") == 1
