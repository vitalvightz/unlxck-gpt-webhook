# Verification, coverage gaps and limitations

## Existing tests run

Environment: Python 3.13, `requirements-dev-fast.txt` (no spaCy — injury
parsing runs in its documented degraded mode; guided-injury inputs used here do
not depend on it).

**Focused planner/validator suites — 1,312 passed, 0 failed** (`pytest -n 4`,
~2 min): `test_bridge_rules`, `test_calendar_integrity`,
`test_calendar_integrity_characterization`, `test_camp_week_filler_aerobic_budget`,
`test_camp_week_fillers`, `test_canonical_session_composition`,
`test_closed_session_composition`, `test_conditioning_session_minimum`,
`test_conditioning_session_resolution_workload`,
`test_consecutive_strength_recovery`, `test_cross_day_realised_load`,
`test_dynamic_sparring_cutoff`, `test_gap_fill_inserts`,
`test_goal_preservation` (+ `_e2e`, `_followups`, `_resolved_evidence`,
`_windows`), `test_injury_exclusion_hardening`, `test_injury_guard`,
`test_late_camp_architecture_cliff`, `test_late_fight_strength_windows`,
`test_placement_ownership`, `test_planner_authority_integrity`,
`test_planner_policy_wiring`, `test_prescription_resolver` (+ `_e2e`),
`test_scheduled_day_strength_authority`, `test_stage1_parity`,
`test_stage2_validator`, `test_stage2_validator_postprocess`,
`test_standalone_strength_minimum`, `test_step10_architecture_closure`,
`test_strength_low_cost_support`, `test_support_insert_movement_blocks`,
`test_validator_release_invariant`, `test_weekly_priority_exposure_floor`,
`test_sparring_dose_planner`, `test_structured_plan_sparring_reconcile`,
`test_sparring_readiness_boundary`, `test_stage2_automation`.

**Full fast lane** (`-m "not spacy"`, 498 test files, excluding `tests/e2e`),
on unmodified `Main`: **14,597 passed, 25 skipped, 4 failed** (1,465
spaCy-marked tests deselected). `pytest -n` cannot be used on this suite
because several parametrised IDs are random per process (e.g.
`test_clinical_review_capture.py`, `test_community_exercises.py`), so xdist
workers disagree at collection; the run was split into 8 file shards instead,
with `test_clinical_review_capture.py` run alone (69 passed).

The 4 failures, none in the generation chain:

| Test | Cause |
| --- | --- |
| `test_exercise_media_search.py::test_auto_provider_uses_ytdlp_even_when_paid_providers_are_configured` | `yt_dlp` not installed here (environment) |
| `test_today_read_amplification.py::test_push_sweep_builds_each_athletes_today_once` | `pywebpush` would not build here (environment) |
| `test_metadata_integrity_audit.py::test_running_full_audit_preserves_deterministic_training_outputs` | Passes when run alone; fails only inside its shard — order-dependent shared state (test-isolation issue, not investigated further) |
| `test_ankle_load_activation.py::test_other_sprain_type_uses_existing_recovery_monitoring` | Fails alone too (`prescribed_rehab` vs `unsupported_prescription`). Today/rehab surface, outside this audit's chain; it may depend on spaCy-less parsing. Not investigated — flag for the Today owners |

Every confirmed finding coexists with a green suite. That is the central
coverage result.

## Why the suites did not catch the findings

| Gap | Where | Finding |
| --- | --- | --- |
| Composition trunk tests build slots by hand with `tags: ["trunk_strength", "core"]`; real Stage 1 pools never contain such a slot | `test_canonical_session_composition.py:166-184`, `test_conditioning_session_minimum.py:85-180` | F01–F03 |
| The tag-map test asserts the map's *contents*, not that strength scoring consumes it | `test_tagging_consistency.py:58-61` | F01 |
| The e2e test locks "a delegated weak area adds no obligation" but nothing asserts the delegate delivered | `test_goal_preservation_e2e.py:127-134` | F03, R1 |
| Goal-preservation e2e uses one MMA fixture (26 d) and overrides; no boxer, no injury, no short camp | `tests/fixtures/goal_preservation/sheyi_like.json` | F06–F08, F13 |
| No invariant that a surviving normal-camp strength/conditioning role has members; the authority gate checks late-tail roles only | `planner_authority_integrity.py:296-317` | F08 |
| Microdose tests check rendering and dedup, not injury, equipment or host emptiness | `test_weekly_priority_exposure_floor.py` | F06, F07 |
| Injury hardening has no foot rows for jumps/landings | `test_injury_exclusion_hardening.py` | F05 |
| No sport × camp-length generation grid | — | F11 |
| `_HARD_SPARRING_STRENGTH_BLOCK_DAYS_OUT` untested and undocumented | `input_parsing.py:34` | F12 |
| Architecture-closure tests check imports and ownership lists, not execution order | `test_step10_architecture_closure.py`, `test_placement_ownership.py` | F09 |
| No agreement test between the resolver's and the authority gate's "loaded" | — | F10 |
| No classifier test over the real bank for "low-load trunk support" | — | F04 |
| Coverage-window tests do not include a 14-day camp or a ≤ 10-day maintain goal | `test_goal_preservation_windows.py` | F13 |

Recommended standing additions (one per root cause; details in
`roadmap.md`): a scenario-matrix e2e driven by `repro/matrix.py` definitions
with these invariants —

1. every selected goal/weakness has a verdict (satisfied / deferred with a
   cited constraint / delegated-and-verified);
2. no surviving physical role has empty closed membership without an
   authoritative body;
3. no member violates the athlete's injury region, equipment or the scheduled
   day's envelope, whoever authored it;
4. no two strength roles share a D-14+ day; no strength role sits on a
   glycolytic day after relocation;
5. zero planner-authority blockers on valid inputs; every supported sport ×
   {14, 35, 56, 84} days generates;
6. D-17 hard / D-10, D-3 technical (known case) and the triage blocks stay
   unchanged.

## Limitations

- **No Stage 2 or card model calls.** Findings are in the deterministic
  handoff; Stage 2 behaviour was assessed from the prompt, render manifest and
  validator code only. Card faithfulness (R3) is unverified at runtime.
- **No database or real athlete records.** Generation-time readiness
  snapshots (`_sparring_readiness`), rehab-stage context and completion history
  were absent; the triage-resume path was exercised with a synthetic override.
- **spaCy absent.** Free-text injury parsing was not exercised; all injuries
  used the guided card.
- **Pairwise, not exhaustive.** 32 scenarios plus probes; counts in
  `scenario_matrix.md` describe this sample, not production frequency.
- **Fixed calendar.** Clock 2026-01-04 (a Sunday generation day, Monday camp
  start). Weekday-dependent placement can differ for other start days.
- **Open-ongoing plans** were checked only for the documented absence of an
  executable goal contract; their calendar was not audited.
- **Nutrition, mindset, recovery copy and the web client** were out of scope
  except where they affect generated sessions.
- **Clinical judgement.** F05's severity boundary and R2 are flagged for
  clinical/coaching review; the audit does not set exercise policy.
