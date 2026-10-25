"""Effective-admin reports and strictly owner-bound optional event ingestion."""

from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from api.dependencies import get_store, require_admin, require_profile
from api.services.product_analytics import EVENT_FEATURES, FEATURES, summarize


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_name: str
    feature: Literal[
        "plans",
        "strength",
        "timer",
        "sparring",
        "history",
        "recovery",
        "nutrition",
        "manual",
        "feedback",
        "onboarding",
    ]
    request_id: UUID
    flow_id: UUID | None = None


class Preference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


def build_product_analytics_router():
    router = APIRouter(tags=["product analytics"])

    @router.get("/api/analytics/preference")
    def preference(profile=Depends(require_profile), store=Depends(get_store)):
        if getattr(profile, "is_minor", False):
            return {"enabled": False}
        result = (
            store.client.table("product_analytics_preferences")
            .select("enabled")
            .eq("athlete_id", profile.athlete_id)
            .execute()
        )
        return {"enabled": bool(result.data and result.data[0]["enabled"])}

    @router.put("/api/analytics/preference")
    def save_preference(
        body: Preference, profile=Depends(require_profile), store=Depends(get_store)
    ):
        if body.enabled and getattr(profile, "is_minor", False):
            raise HTTPException(
                403, "Optional product analytics is available to adults only"
            )
        result = store.client.rpc(
            "set_product_analytics_preference",
            {
                "p_athlete_id": profile.athlete_id,
                "p_enabled": body.enabled,
            },
        ).execute()
        enabled = bool(result.data)
        if body.enabled and not enabled:
            raise HTTPException(
                503,
                "Optional product analytics is temporarily unavailable. Try again later.",
            )
        return {"enabled": enabled}

    @router.post("/api/analytics/events", status_code=202)
    def ingest(body: Event, profile=Depends(require_profile), store=Depends(get_store)):
        if getattr(profile, "is_minor", False):
            return {"accepted": False}
        if EVENT_FEATURES.get(body.event_name) != body.feature and not (
            body.event_name == "frontend_error"
            and body.feature in (*FEATURES, "onboarding")
        ):
            raise HTTPException(422, "Unsupported event and feature combination")
        # No client actor, timestamp, payload or URL is accepted.
        result = store.client.rpc(
            "ingest_product_event",
            {
                "p_athlete_id": profile.athlete_id,
                "p_event_name": body.event_name,
                "p_feature": body.feature,
                "p_request_id": str(body.request_id),
                "p_flow_id": str(body.flow_id) if body.flow_id else None,
            },
        ).execute()
        return {"accepted": bool(result.data)}

    def facts(store, athlete_id=None):
        return (
            store.client.rpc(
                "product_analytics_facts",
                {
                    "p_excluded_emails": sorted(store.admin_emails),
                    "p_athlete_id": str(athlete_id) if athlete_id else None,
                },
            )
            .execute()
            .data
        )

    @router.get("/api/admin/product-analytics")
    def report(
        days: int = Query(30, ge=0, le=90),
        professional_status: str | None = Query(None, max_length=80),
        sport: str | None = Query(None, max_length=80),
        plan_mode: Literal["plan", "plan_free"] | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        admin=Depends(require_admin),
        store=Depends(get_store),
    ):
        if days not in (0, 7, 30, 90):
            raise HTTPException(422, "Period must be 7, 30, 90 days or 0 for all time")
        result = summarize(
            facts(store),
            days=days,
            professional_status=professional_status,
            sport=sport,
            plan_mode=plan_mode,
        )
        result["athlete_total"] = len(result["athletes"])
        result["athletes"] = sorted(
            result["athletes"],
            key=lambda p: (p["last_activity"] or "", p["id"]),
            reverse=True,
        )[offset : offset + limit]
        result["offset"] = offset
        return result

    @router.get("/api/admin/athletes/{athlete_id}/activity")
    def athlete_activity(
        athlete_id: UUID,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        admin=Depends(require_admin),
        store=Depends(get_store),
    ):
        result = summarize(facts(store, athlete_id), days=0)
        if not result["athletes"]:
            raise HTTPException(404, "Athlete not found")
        timeline = (
            store.client.table("product_activity")
            .select("id,occurred_at,feature,action")
            .eq("athlete_id", str(athlete_id))
            .eq("meaningful", True)
            .order("occurred_at", desc=True)
            .order("id")
            .range(offset, offset + limit - 1)
            .execute()
            .data
        )
        plans = (
            store.client.table("product_activity")
            .select("id,occurred_at,action")
            .eq("athlete_id", str(athlete_id))
            .eq("feature", "plans")
            .order("occurred_at", desc=True)
            .limit(10)
            .execute()
            .data
        )
        return {
            "summary": result["athletes"][0],
            "features": result["features"],
            "sessions_started": result["sessions_started"],
            "sessions_completed": result["sessions_completed"],
            "timeline": timeline,
            "latest_plan_interactions": plans,
            "offset": offset,
        }

    return router
