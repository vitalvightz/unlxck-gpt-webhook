"""Lightweight mutation ledger for post-score planner selection changes.

Records when and why the planner changes its selection after scoring has
already ranked candidates.  The ledger is internal and primarily for audit,
debugging, and observability — not for production decision-making.

Classification labels
---------------------
Use the four constants below to tag every post-score override so later work
cannot leave all overrides in one undifferentiated blob:

``MUST_NOT_MISS_GUARANTEE``
    Structural must-not-miss: anchor presence, final injury-safe replacement,
    session integrity — items that would break the session contract if omitted.

``SELECTOR_COMPENSATION_INSERTION``
    Compensatory insertion added because the selector is not trusted to surface
    the item reliably.  Frequent firing is a signal of architecture debt.

``PHASE_SPECIFIC_SAFEGUARD``
    Safeguard scoped to a particular training phase or late-pass context
    (e.g. force-isometric in GPP/SPP, keyword-guard residual catch).

``NICHE_LATE_INSERTION``
    Narrow late insertion covering a niche edge-case not handled by the main
    selector or structural enforcement (e.g. conflict resolution).
"""
from __future__ import annotations

import dataclasses
from typing import Any

# ---------------------------------------------------------------------------
# Override / guarantee classification labels
# ---------------------------------------------------------------------------

#: Structural anchor presence, session integrity, final injury-safe pass.
MUST_NOT_MISS_GUARANTEE = "must_not_miss_guarantee"

#: Compensatory insertion because the selector is not fully trusted.
SELECTOR_COMPENSATION_INSERTION = "selector_compensation_insertion"

#: Safeguard scoped to a training phase or late-pass context.
PHASE_SPECIFIC_SAFEGUARD = "phase_specific_safeguard"

#: Narrow niche late insertion for edge-cases outside the main selector.
NICHE_LATE_INSERTION = "niche_late_insertion"

_ALL_LABELS = frozenset(
    {
        MUST_NOT_MISS_GUARANTEE,
        SELECTOR_COMPENSATION_INSERTION,
        PHASE_SPECIFIC_SAFEGUARD,
        NICHE_LATE_INSERTION,
    }
)


@dataclasses.dataclass
class MutationRecord:
    """A single post-score selection mutation."""

    mechanism: str
    """Short name of the function / sub-phase that caused the mutation."""

    phase: str
    """Training phase (GPP / SPP / TAPER)."""

    original_name: str | None
    """Name of the exercise removed or repositioned (None for pure insertion)."""

    replacement_name: str | None
    """Name of the exercise inserted (None for pure removal)."""

    original_score: float | None
    """Score of the original exercise at selection time, if known."""

    replacement_score: float | None
    """Score of the replacement exercise at selection time, if known."""

    label: str
    """Override classification: one of the four label constants above."""

    reason: str
    """Concise human-readable reason for the mutation."""

    module: str = "strength"
    """Source module (default: 'strength')."""


def record_mutation(
    log: list[MutationRecord],
    *,
    mechanism: str,
    phase: str,
    original_name: str | None,
    replacement_name: str | None,
    original_score: float | None = None,
    replacement_score: float | None = None,
    label: str,
    reason: str,
    module: str = "strength",
) -> None:
    """Append a :class:`MutationRecord` to *log*."""
    log.append(
        MutationRecord(
            mechanism=mechanism,
            phase=phase,
            original_name=original_name,
            replacement_name=replacement_name,
            original_score=original_score,
            replacement_score=replacement_score,
            label=label,
            reason=reason,
            module=module,
        )
    )


def mutation_log_to_dicts(log: list[MutationRecord]) -> list[dict[str, Any]]:
    """Return the mutation log as a list of plain dicts (for JSON serialisation)."""
    return [dataclasses.asdict(record) for record in log]
