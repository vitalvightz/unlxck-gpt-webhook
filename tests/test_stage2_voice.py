"""Dash punctuation is rewritten out of every Stage 2 model response.

The em dash is the clearest tell that a plan was machine-written, so it must not
reach an athlete. These tests pin both halves of that: the dashes that must go,
and the hyphens that must survive untouched because they carry real prescription
detail ("3-5 reps", "coach-led").
"""

import json

from api.stage2_voice import strip_model_dashes


class TestClauseDashes:
    def test_em_dash_before_a_lowercase_clause_becomes_a_comma(self):
        assert (
            strip_model_dashes("Keep rounds technical — nothing all-out today.")
            == "Keep rounds technical, nothing all-out today."
        )

    def test_em_dash_before_a_new_sentence_becomes_a_full_stop(self):
        assert (
            strip_model_dashes("Poor sleep raises injury risk — Skip sparring today.")
            == "Poor sleep raises injury risk. Skip sparring today."
        )

    def test_unspaced_em_dash_is_handled(self):
        assert strip_model_dashes("Cut one round—remove conditioning.") == (
            "Cut one round, remove conditioning."
        )

    def test_en_dash_is_treated_the_same_as_an_em_dash(self):
        assert strip_model_dashes("Taper week – keep it sharp.") == "Taper week, keep it sharp."

    def test_a_spaced_ascii_hyphen_used_as_a_dash_is_rewritten(self):
        assert (
            strip_model_dashes("Pads and footwork - the coach owns those.")
            == "Pads and footwork, the coach owns those."
        )

    def test_a_dash_after_existing_punctuation_does_not_double_it(self):
        assert (
            strip_model_dashes("Session reduced. — Cut one round.")
            == "Session reduced. Cut one round."
        )

    def test_repeated_dashes_collapse_to_one_replacement(self):
        assert strip_model_dashes("Keep it light —— stay sharp.") == "Keep it light, stay sharp."


class TestPreservedHyphens:
    """Hyphens that carry meaning. Rewriting any of these would corrupt a real
    prescription, which is far worse than the tell they are being cleaned of."""

    def test_numeric_ranges_survive(self):
        text = "3-5 reps at RPE 7, 45-60 sec rest."
        assert strip_model_dashes(text) == text

    def test_a_dash_range_is_normalised_to_a_hyphen_not_a_comma(self):
        assert strip_model_dashes("Rest 45–60 sec.") == "Rest 45-60 sec."
        assert strip_model_dashes("Do 3 – 5 reps.") == "Do 3-5 reps."

    def test_compound_words_survive(self):
        text = "Coach-led boxing, reps-in-reserve, warm-up, push-up, max-effort work."
        assert strip_model_dashes(text) == text

    def test_text_without_dash_punctuation_is_returned_unchanged(self):
        text = "Run the planned work and keep the rounds clean."
        assert strip_model_dashes(text) is text


class TestStructure:
    def test_a_line_leading_dash_becomes_a_markdown_bullet(self):
        source = "Fight week:\n— 0–1 days: no training.\n— 2–3 days: one short primer."
        assert strip_model_dashes(source) == (
            "Fight week:\n- 0-1 days: no training.\n- 2-3 days: one short primer."
        )

    def test_a_dangling_dash_at_the_end_of_a_line_is_dropped(self):
        assert strip_model_dashes("Keep it light —\nNext block.") == "Keep it light\nNext block."

    def test_a_dash_in_a_heading_becomes_a_colon_not_a_full_stop(self):
        # A heading's dash introduces a qualifier. A full stop mid-heading reads
        # worse than the dash it replaced, so headings get the colon instead.
        text = "## **Week 1** — Base\n\n**Day 1:** Strength"
        assert strip_model_dashes(text) == "## **Week 1**: Base\n\n**Day 1:** Strength"

    def test_prose_under_a_heading_still_gets_sentence_punctuation(self):
        text = "## Week 1\nKeep it sharp — Run the planned work."
        assert strip_model_dashes(text) == "## Week 1\nKeep it sharp. Run the planned work."


class TestJsonSafety:
    def test_a_structured_response_stays_parseable(self):
        # Stage 2's structured pass returns JSON through the same extraction path,
        # so the rewrite has to stay inside string values and introduce no syntax.
        payload = json.dumps(
            {
                "title": "Coach-led boxing — technical-only combat",
                "prescription": "3–5 reps — keep bar speed fast",
                "sets": 4,
            },
            ensure_ascii=False,
        )
        cleaned = json.loads(strip_model_dashes(payload))
        assert cleaned["title"] == "Coach-led boxing, technical-only combat"
        assert cleaned["prescription"] == "3-5 reps, keep bar speed fast"
        assert cleaned["sets"] == 4

    def test_dashes_written_as_json_escapes_are_caught_too(self):
        # A model may emit — instead of the literal character. Inside a JSON
        # string the escape IS the character, so it has to be cleaned the same way
        # or the tell survives in exactly the responses that are hardest to eyeball.
        payload = json.dumps({"title": "Taper week — keep it sharp"}, ensure_ascii=True)
        assert "\\u2014" in payload
        cleaned = json.loads(strip_model_dashes(payload))
        assert cleaned["title"] == "Taper week, keep it sharp"

    def test_the_coach_led_label_still_classifies_as_coach_led(self):
        # api/structured_plan_sparring_reconcile.py classifies these days by keyword
        # ("coach", "spar", "technical"), never by the exact label string, so
        # rewriting the dash must not change how the day renders.
        from api.structured_plan_sparring_reconcile import _already_coach_led

        cleaned = strip_model_dashes("Coach-led boxing — hard sparring / controlled hard contact")
        assert cleaned == "Coach-led boxing, hard sparring / controlled hard contact"
        assert _already_coach_led(cleaned)


class TestEdges:
    def test_empty_input_is_returned_as_is(self):
        assert strip_model_dashes("") == ""

    def test_a_dash_only_string_is_dropped_rather_than_punctuated(self):
        # Nothing to join, so there is no comma or full stop to invent. Dropping it
        # is the one option that neither invents punctuation nor leaves the tell.
        assert strip_model_dashes("—") == ""

    def test_a_leading_dash_on_the_first_line_becomes_a_bullet(self):
        assert strip_model_dashes("— Cut one round.") == "- Cut one round."
