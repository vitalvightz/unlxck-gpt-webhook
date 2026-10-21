# Rehab progression validation

Baseline: Main `7161c7f53a7186a69b21419cadc24d0dacceba24`, fetched at task start. This branch changes no bank/pathway/ledger content, clinical activation, database schema, RLS or historical event shape.

## Checks

| Check | Result |
| --- | --- |
| Four real Complete → Better → next-day Same journeys, including actual visible exercise and internal requirements | Passed for Achilles, lateral elbow, ankle sprain and cuff shoulder |
| New repeated-work / historical recovery / generation / defined-dose regressions | Included in `tests/test_rehab_consumer_journey.py`; final aggregate recorded below |
| Real PostgreSQL RPC, trigger, ownership, concurrency and frozen-work tests | **49 passed on Main; 49 passed on branch** (`test_rehab_lock_concurrency`, `test_clinical_review_capture_postgres`, `test_intake_injury_sync_postgres`) |
| Targeted frontend status, injury response and clearance tests | **105 passed** |
| Runtime 64-profile report vs actual baseline policy selection and committed artifact | Passed |
| Python transition/scheduler tests after compatibility correction | **65 passed** |
| TypeScript typecheck | Passed |
| Frontend lint | Passed, 51 existing warnings |
| Python imports/compilation and Ruff | Passed at implementation checkpoint; final check recorded below |

The real PostgreSQL tests use a disposable localhost PostgreSQL **17.11** cluster, matching CI's major/minor. No production database or athlete records were accessed. Unit journey storage uses FakeStore with real persisted event shapes; its explicit injury-event adapter represents the SQL trigger rather than mocking a progression decision. Historical UUIDs, immutable frozen blocks and response-group identities are retained.

## Main comparison

Main's complete affected rehab selection (before new tests) returned **2,598 passed, 17 skipped, one failed** locally. The failure is:

`tests/test_rehab_prescription_bundles.py::test_today_uses_live_bundle_only_for_injury_specific_restore_evidence[worse-calm-ids2]`

The current Main hosted workflows were already red before this branch: [Python Quality](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39522441271) and [Web Build](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39522441244). Backend Checks and Validate JSON Banks passed on that exact Main commit. Hosted job logs and PR check outcomes are compared after publication; do not interpret inherited red checks as a green release gate.

An initial local attempt to run the entire repository with pytest-xdist could not collect identical tests because unrelated tests construct random UUID parameter IDs at import. The repository's module-sharded CI invocation avoids that issue. Full module-sharded local runs were sampled and then stopped on the two-CPU workspace in favour of the complete affected rehab run and the hosted six-shard workflow. No incomplete run is counted as passing. Local Python is 3.12; hosted CI uses pinned Python 3.11.15.

## Safety coverage and limits

The affected suite includes all four pilot activation suites, the groin closure suite, shared transition and evidence contracts, completion capture/API flow, stage resolution, selector storage envelopes and aliases, metadata/hash validators, schedule/bundle allocation, clinical assessment boundaries, generation ownership, multi-injury restrictions and started/completed snapshot immutability. It exercises missing/withdrawn rehabilitation permission separately from training/contact scopes; supported and unknown subtype/severity/side; wrong episode evidence; unreviewed/partial/stopped work; next-day unknown/Worse; relevant and irrelevant second injuries; and saved unstarted revalidation.

The current 1,604 bank identities and all clinical hashes are unchanged. The report probes verify conditional content compatibility with known side, supported severity and exact source apparatus. They are not patient-specific medical clearance or a claim that dormant exercises are usable. Production deployment, real athlete data and authenticated production browser interaction were not verified, and this PR must not merge automatically.

## Final aggregate

Validation is in progress while the draft PR checks run. This section will be updated with final affected-suite counts, the exact new-test comparison against Main, frontend build/unit results and newly failing hosted checks before handoff.
