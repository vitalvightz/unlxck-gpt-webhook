# AI exercise coaching contract

Investigation recorded before implementation against Main `8ba651ebe4835164e5a96314360008f0a694900b`.

Baseline: 47 failed, 73 passed (all four requested modules, React dependencies installed).

## Classification before changes

| Primary classification | Measurable | Context | Release | Concise | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Outdated deterministic authoring/field-placement expectation | 18 | 10 | 5 | 2 | 35 |
| Unsafe authored progress accepted (also expects generated replacement) | 5 | 0 | 0 | 0 | 5 |
| Conversion/persisted rendering coverage needs authored source fixture | 1 | 0 | 3 | 0 | 4 |
| Dropped-field fixture incorrectly expects deterministic authoring | 0 | 0 | 2 | 0 | 2 |
| Duplicate-session source identity | 0 | 1 | 0 | 0 | 1 |
| Total | 24 | 11 | 10 | 2 | 47 |

Categories describe the first failed assertion; several tests have mixed causes.

* Measurable outdated: seven exact-future cases; same-day future targets, unique reindexing, equivalent units; numerical Easier; saved-profile replacement; backend/React fixture expecting a fabricated field; legacy record 741aa47d expecting generated Add rules; four missing-note cases.
* Measurable genuine safety: precise authored step with a wrong increment; three hidden second changes; unknown starting load. The replacement is rejection, never generated wording.
* Measurable conversion: unsupported 100 kg must be rejected, not replaced with generated rep advice.
* Context outdated: three helper/label tests and existing-coach test move quality Progress into Cue; six duplicate-recovery cases expect Stage 1 bank Easier to fill missing final AI fields.
* Context genuine identity: source fallback scopes by generic role title instead of the specific appointment label. Block ids also omit session index.
* Release outdated: five constrained-context tests require hardcoded Easier. Two dropped-field fixtures depend on fabricated Easier/Progress. Three persistence/React paths require invented numeric rules and 20 generic alternatives before reaching useful assertions.
* Concise outdated: fallback fabricates Easier; future-exposure test expects Python to write Progress.

Passing assertions also contain incorrect expectations: flat future dose permits “Add 2 reps”; saved flat 100 kg permits “Add +5kg”. These need rejection coverage.

## Execution-path findings

Stage 1 resolves selected assignments and effective prescriptions. `render_authority` emits their deterministic execution/safety text. Stage 2 writes the final text, but `programme_fidelity.reconcile_authoritative_programme` currently replaces the entire schedule with deterministic text, losing AI adjustments. Structured conversion normalizes fields and checks source fidelity; `COACHING_DROPPED` only tests presence, so contradictory nonempty replacements escape. Source-backed fallback parses labelled text by day/session/exercise. Saved recovery never restores adjustments from final text, and only rejects blocked/legacy-profile Progress. Effective-plan resolution invokes that recovery before overrides. React displays the resulting semantic fields, including legacy labelled cues; tests must inspect the persisted payload and expanded cards.

No exercise selection, programme dose, readiness, rehab stage, or model-call policy will be changed.

## Decisions and repaired production defects

* Final-session AI remains the author. Conversion prompts previously said “You own the Progress and Easier notes” and “If Progress or Easier is absent, author a useful short note”. Both instructions are replaced with verbatim projection, including the open-plan conversion prompt. The finalizer receives explicit ownership and safety instructions.
* Reconciliation still owns the calendar, membership and dose, but carries source coaching only for an exact, unambiguous day/session/exercise occurrence. Fidelity compares programme facts independently of AI wording. Source corrections do not move coaching to an invented appointment.
* Numerical Progress uses the existing resolved-exposure utilities for validation only. It requires a comparable current dose, a single safe increase in the actual next exposure, the same programming phase, compatible rest/effort/units and permitted recovery state. Unknown load, excessive jumps, multiple changes, tempo/HR changes and invented future appointments are rejected. No replacement text is emitted.
* Quality-only Progress can remain at the same workload in recovery contexts. Numerical increases remain prohibited by the existing taper, injury, fatigue and cut rules.
* Easier is checked for an actionable same-movement adjustment, supported equipment, non-increased work/effort, non-reduced rest and clinical/stop-rule compatibility. Existing restriction guards are reused. Unparsed numeric quantities are rejected. Distinct valid AI options retain their wording.
* `COACHING_DROPPED` continues to block conversion omissions. `COACHING_CHANGED` blocks nonempty inventions and rewrites as well. Load comparison includes units and reference, not just the scalar value.
* Persistence validates text and structured fields before the existing release override. An unsafe instruction cannot escape through the markdown fallback. Missing required Easier is reported; safe source data remains available without a fabricated replacement.
* Saved metadata recovery accepts final text explicitly, restores only matching source fields, and never modifies a dose. Numerical instructions without usable authority are rejected, including legacy labelled cue leakage. Repeated reads are idempotent.
* Same-day exercise occurrences retain separate session context; deterministic block IDs include the appointment index.
* A prescription edit clears inherited adjustments before accepting any explicitly supplied athlete coaching. Recovery cannot overwrite the edited prescription or license stale numerical progress against it.
* React previously suppressed all Progress and showed only the first Easier. It now renders validated Progress once and preserves authored Easier options in the existing layout. Stop rules and open-plan deload display retain their established treatment. The release harness now asserts visible Progress wording, not just the saved value.

## Replacement safety coverage

| Old assertion or fixture | Replacement covering its intent |
| --- | --- |
| Python creates seven types of next-exposure increment | Same parametrized tests first assert no invention, then supply explicit AI wording and assert exact preservation; unsupported-future and new hidden-change tests assert rejection. |
| Python creates an increment without a future exposure | Missing-note cases assert absence; flat-dose and unknown-load tests reject authored promises. |
| Invalid bank increment becomes Python's supported increment | Precise-step and three hidden-change cases assert rejection with no replacement. |
| Python creates numerical Easier | Numerical-Easier case first asserts absence, then validates the authored reduction. Recovery-context tests supply their own Easier wording. |
| Quality Progress moves into Cue | Context tests retain its semantic Progress field, including safe recovery guidance. |
| Stage 1 bank adjustments restore missing final-session fields | Recovery tests distinguish source-free absence from exact final-text restoration. |
| Old generated profile becomes new numeric advice | Historical-card tests preserve dose/warnings and reject invalid promises without synthesizing a new rule. |
| Conversion fixture generates the field it tries to drop | Release fixtures supply explicit AI fields; both omitted and nonempty altered fields block conversion. |
| React hides every Progress | Expanded-row and detail-sheet tests assert actual authored Progress text once; stop-only and empty-rule cases still show no Progress label. |
| First Easier is silently selected | Distinct authored options survive; exact duplicate strings are deduplicated without rewriting. |

`test_ai_coaching_contract.py` adds adversarial numerical/equipment/clinical checks plus real persistence/effective-plan/React coverage for valid output, unsafe output, missing Easier, conversion loss/invention/rewrite, duplicate sessions and changed prescriptions. Existing recorded programme examples are retained.

## Athlete-facing examples

| Situation | Before | After |
| --- | --- | --- |
| Squat prescribed 3 × 8 now, 3 × 9 next | Valid AI Progress could be discarded during reconciliation or saved but hidden | “Next D-28: add 1 rep per set if controlled and recovered.” survives conversion, save and expanded card. |
| AI Easier for the same squat | Could be dropped or replaced by generic/shortened copy | “Use a shallower pain-free squat; keep the same rest.” remains unchanged. |
| Next dose stays 3 × 8 | “Add 2 reps per set” could survive recovery | Instruction is rejected; no substitute Progress is manufactured. |
| Unknown starting load | “Add 2.5 kg” could survive | Instruction is rejected. |
| Athlete changes current sets | Original AI promise could remain attached to a new prescription | Edit preserves the athlete's prescription and clears inherited adjustments. |
| No AI Easier | Tests expected a generated alternative | Source-validation finding; safe source/programme fallback, with no invented Easier. |

## Verification limits and safety behaviour

Validation deliberately abstains on unsupported language, ambiguous identities, unknown quantities or missing workload authority. This can suppress useful coaching; it cannot license an invented increase. This is a deterministic validator for the existing coaching fields, not a new coaching engine. No new model calls/retry loops, exercise selection changes, workload changes, readiness changes, clinical-stage changes or CI exemptions are introduced.

Persistence tests use the real persistence function with the repository's in-memory store, then resolve the saved row and render the actual React component. They do not write to a live production database or invoke a live model. Production model wording outside the supported validation grammar may be rejected and must remain absent; it is never rewritten into a guessed instruction.

Further decisions from publication-path verification:

* Direct store creation, Stage 2 updates and structured-only backfills apply the same coaching checks. A backfill reuses the row from its stale-text guard, or reads the current row once when it otherwise lacks source/dose authority. Existing JSON columns and database schema are unchanged.
* Athlete-facing API markdown is checked on read for historical plans; the stored row and admin source remain available for audit. A legacy text fallback cannot re-expose a rejected numerical Progress line.
* A known current dose retained in execution metadata can validate a recovery Easier reduction. Explicit current card statistics take precedence, so restoring coaching never rewrites an edited prescription.
* Open-plan reconciliation no longer borrows a block from a global exercise-name lookup. It matches the appointment on its weekday, preferring its exact title, and abstains on ambiguity. A new reversed-order duplicate-appointment regression test covers this path.
* Existing schema-only resolver/persistence fixtures contained “Goblet squat” as a bare alternative with no equipment authority. Those fixtures now provide actionable same-movement authored Easier; their identity, dose, persistence and immutability assertions remain intact. Open-plan preservation fixtures similarly use valid quality guidance rather than unsupported automatic numerical growth.
* Additional checks reject unquantified workload increases (“more weight”, “higher RPE”), wrong future timing, bold Markdown label bypasses, and quality Progress that conflicts with the existing clinical restriction guard.

## Main comparison

Base: `8ba651ebe4835164e5a96314360008f0a694900b` (latest Main when work began).

The untouched local Main comparison produced 603 passed / 3 failed in the 606-test conversion, fidelity, safety, persistence, effective-plan, customisation, fallback and calendar set. A separate open-development comparison produced 20 passed / 1 failed. These four unchanged failures are:

1. `tests/test_exercise_customisation.py::test_library_dose_fields_follow_the_drill[Tempo Hill Runs-intervals]` — catalogue dose metadata.
2. `tests/test_structured_plan_stop_rules.py::test_converter_prompt_requires_compact_athlete_facing_stop_rules` — existing assertion expects “no more than 10 words”, while Main's prompt says 9.
3. `tests/test_card_replay_representative_plans.py::test_final_mental_calendar_is_compact_attached_and_within_frequency[affected_boxer]` — existing mental-calendar expectation.
4. `tests/test_open_plan_development_block.py::test_two_hard_power_open_block_never_turns_a_microdose_into_full_strength` — existing microdose-selection expectation.

These are neither disabled nor repaired by this PR. Main CI is already red: [Python Quality](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39448613153) and [Web Build](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39448613380) failed; [Backend Checks](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39448613333) passed. The local four-module coaching baseline is exactly the reported 47 failed / 73 passed.

## Final verification

* Expanded backend release set: **977 passed, 4 failed** in 981 tests. Every remaining failure is reproduced on untouched Main and listed above. This run covers all four coaching modules; conversion/fidelity/safety; deterministic fallback; persistence/effective plans; athlete edits/customisation; Stage 2 validation; calendar/identity; open programming and development.
* The final focused ownership suite separately includes all 64 new contract cases (including checks added after the broad run). Final four-module and ownership counts are recorded below after completion.
* Frontend unit suite: **2,113 passed, 0 failed**. Subsequent focused rendering/library checks after the final label-handling change: **191 passed, 0 failed**.
* Frontend typecheck passed. ESLint passed with **0 errors and 51 existing warnings**. Production build uses non-secret placeholder public API/Supabase settings because no production configuration is installed in this workspace; build outcome is recorded below after completion.
* Ruff and Python compile/import checks passed. No CI checks were modified or disabled.

No confirmed unsafe accepted case remains in the tested coaching contract. Quantitative validation is exact where authority is available and rejects unsupported claims. Clinical prose checks reuse the existing restriction guard and a bounded equipment/movement vocabulary; this is not a proof of arbitrary natural-language medical meaning. A valid but unrecognised formulation, or a numerical renewable-plan rule without a comparable supported exposure context, can be suppressed. No replacement is invented. No live model, production database, deployment or merge was performed.

Final focused release confirmation: **184 passed, 0 failed** — the four inherited coaching modules now pass **120/120**, compared with Main's 73 passed / 47 failed; the additional ownership/safety/publication suite passes **64/64**. The production frontend build completed successfully with the placeholder public build configuration described above. Safe final text retains its original whitespace, including a trailing newline.


The final source-ownership review also closes two source-free fallback gaps: Stage 1 bank Progress/Easier is never promoted into final-session AI fields when final text is unavailable, and a hosted priority microdose now reads its own source-backed coaching instead of dropping it. Explicit recovery restrictions passed to a helper also override a less-restricted exposure context, without removing safe same-dose quality guidance.

| Coaching module | Main passed / failed | PR passed / failed |
| --- | --- | --- |
| Measurable exercise coaching | 38 / 24 | 62 / 0 |
| Exercise coaching context | 5 / 11 | 16 / 0 |
| Exercise coaching release | 15 / 10 | 25 / 0 |
| Concise exercise coaching | 15 / 2 | 17 / 0 |
| New AI ownership/safety/publication cases | — | 64 / 0 |

Additional store protocol/performance, plan-contract and Stage 2 automation checks: **100 passed, 0 failed**. Final targeted preservation checks also cover an unknown legacy load representation and byte-for-byte safe text with a trailing newline. The PR is for review only; it is not merged and auto-merge is not enabled.

After closing the source-free bank/microdose gaps, the final fallback, source-dose, open-programming and effective-plan verification passed **65/65**. No workload, selection or clinical-policy change was needed.
