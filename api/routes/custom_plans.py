"""Owner-scoped saved custom plans, separate from generated plans."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from api.contracts.custom_plans import CustomPlan, CustomPlanInput
from api.services.custom_plans import plan_fields


def build_custom_plans_router(*, require_profile, get_store):
    router = APIRouter(prefix="/api/custom-plans", tags=["custom plans"])

    def owned(store, athlete_id, plan_id):
        row = store.get_custom_plan(athlete_id, str(plan_id))
        if row is None:
            raise HTTPException(404, "Custom plan not found.")
        return row

    @router.get("", response_model=list[CustomPlan])
    def list_custom_plans(profile=Depends(require_profile), store=Depends(get_store)):
        return store.list_custom_plans(profile.athlete_id)

    @router.post("", response_model=CustomPlan, status_code=201)
    def create_custom_plan(body: CustomPlanInput, profile=Depends(require_profile), store=Depends(get_store)):
        return store.create_custom_plan(profile.athlete_id, plan_fields(store, body))

    @router.get("/{plan_id}", response_model=CustomPlan)
    def read_custom_plan(plan_id: UUID, profile=Depends(require_profile), store=Depends(get_store)):
        return owned(store, profile.athlete_id, plan_id)

    @router.put("/{plan_id}", response_model=CustomPlan)
    def update_custom_plan(plan_id: UUID, body: CustomPlanInput, profile=Depends(require_profile), store=Depends(get_store)):
        previous = owned(store, profile.athlete_id, plan_id)
        row = store.update_custom_plan(profile.athlete_id, str(plan_id), plan_fields(store, body, previous))
        if row is None:
            raise HTTPException(404, "Custom plan not found.")
        return row

    @router.delete("/{plan_id}", status_code=204)
    def delete_custom_plan(plan_id: UUID, profile=Depends(require_profile), store=Depends(get_store)):
        if not store.delete_custom_plan(profile.athlete_id, str(plan_id)):
            raise HTTPException(404, "Custom plan not found.")
        return Response(status_code=204)

    return router
