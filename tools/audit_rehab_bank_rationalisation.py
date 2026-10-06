"""Read-only, reproducible inventory triage; never a clinical review or activation.

Rules identify textual/mechanical evidence, preserve uncertainty, and explain
each decision. They do not establish clinical efficacy from a movement name.
No runtime consumer reads these reports. Only integrity errors affect exit status.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fightcamp.injury_location_registry import canonicalize_location_from_registry  # noqa: E402
from fightcamp.rehab_clinical import (  # noqa: E402
    compose_policy, content_hash, validate_clinical_bank, validate_pathway_catalog,
)
from fightcamp.rehab_pathways import PathwayCatalog  # noqa: E402
from fightcamp.rehab_schema import is_surface_injury_type  # noqa: E402
from tools.rehab_metadata_review_lib import (  # noqa: E402
    REVIEW_FIELDS, classify_movement_archetype, detect_variable_demand_flags, source_hash,
)
from api.contracts.rehab_progression import CAPTURED_FUNCTIONAL_CHECKPOINTS  # noqa: E402
from api.contracts.rehab_assessment import input_definitions  # noqa: E402

CLASSIFICATIONS = (
    "LIVE", "ADVANCED_CANDIDATE", "KEEP_DORMANT", "REPAIR",
    "DUPLICATE_OR_MERGE", "MISPLACED", "DEPRECATE",
)
STAGES = ("calm", "restore", "load", "dynamic", "return")
MECHANICAL_FIELDS = (
    "rehab_stage", "function", "equipment", "load", "impact", "velocity",
    "laterality_applicability", "contraction_type", "sport_specificity",
    "contact_level", "target_regions", "target_tissues",
)
SOURCES = {
    "sprains": {"url": "https://www.nhs.uk/conditions/sprains-and-strains/",
                "scope": "Protection and symptom-based movement; early massage/heat and urgent warning boundaries. Not an advanced protocol."},
    "tendon": {"url": "https://www.nhs.uk/conditions/tendonitis/",
               "scope": "Regional tendon problems require assessed treatment; sudden severe pain may represent rupture. Does not approve any exact resistance variant."},
    "swelling": {"url": "https://www.nhs.uk/conditions/oedema/",
                 "scope": "Unexplained unilateral or severe swelling needs assessment; a swelling label does not establish a drainage mechanism."},
    "eye": {"url": "https://www.nhs.uk/conditions/eye-injuries/",
            "scope": "Eye trauma with vision change, severe pain or other warning signs requires urgent care; generic MSK loading is not justified."},
    "wound": {"url": "https://www.nhs.uk/conditions/cuts-and-grazes/",
              "scope": "Clean and cover small wounds; embedded objects, serious/deep wounds and infection require medical assessment."},
    "blister": {"url": "https://www.nhs.uk/conditions/blisters/",
                "scope": "Do not burst a blister yourself; needle drainage is described as GP treatment, not athlete self-care."},
    "joint": {"url": "https://www.nhs.uk/symptoms/joint-pain/",
              "scope": "Activity modification, assessment and warning boundaries for undiagnosed joint symptoms; not a diagnosis-specific loading protocol."},
}

# Explicit name families are audit search aids, NOT canonical exercise identities.
# Variants retain equipment/range/laterality and type boundaries in the cluster.
SEMANTIC_FAMILIES = (
    ("wrist_cars", r"(?:wrist.*(?:cars|articular rotations)|controlled wrist cars)"),
    ("toe_spread_band", r"(?:toe.*(?:spread|splay).*band|band.*toe.*spread)"),
    ("tendon_gliding", r"tendon glid(?:e|es|ing)"),
    ("towel_toe_curl", r"towel scrunch|toe.*towel.*curl"),
    ("eccentric_wrist_extension", r"(?:eccentric.*(?:wrist extens|reverse wrist curl)|supported eccentric wrist extension)"),
    ("neck_passive_tilt", r"(?:passive.*(?:neck|head).*tilt|passive.*lateral flexion|neck.*passive.*tilt)"),
    ("shoulder_pass_through", r"(?:shoulder dislocat|(?:pvc|stick|dowel).*pass.?through)"),
    ("supine_90_90_breathing", r"(?:90.?90.*breath|supine.*diaphragmatic breath)"),
    ("pigeon_stretch", r"pigeon.*stretch"),
    ("suitcase_carry", r"suitcase carr"),
    ("wall_dead_bug_hold", r"wall dead bug.*iso"),
    ("reverse_hyperextension", r"reverse hyper"),
    ("band_pull_apart", r"(?:band.*pull.?apart|resistance band.*reverse fly)"),
    ("neck_isometric", r"(?:neck.*isometric|(?:lateral flexion|head).*hold)"),
    ("calf_raise", r"(?:calf raise|heel raise)"),
    ("spanish_squat", r"spanish squat"),
    ("hamstring_slider", r"(?:slid(?:er|ing).*hamstring curl|sliding leg curl)"),
    ("terminal_knee_extension", r"terminal knee extens|\btke\b"),
)
HIDDEN = r"\b(?:progress(?:ion|ively)?(?:\s+to)?|advance(?:\s+to)?|increase (?:load|resistance|speed|tempo|rom)|add (?:load|weight|resistance|impact|tempo|band tension)|build toward|later stage)\b|→|->"
MECHANISM = r"\b(?:doms|inflammat\w*|scar tissue|fasci\w*|capsul\w*|tendon healing|drain\w*|adhesion\w*|flush toxins|muscle shortening|activate\w*|instability|impingement)\b"
CLAIM = r"\b(?:flush (?:doms|toxins|inflammation)|break up|release fascial|fascia release|reset capsule|create space|clear pinch|prevent cubital|trapped fascial|bone density support|drain inflammation)\b"
TRAINING = r"\b(?:conditioning|intervals?|airdyne|airbike|row erg|recovery circuit|sparring|shadowboxing|pad work|bag work|combat flow|gi.grip|fight simulation|contact.harden\w*)\b"
GENERIC_STRENGTH = r"\b(?:deadlift|rdl|suitcase carry|farmer.?s carry|turkish get.up|med(?:icine)? ball throw|sledgehammer|weighted plank|cable chop)\b"
UNSAFE_NAME = r"(?:rotational wrist wrenching|cbd topical|facial cupping|sterile drainage|neuro.fascial release|trigeminal nerve floss|resistance band jaw.pull|jaw opening with band|trap bar hang.*neck)"
NEURAL = r"\b(?:nerve (?:tensioner|floss|glide|slider|mobilization)|neural tension)"


def normalise(text):
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    text = re.sub(r"\bw/\b|\bw\b(?=/)", "with", text)
    text = re.sub(r"\bdbs?\b", "dumbbell", text)
    text = re.sub(r"\bkb\b", "kettlebell", text)
    text = re.sub(r"\biso\b", "isometric", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def hits(pattern, text):
    return sorted(set(m.group(0).strip() for m in re.finditer(pattern, text, re.I)))


def affirmative_progression(notes):
    matches, prohibited = [], []
    # Preserve both evidence sets. A sentence-level ban can cover an entire
    # comma/or list ("do not ... add weight ... or increase speed"). Do not let
    # unrelated preceding sentences negate a later affirmative progression.
    for sentence in re.split(r"(?<=[.!?;])\s+|→|->", notes):
        found = hits(HIDDEN, sentence)
        if re.search(r"\b(?:do not|no|never|avoid|must not|without)\b", sentence, re.I):
            prohibited.extend(found)
        else:
            matches.extend(found)
    # An arrow itself is a legacy phase/demand signal, even when a later clause
    # forbids something. It is not a clinically supported progression criterion.
    matches += hits(r"→|->", notes)
    return sorted(set(matches)), sorted(set(prohibited))


def counts(values):
    return dict(sorted(Counter(values).items()))


def display_value(value):
    if value is None:
        return "missing"
    if isinstance(value, list):
        return "+".join(sorted(value)) or "none_required"
    return str(value)


def json_text(value):
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def input_digest(path):
    """Hash Git's LF representation, independent of Windows checkout conversion."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def reachable(policy, stage, checkpoints=CAPTURED_FUNCTIONAL_CHECKPOINTS):
    if stage not in policy.live_stages:
        return False
    if stage in {"calm", "restore"}:
        return True  # Baseline report ladder; not a clinical advanced transition.
    for target in STAGES[2:STAGES.index(stage) + 1]:
        transition = next((t for t in policy.transitions if t.to_stage == target), None)
        if transition is None or not transition.promotable:
            return False
        # The capture registry, rather than a data declaration, owns evaluability.
        if any(r.kind == "functional_checkpoint" and r.checkpoint not in checkpoints
               for r in transition.requirements):
            return False
        if any(r.kind == "input_availability" and r.checkpoint not in input_definitions()
               for r in transition.requirements):
            return False
    return True


def candidate_stages(row):
    """Mechanical plausibility only; never infer medical readiness or a dose."""
    if row["pathway_family"] == "surface_wound_care":
        return []
    if row["canonical_region"] in {"eye", "face", "jaw", "unspecified"}:
        return []
    if row["injury_type"] == "swelling" or row["unsafe_reasons"]:
        return []
    name = normalise(row["name"])
    if re.search(r"\b(?:massage|percuss\w*|contrast|ice|heat|cupping|compression|drain\w*|nerve)\b|foam roll(?:er)?(?:.*(?:sweep|floss|release))?\b", name) and not re.search(r"wall slide", name):
        return []  # A stored LOAD tag alone does not make passive recovery loading.
    if row["review_state"] == "reviewed" and row["rehab_stage"] in STAGES[2:]:
        return [row["rehab_stage"]]
    if re.search(r"\b(?:stretch|traction|distraction|mobilization|mobilisation|glide|circles|cars|opener)\b|pass through", name):
        return []  # A band used for passive/ROM assistance is not active loading.
    if re.search(r"sparring|partner contact|takedown|grappling.*(?:drill|defense|control)|bag work|pad work|shadowbox|punching|wrist locks escape", name):
        return ["return"]
    if re.search(r"hop|jump|pogo|plyo|bound|decelerat|cutting|agility|reactive|ball.*(?:toss|throw|catch)", name):
        return ["dynamic"]
    if re.search(r"isometric|eccentric|curl|raise|press|resisted|resistance|band|squat|rdl|deadlift|bridge|balance|carry|nordic|copenhagen|push up|step down|weight bearing|wall crawl", name):
        return ["load"]
    return []


def non_rehab_destination(row):
    if row["classification"] != "MISPLACED":
        return None
    text = normalise(row["name"])
    if re.search(r"sparring|shadowbox|grappl|defense|fight|gi grip", text):
        return "sport skill/contact preparation; athlete clearance remains required"
    if re.search(r"airdyne|airbike|interval|row erg|conditioning|recovery circuit", text):
        return "conditioning or recovery; split mixed circuits before relocation"
    if re.search(GENERIC_STRENGTH, text) or re.search(r"hammer|sledgehammer", text):
        return "general strength/performance; no injury-specific indication currently established"
    return "general warm-up/mobility/recovery or specialist inventory; compare execution and purpose before relocation"


def debt(row, drill):
    name, notes = row["name"], row["notes"]
    text = f"{name} {notes}"
    row["camp_phase_tokens"] = hits(r"\b(?:GPP|SPP|TAPER)\b", notes)
    row["hidden_progression_matches"], row["prohibited_progression_matches"] = affirmative_progression(notes)
    # A prohibition or quoted diagnosis denial is not an affirmative claim.
    sentences = re.split(r"(?<=[.!?])\s+|→|->", notes)
    positive = [s for s in sentences if not re.search(r"\b(?:not|no|avoid|do not|does not|cannot|without)\b", s, re.I)]
    row["mechanism_matches"] = hits(MECHANISM, " ".join(positive))
    row["mechanism_name_matches"] = hits(MECHANISM, name)
    row["mechanism_debt_kind"] = (
        "clinically_unsafe_implication" if hits(CLAIM, " ".join(positive)) else
        "unsupported_mechanism_language" if row["mechanism_matches"] else
        "harmless_naming_debt" if row["mechanism_name_matches"] else None
    )
    row["variable_demand_flags"] = detect_variable_demand_flags(notes) if row["hidden_progression_matches"] else []
    row["variable_equipment_matches"] = hits(r"\b(?:bodyweight or band|trx or rings|eyes closed or|manual or band|foam roller or ball|various objects|various angles)\b", text)
    row["missing_metadata_fields"] = [f for f in MECHANICAL_FIELDS if drill.get(f) is None]
    row["unknown_metadata_fields"] = [f for f in MECHANICAL_FIELDS if drill.get(f) == "unknown"]
    row["non_rehab_matches"] = hits(TRAINING, name + " " + " ".join(positive))
    row["general_strength_matches"] = hits(GENERIC_STRENGTH, name)
    row["unsafe_reasons"] = []
    if re.search(UNSAFE_NAME, name, re.I):
        row["unsafe_reasons"].append("Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.")
    if row["canonical_region"] == "eye" and row["pathway_family"] != "surface_wound_care":
        row["unsafe_reasons"].append("Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.")
    if row["injury_type"] == "contusion" and re.search(r"massage gun|percuss|lacrosse ball|foam roll", name, re.I):
        row["unsafe_reasons"].append("Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.")
    if re.search(r"tensioner", name, re.I):
        row["unsafe_reasons"].append("Neural tensioning requires a neurological indication and assessment not established by this bank label.")
    if re.search(r"major lifts|various objects|generic mobility flow", name, re.I):
        row["unsafe_reasons"].append("No single reproducible movement identity or demand is specified; retain provenance while reviewing deprecation.")
    row["requires_specialist_indication"] = bool(re.search(NEURAL, text, re.I)) or row["canonical_region"] in {"eye", "face", "jaw"} or bool(re.search(r"\bbfr\b|blood flow restriction", name, re.I))
    row["hidden_progression_kind"] = (
        "legacy_camp_or_demand_change" if row["hidden_progression_matches"] else
        "bounded_self_paced_amount" if re.search(r"\bbuild gradually\b", notes, re.I) else None
    )
    row["source_evidence_ids"] = [
        "eye" if row["canonical_region"] == "eye" else
        "blister" if row["injury_type"] == "blister" else
        "wound" if row["pathway_family"] == "surface_wound_care" else
        "swelling" if row["injury_type"] == "swelling" else
        "tendon" if row["injury_type"] == "tendonitis" else
        "sprains" if row["injury_type"] in {"strain", "sprain"} else "joint"
    ]
    # Non-sprain labels must not inherit sprain treatment. The source here only
    # supports a safety/assessment boundary; not efficacy for this exercise.
    row["evidence_scope"] = "Inventory text/mechanics and existing review provenance; linked guidance supports safety boundaries only, not approval of this exact movement."


def duplicate_clusters(rows, drills):
    proposals = defaultdict(lambda: {"signals": set(), "signature": ""})

    def add(groups, signal):
        for key, ids in sorted(groups.items()):
            if len(ids) < 2:
                continue
            cluster = proposals[tuple(sorted(ids))]
            cluster["signals"].add(signal)
            cluster["signature"] = str(key)

    names, instructions, semantics, exact, global_names, variants = (defaultdict(list) for _ in range(6))
    for row in rows:
        identity, region = row["drill_id"], row["canonical_region"]
        name = normalise(row["name"])
        names[(region, name)].append(identity)
        global_names[name].append(identity)
        # Equipment variants are a search signal, not proof of interchangeability.
        core = re.sub(r"\b(?:dumbbell|kettlebell|barbell|band|banded|resistance|light|weighted|bodyweight|with|without|on|the|a)\b", "", name)
        core = " ".join(core.split())
        if len(core.split()) >= 3:
            variants[(region, row["injury_type"], core)].append(identity)
        stripped = re.sub(r"\b(?:GPP|SPP|TAPER)\s*:", "", row["notes"], flags=re.I)
        if len(normalise(stripped)) >= 35:
            instructions[(region, normalise(stripped))].append(identity)
        for family, pattern in SEMANTIC_FAMILIES:
            if re.search(pattern, name):
                semantics[(region, family)].append(identity)
        exact[(region, row["injury_type"], content_hash({k: v for k, v in drills[identity].items() if k != "id"}))].append(identity)
    add(names, "normalized_name")
    add(instructions, "normalized_instructions_without_camp_labels")
    add(semantics, "curated_movement_family")
    add(exact, "same_region_type_and_content_except_id")
    add(variants, "same_region_type_core_name_equipment_variants")
    # Cross-region copying is explicitly distinct for profile selection, even
    # when movement text matches. Never merge clinical region ownership.
    add({k: v for k, v in global_names.items() if len({r["canonical_region"] for r in rows if r["drill_id"] in v}) > 1}, "same_name_across_distinct_regions")
    index = {r["drill_id"]: r for r in rows}
    clusters = []
    for ids, evidence in sorted(proposals.items()):
        members = [index[i] for i in ids]
        types = {r["injury_type"] for r in members}
        signatures = {tuple(display_value(r[f]) for f in ("equipment", "load", "impact", "velocity", "laterality_applicability", "contraction_type")) for r in members}
        regions = {r["canonical_region"] for r in members}
        same_pair = len(types) == 1 and len(regions) == 1
        signal = evidence["signals"]
        if "same_region_type_and_content_except_id" in signal:
            kind, confidence = "exact_duplicate", "high"
        elif len(regions) > 1 or (len(types) > 1 and all(r["referenced_by_active_profile"] for r in members)):
            kind, confidence = "intentionally_distinct", "high"
        elif len(signatures) > 1 or "curated_movement_family" in signal:
            kind, confidence = "near_duplicate", "requires_variant_review"
        elif "normalized_name" in signal:
            kind, confidence = "uncertain", "same_name_different_instructions_or_unverified_mechanics"
        else:
            kind, confidence = "uncertain", "shared_instruction_may_be_only_a_goal"
        ranked = sorted(members, key=lambda r: (not r["referenced_by_active_profile"], r["review_state"] != "reviewed", bool(re.search(r"_\d+$", r["drill_id"])), r["drill_id"]))
        keep = [r["drill_id"] for r in members if r["referenced_by_active_profile"]] or [ranked[0]["drill_id"]]
        # A reference preference never authorizes cross-type/region migration.
        eligible = same_pair and kind == "exact_duplicate"
        cluster_id = "duplicate_" + hashlib.sha256("\n".join(ids).encode()).hexdigest()[:16]
        clusters.append({
            "cluster_id": cluster_id, "drill_ids": list(ids), "signals": sorted(signal),
            "classification": kind, "confidence": confidence,
            "canonical_region": members[0]["canonical_region"] if len(regions) == 1 else None,
            "canonical_regions": sorted(regions), "injury_types": sorted(types),
            "canonical_identity_candidates_to_keep": sorted(keep),
            "ids_for_later_deprecation_review": sorted(set(ids) - set(keep)) if eligible else [],
            "preserve_source_history": True,
            "profile_reference_migration_required": any(r["referenced_by_active_profile"] for r in members if r["drill_id"] not in keep),
            "profile_reference_review_required": any(r["referenced_by_active_profile"] for r in members),
            "rationale": "Exact same region/type/content excluding ID." if eligible else
                "Same movement signal; compare range, equipment, laterality, demand and indication before merging. Different symptom/diagnosis labels retain separate profile ownership.",
            "recommended_next_action": "Review unsuffixed preferred identity; archive all provenance and migrate references only in a separate controlled PR." if eligible else
                "Manual comparison only; preserve all identities and exact type/region boundaries. Shared mechanics alone is not clinical interchangeability.",
        })
    return clusters


def classify(row, exact_duplicate_ids, checkpoints=CAPTURED_FUNCTIONAL_CHECKPOINTS, assessment_inputs=None):
    flags = []
    if row["duplicate_cluster_ids"]:
        flags.append("duplicate")
    if row["hidden_progression_matches"]:
        flags.append("hidden_progression")
    if row["mechanism_debt_kind"]:
        flags.append("mechanism_claim")
    if row["variable_demand_flags"] or row["variable_equipment_matches"]:
        flags.append("variable_demand")
    if row["missing_metadata_fields"] or row["unknown_metadata_fields"]:
        flags.append("missing_metadata")
    candidates = candidate_stages(row)
    if candidates and not row["referenced_by_active_profile"]:
        flags.append("advanced_candidate")
    if row["non_rehab_matches"] or row["general_strength_matches"]:
        flags.append("non_rehab_like")
    row["secondary_flags"] = sorted(flags)
    row["plausible_future_stages"] = candidates if not row["referenced_by_active_profile"] else []
    live = any(ref["stage_live"] and ref["reachable_in_principle"] for ref in row["active_profile_references"])
    if live and row["review_state"] == "reviewed":
        category = "LIVE"
        reason = "Current matching ledger review and exact active profile prescription in a live, reachable baseline stage."
        action = "Preserve identity, content hash and prescription. Audit any secondary flag without rewriting this PR."
    elif row["unsafe_reasons"]:
        category = "DEPRECATE"
        reason = " ".join(row["unsafe_reasons"])
        action = "Separate safety/content review; retain ID and provenance until removal and every consumer are assessed."
    elif row["drill_id"] in exact_duplicate_ids:
        category = "DUPLICATE_OR_MERGE"
        reason = "Materially identical content under another ID in the same canonical region and injury type; preserve the preferred identity."
        action = "Consolidate only after source-history and profile-reference migration review. Do not delete automatically."
    elif ((row["pathway_family"] == "unspecified_fallback" and not row["requires_specialist_indication"] and
           (hits(TRAINING, row["name"]) or row["general_strength_matches"])) or
          re.search(r"recovery circuit|conditioning interval|fight simulation|gi.grip|visual meditation|stroop test|virtual reality", row["name"] + " " + row["notes"], re.I)):
        category = "MISPLACED"
        reason = "Performance/recovery task without an injury-specific reviewed indication; generic fallback ownership does not establish rehab suitability."
        action = "Consider conditioning, general strength, warm-up, recovery or sport skill inventory; check consumers before any move."
    elif row["pathway_family"] == "surface_wound_care":
        category = "KEEP_DORMANT"
        reason = "Separate wound-care inventory outside the MSK review ledger and active-profile footprint; phase-based care notes need their own audit."
        action = "Keep separate from automatic MSK loading. Review wound-specific indications and legacy helper access before changes."
    elif row["requires_specialist_indication"]:
        category = "KEEP_DORMANT"
        reason = "A specialist neurological/head-face indication is not established; absence from ordinary MSK profiles is intentional safety separation."
        action = "Leave inactive; seek condition-specific review before deciding whether this belongs in another medically supervised pathway."
    elif (row["camp_phase_tokens"] or row["hidden_progression_matches"] or
          row["variable_equipment_matches"] or row["mechanism_debt_kind"] == "clinically_unsafe_implication"):
        category = "REPAIR"
        reason = "Named movement may be useful, but the current instructions carry legacy phase/progression, variable equipment or unsupported mechanism debt."
        action = "Fix one movement and demand; preserve ID/history; verify regional evidence before mechanical/clinical review."
    elif candidates and row["review_state"] == "reviewed":
        category = "ADVANCED_CANDIDATE"
        reason = "Reviewed fixed active loading/impact mechanics, currently dormant; stored review/stage does not activate a profile."
        action = "Review regional prescription evidence, clinical transitions and actually captured functional inputs before any stage activation."
    elif row["review_state"] == "reviewed":
        category = "KEEP_DORMANT"
        reason = "Reviewed inventory outside active prescriptions; passive recovery or a non-advanced movement is not loading merely because of a legacy stage tag. Reviewed unknowns remain unknown."
        action = "Retain provenance; inspect regional indication and stage/function fit before any future use. Do not fabricate demand to fill intentional unknowns."
    elif row["missing_metadata_fields"] or row["unknown_metadata_fields"]:
        category = "REPAIR"
        reason = "Movement identity is recognizable but mechanical classification is incomplete; no precision is inferred from the name."
        action = "Confirm execution/range/equipment, then review minimal metadata only if worth regional use."
    else:
        category = "KEEP_DORMANT"
        reason = "Useful inventory outside the current active prescriptions; no applicable production profile approval is established."
        action = "Retain for targeted regional review; dormancy alone does not justify removal."
    row.update(classification=category, rationale=reason, recommended_next_action=action)
    row["likely_non_rehab_destination"] = non_rehab_destination(row)
    if live:
        dormant = []
    else:
        dormant = []
        if row["pathway_family"] == "surface_wound_care":
            dormant.append("outside_active_MSK_profile_model; legacy wound-care helper can still enumerate this inventory")
        if not row["matching_active_profile_ids"]:
            dormant.append("no_exact_active_region_type_profile")
        if not row["referenced_by_active_profile"]:
            dormant.append("not_an_active_profile_prescription")
        if row["review_state"] != "reviewed":
            dormant.append("clinical_mechanical_review_incomplete_or_stale")
        if candidates:
            dormant.append("advanced_stage_not_live_or_not_prescribed; regional_criteria_and_input_review_required")
    row["why_dormant"] = dormant
    row["advanced_candidate_assessment"] = None
    if candidates and not live:
        row["advanced_candidate_assessment"] = {
            "candidate_stages": candidates,
            "regional_indication_requires_clinical_review": True,
            "fallback_inventory_boundary": "An unspecified bank identity can be a mechanical candidate; it does not establish an injury diagnosis or authorize a profile to prescribe it. Regional indication and explicit source-backed ownership must be reviewed." if row["injury_type"] == "unspecified" else None,
            "mechanical_demand": {f: row[f] for f in MECHANICAL_FIELDS},
            "mechanical_evidence": row["name"],
            "why_stage_could_fit": "Resistance/control suggests LOAD; impact/reactivity suggests DYNAMIC; sport exposure suggests RETURN. This is a screening hypothesis, not a prescription or evidence of readiness.",
            "drill_needs_repair": category == "REPAIR" or bool(row["hidden_progression_matches"] or row["variable_equipment_matches"]),
            "metadata_or_individual_demand_needs_assessment": bool(row["missing_metadata_fields"] or row["unknown_metadata_fields"]),
            "current_content_problems": [*row["hidden_progression_matches"], *row["variable_equipment_matches"], *row["missing_metadata_fields"], *row["unknown_metadata_fields"]],
            "readiness_class": "GOOD_FIXED_MECHANICS_GATE_NOT_READY" if category == "ADVANCED_CANDIDATE" else "MOVEMENT_IDENTITY_ONLY_REPAIR_OR_PLACEMENT_REVIEW_FIRST",
            "profile_evidence_missing": True,
            "evidence_missing_detail": "No active reviewed prescription approves this identity in its candidate stage. Existing movement sources do not establish regional advanced readiness.",
            "transition_criteria_missing": not any(ref["advanced_transition_promotable"] for ref in row["matching_profile_stage_gates"]),
            "captured_functional_checkpoints": sorted(checkpoints),
            "required_product_inputs_not_captured": "A regional source must first define which strength/function/impact/skill inputs are actually necessary, then compare them with the capture registry. No current requirement may be inferred from a movement name or proxied by another signal.",
            "safety_blocks": ["identity_not_an_advanced_live_prescription", "regional_transition_and_input_evaluability_review_required", "complete_episode_history_and_no_unresolved_setback_still_required"],
        }
        registered_inputs = input_definitions() if assessment_inputs is None else assessment_inputs
        if registered_inputs:
            available_inputs = sorted(
                key for key, (_, protocol) in registered_inputs.items()
                if (row["canonical_region"], row["injury_type"]) == (protocol.region, protocol.injury_type))
            if available_inputs:
                row["advanced_candidate_assessment"]["captured_assessment_inputs"] = available_inputs


def build_audit(bank, ledger, pathways, *, captured_checkpoints=CAPTURED_FUNCTIONAL_CHECKPOINTS, captured_assessment_inputs=None):
    """Return report + duplicate clusters, without mutating any input object."""
    catalog = PathwayCatalog.model_validate(pathways)
    policies = tuple(compose_policy(catalog, p) for p in catalog.profiles)
    errors = validate_pathway_catalog(catalog) + validate_clinical_bank(policies, bank)
    active = [p for p in policies if p.status == "active" and p.activation == "live"]
    review = {}
    for item in ledger:
        if item["drill_id"] in review:
            errors.append("duplicate ledger ID: " + item["drill_id"])
        review[item["drill_id"]] = item
        if item.get("review_state") not in {"reviewed", "needs_review"}:
            errors.append("unknown ledger review state: " + item["drill_id"])
    family_map = {t: f.family_id for f in catalog.families for t in f.injury_types}
    references = defaultdict(list)
    for p in active:
        for rx in p.prescriptions:
            references[rx.drill_id].append({
                "policy_id": p.policy_id, "stage": rx.stage, "stage_live": rx.stage in p.live_stages,
                "reachable_in_principle": reachable(p, rx.stage, captured_checkpoints),
                "advanced_transition_promotable": any(t.to_stage == rx.stage and t.promotable for t in p.transitions),
            })
    rows, drills = [], {}
    for group_index, group in enumerate(bank):
        location, kind = group["location"], group["type"]
        region = canonicalize_location_from_registry(location)
        for drill in group["drills"]:
            identity = drill["id"]
            if identity in drills:
                errors.append("duplicate bank ID: " + identity)
            drills[identity] = drill
            current_source = source_hash(drill_id=identity, location=location, injury_type=kind,
                                         name=drill["name"], notes=drill["notes"])
            record = review.get(identity)
            surface = is_surface_injury_type(kind)
            if not record and not surface:
                errors.append("MSK identity missing from review ledger: " + identity)
            state = record["review_state"] if record else "outside_msk_review_ledger" if surface else "needs_review"
            if record and record["source_hash"] != current_source:
                state = "stale"
                errors.append("stale ledger source hash: " + identity)
            refs = sorted(references[identity], key=lambda r: (r["policy_id"], r["stage"]))
            matching = [p for p in active if p.region == region and p.injury_type == kind]
            row = {
                "drill_id": identity, "group_index": group_index, "group_location": location,
                "group_phase_progression": group.get("phase_progression"), "canonical_region": region,
                "injury_type": kind, "pathway_family": family_map.get(kind, "surface_wound_care" if surface else "unspecified_fallback"),
                "name": drill["name"], "notes": drill["notes"], "review_state": state,
                "source_hash": record.get("source_hash") if record else None,
                "current_source_hash": current_source, "current_content_hash": content_hash(drill),
                "source_history": record.get("source_history", []) if record else [],
                "evidence_notes": drill.get("evidence_notes"),
                "review_version": record.get("review_version") if record else None,
                "movement_archetype": record.get("movement_archetype") if record else classify_movement_archetype(drill["name"], drill["notes"]),
                "mechanical_metadata_is_reviewed": state == "reviewed",
                "active_profile_references": refs,
                "referenced_by_active_profile": bool(refs),
                "profile_ids": sorted({r["policy_id"] for r in refs}),
                "stages_using_identity": [s for s in STAGES if any(r["stage"] == s for r in refs)],
                "live_progression_path_reachable": any(r["reachable_in_principle"] for r in refs),
                "reachability_scope": "In-principle profile/baseline availability; athlete eligibility, severity, clearance, side, setbacks and history remain authoritative.",
                "matching_active_profile_ids": sorted(p.policy_id for p in matching),
                "matching_profile_stage_gates": [{"policy_id": p.policy_id, "live_stages": list(p.live_stages), "advanced_transition_promotable": any(t.promotable for t in p.transitions), "sources": list(p.evidence_sources)} for p in matching],
                **{f: drill.get(f) for f in MECHANICAL_FIELDS},
                "duplicate_cluster_ids": [],
            }
            debt(row, drill)
            if refs and state != "reviewed":
                errors.append("active profile references non-reviewed/stale identity: " + identity)
            if state == "reviewed" and record and any(record.get("proposed", {}).get(f) != drill.get(f) for f in REVIEW_FIELDS):
                errors.append("reviewed metadata differs from applied bank: " + identity)
            rows.append(row)
    for identity in sorted(set(review) - set(drills)):
        errors.append("ledger identity missing from bank: " + identity)
    rows.sort(key=lambda r: r["drill_id"])
    clusters = duplicate_clusters(rows, drills)
    index = {r["drill_id"]: r for r in rows}
    duplicate_ids = set()
    for cluster in clusters:
        for identity in cluster["drill_ids"]:
            index[identity]["duplicate_cluster_ids"].append(cluster["cluster_id"])
        if cluster["classification"] == "exact_duplicate":
            duplicate_ids.update(cluster["ids_for_later_deprecation_review"])
    for row in rows:
        classify(row, duplicate_ids, captured_checkpoints, captured_assessment_inputs)
    profiles = []
    for policy in sorted(active, key=lambda p: p.policy_id):
        candidates = [r for r in rows if policy.policy_id in r["matching_active_profile_ids"] and r["plausible_future_stages"]]
        fallback = [r for r in rows if r["canonical_region"] == policy.region and r["injury_type"] == "unspecified" and r["plausible_future_stages"] and r["classification"] not in {"MISPLACED", "DEPRECATE"}]
        profiles.append({
            "policy_id": policy.policy_id, "region": policy.region, "injury_type": policy.injury_type,
            "pathway_family": policy.pathway_family, "content_hash": policy.content_hash,
            "live_stages": list(policy.live_stages),
            "prescription_ids": sorted(r.drill_id for r in policy.prescriptions),
            "advanced_candidates": [r["drill_id"] for r in candidates],
            "unassigned_regional_inventory_candidates": [r["drill_id"] for r in fallback],
            "fixed_reviewed_advanced_candidates": [r["drill_id"] for r in candidates if r["classification"] == "ADVANCED_CANDIDATE"],
            "no_viable_advanced_candidate": not candidates and not fallback,
            "no_exact_type_advanced_candidate": not candidates,
            "advanced_gate_status": [{"transition": t.key, "promotable": t.promotable, "closed_reason": t.closed_reason,
                                      "clinical_criteria": [r.model_dump() for r in t.requirements if r.basis == "clinical"]} for t in policy.transitions],
        })
    live_rows = [r for r in rows if r["classification"] == "LIVE"]
    buckets = {key: sum(r["classification"] == key for r in rows) for key in CLASSIFICATIONS}
    potential = sum(buckets[k] for k in ("ADVANCED_CANDIDATE", "KEEP_DORMANT", "REPAIR"))
    summary = {
        "total_groups": len(bank), "total_drills": len(rows), "primary_classification_counts": buckets,
        "drills_by_injury_type": counts(r["injury_type"] for r in rows),
        "drills_by_canonical_region": counts(r["canonical_region"] for r in rows),
        "drills_by_bank_location": counts(r["group_location"] for r in rows),
        "drills_by_pathway_family": counts(r["pathway_family"] for r in rows),
        "review_state_counts": counts(r["review_state"] for r in rows),
        "live_unique_drills": len(live_rows), "dormant_from_active_profile_model": len(rows) - len(live_rows),
        "reviewed_referenced_active_unique_drills": sum(r["review_state"] == "reviewed" and r["referenced_by_active_profile"] for r in rows),
        "live_unique_identities_by_stage": {s: len({r["drill_id"] for r in live_rows if s in r["stages_using_identity"]}) for s in STAGES},
        "active_profile_count": len(profiles),
        "promotable_advanced_transitions": sum(t.promotable for p in active for t in p.transitions),
        "captured_functional_checkpoints": sorted(captured_checkpoints),
        "captured_assessment_inputs": sorted(input_definitions()),
        "active_profile_stage_counts": counts("+".join(p["live_stages"]) for p in profiles),
        "profiles_with_load_or_above": [p["policy_id"] for p in profiles if set(p["live_stages"]) & {"load", "dynamic", "return"}],
        "profiles_without_viable_advanced_candidate": [p["policy_id"] for p in profiles if p["no_viable_advanced_candidate"]],
        "profiles_without_exact_type_advanced_candidate": [p["policy_id"] for p in profiles if p["no_exact_type_advanced_candidate"]],
        "profiles_without_fixed_reviewed_advanced_candidate": [p["policy_id"] for p in profiles if not p["fixed_reviewed_advanced_candidates"]],
        "metadata_distributions": {f: counts(display_value(r[f]) for r in rows) for f in MECHANICAL_FIELDS},
        "missing_metadata_counts": {f: sum(f in r["missing_metadata_fields"] for r in rows) for f in MECHANICAL_FIELDS},
        "unknown_metadata_counts": {f: sum(f in r["unknown_metadata_fields"] for r in rows) for f in MECHANICAL_FIELDS},
        "msk_missing_metadata_counts": {f: sum(f in r["missing_metadata_fields"] for r in rows if r["pathway_family"] != "surface_wound_care") for f in MECHANICAL_FIELDS},
        "duplicate_cluster_count": len(clusters), "duplicate_cluster_kinds": counts(c["classification"] for c in clusters),
        "duplicate_unique_drills": sum(bool(r["duplicate_cluster_ids"]) for r in rows),
        "hidden_progression_drills": sum(bool(r["hidden_progression_matches"]) for r in rows),
        "camp_phase_instruction_drills": sum(bool(r["camp_phase_tokens"]) for r in rows),
        "mechanism_debt_drills": sum(bool(r["mechanism_debt_kind"]) for r in rows),
        "mechanism_debt_kinds": counts(r["mechanism_debt_kind"] or "none" for r in rows),
        "likely_non_rehab_secondary_flags": sum("non_rehab_like" in r["secondary_flags"] for r in rows),
        "plausible_future_stage_candidates": {s: sum(s in r["plausible_future_stages"] for r in rows) for s in STAGES[2:]},
        "fixed_reviewed_advanced_stage_candidates": {s: sum(s in r["plausible_future_stages"] and r["classification"] == "ADVANCED_CANDIDATE" for r in rows) for s in STAGES[2:]},
        "percent_bank_live": round(100 * len(live_rows) / len(rows), 2) if rows else 0,
        "percent_bank_reviewed": round(100 * sum(r["review_state"] == "reviewed" for r in rows) / len(rows), 2) if rows else 0,
        "percent_msk_reviewed": round(100 * sum(r["review_state"] == "reviewed" for r in rows) / sum(r["pathway_family"] != "surface_wound_care" for r in rows), 2) if any(r["pathway_family"] != "surface_wound_care" for r in rows) else 0,
        "percent_dormant_potentially_useful": round(100 * potential / len(rows), 2) if rows else 0,
        "percent_likely_removable_eventually": round(100 * (buckets["DEPRECATE"] + buckets["DUPLICATE_OR_MERGE"]) / len(rows), 2) if rows else 0,
        "legacy_surface_helper_inventory": sum(r["pathway_family"] == "surface_wound_care" for r in rows),
    }
    summary["hidden_progression_breakdowns"] = {key: counts(r[key] for r in rows if r["hidden_progression_matches"]) for key in ("injury_type", "canonical_region", "review_state", "classification")}
    summary["classification_breakdowns"] = {
        dimension: {value: {bucket: sum(r[dimension] == value and r["classification"] == bucket for r in rows) for bucket in CLASSIFICATIONS}
                    for value in sorted({r[dimension] for r in rows})}
        for dimension in ("pathway_family", "canonical_region", "injury_type")
    }
    summary["primary_bucket_id_lists"] = {bucket: [r["drill_id"] for r in rows if r["classification"] == bucket] for bucket in CLASSIFICATIONS}
    return {
        "schema_version": 1, "classification_enum": list(CLASSIFICATIONS),
        "scope": "Whole-bank inventory triage; primary buckets exclusive, secondary flags overlap. No clinical review, deletion or activation. Surface inventory is outside the active MSK profile model, not proven inaccessible to all legacy helpers.",
        "method": "Ordered LIVE, unsafe/low-value DEPRECATE, exact same-pair duplicate surplus, explicit MISPLACED, separate/specialist KEEP_DORMANT, textual REPAIR, fixed-reviewed ADVANCED_CANDIDATE, incomplete REPAIR, KEEP_DORMANT. Rules are conservative screening; semantic efficacy/indications remain uncertain.",
        "evidence_sources": SOURCES, "summary": summary, "profiles": profiles,
        "integrity_errors": sorted(set(errors)), "drills": rows,
    }, {"schema_version": 1, "method": "Overlapping evidence clusters, not disjoint merge groups; a drill can appear in multiple signals. Only content-identical same-region/type surplus receives primary DUPLICATE_OR_MERGE. Exact IDs valid; aliases use existing location registry.", "clusters": clusters}


def markdown(report, duplicates):
    s = report["summary"]
    lines = ["# Rehab-bank rationalisation", "", "## Executive summary", "",
             f"Current inputs contain **{s['total_groups']} groups / {s['total_drills']} drills**, **{s['active_profile_count']} active profiles**, and **{s['live_unique_drills']} unique live MSK identities** ({s['percent_bank_live']}% of the whole bank).",
             "", "This report is generated read-only: the audit itself never rewrites bank content, review history, profile hashes or stage activation. It describes current selectable inventory; retired exact identities and their complete provenance are preserved separately in data/rehab_archive/exact_duplicates.json when consolidation has been applied. Each retained drill has exactly one primary bucket. Secondary flags overlap; duplicate clusters overlap and must not be summed as distinct drills.",
             "", "Classification is evidence-backed inventory triage, not a clinical approval of dormant content. Name-based future-stage screening proposes a mechanical hypothesis only. Missing metadata remains missing; no dose, pain ceiling or checkpoint is invented.",
             "", "| Primary bucket | Drills |", "| --- | ---: |"]
    lines += [f"| {k} | {v} |" for k, v in s["primary_classification_counts"].items()]
    lines += ["", f"Reviewed: **{s['review_state_counts'].get('reviewed', 0)} / {s['total_drills']} ({s['percent_bank_reviewed']}%)**; MSK-only reviewed percentage: **{s['percent_msk_reviewed']}%**. Dormant potentially useful: **{s['percent_dormant_potentially_useful']}%** (ADVANCED_CANDIDATE + KEEP_DORMANT + REPAIR). Likely eventually removable: **{s['percent_likely_removable_eventually']}%** (DEPRECATE + exact duplicate surplus); MISPLACED means relocation review, not removal.",
              "", "## Production footprint", "", "| Live stage | Unique identities |", "| --- | ---: |"]
    lines += [f"| {k.upper()} | {v} |" for k, v in s["live_unique_identities_by_stage"].items()]
    lines += ["", f"Active profiles by stages: `{json.dumps(s['active_profile_stage_counts'], sort_keys=True)}`. Reviewed identities referenced by active profiles: **{s['reviewed_referenced_active_unique_drills']}**. Advanced live profiles: **{len(s['profiles_with_load_or_above'])}**.",
              "", "Reachability means the profile/baseline can select a stage in principle; it is not clearance for every athlete. Severity, red flags, clinician restrictions, side, complete history and setbacks remain authoritative. CALM/RESTORE use the existing report ladder. Advanced availability requires a live target, a promotable clinical transition and captured required checkpoints.",
              "", "### Surface inventory caveat", "", f"**{s['legacy_surface_helper_inventory']} wound-care identities** are outside the MSK review ledger and the 64-profile model. They are not counted as live MSK work. `fightcamp/rehab_protocols.py::_collect_surface_drills` and `_rehab_drills_for_phase` can still enumerate this inventory; main generation renders a single wound-care note. Therefore 'dormant from active profiles' does not mean unreachable by every legacy helper.",
              "", "**Separate safety finding:** `heel_blister_sterile_drainage_if_tense` instructs needle drainage without limiting it to a clinician. NHS blister guidance says not to burst a blister yourself and describes sterile-needle drainage as GP treatment. It is a DEPRECATE candidate and must be addressed in a separate surface-content/consumer review; this PR does not change behavior.",
              "", "## Breakdown", ""]
    for key, heading in (("drills_by_injury_type", "Injury type"), ("drills_by_canonical_region", "Canonical region"), ("drills_by_pathway_family", "Pathway family"), ("review_state_counts", "Review state")):
        lines += [f"### {heading}", "", f"| {heading} | Drills |", "| --- | ---: |"]
        lines += [f"| {k} | {v} |" for k, v in s[key].items()]
        lines += [""]
    lines += ["Aliases are resolved by the existing registry: bicep → biceps, hamstrings → hamstring, glutes → glute, lower_back → lower back, upper_back → upper back. The report retains the original group location/index; no bank vocabulary is rewritten.", "", "## Mechanical metadata", ""]
    for dimension, heading in (("pathway_family", "Family classification"), ("canonical_region", "Region classification")):
        lines += [f"### {heading}", "", "| Identity | " + " | ".join(CLASSIFICATIONS) + " |", "| --- | " + " | ".join("---:" for _ in CLASSIFICATIONS) + " |"]
        lines += ["| " + value + " | " + " | ".join(str(buckets[b]) for b in CLASSIFICATIONS) + " |" for value, buckets in s["classification_breakdowns"][dimension].items()]
        lines += [""]
    for field, values in s["metadata_distributions"].items():
        lines += [f"### {field}", "", "| Value | Drills |", "| --- | ---: |"]
        lines += [f"| {k} | {v} |" for k, v in values.items()]
        lines += [""]
    lines += ["Surface loading fields are intentionally absent. Empty equipment lists mean no equipment required; they are not missing. The JSON separates whole-bank missing counts, MSK-only missing counts and explicit unknowns. Unreviewed keyword functions/archetypes are not verified mechanics. Group phase availability is orthogonal to rehab_stage; the audit flags camp-phase demand changes inside instructions, not availability alone.", "", "## Biggest debt areas", "",
              f"- **{s['duplicate_cluster_count']} duplicate/near-duplicate/uncertain clusters**, involving **{s['duplicate_unique_drills']} unique drills**; kinds: `{json.dumps(s['duplicate_cluster_kinds'], sort_keys=True)}`.",
              f"- **{s['camp_phase_instruction_drills']}** drills contain camp-phase instructions; **{s['hidden_progression_drills']}** contain arrows or hidden progression signals.",
              f"- **{s['mechanism_debt_drills']}** have mechanism-language or naming flags; kinds: `{json.dumps(s['mechanism_debt_kinds'], sort_keys=True)}`.",
              f"- **{s['likely_non_rehab_secondary_flags']}** have general-training/performance signals. Only explicit indication-free tasks receive primary MISPLACED; a compound lift or mobility exercise is not automatically non-rehab.",
              "", "### Hidden progression breakdowns", ""]
    for field, values in s["hidden_progression_breakdowns"].items():
        lines += [f"| {field} | Flagged drills |", "| --- | ---: |"]
        lines += [f"| {k} | {v} |" for k, v in values.items()]
        lines += [""]
    live_flags = [r for r in report["drills"] if r["classification"] == "LIVE" and (r["hidden_progression_kind"] or r["mechanism_debt_kind"] == "clinically_unsafe_implication")]
    lines += ["### Live instruction findings", ""]
    if live_flags:
        lines += [f"- `{r['drill_id']}`: {r['hidden_progression_kind'] or r['mechanism_debt_kind']}. Existing bounded self-paced wording must be distinguished from changing load/impact/contact; review separately, preserve its hash here." for r in live_flags]
    else:
        lines += ["No live hidden-demand progression or unsafe mechanism implication detected by these conservative rules. This is a textual screen, not proof of absence of every clinical issue."]
    lines += ["", "## Advanced inventory: good mechanics versus repair debt", "", "| Candidate stage | All dormant screening candidates | Fixed reviewed candidates |", "| --- | ---: | ---: |"]
    lines += [f"| {stage.upper()} | {s['plausible_future_stage_candidates'][stage]} | {s['fixed_reviewed_advanced_stage_candidates'][stage]} |" for stage in STAGES[2:]]
    lines += ["", "Fixed reviewed candidates are mechanically defined movements; their exact regional prescriptions and readiness gates still need clinical evidence. Reviewed unknown load/impact stays unknown and requires individual demand assessment, not invented precision. Reviewed passive massage/rolling entries tagged LOAD are deliberately excluded from loading candidates. Other screened candidates often require substantial repair and are NOT ready for review/activation. Unspecified-type regional inventory is screened mechanically too, but its indication/ownership is unassigned; it is never silently converted into a diagnosis or borrowed across profile types. Each JSON row states content defects, review state, stage hypothesis, evidence/transition/input gaps and safety blocks.", "", "### Active-profile candidate matrix", "", "| Profile | Live stages | Fixed reviewed advanced IDs | Other exact-type candidates | Unassigned regional candidates |", "| --- | --- | --- | ---: | ---: |"]
    for p in report["profiles"]:
        lines.append(f"| {p['policy_id']} | {', '.join(p['live_stages'])} | {', '.join(p['fixed_reviewed_advanced_candidates']) or 'none'} | {len(p['advanced_candidates']) - len(p['fixed_reviewed_advanced_candidates'])} | {len(p['unassigned_regional_inventory_candidates'])} |")
    lines += ["", "Profiles with no screened viable advanced inventory: " + (", ".join(f"`{p}`" for p in s["profiles_without_viable_advanced_candidate"]) or "none") + ".",
              "", "Profiles with no exact-type candidate (regional unassigned inventory may exist): " + (", ".join(f"`{p}`" for p in s["profiles_without_exact_type_advanced_candidate"]) or "none") + ".",
              "", "Profiles with no fixed reviewed advanced inventory: " + (", ".join(f"`{p}`" for p in s["profiles_without_fixed_reviewed_advanced_candidate"]) or "none") + ".",
              "", f"Promotable advanced transitions: **{s['promotable_advanced_transitions']}**. Captured clinical functional checkpoints: `{json.dumps(s['captured_functional_checkpoints'])}`. Captured assessment availability inputs: `{json.dumps(s['captured_assessment_inputs'])}`. Which regional strength/function/tolerance tests are necessary remains a literature/clinical decision; the audit does not substitute whole-athlete readiness, elapsed time, session counts or a different input. This audit activates no stage.",
              ""]
    lines += ["## Deprecation candidates", "", "These are candidates for a separate review, not deletion instructions. Every ID remains in the bank.", ""]
    lines += [f"- `{r['drill_id']}`: {r['rationale']}" for r in report["drills"] if r["classification"] == "DEPRECATE"]
    lines += ["", "## Misplaced candidates", "", "| ID | Likely destination |", "| --- | --- |"]
    lines += [f"| {r['drill_id']} | {r['likely_non_rehab_destination']} |" for r in report["drills"] if r["classification"] == "MISPLACED"]
    lines += ["", "## Recommended cleanup order", "",
              "**P0:** inspect live flags without hash changes here; bounded self-paced ankle wording is not a hidden LOAD gate. Preserve the surface/helper identity-and-content approval boundary from #2740: unsafe needle inventory is archival, not automatic athlete guidance. Any newly discovered critical runtime bug gets a separate PR.",
              "", "**P1:** consolidate exact same-pair surplus IDs first, preserving review/source history and migrating any references explicitly. Review DEPRECATE items (eye-as-MSK, neural tensioners, invasive/speculative/forceful identities and percussion on bruises). Review MISPLACED fallback performance/conditioning tasks. Never merge cross-label clinical prescriptions merely because mechanics match.",
              "", "**P2:** repair a small useful set of named movements: remove GPP/SPP/TAPER demand changes, select one execution/equipment/range, remove unsupported mechanism claims and then review truthful metadata. Keep uncertain near duplicates pending comparison.",
              "", "**P3:** start regional advanced prescription/criteria review from fixed reviewed LOAD candidates. Achilles floor-level lowering, elbow/forearm supported wrist extension and wrist flexion are strong existing mechanical anchors; subtype ambiguity and condition-specific limits still need evidence and captured inputs.",
              "", "**P4:** lower-value dormant inventory, generic fallback and specialist-indication content can wait; absence from current profiles is not evidence of obsolescence.",
              "", "**Best next PR after rationalisation:** consolidate duplicated calf/knee identities and target a small tendon resistance set (Achilles and elbow/forearm/wrist). Verify region/subtype-specific prescription evidence and readiness criteria, define and capture exactly the functional inputs required, then selectively open LOAD only for profiles whose full gate is evaluable. If subtype/input ambiguity persists, ship repair/input capture while keeping LOAD closed. No blanket LOAD rollout.",
              "", "## Evidence and method limits", ""]
    lines += [f"- [{key}]({value['url']}): {value['scope']}" for key, value in SOURCES.items()]
    lines += ["", "Sources were read directly for this audit. They support safety/classification boundaries, not every drill's effectiveness. Inventory evidence is the actual name/notes, current metadata, ledger review/source history and exact profile references, all retained per row. Keyword rules cannot determine diagnosis or semantic equivalence reliably; ambiguous clusters are marked uncertain/near-duplicate, and no unreviewed movement is approved.",
              "", "## Rerun and verification", "",
              "Run `python tools/audit_rehab_bank_rationalisation.py` to regenerate docs only, or add `--check` to compare committed output. `--output-dir` supports an isolated output directory. No network, external API or runtime dependency is added. Stable ID sorting and content hashes make repeated output byte-identical. Debt never makes the command fail; genuine integrity errors do.",
              "", "The original baseline fixture freezes pre-consolidation input hashes, all original IDs and all profile hashes. Tests reconstruct the original bank and review ledger from retained inventory plus the exact-duplicate archive, without replacing that baseline. Tests verify complete classification, live review/reference provenance, exact source/content hashes, valid clusters, advanced dormancy, deterministic/non-mutating output, validator/vocabulary success and seed idempotence. Safety, Today, frozen completion, exposure, unknown-side and multi-injury tests verify that historical lookup preserves original identities while current selection excludes retired duplicates.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs")
    parser.add_argument("--check", action="store_true", help="Verify deterministic committed reports without writing")
    args = parser.parse_args(argv)
    try:
        paths = [args.data_dir / f"{name}.json" for name in ("rehab_bank", "rehab_metadata_review", "rehab_pathways")]
        inputs = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
        report, duplicate_report = build_audit(*inputs)
        report["input_sha256"] = {p.name: input_digest(p) for p in paths}
        report["input_hash_line_endings"] = "Git LF representation; Windows CRLF checkout conversion is normalized, no other bytes are changed."
        if report["integrity_errors"]:
            print("\n".join(report["integrity_errors"]))
            return 1
        outputs = {
            "rehab-bank-rationalisation.json": json_text(report),
            "rehab-bank-duplicate-clusters.json": json_text(duplicate_report),
            "rehab-bank-rationalisation.md": markdown(report, duplicate_report),
        }
        if args.check:
            stale = [name for name, value in outputs.items() if not (args.output_dir / name).exists() or (args.output_dir / name).read_text(encoding="utf-8") != value]
            if stale:
                print("Report integrity failure: generated output differs: " + ", ".join(stale))
                return 1
        else:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for name, value in outputs.items():
                (args.output_dir / name).write_text(value, encoding="utf-8", newline="\n")
        print(json.dumps(report["summary"]["primary_classification_counts"], sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Audit integrity failure: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
