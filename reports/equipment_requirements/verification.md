# Executed verification and limits

Base: Main `b074e8a1`, including #2822/#2823. The compact pre-change digests
were captured before implementation; original audit reports were not refreshed.

| Check | Result |
| --- | --- |
| New equipment requirements, API/provenance and setup semantics | 50 passed |
| Existing canonical metadata, catalogue/library, schema and historical audit | 146 passed |
| Focused strength metadata, conditioning render, injury guard, rehab selector/stages and saved pads compatibility | 199 existing regression cases passed |
| Frontend formatting, library request/pagination/retry and intake persistence | 12 passed |
| TypeScript and production Next build | Passed with existing CI placeholder public configuration |
| Library browser flows | 10 existing flows passed; 3 new setup flows passed after fixture routing correction |
| Mobile/desktop browser setup checks | 320/390/1280 px; axe, overflow, modal close and focus restoration passed; 320 px screenshot inspected |
| Ruff over api/fightcamp/tests/tools; targeted frontend ESLint; Python import/compile; diff whitespace | Passed |
| Original banks, manifest, catalogue/media identities and prescription boundaries | All 2,855 entries retained; every original hash unchanged |
| Fighter-search and non-equipment facets | All 30 full ordered query/control results unchanged; all non-equipment facet sets unchanged |
| Verified Goal coverage | Unchanged: 222/1,010 Training records |
| Fixed-seed generation | Existing harness compared complete plan text and Stage 2 outputs for three original payloads; strict equality, including doses, selections, scores and array order |

The new API test initially requested a page size of 100, beyond the existing
endpoint maximum of 50. It now requests 24 and asserts the complete filtered
total of 263; the backend test separately checks the full matching identity set.
The initial new browser route mocked only `/library/entry`, leaving search on
the older fixture. The route was corrected to include `/library` queries and
all three new flows passed without weakening assertions. No production limit,
filter behavior or runtime authority was changed to fix these test errors.

Full backend/frontend CI is running on the PR. Local verification does not
claim a full-suite CI result. PostgreSQL concurrency and runtime-schema checks
run in CI; no local database integration or live deployment verification was
performed. No merge was performed.

## Artifact size and frozen evidence

- Reviewed mapping: 25 compact records, approximately 11 KB / 27 lines.
- New pre-change baseline: approximately 2.8 KB / 118 lines of digests/counts.
- Generated human summary: approximately 6 KB / 96 lines.
- One additive original UI source receipt: 13,360 bytes, verified against the
  existing frozen PR #2822 hash, to preserve offline historical replay after
  updating the preview. All four previous receipts are byte-for-byte unchanged.
- No per-exercise inventory, full API fixture or full training plan was added.
  Browser screenshots and complete comparison outputs remain untracked.

## Remaining correctness boundary

Plan equality demonstrates preservation of existing behavior, not correctness
of its original equipment interpretation. The generator still reads original
bank equipment. The five source-association problems corrected for discovery
remain an explicit generator cleanup gap. See [roadmap.md](roadmap.md) for the
source rebinding, exact eligibility differences and safety verification required
before correcting that gap. Eleven equipment relationships remain UNKNOWN.
