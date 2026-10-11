# Verification of the discovery projection

Base: Main `ad82c28911103e11915a5567fc18623c056ba7d4` (merged #2822).
The original snapshot was captured before production edits. No baseline refresh
or PR #2822 report overwrite was performed.

## Executed checks

| Check | Result |
| --- | --- |
| Catalogue, library, existing pads compatibility, generated API types | 135 passed |
| Canonical metadata, historical audit replay and schema tests | 58 passed; final retained-report check rerun after adding consumer receipts |
| Conditioning, strength, phases, generator, injury, rehab and policy regression batch | 3,178 passed, 17 PostgreSQL integration skips; two Windows memory failures passed on isolated rerun with unchanged assertions |
| Rehab fixture failure reproduction | Original Main and pre-fix branch: seed fixture passes, subsequent two clinical tests fail. After deep-copy isolation: all three pass |
| Full frontend unit suite | 1,855 passed with `--test-concurrency=2`; new persisted-equipment reload test separately passed |
| Production Next build and TypeScript | Passed using existing placeholder Supabase/API settings |
| ESLint | Zero errors; 47 existing warnings |
| Ruff over api/fightcamp/tests/tools, Python compile/import, generated schema freshness, diff whitespace | Passed |
| Existing library browser flows plus canonical filters | 10 passed in Chromium; 320/390/1280/1440 px, no horizontal overflow, axe, keyboard/focus, previews, categories and retry |
| Browser against live local library API | 3 canonical-filter flows passed at 320/390/1280 px with the actual catalogue, API adapter, test auth and fake store; one worker after a memory-limited parallel attempt |
| Original source banks, catalogue/media identities, original audit reports | All hashes/identities unchanged, all 2,855 entries accounted for |
| Reviewed fighter search | All 30 query totals, full ordered identities and exact/related evidence labels identical to original Main |
| Goal filters | All original per-entry Goal sets identical; 222/1,010 Training entries |
| Fixed-seed plans | Three synthetic payloads: complete original/current plan text and Stage 2 equality, including array order, selections, scores, doses and restrictions |

The broad regression batch was selected with:

```powershell
$taskTests = @(rg --files tests | Where-Object { $_ -match 'test_(conditioning|strength|rehab|injury|training_context|camp_phases|exercise_bank_phases|structured_plan_generation|plan_generation_response|planner_policy_wiring|planner_authority_integrity|canonical_pads_equipment)' })
python -m pytest @taskTests -q
```

The two memory errors occurred in the long-lead-in planner test (spaCy/thinc
allocation) and the policy-import subprocess probe. Both passed together on
isolated rerun. The host was near its Windows commit-memory limit; no assertion,
runtime allocation policy or programming outcome was changed to accommodate it.

The earlier rehab failures were a different problem: an existing pilot-seed
test removed the ankle activation drill from `get_rehab_bank()`'s shared cache.
That failure was reproduced with original Main code and original shared
contracts. The test now deep-copies its fixture and additionally asserts the
live drill remains present. Production caches, source banks and clinical rules
are untouched.

## Deterministic evidence

```powershell
python tools/audit_canonical_metadata.py --check
python tools/audit_metadata_integrity.py --historical --check
python tools/generate_api_types.py --check
python -m pytest tests/test_canonical_metadata.py tests/test_metadata_integrity_audit.py tests/test_api_types_generated.py -q
```

`before-after.json` includes source and identity hashes, every projected raw
token, canonical/display/dimension/subtype identities, reviewed decisions,
original and final facet values, distinct matching catalogue IDs, source
association exclusions, current consumer file/function/line references and
remaining register decisions. The backend-derived browser fixture is also
regenerated and checked by this script and its Python regression test.

The uncontrolled original Stage 2 hashes are retained. Replaying original code
with Python hash seeds 0 and 1 demonstrates an ordering-only difference at
`/stage2_payload/candidate_pools/SPP/strength_slots/4/selected/movement_patterns`
(high-torque rotation / change-of-direction). Controlled before/after probes pin
both existing planner clock bindings to 2026-10-11 09:00 UTC and Python hash seed
0, then compare full payloads without normalizing their arrays. The random seed
is 7; cases cover shoulder restrictions, reviewed equipment spellings, and MMA
with no equipment. No nondeterminism fix is made to production code.

PR #2822's offline historical replay retains the four original production
sources changed by this PR and validates them against its original hashes.
Every other replayed production/configuration/source file must still match the
original baseline. The default investigation command continues to reject any
production drift; historical mode is explicitly read-only.

## Browser QA

Browser plugin not available; the repository's existing Playwright workflow was
used with the production build and isolated test authentication. The canonical
fixture is generated by the real 2,855-entry library, rather than hand-authored
filter counts. Mobile filter and desktop result screenshots were inspected;
the intended Find a Drill page is visible and usable, with no application
overlay blocking interactions or console/page errors in the passing runs.

```powershell
$env:NEXT_PUBLIC_SUPABASE_URL='https://stub.supabase.co'
$env:NEXT_PUBLIC_SUPABASE_ANON_KEY='stub-anon-key'
$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:3100'
npx playwright test e2e/training-library.spec.ts --workers=2 --output="$env:TEMP/unlxck-pr2-browser"
```

Screenshots and test traces are kept outside the repository. Existing native
dropdowns and the existing filter sheet are unchanged. No new screens or UI
layout changes are included.

The same three canonical flows were additionally forwarded to the real local
FastAPI app via `LIBRARY_TEST_API=http://127.0.0.1:3101`, with the existing
`tests.support._build_client()` authentication/store overrides. They passed
using one worker. A previous parallel attempt exhausted host memory (browser
spawn and API allocation failures); repeating serially required no code or
assertion changes. No live athlete data or external database was used.

Live PostgreSQL lock behavior, production latency, Safari and qualified review
of unresolved source assignments remain unverified. Discovery retains
`prescription_allowed: false`; canonical equipment does not authorize apparatus
substitution, infer quantity, establish a goal, grant contact permission or
change clinical eligibility.
