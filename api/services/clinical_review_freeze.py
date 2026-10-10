"""Prospective pin/safety overlays; never rewrite started/completed content."""
from copy import deepcopy
from datetime import datetime, timezone
import logging

from api.contracts.clinical_review_validity import FrozenClinicalReviewPin, evaluate_clinical_review, evaluate_frozen_review
from api.contracts.reviewed_prescription import validate_prescription_selection
from api.services.clinical_review_capture_service import hydrate_review_input
from api.contracts.clinical_progression_review import CLINICAL_REVIEW_REGISTRY
from fightcamp.rehab_clinical import content_hash, load_clinical_policies
from fightcamp.exercise_identity import normalize_exercise_key

logger = logging.getLogger(__name__)


def executable_selection_matches(block, option, selection):
    """Executable fields cannot drift from the shared selected-work identity."""
    if "rehab_drill_id" not in block:
        return True  # Non-executable legacy pin projections remain supported.
    dose = selection.dose.model_dump(exclude_none=True)
    return (block.get("rehab_drill_id") == selection.drill_id
        and block.get("bank_hash") == selection.bank_hash
        and content_hash(block.get("drill_snapshot")) == selection.bank_hash
        and block.get("instructions") == option.instructions
        and block.get("coaching_cues") == [option.instructions]
        and block.get("display_name") == block.get("drill_snapshot", {}).get("name")
        and block.get("title") == block.get("drill_snapshot", {}).get("name")
        and block.get("dose") == dose
        and all(block.get(key) == dose.get(key) for key in ("sets", "reps", "duration_seconds"))
        and block.get("range_choice") == selection.range_choice
        and block.get("resistance") == selection.resistance.model_dump(mode="json")
        and block.get("mandatory_restrictions") == list(selection.restrictions)
        and block.get("frequency") == selection.cadence.frequency
        and block.get("minimum_gap_days") == selection.cadence.minimum_gap_days
        and not any(block.get(key) for key in ("load", "weight", "alternates", "exercises",
            "prescription", "duration_minutes", "rest", "rest_seconds", "tempo", "rpe", "intensity"))
        and (not block.get("duration") or "duration_seconds" in dose))


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
    current_registry = registry or CLINICAL_REVIEW_REGISTRY
    gated_drills = {o.drill_id for definition in current_registry._definitions.values() for o in definition.options}
    for block in snapshot.get("session", {}).get("blocks", []):
        if block.get("required_rehabilitation_level") == "loading":
            # A self-report has no verified-clinician pin. Withdraw incompatible
            # future work, while leaving started/completed snapshots intact.
            try:
                from api.services.injury_episode_service import apply_episode_observations, episode_observations, exposure_rows_with_observations
                from api.contracts.injury_policy import reported_load_hold, reported_load_option
                injury = store.get_injury_flag_for_athlete(block["injury_id"], athlete_id)
                if not injury or str(injury.get("episode_id")) != block.get("injury_episode_id"):
                    return True
                observations = episode_observations(store, athlete_id, injury)
                current = apply_episode_observations(injury, observations, as_of=now)
                option = reported_load_option(block.get("policy_id"))
                if option is None:
                    return True
                if work_state == "unstarted":
                    window = store.list_rehab_exposures(athlete_id, injury_id=injury["id"],
                                                       injury_episode_id=injury["episode_id"])
                    if reported_load_hold(block.get("policy_id"), current, as_of=now,
                            exposures=window.rows, history_truncated=window.history_truncated):
                        return True
                if work_state == "unstarted":
                    plan = store.get_plan_for_athlete(snapshot.get("plan_id"), athlete_id) or {}
                    intake = (store.get_intake(plan["intake_id"]) if plan.get("intake_id")
                              else store.get_latest_intake(athlete_id)) or {}
                    if intake.get("athlete_id") != athlete_id:
                        return True
                    intake = intake.get("intake") or intake
                    if not set(block.get("drill_snapshot", {}).get("equipment") or []) <= set(intake.get("equipment_access") or []):
                        return True
                    if block.get("policy_id") in {"elbow_tendonitis", "ankle_sprain"}:
                        from api.contracts.injury_policy import resolve_injury_policy
                        from fightcamp.rehab_protocols import get_rehab_bank
                        decision = resolve_injury_policy(current,
                            policies=policies if policies is not None else load_clinical_policies(),
                            bank=bank if bank is not None else get_rehab_bank(),
                            equipment=intake.get("equipment_access") or [],
                            exposures=exposure_rows_with_observations(window.rows, observations),
                            history_truncated=window.history_truncated, as_of=now)
                        if (decision.get("stage") != "load" or
                                (decision.get("prescription") or {}).get("drill_id") != option.drill_id):
                            return True
                policy = next(p for p in (policies if policies is not None else load_clinical_policies())
                              if p.policy_id == block.get("policy_id"))
                prescription = next(p for p in policy.prescriptions if p.drill_id == block.get("rehab_drill_id"))
                if (prescription.required_rehabilitation_level != "loading"
                        or prescription.drill_id != option.drill_id
                        or prescription.bank_hash != option.bank_hash
                        or block.get("policy_review_hash") != policy.content_hash
                        or block.get("bank_hash") != prescription.bank_hash
                        or normalize_exercise_key(block.get("exercise_key", prescription.drill_id)) != normalize_exercise_key(prescription.drill_id)
                        or block.get("dose") != prescription.dose.model_dump(exclude_none=True)
                        or block.get("instructions") != prescription.instructions
                        or block.get("coaching_cues") != [prescription.instructions]
                        or block.get("mandatory_restrictions") != list(option.mandatory_restrictions)
                        or block.get("title") != block.get("drill_snapshot", {}).get("name")
                        or block.get("display_name") != block.get("drill_snapshot", {}).get("name")
                        or block.get("stop_rules") != prescription.stop_when
                        or block.get("range_choice") != option.range_choices[0]
                        or block.get("resistance") != {"mode": "bodyweight", "kg": None}
                        or block.get("frequency") != "daily" or block.get("minimum_gap_days") != 1
                        or content_hash(block.get("drill_snapshot")) != prescription.bank_hash
                        or any(block.get(name) != getattr(prescription.dose, name) for name in ("sets", "reps", "duration_seconds"))
                        or any(block.get(name) for name in ("load", "weight", "prescription", "alternates", "exercises", "tempo", "rpe", "intensity", "duration_minutes", "rest", "rest_seconds", "duration"))):
                    return True
            except (ValueError, TypeError, KeyError, StopIteration):
                return True
            except Exception as exc:  # noqa: BLE001 - unavailable safety inputs hold future work
                logger.error("reported_permission_work_failed category=%s", type(exc).__name__)
                return True
            continue
        if "clinical_review_pin" not in block:
            if block.get("rehab_drill_id") in gated_drills:
                return True
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
            definition = supplied.registry.current(pin.criterion_id)
            review = next(supplied.registry.parse(value) for value in supplied.reviews
                          if (value.get("review_id") if isinstance(value, dict) else value.review_id) == pin.review_id)
            selection = review.selected_prescription
            option = next(o for o in definition.options if o.option_id == pin.option_id)
            if (block.get("reviewed_prescription") != {"option": option.model_dump(mode="json"),
                    "selection": selection.model_dump(mode="json")}
                    or not executable_selection_matches(block, option, selection)):
                return True
            if block.get("rehab_drill_id"):
                current_policy = next(p for p in (policies if policies is not None else load_clinical_policies())
                                      if p.policy_id == option.profile_id)
                prescription = next(p for p in current_policy.prescriptions if p.drill_id == option.drill_id)
                if (block.get("stop_rules") != prescription.stop_when
                        or prescription.clinical_criterion != pin.criterion_id):
                    return True
        except (ValueError, KeyError, StopIteration):
            logger.info("clinical_review_work_unavailable category=invalid_saved_work")
            return True
        except Exception as exc:  # noqa: BLE001 - unavailable authority holds future work
            logger.error("clinical_review_work_failed category=%s", type(exc).__name__)
            return True
    return False
