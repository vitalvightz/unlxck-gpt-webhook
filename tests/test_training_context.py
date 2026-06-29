from dataclasses import fields

import pytest

from fightcamp.training_context import TrainingContext, allocate_sessions


def test_training_context_has_single_declared_support_day_fields():
    field_names = [item.name for item in fields(TrainingContext)]

    assert field_names.count("training_split") == 1
    assert field_names.count("hard_sparring_days") == 1
    assert field_names.count("support_work_days") == 1
    assert field_names.count("technical_skill_days") == 1


class TestTaperAllocationReallocatedTowardConditioning:
    """Higher-availability taper weeks keep sharpness work ahead of recovery slots."""

    @pytest.mark.parametrize(
        ("freq", "expected"),
        [
            (3, {"strength": 1, "conditioning": 2, "recovery": 1}),
            (4, {"strength": 1, "conditioning": 3, "recovery": 1}),
            (5, {"strength": 1, "conditioning": 4, "recovery": 1}),
            (6, {"strength": 1, "conditioning": 4, "recovery": 1}),
        ],
    )
    def test_reallocated_taper_splits(self, freq, expected):
        assert allocate_sessions(freq, "TAPER") == expected

    @pytest.mark.parametrize("freq", [1, 2, 3, 4, 5, 6])
    def test_taper_totals_add_one_extra_app_session(self, freq):
        assert sum(allocate_sessions(freq, "TAPER").values()) == min(freq + 1, 6)

    @pytest.mark.parametrize("freq", [1, 2])
    def test_low_frequency_taper_gets_extra_slot(self, freq):
        expected = {
            1: {"strength": 0, "conditioning": 1, "recovery": 1},
            2: {"strength": 1, "conditioning": 1, "recovery": 1},
        }[freq]
        assert allocate_sessions(freq, "TAPER") == expected

    @pytest.mark.parametrize(
        ("freq", "phase", "total"),
        [
            (1, "GPP", 2),
            (4, "GPP", 5),
            (1, "SPP", 2),
            (4, "SPP", 5),
        ],
    )
    def test_all_phases_get_one_extra_app_session(self, freq, phase, total):
        assert sum(allocate_sessions(freq, phase).values()) == total
