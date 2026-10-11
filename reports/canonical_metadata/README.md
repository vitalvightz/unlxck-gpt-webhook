# Canonical metadata and filter evidence

Six high-confidence PR #2822 decisions are projected for discovery. Original values, requirements, source pointers, row hashes, catalogue IDs and audit decisions remain available in drill previews. No bank, planner, dose, injury, rehabilitation or Goal rule changed.

| Reviewed decision | Raw values | Canonical filter | Source rows | Training matches before (distinct union) → after |
| --- | --- | --- | ---: | ---: |
| `MI-f400cf810ade` | `battle_rope`, `battle_ropes` | Battle ropes (`battle_ropes`) | 9 | 9 → 7 |
| `MI-45e540176268` | `kettlebell`, `kettlebells` | Kettlebell (`kettlebell`) | 26 | 24 → 24 |
| `MI-35204cfd5cf6` | `weight_vest`, `weighted_vest` | Weight vest (`weight_vest`) | 6 | 6 → 6 |
| `MI-c8c1f7bc7749` | `rower`, `rowing_machine` | Rower (`rower`) | 8 | 8 → 8 |
| `MI-1d52007d31ef` | `double-end_bag`, `double_end_bag` | Double-end bag (`double_end_bag`) | 4 | 4 → 4 |
| `MI-a793c6f54e62` | `adductor`, `adductors` | Inner thighs (adductors) (`adductors`) | 7 | 0 → 7 |

Battle-rope source rows include two climbing drills whose equipment notes explicitly require a climbing rope. Those pinned associations remain raw evidence but cannot qualify battle-rope filters or searches. This is a discovery exclusion, not a source correction or programming change.

The anatomical projection adds the reviewed hip-adductor focus to seven Training rows with existing adductor/adductors tags. It does not alias clinical region IDs or add goals. Kettlebell quantity remains in the original name/instructions/notes; plural spelling alone does not establish a pair requirement.

Counts use distinct catalogue IDs. Filters retain AND semantics, independently scoped facet counts and legacy identifiers. Unknown equipment never becomes No Equipment. Compound strings remain whole unresolved tokens with their original requirements and grouping.

## Evidence and verification

[before-after.json](before-after.json) contains every projected token, raw/canonical/display distinction, full before/after filter values and matching identities, unchanged source hashes, remaining register issues, 30 identical reviewed query result orders and three identical fixed-seed plan/prescription hashes.

Goal coverage remains **222/1,010**. All 2,855 catalogue identities and media keys, source bank hashes and PR 1 report hashes match the captured Main baseline. The existing shared pads intake contract is identical; catalogue aliases never alter athlete capability normalization.

The smallest architecture is two small field-scoped reviewed mapping arrays and pure adapters used only by the library. Equipment aliases extend the existing shared contract additively; the anatomical tag mapping is Training-only. Source requirements and athlete capabilities remain separate. No parent categories, clinical registries or compound AND/OR rules are inferred.

Consumer changes: `training_library._prepare` projects facets; `search` resolves legacy facet IDs and conservative apparatus query aliases; `preview` exposes provenance; `LibraryCache` includes mapping contracts in its revision. `training_context`, strength, conditioning and clinical consumers retain their original source hashes and exact behavior. `intake-options.ts` continues reading only `pads`. The native dropdown UI already consumes API labels and distinct counts.

PR 1 is historical evidence: its reports and original baseline are unchanged. `--historical --check` replays original code receipts offline using four retained pre-projection sources, individually verified against frozen PR 1 hashes. The ordinary PR 1 command remains strict against production drift.

The initial uncontrolled Stage 2 hashes exposed existing cross-process ordering variance in selected `movement_patterns` (high-torque rotation / change-of-direction). The report retains those original hashes and records the exact original-code variation with Python hash seeds 0 and 1. Before/after checks pin both planner clocks and hash seed 0, then compare complete payloads including array order; no dose, score, selection or array is normalized to make the check pass.

```powershell
python tools/audit_canonical_metadata.py
python tools/audit_canonical_metadata.py --check
python tools/audit_metadata_integrity.py --historical --check
python -m pytest tests/test_canonical_metadata.py tests/test_metadata_integrity_audit.py -q
```

See [verification.md](verification.md) for executed checks and limitations, and [roadmap.md](roadmap.md) for remaining remediation gates.
