"""Bounded wall-push-up starter eligibility, not a diagnosis or capacity assessment."""
import re

from fightcamp.injury_negation import remove_negated_phrases

CRITERION = "shoulder_cuff_reported_wall_load_v1"
SOURCES = (
    "https://www.orthopt.org/uploads/content_files/files/Rotator_Cuff_CPG.pdf",
    "https://www.rjah.nhs.uk/our-services/therapy/supported-self-care/rotator-cuff-related-shoulder-pain/",
)


def unsupported_shoulder_presentation(injury):
    text = remove_negated_phrases(" ".join(str(injury.get(k) or "") for k in ("body_area", "description"))).lower()
    return ("[shoulder_scope:other]" in text or bool(re.search(
        r"\b(tear|torn|rupture|trauma\w*|fall|fell|fracture|break|structural|unstable|instability|recurrent|dislocat\w*|sublux\w*|giving way|gave way|numb\w*|tingling|pins and needles|loss of sensation|neurolog\w*|radicul\w*|weak\w*|power loss|strength loss|loss of (?:power|function|strength)|cannot (?:lift|raise)|unable to (?:lift|raise)|frozen shoulder|adhesive capsulitis|biceps|labra\w*|acromioclavicular|ac joint|(?:osteo)?arthrit\w*|cervical|surgery|post[- ]?operati\w*)\b", text)))


def wall_shoulder_multi_injury_hold(injury, injuries):
    """Wall push-ups use both arms and standing support.

    Withhold this starter with any other active injury rather than borrow its
    permission or infer tolerance of a bilateral weight-bearing task.
    """
    from .rehab_assessment import assessment_identity
    if assessment_identity(injury) != ("shoulder", "tendonitis"):
        return False
    return any(str(other.get("id")) != str(injury.get("id"))
               and other.get("status") != "resolved"
               for other in injuries)


def evaluate_shoulder_permission(context):
    """Reported diagnosis and loading permission only; no measured capacity.

    The shared engine separately requires actual RESTORE and response evidence.
    """
    from .clinician_clearance import permits_rehabilitation_loading
    from .rehab_assessment import assessment_identity

    injury = context.injury
    def result(status, reason):
        return {"status": status, "reason_code": reason}
    if assessment_identity(injury) != ("shoulder", "tendonitis") or injury.get("side") not in {"left", "right"}:
        return result("unknown", "shoulder_nontraumatic_cuff_not_reported")
    if not context.history_complete:
        return result("unknown", "assessment_history_incomplete")
    if (context.medical_hold or injury.get("consequence") in {"structural", "neuro"}
            or injury.get("latest_reported_status") == "worse"
            or any(injury.get(k) for k in ("medical_hold", "restriction_hold", "progression_assessment_medical_hold"))):
        return result("fail", "injury_loading_safety_hold")
    if unsupported_shoulder_presentation(injury):
        return result("fail", "shoulder_conflicting_or_unsupported_presentation")
    markers = re.findall(r"\[shoulder_scope:([^\]]*)\]", str(injury.get("description") or ""))
    if markers != ["nontraumatic_cuff"]:
        return result("unknown", "shoulder_nontraumatic_cuff_not_reported")
    if injury.get("severity") not in {"mild", "low"}:
        return result("unknown", "shoulder_loading_severity_not_supported")
    if not permits_rehabilitation_loading(injury):
        return result("unknown", "rehabilitation_loading_not_reported")
    return result("pass", "reported_permission_and_wall_option_applicable")
