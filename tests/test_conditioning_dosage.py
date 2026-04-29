from fightcamp.conditioning_dosage import normalize_conditioning_dose


def test_gpp_aerobic_compatible_bank_dose_is_preserved():
    dose = normalize_conditioning_dose(
        {"name": "Zone 2 Bike", "system": "aerobic", "total_minutes": 20, "rpe": 6, "lactate_load": "low"},
        system="aerobic",
        phase="GPP",
    )

    assert dose["status"] == "prescribed"
    assert dose["source"] == "bank_metadata"
    assert dose["stimulus_preserved"] is True
    assert dose["active_work_minutes"] == 20
    assert dose["elapsed_minutes"] == 20
    assert dose["display"] == "20 min continuous @ RPE 6"


def test_spp_controlled_glycolytic_dose_is_prescribed_when_unconstrained():
    dose = normalize_conditioning_dose(
        {
            "name": "Fight Pace Intervals",
            "system": "glycolytic",
            "work_sec": 60,
            "rest_sec": 60,
            "rounds": 4,
            "rpe": 7,
            "lactate_load": "high",
        },
        system="glycolytic",
        phase="SPP",
        days_until_fight=21,
        fatigue="low",
        cut_bucket="low",
    )

    assert dose["status"] == "prescribed"
    assert dose["stimulus_preserved"] is True
    assert dose["display"] == "4 x 60s / 60s rest @ RPE 7"


def test_d7_dense_glycolytic_is_blocked():
    dose = normalize_conditioning_dose(
        {
            "name": "Dense Fight Pace",
            "system": "glycolytic",
            "work_sec": 60,
            "rest_sec": 30,
            "rounds": 8,
            "rpe": 9,
            "lactate_load": "high",
        },
        system="glycolytic",
        phase="TAPER",
        days_until_fight=7,
    )

    assert dose["status"] == "blocked"
    assert dose["intent_status"] == "violated"
    assert "dose_blocked_glycolytic_tight_window" in dose["dose_reason_codes"]


def test_d4_high_lactate_glycolytic_blocks_instead_of_capping():
    dose = normalize_conditioning_dose(
        {
            "name": "High Lactate Finisher",
            "system": "glycolytic",
            "work_sec": 45,
            "rest_sec": 45,
            "rounds": 4,
            "rpe": 8,
            "lactate_load": "high",
        },
        system="glycolytic",
        phase="TAPER",
        days_until_fight=4,
    )

    assert dose["status"] == "blocked"
    assert dose["applied_caps"] == []
    assert dose["stimulus_preserved"] is False


def test_missing_work_rest_high_lactate_blocks_at_d7():
    dose = normalize_conditioning_dose(
        {"name": "Lactate Builder", "system": "glycolytic", "lactate_load": "high"},
        system="glycolytic",
        phase="TAPER",
        days_until_fight=7,
    )

    assert dose["status"] == "blocked"
    assert "dose_blocked_glycolytic_tight_window" in dose["dose_reason_codes"]


def test_rpe_only_metadata_defaults_to_complete_prescription():
    dose = normalize_conditioning_dose(
        {"name": "Easy Aerobic", "system": "aerobic", "rpe": 5},
        system="aerobic",
        phase="GPP",
    )

    assert dose["status"] == "defaulted"
    assert dose["display"] == "20 min continuous @ RPE 5"


def test_alactic_metadata_conflict_blocks():
    dose = normalize_conditioning_dose(
        {"name": "Mislabelled Alactic", "system": "alactic", "work_sec": 45, "rest_sec": 30, "rounds": 6, "rpe": 8},
        system="alactic",
        phase="SPP",
    )

    assert dose["status"] == "blocked"
    assert "dose_blocked_system_metadata_conflict" in dose["dose_reason_codes"]


def test_high_fatigue_caps_safe_alactic_without_changing_intent():
    dose = normalize_conditioning_dose(
        {"name": "Short Sprint Starts", "system": "alactic", "work_sec": 10, "rest_sec": 90, "rounds": 8, "rpe": 9},
        system="alactic",
        phase="SPP",
        fatigue="high",
    )

    assert dose["status"] == "capped"
    assert dose["rounds"] == 4
    assert dose["rpe"] == 7
    assert dose["stimulus_preserved"] is True
    assert "dose_capped_high_fatigue" in dose["dose_reason_codes"]


def test_active_cut_moderate_fatigue_preserves_aerobic_but_blocks_dense_glycolytic():
    aerobic = normalize_conditioning_dose(
        {"name": "Easy Bike", "system": "aerobic", "total_minutes": 15, "rpe": 6, "lactate_load": "low"},
        system="aerobic",
        phase="SPP",
        fatigue="moderate",
        weight_cut_risk=True,
        cut_bucket="moderate",
    )
    glycolytic = normalize_conditioning_dose(
        {
            "name": "Dense Glycolytic",
            "system": "glycolytic",
            "work_sec": 60,
            "rest_sec": 45,
            "rounds": 5,
            "rpe": 8,
            "lactate_load": "high",
        },
        system="glycolytic",
        phase="SPP",
        fatigue="moderate",
        weight_cut_risk=True,
        cut_bucket="moderate",
    )

    assert aerobic["status"] in {"prescribed", "capped"}
    assert aerobic["stimulus_preserved"] is True
    assert glycolytic["status"] == "blocked"
    assert "dose_blocked_high_lactate_cut_pressure" in glycolytic["dose_reason_codes"]
