from __future__ import annotations

from fightcamp.injury_filtering import infer_tags_from_name


def test_assault_bike_sprint_does_not_infer_running_max_velocity() -> None:
    tags = infer_tags_from_name("Assault Bike Sprint Intervals")

    assert "max_velocity" not in tags
    assert "mech_max_velocity" not in tags


def test_true_running_sprint_keeps_max_velocity_protection() -> None:
    tags = infer_tags_from_name("30m Max Sprint")

    assert "max_velocity" in tags
    assert "mech_max_velocity" in tags
