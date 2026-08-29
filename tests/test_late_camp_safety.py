from fightcamp.late_camp_safety import aggressive_cut_extra_compression


def test_moderate_cut_does_not_add_extra_compression():
    athlete = {"cut_severity_bucket": "moderate", "days_until_fight": 20}
    assert aggressive_cut_extra_compression(athlete) == 0


def test_high_cut_adds_one_late_camp_compression_slot():
    athlete = {"cut_severity_bucket": "high", "days_until_fight": 20}
    assert aggressive_cut_extra_compression(athlete) == 1


def test_high_cut_does_not_change_far_out_architecture():
    athlete = {"cut_severity_bucket": "high", "days_until_fight": 40}
    assert aggressive_cut_extra_compression(athlete) == 0


def test_scheduled_day_can_drive_cut_overlay_independently_of_generation_day():
    athlete = {"cut_severity_bucket": "critical", "days_until_fight": 35}
    assert aggressive_cut_extra_compression(athlete, scheduled_d_day=20) == 1
    assert aggressive_cut_extra_compression(athlete, scheduled_d_day=32) == 0
