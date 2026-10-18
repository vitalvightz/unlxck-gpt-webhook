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
    """Exercise-specific veto; shared whole-athlete safety stays authoritative.

    Both arms, trunk/neck control and standing support participate. A mild,
    non-limiting soft-tissue bruise away from the feet/joints is not itself a
    contraindication. This does not measure standing tolerance or grant another
    episode's permission. Unknown anatomy remains conservative.
    """
    from .rehab_assessment import assessment_identity
    from fightcamp.injury_body_region import body_region_for_canonical_location
    from fightcamp.injury_location_registry import canonicalize_location_from_registry

    if assessment_identity(injury) != ("shoulder", "tendonitis"):
        return False
    for other in injuries:
        if str(other.get("id")) == str(injury.get("id")) or other.get("status") == "resolved":
            continue
        if (other.get("consequence") in {"structural", "neuro"}
                or other.get("severity") in {"severe", "high"}
                or any(other.get(k) for k in ("medical_hold", "restriction_hold", "rehab_medical_gate"))):
            return True
        # The planning parser intentionally drops not-limiting notes. Strip
        # only its internal impact marker when identifying mechanical anatomy;
        # keep the original report below and leave planning behaviour unchanged.
        described = {**other, "description": re.sub(r"\s*\[training_impact:[^\]]*\]", "", str(other.get("description") or ""))}
        region, kind = assessment_identity(described)
        region = canonicalize_location_from_registry(region)
        body = body_region_for_canonical_location(region)
        raw_text = " ".join(str(other.get(k) or "") for k in ("body_area", "description")).lower()
        text = remove_negated_phrases(raw_text)
        standing_restriction = re.search(
            r"\b(non[- ]weight[- ]bearing|unable to (?:stand|walk|bear weight)|cannot (?:stand|walk|bear weight)|limping|giving way|unstab\w*|pain (?:with|when|on) (?:standing|walking|weight[- ]bearing))\b", text)
        if standing_restriction or re.search(r"\b(?:no|avoid|restricted|prohibited) (?:standing|weight[- ]bearing|bearing weight)\b", raw_text):
            return True
        minor_bruise = (region in {"shin", "quads", "hamstring", "glute"} and kind == "contusion"
            and other.get("severity") in {"mild", "low"} and other.get("latest_reported_status") != "worse"
            and not re.search(r"\[training_impact:(?:limiting|cant_train)\]", text))
        if minor_bruise:
            continue
        if body in {"upper_limb", "trunk_spine", "lower_limb", "unknown"} or region == "neck":
            return True
        # Known head/face concerns still pass through the existing medical,
        # readiness and clinician restrictions; this helper cannot clear them.
    return False


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
    if injury.get("severity") not in {"mild", "low", "moderate"}:
        return result("unknown", "shoulder_loading_severity_not_supported")
    if not permits_rehabilitation_loading(injury):
        return result("unknown", "rehabilitation_loading_not_reported")
    return result("pass", "reported_permission_and_wall_option_applicable")
