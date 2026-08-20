"""Carrying the canonical rehab-bank id from the plan to the completed session.

A completed rehab drill can only become injury evidence if it can be named. The
display name cannot name it — Stage 2 rewrites that text, and the markdown→JSON
conversion never sees the candidate pools at all, so nothing downstream can
recover the identity on its own.

The id is therefore resolved once, server-side, against the plan's own option
set, and stored on the block. These tests pin both halves: that the resolution
only ever produces an id it can actually justify, and that the bank lookup it
feeds refuses anything ambiguous.
"""

import pytest

from api.structured_plan_generation import reconcile_rehab_drill_ids
from fightcamp.rehab_protocols import (
    get_rehab_bank,
    rehab_drill_by_id,
    rehab_drill_options_for_phase,
)

ANKLE_DRILL = "ankle_sprain_single_leg_balance_on_foam_pad"


def _brief(*options: dict) -> dict:
    return {
        "candidate_pools": {
            "GPP": {
                "rehab_slots": [
                    {
                        "slot_id": "gpp_rehab_ankle_sprain_1",
                        "role": "rehab_ankle_sprain",
                        "selected": options[0],
                        "alternates": list(options[1:]),
                    }
                ]
            }
        }
    }


def _option(name: str, drill_id: str) -> dict:
    return {"name": name, "source": "rehab_block", "rehab_drill_id": drill_id}


def _plan(*blocks: dict) -> dict:
    return {
        "weeks": [
            {
                "week_index": 1,
                "days": [{"date": "2026-08-20", "sessions": [{"session_id": "s1", "blocks": list(blocks)}]}],
            }
        ]
    }


def _blocks(plan: dict) -> list[dict]:
    return plan["weeks"][0]["days"][0]["sessions"][0]["blocks"]


def _resolved_id(plan: dict, index: int = 0) -> str | None:
    """The block's id as every reader sees it.

    An unresolved block is left without the key rather than carrying an explicit
    null, which reads the same through ``.get()`` and through the Pydantic model
    (whose default is ``None``), and avoids rewriting every stored plan just to
    record an absence.
    """
    return _blocks(plan)[index].get("rehab_drill_id")


def _rehab_block(display_name: str, **extra) -> dict:
    return {
        "block_id": "b1",
        "block_type": "rehab",
        "display_name": display_name,
        **extra,
    }


# ---------------------------------------------------------------------------
# Resolving the id onto the plan
# ---------------------------------------------------------------------------


def test_a_rehab_block_gets_the_id_of_the_option_it_names():
    plan = _plan(_rehab_block("Single-Leg Balance on Foam Pad"))
    brief = _brief(_option("Single-Leg Balance on Foam Pad", ANKLE_DRILL))

    resolved = reconcile_rehab_drill_ids(plan, brief)

    assert _resolved_id(resolved) == ANKLE_DRILL


def test_an_alternate_the_plan_chose_instead_still_resolves():
    """Stage 2 may swap the selected drill for one of its alternates."""
    plan = _plan(_rehab_block("Ankle Alphabet"))
    brief = _brief(
        _option("Single-Leg Balance on Foam Pad", ANKLE_DRILL),
        _option("Ankle Alphabet", "ankle_sprain_ankle_alphabet"),
    )

    resolved = reconcile_rehab_drill_ids(plan, brief)

    assert _resolved_id(resolved) == "ankle_sprain_ankle_alphabet"


def test_matching_ignores_case_and_punctuation_but_not_the_words():
    plan = _plan(_rehab_block("single-leg balance on foam pad"))
    brief = _brief(_option("Single-Leg Balance on Foam Pad", ANKLE_DRILL))

    assert _resolved_id(reconcile_rehab_drill_ids(plan, brief)) == ANKLE_DRILL


def test_a_rewritten_name_resolves_to_nothing_rather_than_the_nearest_option():
    """Stage 2 rewriting the text is exactly when a guess would be wrong."""
    plan = _plan(_rehab_block("Balance work on the soft pad, 3 rounds"))
    brief = _brief(_option("Single-Leg Balance on Foam Pad", ANKLE_DRILL))

    resolved = reconcile_rehab_drill_ids(plan, brief)

    assert _resolved_id(resolved) is None


def test_one_name_claimed_by_two_bank_ids_resolves_to_nothing():
    """Two drills answering to one name cannot be told apart, so neither wins."""
    plan = _plan(_rehab_block("Isometric Hold"))
    brief = _brief(
        _option("Isometric Hold", "ankle_sprain_isometric_hold"),
        _option("Isometric Hold", "knee_pain_isometric_hold"),
    )

    resolved = reconcile_rehab_drill_ids(plan, brief)

    assert _resolved_id(resolved) is None


def test_a_non_rehab_block_never_carries_a_rehab_id():
    """A strength block is not an injury exposure, whatever it is named."""
    plan = _plan(
        {
            "block_id": "b1",
            "block_type": "strength",
            "display_name": "Single-Leg Balance on Foam Pad",
            "rehab_drill_id": ANKLE_DRILL,
        }
    )
    brief = _brief(_option("Single-Leg Balance on Foam Pad", ANKLE_DRILL))

    resolved = reconcile_rehab_drill_ids(plan, brief)

    assert _resolved_id(resolved) is None


def test_a_model_supplied_id_is_replaced_by_the_resolved_one():
    """The server's resolution is authoritative; a claimed id is not evidence."""
    plan = _plan(
        _rehab_block("Single-Leg Balance on Foam Pad", rehab_drill_id="something_invented")
    )
    brief = _brief(_option("Single-Leg Balance on Foam Pad", ANKLE_DRILL))

    resolved = reconcile_rehab_drill_ids(plan, brief)

    assert _resolved_id(resolved) == ANKLE_DRILL


def test_a_claimed_id_with_no_matching_option_is_cleared():
    plan = _plan(_rehab_block("Some Other Drill", rehab_drill_id=ANKLE_DRILL))
    brief = _brief(_option("Single-Leg Balance on Foam Pad", ANKLE_DRILL))

    resolved = reconcile_rehab_drill_ids(plan, brief)

    assert _resolved_id(resolved) is None


def test_a_plan_with_no_rehab_pool_is_returned_untouched():
    plan = _plan(_rehab_block("Single-Leg Balance on Foam Pad"))

    assert reconcile_rehab_drill_ids(plan, {"candidate_pools": {}}) is plan
    assert reconcile_rehab_drill_ids(plan, {}) is plan


def test_reconciliation_does_not_mutate_the_input_plan():
    plan = _plan(_rehab_block("Single-Leg Balance on Foam Pad"))
    brief = _brief(_option("Single-Leg Balance on Foam Pad", ANKLE_DRILL))

    reconcile_rehab_drill_ids(plan, brief)

    assert "rehab_drill_id" not in _blocks(plan)[0]


def test_reconciliation_is_idempotent():
    plan = _plan(_rehab_block("Single-Leg Balance on Foam Pad"))
    brief = _brief(_option("Single-Leg Balance on Foam Pad", ANKLE_DRILL))

    once = reconcile_rehab_drill_ids(plan, brief)
    twice = reconcile_rehab_drill_ids(once, brief)

    assert twice is once


def test_the_stamped_id_survives_the_structured_plan_schema():
    """A resolved id is no use if the model drops it on the way to storage."""
    from api.structured_plan_models import SessionBlock

    block = SessionBlock(
        block_id="b1",
        block_type="rehab",
        display_name="Single-Leg Balance on Foam Pad",
        rehab_drill_id=ANKLE_DRILL,
    )
    assert block.model_dump(mode="json")["rehab_drill_id"] == ANKLE_DRILL
    assert SessionBlock(block_id="b2", block_type="strength", display_name="Squat").rehab_drill_id is None


# ---------------------------------------------------------------------------
# Looking the drill back up
# ---------------------------------------------------------------------------


def test_a_real_bank_id_resolves_to_its_drill():
    drill = rehab_drill_by_id(ANKLE_DRILL)

    assert drill is not None
    assert drill["id"] == ANKLE_DRILL
    assert drill["target_regions"] == ["ankle"]


@pytest.mark.parametrize("value", ["", None, "   ", "not_a_real_drill", "Single-Leg Balance"])
def test_anything_the_bank_does_not_contain_resolves_to_nothing(value):
    assert rehab_drill_by_id(value) is None


def test_every_shipped_drill_id_resolves_to_itself():
    """The lookup is the completion path's only route back to the bank."""
    resolved = 0
    for entry in get_rehab_bank():
        for drill in entry.get("drills") or []:
            drill_id = drill.get("id")
            if not drill_id:
                continue
            assert rehab_drill_by_id(drill_id) is not None, drill_id
            resolved += 1
    assert resolved > 1000, "the musculoskeletal bank should be fully addressable"


def test_the_ids_offered_to_a_plan_are_the_ids_the_bank_answers_to():
    """The two halves must agree, or a stamped id would not resolve later."""
    for phase in ("GPP", "SPP", "TAPER"):
        for option in rehab_drill_options_for_phase("sprain", "ankle", phase, limit=6):
            drill_id = option["drill"]["id"]
            assert rehab_drill_by_id(drill_id) is option["drill"]


# ---------------------------------------------------------------------------
# The id survives the real Stage 2 candidate pool
# ---------------------------------------------------------------------------


def test_every_option_in_a_real_rehab_slot_carries_a_resolvable_id():
    """The chain only works if the pool the plan is built from carries the ids.

    Selected drills and alternates are drawn from two different reads of the
    bank, so this walks a genuinely generated rehab block rather than a fixture:
    an option without an id would silently make its drill unloggable forever.
    """
    from fightcamp.rehab_protocols import generate_rehab_protocols, get_exercise_bank
    from fightcamp.stage2_payload import _build_rehab_slots

    checked = 0
    for phase in ("GPP", "SPP", "TAPER"):
        block, _seen = generate_rehab_protocols(
            injury_string="left ankle sprain, right knee pain",
            exercise_data=get_exercise_bank(),
            current_phase=phase,
        )
        slots = _build_rehab_slots(block, phase)
        assert slots, f"expected rehab slots for {phase}"
        for slot in slots:
            for option in [slot["selected"], *slot["alternates"]]:
                drill_id = option["rehab_drill_id"]
                assert drill_id, f"{phase}: {option['name']!r} carries no bank id"
                assert rehab_drill_by_id(drill_id) is not None, drill_id
                checked += 1
    assert checked >= 30


def test_a_surface_wound_option_carries_no_bank_id():
    """Wound care has no loading drill to attribute, so it claims no identity."""
    options = rehab_drill_options_for_phase("laceration", "brow", "GPP", limit=4)
    assert options, "expected wound-care guidance"
    assert all(option["drill"] is None for option in options)
