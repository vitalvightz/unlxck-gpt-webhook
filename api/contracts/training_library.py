"""Discovery-only library responses; none authorises a prescription."""
from typing import Literal
from pydantic import BaseModel, Field
from api.models import ExerciseMedia

LibraryCategory = Literal["training", "rehab", "learn"]


class LibraryFacet(BaseModel):
    value: str
    label: str
    count: int


class LibraryEntry(BaseModel):
    catalogue_id: str
    name: str
    content_type: str
    category: LibraryCategory
    context: str
    focus: list[str]
    discovery_match: str | None = None
    equipment: list[str] | None
    equipment_state: str
    exercise_key: str | None
    media: ExerciseMedia | None = None
    selection_boundary: str
    prescription_allowed: Literal[False] = False


class LibraryPreview(LibraryEntry):
    source: str
    source_revision: str
    row_revision: str
    guidance: dict[str, list[str]] = Field(default_factory=dict)


class LibrarySearchResponse(BaseModel):
    entries: list[LibraryEntry]
    total: int
    catalogue_total: int
    offset: int
    limit: int
    next_offset: int | None
    revision: str
    facets: dict[str, list[LibraryFacet]]
