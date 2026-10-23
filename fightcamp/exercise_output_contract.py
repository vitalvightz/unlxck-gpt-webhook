"""One semantic contract for final-session prose and its JSON projection."""

import re


def exercise_field_ownership_errors(plan: dict) -> list[str]:
    """Reject explicit doses filed as execution prose in newly converted cards.

    Locked mental tasks retain their ordered bank steps. Movement instructions
    containing a number (for example, a stance angle) are not dose grammar.
    """
    dose_start = re.compile(r"^\s*(?:(?:complete|perform|do)\s+)?\d+(?:\.\d+)?\s*(?:sets?\s*[x×]|[x×]\s*\d|rounds?\s+(?:of|[x×])|(?:s|secs?|seconds?|mins?|minutes?)\s+(?:work|continuous))", re.I)
    errors = []
    for wi, week in enumerate(plan.get("weeks") or []):
        for di, day in enumerate(week.get("days") or []):
            for si, session in enumerate(day.get("sessions") or []):
                for bi, block in enumerate(session.get("blocks") or []):
                    if block.get("block_type") == "mindset":
                        continue
                    fields = [("coaching_cues", text) for text in block.get("coaching_cues") or []]
                    fields.append(("execution_instructions", block.get("execution_instructions") or ""))
                    for name, text in fields:
                        if dose_start.match(text):
                            errors.append(f"field_ownership: weeks[{wi}].days[{di}].sessions[{si}].blocks[{bi}].{name}: move dose to quantitative fields")
    return errors

EXERCISE_TEXT_CONTRACT = """EXERCISE OUTPUT CONTRACT v1
For each selected physical exercise, emit exactly one bullet and these labelled lines in this order:
- <exact exercise name>: <one resolved dose, with quantities and units>
  How: <setup or movement sequence, only if needed; no dose recap>
  Cue: <one short execution cue; no quantities or rationale>
  Easier: <one supported regression, if provided or authorised>
  Progress: <one authorised next step, or none this block>
  Deload: <the exercise's prescribed easy-week change, only if supplied>
  Stop: <source-backed stop criteria; preserve every safety condition>
Omit inapplicable optional lines. Never emit synonymous duplicate labels.
Dose grammar: N sets x N reps; load N kg or N% 1RM; rest N sec; RPE N.
Intervals: N rounds x N sec work; rest N sec. Nested intervals additionally use N blocks; between-block rest N sec.
Continuous work: duration N min. Carries: N sets x distance N m. Holds: N holds x N sec.
Preserve the exact resolved prescription and every qualifier (side, tempo, intent, restrictions). Never invent a load or %1RM. Resolve authorised ranges at lower work/intensity and longer rest only where no exact dose is supplied.
Dose belongs only on the bullet. How explains movement; Cue directs execution; Progress/Deload describes a change, never repeats today's dose. Preserve locked bank bodies verbatim instead of reformatting them.
"""

STRUCTURED_CONVERSION_CONTRACT = """Convert the supplied plan into the provided strict StructuredTrainingPlan JSON schema. Return one root object, no wrapper, markdown or commentary.
This is transcription, not coaching: preserve every selected exercise, session, day, date, dose and safety condition. Do not infer missing rest, effort, loading, cues or progression. Use null/[]/empty strings for unsupported fields. IDs may be null; execution_order is null. The server restores locked content and deterministic support.
Field ownership:
- Dose -> sets/reps/rounds/work/duration/distance/load/rest/effort/tempo. For nested intervals, interval_blocks and between_block_rest are distinct from per-round rest. Preserve units, side and intent; never reinterpret time or distance as reps.
- How -> execution_instructions, movement/setup only, never a dose recap.
- Cue -> coaching_cues, one execution cue, never a dose, rationale or adjustment.
- Purpose/Why today -> purpose/why_today, never cues.
- Easier/Swap -> regression_options/substitutions verbatim.
- Progress/Deload -> progression_rule/deload_rule verbatim, only authored changes; never today's full dose. none this block means no progression.
- Stop -> stop_rules, preserve all triggers and conditions without inventing or shortening them.
Keep longer technical sequences and locked tactical steps intact. Never manufacture self-report/check-in scores. Coach-owned contact stays in today_card.coach_led_contact, alongside any separately prescribed work. Empty/rest days are not invented sessions.
Follow the supplied render mode: open plans use weekdays and four block weeks without fight countdowns; dated camps preserve source dates/countdowns and week boundaries.
Keep titles/goals short and athlete-facing. Include only source-backed plan notes. Do not duplicate a dose across prose fields or duplicate identical day/session mindset anchors. Keep nutrition empty except an explicitly supplied weight-cut risk band; do not escalate it or expose coach_gated advice. Never provide acute-cut protocols or invent clinical/mental diagnoses. Preserve minor protections and server safety rules.
Set schema_version to 1.0 and raw_markdown_fallback to an empty string; the server restores the original text.

PRESERVATION RULES
- A dated D-X (weekday) heading starts a day; its Why line is the session objective, not a block. Indented How/Cue/adjustment/Step/Intent/Focus/Reset/Anchor lines belong to the preceding exercise. A locked tactical drill is one block with all its steps, never one block per step. Low-load breathing, mobility, tactical and freshness tasks remain real scheduled sessions.
- Keep every active planning week and day. Known fight dates use source countdowns, including D-0/D+1. Contact-only days remain days with sessions=[], and a contact headline. When contact and programmed work coexist, retain both: contact in coach_led_contact, exercises in sessions. Truly empty days say No planned session and use day_type rest; never retain an empty strength/conditioning headline.
- Counts are sets/rounds/reps, time is work/duration/rest, distance is distance. A timed hold uses sets and duration, not one rep. Preserve side, stance, tempo and movement order. Keep fixed values exactly; when only authorised bounds exist, use lower work/intensity and longer rest, never an invented intermediate target. Safety/conditional ranges remain intact in their source text.
- Never derive kg/%1RM from RPE or light/easy prose. Bodyweight means no external load; qualitative bands remain words if no numeric resistance is stated. Effort stays distinct from loading: RPE/RIR/zone/pace/intent follows the source. Max intent is a phrase, never the number 1. Tempo preserves each stated phase, including X. Do not put combined number chains, time or distance in reps.
- Classify jumps/throws/slams/max-speed power as plyometric_power, sprints/reaction as speed, and trunk/isolation support as accessory. Tactical review/visualisation is skill or mindset, never physical conditioning. Never turn zero-load support into physical session volume.
- Readiness is self-report only: never invent HRV, CNS/recovery percentages, wearable/WHOOP/strain metrics, daily check-in dates or scores. Preserve provided mindset intent, focus, confidence and context. Personalise only from supplied athlete context; do not echo distressing disclosures or invent treatment.
- Computed support owns mindset classification and weight-cut risk. Bands none/moderate: at most one calm weight-cut plan note, no added stop/report warning or professional-support escalation. High: amber measured precaution; severe: red/professional support. Never exceed the supplied band. Never expose coach_gated supplement or acute-cut content.
- Red flags contain stop/modify/report criteria only; keep every trigger and action. Numeric thresholds remain numbers, comparisons in operator, wording in display_text. Context notes remain plan_notes, never repeated safety rules. No invented dehydration, sauna, water-loading or sodium protocols; minor protections still apply.
- Plain athlete language, one idea at a time; preserve exact exercise names, quantities, conditions and safety details. Week goals are short labels (six words where possible). Objectives explain why today, including any source-backed freshness trade-off, rather than repeating the dose/title. Keep the original wording if simplification would change meaning. Never shorten safety to meet a word limit or add references to the app/platform.
"""
