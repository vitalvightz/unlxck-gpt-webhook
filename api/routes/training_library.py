"""Authenticated, read-only discovery. No planner or scheduling operations."""
import logging
from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Query

from api.contracts.training_library import LibraryCategory, LibraryFeaturedResponse, LibraryPreview, LibrarySearchResponse
from api.services import training_library as library
from api.services.exercise_media import load_media_index
from fightcamp.exercise_identity import normalize_exercise_key

logger = logging.getLogger(__name__)


def _index():
    try:
        return library.cache.get()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        logger.exception("Training catalogue unavailable or invalid")
        raise HTTPException(503, "Training library is temporarily unavailable.") from None


def _attach_media(payload, record, media):
    entry = record["entry"]
    if payload["category"] == "training":
        key = entry["exercise_key"]
    elif payload["category"] == "rehab":
        key = normalize_exercise_key(entry["source_id"])
    else:
        return
    payload["media"] = media.get(key)


def build_training_library_router(*, require_profile, get_store):
    router = APIRouter(prefix="/api/training/library", tags=["training library"])

    @router.get("", response_model=LibrarySearchResponse)
    def find_drills(
        q: str = Query("", max_length=100), category: LibraryCategory = "training",
        type_filter: str | None = Query(None, alias="type", max_length=100),
        goal: str | None = Query(None, max_length=100), sport: str | None = Query(None, max_length=100),
        equipment: str | None = Query(None, max_length=100), body_focus: str | None = Query(None, max_length=100),
        movement: str | None = Query(None, max_length=100), training_method: str | None = Query(None, max_length=100),
        skill_focus: str | None = Query(None, max_length=100),
        physical_focus: str | None = Query(None, max_length=100),
        offset: int = Query(0, ge=0, le=10000), limit: int = Query(24, ge=1, le=50),
        revision: str | None = Query(None, max_length=64),
        for_plan: bool = False,
        # Recording performed work: add each result's suggested measurement layout.
        for_log: bool = False,
        profile=Depends(require_profile), store=Depends(get_store),
    ):
        index = _index()
        if for_plan and category == "training":
            from api.services.exercise_customisation import AthleteContext, _sport_allows

            athlete = AthleteContext({"athlete": {"technical_style": profile.technical_style}})
            index = replace(index, records=[record for record in index.records if _sport_allows(record, athlete)])
        if revision and revision != index.revision:
            raise HTTPException(409, "Library changed. Refresh your search.")
        result = library.search(index, q=q, category=category, offset=offset, limit=limit,
                                filters=dict(type=type_filter, goal=goal, sport=sport,
                                             equipment=equipment, body_focus=body_focus, movement=movement,
                                             training_method=training_method, skill_focus=skill_focus,
                                             physical_focus=physical_focus))
        media = load_media_index(store)
        for payload in result["entries"]:
            _attach_media(payload, index.by_id[payload["catalogue_id"]], media)
            if for_log and payload["category"] == "training":
                from api.services.manual_exercises import catalogue_format

                payload["log_format"] = catalogue_format(index.by_id[payload["catalogue_id"]])
        return result

    @router.get("/featured", response_model=LibraryFeaturedResponse)
    def featured_drill(profile=Depends(require_profile), store=Depends(get_store)):
        # Editorial priority, never a popularity score or a prescription. Only
        # current, curated demos on exact Training identities may be featured.
        index = _index()
        media = load_media_index(store)
        preferred = ("medicine-ball-hook-throw", "check-hook-pivot-burst", "standing-cable-punch-simulation")
        candidates = [record for record in index.records if record["summary"]["category"] == "training"
                      and record["entry"]["exercise_key"] in media]
        if not candidates:
            return {"entry": None}
        candidates.sort(key=lambda record: (
            preferred.index(record["entry"]["exercise_key"]) if record["entry"]["exercise_key"] in preferred else len(preferred),
            record["entry"]["catalogue_id"],
        ))
        record = candidates[0]
        payload = dict(record["summary"])
        _attach_media(payload, record, media)
        return {"entry": payload}

    @router.get("/entry", response_model=LibraryPreview)
    def drill_preview(
        catalogue_id: str = Query(..., min_length=1, max_length=250),
        profile=Depends(require_profile), store=Depends(get_store),
    ):
        record = _index().by_id.get(catalogue_id)
        if record is None:
            raise HTTPException(404, "Drill is no longer available.")
        result = library.preview(record)
        _attach_media(result, record, load_media_index(store))
        return result

    return router
