"""Canonical declared-combat copy must have exactly one source.

The hard-sparring / technical-only / light-combat label+note pairs used to be
written out independently in the Stage 2 prompt, the Stage 2 repair prompt, the
late-fight visible calendar, the structured-plan reconciler and (nearly) in a new
render manifest. Every runtime consumer now reads
``fightcamp.combat_render_authority``; the two prompt templates still inline the
strings as prose, so this test pins them to the constants and fails the moment
either side drifts.
"""

import pytest

from fightcamp.combat_render_authority import (
    CANONICAL_HARD_SPARRING_BAN_LABEL,
    CANONICAL_HARD_SPARRING_LABEL,
    CANONICAL_HARD_SPARRING_NOTE,
    CANONICAL_LIGHT_COMBAT_LABEL,
    CANONICAL_LIGHT_COMBAT_NOTE,
    CANONICAL_TECHNICAL_ONLY_NOTE,
)
from fightcamp.declared_combat_ownership import LIGHT_COMBAT_ATHLETE_FACING_LABEL
from fightcamp.stage2_payload import STAGE2_FINALIZER_PROMPT
from fightcamp.stage2_repair import REPAIR_PROMPT_TEMPLATE


_CANONICAL = (
    CANONICAL_HARD_SPARRING_LABEL,
    CANONICAL_HARD_SPARRING_BAN_LABEL,
    CANONICAL_HARD_SPARRING_NOTE,
    CANONICAL_TECHNICAL_ONLY_NOTE,
)


@pytest.mark.parametrize("canonical", _CANONICAL)
def test_repair_prompt_uses_the_canonical_combat_copy(canonical):
    assert canonical in REPAIR_PROMPT_TEMPLATE


@pytest.mark.parametrize("canonical", _CANONICAL)
def test_finalizer_prompt_uses_the_canonical_combat_copy(canonical):
    assert canonical in STAGE2_FINALIZER_PROMPT


def test_hard_and_technical_notes_never_share_wording():
    """A technical-only card must never tell the athlete to spar hard."""
    assert CANONICAL_HARD_SPARRING_NOTE != CANONICAL_TECHNICAL_ONLY_NOTE
    assert "no hard sparring" in CANONICAL_TECHNICAL_ONLY_NOTE


def test_light_combat_label_has_one_owner():
    assert CANONICAL_LIGHT_COMBAT_LABEL == LIGHT_COMBAT_ATHLETE_FACING_LABEL
    assert CANONICAL_LIGHT_COMBAT_NOTE.startswith("Your declared light-combat")


def test_late_fight_visible_calendar_uses_the_shared_constants():
    from fightcamp.stage2_payload_late_fight import _coach_owned_context_session_sequence

    visible = _coach_owned_context_session_sequence(
        [
            {
                "role_key": "hard_sparring_day",
                "scheduled_day_hint": "sunday",
                "countdown_offset": 11,
            },
            {
                "role_key": "hard_sparring_day",
                "scheduled_day_hint": "tuesday",
                "countdown_offset": 9,
                "downgraded": True,
            },
            {
                "role_key": "light_combat_day",
                "coach_owned": True,
                "scheduled_day_hint": "wednesday",
                "countdown_offset": 8,
            },
        ]
    )
    rendered = {
        session["athlete_facing_label"]: session["display_text"] for session in visible
    }
    assert rendered == {
        CANONICAL_HARD_SPARRING_LABEL: CANONICAL_HARD_SPARRING_NOTE,
        CANONICAL_HARD_SPARRING_BAN_LABEL: CANONICAL_TECHNICAL_ONLY_NOTE,
        CANONICAL_LIGHT_COMBAT_LABEL: CANONICAL_LIGHT_COMBAT_NOTE,
    }
