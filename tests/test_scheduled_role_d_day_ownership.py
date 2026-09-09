"""Day ownership for a scheduled role has one resolver.

``stage2_validator._scheduled_role_d_day`` used to be a local resolver with its
own field precedence: ``scheduled_countdown_label``, then ``countdown_label``,
then the weekday. It never read ``scheduled_d_day`` or ``countdown_offset``.

Those are exactly the two fields ``calendar_integrity._stamp_relocation`` always
writes when the final governor moves a role, while ``countdown_label`` is never
refreshed there. So the old order trusted a field the governor leaves stale over
the two it keeps current — and ``stage2_repair`` resolves days through the same
helper, so a closed conditioning member could be looked for, or re-inserted, on
a day the governor had already moved it off.

These tests pin the delegation to ``calendar_context.role_d_day``, the canonical
representation owner named by the architecture contract.
"""

from fightcamp.calendar_context import role_d_day
from fightcamp.calendar_integrity import _stamp_relocation
from fightcamp.combat_load_policy import PlacementDirective
from fightcamp.stage2_validator import _scheduled_role_d_day


def _week() -> dict:
    return {
        "calendar_days": [
            {"weekday": "Monday", "d_day": 20},
            {"weekday": "Tuesday", "d_day": 19},
            {"weekday": "Wednesday", "d_day": 18},
            {"weekday": "Thursday", "d_day": 17},
        ]
    }


def test_stale_countdown_label_does_not_win_after_a_governor_relocation():
    """The real relocation stamp must decide the day, not the field it leaves behind."""
    role = {
        "role_key": "fight_pace_repeatability_day",
        "category": "conditioning",
        "scheduled_day_hint": "Monday",
        "real_weekday": "Monday",
        "countdown_label": "D-20",
        "scheduled_countdown_label": "D-20",
        "countdown_offset": 20,
    }

    _stamp_relocation(
        role,
        weekday="wednesday",
        d_day=18,
        reason_code="between_effective_hard_contacts",
        directive=PlacementDirective.FORBID,
    )

    # The governor refreshes these three and deliberately leaves countdown_label alone.
    assert role["scheduled_countdown_label"] == "D-18"
    assert role["scheduled_d_day"] == 18
    assert role["countdown_offset"] == 18
    assert role["countdown_label"] == "D-20", "stale by design; nothing refreshes it"

    assert _scheduled_role_d_day(_week(), role) == 18


def test_numeric_placement_fields_are_read_when_no_scheduled_label_exists():
    """A relocated role with no fresh label still resolves from scheduled_d_day.

    The old local resolver skipped the numeric fields entirely, so this case fell
    through to the stale label (wrong day) or to None (member never validated).
    """
    role = {
        "category": "conditioning",
        "scheduled_d_day": 18,
        "countdown_label": "D-20",
    }

    assert _scheduled_role_d_day(_week(), role) == 18


def test_countdown_offset_is_read_when_it_is_the_only_placement_signal():
    role = {"category": "conditioning", "countdown_offset": 17}

    assert _scheduled_role_d_day(_week(), role) == 17


def test_weekday_fallback_still_resolves_through_the_week_calendar():
    role = {"category": "conditioning", "scheduled_day_hint": "Tuesday"}

    assert _scheduled_role_d_day(_week(), role) == 19


def test_dayless_role_still_resolves_to_none():
    """Placement leaves a role with no legal day dayless; that must stay unresolved."""
    role = {"category": "conditioning"}

    assert _scheduled_role_d_day(_week(), role) is None


def test_validator_and_canonical_adapter_cannot_fork_again():
    """Guard the delegation itself: the two must agree on every shape above."""
    week = _week()
    roles = [
        {"scheduled_countdown_label": "D-18", "countdown_label": "D-20"},
        {"scheduled_d_day": 18, "countdown_label": "D-20"},
        {"countdown_offset": 17},
        {"scheduled_day_hint": "Tuesday"},
        {"countdown_label": "D-19"},
        {},
    ]

    for role in roles:
        assert _scheduled_role_d_day(week, role) == role_d_day(week, role), role
