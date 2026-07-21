from .daily import build_daily_router
from .feedback import build_feedback_router
from .generation_jobs import build_generation_jobs_router
from .nutrition import build_nutrition_router
from .plans import build_plans_router
from .profile import build_profile_router
from .push import build_push_router
from .today import build_today_router

__all__ = [
    "build_daily_router",
    "build_feedback_router",
    "build_generation_jobs_router",
    "build_nutrition_router",
    "build_plans_router",
    "build_profile_router",
    "build_push_router",
    "build_today_router",
]
