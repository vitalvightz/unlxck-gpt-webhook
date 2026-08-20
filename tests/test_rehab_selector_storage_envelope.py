from fightcamp.rehab_selector import select_rehab_candidate


def _injury() -> dict[str, object]:
    return {
        "athlete_id": "athlete-a",
        "id": "injury-a",
        "episode_id": "episode-a",
        "body_region": "ankle",
        "side": "left",
        "injury_type": "sprain",
        "severity": "low",
    }


def _drill(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
        "rehab_stage": "restore",
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


def test_persisted_event_json_keeps_storage_envelope_identity_for_adverse_evidence():
    stored = {
        "id": "row-a",
        "athlete_id": "athlete-a",
        "injury_id": "injury-a",
        "injury_episode_id": "episode-a",
        "body_region": "ankle",
        "side": "left",
        "drill_id": "alpha",
        "occurred_at": "2026-08-20T10:00:00+00:00",
        "event_json": {
            "injury_id": "injury-a",
            "injury_episode_id": "episode-a",
            "body_region": "ankle",
            "side": "left",
            "drill_id": "alpha",
            "occurred_at": "2026-08-20T10:00:00+00:00",
            "response": {
                "during_response": "worse",
                "next_day_response": "not_yet_known",
                "stopped_due_to_symptoms": False,
                "worsening_reported": False,
            },
        },
    }

    result = select_rehab_candidate(
        injury=_injury(),
        rehab_stage="restore",
        candidates=[_drill("alpha"), _drill("beta")],
        exposures=[stored],
    )

    assert result.selected_drill_id == "beta"
    rejected = {
        item.drill_id: item.reason_codes for item in result.rejected_candidates
    }
    assert "REJECT_UNRESOLVED_NEGATIVE_EXPOSURE" in rejected["alpha"]


def test_storage_envelope_athlete_mismatch_cannot_penalise_current_athlete():
    stored = {
        "id": "row-other",
        "athlete_id": "athlete-b",
        "injury_id": "injury-a",
        "injury_episode_id": "episode-a",
        "body_region": "ankle",
        "side": "left",
        "drill_id": "alpha",
        "occurred_at": "2026-08-20T10:00:00+00:00",
        "event_json": {
            "injury_id": "injury-a",
            "injury_episode_id": "episode-a",
            "body_region": "ankle",
            "side": "left",
            "drill_id": "alpha",
            "occurred_at": "2026-08-20T10:00:00+00:00",
            "response": {
                "during_response": "worse",
                "next_day_response": "not_yet_known",
                "stopped_due_to_symptoms": False,
                "worsening_reported": False,
            },
        },
    }

    result = select_rehab_candidate(
        injury=_injury(),
        rehab_stage="restore",
        candidates=[_drill("alpha"), _drill("beta")],
        exposures=[stored],
    )

    assert result.selected_drill_id == "alpha"
