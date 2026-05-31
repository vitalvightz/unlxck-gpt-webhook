from .generation_jobs import build_generation_jobs_router
from .nutrition import build_nutrition_router
from .plans import build_plans_router
from .profile import build_profile_router

__all__ = [
    "build_generation_jobs_router",
    "build_nutrition_router",
    "build_plans_router",
    "build_profile_router",
]
