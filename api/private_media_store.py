"""Small store mixin; privileged queries always carry the authenticated owner."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


class PrivateMediaStoreMixin:
    def private_media_worker_healthy(self):
        try:
            since = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
            row = self._select_first(self.client.table("private_media_worker_health").select("id")
                                     .eq("id", "isolated-v1").gt("healthy_at", since))
            return bool(row)
        except Exception:
            # A missing migration or worker must never accidentally open uploads.
            return False

    def claim_private_media_budget(self, athlete_id):
        response = self.client.rpc("claim_private_media_budget", {"p_athlete_id": athlete_id}).execute()
        if not response.data:
            raise HTTPException(429, "Video limit reached. Try again later.", headers={"Retry-After": "3600"})

    def reserve_private_video(self, athlete_id, size_bytes, content_type):
        response = self.client.rpc("reserve_private_video", {
            "p_athlete_id": athlete_id, "p_size_bytes": size_bytes, "p_content_type": content_type,
        }).execute()
        if not response.data:
            raise HTTPException(429, "Video limit reached. Try again later.", headers={"Retry-After": "3600"})
        return response.data[0]

    def create_private_media(self, athlete_id, fields):
        allowed = ("provider", "video_id", "start_s", "end_s", "channel_title", "orientation", "made_for_kids")
        payload = {key: fields[key] for key in allowed if key in fields}
        response = self.client.table("private_exercise_media").insert({**payload, "athlete_id": athlete_id}).execute()
        return response.data[0]

    def get_private_media(self, athlete_id, media_id):
        return self._select_first(self.client.table("private_exercise_media").select("*")
                                 .eq("athlete_id", athlete_id).eq("id", media_id))

    def get_private_media_for_asset(self, athlete_id, asset_id):
        return self._select_first(self.client.table("private_exercise_media").select("*")
                                 .eq("athlete_id", athlete_id).eq("asset_id", asset_id))

    def get_private_video_asset(self, athlete_id, asset_id):
        return self._select_first(self.client.table("private_video_assets").select("*")
                                 .eq("athlete_id", athlete_id).eq("id", asset_id))

    def private_video_signed_url(self, path, *, expires_in):
        response = self.client.storage.from_("private-demo-ready").create_signed_url(path, expires_in)
        url = response.get("signedURL") or response.get("signedUrl")
        if not url:
            raise HTTPException(503, "Unable to open video. Try again.")
        return url
