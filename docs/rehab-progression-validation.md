# Rehab progression validation

Original baseline: Main `7161c7f53a7186a69b21419cadc24d0dacceba24`, fetched at task start. Follow-up PR #2977 is based on merged Main `4af1dfb9de273dc78029f7c0d2e56c7480861bc6`, also confirmed as remote Main during review. Bank and ledger content, clinical stage activations, database schema, RLS and historical events are preserved. The later authorised permission-entry revision changes four policy versions/hashes and entry behaviour and normal prescription execution metadata; prescribed exercises and clinical limits stay unchanged.

## Checks

| Check | Result |
| --- | --- |
| Four real Complete → Better → next-day Same journeys, including actual visible exercise and internal requirements | Passed for Achilles, lateral elbow, ankle sprain and cuff shoulder |
| Repeated work, exposure and standalone injury-check-in setbacks, generation, defined dose, scheduler/transition contracts | **101 passed**; all four pilots hold after injury-only Worse → Same, even with renewed advice, until genuine post-setback recovery work |
| Real PostgreSQL RPC, trigger, ownership, concurrency and frozen-work tests | **49 passed on Main; 49 passed on branch** (`test_rehab_lock_concurrency`, `test_clinical_review_capture_postgres`, `test_intake_injury_sync_postgres`) |
| Targeted frontend status, injury response and clearance tests | **105 passed** initially; the final blocker component suite has **11 passed**, including the additional injury-check-in setback explanation |
| Runtime 64-profile report vs actual baseline policy selection and committed artifact | Passed |
| Completion provenance/API/journey/scheduler/transition checkpoint | **217 passed**, before the additional standalone-report and LOAD-flare journeys; the final aggregate includes those additions |
| TypeScript typecheck | Passed |
| Frontend lint | Passed, 51 existing warnings |
| Python imports/compilation and repository Ruff | Passed on final source changes |

The real PostgreSQL tests use a disposable localhost PostgreSQL **17.11** cluster, matching CI's major/minor. No production database or athlete records were accessed. Unit journey storage uses FakeStore with real persisted event shapes; its explicit injury-event adapter represents the SQL trigger rather than mocking a progression decision. Historical UUIDs, immutable frozen blocks and response-group identities are retained.

## Main comparison

Main's core affected rehab selection (before new tests, with groin checked separately) returned **2,598 passed, 17 skipped, one failed** locally. Main's isolated groin suite passed **65 tests**. The core failure is:

`tests/test_rehab_prescription_bundles.py::test_today_uses_live_bundle_only_for_injury_specific_restore_evidence[worse-calm-ids2]`

The exact Main hosted workflows were already red before this branch: [Python Quality](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39522441271) and [Web Build](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39522441244). Backend Checks and Validate JSON Banks passed on that Main commit. Do not interpret inherited red checks as a green release gate.

The completed six-shard [PR Python run at e8b46a36](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39528618061) returned **17,884 passed, 96 failed, 13 errors, 128 skipped**. All 69 failing/error nodes from Main reappear. Main shard 3 was cancelled; another **39** PR failing/error nodes were individually replayed on unchanged Main and **all reproduced** (37 failures, two fixture errors). The one additional branch-specific failing node was a historical whole-file freeze assertion covering the intentionally changed follow-up label and subsequently refreshed completion-service runtime fingerprint. It now normalises only those exact authorised deltas, retaining the original manifest, clinical judgments and every other protected byte. Exact node sets and comparison limits are in [rehab-ci-comparison.json](rehab-ci-comparison.json).

Main's full frontend unit suite passed **2,114 tests**; this branch initially passed **2,118** (four new blocker cases), with the extra standalone-setback explanation verified separately. Typecheck, lint and production build passed. The earlier hosted PR web run passed these checks too, then retained the same smoke/accessibility failing or flaky cases seen on Main: mental layout, round timer, starting path and custom plans. No unrelated frontend failure was repaired here.

The hosted Python dependency audit still reports the same eight Pillow 12.3.0 vulnerabilities as Main (the audit recommends 13.0.0). Dependencies are unchanged; this remains an inherited release concern.

The first 24 new consumer-journey cases copied onto unchanged Main returned **19 failed, five passed**; the corresponding branch cases pass. An inherited fixture alias issue also reproduces when Main's metadata-contract and groin suites run together (two failures, 110 passes); the groin test now snapshots its expected drill rather than retaining another test's discarded mutable bank object. No clinical manifest was rehashed.

An initial local attempt to run the entire repository with pytest-xdist could not collect identical tests because unrelated tests construct random UUID parameter IDs at import. The repository's module-sharded CI invocation avoids that issue. Full module-sharded local runs were sampled and then stopped on the two-CPU workspace in favour of the complete affected rehab run and the hosted six-shard workflow. No incomplete run is counted as passing. Local Python is 3.12; hosted CI uses pinned Python 3.11.15.

## Safety coverage and limits

The affected suite includes all four pilot activation suites, the groin closure suite, shared transition and evidence contracts, completion capture/API flow, stage resolution, selector storage envelopes and aliases, metadata/hash validators, schedule/bundle allocation, clinical assessment boundaries, generation ownership, multi-injury restrictions and started/completed snapshot immutability. It exercises missing/withdrawn rehabilitation permission separately from training/contact scopes; supported and unknown subtype/severity/side; wrong episode evidence; unreviewed/partial/stopped work; next-day unknown/Worse; relevant and irrelevant second injuries; and saved unstarted revalidation.

The current 1,604 bank identities and their clinical bank hashes are unchanged; the permission revision intentionally versions four pathway policies. The report probes verify conditional content compatibility with known side, supported severity and exact source apparatus. They are not patient-specific medical clearance or a claim that dormant exercises are usable. Production deployment, real athlete data and authenticated production browser interaction were not verified, and this PR must not merge automatically.

## Aggregate before permission-entry revision

The complete final-source affected run returned **2,700 passed, 17 skipped, two failed**. One failure is the unchanged Main bundle case named above. The other was the groin freeze assertion for the explicitly refreshed completion-service fingerprint; that test-only compatibility correction is verified by the combined metadata-contract/groin run: **112 passed** (the same cohort has two failures on Main). The 17 skipped real PostgreSQL cases pass in the separate 49-test PostgreSQL run. No unresolved new production failure was found in the affected selection.

Reproduction commands:

```sh
python -m pytest -q -n 2 tests/test_rehab* tests/test_achilles* tests/test_ankle_load_activation.py tests/test_lateral_elbow_load_activation.py tests/test_shoulder_load_activation.py tests/test_groin_load_hold.py tests/test_api_rehab_completion_flow.py tests/test_injury_policy_journey.py tests/test_multi_injury_today.py
python -m pytest -q tests/test_rehab_metadata_contract.py tests/test_groin_load_hold.py
python -m pytest -q tests/test_rehab_consumer_journey.py -k standalone
python tools/report_rehab_reachability.py --check
python tools/review_rehab_advanced_candidates.py --check
```

Original progression-fix production source commit: `ec0e8b67e89fc10b1d994802d1102f73ee745653`; the subsequent original handoff changed only test compatibility and these validation documents. Hosted [Backend Checks](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39531240915) and [Validate JSON Banks](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39531240899) pass on that source commit. Its frontend typecheck, lint, unit tests and production build also pass. The broader six-shard Python and browser workflow reruns were still running at that handoff; their completed earlier full-run comparison is retained above. This is a draft for review, with inherited red release checks, not an approval to merge.

## Permission-entry revision

The user subsequently authorised reported clinician advice to open existing published work without prior RESTORE logs. This intentionally replaces earlier tests that treated no exercise history as an automatic hold. Known pending/uncertain responses and any unresolved setback still hold loading. Foreign episode/side exposures are excluded; they do not certify tolerance, and their absence does not invalidate independent, current clinician permission.

The four policy versions are now Achilles 3, elbow 4, ankle 6 and shoulder 3. An exact historical-policy reconstruction keeps dated audits/manifests inspectable without changing their clinical judgments. No new stage, exercise, dose, resistance or clinical subtype is activated. Entry/recovery flags and the per-exercise Python option registry are removed; ordinary publication supplies the stage and prescription limits.

## Review corrections on #2977

Production/test source: `36a17e4f3b64e592f205c9e974955911e3a71d10`. The nineteen lost-clearance regressions were caused by filtering the shared clearance projection by evaluation time. That change is removed; rehab entry still independently rejects future-dated advice. Seven version expectations now match the intentionally versioned policies without relaxing their content assertions. All 26 previously failing cases pass on unchanged Main `4af1dfb9` and on this correction.

The focused correction run passed **268 tests** (excluding only the known Main bundle failure). Another **28 new tests passed**, covering permission without exercise history against unsupported/unknown subtype, medical/restriction holds, severity and withdrawal for all four profiles, plus relevant/unrelated second injuries in Today and generation. The original 52 permission tests remain covered, including all four actual visible LOAD identities, future/missing advice, pending/Worse responses and normal publication without special flags. The unchanged frontend has **2,121 passing unit tests**, **58 passing targeted tests**, passing typecheck/lint/build; lint retains 51 existing warnings.

The final-source real PostgreSQL cohort passed **49 tests**. Runtime reachability and dated advanced-candidate `--check` commands passed with no inventory or activation changes. Repository Ruff and `git diff --check` passed. The historical permission replay and its tampering test passed; the unrelated custom-plan audit failure reproduces on unchanged Main.

The reviewed six-shard [Python run at 770110fc](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39589045760) returned **17,920 passed, 123 failed, 13 errors, 128 skipped**. Its 136 failed/error nodes separate into **27 corrected here** (the 26 reported regressions plus the permission-reader historical replay guard) and **109 reproduced on unchanged Main `4af1dfb9`**. Replaying the exact latter node set returned **96 failures and 13 fixture errors, zero passes**. Exact IDs, source commits and comparison limits are retained in [rehab-permission-ci-comparison.json](rehab-permission-ci-comparison.json). This is an exact failure-node comparison, not a full fresh passing-suite run on Main.

The reviewed [web workflow](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39589045715) passed typecheck, lint, unit tests, dependency audit and production build before browser smoke/accessibility returned **197 passed, five failed, three flaky**. The failing/flaky suites are the same mental layout, round timer, starting path and custom-plan families documented against the original Main workflow. They were not rerun locally during this backend-only correction. No unrelated browser or dependency failure was repaired here.

The final complete affected run returned **2,781 passed, 17 skipped, one failed** in 624.74 seconds. The sole failure is the exact Main bundle case named above and reproduced in the 109-node Main comparison. There are **no remaining new failures in the affected selection**. All **80 permission-entry cases** and **33 consumer journeys** pass, including injury-only Worse → Same without new work. The 17 skipped PostgreSQL cases pass in the separate 49-test database cohort. The eight positive permission-entry journeys fail on unchanged Main `4af1dfb9` and pass here: applicable advice now produces the exact published LOAD exercise without fabricated completions or responses.

New hosted reruns will be reported separately; this local result does not claim that all inherited release checks are green. Earlier counts above refer to their explicitly named source commits and are retained for comparison. Authenticated production/browser interaction remains unverified; the journey proof runs real application services and persisted event shapes in test storage.
