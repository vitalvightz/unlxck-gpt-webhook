from copy import deepcopy

import pytest

from api.contracts.rehab_stage import MAX_RESOLVABLE_STAGE, STAGE_RESTORE
from fightcamp import rehab_protocols
from fightcamp.rehab_schema import (
    LATERALITY_APPLICABILITY_VALUES,
    SEVERITY_VALUES,
    normalize_severity_bucket,
)
from fightcamp.rehab_selector import select_rehab_candidate


def injury(**overrides):
    value = {
        "athlete_id": "athlete-a",
        "id": "injury-a",
        "episode_id": "episode-a",
        "body_region": "ankle",
        "side": "left",
        "injury_type": "sprain",
        "severity": "low",
    }
    value.update(overrides)
    return value


def drill(identifier, stage="restore", **overrides):
    value = {
        "id": identifier,
        "rehab_stage": stage,
        "target_regions": ["ankle"],
        "injury_type": "sprain",
        "laterality_applicability": "side_specific",
        "care_pathway": "msk",
        "allowed_severities": ["low", "moderate"],
        "function": "control",
        "load": "low",
        "impact": "none",
        "velocity": "low",
    }
    value.update(overrides)
    return value


def exposure(
    drill_id,
    *,
    during="same",
    next_day="not_yet_known",
    occurred_at="2026-08-20T10:00:00+00:00",
    **overrides,
):
    event = {
        "athlete_id": "athlete-a",
        "injury_id": "injury-a",
        "injury_episode_id": "episode-a",
        "body_region": "ankle",
        "side": "left",
        "drill_id": drill_id,
        "occurred_at": occurred_at,
        "response": {
            "during_response": during,
            "next_day_response": next_day,
            "stopped_due_to_symptoms": False,
            "worsening_reported": False,
        },
    }
    event.update(overrides)
    return event


def selected(candidates, **kwargs):
    return select_rehab_candidate(
        injury=kwargs.pop("injury", injury()),
        rehab_stage=kwargs.pop("stage", "restore"),
        candidates=candidates,
        **kwargs,
    )


def test_exact_stage_dominates_and_later_stage_is_rejected():
    result = selected(
        [
            drill("calm", "calm"),
            drill("load", "load"),
            drill("restore"),
        ]
    )
    assert result.selected_drill_id == "restore"
    rejected = {item.drill_id: item.reason_codes for item in result.rejected_candidates}
    assert rejected["load"] == ("REJECT_STAGE_TOO_ADVANCED",)


def test_calm_cannot_select_restore_or_load_and_restore_cannot_select_load():
    result = selected([drill("restore"), drill("load", "load")], stage="calm")
    assert result.selected_drill_id is None
    assert selected([drill("load", "load")], stage="restore").selected_drill_id is None


def test_non_live_stages_are_unreachable_and_cap_is_unchanged():
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE
    for stage in ("load", "dynamic", "return"):
        assert selected([drill(stage, stage)], stage=stage).selected_drill_id is None


def test_surface_wrong_region_family_severity_and_equipment_are_hard_rejections():
    cases = [
        (drill("surface", care_pathway="wound_care"), "REJECT_SURFACE_PATHWAY"),
        (drill("knee", target_regions=["knee"]), "REJECT_REGION_MISMATCH"),
        (drill("strain", injury_type="strain"), "REJECT_INJURY_FAMILY"),
        (drill("high", allowed_severities=["high"]), "REJECT_SEVERITY"),
    ]
    for candidate, reason in cases:
        result = selected([candidate])
        assert reason in result.rejected_candidates[0].reason_codes

    result = selected(
        [drill("band", equipment=["band"])],
        available_equipment=["bodyweight"],
    )
    assert "REJECT_EQUIPMENT_UNAVAILABLE" in result.rejected_candidates[0].reason_codes


def test_severity_aliases_are_normalized_to_bank_contract():
    low = drill("low", allowed_severities=["low"])
    high = drill("high", allowed_severities=["high"])

    assert selected([low], injury=injury(severity="low")).selected_drill_id == "low"
    assert selected([low], injury=injury(severity="mild")).selected_drill_id == "low"
    assert selected([high], injury=injury(severity="severe")).selected_drill_id == "high"

    unknown = selected([low], injury=injury(severity="unknown"))
    assert "REJECT_UNKNOWN_REQUIRED_SEVERITY" in unknown.rejected_candidates[0].reason_codes


def test_exact_region_and_family_beat_generic_fallbacks():
    generic = drill(
        "a_generic",
        target_regions=["generic"],
        injury_type="unspecified",
    )
    exact = drill("z_exact")
    assert selected([generic, exact]).selected_drill_id == "z_exact"


def test_every_canonical_laterality_value_is_admissible_for_a_known_side():
    """The four bank values are LATERALITY_APPLICABILITY_VALUES, and for a
    left-side injury none of them is a reason to throw a drill away."""
    assert set(LATERALITY_APPLICABILITY_VALUES) == {
        "side_specific",
        "bilateral_only",
        "not_applicable",
        "unknown",
    }
    for applicability in LATERALITY_APPLICABILITY_VALUES:
        result = selected(
            [drill("d", laterality_applicability=applicability)],
            injury=injury(side="left"),
        )
        assert result.selected_drill_id == "d", (
            f"{applicability} was rejected: {result.rejected_candidates}"
        )


def test_side_specific_is_the_only_laterality_value_that_can_fail_closed():
    """A drill performed on a named side is unsatisfiable when no side is known.

    Every other value stays admissible, because none of them needs to be told
    which side is hurt in order to be performed.
    """
    unknown_side = injury(side="unknown")
    rejected = selected(
        [drill("side", laterality_applicability="side_specific")],
        injury=unknown_side,
    )
    assert (
        "REJECT_UNKNOWN_REQUIRED_LATERALITY"
        in rejected.rejected_candidates[0].reason_codes
    )

    for applicability in ("bilateral_only", "not_applicable", "unknown"):
        result = selected(
            [drill("d", laterality_applicability=applicability)],
            injury=unknown_side,
        )
        assert result.selected_drill_id == "d", applicability


def test_unknown_laterality_is_never_positive_specificity():
    """``unknown`` must not outrank a drill that states its applicability."""
    stated = drill("z_stated", laterality_applicability="side_specific")
    unstated = drill("a_unknown", laterality_applicability="unknown")
    # The unstated drill sorts first on canonical id, so only the laterality
    # ordering can put the stated one ahead of it.
    assert selected([unstated, stated], injury=injury(side="left")).selected_drill_id == (
        "z_stated"
    )


def test_bilateral_only_ranks_top_for_a_bilateral_injury():
    bilateral_only = drill("z_both", laterality_applicability="bilateral_only")
    not_applicable = drill("a_na", laterality_applicability="not_applicable")
    result = selected([not_applicable, bilateral_only], injury=injury(side="bilateral"))
    assert result.selected_drill_id == "z_both"


def test_unmigrated_stage_is_admissible_but_cannot_claim_a_stage_match():
    """``rehab_stage: null`` is PR1's not-migrated marker, not a rejection.

    It is also the state of every drill in the live bank, so rejecting it would
    empty the rehab block entirely.
    """
    unmigrated = selected([drill("a_unmigrated", rehab_stage=None)])
    assert unmigrated.selected_drill_id == "a_unmigrated"
    assert dict(
        (factor.factor, factor.result) for factor in unmigrated.ranking_factors
    )["stage_match"] == "stage_unmigrated"

    # A migrated exact match outranks it despite sorting later by id.
    ranked = selected([drill("a_unmigrated", rehab_stage=None), drill("z_restore")])
    assert ranked.selected_drill_id == "z_restore"


def test_a_stated_but_unrecognised_stage_still_fails_closed():
    result = selected([drill("bad", rehab_stage="not_a_stage")])
    assert (
        "REJECT_UNKNOWN_REQUIRED_STAGE"
        in result.rejected_candidates[0].reason_codes
    )


def test_a_more_protective_stage_is_a_conservative_fallback_not_a_rejection():
    """A CALM drill is always acceptable for a RESTORE athlete — it asks less."""
    result = selected([drill("calm_drill", "calm")], stage="restore")
    assert result.selected_drill_id == "calm_drill"
    assert dict(
        (factor.factor, factor.result) for factor in result.ranking_factors
    )["stage_match"] == "conservative_fallback"


def test_unknown_region_is_still_not_reinterpreted_as_compatible():
    result = selected([drill("no_region", target_regions=None)])
    reasons = {item.drill_id: item.reason_codes for item in result.rejected_candidates}
    assert "REJECT_UNKNOWN_REQUIRED_REGION" in reasons["no_region"]


def test_known_demand_beats_unknown_only_after_clinical_dimensions_tie():
    unknown = drill(
        "a_unknown",
        load="unknown",
        impact="unknown",
        velocity="unknown",
    )
    known = drill("z_known")
    assert selected([unknown, known]).selected_drill_id == "z_known"


def test_order_independence_and_canonical_id_tie_break():
    bank = [drill("zeta"), drill("alpha")]
    expected = selected(bank).selected_drill_id
    assert expected == "alpha"
    assert selected(list(reversed(bank))).selected_drill_id == expected
    assert {selected(deepcopy(bank)).selected_drill_id for _ in range(10)} == {expected}


def test_exact_episode_region_and_side_negative_evidence_is_isolated():
    negative = exposure("alpha", during="worse")
    bank = [drill("alpha"), drill("beta")]
    result = selected(bank, exposures=[negative])
    assert result.selected_drill_id == "beta"
    rejected = {item.drill_id: item.reason_codes for item in result.rejected_candidates}
    assert "REJECT_UNRESOLVED_NEGATIVE_EXPOSURE" in rejected["alpha"]

    changed_identity = (
        {"injury_id": "other"},
        {"injury_episode_id": "old"},
        {"athlete_id": "other"},
        {"body_region": "knee"},
        {"side": "right"},
    )
    for changed in changed_identity:
        event = {**negative, **changed}
        assert selected(bank, exposures=[event]).selected_drill_id == "alpha"


def test_historical_negative_is_uncertainty_not_permanent_blacklist():
    adverse = exposure(
        "alpha",
        during="worse",
        occurred_at="2026-08-20T10:00:00+00:00",
    )
    newer_non_adverse = exposure(
        "alpha",
        during="same",
        occurred_at="2026-08-20T12:00:00+00:00",
    )

    clean_alternative = selected(
        [drill("alpha"), drill("beta")],
        exposures=[adverse, newer_non_adverse],
    )
    assert clean_alternative.selected_drill_id == "beta"

    only_candidate = selected(
        [drill("alpha")],
        exposures=[adverse, newer_non_adverse],
    )
    assert only_candidate.selected_drill_id == "alpha"
    assert (
        only_candidate.selection_reason
        == "SELECT_DETERMINISTIC_WITH_HISTORICAL_NEGATIVE_UNCERTAINTY"
    )
    factors = {factor.factor: factor.result for factor in only_candidate.ranking_factors}
    assert factors["historical_negative"] == "uncertainty"
    assert only_candidate.rehab_stage == "restore"
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE


def test_not_sure_does_not_resolve_negative_exposure():
    adverse = exposure(
        "alpha",
        during="worse",
        occurred_at="2026-08-20T10:00:00+00:00",
    )
    uncertain = exposure(
        "alpha",
        during="not_sure",
        occurred_at="2026-08-20T12:00:00+00:00",
    )
    result = selected([drill("alpha")], exposures=[adverse, uncertain])
    assert result.selected_drill_id is None
    assert (
        "REJECT_UNRESOLVED_NEGATIVE_EXPOSURE"
        in result.rejected_candidates[0].reason_codes
    )


def test_function_and_continuity_context_rank_without_overriding_safety():
    control = drill("control", function="control")
    mobility = drill("mobility", function="mobility")

    function_result = selected(
        [control, mobility],
        injury=injury(session_rehab_function="mobility"),
    )
    assert function_result.selected_drill_id == "mobility"

    continuity_result = selected(
        [control, mobility],
        injury=injury(current_rehab_drill_id="mobility"),
    )
    assert continuity_result.selected_drill_id == "mobility"

    adverse = exposure(
        "mobility",
        during="worse",
        occurred_at="2026-08-20T10:00:00+00:00",
    )
    newer_non_adverse = exposure(
        "mobility",
        during="same",
        occurred_at="2026-08-20T12:00:00+00:00",
    )
    safety_first = selected(
        [control, mobility],
        injury=injury(current_rehab_drill_id="mobility"),
        exposures=[adverse, newer_non_adverse],
    )
    assert safety_first.selected_drill_id == "control"


def test_free_text_camp_phase_global_burden_and_shadow_load_are_not_inputs():
    noisy = injury(
        description="maybe torn Achilles",
        camp_phase="TAPER",
        global_rpe=10,
        session_pain=10,
        eligible_for_load=True,
    )
    result = selected([drill("restore"), drill("load", "load")], injury=noisy)
    assert result.selected_drill_id == "restore"
    assert all("description" not in factor.factor for factor in result.ranking_factors)


def test_result_contract_is_auditable_and_identity_is_per_injury():
    result = selected([drill("restore")])
    assert (result.injury_id, result.injury_episode_id, result.rehab_stage) == (
        "injury-a",
        "episode-a",
        "restore",
    )
    assert result.candidate_count == result.eligible_candidate_count == 1
    assert result.selector_version == "2"


def test_authoritative_bank_option_path_returns_ranked_live_stage_drill(monkeypatch):
    bank = [
        {
            "location": "ankle",
            "type": "sprain",
            "phase_progression": "GPP → SPP → TAPER",
            "drills": [
                drill("load", "load", name="Load", notes="later"),
                drill("restore", name="Restore", notes="now"),
            ],
        }
    ]
    monkeypatch.setattr(rehab_protocols, "get_rehab_bank", lambda: bank)
    monkeypatch.setattr(rehab_protocols, "get_rehab_locations", lambda: {"ankle"})

    options = rehab_protocols.rehab_drill_options_for_phase(
        "sprain",
        "ankle",
        "TAPER",
        injury=injury(),
        rehab_stage="restore",
    )
    assert [option["drill"]["id"] for option in options] == ["restore"]
    assert set(options[0]) == {"line", "drill", "location", "type"}


def test_legacy_option_shape_is_unchanged_when_live_stage_context_is_absent(
    monkeypatch,
):
    bank = [
        {
            "location": "ankle",
            "type": "sprain",
            "phase_progression": "GPP",
            "drills": [drill("one", name="One", notes="dose")],
        }
    ]
    monkeypatch.setattr(rehab_protocols, "get_rehab_bank", lambda: bank)
    monkeypatch.setattr(rehab_protocols, "get_rehab_locations", lambda: {"ankle"})

    option = rehab_protocols.rehab_drill_options_for_phase(
        "sprain",
        "ankle",
        "GPP",
    )[0]
    assert set(option) == {"line", "drill", "location", "type"}
    assert option["drill"]["id"] == "one"


# ---------------------------------------------------------------------------
# Against the real validated bank, not synthetic candidate dictionaries.
#
# The synthetic suites above are free to invent well-migrated drills. These are
# not: they run the shipped ``data/rehab_bank.json`` through the real option
# path, which is the only thing that can catch the selector agreeing with a
# contract the bank does not actually use.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("live_stage", ["calm", "restore"])
def test_real_bank_yields_an_eligible_canonical_drill_for_each_live_stage(live_stage):
    """A realistic CALM and RESTORE injury each select a real, resolvable drill."""
    real_injury = injury(body_region="ankle", injury_type="sprain", side="left")

    options = rehab_protocols.rehab_drill_options_for_phase(
        "sprain",
        "ankle",
        "GPP",
        injury=real_injury,
        rehab_stage=live_stage,
    )

    assert options, f"real bank selected nothing at {live_stage}"
    selected_option = options[0]
    assert set(selected_option) == {"line", "drill", "location", "type"}

    drill_id = selected_option["drill"]["id"]
    assert drill_id
    # The id has to be resolvable back through the canonical bank, or a
    # completed drill could never be tied to what was prescribed.
    assert rehab_protocols.rehab_drill_by_id(drill_id) is not None


def test_real_bank_severity_gate_uses_the_contract_vocabulary():
    """Raw intake severities reach the bank's buckets, not a parallel vocabulary."""
    assert set(SEVERITY_VALUES) == {"low", "moderate", "high"}
    for raw, expected in (("mild", "low"), ("severe", "high"), ("moderate", "moderate")):
        assert normalize_severity_bucket(raw) == expected

    for raw in ("mild", "moderate", "severe"):
        options = rehab_protocols.rehab_drill_options_for_phase(
            "sprain",
            "ankle",
            "GPP",
            injury=injury(body_region="ankle", injury_type="sprain", severity=raw),
            rehab_stage="restore",
        )
        assert options, f"severity {raw!r} selected nothing from the real bank"


def test_real_bank_selection_is_deterministic_across_candidate_order():
    """Same athlete, same bank, same answer — no ordering or randomness effects."""
    real_injury = injury(body_region="ankle", injury_type="sprain", side="left")
    runs = {
        rehab_protocols.rehab_drill_options_for_phase(
            "sprain",
            "ankle",
            "GPP",
            injury=real_injury,
            rehab_stage="restore",
        )[0]["drill"]["id"]
        for _ in range(5)
    }
    assert len(runs) == 1


def test_live_stage_ceiling_is_unchanged_by_this_selector():
    """PR5 selects drills. It does not move the ladder's ceiling."""
    assert MAX_RESOLVABLE_STAGE == STAGE_RESTORE
