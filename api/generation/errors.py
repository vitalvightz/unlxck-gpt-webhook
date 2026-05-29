"""Exceptions raised by the generation runtime."""
from __future__ import annotations


class TriageResumeMissingPlanError(RuntimeError):
    """Raised when an admin_triage_resume job cannot find its linked plan.

    A resume job must update the original triage-blocked plan in place; if the
    linked plan is missing we fail loudly rather than silently creating a
    duplicate plan.
    """

    pass


class AdminLatestIntakeLinkageError(RuntimeError):
    """Raised when an admin_latest_intake job linkage/ownership validation fails."""

    pass
