"""Strict factual admin transport; authority fields belong to the server."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .clinical_progression_review import ReviewDecision
from .reviewed_prescription import (
    Digest, Identifier, ReviewModel, ReviewedCadence, ReviewedDose, SelectedResistance, Version,
)


class ReviewSelectionRequest(ReviewModel):
    option_id: Identifier
    option_version: Version
    range_choice: Identifier
    resistance: SelectedResistance
    dose: ReviewedDose
    cadence: ReviewedCadence
    restrictions: tuple[Identifier, ...] = Field(min_length=1)


class ConfirmedClinicalStatement(ReviewModel):
    author_reference: Identifier
    author_display_name: Identifier
    qualification_reference: Identifier
    clinical_scope: Identifier
    statement_reference: Identifier
    statement_text: str = Field(strict=True, min_length=1, max_length=20000)
    confirmation_reference: Identifier
    reviewed_at: AwareDatetime
    confirmed_at: AwareDatetime
    reviewed_packet_revision: Digest
    decision: ReviewDecision
    interpretation: dict
    selection: ReviewSelectionRequest | None = None
    rationale: Identifier
    structured_reasons: tuple[Identifier, ...] = Field(min_length=1)
    valid_until: AwareDatetime | None = None
    expiry_reason: Identifier | None = None

    @model_validator(mode="after")
    def chronology(self):
        if not self.statement_text.strip():
            raise ValueError("the exact independently confirmed statement is required")
        if self.confirmed_at < self.reviewed_at:
            raise ValueError("confirmation must follow the clinician decision")
        return self


class ClinicalReviewCaptureRequest(ReviewModel):
    request_id: UUID
    athlete_id: UUID
    injury_id: UUID
    injury_episode_id: UUID
    criterion_id: Identifier
    criterion_version: Version
    statement: ConfirmedClinicalStatement
    supersedes_review_id: UUID | None = None


class ClinicalReviewLifecycleRequest(ReviewModel):
    request_id: UUID
    athlete_id: UUID
    injury_id: UUID
    injury_episode_id: UUID
    review_id: UUID
    action: Literal["revoke", "supersede"]
    replacement_review_id: UUID | None = None
    effective_at: AwareDatetime
    confirmation_reference: Identifier
    reason: Identifier

    @model_validator(mode="after")
    def replacement(self):
        if (self.action == "supersede") != (self.replacement_review_id is not None):
            raise ValueError("only supersession identifies a replacement")
        if self.review_id == self.replacement_review_id:
            raise ValueError("self supersession is invalid")
        return self


class ClinicalReviewCaptureResult(ReviewModel):
    event_id: UUID
    review_id: UUID
    recorded_at: datetime
    event_type: Literal["clinical_progression_review", "clinical_progression_review_lifecycle"]
