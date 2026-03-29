# Fight-camp plan-quality regression diagnosis (PR 556–559 window to HEAD)

## Scope and method
- Reviewed commit history and diffs in `fightcamp/` for planning/generation-only changes (no UI-only focus).
- Focused on:
  - weekly role map and short-camp compression
  - Stage 2 planning brief/handoff/finalizer rules
  - limiter mapping and hard sparring-day logic
  - validator/repair rules that can make plans cleaner but less specific

## Commit-level classification around the suspected window

### Likely generation/planning logic commits
1. `322f7eb` — **Compress short-camp planning priorities**
   - Adds `compressed_priorities` model and feeds it into limiter derivation and global priorities.
   - Introduces short-camp selective targeting logic (primary/maintenance/embedded/deferred).

2. `4b66859` — **Enforce short-camp priorities in weekly roles**
   - Adds `_apply_short_camp_role_compression()` and removes any session role that does not map to compressed priorities.
   - This is hard suppression in the weekly-role execution layer.

3. `f78dcd5` — **Align short-camp phase framing with progression**
   - Adds visible label/objective mapping from week progression into phase strategy.
   - Primarily framing consistency; low risk to core quality by itself.

### Mostly cleanup / metadata / low-impact commits in that window
1. `cd85809` — **Trim short-camp payload metadata**
   - Removes reasons/extra metadata fields from compressed-priority objects.
   - Mostly payload simplification; little direct effect on generated plan decisions.

### Post-window logic commits that can affect plan quality
1. `162bf6a` — **Slim stage2 handoff prompt context**
   - Collapses explicit multi-section context into a single `PLANNING BRIEF` block and minifies JSON.
   - Likely reduces model salience of certain constraints/archetype details.

2. `878a63a` — **Protect sparring freshness from glycolytic collisions**
   - Auto-downgrades glycolytic roles to aerobic when adjacent to hard sparring under high fatigue/cut pressure.
   - Safety-positive but can blur hard sparring intent fidelity in constrained weeks if over-triggered.

3. `abb091b` — **Tighten Stage 2 voice rules and repair triggers**
   - Adds stronger anti-optionality / anti-hedging validator+repair behavior.
   - Improves cleanliness but can over-collapse structure and reduce transparent limiter honesty.

4. `6649470` — **Enforce taper spar downgrades in Stage 2**
   - Additional sparring conversion pressure in taper contexts.
   - Generally safety-positive, but can compound with collision downgrades.

## Symptom mapping to likely causes
1. **Cleaner plans but weaker decision coverage**
   - Most consistent with `4b66859` hard session suppression + `abb091b` option-collapsing/voice tightening.

2. **Hard sparring day fidelity misses**
   - Most consistent with collision/taper downgrade logic from `878a63a` + `6649470` when constraints stack.

3. **Less honest limiter language**
   - Compression-to-label flow can over-normalize limiter framing in short camps (`322f7eb` + `4b66859` downstream effects).
   - Handoff salience reduction (`162bf6a`) likely contributes when nuanced limiter context gets buried.

4. **More generic / less archetype-specific output**
   - Most consistent with context slimming/minified handoff (`162bf6a`) and strong anti-template style filters (`abb091b`) that can flatten voice into safe generic directives.

5. **“Safe/clean” but less athlete-matched plans**
   - Combination effect: role suppression (`4b66859`) + high strictness rewrite rules (`abb091b`) + reduced explicit context salience (`162bf6a`).

## Peak logic point (most likely)
- **Likely peak baseline for quality is `f78dcd5` with caution on `4b66859`.**
- Rationale:
  - Keeps short-camp framing/progression alignment.
  - Avoids later context-slimming and heavy rewrite strictness changes.
  - However, hard suppression behavior from `4b66859` appears to be a quality-risk element even near this window.

## Recommended action

### Preferred: minimal corrective patch on current base (not full rollback)
Patch only the highest-regression block while keeping later safety/ops gains.

1. **Soften `4b66859` role compression from hard suppression to guided demotion**
   - In `_apply_short_camp_role_compression()`:
     - keep unmatched roles when they are structural for weekly rhythm (especially declared hard sparring/technical day alignment),
     - mark them `embedded_support`/`maintenance` with explicit rationale,
     - only suppress clearly redundant duplicates.
   - This directly targets decision coverage loss without removing short-camp selectivity.

2. **Partially restore Stage 2 context salience from pre-`162bf6a` behavior**
   - Keep compact payload transport if needed, but restore explicit labeled sections in handoff text (athlete snapshot/restrictions/phase briefs/candidate pools/rewrite guidance) so constraints remain model-salient.

3. **Loosen blocking behavior from `abb091b` only in non-risk contexts**
   - Keep anti-filler quality rules,
   - but do not force option collapse when no high-risk context exists and both options are materially meaningful.

### If rollback is required instead of patching
- **Best rollback target: revert `4b66859` first** (or partial revert of `_apply_short_camp_role_compression` only).
- This is the most direct single-point rollback for “clean but dumber” short-camp behavior.

## What to keep from later commits even if rolling back logic blocks
- Keep loaded-anchor safeguards and injury-limited honesty rules from `8bda8ab`.
- Keep sparring safety protections (`878a63a`, `6649470`) but gate them more narrowly rather than removing them.
- Keep anti-filler language improvements from `abb091b` while reducing over-blocking on structurally useful options.
- Keep non-generation UI/refactor cleanup as-is.

## Immediate implementation order
1. Patch `_apply_short_camp_role_compression()` behavior (highest impact).
2. Restore handoff section salience (second highest impact on specificity).
3. Tune validator blocking thresholds for option collapse in low-risk contexts.
4. Re-run constrained short-camp + hard-sparring snapshot tests before considering broader rollback.

