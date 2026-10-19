"""Discovery-only library responses; none authorises a prescription."""
from typing import Literal
from pydantic import BaseModel, Field
from api.models import ExerciseMedia

LibraryCategory = Literal["training", "rehab", "learn"]


class LibraryFacet(BaseModel):
    value: str
    label: str
    count: int


class EquipmentRequirementItem(BaseModel):
    canonical_id: str
    kind: Literal["apparatus", "partner"]
    quantity: int | None = None


class EquipmentRequirementGroup(BaseModel):
    mode: Literal["SINGLE", "ALL", "ANY", "OPTIONAL", "UNKNOWN"]
    items: list[EquipmentRequirementItem]


class EquipmentRequirements(BaseModel):
    status: Literal["reviewed", "unresolved"]
    groups: list[EquipmentRequirementGroup]
    source_value: str | list[str] | None
    source: str
    source_pointer: str
    catalogue_id: str
    row_revision: str
    audit_decisions: list[str]
    evidence: str


class ExerciseDetail(BaseModel):
    value: str
    label: str
    group: Literal["movement", "training_method", "skill_focus", "physical_focus"]


class LibraryEntry(BaseModel):
    catalogue_id: str
    name: str
    content_type: str
    category: LibraryCategory
    context: str
    focus: list[str]
    verified_goals: list[str] = Field(default_factory=list)
    exercise_details: list[ExerciseDetail] = Field(default_factory=list)
    discovery_match: str | None = None
    equipment: list[str] | None
    equipment_state: str
    equipment_requirements: EquipmentRequirements | None = None
    exercise_key: str | None
    media: ExerciseMedia | None = None
    selection_boundary: str
    prescription_allowed: Literal[False] = False
    # Only with ``for_log``: the layout for recording performed work, or None
    # when the catalogue's own evidence leaves it ambiguous.
    log_format: Literal["strength", "bodyweight", "isometric", "intervals", "distance"] | None = None


class ProjectedMetadata(BaseModel):
    canonical_id: str
    label: str
    source_value: str
    source_field: str
    dimension: str
    subtype: str | None
    catalogue_id: str
    source: str
    source_pointer: str
    source_revision: str
    row_revision: str
    audit_decision: str | None
    audit_report: str | None
    audit_revision: str | None
    status: Literal["reviewed_alias", "source_value", "unresolved_compound", "association_review", "reviewed_goal"]
    filter_eligible: bool
    association_note: str | None
    requirement_evidence: dict[str, object] = Field(default_factory=dict)
    goal_evidence: dict[str, object] = Field(default_factory=dict)


class LibraryPreview(LibraryEntry):
    source: str
    source_revision: str
    row_revision: str
    guidance: dict[str, list[str]] = Field(default_factory=dict)
    metadata_projection: list[ProjectedMetadata] = Field(default_factory=list)
    equipment_source: dict[str, object] = Field(default_factory=dict)


class LibraryFeaturedResponse(BaseModel):
    entry: LibraryEntry | None = None


class LibrarySearchResponse(BaseModel):
    entries: list[LibraryEntry]
    total: int
    catalogue_total: int
    offset: int
    limit: int
    next_offset: int | None
    revision: str
    facets: dict[str, list[LibraryFacet]]
