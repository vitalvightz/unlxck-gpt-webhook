from fightcamp import injury_guard, rehab_protocols
from fightcamp.injury_taxonomy import (
    INJURY_TAXONOMY,
    derive_injury_type_severity_map,
    derive_red_flag_types,
    derive_urgent_injury_tokens,
    get_required_flags,
)
from fightcamp.injury_synonyms import TRIAGE_CATEGORY_MAP
from fightcamp.injury_scoring import score_injury_phrase
from fightcamp.rehab_protocols import generate_rehab_protocols


def test_taxonomy_completeness_for_canonical_injury_types():
    required = {
        "sprain", "strain", "tightness", "contusion", "swelling", "tendonitis",
        "impingement", "instability", "stiffness", "pain", "soreness", "hyperextension",
        "abrasion", "cut", "laceration", "graze", "blister", "unspecified",
    }
    assert required.issubset(INJURY_TAXONOMY.keys())


def test_taxonomy_entry_shape_and_severity_validity():
    for rule in INJURY_TAXONOMY.values():
        assert rule["default_severity"] in {"low", "moderate", "high"}
        assert isinstance(rule["urgent"], bool)
        assert isinstance(rule["rehab_allowed"], bool)
        assert isinstance(rule["flags"], list)
        assert isinstance(rule["blocked_training_tags"], list)
        assert isinstance(rule["blocked_rehab_terms"], list)


def test_compatibility_maps_are_taxonomy_derived():
    assert injury_guard.INJURY_TYPE_SEVERITY == derive_injury_type_severity_map()
    assert rehab_protocols._URGENT_INJURY_TOKENS == derive_urgent_injury_tokens()
    assert rehab_protocols.RED_FLAG_TYPES == derive_red_flag_types()


def test_structural_flags_from_taxonomy():
    assert {"urgent", "structural_red_flag", "suspected_ligament_tear"}.issubset(set(get_required_flags("acl_tear")))
    assert {"urgent", "structural_red_flag", "suspected_tendon_rupture"}.issubset(set(get_required_flags("tendon_rupture")))
    assert {"urgent", "structural_red_flag", "suspected_dislocation"}.issubset(set(get_required_flags("dislocation")))


def test_all_triage_categories_exist_in_taxonomy():
    for triage_category in TRIAGE_CATEGORY_MAP.values():
        assert triage_category in INJURY_TAXONOMY


def test_scored_collateral_ligament_tears_exist_in_taxonomy_with_structural_flags():
    for phrase in ["mcl tear", "lcl tear", "pcl tear"]:
        scored = score_injury_phrase(phrase)
        triage = scored.get("triage_category")
        assert triage in INJURY_TAXONOMY
        assert "urgent" in scored["flags"]
        assert "structural_red_flag" in scored["flags"]


def test_raw_rehab_red_flag_scan_parity_for_urgent_phrases():
    for phrase in ["tendon rupture", "fracture", "dislocation", "post-surgery", "acute nerve issue"]:
        text, _ = generate_rehab_protocols(
            injury_string=phrase,
            exercise_data=[],
            current_phase="GPP",
            parsed_entries=None,
        )
        assert "Red Flag Detected" in text


def test_urgent_token_derivation_does_not_include_generic_last_words():
    tokens = derive_urgent_injury_tokens()

    forbidden = {
        "issue",
        "issues",
        "problem",
        "problems",
        "involvement",
        "condition",
        "symptom",
        "symptoms",
        "pain",
        "injury",
        "injuries",
        "swelling",
        "instability",
        "weakness",
    }

    assert tokens.isdisjoint(forbidden)


def test_urgent_token_derivation_keeps_structural_variants():
    tokens = derive_urgent_injury_tokens()

    expected = {
        "acl_tear",
        "acl-tear",
        "acl tear",
        "tendon_rupture",
        "tendon-rupture",
        "tendon rupture",
        "dislocation",
        "fracture",
        "concussion",
        "infection",
        "hernia",
    }

    assert expected <= tokens


def test_generic_issue_language_does_not_create_urgent_flags():
    scored = score_injury_phrase("old shoulder issue")

    assert scored["location"] == "shoulder"
    assert "urgent" not in scored["flags"]
    assert "structural_red_flag" not in scored["flags"]


def test_specific_urgent_phrases_still_trigger_flags():
    acl = score_injury_phrase("right knee acl tear")
    assert acl["triage_category"] == "acl_tear"
    assert "urgent" in acl["flags"]

    concussion = score_injury_phrase("concussion after sparring")
    assert concussion["triage_category"] == "concussion"
    assert "urgent" in concussion["flags"]
