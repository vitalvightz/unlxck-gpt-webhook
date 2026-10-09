"""Episode-bound, self-reported clinician permissions; never medical verification."""
from collections.abc import Mapping, Sequence
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict

from .injury_checkin import build_injury_label, injury_consequence_tier

_SCOPES = (("rehab",), ("rehab", "training"), ("rehab", "training", "contact"))
_LEVELS = ("rehab_only", "train_no_contact", "train_contact")

LOAD_PERMISSION_CHECKPOINT = "achilles_midportion_reported_load_permission_v1"


class RehabilitationPermission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    level: Literal["gentle_recovery", "loading", "sport_specific", "not_cleared"]


def permits_rehabilitation_loading(injury: Mapping) -> bool:
    report = injury.get("clinician_clearance")
    if not isinstance(report, Mapping) or str(report.get("episode_id")) != str(injury.get("episode_id")):
        return False
    try:
        permission = RehabilitationPermission.model_validate(report.get("rehabilitation_permission"))
    except (ValueError, TypeError):
        return False
    return (bool(injury.get("episode_id")) and injury.get("status") in {"open", "monitoring"}
            and permission.level in {"loading", "sport_specific"})


def achilles_load_permission_reason(injury: Mapping) -> str | None:
    """Applicability of the single reviewed option, without diagnosing readiness."""
    if not permits_rehabilitation_loading(injury):
        return "rehabilitation_loading_not_reported"
    # Only the explicit injury-information answer applies. Legacy training
    # scopes, clinical worksheets and free-text guesses cannot supply this.
    description = str(injury.get("description") or "")
    locations = re.findall(r"\[achilles_site:(midportion|insertional|unknown)\]", description)
    if locations != ["midportion"]:
        return "achilles_midportion_not_confirmed"
    if (injury.get("rehab_medical_gate") or injury.get("progression_assessment_medical_hold")
            or injury.get("medical_hold") or injury.get("restriction_hold")
            or injury.get("latest_reported_status") == "worse"
            or str(injury.get("severity")) not in {"mild", "moderate", "low", "medium"}):
        return "injury_loading_safety_hold"
    return None


def canonical_clearance_scopes(value):
    if not isinstance(value, list) or not all(isinstance(scope, str) for scope in value):
        return None
    if len(set(value)) != len(value):
        return None
    return next((list(scopes) for scopes in _SCOPES if set(value) == set(scopes)), None)


def effective_clinician_clearance(injuries: Sequence[Mapping]):
    reports = []
    for injury in injuries:
        report = injury.get("clinician_clearance")
        if (injury.get("status") not in {"open", "monitoring"} or not isinstance(report, Mapping)
                or not injury.get("episode_id") or str(report.get("episode_id")) != str(injury["episode_id"])):
            continue
        scopes = canonical_clearance_scopes(report.get("scopes"))
        reports.append((len(scopes) - 1 if scopes else 0, scopes is None, injury))
    if not reports:
        return None
    rank = min(item[0] for item in reports)
    limiters = sorted((injury for level, _, injury in reports if level == rank),
                     key=lambda injury: (str(injury.get("id")), str(injury.get("episode_id"))))
    return {
        "level": _LEVELS[rank], "scopes": list(_SCOPES[rank]),
        "requires_update": any(invalid for _, invalid, _ in reports),
        "limited_by": [{"injury_id": str(injury["id"]), "injury_episode_id": str(injury["episode_id"]),
                        "label": injury.get("label") or build_injury_label(injury.get("body_area"), injury.get("description"))}
                       for injury in limiters],
    }


def clinician_clears_baseline(injury: Mapping, *, contact: bool = False) -> bool:
    """Relax only this episode's generic restrictions; hard gates still win."""
    clearance = effective_clinician_clearance([injury])
    if not clearance or clearance["requires_update"]:
        return False
    if str(injury.get("severity") or "").lower() not in {"mild", "moderate", "low", "medium"}:
        return False
    if (injury.get("latest_reported_status") == "worse" or injury.get("rehab_medical_gate")
            or (injury.get("rehab_decision") or {}).get("outcome") == "medical_review"):
        return False
    consequence = injury.get("consequence") if "consequence" in injury else injury_consequence_tier(
        injury.get("body_area"), injury.get("description"), severity=injury.get("severity"))
    if consequence in {"structural", "neuro"}:
        return False
    return ("contact" if contact else "training") in clearance["scopes"]
