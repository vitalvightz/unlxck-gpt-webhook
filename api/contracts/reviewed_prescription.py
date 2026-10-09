"""Bounded individual selections; registration does not schedule executable work."""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fightcamp.rehab_clinical import content_hash
from fightcamp.rehab_pathways import TRANSITION_STAGES

Identifier = Annotated[str, Field(strict=True, min_length=1, pattern=r"^\S(?:.*\S)?$")]
Digest = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
Version = Annotated[int, Field(strict=True, ge=1)]


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ReviewTransition(ReviewModel):
    from_stage: Literal["restore", "load", "dynamic"]
    to_stage: Literal["load", "dynamic", "return"]

    @model_validator(mode="after")
    def consecutive(self):
        if (self.from_stage, self.to_stage) not in TRANSITION_STAGES:
            raise ValueError("review must bind one consecutive higher-stage transition")
        return self


class ReviewedDose(ReviewModel):
    sets: int = Field(strict=True, gt=0)
    reps: int | None = Field(default=None, strict=True, gt=0)
    duration_seconds: float | None = Field(default=None, strict=True, gt=0)

    @model_validator(mode="after")
    def measurable(self):
        if self.reps is None and self.duration_seconds is None:
            raise ValueError("reviewed dose requires reps or duration")
        return self


class ReviewedCadence(ReviewModel):
    frequency: Literal["daily", "scheduled_sessions"]
    minimum_gap_days: int = Field(strict=True, ge=1, le=14)


class ResistanceRule(ReviewModel):
    mode: Literal["bodyweight", "external_kg"]
    minimum_kg: float | None = Field(default=None, strict=True, ge=0)
    maximum_kg: float | None = Field(default=None, strict=True, ge=0)

    @model_validator(mode="after")
    def bounds(self):
        if self.mode == "bodyweight":
            if self.minimum_kg is not None or self.maximum_kg is not None:
                raise ValueError("bodyweight cannot carry external load bounds")
        elif self.minimum_kg is None or self.maximum_kg is None or self.minimum_kg > self.maximum_kg:
            raise ValueError("external resistance requires explicit reviewed bounds")
        return self


class SelectedResistance(ReviewModel):
    mode: Literal["bodyweight", "external_kg"]
    kg: float | None = Field(default=None, strict=True, ge=0)

    @model_validator(mode="after")
    def units(self):
        if (self.mode == "external_kg") != (self.kg is not None):
            raise ValueError("kg belongs only to external resistance")
        return self


class ReviewedPrescriptionOption(ReviewModel):
    option_id: Identifier
    option_version: Version
    profile_id: Identifier
    criterion_id: Identifier
    criterion_version: Version
    transition: ReviewTransition
    drill_id: Identifier
    bank_hash: Digest  # The existing bank has content hashes, not numeric versions.
    instructions: Identifier
    range_choices: tuple[Identifier, ...] = Field(min_length=1)
    resistance_rules: tuple[ResistanceRule, ...] = Field(min_length=1)
    dose_choices: tuple[ReviewedDose, ...] = Field(min_length=1)
    cadence_choices: tuple[ReviewedCadence, ...] = Field(min_length=1)
    mandatory_restrictions: tuple[Identifier, ...] = Field(min_length=1)
    allowed_restrictions: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unambiguous(self):
        choices = (self.range_choices, self.dose_choices, self.cadence_choices,
                   self.mandatory_restrictions, self.allowed_restrictions)
        if any(len(set(values)) != len(values) for values in choices):
            raise ValueError("duplicate option choices")
        if len({r.mode for r in self.resistance_rules}) != len(self.resistance_rules):
            raise ValueError("one reviewed bound per resistance mode")
        if not set(self.mandatory_restrictions) <= set(self.allowed_restrictions):
            raise ValueError("mandatory restrictions must be allowed")
        return self

    @property
    def option_hash(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class ReviewedPrescriptionSelection(ReviewModel):
    selection_version: Version = 1
    option_id: Identifier
    option_version: Version
    option_hash: Digest
    drill_id: Identifier
    bank_hash: Digest
    range_choice: Identifier
    resistance: SelectedResistance
    dose: ReviewedDose
    cadence: ReviewedCadence
    restrictions: tuple[Identifier, ...] = Field(min_length=1)
    materialised_prescription_hash: Digest

    @model_validator(mode="after")
    def canonical_restrictions(self):
        if tuple(sorted(set(self.restrictions))) != self.restrictions:
            raise ValueError("selection restrictions must be unique and sorted")
        return self


class PrescriptionReason(str, Enum):
    MALFORMED = "review_selection_or_option_malformed"
    OPTION_MISSING = "review_option_missing"
    OPTION_BINDING = "review_option_binding_mismatch"
    OPTION_CHANGED = "review_option_version_or_hash_changed"
    DRILL_CHANGED = "review_drill_identity_or_hash_changed"
    RANGE = "review_range_not_allowed"
    RESISTANCE = "review_resistance_not_allowed"
    DOSE = "review_dose_not_allowed"
    CADENCE = "review_cadence_not_allowed"
    RESTRICTIONS = "review_restrictions_not_preserved"
    MATERIALISATION = "review_materialised_hash_or_version_mismatch"


class PrescriptionValidation(ReviewModel):
    valid: bool
    reason_codes: tuple[PrescriptionReason, ...]


def materialised_selection_hash(option: ReviewedPrescriptionOption, selection: ReviewedPrescriptionSelection) -> str:
    """Integrity of executable selected work, including fixed reviewed mechanics.

    Hashing does not grant trust or permission to execute. This is not persistence.
    """
    raw = selection.model_dump(mode="json", exclude={"materialised_prescription_hash"})
    return content_hash({"selection": raw, "option": option.model_dump(mode="json")})


def validate_prescription_selection(selection: ReviewedPrescriptionSelection,
                                    option: ReviewedPrescriptionOption | None, *,
                                    profile_id: str, criterion_id: str, criterion_version: int,
                                    transition: ReviewTransition, current_bank_hash: str | None) -> PrescriptionValidation:
    """Pure checks against a registered option and the caller's replay bank snapshot."""
    if option is None:
        return PrescriptionValidation(valid=False, reason_codes=(PrescriptionReason.OPTION_MISSING,))
    try:
        # JSON serialisation can normalise a copied bool into an integer field.
        # Recheck original Python values before computing any content digest.
        selection = ReviewedPrescriptionSelection.model_validate(selection.model_dump(mode="python"))
        option = ReviewedPrescriptionOption.model_validate(option.model_dump(mode="python"))
    except (ValueError, TypeError, AttributeError):
        return PrescriptionValidation(valid=False, reason_codes=(PrescriptionReason.MALFORMED,))
    reasons = []
    if (option.profile_id, option.criterion_id, option.criterion_version, option.transition) != (
            profile_id, criterion_id, criterion_version, transition):
        reasons.append(PrescriptionReason.OPTION_BINDING)
    if (selection.option_id, selection.option_version, selection.option_hash) != (
            option.option_id, option.option_version, option.option_hash):
        reasons.append(PrescriptionReason.OPTION_CHANGED)
    if (selection.drill_id, selection.bank_hash) != (option.drill_id, option.bank_hash) or current_bank_hash != option.bank_hash:
        reasons.append(PrescriptionReason.DRILL_CHANGED)
    if selection.range_choice not in option.range_choices:
        reasons.append(PrescriptionReason.RANGE)
    rule = next((r for r in option.resistance_rules if r.mode == selection.resistance.mode), None)
    if rule is None or (rule.mode == "external_kg" and not rule.minimum_kg <= selection.resistance.kg <= rule.maximum_kg):
        reasons.append(PrescriptionReason.RESISTANCE)
    if selection.dose not in option.dose_choices:
        reasons.append(PrescriptionReason.DOSE)
    if selection.cadence not in option.cadence_choices:
        reasons.append(PrescriptionReason.CADENCE)
    if (not set(option.mandatory_restrictions) <= set(selection.restrictions)
            or not set(selection.restrictions) <= set(option.allowed_restrictions)):
        reasons.append(PrescriptionReason.RESTRICTIONS)
    if selection.selection_version != 1 or selection.materialised_prescription_hash != materialised_selection_hash(option, selection):
        reasons.append(PrescriptionReason.MATERIALISATION)
    return PrescriptionValidation(valid=not reasons, reason_codes=tuple(reasons))
