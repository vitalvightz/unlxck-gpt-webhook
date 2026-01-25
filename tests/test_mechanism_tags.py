from fightcamp.injury_filtering import infer_tags_from_name


def test_infer_mechanism_tags_from_names():
    cases = {
        "Flying Sprint 20m": {"mech_max_velocity"},
        "Hill Sprint Accel Start": {"mech_acceleration", "mech_max_velocity"},
        "Pro Agility Cut Drill": {"mech_change_of_direction"},
        "Depth Drop Land and Stick": {"mech_landing_impact"},
        "Pogo Reactive Rebound Hops": {"mech_reactive_rebound"},
        "Nordic Hamstring Slow Lower": {"mech_hinge_eccentric"},
        "Isometric Deadlift Hold": {"mech_hinge_isometric", "mech_grip_static"},
        "Cossack Lateral Lunge": {"mech_lateral_shift"},
    }

    for name, expected in cases.items():
        inferred = infer_tags_from_name(name)
        missing = expected - inferred
        assert not missing, f"{name} missing mechanism tags: {missing}"
