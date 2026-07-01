"""Tests for structured guided-injury field triage mapping.

Covers:
- Structured serious injuries (fracture, dislocation, tendon_ligament, post_surgery)
- Head/nerve/breathing structured types
- Surface injury mapping (cut, laceration, abrasion, blister, bruise, burn)
- Regression: legacy free-text and old guided payloads still work
"""

from fightcamp.injury_triage import (
    FULL_PLAN,
    MEDICAL_HOLD,
    NEEDS_REVIEW,
    RESTRICTED_REHAB_ONLY,
    SURFACE_MINOR_TRAIN_THROUGH_NOTE,
    triage_injuries,
)
from fightcamp.input_parsing import PlanInput
from support import _build_request


def _base_payload() -> dict:
    return _build_request().to_payload()


def _payload_with_guided(guided: dict, injury_text: str = "") -> dict:
    data = _base_payload()
    if injury_text:
        for field in data["data"]["fields"]:
            if field.get("label") == "Any injuries or areas you need to work around?":
                field["value"] = injury_text
                break
    data["guided_injury"] = guided
    return data


# ── Structured serious injuries ───────────────────────────────────────


class TestStructuredFracture:
    def test_fracture_not_cleared_routes_restricted(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "right shin",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "fracture",
            "timeframe": "last_month",
            "cleared": "no",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode in (RESTRICTED_REHAB_ONLY, NEEDS_REVIEW)
        assert triage.should_block_stage2 is True
        assert "fracture" in triage.matched_high_risk_categories

    def test_fracture_old_cleared_no_symptoms_allows_plan(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "right shin",
            "severity": "low",
            "trend": "stable",
            "injury_type": "fracture",
            "timeframe": "old_cleared",
            "cleared": "yes",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN
        assert "fracture" not in triage.matched_high_risk_categories

    def test_fracture_old_cleared_but_worsening_still_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left wrist",
            "severity": "moderate",
            "trend": "worsening",
            "injury_type": "fracture",
            "timeframe": "old_cleared",
            "cleared": "yes",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode != FULL_PLAN
        assert "fracture" in triage.matched_high_risk_categories


class TestStructuredDislocation:
    def test_dislocation_not_cleared_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "right shoulder",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "dislocation",
            "timeframe": "last_month",
            "cleared": "not_sure",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode in (RESTRICTED_REHAB_ONLY, NEEDS_REVIEW)
        assert "dislocation" in triage.matched_high_risk_categories


class TestStructuredTendonLigament:
    def test_tendon_ligament_high_worsening_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left knee",
            "severity": "high",
            "trend": "worsening",
            "injury_type": "tendon_ligament",
            "notes": "feels unstable, giving way on stairs",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode != FULL_PLAN
        # The specific tendon/ligament label may be folded into the consolidated
        # "structural_high_severity" bucket; either satisfies the block.
        assert {"tendon_rupture_or_avulsion", "structural_high_severity"} & set(
            triage.matched_high_risk_categories
        )

    def test_tendon_ligament_mild_stable_cleared_allows_plan(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "right ankle",
            "severity": "low",
            "trend": "improving",
            "injury_type": "tendon_ligament",
            "cleared": "yes",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN


class TestStructuredPostSurgery:
    def test_post_surgery_not_cleared_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left knee",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "post_surgery",
            "timeframe": "one_to_three_months",
            "cleared": "no",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode in (RESTRICTED_REHAB_ONLY, NEEDS_REVIEW)
        assert triage.should_block_stage2 is True


# ── Head / nerve / breathing ──────────────────────────────────────────


class TestStructuredHeadImpact:
    def test_head_impact_routes_medical_hold(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "Head / Neck",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "head_impact",
            "notes": "[red_flags:loss_of_consciousness,vomiting]",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == MEDICAL_HOLD
        assert "loss_of_consciousness" in triage.red_flags

    def test_head_impact_without_red_flags_still_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "Head / Neck",
            "severity": "low",
            "trend": "stable",
            "injury_type": "head_impact",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode in (MEDICAL_HOLD, NEEDS_REVIEW, RESTRICTED_REHAB_ONLY)
        assert triage.should_block_stage2 is True


class TestStructuredNerveSymptoms:
    def test_nerve_worsening_post_impact_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left arm",
            "severity": "moderate",
            "trend": "worsening",
            "injury_type": "nerve_symptoms",
            "impact_related": "yes",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode != FULL_PLAN
        assert "numbness" in triage.red_flags


class TestStructuredChestBreathing:
    def test_chest_breathing_triggers_medical_gate(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "chest",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "chest_breathing",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode in (MEDICAL_HOLD, NEEDS_REVIEW)
        assert "breathing_pain" in triage.red_flags or "chest_pain" in triage.red_flags


# ── Surface injuries ──────────────────────────────────────────────────


class TestSurfaceCut:
    def test_cut_open_wound_needs_review(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "right eyebrow",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "cut",
            "open_wound": "yes",
            "bleeding_status": "a_little",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == NEEDS_REVIEW
        assert "open_wound" in triage.red_flags

    def test_cut_uncontrolled_bleeding_medical_hold(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "forearm",
            "severity": "high",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "cut",
            "bleeding_status": "wont_stop",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == MEDICAL_HOLD
        assert "uncontrolled_bleeding" in triage.red_flags

    def test_laceration_needs_stitches_needs_review(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left shin",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "laceration",
            "notes": "deep gash, probably needs stitches",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == NEEDS_REVIEW
        assert "needs_stitches" in triage.red_flags

    def test_cut_sensitive_area_eye_needs_review(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left eyebrow",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "cut",
            "sensitive_area": "eye",
            "open_wound": "no",
            "bleeding_status": "none",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == NEEDS_REVIEW
        assert "eye_area_wound" in triage.red_flags


class TestSurfaceAbrasion:
    def test_abrasion_stable_no_infection_allows_plan(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "right knee",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "abrasion",
            "infection_signs": [],
            "open_wound": "no",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN

    def test_abrasion_with_pus_and_fever_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left elbow",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "abrasion",
            "infection_signs": ["pus", "fever"],
        }))
        triage = triage_injuries(parsed)
        assert triage.mode in (MEDICAL_HOLD, NEEDS_REVIEW)
        assert "infection_signs" in triage.red_flags


class TestSurfaceBlister:
    def test_blister_closed_stable_allows_plan(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "right foot",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "blister",
            "open_wound": "no",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN


class TestSurfaceBruise:
    def test_bruise_stable_no_danger_allows_plan(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left quad",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "bruise",
            "impact_related": "yes",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN

    def test_bruise_rib_chest_with_breathing_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left rib",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "bruise",
            "impact_related": "yes",
            "notes": "pain breathing after impact",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode != FULL_PLAN


# ── Minor surface injuries train through (PR 2) ───────────────────────
#
# Grazes, scrapes, abrasions, and mild bruises are skin-level damage. In a combat
# sport they must NOT restrict normal training unless a real danger signal is
# present. These tests pin the train-through behaviour and the calm, coach-facing
# global note, while the danger-signal tests below prove the safety gates survive.


class TestSurfaceMinorTrainThrough:
    def test_lower_back_graze_returns_full_plan(self):
        # (A) A minor lower-back graze trains through: full plan, no block, no
        # review, no restriction, no broad exclusion.
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "lower back",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "graze",
            "infection_signs": [],
            "open_wound": "no",
            "bleeding_status": "none",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN
        assert triage.should_block_stage2 is False
        assert triage.clinician_clearance_required is False
        assert triage.matched_high_risk_categories == []
        assert triage.red_flags == []
        assert triage.surface_minor_train_through is True
        # No hard restriction was synthesised from the surface injury's guidance.
        assert parsed.restrictions == []

    def test_lower_back_graze_emits_calm_global_note(self):
        # (A) The only guidance is a single calm global note — no per-session
        # wound-care panic, no medical-clearance language.
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "lower back",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "graze",
        }))
        triage = triage_injuries(parsed)
        assert triage.global_notes == [SURFACE_MINOR_TRAIN_THROUGH_NOTE]
        note = triage.global_notes[0].lower()
        # Coach language, not medical panic.
        assert "medical" not in note
        assert "clearance" not in note
        assert "restricted" not in note
        assert "seek" not in note

    def test_shin_scrape_trains_through(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "right shin",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "scrape",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN
        assert triage.surface_minor_train_through is True

    def test_minor_bruise_stable_trains_through_with_calm_note(self):
        # (C) A stable minor bruise trains through with only the calm global note —
        # no conditioning/strength suppression, no block.
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left quad",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "bruise",
            "impact_related": "yes",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN
        assert triage.should_block_stage2 is False
        assert triage.surface_minor_train_through is True
        assert triage.global_notes == [SURFACE_MINOR_TRAIN_THROUGH_NOTE]

    def test_train_through_note_is_not_repeated(self):
        # (E) Regression: the calm note is surfaced exactly once as a global note,
        # never duplicated as if it must be repeated per session.
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "lower back",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "abrasion",
        }))
        triage = triage_injuries(parsed)
        assert triage.global_notes.count(SURFACE_MINOR_TRAIN_THROUGH_NOTE) == 1


class TestSurfaceMinorTrainThroughGating:
    # Bruises/contusions are soft-tissue, not skin wounds: they train through only
    # when explicitly classified as a surface/bruise injury AND low severity. These
    # pin the severity/category gating so a moderate bruise or a bare parsed
    # soft-tissue contusion is not labelled a minor surface injury.

    def test_moderate_bruise_is_not_train_through(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left quad",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "bruise",
            "impact_related": "yes",
        }))
        triage = triage_injuries(parsed)
        assert triage.surface_minor_train_through is False
        assert triage.global_notes == []

    def test_low_bruise_is_train_through(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left quad",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "bruise",
            "impact_related": "yes",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN
        assert triage.surface_minor_train_through is True

    def test_bare_free_text_contusion_is_not_labelled_surface(self):
        # A soft-tissue contusion parsed from free text must not be treated as a
        # minor surface injury (it has no explicit surface classification).
        data = _base_payload()
        for field in data["data"]["fields"]:
            if field.get("label") == "Any injuries or areas you need to work around?":
                field["value"] = "thigh contusion"
                break
        triage = triage_injuries(PlanInput.from_payload(data))
        assert triage.surface_minor_train_through is False
        assert triage.global_notes == []


class TestSurfaceDangerSignalsStillBlock:
    # (D) Real danger signals keep their block/review routing — train-through must
    # never leak past a genuine safety gate.

    def test_uncontrolled_bleeding_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "forearm",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "abrasion",
            "bleeding_status": "wont_stop",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode != FULL_PLAN
        assert triage.should_block_stage2 is True
        assert triage.surface_minor_train_through is False
        assert "uncontrolled_bleeding" in triage.red_flags

    def test_infection_signs_block(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left elbow",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "abrasion",
            "infection_signs": ["pus", "spreading"],
        }))
        triage = triage_injuries(parsed)
        assert triage.mode != FULL_PLAN
        assert triage.surface_minor_train_through is False
        assert "infection_signs" in triage.red_flags

    def test_needs_stitches_needs_review(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left shin",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "cut",
            "notes": "deep gash, needs stitches",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == NEEDS_REVIEW
        assert triage.surface_minor_train_through is False
        assert "needs_stitches" in triage.red_flags

    def test_eye_wound_needs_review(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left eyebrow",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "cut",
            "sensitive_area": "eye",
            "open_wound": "no",
            "bleeding_status": "none",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode == NEEDS_REVIEW
        assert triage.surface_minor_train_through is False
        assert "eye_area_wound" in triage.red_flags

    def test_worsening_bruise_needs_review(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "thigh",
            "severity": "moderate",
            "trend": "worsening",
            "injury_type": "surface_injury",
            "surface_type": "bruise",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode != FULL_PLAN
        assert triage.surface_minor_train_through is False

    def test_rib_impact_bruise_with_breathing_blocks(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left rib",
            "severity": "moderate",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "bruise",
            "impact_related": "yes",
            "notes": "pain breathing after impact",
        }))
        triage = triage_injuries(parsed)
        assert triage.mode != FULL_PLAN
        assert triage.surface_minor_train_through is False


# ── Regression tests ──────────────────────────────────────────────────


class TestRegressionLegacyParsing:
    def test_legacy_free_text_still_works(self):
        data = _base_payload()
        for field in data["data"]["fields"]:
            if field.get("label") == "Any injuries or areas you need to work around?":
                field["value"] = "mild left calf soreness"
                break
        parsed = PlanInput.from_payload(data)
        triage = triage_injuries(parsed)
        assert triage.mode == FULL_PLAN

    def test_old_guided_area_severity_trend_still_works(self):
        data = _base_payload()
        data["guided_injury"] = {
            "area": "left rib",
            "severity": "high",
            "trend": "worsening",
            "avoid": "contact and hard sparring",
            "notes": "pain breathing deeply after impact",
        }
        parsed = PlanInput.from_payload(data)
        triage = triage_injuries(parsed)
        assert triage.mode == MEDICAL_HOLD

    def test_no_fracture_text_does_not_trigger_fracture(self):
        data = _base_payload()
        for field in data["data"]["fields"]:
            if field.get("label") == "Any injuries or areas you need to work around?":
                field["value"] = "mild knee soreness, no fracture"
                break
        parsed = PlanInput.from_payload(data)
        triage = triage_injuries(parsed)
        assert "fracture" not in triage.matched_high_risk_categories

    def test_no_infection_signs_does_not_trigger_infection(self):
        parsed = PlanInput.from_payload(_payload_with_guided({
            "area": "left shin",
            "severity": "low",
            "trend": "stable",
            "injury_type": "surface_injury",
            "surface_type": "abrasion",
            "infection_signs": ["none"],
        }))
        triage = triage_injuries(parsed)
        assert "infection_signs" not in triage.red_flags
