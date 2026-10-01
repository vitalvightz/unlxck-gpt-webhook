# PR #2677 review cleanup

This pass fixes the PostgreSQL CI dependency setup and addresses 18 of the 20 P2 findings in code. Two suggestions require a separate correction design; their conservative current behavior is retained below. This document records dispositions, not GitHub thread resolution or approval to merge.

## P2 dispositions

| Finding | Change / disposition |
| --- | --- |
| Unknown policy region or injury type | Validate against the canonical registries. |
| Blank instructions or stop rules | Reject whitespace-only guidance. |
| Consumed activation iterator | Materialize activated stages once before selecting candidates. |
| UTC date rejects local next-day answers | Use recorded training day, falling back to the athlete's timezone and training-day rollover. |
| Missing deploy-gate exposure columns | Require every exposure column used by persistence/history. |
| Existing rehab silently disappears | Replace only the exact due policy/injury/episode block; retain or explicitly hold other blocks. Held work is excluded from standalone offers. |
| Clearance retry duplicates its event | Retain the idempotency key until refresh succeeds. |
| Frozen drill identity mismatch | Reject conflicting snapshot and block drill identifiers before recording an exposure. |
| Resolved injuries prescribed again | Preserve episode status and report timestamp through generation. |
| Shared drill name hides a deferred episode | Track each episode's allocation independently of drill-name deduplication. |
| Completion without performed-work choice | Require a choice in both the UI and API. |
| SQL fixture omits response-group identity | Apply the real preceding migration and provide valid UUIDs in both SQL harnesses. |
| Pre-activation started work cannot log a stop | Permit a verified server-held stop without manufacturing a new frozen prescription. |
| Reopening hides old unanswered feedback | Keep owned historical exposures discoverable; accept answers only against that exposure's exact episode. |
| Legacy frozen block lacks drill metadata | Resolve its saved drill identifier against the bank when metadata is absent. |
| Duplicate overwritten exposure RPC | Remove the obsolete schema definition; preserve the final implementation. |
| Untimestamped setback cannot be ordered against improvement | Retain the loading hold. Discarding an undated negative response would convert uncertainty into recovery evidence. Baseline CALM remains available; repairing source timestamps requires a separate data correction process. |
| Delayed answer cannot be edited | Preserve immutable, once-per-exposure answers. Overwriting a setback or creating competing answers changes safety evidence. A future correction flow must append a traceable correction with explicit ordering semantics. |
| Skip fails during non-critical history outages | Allow skipping without training/rehab credit when Today reads fail; training still fails closed. |
| Client stopped enum bypasses holds | Require an existing started session for the same plan, a reason, and a server-confirmed severe/safety hold. Do not complete sibling sessions through this exception. |

## Verification and limits

The next review identified three further P2s. General audit and explicit-report triggers now share an injury/episode/transaction/statement event identity and merge the explicit marker within that statement, so status changes (including combined severity edits) create one event. Separate updates still create separate events, including unchanged-status reports. Inserts create baseline audit history with `explicit_report=false`; only an UPDATE targeting the report column can create explicit recovery evidence. Text RIR uses the planner's existing numeric parser and the harder, lower end of a range before conversion to RPE. Native PostgreSQL and scheduling regressions cover these cases.

A subsequent review found three additional P2s: current-episode routines now replace their existing blocks in place before new episodes compete for the remaining allocation; an idempotent completion retry reuses the saved performed-work answer; and the chest acceptance fixture has its own response-group identity. Strength and sparring allocation regressions, completed-session retries and the migration harness verify these fixes.

The meaningful P3 cleanup aligns database side attribution with the Python contract: blank/whitespace sides normalize to unknown, and region-wide baseline work still requires the exact accepted pilot episode and prescription. Legacy unknown-side work remains ineligible. Generated plans retain the resolver's retired-policy guidance instead of replacing it with generic unsupported copy. The five pilot drills now use the existing `unrestricted` pain-ceiling sentinel, with policy version 3 and refreshed hashes; no numerical pain ceiling or other drill metadata was introduced. Accepted historical snapshots remain unchanged. Validation: 169 focused tests (including seven native PostgreSQL cases), 12 migration acceptance checks, three data validators, Ruff and imports pass.

Focused backend, Today, selector, exposure and schema regressions cover these paths. Native PostgreSQL tests execute the real migration, including two-connection lock races, explicit report timestamps and owned historical feedback after episode reopening. The PGlite harness also applies the existing response-group migration before its 12 acceptance checks.

Frontend tests exercise the performed-work choice and refresh-failure retry. Production build, typecheck, targeted lint, Python imports/Ruff and rehab bank/policy/metadata validators are checked. The full suite is intentionally not rerun at the user's request. Earlier rollout-document suite counts describe prior validation, not this cleanup pass.

Remaining P3 review items and fresh CI/review status still need assessment. No remote database migration, deployment or merge is performed by this pass.
