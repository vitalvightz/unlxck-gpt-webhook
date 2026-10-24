# Injury-aware programme integrity audit

## Evidence and scope

Read-only inspection of Supabase plan `1ef4f5bc-dc44-49d3-93c0-7295c3826a06` confirmed `full_plan`, empty restrictions, no clearance requirement, and populated strength pools. The saved payload's rehab candidate was an activity-guidance paragraph with its stop/referral paragraph repeated. The stored validator marked the structured card valid and athlete-releasable. Its calendar contract check reported no weekly schedule, as a warning.

The saved payload predates the current deterministic Open Build development-block path. Current `Main` already has bounded goal repair, closed session membership, structured fallback, rehab instruction/safety separation, and non-limiting injury awareness. This change extends those owners; it does not reproduce the older generator or attribute every historical omission to today's code.

## Trace and confirmed defects

| Boundary | Existing owner / defect | Change |
| --- | --- | --- |
| Onboarding / Camp Setup | `PlanIntakeForm` uses `GuidedInjuryCard` and `INJURY_IMPACT_OPTIONS`; notes store the existing impact marker. | Keep the existing choices and wording. |
| Quick Build | Separate `QuickBuildForm` exposed only symptom text. `planRequestToQuickBuildInput` discarded structured injury context on conversion back into a request. | Use the same three impact options and chip styles. Prefill existing impact and retain guided injury details. Preserve the marker in new raw reports and saved requests. |
| Injury parsing | `_parse_guided_injury` copied only `not_limiting` into the canonical parsed field; raw Quick Build had no impact interpretation. | Carry all existing choices through both paths, without rewriting reported medical severity from raw text. |
| Triage / runtime | Triage runs first. `build_runtime_context` then removed every marked non-limiting injury and even its explicit avoidance restrictions. | Reuse `is_awareness_only`; independent medical evidence and explicit avoidance survive. Never discard explicit restrictions merely because of the impact choice. |
| Candidate selection | Injury guard and exercise-specific contraindications already filter movements. | Leave these safety authorities intact. |
| Role budgeting | `_active_injury_is_moderate_plus` counted any non-surface symptom and generic `injury_management` as moderate-plus, unlike the existing severity-aware crowded-week policy. | Use the existing severity-aware interpretation; low/missing severity alone does not add global compression. Significant functional inability and genuine moderate/high injury evidence still do. |
| Suppression audit | Compression wrote `compression_reason_codes`, but Open Build's projection read `reason_codes`, falling back to `role_budget`. | Preserve canonical reason codes and all details in the projected removal ledger. |
| Rehab selection / Stage 1 | `_reviewed_episode_option` rendered informational bank entries as drills and appended stop text already present in their instructions. `_build_rehab_slots` promoted those lines into closed exercise membership. | Keep advisory entries in informational summaries; preserve distinct stop rules once; exclude legacy advice lines from selected and alternate rehab slots. Deduplicate identical selected drill lines. |
| Stage 2 | Finalizer consumes selected membership and injury context. | Explicitly keep precautions in Rehab / Red Flags once. Carry distinct informational rehab summaries in injury context. |
| Structured conversion | Schema validity did not distinguish medical advice from an exercise. Existing S&C conversion coverage checked dated D-days only. | Block advice masquerading as an exercise, even with invented sets/reps. Check Open Build conversion against planned weekday exercise membership. Use existing injury notes / red-flag fields for information. |
| Release validation | `validate_goal_preservation` returned success immediately for Open Build without the dated goal contract version. | Validate the canonical goal-preservation contract before projection; unjustified loss, missing evidence and invalid coverage block release, while justified secondary deferrals remain permitted even when unsatisfied. No minimum session/exercise count. |
| Plan rendering | Existing `RehabExerciseGuide`, `RehabExerciseLimits`, plan notes and red flags already separate execution instructions from precautions and consolidate narrow duplicate warnings. | Reuse these components; no redesign or changes to exercise editing/logging/completion. |

## Behaviour

An occasional symptom remains subject to triage and movement-specific filtering, but no longer contributes global readiness compression just because an injury is present. Existing medical holds, contraindications, clinician avoidance, contact legality and dose rules still apply. Significant limitations can legitimately reduce programming. The planner retains the causal reasons rather than presenting a generic budget explanation.

Quick Build now offers exactly Camp Setup's existing `not_limiting`, `limiting`, and `cant_train` click choices. Missing answers remain missing; legacy records still load. An unrecognized historical impact remains unspecified rather than becoming a significant limitation. Original symptom text remains separate from the stored impact metadata. Detailed inherited injuries can be updated through the existing full intake; Quick Build can update their impact while retaining their restrictions.

Advice is informational, never counted as rehab stimulus. Distinct safety instructions remain visible through the existing guidance surfaces. Previously persisted production cards are not rewritten by this PR.

## Verification and limits

Regression tests cover raw Quick Build impact parsing; guided impact provenance across four regions; low, mild, significant, unknown and legacy states; simultaneous injuries; authoritative restrictions; preservation of strength/conditioning under the supplied symptom and a shoulder symptom in Open Build and Fight Camp; suppression causes; advisory drill rejection; stop-text deduplication; and Open Build goal/conversion checks. Existing safety, triage, intake sync, architecture, composition and rendering suites provide additional coverage.

The original symptom replay retains strength and conditioning. It does **not** prove every requested goal is satisfied in every calendar: existing bounded goal validation still reports uncovered power/conditioning/footwork in some Fight Camp variants. These remain blockers, not grounds to manufacture filler, bypass a contraindication or claim a releasable plan. Further candidate/placement work for those deficits is separate from this fix.

No live model finalization, production end-to-end generation, production record mutation or deployment was performed. Database persistence is exercised with the existing fake-store tests; live Postgres persistence tests require a dedicated test database. Historical malformed cards require regeneration, not an unreviewed production backfill.

Untouched `Main` reproduces three failures in this environment: two tests in `test_injury_triage.py` (text severity evidence and negated fracture history) and `test_two_hard_power_open_block_never_turns_a_microdose_into_full_strength`. These are not waived by this patch. The environment uses the repository's fast dependency set without spaCy.

### Recorded checks

- 614 focused Python tests passed.
- 87 existing injury/rehab rendering and interaction tests passed.
- 39 Quick Build/health-consent tests passed, including marker persistence and inherited-injury updates.
- TypeScript typecheck and production frontend build passed with placeholder public configuration.
- Playwright Quick Build passed at 320, 390, 430 and 1280 pixels, including the three impact cards, selected state, no horizontal overflow, no page errors, and the saved request payload. Browser plugin was unavailable, so the repository's Playwright workflow was used. Keyboard selection and a scoped axe accessibility scan also passed. Screenshots remain outside committed source.

## PR review corrections

- Quick Build impact updates now change only the notes marker. They no longer map the selection back onto an existing guided injury's severity. High severity, clinical notes, clearance, worsening trend and independently recorded avoidance remain unchanged, including for `not_limiting`. Regression tests cover every impact choice and confirm the source record is not mutated.
- Open Build now evaluates `validate_goal_preservation` on the canonical development block before weekday projection, retaining per-goal contract errors. Release validation consumes that verdict rather than treating `satisfied: false` as an automatic failure. A genuinely causal secondary deferral can pass; missing or stale causal restrictions, unjustified primary loss, missing contract evidence, invalid states and evidence absent from planned weekday membership still block. No repair or new deferral policy was added.
- Affected Quick Build/health-consent tests: 41 passed; TypeScript typecheck passed. Affected planner tests: 157 passed, with the previously reproduced baseline failure `test_two_hard_power_open_block_never_turns_a_microdose_into_full_strength` still failing (one exercise versus its expected two to three). No merge or deployment; PR remains draft.
