from fightcamp.weight_cut import compute_weight_cut_pct, parse_weight_value


def test_compute_weight_cut_pct_uses_current_body_mass_denominator():
    # 102 -> 98 is 3.9% of current body mass (not ~7%).
    assert compute_weight_cut_pct(102, 98) == 3.9


def test_parse_weight_value_handles_unit_suffixes():
    assert parse_weight_value("102 kg") == 102.0
    assert parse_weight_value("98.5kg") == 98.5
