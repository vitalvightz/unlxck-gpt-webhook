"""Block 4 executable contract layer for Today/Overview.

Pure, non-UI contracts so the frontend never improvises readiness, landing,
completion, or Overview state. See ``docs/block-4-ux-hierarchy-addendum.md``.

Modules:

* ``training_day`` — athlete-local training day resolver (§3 day-boundary).
* ``recommendation`` — recommendation TTL / validity (§3).
* ``checkin_decision`` — deterministic check-in decision evaluator (§4).
* ``completion`` — thin session-completion contract + landing mapping (§5).
* ``command_view`` — normalized command-view read model + risk watch (§6, §7).
* ``injury_checkin`` — daily per-injury check-in reconciliation + flag risks (§6).
* ``injury_signal`` — derived injury-risk signal from logged pain history (§6).
* ``rehab_stage`` — per-injury rehabilitation stage, independent of camp phase.
* ``rehab_completion`` — which completed rehab work may become injury evidence.
* ``load_eligibility`` — injury-episode LOAD eligibility (shadow mode only).
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
    RiskTimeframe,
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
from .injury_checkin import (
    DeclaredInjury,
    ReconciliationPlan,
    build_injury_label,
    open_injury_flag_risks,
    reconcile_injury_checkin,
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
from .load_eligibility import (
    LOAD_CRITERIA_REGISTRY,
    LOAD_ELIGIBILITY_ENGINE_VERSION,
    LoadEligibilityResult,
    resolve_load_eligibility,
)
from .rehab_completion import (
    RehabCompletionResolution,
    RehabExposureCandidate,
    RehabResponsePrompt,
    build_rehab_response_prompts,
    build_response_group_id,
    completed_dose_from_session,
    completed_dose_stopped_early,
    exposure_response_from_answers,
    resolve_rehab_completion,
    resolve_rehab_exposure_candidate,
)
from .rehab_stage import (
    REHAB_STAGES,
    RehabStageDecision,
    RehabStageEvidence,
    resolve_rehab_stage,
    resolve_rehab_stages,
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
    "RiskTimeframe",
    "RiskWatchItem",
    "build_command_view",
    "make_risk",
    "sort_risk_watch",
    "visible_risk_watch",
    # injury_checkin
    "DeclaredInjury",
    "ReconciliationPlan",
    "build_injury_label",
    "open_injury_flag_risks",
    "reconcile_injury_checkin",
    # injury_signal
    "derive_injury_signal",
    # rehab_completion
    "RehabCompletionResolution",
    "RehabExposureCandidate",
    "RehabResponsePrompt",
    "build_rehab_response_prompts",
    "build_response_group_id",
    "completed_dose_from_session",
    "completed_dose_stopped_early",
    "exposure_response_from_answers",
    "resolve_rehab_completion",
    "resolve_rehab_exposure_candidate",
    # load_eligibility (shadow mode only)
    "LOAD_CRITERIA_REGISTRY",
    "LOAD_ELIGIBILITY_ENGINE_VERSION",
    "LoadEligibilityResult",
    "resolve_load_eligibility",
    # rehab_stage
    "REHAB_STAGES",
    "RehabStageDecision",
    "RehabStageEvidence",
    "resolve_rehab_stage",
    "resolve_rehab_stages",
    # landing
    "LandingCTA",
    "LandingDecision",
    "LandingTarget",
    "resolve_landing",
]
