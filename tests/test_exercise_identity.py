"""Exercise identity (SessionBlock.exercise_key) is separate from display copy.

Demo videos must resolve on the block's canonical exercise identity, so a
Stage-2 rewrite of display_name ("3 x 2 min easy rounds") or of the session
title never loses or swaps a video. Legacy blocks without identity keep the
display_name fallback.
"""

from __future__ import annotations

import copy

import pytest

from api.exercise_identity import reconcile_exercise_keys
from api.services import exercise_media as media
from api.structured_plan_generation import bank_conditioning_to_block, bank_strength_to_block
from api.structured_plan_models import StructuredTrainingPlan
from fightcamp.exercise_identity import stamp_exercise_key
from fightcamp.gap_fill_inserts import _build_insert_role
from fightcamp.session_composition import assignment_from_slot
from test_structured_plan_models import _valid_plan

SHADOW_VIDEO = "SHADOWxxxx1"
ROPE_VIDEO = "ROPExxxxxx1"


def _row(key, video_id, aliases=()):
    return {
        "exercise_key": key,
        "video_id": video_id,
        "start_s": 0,
        "end_s": None,
        "made_for_kids": False,
        "aliases": list(aliases),
    }


def _index():
    return media.build_media_index(
        [
            _row("tempo-shadowboxing", SHADOW_VIDEO, aliases=["shadowboxing-aerobic-flow"]),
            _row("jump-rope-recovery-pace", ROPE_VIDEO),
            _row("box-jump-max-height", "BOXMAXxxxx1"),
            _row("box-jump-stick-landing", "BOXSTICKxx1"),
            _row("sled-push", "SLEDPUSHxx1"),
            _row("sled-drag", "SLEDDRAGxx1", aliases=["sled-push"]),
            _row("romanian-deadlift-rdl", "RDLxxxxxxx1", aliases=["RDL"]),
        ]
    )


def _plan(blocks: list[dict], *, title: str = "Session", countdown: str | None = None) -> dict:
    plan = copy.deepcopy(_valid_plan())
    day = plan["weeks"][0]["days"][0]
    if countdown is not None:
        day["countdown_label"] = countdown
    session = day["sessions"][0]
    session["title"] = title
    template = session["blocks"][0]
    session["blocks"] = [
        {**copy.deepcopy(template), "block_id": f"b-{i}", **block}
        for i, block in enumerate(blocks)
    ]
    return plan


def _blocks(plan: dict) -> list[dict]:
    return plan["weeks"][0]["days"][0]["sessions"][0]["blocks"]


def _resolve(plan: dict) -> dict:
    return media.resolve_plan_exercise_media(StructuredTrainingPlan.model_validate(plan), _index())


def _brief(*roles: dict, d_day: int = 9, **extra) -> dict:
    """A camp brief: fight date plus one planning week covering ``d_day``."""
    return {
        "fight_date": "2026-12-01",
        "weekly_role_map": {
            "weeks": [{
                "phase": "GPP",
                "week_index": 1,
                "calendar_days": [{"d_day": d_day}],
                "session_roles": list(roles),
            }]
        },
        **extra,
    }


def _brief_with_insert(role: dict) -> dict:
    return _brief(role, d_day=role["countdown_offset"])


def _strength_role(*names: str, d_day: int = 9) -> dict:
    return {
        "role_key": "primary_strength",
        "athlete_facing_label": "Power Strength",
        "countdown_offset": d_day,
        "countdown_label": f"D-{d_day}",
        "selected_exercise_assignments": [
            stamp_exercise_key({"name": name, "slot_group": "strength_slots"}) for name in names
        ],
    }


def _boxing_role(role_key: str, *, fatigue: str = "high") -> dict:
    athlete = {"sport": "boxing", "fatigue": fatigue, "fight_format": "boxing"}
    return _build_insert_role(role_key, athlete, 9, "tue")


# -- resolution on identity --------------------------------------------------


def test_canonical_identity_resolves_despite_dose_display_name():
    plan = _plan([{"display_name": "3 x 2 min easy rounds", "exercise_key": "tempo-shadowboxing"}])

    resolved = _resolve(plan)

    assert resolved == {"exercise:tempo-shadowboxing": resolved["exercise:tempo-shadowboxing"]}
    assert resolved["exercise:tempo-shadowboxing"].video_id == SHADOW_VIDEO


@pytest.mark.parametrize("display_name", ["Tempo Shadowboxing", "Easy rounds", "Shadow work (light)"])
def test_rewording_display_name_does_not_break_lookup(display_name):
    plan = _plan([{"display_name": display_name, "exercise_key": "tempo-shadowboxing"}])

    assert _resolve(plan)["exercise:tempo-shadowboxing"].video_id == SHADOW_VIDEO


def test_legacy_block_without_identity_uses_display_name():
    plan = _plan([{"display_name": "Romanian Deadlift (RDL)"}, {"display_name": "Sled Push - 4 x 20 m"}])

    resolved = _resolve(plan)

    assert resolved["Romanian Deadlift (RDL)"].video_id == "RDLxxxxxxx1"
    assert resolved["Sled Push - 4 x 20 m"].video_id == "SLEDPUSHxx1"


def test_explicit_alias_still_resolves_for_identity_and_legacy_name():
    plan = _plan([
        {"display_name": "RDL"},
        {"display_name": "anything", "exercise_key": "shadowboxing-aerobic-flow"},
    ])

    resolved = _resolve(plan)

    assert resolved["RDL"].video_id == "RDLxxxxxxx1"
    assert resolved["exercise:shadowboxing-aerobic-flow"].video_id == SHADOW_VIDEO


def test_primary_key_beats_alias_on_identity():
    plan = _plan([{"display_name": "Sled work", "exercise_key": "sled-push"}])

    assert _resolve(plan)["exercise:sled-push"].video_id == "SLEDPUSHxx1"


def test_qualified_variants_keep_distinct_media():
    plan = _plan([
        {"display_name": "Box Jump (Max Height)", "exercise_key": "box-jump-max-height"},
        {"display_name": "Box Jump (Stick Landing)", "exercise_key": "box-jump-stick-landing"},
        {"display_name": "Box Jump"},
    ])

    resolved = _resolve(plan)

    assert resolved["exercise:box-jump-max-height"].video_id == "BOXMAXxxxx1"
    assert resolved["exercise:box-jump-stick-landing"].video_id == "BOXSTICKxx1"
    assert "Box Jump" not in resolved


def test_identity_is_authoritative_over_a_shared_display_name():
    # Same copy, different movements: neither borrows the other's video.
    plan = _plan([
        {"display_name": "3 x 2 min easy rounds", "exercise_key": "tempo-shadowboxing"},
        {"display_name": "3 x 2 min easy rounds"},
    ])

    assert set(_resolve(plan)) == {"exercise:tempo-shadowboxing"}


def test_non_physical_blocks_stay_media_free():
    plan = _plan([
        {"display_name": "Tempo Shadowboxing", "block_type": "mindset"},
        {"display_name": "Visualise", "block_type": "mindset", "exercise_key": "tempo-shadowboxing"},
    ])

    assert _resolve(plan) == {}


def test_bank_adapters_stamp_canonical_identity():
    assert bank_strength_to_block({"name": "Box Jump (Max Height)"})["exercise_key"] == "box-jump-max-height"
    assert bank_conditioning_to_block({"name": "Tempo Shadowboxing"})["exercise_key"] == "tempo-shadowboxing"


# -- reconciliation from planner data ---------------------------------------


def test_gap_fill_role_carries_deterministic_identity():
    assert _boxing_role("aerobic_shadow_flow")["athlete_facing_label"] == "Shadowboxing Aerobic Flow"
    assert _boxing_role("aerobic_shadow_flow")["exercise_key"] == "tempo-shadowboxing"
    assert _boxing_role("aerobic_skip_flush")["exercise_key"] == "jump-rope-recovery-pace"
    # Generic solo movement is not a known movement, so it gets no key.
    generic = _build_insert_role("aerobic_shadow_flow", {"sport": "mma"}, 9, "tue")
    assert generic["athlete_facing_label"] == "Aerobic Movement Flow"
    assert "exercise_key" not in generic
    for role_key in ("aerobic_walk_flush", "aerobic_jog_flush", "aerobic_footwork_rhythm"):
        assert "exercise_key" not in _boxing_role(role_key)


def test_shadowboxing_gap_fill_resolves_despite_dose_block_name():
    role = _boxing_role("aerobic_shadow_flow")
    plan = _plan(
        [{"display_name": "3 x 2 min easy rounds", "block_type": "conditioning"}],
        title="Shadowboxing Aerobic Flow",
        countdown=role["countdown_label"],
    )

    reconciled = reconcile_exercise_keys(plan, _brief_with_insert(role))

    assert _blocks(reconciled)[0]["exercise_key"] == "tempo-shadowboxing"
    assert _blocks(reconciled)[0]["display_name"] == "3 x 2 min easy rounds"
    assert reconciled["weeks"][0]["days"][0]["sessions"][0]["title"] == "Shadowboxing Aerobic Flow"
    assert _resolve(reconciled)["exercise:tempo-shadowboxing"].video_id == SHADOW_VIDEO


def test_skipping_flush_resolves_through_identity_not_alias():
    role = _boxing_role("aerobic_skip_flush")
    plan = _plan(
        [{"display_name": "Skipping flush (30/30)", "block_type": "conditioning"}],
        title="Skipping flush (short)",
        countdown=role["countdown_label"],
    )

    reconciled = reconcile_exercise_keys(plan, _brief_with_insert(role))

    assert _blocks(reconciled)[0]["exercise_key"] == "jump-rope-recovery-pace"
    # No "skipping-flush-30-30" alias exists in the index.
    assert _resolve(reconciled)["exercise:jump-rope-recovery-pace"].video_id == ROPE_VIDEO


def test_insert_identity_needs_the_inserts_own_day():
    role = _boxing_role("aerobic_shadow_flow")
    plan = _plan(
        [{"display_name": "3 x 2 min easy rounds", "block_type": "conditioning"}],
        title="Shadowboxing Aerobic Flow",
        countdown="D-30",
    )

    assert reconcile_exercise_keys(plan, _brief_with_insert(role)) is plan


def test_insert_identity_skips_other_named_blocks_and_mindset():
    role = _boxing_role("aerobic_shadow_flow")
    plan = _plan(
        [
            {"display_name": "Ankle rocks", "block_type": "mobility_activation"},
            {"display_name": "3 x 2 min easy rounds", "block_type": "conditioning"},
            {"display_name": "Breathe and reset", "block_type": "mindset"},
        ],
        title="Shadowboxing Aerobic Flow",
        countdown=role["countdown_label"],
    )

    blocks = _blocks(reconcile_exercise_keys(plan, _brief_with_insert(role)))

    assert [block.get("exercise_key") for block in blocks] == [None, "tempo-shadowboxing", None]


def test_bank_blocks_take_identity_from_candidate_pool_exactly():
    brief = {
        "candidate_pools": {
            "GPP": {
                "strength_slots": [{"selected": {"name": "Box Jump (Max Height)"}, "alternates": []}],
                "conditioning_slots": [{"selected": {"name": "Tempo Shadowboxing"}}],
            }
        }
    }
    plan = _plan([
        {"display_name": "Box Jump (Max Height)", "block_type": "plyometric_power"},
        {"display_name": "Box Jump (Stick Landing)", "block_type": "plyometric_power"},
        {"display_name": "Tempo Shadowboxing - 3 x 3 min", "block_type": "conditioning"},
    ])

    blocks = _blocks(reconcile_exercise_keys(plan, brief))

    assert [block.get("exercise_key") for block in blocks] == [
        "box-jump-max-height",
        None,
        "tempo-shadowboxing",
    ]


def test_model_supplied_identity_is_not_trusted():
    plan = _plan([{"display_name": "Push-ups", "exercise_key": "tempo-shadowboxing"}])

    reconciled = reconcile_exercise_keys(plan, {})

    assert _blocks(reconciled)[0]["exercise_key"] is None


def test_reconcile_is_idempotent_and_preserves_identity_through_serialization():
    role = _boxing_role("aerobic_shadow_flow")
    plan = _plan(
        [{"display_name": "3 x 2 min easy rounds", "block_type": "conditioning"}],
        title="Shadowboxing Aerobic Flow",
        countdown=role["countdown_label"],
    )
    brief = _brief_with_insert(role)
    once = reconcile_exercise_keys(plan, brief)

    assert reconcile_exercise_keys(once, brief) is once
    dumped = StructuredTrainingPlan.model_validate(once).model_dump(mode="json")
    assert _blocks(dumped)[0]["exercise_key"] == "tempo-shadowboxing"


def test_legacy_plan_without_brief_is_left_unchanged():
    plan = _plan([{"display_name": "Romanian Deadlift (RDL)"}])

    assert reconcile_exercise_keys(plan, None) is plan
    assert _resolve(plan)["Romanian Deadlift (RDL)"].video_id == "RDLxxxxxxx1"


# -- planner assignments are the identity authority --------------------------


def test_assignment_is_stamped_at_selection():
    assignment = assignment_from_slot(
        "GPP", "strength_slots", {"slot_id": "s1", "selected": {"name": "Medicine Ball Rotational Slam"}}
    )

    assert assignment["exercise_key"] == "medicine-ball-rotational-slam"


def test_retitled_session_and_renamed_blocks_take_keys_from_planner_membership():
    role = _strength_role("Medicine Ball Rotational Slam", "Trap Bar Deadlift")
    plan = _plan(
        [
            {"display_name": "4 x 5 explosive throws", "block_type": "plyometric_power"},
            {"display_name": "Heavy pulls", "block_type": "strength"},
        ],
        title="Power Strength",
        countdown="D-9",
    )

    blocks = _blocks(reconcile_exercise_keys(plan, _brief(role)))

    assert [b["exercise_key"] for b in blocks] == ["medicine-ball-rotational-slam", "trap-bar-deadlift"]
    assert [b["display_name"] for b in blocks] == ["4 x 5 explosive throws", "Heavy pulls"]


def test_named_member_is_claimed_first_and_order_fills_the_rest():
    role = _strength_role("Medicine Ball Rotational Slam", "Trap Bar Deadlift")
    plan = _plan(
        [
            {"display_name": "Trap Bar Deadlift", "block_type": "strength"},
            {"display_name": "Explosive throws", "block_type": "plyometric_power"},
        ],
        title="Power Strength",
        countdown="D-9",
    )

    blocks = _blocks(reconcile_exercise_keys(plan, _brief(role)))

    assert [b["exercise_key"] for b in blocks] == ["trap-bar-deadlift", "medicine-ball-rotational-slam"]


def test_converter_added_warmup_is_set_aside_from_planner_order():
    role = _strength_role("Medicine Ball Rotational Slam")
    plan = _plan(
        [
            {"display_name": "Dynamic warm-up", "block_type": "preparation"},
            {"display_name": "4 x 5 explosive throws", "block_type": "plyometric_power"},
        ],
        title="Power Strength",
        countdown="D-9",
    )

    blocks = _blocks(reconcile_exercise_keys(plan, _brief(role)))

    assert [b.get("exercise_key") for b in blocks] == [None, "medicine-ball-rotational-slam"]


def test_membership_count_mismatch_stamps_nothing_rather_than_guess():
    role = _strength_role("Medicine Ball Rotational Slam", "Trap Bar Deadlift")
    plan = _plan(
        [
            {"display_name": "Explosive throws", "block_type": "plyometric_power"},
            {"display_name": "Heavy pulls", "block_type": "strength"},
            {"display_name": "Carries", "block_type": "strength"},
        ],
        title="Power Strength",
        countdown="D-9",
    )

    assert reconcile_exercise_keys(plan, _brief(role)) is plan


def test_membership_identity_needs_the_roles_own_day():
    role = _strength_role("Medicine Ball Rotational Slam")
    plan = _plan(
        [{"display_name": "4 x 5 explosive throws", "block_type": "plyometric_power"}],
        title="Power Strength",
        countdown="D-12",
    )

    assert reconcile_exercise_keys(plan, _brief(role)) is plan


def test_legacy_assignments_without_stamp_derive_key_from_bank_name():
    role = _strength_role("Medicine Ball Rotational Slam")
    for assignment in role["selected_exercise_assignments"]:
        assignment.pop("exercise_key")
    plan = _plan(
        [{"display_name": "4 x 5 explosive throws", "block_type": "plyometric_power"}],
        title="Power Strength",
        countdown="D-9",
    )

    blocks = _blocks(reconcile_exercise_keys(plan, _brief(role)))

    assert blocks[0]["exercise_key"] == "medicine-ball-rotational-slam"


def test_labelled_microdose_block_resolves_to_its_assignment():
    role = _strength_role("Pallof Press")
    plan = _plan(
        [
            {"display_name": "Core microdose - Pallof Press", "block_type": "accessory"},
            {"display_name": "Breathe", "block_type": "mindset"},
        ],
        title="Something else",
        countdown="D-9",
    )

    blocks = _blocks(reconcile_exercise_keys(plan, _brief(role)))

    assert [b.get("exercise_key") for b in blocks] == ["pallof-press", None]


def test_manifest_carries_planner_keys_in_membership_order():
    from fightcamp.stage2_payload import _attach_manifest_exercise_keys

    entry: dict = {}
    _attach_manifest_exercise_keys(entry, _strength_role("Medicine Ball Rotational Slam", "Pallof Press")["selected_exercise_assignments"])

    assert entry["exercise_keys"] == ["medicine-ball-rotational-slam", "pallof-press"]
