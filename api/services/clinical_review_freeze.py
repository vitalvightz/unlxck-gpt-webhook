"""Prospective pin/safety overlays; never rewrite started/completed content."""
from copy import deepcopy
from datetime import datetime, timezone

from api.contracts.clinical_review_validity import FrozenClinicalReviewPin, evaluate_clinical_review, evaluate_frozen_review
from api.contracts.reviewed_prescription import validate_prescription_selection
from api.services.clinical_review_capture_service import hydrate_review_input


def pin_reviewed_work(block, evaluation, *, option, selection):
    if evaluation.pin is None or not evaluate_frozen_review(evaluation.pin, evaluation,
            work_state="unstarted", as_of=evaluation.evaluated_at).can_accept:
        raise ValueError("only valid matching reviewed work can be pinned")
    validated = validate_prescription_selection(selection, option, profile_id=option.profile_id,
        criterion_id=evaluation.pin.criterion_id, criterion_version=evaluation.pin.criterion_version,
        transition=option.transition, current_bank_hash=selection.bank_hash)
    if not validated.valid or selection.materialised_prescription_hash != evaluation.pin.materialised_prescription_hash:
        raise ValueError("pinned content must match the validated reviewed selection")
    return {**deepcopy(block), "clinical_review_pin": evaluation.pin.model_dump(mode="json"),
            "reviewed_prescription": {"option":option.model_dump(mode="json"), "selection":selection.model_dump(mode="json")}}


def frozen_review_hold(store, athlete_id, snapshot, *, work_state, as_of=None, registry=None, policies=None, bank=None):
    if work_state == "completed":
        return False
    now = as_of or datetime.now(timezone.utc)
    for block in snapshot.get("session", {}).get("blocks", []):
        if "clinical_review_pin" not in block:
            continue
        try:
            pin = FrozenClinicalReviewPin.model_validate(block["clinical_review_pin"])
            state = store.get_clinical_review_capture_context(athlete_id, block["injury_id"], block["injury_episode_id"])
            kwargs = dict(policies=policies, bank=bank)
            if registry is not None:
                kwargs["registry"] = registry
            supplied = hydrate_review_input(state, criterion_id=pin.criterion_id, criterion_version=pin.criterion_version,
                                            as_of=now, **kwargs)
            evaluation = evaluate_clinical_review(supplied.context, supplied.reviews, as_of=now,
                lifecycle=supplied.lifecycle, registry=supplied.registry, trust=supplied.trust)
            if evaluate_frozen_review(pin, evaluation, work_state=work_state, as_of=now).safety_hold:
                return True
        except Exception:  # noqa: BLE001 - unavailable/malformed authority holds future work
            return True
    return False
