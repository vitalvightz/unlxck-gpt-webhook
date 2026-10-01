# Simple injury rehab scheduling

Chest/pec strains and ankle sprains have active, populated policies. There is no mandatory clinician approval, upload, admin queue or additional daily questionnaire. Rehab owns its cadence and appears in Today, inside suitable training or as a separate session on rest days and when training is held.

## Pilot content and validation

- `data/rehab_clinical_policies.json` uses schema version 2: draft/active/retired status, version, source references and a content hash. Active policies require complete mechanical metadata and exact bank hashes for every routine. Historical `policy_review_hash` fields retain their wire name; they now mean content integrity, not clinician approval.
- Five routines were added to `data/rehab_bank.json`: chest recovery support and comfortable movement; ankle gentle movement, supported firm-ground balance and supported heel lowering. Existing drill metadata and other injury families retain their behavior.
- Sources are [NHS sprains and strains](https://www.nhs.uk/conditions/sprains-and-strains/), [East Cheshire ankle rehabilitation](https://services.eastcheshire.nhs.uk/physiotherapy-service/self-help/ankle-and-foot-pain-physiotherapy-self-help) and [Whittington ankle sprain guidance](https://www.whittington.nhs.uk/mini-apps/leaflet/Default.asp?id=53&print=1). Chest content adapts general strain guidance; it is not a pectoral repair protocol. No resisted flies are automatically introduced.
- Instructions remain self-paced where sources supply no starting numerical dose. East Cheshire's heel lowering has an alternate-day gap and an upper limit of two sets, without an invented repetition count. Other baseline routines have a one-day allocation gap; this is the product's scheduling cap, not a claim that every injury needs daily exercise. Completed quantity remains unknown for self-paced work, even after “Done as shown.”
- `tools/seed_rehab_pilot.py` reproduces only these five routines and policy hashes. After deliberate content changes, run it, regenerate the metadata ledger, and validate all rehab data. It does not approve any of the wider bank's review proposals.

## Scheduling and feedback

`api/contracts/rehab_schedule.py` uses episode identity, recent accepted prescriptions, rehab exposures, injury-specific responses, readiness and known training demands. It never counts ordinary training as rehab. Each episode receives at most one daily routine; total allocations remain one on sparring sessions and two otherwise. Due lighter alternatives can replace a recovering or held loading routine within the same allocation.

Started work reserves the current day's allocation. Done, changed and symptom-stopped work spaces subsequent performance; skipped work earns no credit. Missed work never accumulates. A previously accepted longer gap survives policy and plan changes. Frozen prescriptions remain unchanged; current safety checks can hold them.

Worsening and symptom stopping hold loading work. A later explicit injury-specific improvement can restore baseline work. Its timestamp comes from a database-marked report event for the same athlete, injury and episode, never the generic injury `updated_at`. Repeated reports are captured even when the status value is unchanged; unrelated severity/description edits preserve the hold. Legacy events without explicit-report provenance cannot release it. Missing or uncertain responses never advance recovery. Automatic LOAD/DYNAMIC/RETURN transitions are disabled. Camp phase, including TAPER, cannot advance healing or remove otherwise eligible chest guidance. Truncated older history prevents unsupported progression without permanently removing baseline guidance.

Training-demand checks reuse the planner's canonical intensity rules for structured percentage/RPE prescriptions and intensity tags, with RIR converted to RPE. Known hard same-region session demand remains authoritative when a block has low or unknown load; absolute kilograms alone do not imply a relative demand level.

Today exposes `due`, `recovery_day`, `already_completed`, `held`, `deferred` or `unsupported`, with a short reason and a next due day when known. Existing completion, during-rehab and next-day response controls are reused. “My clinician cleared me” records optional athlete-reported information; it changes neither routine eligibility nor scheduling.

Region-wide frozen pilot guidance can retain an injury response with unknown laterality. It preserves “unknown,” requires exact episode and accepted prescription attribution, and cannot become advanced capacity evidence. Unattributed legacy work keeps its existing stricter checks.

## Persistence and rollout

No scheduler tables or jobs were added. Scheduling reuses session completions, frozen prescriptions and rehab exposures. The previously pending `20260930173118_injury_episode_prescription_history.sql` migration also provides append-only episode observations, delayed responses, owner-only reads and backend-only mutation RPCs.

The migration's existing start trigger now serializes acceptance per athlete and rechecks injury, readiness and feedback freshness. It enforces daily allocation and routine spacing across plans and session types, preserves accepted snapshots and prevents erasing terminal rehab credit. Optional clearance does not change the scheduling evidence revision. Historical observations survive reopening an injury.

Before deployment:

1. Apply the pending migration to Supabase staging; verify real multi-connection start/feedback contention and existing production RLS. No remote migration or deployment has been performed by this change.
2. Run backend/API/schema and frontend regressions, Python import/lint checks, frontend typecheck/lint/build and the three rehab data validators.
3. Deploy the validated API and UI together with the migration. The checked-in pilot policies are active after software checks; no clinician sign-off step is required.

For reproducible isolated SQL acceptance checks, install `@electric-sql/pglite@0.5.8` into a temporary directory outside the repository, then run:

```text
node tools/test_rehab_migration.mjs <temporary-directory>
```

This executes the real pending SQL against PostgreSQL and exercises start retries, duplicate allocations across plans, immutable snapshots, cadence, skipped work, owner-only reads, optional clearance, delayed response idempotency, episode reopening and attributed unknown-side guidance. PGlite uses one connection; these checks do not claim to simulate multi-connection contention. No frontend dependency was added.

Real lock contention is tested separately in `tests/test_rehab_lock_concurrency.py` using two PostgreSQL connections and the actual migration. Both recording RPCs take the athlete advisory lock before `FOR SHARE`. The test waits for the RPC's ungranted advisory lock in `pg_locks`, then updates/reopens the injury in the other transaction. Both RPCs complete without deadlock; reopened episodes reject stale evidence. Restoring the old lock order reproduces deadlocks and fails all four cases.

Backend Checks runs these tests against its disposable PostgreSQL 17.11 service. To repeat locally, install `requirements-dev.txt`, start a disposable localhost PostgreSQL cluster and run:

```text
REHAB_TEST_DATABASE_URL=postgresql://postgres:<test-password>@127.0.0.1:5432/postgres python -m pytest tests/test_rehab_lock_concurrency.py -q
```

The configured role needs CREATE DATABASE/ROLE privileges. The fixture creates and drops only its uniquely named test database; it rejects remote hosts. Without the explicit test URL, normal unit runs skip these five integration cases. Four exercise lock contention; the fifth executes the actual report/audit triggers and proves that unrelated edits retain a loading hold while a repeated explicit improving report restores baseline rehab. The CI job supplies the URL and treats missing drivers or setup failures as failures.

## Verification

Quick repeat from the repository root:

```text
python -m pytest tests/test_injury_policy_journey.py tests/test_rehab_schedule.py tests/test_injury_policy_migration.py -q
python tools/validate_rehab_bank.py
python tools/validate_rehab_metadata_review.py
python tools/validate_rehab_clinical.py
```

From `web`, run `npm run test:unit`, `npm run typecheck`, `npm run lint` and `npm run build`.

On the PR branch based on current Main, the focused backend/API/schema/rehab suite passes 356 tests. A separate Today caching, readiness and pilot journey run passes 64 tests, including the new whole-day prescription checks. All 1,561 frontend unit tests pass. Typecheck, production build, Python imports/Ruff and generated API contract checks pass. Frontend lint has no errors and retains 52 existing warnings. The build used a temporary non-secret API URL for its required rewrite configuration; no environment file was changed.

Bank, policy and metadata validators and the bank migration check pass. The pending migration executes successfully in the isolated PostgreSQL database across 12 acceptance checks. Staging concurrency and deployment remain rollout work.

The broader backend run completed with 2,373 passing tests and 14 initial failures. Those failures were resolved through the text-only pilot path, legacy metadata fixture scope, reuse of Main's completion cache, keeping skip available during injury-read outages, and installation of the already-required pywebpush test dependency. Every affected test group then passed in focused reruns; the entire broader suite was not repeated. The unrelated generation-response failures from the original dirty checkout are absent on this isolated branch, which excludes that unrelated local work.
