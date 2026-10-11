"""Private demo identities. Never reuse exercise_media.video_id for upload UUIDs."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class YouTubeClipInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=500)
    start_s: int = Field(strict=True, ge=0, le=86400)
    end_s: int = Field(strict=True, ge=1, le=86430)

    @model_validator(mode="after")
    def segment(self):
        if not 0 < self.end_s - self.start_s <= 30:
            raise ValueError("Choose a clip between 1 and 30 seconds.")
        return self


class UploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    size_bytes: int = Field(strict=True, ge=1, le=20 * 1024 * 1024)
    content_type: Literal["video/mp4", "video/quicktime", "video/webm"]


class UploadPermission(BaseModel):
    asset_id: UUID
    bucket: Literal["private-demo-intake"] = "private-demo-intake"
    path: str
    expires_at: str


class PrivateMediaPreview(BaseModel):
    id: UUID
    provider: Literal["youtube", "uploaded"]
    video_id: str | None = None
    asset_id: UUID | None = None
    start_s: int = 0
    end_s: int
    channel_title: str | None = None
    orientation: Literal["portrait", "landscape"] | None = None
    url: str | None = None


class UploadState(BaseModel):
    status: Literal["reserved", "queued", "processing", "verified", "rejected", "deleted"]
    media: PrivateMediaPreview | None = None


class PrivateMediaSettings(BaseModel):
    uploads_available: bool
    youtube_available: bool
