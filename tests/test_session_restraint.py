"""Tests for the session_restraint module.

Covers:
  1. context_density_cap — verifies tighter caps in taper / short-notice /
     high-fatigue contexts while leaving GPP + low-fatigue unchanged.
  2. tie_break_sort      — verifies that the near-equal band comparator applies
     fatigue cost within the band and does NOT apply it outside the band.
  3. pruning_pass        — verifies base-category AND quality-class coverage
     are both preserved; that the safety note explains why removal was safe.

Also contains smoke tests that run generate_strength_block with restrictive
flags and confirm the restraint behaviour without breaking the planner.
"""

from __future__ import annotations

import pytest

from fightcamp.session_restraint import (
    NEAR_EQUAL_SCORE_BAND,
    SHORT_NOTICE_DAYS,
    context_density_cap,
    fatigue_cost,
    pruning_pass,
    tie_break_sort,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ex(name: str, tags: list[str] | None = None, *, anchor: bool = False) -> dict:
    """Return a minimal exercise dict for use in tests."""
    t: list[str] = list(tags or [])
    if anchor:
        # Give it a 'compound' tag so classify_strength_item marks it anchor_capable
        # and a lower-body hint so it gets lower_body_loaded base category.
        t += ["compound", "posterior_chain", "mech_lower_hip_hinge"]
    return {"name": name, "tags": t, "movement": "hinge" if anchor else "core", "equipment": "bodyweight"}


# ---------------------------------------------------------------------------
# 1. fatigue_cost
# ---------------------------------------------------------------------------

class TestFatigueCost:
    def test_high_cost_tags_add_to_cost(self):
        ex = _make_ex("High Demand", ["mech_cns_high", "eccentric"])
        assert fatigue_cost(ex) > 0

    def test_low_cost_tags_reduce_cost(self):
        ex = _make_ex("Easy Iso", ["isometric", "rehab_friendly"])
        assert fatigue_cost(ex) < 0

    def test_neutral_tags_give_zero(self):
        ex = _make_ex("Plain", ["unilateral", "grip"])
        assert fatigue_cost(ex) == 0

    def test_mixed_tags_sum_correctly(self):
        # mech_cns_high (+2) + isometric (-1) → +1
        ex = _make_ex("Mixed", ["mech_cns_high", "isometric"])
        assert fatigue_cost(ex) == 1

    def test_empty_tags(self):
        assert fatigue_cost({"name": "No Tags"}) == 0


# ---------------------------------------------------------------------------
# 2. context_density_cap
# ---------------------------------------------------------------------------

class TestContextDensityCap:
    def test_gpp_low_fatigue_no_shortnotice_unchanged(self):
        """GPP + low fatigue + no short notice should match the base cap."""
        cap = context_density_cap(phase="GPP", fatigue="low", days_until_fight=None, num_sessions=2)
        # Base = 7 per session × 2 sessions = 14
        assert cap == 14

    def test_taper_low_fatigue_capped_lower_than_gpp(self):
        cap_taper = context_density_cap(phase="TAPER", fatigue="low", days_until_fight=None, num_sessions=1)
        cap_gpp = context_density_cap(phase="GPP", fatigue="low", days_until_fight=None, num_sessions=1)
        assert cap_taper < cap_gpp

    def test_high_fatigue_reduces_cap(self):
        low = context_density_cap(phase="SPP", fatigue="low", days_until_fight=None, num_sessions=1)
        high = context_density_cap(phase="SPP", fatigue="high", days_until_fight=None, num_sessions=1)
        assert high < low

    def test_moderate_fatigue_reduces_cap_less_than_high(self):
        low = context_density_cap(phase="SPP", fatigue="low", days_until_fight=None, num_sessions=1)
        mod = context_density_cap(phase="SPP", fatigue="moderate", days_until_fight=None, num_sessions=1)
        high = context_density_cap(phase="SPP", fatigue="high", days_until_fight=None, num_sessions=1)
        assert low > mod > high

    def test_short_notice_reduces_spp_cap(self):
        normal = context_density_cap(phase="SPP", fatigue="low", days_until_fight=30, num_sessions=1)
        short = context_density_cap(phase="SPP", fatigue="low", days_until_fight=7, num_sessions=1)
        assert short < normal

    def test_short_notice_does_not_reduce_gpp_cap(self):
        """Short notice should not penalise GPP (rare edge case)."""
        normal = context_density_cap(phase="GPP", fatigue="low", days_until_fight=30, num_sessions=1)
        short = context_density_cap(phase="GPP", fatigue="low", days_until_fight=7, num_sessions=1)
        assert short == normal

    def test_cap_never_below_floor_per_session(self):
        """Even in the worst case the cap is at least 2 per session."""
        cap = context_density_cap(phase="TAPER", fatigue="high", days_until_fight=2, num_sessions=1)
        assert cap >= 2

    def test_cap_scales_with_num_sessions(self):
        one = context_density_cap(phase="GPP", fatigue="low", days_until_fight=None, num_sessions=1)
        two = context_density_cap(phase="GPP", fatigue="low", days_until_fight=None, num_sessions=2)
        assert two == one * 2

    def test_short_notice_boundary_exactly_at_threshold(self):
        at = context_density_cap(phase="SPP", fatigue="low", days_until_fight=SHORT_NOTICE_DAYS, num_sessions=1)
        just_over = context_density_cap(phase="SPP", fatigue="low", days_until_fight=SHORT_NOTICE_DAYS + 1, num_sessions=1)
        assert at < just_over


# ---------------------------------------------------------------------------
# 3. tie_break_sort — near-equal band behaviour
# ---------------------------------------------------------------------------

class TestTieBreakSort:
    def _weighted(self, name: str, score: float, tags: list[str] | None = None):
        return (_make_ex(name, tags), score, {})

    def test_higher_score_comes_first(self):
        items = [self._weighted("B", 1.0), self._weighted("A", 2.0)]
        result = tie_break_sort(items)
        assert result[0][0]["name"] == "A"

    def test_near_equal_scores_resolved_by_lower_cost(self):
        """Two exercises within the near-equal band: the cheaper one comes first."""
        expensive = self._weighted("Expensive", 2.0, ["mech_cns_high", "eccentric"])
        cheap = self._weighted("Cheap", 2.0, ["isometric", "rehab_friendly"])
        result = tie_break_sort([expensive, cheap])
        assert result[0][0]["name"] == "Cheap"

    def test_near_equal_band_boundary_applies_cost(self):
        """Scores exactly at the band boundary are near-equal: fatigue cost applies."""
        # Scores differ by exactly NEAR_EQUAL_SCORE_BAND — still near-equal.
        expensive = self._weighted("Expensive", 2.0 + NEAR_EQUAL_SCORE_BAND, ["mech_cns_high"])
        cheap = self._weighted("Cheap", 2.0, ["isometric"])
        result = tie_break_sort([expensive, cheap])
        # Both are within the band — lower fatigue cost (cheap) wins.
        assert result[0][0]["name"] == "Cheap"

    def test_outside_near_equal_band_uses_score_only(self):
        """Scores outside the near-equal band: higher score always wins, regardless of fatigue cost."""
        # expensive has a much higher score but high fatigue cost.
        # It should still rank first because the score gap exceeds the band.
        score_gap = NEAR_EQUAL_SCORE_BAND + 0.05
        expensive = self._weighted("Expensive", 2.0 + score_gap, ["mech_cns_high", "eccentric"])
        cheap = self._weighted("Cheap", 2.0, ["isometric", "rehab_friendly"])
        result = tie_break_sort([expensive, cheap])
        assert result[0][0]["name"] == "Expensive", (
            "When scores are outside the near-equal band, the higher-scored item must win "
            "regardless of its fatigue cost."
        )

    def test_near_equal_same_cost_resolved_by_name(self):
        """Same score + same cost → alphabetical order."""
        a = self._weighted("Alpha", 1.5)
        b = self._weighted("Beta", 1.5)
        result = tie_break_sort([b, a])
        assert result[0][0]["name"] == "Alpha"

    def test_empty_list_ok(self):
        assert tie_break_sort([]) == []

    def test_single_item_unchanged(self):
        items = [self._weighted("Solo", 3.0)]
        result = tie_break_sort(items)
        assert result[0][0]["name"] == "Solo"

    def test_sort_is_deterministic_across_identical_inputs(self):
        items_a = [self._weighted("X", 1.0), self._weighted("Y", 1.0), self._weighted("Z", 1.0)]
        items_b = [self._weighted("Z", 1.0), self._weighted("X", 1.0), self._weighted("Y", 1.0)]
        result_a = [i[0]["name"] for i in tie_break_sort(items_a)]
        result_b = [i[0]["name"] for i in tie_break_sort(items_b)]
        assert result_a == result_b

    def test_band_is_real_not_just_exact_tie(self):
        """Demonstrate that the near-equal band works for non-exact score differences.

        This is the core fix: the old (-score, fatigue_cost, name) sort would
        only apply fatigue cost on exact ties.  With the band comparator,
        borderline score differences within the band also defer to fatigue cost.
        """
        # Scores differ by a small amount inside the band (simulating noise).
        noise = NEAR_EQUAL_SCORE_BAND * 0.5
        high_score_costly = self._weighted("SlightlyHigherButCostly", 2.0 + noise, ["mech_cns_high", "eccentric"])
        low_score_cheap = self._weighted("SlightlyLowerButCheap", 2.0, ["isometric", "rehab_friendly"])
        result = tie_break_sort([high_score_costly, low_score_cheap])
        # Within the band, cheaper item wins despite slightly lower score.
        assert result[0][0]["name"] == "SlightlyLowerButCheap"


# ---------------------------------------------------------------------------
# 4. pruning_pass — base-category AND quality-class coverage
# ---------------------------------------------------------------------------

class TestPruningPass:
    def _score_lookup(self, exercises: list[dict]) -> dict[str, float]:
        """Assign scores in the order they appear (first = highest)."""
        return {ex["name"]: float(len(exercises) - i) for i, ex in enumerate(exercises)}

    def _make_list(self, n_anchors: int, n_support: int) -> list[dict]:
        anchors = [_make_ex(f"Anchor{i}", anchor=True) for i in range(n_anchors)]
        support = [_make_ex(f"Support{i}", ["core", "stability"]) for i in range(n_support)]
        return anchors + support

    # --- restrictive context ---

    def test_prunes_one_support_in_taper_high_fatigue(self):
        exercises = self._make_list(n_anchors=1, n_support=3)
        scores = self._score_lookup(exercises)
        result, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        assert removed is not None
        assert len(result) == len(exercises) - 1

    def test_prunes_in_short_notice_context(self):
        exercises = self._make_list(n_anchors=1, n_support=2)
        scores = self._score_lookup(exercises)
        result, removed, note = pruning_pass(
            exercises, phase="SPP", fatigue="low", days_until_fight=7, score_lookup=scores
        )
        assert removed is not None

    def test_anchor_never_pruned(self):
        exercises = self._make_list(n_anchors=2, n_support=2)
        scores = self._score_lookup(exercises)
        result, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        if removed is not None:
            from fightcamp.strength_session_quality import classify_strength_item
            assert not classify_strength_item(removed)["anchor_capable"]

    def test_session_always_retains_anchor_after_prune(self):
        exercises = self._make_list(n_anchors=1, n_support=2)
        scores = self._score_lookup(exercises)
        result, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        from fightcamp.strength_session_quality import classify_strength_item
        assert any(classify_strength_item(ex)["anchor_capable"] for ex in result)

    def test_nothing_pruned_when_only_2_items(self):
        exercises = self._make_list(n_anchors=1, n_support=1)
        scores = self._score_lookup(exercises)
        result, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        assert removed is None
        assert result == exercises

    # --- non-restrictive context ---

    def test_nothing_pruned_in_gpp_low_fatigue(self):
        exercises = self._make_list(n_anchors=1, n_support=5)
        scores = self._score_lookup(exercises)
        result, removed, note = pruning_pass(
            exercises, phase="GPP", fatigue="low", days_until_fight=90, score_lookup=scores
        )
        assert removed is None
        assert result == exercises

    def test_nothing_pruned_in_spp_low_fatigue_no_short_notice(self):
        exercises = self._make_list(n_anchors=1, n_support=4)
        scores = self._score_lookup(exercises)
        result, removed, note = pruning_pass(
            exercises, phase="SPP", fatigue="low", days_until_fight=30, score_lookup=scores
        )
        assert removed is None

    # --- lowest-score target ---

    def test_lowest_scoring_support_is_removed(self):
        exercises = [
            _make_ex("Anchor0", anchor=True),
            _make_ex("HighScore", ["core", "stability"]),
            _make_ex("LowScore", ["core", "stability"]),
        ]
        scores = {"Anchor0": 5.0, "HighScore": 3.0, "LowScore": 1.0}
        result, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        assert removed is not None
        assert removed["name"] == "LowScore"
        assert "LowScore" not in [ex["name"] for ex in result]

    # --- safety note ---

    def test_safety_note_always_non_empty(self):
        """pruning_pass always returns a non-empty safety note string."""
        exercises = self._make_list(n_anchors=1, n_support=3)
        scores = self._score_lookup(exercises)
        _, _, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        assert isinstance(note, str) and len(note) > 0

    def test_safety_note_when_pruned_mentions_anchor_and_context(self):
        """When an item is pruned, the note should name the anchor and context."""
        exercises = [
            _make_ex("MyAnchor", anchor=True),
            _make_ex("SupportA", ["core", "stability"]),
            _make_ex("SupportB", ["core", "stability"]),
        ]
        scores = {"MyAnchor": 5.0, "SupportA": 3.0, "SupportB": 1.0}
        _, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        assert removed is not None
        # Note must state context, anchor retention, and coverage preservation.
        assert "TAPER" in note or "high fatigue" in note
        assert "MyAnchor" in note
        assert "coverage preserved" in note

    def test_safety_note_when_not_pruned_explains_why(self):
        """When nothing is pruned, the note explains why."""
        exercises = self._make_list(n_anchors=1, n_support=1)
        scores = self._score_lookup(exercises)
        _, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        assert removed is None
        assert len(note) > 0  # Explanation is always given.

    # --- quality-class coverage protection (Fix 2) ---

    def test_sole_quality_class_representative_never_pruned(self):
        """An item is the sole representative of its quality_class → must not be removed.

        This is the key Fix 2 test: the old code only checked base_categories;
        the new code also checks quality_class so a unique support role is preserved.
        """
        from fightcamp.strength_session_quality import classify_strength_item

        # Build a session where one support item is an isometric (support_isometric)
        # and the rest are support_accessory.  The isometric is the only one of its
        # quality class so it must not be pruned.
        isometric_ex = _make_ex("UniqueIsometric", ["isometric", "stability"])
        exercises = [
            _make_ex("Anchor0", anchor=True),
            isometric_ex,
            _make_ex("Accessory1", ["core", "stability"]),
            _make_ex("Accessory2", ["core", "stability"]),
        ]
        scores = {
            "Anchor0": 5.0,
            "UniqueIsometric": 1.0,  # lowest score, so would be target without protection
            "Accessory1": 3.0,
            "Accessory2": 2.0,
        }
        result, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        # The isometric must NOT be removed even though it has the lowest score.
        remaining_names = [ex["name"] for ex in result]
        assert "UniqueIsometric" in remaining_names, (
            "The sole support_isometric item must be protected from pruning."
        )
        # Something else should be pruned instead (if anything is).
        if removed is not None:
            assert removed["name"] != "UniqueIsometric"

    def test_duplicate_quality_class_allows_pruning(self):
        """When two items share the same quality_class, the lower-scoring one can be pruned."""
        exercises = [
            _make_ex("Anchor0", anchor=True),
            _make_ex("Accessory1", ["core", "stability"]),
            _make_ex("Accessory2", ["core", "stability"]),
        ]
        scores = {"Anchor0": 5.0, "Accessory1": 3.0, "Accessory2": 1.0}
        result, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        # With two support_accessory items, the lower scorer is a valid candidate.
        assert removed is not None
        assert removed["name"] == "Accessory2"

    def test_rehab_support_as_sole_representative_is_protected(self):
        """rehab_support items (protective role) should not be pruned if sole in their class."""
        rehab_ex = {
            "name": "RehabItem",
            "tags": ["rehab_friendly"],
            "movement": "rehab",
            "equipment": "bodyweight",
            "name_lower": "rehabitem",
        }
        exercises = [
            _make_ex("Anchor0", anchor=True),
            rehab_ex,
            _make_ex("Accessory1", ["core", "stability"]),
            _make_ex("Accessory2", ["core", "stability"]),
        ]
        scores = {
            "Anchor0": 5.0,
            "RehabItem": 0.5,  # lowest score; would be pruned without class protection
            "Accessory1": 3.0,
            "Accessory2": 2.0,
        }
        result, removed, note = pruning_pass(
            exercises, phase="TAPER", fatigue="high", days_until_fight=None, score_lookup=scores
        )
        remaining_names = [ex["name"] for ex in result]
        assert "RehabItem" in remaining_names, (
            "The sole rehab_support item must be protected from pruning."
        )


# ---------------------------------------------------------------------------
# 5. Integration smoke test — generate_strength_block respects density cap
# ---------------------------------------------------------------------------

class TestStrengthBlockRestraintIntegration:
    """Smoke tests that run generate_strength_block with restrictive flags and
    verify the restraint rules reduce exercise count as expected."""

    def _base_flags(self, *, phase: str, fatigue: str, days_until_fight: int | None = None) -> dict:
        return {
            "phase": phase,
            "fatigue": fatigue,
            "training_frequency": 5,
            "training_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "equipment": ["barbell", "dumbbell", "bands", "medicine_ball", "bodyweight"],
            "key_goals": ["strength", "power"],
            "style_tactical": ["pressure_fighter"],
            "fight_format": "boxing",
            "days_until_fight": days_until_fight,
            "random_seed": 42,
        }

    def _exercise_count(self, flags: dict) -> int:
        from fightcamp.strength import generate_strength_block
        result = generate_strength_block(flags=flags)
        return len(result.get("exercises", []))

    def test_taper_high_fatigue_fewer_exercises_than_gpp_low(self):
        taper_high = self._exercise_count(self._base_flags(phase="TAPER", fatigue="high"))
        gpp_low = self._exercise_count(self._base_flags(phase="GPP", fatigue="low"))
        assert taper_high <= gpp_low

    def test_short_notice_spp_not_more_than_normal_spp(self):
        short = self._exercise_count(self._base_flags(phase="SPP", fatigue="low", days_until_fight=7))
        normal = self._exercise_count(self._base_flags(phase="SPP", fatigue="low", days_until_fight=60))
        assert short <= normal

    def test_why_log_records_pruned_item_when_pruning_occurs(self):
        """When a pruning pass removes an item, the why_log entry should include the safety note."""
        from fightcamp.strength import generate_strength_block
        flags = self._base_flags(phase="TAPER", fatigue="high")
        result = generate_strength_block(flags=flags)
        why_log = result.get("why_log", [])
        pruned_entries = [
            entry for entry in why_log
            if "pruning pass" in (entry.get("explanation") or "")
        ]
        # May or may not prune depending on exercise pool; just assert the log
        # never raises and pruned entries (if any) are well-formed with safety note.
        for entry in pruned_entries:
            assert entry.get("name") is not None
            assert "final_score" in entry.get("reasons", {})
            # The explanation should now contain the safety note (why removal was safe).
            explanation = entry.get("explanation", "")
            assert "context=" in explanation or "anchor retained" in explanation, (
                f"why_log pruning entry should explain why removal was safe; got: {explanation!r}"
            )

    def test_block_always_has_at_least_one_exercise(self):
        from fightcamp.strength import generate_strength_block
        for phase in ("GPP", "SPP", "TAPER"):
            for fatigue in ("low", "moderate", "high"):
                flags = self._base_flags(phase=phase, fatigue=fatigue)
                result = generate_strength_block(flags=flags)
                assert len(result.get("exercises", [])) >= 1, (
                    f"phase={phase} fatigue={fatigue} produced no exercises"
                )
