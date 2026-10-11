# Executed verification — investigation PR 1

Baseline: `Main` at `a91b0be3593b6887162866c19712ab087392d459`, after PRs #2816, #2818 and #2820. Work was performed in an isolated worktree; unrelated changes in the original checkout were excluded.

## Results

| Check | Result |
| --- | --- |
| Final metadata audit test file | 14 passed |
| Existing catalogue and training-library tests | 88 passed, in the initial combined run with 13 audit tests (101 passed total) |
| Focused programming, injury, rehabilitation and media regressions | 716 passed |
| Deterministic generated-report comparison (`--check`) | Passed |
| Ruff on the two new Python files | Passed |
| Python compilation of the two new Python files | Passed |

There are **818 distinct passing tests** across these groups in the final test set. The final audit-only rerun includes the additional alias-collision test. Counts above describe the executed suites, not the number of semantic findings or the entire repository suite.

```powershell
python tools/audit_metadata_integrity.py --check
python -m pytest tests/test_metadata_integrity_audit.py -q
python -m pytest tests/test_training_catalogue.py tests/test_training_library.py -q
python -m ruff check tools/audit_metadata_integrity.py tests/test_metadata_integrity_audit.py
python -m py_compile tools/audit_metadata_integrity.py tests/test_metadata_integrity_audit.py
```

The existing catalogue/library tests were executed together with the initial audit tests using:

```powershell
python -m pytest tests/test_metadata_integrity_audit.py tests/test_training_catalogue.py tests/test_training_library.py -q
```

The focused regression command was:

```powershell
python -m pytest tests/test_exercise_bank_phases.py tests/test_exercise_bank_late_windows.py tests/test_style_taper_bank_governance.py tests/test_strength_metadata_selection.py tests/test_conditioning_metadata_selection.py tests/test_coordination_support_v2.py tests/test_technical_footwork_injury.py tests/test_restriction_filtering.py tests/test_injury_guard.py tests/test_rehab_selector.py tests/test_rehab_stage_boundaries.py tests/test_rehab_pathway_safety_invariants.py tests/test_reviewed_rehab_progression.py tests/test_rehab_completion_capture.py tests/test_exercise_media.py -q
```

## Preservation evidence

- Independently count every source row, including grouped rehabilitation drills, all five coordination sources and the empty legacy coordination shim. Assert 2,855 distinct pinned catalogue identities and the expected content-class totals; archive rows are excluded.
- Compare every extracted raw row, group, field occurrence, JSON pointer and value type with its source. Retain nulls, empty arrays, numeric values, ordering, prose and compound strings without normalisation or splitting.
- Detect compounds and repeated risk tokens while preserving distinct concepts. Adversarial controls preserve reaction versus mechanics, neck versus vestibular focus, unresolved timing semantics and valid fixed-duration ranges such as `[3, 3]`.
- Compare generated reports between runs and against their retained files. Outputs have no execution timestamps or absolute checkout paths.
- Compare the frozen source, configuration, production-file, row-hash, catalogue-ID and media-key baseline. SHA256 comparisons normalise only checkout CRLF to LF; a separate fixture compares raw file-byte hashes around audit execution.
- Generate a real fixed-seed training plan before and after the full audit. Assert identical `plan_text` and `stage2_payload`, alongside the existing catalogue/library and focused runtime regressions.
- Reject source drift rather than silently refreshing the baseline. No bank, generator, search-ranking, clinical-policy, identity-manifest or schema file is modified by this PR.

## Limits and follow-up

The full repository suite and frontend build were not run. This PR adds no frontend or production implementation changes. No live database, deployment or external exercise-efficacy dataset was queried.

Static receipts and reviewed consumer families identify dependency evidence; they do not prove execution of every possible dynamic branch. Unestablished enforcement and vocabulary without raw source occurrences remain explicit REVIEW findings, not unused-value claims. The accuracy report screens suspicious associations and incomplete declarations; neither a passing test nor an unflagged row certifies scientific or clinical accuracy.

Qualified source review remains required for the unresolved assignments, equipment grouping, clinical declarations and intentional behaviour changes. The [roadmap](roadmap.md) specifies the scope and before/after gates for each remediation PR. PR 1 performs no remediation.
