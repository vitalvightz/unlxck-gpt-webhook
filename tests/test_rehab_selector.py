from copy import deepcopy

from api.contracts.rehab_stage import MAX_RESOLVABLE_STAGE, STAGE_RESTORE
from fightcamp.rehab_selector import select_rehab_candidate
from fightcamp import rehab_protocols


def injury(**overrides):
    value = {
        "athlete_id": "athlete-a", "id": "injury-a", "episode_id": "episode-a",
        "body_region": "ankle", "side": "left", "injury_type": "sprain", "severity": "mild",
    }
    value.update(overrides)
    return value


def drill(identifier, stage="restore", **overrides):
    value = {
        "id": identifier, "rehab_stage": stage, "target_regions": ["ankle"],
        "injury_type": "sprain", "laterality_applicability": "any", "care_pathway": "msk",
        "allowed_severities": ["mild", "moderate"], "load": "low", "impact": "none", "velocity": "low",
    }
    value.update(overrides)
    return value


def selected(candidates, **kwargs):
    return select_rehab_candidate(injury=kwargs.pop("injury", injury()), rehab_stage=kwargs.pop("stage", "restore"), candidates=candidates, **kwargs)


def test_exact_stage_dominates_and_later_stage_is_rejected():
    result = selected([drill("calm", "calm"), drill("load", "load"), drill("restore")])
    assert result.selected_drill_id == "restore"
    assert dict((r.drill_id, r.reason_codes) for r in result.rejected_candidates)["load"] == ("REJECT_STAGE_TOO_ADVANCED",)


def test_calm_cannot_select_restore_or_load_and_restore_cannot_select_load():
    assert selected([drill("restore"), drill("load", "load")], stage="calm").selected_drill_id is None
    assert selected([drill("load", "load")], stage="restore").selected_drill_id is None


def test_non_live_stages_are_unreachable_and_cap_is_unchanged():
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE
    for stage in ("load", "dynamic", "return"):
        assert selected([drill(stage, stage)], stage=stage).selected_drill_id is None


def test_surface_wrong_region_family_severity_and_equipment_are_hard_rejections():
    cases = [
        (drill("surface", care_pathway="surface"), "REJECT_SURFACE_PATHWAY"),
        (drill("knee", target_regions=["knee"]), "REJECT_REGION_MISMATCH"),
        (drill("strain", injury_type="strain"), "REJECT_INJURY_FAMILY"),
        (drill("severe", allowed_severities=["severe"]), "REJECT_SEVERITY"),
    ]
    for candidate, reason in cases:
        result = selected([candidate])
        assert reason in result.rejected_candidates[0].reason_codes
    result = selected([drill("band", equipment=["band"])], available_equipment=["bodyweight"])
    assert "REJECT_EQUIPMENT_UNAVAILABLE" in result.rejected_candidates[0].reason_codes


def test_exact_region_and_family_beat_generic_fallbacks():
    generic = drill("a_generic", target_regions=["generic"], injury_type="unspecified")
    exact = drill("z_exact")
    assert selected([generic, exact]).selected_drill_id == "z_exact"


def test_laterality_specificity_and_unknown_injury_side_fail_closed_when_required():
    assert selected([drill("left", laterality_applicability="left"), drill("any")]).selected_drill_id == "left"
    unknown = injury(side="unknown")
    result = selected([drill("left", laterality_applicability="left")], injury=unknown)
    assert "REJECT_LATERALITY_MISMATCH" in result.rejected_candidates[0].reason_codes
    bilateral = selected([drill("both", laterality_applicability="bilateral")], injury=injury(side="bilateral"))
    assert bilateral.selected_drill_id == "both"


def test_unknown_stage_and_region_are_not_reinterpreted_as_compatible():
    result = selected([drill("unknown", rehab_stage=None), drill("no_region", target_regions=None)])
    reasons = {item.drill_id: item.reason_codes for item in result.rejected_candidates}
    assert "REJECT_UNKNOWN_REQUIRED_STAGE" in reasons["unknown"]
    assert "REJECT_UNKNOWN_REQUIRED_REGION" in reasons["no_region"]


def test_known_demand_beats_unknown_only_after_clinical_dimensions_tie():
    unknown = drill("a_unknown", load="unknown", impact="unknown", velocity="unknown")
    known = drill("z_known")
    assert selected([unknown, known]).selected_drill_id == "z_known"


def test_order_independence_and_canonical_id_tie_break():
    bank = [drill("zeta"), drill("alpha")]
    expected = selected(bank).selected_drill_id
    assert expected == "alpha"
    assert selected(list(reversed(bank))).selected_drill_id == expected
    assert {selected(deepcopy(bank)).selected_drill_id for _ in range(10)} == {expected}


def test_exact_episode_negative_excludes_drill_but_unrelated_evidence_has_no_effect():
    negative = {
        "athlete_id": "athlete-a", "injury_id": "injury-a", "injury_episode_id": "episode-a",
        "drill_id": "alpha", "response": {"during_response": "worse"},
    }
    bank = [drill("alpha"), drill("beta")]
    assert selected(bank, exposures=[negative]).selected_drill_id == "beta"
    for changed in (
        {"injury_id": "other"}, {"injury_episode_id": "old"}, {"athlete_id": "other"},
    ):
        event = {**negative, **changed}
        assert selected(bank, exposures=[event]).selected_drill_id == "alpha"


def test_free_text_camp_phase_session_burden_and_shadow_load_fields_are_not_inputs():
    noisy = injury(description="maybe torn Achilles", camp_phase="TAPER", global_rpe=10, session_pain=10, eligible_for_load=True)
    result = selected([drill("restore"), drill("load", "load")], injury=noisy)
    assert result.selected_drill_id == "restore"
    assert all("description" not in factor.factor for factor in result.ranking_factors)


def test_result_contract_is_auditable_and_identity_is_per_injury():
    result = selected([drill("restore")])
    assert (result.injury_id, result.injury_episode_id, result.rehab_stage) == ("injury-a", "episode-a", "restore")
    assert result.candidate_count == result.eligible_candidate_count == 1
    assert result.selector_version == "1"


def test_authoritative_bank_option_path_returns_only_ranked_live_stage_drill(monkeypatch):
    bank = [{
        "location": "ankle", "type": "sprain", "phase_progression": "GPP → SPP → TAPER",
        "drills": [drill("load", "load", name="Load", notes="later"), drill("restore", name="Restore", notes="now")],
    }]
    monkeypatch.setattr(rehab_protocols, "get_rehab_bank", lambda: bank)
    monkeypatch.setattr(rehab_protocols, "get_rehab_locations", lambda: {"ankle"})
    options = rehab_protocols.rehab_drill_options_for_phase(
        "sprain", "ankle", "TAPER", injury=injury(), rehab_stage="restore"
    )
    assert [option["drill"]["id"] for option in options] == ["restore"]


def test_legacy_option_shape_is_unchanged_when_live_stage_context_is_absent(monkeypatch):
    bank = [{
        "location": "ankle", "type": "sprain", "phase_progression": "GPP",
        "drills": [drill("one", name="One", notes="dose")],
    }]
    monkeypatch.setattr(rehab_protocols, "get_rehab_bank", lambda: bank)
    monkeypatch.setattr(rehab_protocols, "get_rehab_locations", lambda: {"ankle"})
    option = rehab_protocols.rehab_drill_options_for_phase("sprain", "ankle", "GPP")[0]
    assert set(option) == {"line", "drill", "location", "type"}
    assert option["drill"]["id"] == "one"
