"""Bounded seated starter eligibility, not a diagnosis or capacity assessment."""
import re

from fightcamp.injury_negation import remove_negated_phrases

CRITERION = "ankle_lateral_reported_seated_load_v1"
SOURCES = (
    "https://www.jospt.org/doi/10.2519/jospt.2021.0302",
    "https://www.ouh.nhs.uk/media/i0ldiecy/116454sprain.pdf",
    "https://msk-bexley.nhs.uk/conditions/foot-and-ankle-pain/ankle-sprain",
    "https://pmc.ncbi.nlm.nih.gov/articles/PMC8824326/",
)


def unsupported_ankle_presentation(injury):
    text = remove_negated_phrases(" ".join(str(injury.get(k) or "") for k in ("body_area", "description"))).lower()
    return ("[ankle_scope:other]" in text or bool(re.search(
        r"\b(medial|deltoid|syndesmo\w*|high ankle|fracture|break|rupture|structural|unstable|instability|recurrent|giving way|gave way|numb\w*|tingling|deform\w*|cold|discolou?r\w*|cannot walk|unable to (?:walk|bear weight)|non[- ]weight[- ]bearing|bony tenderness)\b", text)))


def seated_ankle_multi_injury_hold(injury, injuries):
    """Both feet move: another active lower-leg/foot injury needs its own advice.

    Conservatively withhold the new bilateral option rather than borrow one
    episode's permission for the other limb. No stored restriction is changed.
    """
    from .rehab_assessment import assessment_identity
    if assessment_identity(injury) != ("ankle", "sprain"):
        return False
    return any(str(other.get("id")) != str(injury.get("id"))
               and other.get("status") != "resolved"
               and assessment_identity(other)[0] in {"ankle", "foot", "toe", "heel", "calf", "achilles"}
               for other in injuries)


def evaluate_ankle_permission(context):
    """Permission for this seated movement only; shared engine checks exposure.

    A clinician-described uncomplicated presentation is an athlete report. It
    does not verify fracture exclusion, ligament grade, ROM, balance or strength.
    No standing capacity is required or inferred for the seated starter.
    """
    from .clinician_clearance import permits_rehabilitation_loading
    from .rehab_assessment import assessment_identity

    injury = context.injury
    def result(status, reason):
        return {"status": status, "reason_code": reason}
    if assessment_identity(injury) != ("ankle", "sprain") or injury.get("side") not in {"left", "right"}:
        return result("unknown", "ankle_uncomplicated_lateral_not_reported")
    if not context.history_complete:
        return result("unknown", "assessment_history_incomplete")
    if (context.medical_hold or injury.get("consequence") in {"structural", "neuro"}
            or injury.get("latest_reported_status") == "worse"
            or any(injury.get(k) for k in ("medical_hold", "restriction_hold", "progression_assessment_medical_hold"))):
        return result("fail", "injury_loading_safety_hold")
    if unsupported_ankle_presentation(injury):
        return result("fail", "ankle_conflicting_or_unsupported_presentation")
    markers = re.findall(r"\[ankle_scope:([^\]]*)\]", str(injury.get("description") or ""))
    if markers != ["uncomplicated_lateral"]:
        return result("unknown", "ankle_uncomplicated_lateral_not_reported")
    if injury.get("severity") not in {"mild", "low"}:
        return result("unknown", "ankle_loading_severity_not_supported")
    if not permits_rehabilitation_loading(injury):
        return result("unknown", "rehabilitation_loading_not_reported")
    return result("pass", "reported_permission_and_seated_option_applicable")
