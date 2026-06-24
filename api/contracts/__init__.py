"""Block 4 executable contract layer for Today/Overview.

Pure, non-UI contracts so the frontend never improvises readiness, landing,
completion, or Overview state. See ``docs/block-4-ux-hierarchy-addendum.md``.

Modules:

* ``training_day`` — athlete-local training day resolver (§3 day-boundary).
* ``recommendation`` — recommendation TTL / validity (§3).
* ``checkin_decision`` — deterministic check-in decision evaluator (§4).
* ``completion`` — thin session-completion contract + landing mapping (§5).
* ``command_view`` — normalized command-view read model + risk watch (§6, §7).
* ``injury_signal`` — derived injury-risk signal from logged pain history (§6).
* ``landing`` — state-dependent landing resolver (§1).
"""

from __future__ import annotations

from .checkin_decision import (
    CheckinDecision,
    CheckinDecisionValue,
    CheckinInputs,
    SAFETY_FLAGS,
    evaluate_checkin,
)
from .command_view import (
    CommandView,
    CommandViewToday,
    QuickAction,
    RiskCategory,
    RiskWatchItem,
    build_command_view,
    make_risk,
    sort_risk_watch,
    visible_risk_watch,
)
from .completion import (
    COMPLETION_STATUSES,
    CompletionStatus,
    LandingSessionState,
    SessionCompletionRecord,
    completion_key,
    completion_landing_state,
    completion_status_of,
    find_completion,
)
from .injury_signal import (
    derive_injury_signal,
)
from .landing import (
    LandingCTA,
    LandingDecision,
    LandingTarget,
    resolve_landing,
)
from .recommendation import (
    RecommendationState,
    RecommendationView,
    is_recommendation_valid,
    resolve_recommendation_state,
)
from .training_day import (
    DAY_ROLLOVER_HOUR,
    DEFAULT_TIMEZONE,
    current_training_day,
    resolve_timezone,
    resolve_training_day,
    resolve_training_day_str,
)

__all__ = [
    # training_day
    "DAY_ROLLOVER_HOUR",
    "DEFAULT_TIMEZONE",
    "current_training_day",
    "resolve_timezone",
    "resolve_training_day",
    "resolve_training_day_str",
    # recommendation
    "RecommendationState",
    "RecommendationView",
    "is_recommendation_valid",
    "resolve_recommendation_state",
    # checkin_decision
    "CheckinDecision",
    "CheckinDecisionValue",
    "CheckinInputs",
    "SAFETY_FLAGS",
    "evaluate_checkin",
    # completion
    "COMPLETION_STATUSES",
    "CompletionStatus",
    "LandingSessionState",
    "SessionCompletionRecord",
    "completion_key",
    "completion_landing_state",
    "completion_status_of",
    "find_completion",
    # command_view
    "CommandView",
    "CommandViewToday",
    "QuickAction",
    "RiskCategory",
    "RiskWatchItem",
    "build_command_view",
    "make_risk",
    "sort_risk_watch",
    "visible_risk_watch",
    # injury_signal
    "derive_injury_signal",
    # landing
    "LandingCTA",
    "LandingDecision",
    "LandingTarget",
    "resolve_landing",
]
