"""Authenticated submission, audited moderation and discovery-only publication."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from api.contracts.community_exercises import (
    CommunityDecision,
    CommunityDraft,
    CommunityEntry,
    CommunityReport,
    CommunitySearch,
    CommunitySubmission,
)
from api.services.community_exercises import command, detail_row, present, verify_media


def build_community_router(*, require_profile, require_admin, get_store):
    router = APIRouter(prefix="/api/community-exercises", tags=["community exercises"])

    def read(store, actor, revision, admin=False):
        return present(
            store, detail_row(store, actor, revision, admin=admin), preview=True
        )

    def listing(store, actor, scope, q="", offset=0):
        result = store.community_rpc(
            "community_list",
            {
                "p_actor_id": actor,
                "p_scope": scope,
                "p_query": q,
                "p_offset": offset,
                "p_limit": 30,
            },
        )
        return {**result, "entries": [present(store, row) for row in result["entries"]]}

    @router.get("", response_model=CommunitySearch)
    def discover(
        q: str = Query("", max_length=100),
        offset: int = Query(0, ge=0, le=100000),
        profile=Depends(require_profile),
        store=Depends(get_store),
    ):
        return listing(store, profile.athlete_id, "public", q, offset)

    @router.get("/mine", response_model=CommunitySearch)
    def mine(
        offset: int = Query(0, ge=0),
        profile=Depends(require_profile),
        store=Depends(get_store),
    ):
        return listing(store, profile.athlete_id, "mine", offset=offset)

    @router.get("/owned/{exercise_id}", response_model=CommunityEntry)
    def owned(
        exercise_id: UUID, profile=Depends(require_profile), store=Depends(get_store)
    ):
        revision = store.community_rpc(
            "community_owned_revision",
            {"p_actor_id": profile.athlete_id, "p_exercise_id": str(exercise_id)},
        )
        return read(store, profile.athlete_id, revision)

    @router.post("/drafts", response_model=CommunityEntry, status_code=201)
    def draft(
        body: CommunityDraft, profile=Depends(require_profile), store=Depends(get_store)
    ):
        revision = command(
            store, profile.athlete_id, "draft", body.model_dump(mode="json")
        )
        return read(store, profile.athlete_id, revision)

    @router.get("/review", response_model=CommunitySearch)
    def queue(
        q: str = Query("", max_length=100),
        offset: int = Query(0, ge=0),
        admin=Depends(require_admin),
        store=Depends(get_store),
    ):
        return listing(store, admin.athlete_id, "review", q, offset)

    @router.get("/review/{revision_id}", response_model=CommunityEntry)
    def review(
        revision_id: UUID, admin=Depends(require_admin), store=Depends(get_store)
    ):
        return read(store, admin.athlete_id, revision_id, True)

    @router.put("/review/{revision_id}", response_model=CommunityEntry)
    def edit(
        revision_id: UUID,
        body: CommunityDraft,
        admin=Depends(require_admin),
        store=Depends(get_store),
    ):
        payload = body.model_dump(mode="json")
        payload["revision_id"] = str(revision_id)
        revision = command(store, admin.athlete_id, "edit", payload)
        return read(store, admin.athlete_id, revision, True)

    @router.post("/review/{revision_id}", response_model=CommunityEntry)
    def decide(
        revision_id: UUID,
        body: CommunityDecision,
        admin=Depends(require_admin),
        store=Depends(get_store),
    ):
        payload = body.model_dump(mode="json")
        payload["revision_id"] = str(revision_id)
        if (
            body.action in ("reject", "request_changes", "remove", "dismiss_report")
            and not (body.reason or "").strip()
        ):
            raise HTTPException(422, "Add a reason for this decision.")
        if body.action in ("confirm", "approve") and not body.final_confirmation:
            raise HTTPException(
                422, "Confirm the final exercise and video before continuing."
            )
        if body.action in ("verify", "approve"):
            payload.update(
                verify_media(
                    detail_row(store, admin.athlete_id, revision_id, admin=True)
                )
            )
        if body.action == "dismiss_report":
            if not body.report_id:
                raise HTTPException(422, "Select the report to dismiss.")
            revision = store.community_rpc(
                "community_dismiss_report",
                {
                    "p_actor_id": admin.athlete_id,
                    "p_revision_id": str(revision_id),
                    "p_report_id": str(body.report_id),
                    "p_reason": body.reason,
                },
            )
        else:
            revision = command(store, admin.athlete_id, body.action, payload)
        return read(store, admin.athlete_id, revision, True)

    @router.get("/revisions/{revision_id}", response_model=CommunityEntry)
    def preview(
        revision_id: UUID, profile=Depends(require_profile), store=Depends(get_store)
    ):
        return read(store, profile.athlete_id, revision_id)

    @router.post("/revisions/{revision_id}/submit", response_model=CommunityEntry)
    def submit(
        revision_id: UUID,
        body: CommunitySubmission,
        profile=Depends(require_profile),
        store=Depends(get_store),
    ):
        revision = command(
            store,
            profile.athlete_id,
            "submit",
            {"revision_id": str(revision_id), **body.model_dump(mode="json")},
        )
        return read(store, profile.athlete_id, revision)

    @router.post("/revisions/{revision_id}/withdraw", response_model=CommunityEntry)
    def withdraw(
        revision_id: UUID, profile=Depends(require_profile), store=Depends(get_store)
    ):
        revision = command(
            store, profile.athlete_id, "withdraw", {"revision_id": str(revision_id)}
        )
        return read(store, profile.athlete_id, revision)

    @router.post("/revisions/{revision_id}/report", status_code=204)
    def report(
        revision_id: UUID,
        body: CommunityReport,
        profile=Depends(require_profile),
        store=Depends(get_store),
    ):
        command(
            store,
            profile.athlete_id,
            "report",
            {"revision_id": str(revision_id), **body.model_dump(mode="json")},
        )

    return router
