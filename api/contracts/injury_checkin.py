"""Daily injury check-in reconciliation (Block 4 §6 follow-up).

The Today check-in carries a single ``active_injury`` flag (none/stable/worse).
That can't say *which* injury, and it can't tell a resolved injury from a brand
new one. This contract reconciles the athlete's declared injuries for a training
day against their existing open ``injury_flags`` so every injury keeps identity
over time:

* a report with no ``flag_id`` opens a new flag,
* an ``improving`` report parks the flag in ``monitoring``,
* a ``resolved`` report closes it (``resolved``), and
* an ``ongoing`` / ``worse`` report keeps it ``open`` (severity may change).

Pure and deterministic: this computes the create/update plan; the service
applies it to storage and stamps ``resolved_at``. Capturing per-injury state now
is exactly what lets a later PR make plans dynamic when an injury clears or a new
one appears — this PR only persists it and feeds the risk watch.
"""

from __future__ import annotations

from typing import Iterable, Literal, Mapping, Sequence

from pydantic import BaseModel, Field, model_validator

from .command_view import RiskWatchItem, make_risk

InjuryFlagSeverity = Literal["mild", "moderate", "severe"]
InjuryFlagStatus = Literal["open", "monitoring", "resolved"]
# What the athlete reports about an injury on a given day.
InjuryCheckinStatus = Literal["ongoing", "improving", "worse", "resolved"]

# Reported day-state -> persisted flag status. "improving" parks the flag in
# monitoring; "resolved" closes it; "ongoing"/"worse" keep it open.
_FLAG_STATUS_BY_REPORT: dict[str, InjuryFlagStatus] = {
    "ongoing": "open",
    "worse": "open",
    "improving": "monitoring",
    "resolved": "resolved",
}

# Open/active statuses for risk-watch purposes (resolved flags are silent).
ACTIVE_FLAG_STATUSES: frozenset[str] = frozenset({"open", "monitoring"})


class DeclaredInjury(BaseModel):
    """One injury as reported on a daily check-in.

    ``flag_id`` references an existing open flag being updated; without it the
    report is a new injury and needs a ``body_area`` or ``description`` to
    identify it.
    """

    flag_id: str | None = None
    body_area: str = ""
    description: str = ""
    severity: InjuryFlagSeverity = "moderate"
    status: InjuryCheckinStatus = "ongoing"

    @model_validator(mode="after")
    def _check_identifiable(self) -> "DeclaredInjury":
        if not self.flag_id and not (self.body_area.strip() or self.description.strip()):
            raise ValueError("a new injury needs a body_area or description")
        return self


class FlagUpdate(BaseModel):
    flag_id: str
    fields: dict[str, object] = Field(default_factory=dict)


class ReconciliationPlan(BaseModel):
    """Storage-agnostic plan: flags to create, and existing flags to update."""

    creates: list[dict[str, object]] = Field(default_factory=list)
    updates: list[FlagUpdate] = Field(default_factory=list)


def _flag_label(flag: Mapping[str, object]) -> str:
    label = str(flag.get("body_area") or "").strip() or str(flag.get("description") or "").strip()
    return label[:60] if label else "injury"


def reconcile_injury_checkin(
    *,
    declared: Sequence[DeclaredInjury],
    open_flag_ids: Iterable[str],
) -> ReconciliationPlan:
    """Build the create/update plan for a day's declared injuries.

    A ``flag_id`` is only honoured when it belongs to the athlete's current open
    flags (``open_flag_ids``) — anything else is treated as a new injury, so a
    stale or foreign id can never mutate another athlete's flag.
    """
    known = {str(flag_id) for flag_id in open_flag_ids}
    creates: list[dict[str, object]] = []
    updates: list[FlagUpdate] = []

    for injury in declared:
        flag_status = _FLAG_STATUS_BY_REPORT[injury.status]
        if injury.flag_id and injury.flag_id in known:
            fields: dict[str, object] = {"status": flag_status, "severity": injury.severity}
            if injury.body_area.strip():
                fields["body_area"] = injury.body_area.strip()
            if injury.description.strip():
                fields["description"] = injury.description.strip()
            updates.append(FlagUpdate(flag_id=injury.flag_id, fields=fields))
            continue

        # A brand-new injury reported as already resolved is a no-op — there is
        # nothing to track. Otherwise open (or monitor) a fresh flag.
        if flag_status == "resolved":
            continue
        description = injury.description.strip() or injury.body_area.strip()
        creates.append(
            {
                "source": "checkin",
                "body_area": injury.body_area.strip(),
                "description": description,
                "severity": injury.severity,
                "status": flag_status,
            }
        )

    return ReconciliationPlan(creates=creates, updates=updates)


def open_injury_flag_risks(
    open_flags: Sequence[Mapping[str, object]],
) -> list[RiskWatchItem]:
    """Surface tracked open injuries as a single risk-watch item.

    A severe open injury reads as a stop-level "keep load off it" item; otherwise
    a softer "training around it" reminder so the badge stays live for as long as
    any injury is open and clears the moment they are all resolved.
    """
    active = [f for f in open_flags if str(f.get("status") or "") in ACTIVE_FLAG_STATUSES]
    if not active:
        return []

    severe = [
        f
        for f in active
        if str(f.get("severity") or "") == "severe" and str(f.get("status") or "") == "open"
    ]
    if severe:
        return [
            make_risk(
                "active_injury_worse",
                text=f"Open severe injury: {_flag_label(severe[0])}. Keep load off it until cleared.",
            )
        ]

    labels = ", ".join(_flag_label(f) for f in active[:2])
    count = len(active)
    noun = "injury" if count == 1 else "injuries"
    return [
        make_risk(
            "reminder",
            text=f"Tracking {count} open {noun}: {labels}. Train around it.",
        )
    ]
