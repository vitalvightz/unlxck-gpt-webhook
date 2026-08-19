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

754 groups; 1404 musculoskeletal drills; 104 wound-care drills.

| Field | Status |
| --- | --- |
| `id` | **Complete.** Deterministic `location_type_name` slug, numeric suffix on collision. |
| `function` | **Partial — 963 of 1404 (69%).** Derived from the existing keyword classifier, and only where a keyword actually matched. |
| everything else | **Not migrated.** `null` on every drill. |

### Why `function` is only 69% migrated

The runtime classifier `classify_drill_function()` returns `"control"` when no
keyword matches. That default is a *rendering* fallback, not evidence about the
drill. Baking it into the data would make 441 unclassified drills indistinguishable
from 153 genuinely control-classed ones.

So migration used `match_drill_function()`, which returns `None` on a non-match,
and wrote `null` for those 441 drills. The validator reports them as
`unmigrated_function` (informational) — never as `"control"`, and never by
consulting the keyword classifier itself.

### Fields PR3 owns

For all 1404 musculoskeletal drills:

- `rehab_stage`
- `impact`, `load`, `velocity`
- `pain_ceiling`
- `allowed_severities`
- `dose`
- `equipment`
- `progress_when`, `regress_when`, `stop_when`

Plus `function` for the 441 drills the keyword classifier could not place.

Nothing above was guessed. Every one of these is clinical content, and PR1
deliberately left it empty rather than inventing thresholds, doses or stop
criteria.

Progress is measurable at any time:

```bash
python tools/validate_rehab_bank.py                     # reports pending counts, exits 0
python tools/validate_rehab_bank.py --strict-migration  # exits 1 while anything is pending
```

`--strict-migration` is the switch PR3 flips on in CI once the content migration
completes.

## What still drives selection

Nothing in this schema. Rehab selection, severity filtering, the volume ceiling,
the keyword safety filter and the red-flag gates all behave exactly as before.
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

## The one data-level change

Migration dropped 15 group records that were byte-identical duplicates of an
earlier record (769 → 754 groups). They were the reason a handful of rehab blocks
listed the same drill twice in a row. Across an exhaustive sweep of 27,027
generated blocks (every location/type × phase × severity × day type, plus the
string-parsed and three-phase paths), 21 changed, all in the same way:

```
before:  • Heel Walks …
         • Heel Walks …
after:   • Heel Walks …
         • Anterior Compartment Foam Rolling …
```

No block lost a drill, and no other output changed.

## CI

`.github/workflows/validate_banks.yml` runs three steps:

1. `python tools/validate_banks.py` — the existing cross-bank audit, which now
   reports rehab contract findings under the `rehab bank schema` group.
2. `python tools/validate_rehab_bank.py` — **blocking**; exits non-zero on any
   schema error.
3. `python tools/migrate_rehab_bank_schema.py --check` — **blocking**; fails if
   the derived fields (ids, keyword-matched functions) drifted from what the
   deterministic migration produces.
