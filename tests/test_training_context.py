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
            (3, {"strength": 1, "conditioning": 1, "recovery": 1}),
            (4, {"strength": 1, "conditioning": 1, "recovery": 2}),
            (5, {"strength": 1, "conditioning": 2, "recovery": 2}),
            (6, {"strength": 1, "conditioning": 2, "recovery": 3}),
        ],
    )
    def test_reallocated_taper_splits(self, freq, expected):
        assert allocate_sessions(freq, "TAPER") == expected

    @pytest.mark.parametrize("freq", [1, 2, 3, 4, 5, 6])
    def test_taper_totals_still_sum_to_frequency(self, freq):
        assert sum(allocate_sessions(freq, "TAPER").values()) == freq

    @pytest.mark.parametrize("freq", [1, 2])
    def test_low_frequency_taper_unchanged(self, freq):
        expected = {
            1: {"strength": 0, "conditioning": 1, "recovery": 0},
            2: {"strength": 0, "conditioning": 1, "recovery": 1},
        }[freq]
        assert allocate_sessions(freq, "TAPER") == expected

    @pytest.mark.parametrize(
        ("freq", "phase", "total"),
        [
            (1, "GPP", 1),
            (4, "GPP", 4),
            (1, "SPP", 1),
            (4, "SPP", 4),
        ],
    )
    def test_all_phases_respect_selected_frequency(self, freq, phase, total):
        assert sum(allocate_sessions(freq, phase).values()) == total
