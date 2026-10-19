"""Stage A verification/player payloads; no generator or clinical integration."""

from urllib.parse import urlparse
from fastapi import HTTPException
from api.contracts.community_exercises import CommunityEntry
from api.contracts.private_media import PrivateMediaPreview, YouTubeClipInput
from api.services.private_media import validate_clip


def command(store, actor_id, action, payload):
    result = store.community_rpc(
        "community_command",
        {"p_actor_id": actor_id, "p_action": action, "p_payload": payload},
    )
    if action == "approve":
        from api.services.tracking_xp import reconcile_contribution_xp

        reconcile_contribution_xp(store, str(result))
    return result


def detail_row(store, actor_id, revision_id, *, admin=False):
    return store.community_rpc(
        "community_detail",
        {"p_actor_id": actor_id, "p_revision_id": str(revision_id), "p_admin": admin},
    )


def present(store, row, *, preview=False):
    row = dict(row)
    raw = row.pop("raw_media", None)
    if raw and raw.get("provider") == "youtube":
        row["thumbnail"] = f"https://i.ytimg.com/vi/{raw['video_id']}/mqdefault.jpg"
    if preview and raw:
        media = {
            key: raw.get(key)
            for key in (
                "id",
                "provider",
                "video_id",
                "asset_id",
                "start_s",
                "end_s",
                "channel_title",
                "orientation",
            )
        }
        if raw["provider"] == "uploaded":
            asset = raw.get("asset")
            if asset and asset.get("status") == "verified":
                media["url"] = store.private_video_signed_url(
                    asset["rendition_path"], expires_in=60
                )
            else:
                media = None
        if media:
            row["media"] = PrivateMediaPreview(**media)
    contributor = row.get("contributor")
    if contributor and contributor.get("avatar_url"):
        url = urlparse(contributor["avatar_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            contributor = {**contributor, "avatar_url": None}
        row["contributor"] = contributor
    return CommunityEntry(**row)


def verify_media(row):
    raw = row.get("raw_media")
    proof = {"verified_media_id": row.get("media_id")}
    if not raw:
        if row.get("media_id"):
            raise HTTPException(409, "Video is unavailable. Replace it before review.")
        return proof
    if raw["provider"] == "youtube":
        checked = validate_clip(
            YouTubeClipInput(
                url=f"https://www.youtube.com/watch?v={raw['video_id']}",
                start_s=raw["start_s"],
                end_s=raw["end_s"],
            )
        )
        proof.update(youtube_id=checked["video_id"], youtube_verified=True)
    else:
        asset = raw.get("asset")
        if (
            not asset
            or asset["status"] != "verified"
            or asset.get("processor_version") != "isolated-v1"
        ):
            raise HTTPException(409, "Video has not passed secure processing.")
        proof["sha256"] = asset["sha256"]
    return proof
