# Generator equipment accuracy: five confirmed corrections

Base: Main `4f77cb43` (merged #2824). Scope is exactly five exercise source records, not an accuracy claim for the entire catalogue.

| Exercise | Planner source requirement | Intentional eligibility change |
| --- | --- | --- |
| Rope Climb + Short Sprint | climbing_rope | Climbing rope alone now qualifies; battle ropes never substitute |
| Rope Climb Sprints | climbing_rope | Climbing rope alone now qualifies; battle ropes never substitute |
| Towel Pull-Up Sprints | towel AND pullup_bar | Empty/partial setups no longer qualify |
| Slow-Lowered Pull-Up | pullup_bar | Bodyweight alone no longer qualifies |
| Towel-assisted lateral neck isometric | towel | No-towel setups no longer qualify |

None of these records has a `required_equipment` override. Strength reads `equipment` through its existing normalizer and subset gate in scoring and fallback. Conditioning uses the same normalized mandatory-set gate across base/style, refill, and append paths; its decorated `required_equipment` now carries the corrected source. No discovery review is imported into prescription selection. Existing aliases remain unchanged.

Five manifest hashes are rebound to the same permanent IDs. Names, exercise keys, media associations and historical identities remain unchanged. The five requirement reviews retain prior hashes/values in `source_history`; the two retired battle-rope association reviews are rebound. Tests compare all 2,855 identities and every raw source row, allowing only these five equipment-field edits.

Frozen #2822–#2824 reports and baseline files are unchanged. The existing offline replay reverses only the reviewed equipment/hash edits and the exact fallback guard insertion, then checks original whole-file hashes. Frozen discovery indexes reconstruct original contracts and revisions. Current-state tests separately verify source/discovery/generator agreement and reject non-equipment drift. No inventories or generated plans are committed.

## Programming and fallback safety

Equipment does not override phase, injury, restriction, familiarity or fight-window gates. The neck variant keeps its existing late-window and familiarity rules. Isolated real-bank generator tests cover all five exercises with complete, partial, absent, irrelevant and aliased apparatus; emitted fallback records must satisfy declared equipment.

A sparse-bank clinical test exposed an existing strength fallback bypass: primary selection rejected a declared restriction, but fallback could re-add that exercise. With explicit user approval, this PR adds the same existing restriction check to fallback. This also corrects a pre-existing restricted Sissy Squat selection in the shoulder-limited control below. Scoring formulas, doses, adaptive workload, rehab stage/clearance, contact and mechanical policies are unchanged.

## Controlled comparisons

Full generator plans use the existing probe: UTC clock 2026-10-11 09:00, athlete seed 7, Python hash seed 0, and the three original fixed athlete inputs. Complete Stage 2 payloads and plan text are compared; unchanged exercises retain exact score/reason evidence and rendered doses.

- `boxing_shoulder_limited`: GPP removes Slow-Lowered Pull-Up because no pull-up bar is available. The approved clinical fallback fix removes Sissy Squat and inserts Cossack Squat after Glute Bridge Hold. The SPP alternate pool loses Slow-Lowered Pull-Up.
- `boxing_healthy_reviewed_equipment`: GPP/SPP remove Slow-Lowered Pull-Up because the listed apparatus does not include a pull-up bar.
- `mma_no_equipment`: GPP/SPP remove Slow-Lowered Pull-Up for the same reason; the planner safely leaves the reduced pool rather than inventing apparatus.

Only strength selections, their reason logs, and corresponding candidate slots/alternates differ. All other Stage 2 content, conditioning, rehab, workload and scheduling match exactly. Rendering differs only in the selected-name summaries and the explained reason-log entries. Isolated before/after generator comparisons additionally prove both rope drills gain eligibility with climbing rope alone, the three missing-apparatus drills lose eligibility, and complete-equipment doses/scores remain identical. Towel Pull-Up Sprints correctly changes `universally_available` from true to false.

Additional current-state checks retain the original seven-window selector golden and assert exactly one additional D-1 `late_block_d1_equipment` reason for the towel-assisted neck drill, with every other diagnostic/winner unchanged. GPP role coverage now counts only anchor-capable providers, matching the existing promotion gate: without a pull-up bar, the remaining upper-pull metadata match is rehab support and cannot promise a base anchor. Adding a pull-up bar restores that supported role. No support drill or apparatus substitution is introduced to hide this reduced availability.

## Verification

- 89 new generator/source regressions, including complete fixed-clock plan comparisons (88 passed together; final added source-drift check passed separately).
- Ruff across api/fightcamp/tests/tools; Python compilation/import execution; frontend TypeScript check: passed.
- Bank validation, tag audit/migration/authority, rehab schema/review/clinical validators: passed.
- Frozen audit compatibility: 53 tests passed; equipment audit `--check` passed.
- Catalogue/library/equipment/identity suite: 171 passed. GPP coverage and late-selector expectation regressions: 24 passed.
- Full Python shards, runtime regression suites, PostgreSQL concurrency/schema checks and web build run in hosted CI. Final results are recorded on the implementation PR.

Limitations: this corrects only the five reviewed records. Other unresolved equipment compounds retain their existing behavior. PostgreSQL/live-schema and hosted build checks depend on their existing CI environments; no deployment, schema or environment-variable changes are part of this PR. Initial local parallel attempts hit memory limits and pre-existing random UUID test-collection mismatches; relevant suites use sequential local execution, with the complete suite delegated to the existing hosted CI shards.
