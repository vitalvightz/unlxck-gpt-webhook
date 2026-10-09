"""Calm-stage guidance prompts keep their wording wherever they are rehydrated."""
from api.services.rehab_completion_service import _prompt_from_context, prompts_as_payload

INJURY = {"id": "injury-1", "episode_id": "episode-1", "body_region": "chest", "side": "unknown"}


def _payload(*drill_ids: str) -> dict:
    context = {"injury_id": "injury-1", "injury_episode_id": "episode-1",
               "expected_exposures": [{"drill_id": drill_id} for drill_id in drill_ids]}
    return prompts_as_payload([_prompt_from_context(context, INJURY)])[0]


def test_calm_recovery_support_prompt_asks_about_the_guidance():
    payload = _payload("chest_strain_recovery_support")
    assert payload["guidance_only"] is True
    assert payload["during_question"] == "How did it feel while following the guidance?"
    assert payload["limit_question"] == "Did it make you ease off or stop anything?"


def test_exercise_prompt_keeps_rehab_work_wording():
    payload = _payload("ankle_sprain_heel_lowering")
    assert payload["guidance_only"] is False
    assert payload["during_question"] == "How did it feel during the rehab work?"


def test_mixed_guidance_and_exercise_is_asked_as_rehab_work():
    payload = _payload("chest_strain_recovery_support", "ankle_sprain_heel_lowering")
    assert payload["guidance_only"] is False
