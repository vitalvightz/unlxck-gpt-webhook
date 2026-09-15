"""Deterministic Stage 1 content must survive Stage 1 -> Stage 2 rendering.

The production failure these cover: Stage 1's Week 1 role map held five roles and
Stage 2 rendered four — the D-14 Recovery Reset vanished — and deterministic
source repair could not put it back, because (a) the locked render manifest only
recognised ``selected_exercise_assignments`` so a planner-written Recovery Reset
never reached the first pass, and (b) the repair parser only found week sections
behind a Markdown ``#`` prefix, so the contract-valid plain header
``SPP — Week 1 (D-14 to D-8) — Objective`` read as "week not rendered".
"""

import pytest

from fightcamp.combat_render_authority import (
    CANONICAL_HARD_SPARRING_BAN_LABEL,
    CANONICAL_HARD_SPARRING_LABEL,
    CANONICAL_HARD_SPARRING_NOTE,
    CANONICAL_LIGHT_COMBAT_LABEL,
    CANONICAL_LIGHT_COMBAT_NOTE,
    CANONICAL_TECHNICAL_ONLY_NOTE,
    canonical_combat_render,
)
from fightcamp.coordination_support_library import (
    all_coordination_drills,
    build_coordination_display_text,
    coordination_support_metadata,
)
from fightcamp.fight_day_override import FIGHT_DAY_PROTOCOL_TEXT
from fightcamp.gap_fill_inserts import _INSERT_META, _build_insert_role
from fightcamp.render_authority import (
    AUTHORITY_CANONICAL_COMBAT,
    AUTHORITY_CLOSED_SELECTED_ASSIGNMENTS,
    AUTHORITY_DETERMINISTIC_DISPLAY_TEXT,
    AUTHORITY_FIGHT_DAY_PROTOCOL,
    authoritative_render_for_role,
)
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import _closed_membership_render_manifest
from fightcamp.stage2_pipeline import repair_stage2_structural_text
from fightcamp.tactical_watch_library import (
    build_watch_display_text,
    select_tactical_watch,
    watch_metadata,
)


# ─────────────────────────── B. deterministic exact content ──────────────────


@pytest.mark.parametrize(
    "role_key",
    sorted(key for key, meta in _INSERT_META.items() if meta.get("display_text")),
)
def test_every_static_gap_fill_insert_is_server_authoritative(role_key):
    """Each _INSERT_META insert leaves Stage 1 with a complete body."""
    role = _build_insert_role(role_key, {"sport": "boxing"}, 9, weekday="tuesday")

    render = authoritative_render_for_role(role)

    assert render is not None, role_key
    assert render["authority"] == AUTHORITY_DETERMINISTIC_DISPLAY_TEXT
    assert render["athlete_facing_label"] == role["athlete_facing_label"]
    assert render["body_lines"] == [_INSERT_META[role_key]["display_text"]]


def test_tactical_watch_copy_comes_from_the_selected_bank_item():
    """The watch body is bank-selected, not _INSERT_META copy."""
    role = _build_insert_role("tactical_watch", {"sport": "boxing"}, 11, weekday="sunday")

    render = authoritative_render_for_role(role)

    assert render is not None
    assert render["authority"] == AUTHORITY_DETERMINISTIC_DISPLAY_TEXT
    assert role["governance"]["selected_drill_locked"] is True
    # Zero-load review work: it must never look like physical training.
    assert render["zero_physical_load"] is True
    assert render["body_lines"] == [
        line for line in role["display_text"].splitlines() if line.strip()
    ]


def test_selected_coordination_support_survives_exactly():
    drill = next(iter(all_coordination_drills()))
    metadata = coordination_support_metadata(drill)
    role = {
        "category": "support_insert",
        "role_key": "coordination_support",
        "athlete_facing_label": "Coordination",
        "scheduled_day_hint": "wednesday",
        "display_text": build_coordination_display_text(drill),
        **{k: v for k, v in metadata.items() if k != "governance"},
        "governance": metadata["governance"],
    }

    render = authoritative_render_for_role(role)

    assert render is not None
    assert render["authority"] == AUTHORITY_DETERMINISTIC_DISPLAY_TEXT
    # The selected drill's own name and dose, never a reselected one.
    assert any(drill.name in line for line in render["body_lines"])
    assert render["body_lines"] == [
        line for line in role["display_text"].splitlines() if line.strip()
    ]


# ─────────────────────────────── combat ──────────────────────────────────────


def _hard_sparring_role(**overrides):
    role = {
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "coach_owned": True,
        "scheduled_day_hint": "sunday",
        "hard_sparring_status": "hard_as_planned",
    }
    role.update(overrides)
    return role


def test_hard_as_planned_renders_canonical_hard_copy():
    render = authoritative_render_for_role(_hard_sparring_role(), d_day=25)

    assert render["authority"] == AUTHORITY_CANONICAL_COMBAT
    assert render["athlete_facing_label"] == CANONICAL_HARD_SPARRING_LABEL
    assert render["body_lines"] == [CANONICAL_HARD_SPARRING_NOTE]
    assert render["contact_load"] == "hard"


def test_technical_only_conversion_never_renders_hard_copy():
    for role in (
        _hard_sparring_role(hard_sparring_status="convert_to_technical_suggested"),
        _hard_sparring_role(hard_sparring_reason_codes=["d14_hard_sparring_ban"]),
        _hard_sparring_role(downgraded=True, downgraded_from_role_key="hard_sparring_day"),
    ):
        render = authoritative_render_for_role(role, d_day=12)
        assert render["athlete_facing_label"] == CANONICAL_HARD_SPARRING_BAN_LABEL
        assert render["body_lines"] == [CANONICAL_TECHNICAL_ONLY_NOTE]
        assert CANONICAL_HARD_SPARRING_NOTE not in render["body_lines"]


def test_declared_light_combat_uses_the_one_canonical_copy():
    from fightcamp.declared_combat_ownership import build_declared_light_combat_role

    role = build_declared_light_combat_role("wednesday")

    render = authoritative_render_for_role(role)

    assert render["athlete_facing_label"] == CANONICAL_LIGHT_COMBAT_LABEL
    assert render["body_lines"] == [CANONICAL_LIGHT_COMBAT_NOTE]


def test_safety_blocked_contact_is_never_server_rendered():
    """A medical block fails closed: no invented wording, and no restored contact."""
    blocked = _hard_sparring_role(hard_sparring_status="blocked")

    assert canonical_combat_render(blocked) is None
    assert authoritative_render_for_role(blocked, d_day=20) is None

    # The snapshot-level safety veto wins over an otherwise hard-as-planned day.
    assert (
        authoritative_render_for_role(
            _hard_sparring_role(),
            d_day=20,
            athlete_snapshot={"readiness_flags": ["suspected_concussion"]},
        )
        is None
    )


def test_unresolved_or_deloaded_combat_state_is_not_authoritative():
    # No status at all: the planner never ran its verdict over this day.
    assert authoritative_render_for_role(
        {"role_key": "hard_sparring_day", "category": "sparring", "coach_owned": True},
        d_day=25,
    ) is None
    # Deloaded: still hard contact, but its coach note carries the meaning.
    assert authoritative_render_for_role(
        _hard_sparring_role(hard_sparring_status="deload_suggested"), d_day=25
    ) is None


def test_fight_day_protocol_is_server_owned():
    from fightcamp.fight_day_override import _make_fight_day_protocol_role

    render = authoritative_render_for_role(_make_fight_day_protocol_role("saturday"), d_day=0)

    assert render["authority"] == AUTHORITY_FIGHT_DAY_PROTOCOL
    assert render["body_lines"] == [FIGHT_DAY_PROTOCOL_TEXT]


# ───────────────────────── closed membership + microdose ─────────────────────


def test_closed_membership_stays_authoritative_and_fully_priced():
    role = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "selected_exercise_assignments": [
            {"name": "Trap Bar Deadlift", "effective_prescription": "3 x 3; RPE 6-7"},
        ],
    }

    render = authoritative_render_for_role(role)

    assert render["authority"] == AUTHORITY_CLOSED_SELECTED_ASSIGNMENTS
    assert render["exercise_lines"] == ["- Trap Bar Deadlift — 3 x 3; RPE 6-7"]

    # One unpriced member makes the whole role non-authoritative.
    role["selected_exercise_assignments"].append({"name": "Med Ball Scoop Toss"})
    assert authoritative_render_for_role(role) is None


def test_priority_microdose_survives_once_inside_its_host():
    microdose = {
        "goal": "speed",
        "name": "Band-Resisted Punch Throw",
        "prescription": "2 x 6 each side; full recovery",
    }
    host = {
        "role_key": "technical_touch_day",
        "category": "technical",
        "priority_microdose": microdose,
        "selected_exercise_assignments": [
            {"name": "Shadow Rhythm", "effective_prescription": "3 x 2 min"},
        ],
    }

    render = authoritative_render_for_role(host)
    body = "\n".join(render["body_lines"])

    assert body.count(microdose["name"]) == 1
    assert microdose["prescription"] in body
    assert render["priority_microdose"] == microdose

    # Goal preservation mirrors a microdose into the host's closed membership.
    # It must not then be added a second time.
    host["selected_exercise_assignments"].append(
        {"name": microdose["name"], "effective_prescription": microdose["prescription"]}
    )
    rerendered = "\n".join(authoritative_render_for_role(host)["body_lines"])
    assert rerendered.count(microdose["name"]) == 1


# ─────────────────────────── C. genuinely open roles ─────────────────────────


def test_open_role_gets_no_invented_body():
    """The negative case: no assignments, no decided text, no canonical body."""
    for role in (
        {
            "role_key": "conditioning_day",
            "category": "conditioning",
            "athlete_facing_label": "Fight-pace conditioning",
            "scheduled_day_hint": "monday",
            "preferred_exercise_names": ["Air Bike Sprint"],
        },
        # A category such as "recovery" is not authority.
        {
            "role_key": "recovery_day",
            "category": "recovery",
            "scheduled_day_hint": "friday",
        },
        # Draft prose with no authority signal is not server truth.
        {
            "role_key": "technical_day",
            "category": "technical",
            "display_text": "Some drafted technical notes.",
        },
    ):
        assert authoritative_render_for_role(role) is None
