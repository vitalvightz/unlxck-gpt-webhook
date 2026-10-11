"""Authenticated private video permissions and previews. No public/review routes."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.contracts.private_media import (
    PrivateMediaPreview, PrivateMediaSettings, UploadInput, UploadPermission, UploadState, YouTubeClipInput,
)
from api.services.exercise_media import youtube_api_key
from api.services.private_media import media_preview, upload_state, uploads_available, validate_clip


def build_private_media_router(*, require_profile, get_store):
    router = APIRouter(prefix="/api/private-media", tags=["private exercise demos"])

    @router.get("/settings", response_model=PrivateMediaSettings)
    def settings(profile=Depends(require_profile), store=Depends(get_store)):
        return {"uploads_available": uploads_available(store), "youtube_available": bool(youtube_api_key())}

    @router.post("/youtube", response_model=PrivateMediaPreview, status_code=201)
    def youtube(body: YouTubeClipInput, profile=Depends(require_profile), store=Depends(get_store)):
        store.claim_private_media_budget(profile.athlete_id)
        fields = validate_clip(body)
        row = store.create_private_media(profile.athlete_id, fields)
        return media_preview(store, profile.athlete_id, row["id"])

    @router.post("/uploads", response_model=UploadPermission, status_code=201)
    def reserve(body: UploadInput, profile=Depends(require_profile), store=Depends(get_store)):
        if not uploads_available(store):
            raise HTTPException(503, "Video uploads are temporarily unavailable. You can save without a video.")
        asset = store.reserve_private_video(profile.athlete_id, body.size_bytes, body.content_type)
        return {"asset_id": asset["id"], "path": asset["intake_path"], "expires_at": asset["upload_expires_at"]}

    @router.get("/uploads/{asset_id}", response_model=UploadState)
    def uploaded(asset_id: UUID, profile=Depends(require_profile), store=Depends(get_store)):
        return upload_state(store, profile.athlete_id, asset_id)

    @router.get("/{media_id}", response_model=PrivateMediaPreview)
    def preview(media_id: UUID, profile=Depends(require_profile), store=Depends(get_store)):
        return media_preview(store, profile.athlete_id, media_id)

    return router
