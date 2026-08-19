# Rehab bank schema and migration status

`data/rehab_bank.json` is now a machine-readable rehabilitation data source with
a formal contract and a blocking validator. This note records what the contract
is, what was populated, and — the point of the document — exactly which fields
are still incomplete so PR3 knows what it owns.

## Where the contract lives

| Concern | Owner |
| --- | --- |
| Finite value sets, sentinels, structural helpers | `fightcamp/rehab_schema.py` |
| Strict validation, CI exit code | `tools/validate_rehab_bank.py` |
| Deterministic (re)generation of derived fields | `tools/migrate_rehab_bank_schema.py` |
| Grandfathered duplicate drills | `data/rehab_bank_duplicate_debt.json` |
| Recognised injury types | `fightcamp/injury_taxonomy.py` via `injury_registry.REHAB_SAFE_TYPES` |
| Recognised locations | injury parser vocabulary + `injury_location_registry.LOCATION_REGISTRY` |

No injury or location list is redefined by the schema module or the validator.

## Shape

Location and injury-type ownership stays on the group record, as it already did.
Drills never repeat them.

```json
{
  "location": "ankle",
  "type": "sprain",
  "phase_progression": "GPP → SPP",
  "drills": [
    {
      "id": "ankle_sprain_single_leg_balance_on_foam_pad",
      "name": "Single-Leg Balance on Foam Pad",
      "notes": "GPP: Rebuild proprioception → SPP: Progress to dynamic balance under fatigue",
      "rehab_stage": null,
      "function": "control",
      "equipment": null,
      "dose": null,
      "impact": null,
      "load": null,
      "velocity": null,
      "pain_ceiling": null,
      "allowed_severities": null,
      "progress_when": null,
      "regress_when": null,
      "stop_when": null
    }
  ]
}
```

### Value sets

| Field | Values |
| --- | --- |
| `rehab_stage` | `calm`, `restore`, `load`, `dynamic`, `return` |
| `function` | `activation`, `control`, `isometric_analgesia`, `mobility`, `tendon_loading`, `recovery_downregulation` |
| `impact` | `none`, `low`, `moderate`, `high` |
| `load` | `minimal`, `low`, `moderate`, `high` |
| `velocity` | `low`, `moderate`, `high` |
| `allowed_severities` | non-empty subset of `low`, `moderate`, `high` |
| `pain_ceiling` | `0`–`10`, or `"unrestricted"` |
| `dose` | `{"sets": …, "reps": …, "duration_seconds": …}`, each slot a positive number or `null` |
| `equipment` | list of tokens; `[]` means "needs nothing" |
| `progress_when` / `regress_when` / `stop_when` | list of strings; `[]` means "no criteria apply" |

### Unknown vs. deliberately unrestricted

`null` always means **not migrated yet**. It is the deterministic incompleteness
marker, and `rehab_schema.unmigrated_fields(drill)` enumerates it for any drill.

Every deliberately-open value has its own spelling, so an unmigrated field can
never be mistaken for an intentional one:

| Intent | Spelling |
| --- | --- |
| Not migrated yet | `null` |
| No pain ceiling applies | `"unrestricted"` |
| No equipment needed | `[]` |
| No progress/regress/stop criteria | `[]` |
| No impact | `"none"` |
| Dose structure declared, values unprescribed | `{"sets": null, "reps": null, "duration_seconds": null}` |

## Surface (skin) injuries

`cut`, `laceration`, `abrasion`, `graze` and `blister` groups are wound care, not
musculoskeletal rehabilitation. Their drills carry `id`, `name` and `notes` only.
Declaring any loading field on one is a **validation error**, not an omission —
the schema refuses to dress a skin wound up as loading rehab. The existing
surface pathway (`SURFACE_WOUND_CARE_NOTE`, the minor train-through note, and
the danger gates upstream) is untouched.

## What PR1 populated

769 groups; 1434 musculoskeletal drills; 104 wound-care drills. No group record
was added, removed or reordered.

| Field | Status |
| --- | --- |
| `id` | **Complete.** Deterministic `location_type_name` slug, numeric suffix on collision. |
| `function` | **Partial — 979 of 1434 (68%).** Derived from the existing keyword classifier, and only where a keyword actually matched. |
| everything else | **Not migrated.** `null` on every drill. |

### Why `function` is only 69% migrated

The runtime classifier `classify_drill_function()` returns `"control"` when no
keyword matches. That default is a *rendering* fallback, not evidence about the
drill. Baking it into the data would make 455 unclassified drills indistinguishable
from 154 genuinely control-classed ones.

So migration used `match_drill_function()`, which returns `None` on a non-match,
and wrote `null` for those 455 drills. The validator reports them as
`unmigrated_function` (informational) — never as `"control"`, and never by
consulting the keyword classifier itself.

### Fields PR3 owns

For all 1434 musculoskeletal drills:

- `rehab_stage`
- `impact`, `load`, `velocity`
- `pain_ceiling`
- `allowed_severities`
- `dose`
- `equipment`
- `progress_when`, `regress_when`, `stop_when`

Plus `function` for the 455 drills the keyword classifier could not place, and
the 30 duplicate drills declared in the ledger below.

Nothing above was guessed. Every one of these is clinical content, and PR1
deliberately left it empty rather than inventing thresholds, doses or stop
criteria.

Progress is measurable at any time:

```bash
python tools/validate_rehab_bank.py                     # reports pending counts, exits 0
python tools/validate_rehab_bank.py --strict-migration  # exits 1 while anything is pending
```

`--strict-migration` is the switch PR3 flips on in CI once the content migration
completes and the duplicate ledger is empty.

## What still drives selection

Nothing in this schema. Rehab selection, severity filtering, the volume ceiling,
the keyword safety filter and the red-flag gates all behave exactly as before.
Every one of 27,027 generated rehab blocks is byte-identical to the pre-PR bank.
`rehab_stage` is inert. `impact`/`load`/`velocity` are inert. The rendered
function label is still derived at runtime from the phase-specific note, because
a single stored `function` cannot reproduce a per-phase classification — a drill
whose GPP note reads as mobility and whose SPP note reads as tendon loading gets
one stored value and two rendered ones. `rehab_schema.resolve_drill_function()`
is the forward path for when PR3 makes the stored value authoritative.

`tests/test_rehab_metadata_contract.py` holds this line: it stamps every
musculoskeletal drill with metadata that would forbid it (stage `return`, high
impact/load/velocity, a severity gate excluding the athlete, a zero pain ceiling)
and asserts the generated rehab block is byte-identical.

## Duplicate drills: declared debt, not a silent pass

The bank contains 15 group records that duplicate an earlier record exactly.
They are why a handful of rehab blocks list the same drill twice in a row:

```
• Heel Walks – …
• Heel Walks – …
```

Collapsing them changes generated output — an exhaustive sweep of 27,027 blocks
(every location/type × phase × severity × day type, plus the string-parsed,
three-phase and `_rehab_drills_for_phase` paths) found 21 blocks where the
repeated bullet becomes a different drill. That is a content change, so PR1 does
not make it. The duplicates stay, byte-for-byte, and PR1 generates output
identical to the pre-PR bank across all 27,027 blocks.

Instead the 30 affected drill combinations are **declared** in
`data/rehab_bank_duplicate_debt.json`:

```json
{
  "location": "shin",
  "type": "pain",
  "rehab_stage": null,
  "name": "Heel Walks",
  "grandfathered_copies": 1
}
```

The validator spends this ledger before reporting, which gives three behaviours:

| Situation | Result |
| --- | --- |
| Duplicate declared in the ledger | `grandfathered_duplicate` — reported on **every** run as debt |
| Duplicate not in the ledger | `duplicate_drill_combination` — **error**, CI fails |
| More copies than the ledger declares | `duplicate_drill_combination` for the excess — **error** |
| Ledger row whose duplicate is gone | `resolved_duplicate_debt` — informational; drop the row |

So a newly introduced duplicate still fails, while the pre-existing ones are
visible rather than silently tolerated. `--strict-migration` counts the declared
debt as a failure, so PR3 can gate on the ledger reaching zero.

There is no command that regenerates the ledger. Adding a row is a deliberate
hand edit that shows up in review; the file should only ever shrink.

## CI

`.github/workflows/validate_banks.yml` runs three steps:

1. `python tools/validate_banks.py` — the existing cross-bank audit, which now
   reports rehab contract findings under the `rehab bank schema` group.
2. `python tools/validate_rehab_bank.py` — **blocking**; exits non-zero on any
   schema error.
3. `python tools/migrate_rehab_bank_schema.py --check` — **blocking**; fails if
   the derived fields (ids, keyword-matched functions) drifted from what the
   deterministic migration produces. The migration adds fields only; it never
   drops, merges or reorders a group record.
