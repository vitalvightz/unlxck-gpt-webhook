"""Community review inputs. Publication is an explicit, revision-bound decision."""

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from api.contracts.custom_plans import Name
from api.contracts.private_media import PrivateMediaPreview


class CommunityDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exercise_id: UUID | None = None
    expected_revision_id: UUID | None = None
    name: Name
    equipment: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=2000)
    media_id: UUID | None = None


class CommunitySubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    share_rights: Literal[True]
    attribution_consent: Literal[True]


class CommunityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "verify", "confirm", "approve", "request_changes", "reject", "remove"
    ]
    reason: str | None = Field(None, max_length=1000)
    final_confirmation: bool = Field(False, strict=True)


class CommunityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)


class CommunityContributor(BaseModel):
    username: str
    avatar_url: str | None = None


class CommunityEntry(BaseModel):
    id: UUID
    revision_id: UUID
    name: str
    equipment: str | None = None
    notes: str | None = None
    media_id: UUID | None = None
    status: Literal[
        "private",
        "in_review",
        "changes_requested",
        "rejected",
        "published",
        "superseded",
    ]
    submitted_at: str | None = None
    created_at: str
    reason: str | None = None
    verified: bool = False
    confirmed: bool = False
    published: bool = False
    has_publication: bool = False
    contributor: CommunityContributor | None = None
    media: PrivateMediaPreview | None = None
    thumbnail: str | None = None
    audit: list[dict] = Field(default_factory=list)
    reports: list[dict] = Field(default_factory=list)
    prescription_allowed: Literal[False] = False


class CommunitySearch(BaseModel):
    entries: list[CommunityEntry]
    total: int
    next_offset: int | None = None
