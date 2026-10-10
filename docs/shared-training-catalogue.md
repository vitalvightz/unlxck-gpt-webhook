# Shared training catalogue foundation

This is the foundation requested after #2816 and #2817. It adds no UI, search
endpoint, scheduling, database tables, prescription engine or planner wiring.
`fightcamp.training_catalogue.build_catalogue()` reads the same 14 sources as the
audit, retains every row and returns owned records with raw metadata, source and
row hashes, JSON pointers, field states, classification and search evidence.
Source hashes normalise CRLF to LF before SHA-256 so Git's Windows and Linux
checkouts describe the same revision; all other source bytes are preserved.
They are not raw on-disk byte digests. Row hashes separately use canonical JSON.
It deliberately avoids runtime loaders that infer tags or supply defaults.

## Identity

Every identity is `<source path>:<local ID>`. Existing `id` and `key` values are
preserved. `data/training_catalogue_ids.json` pins 952 UUIDs for the five sources
without IDs. The UUID is the identity; the canonical SHA-256 of a raw row is only
its current manifest binding. Names are included in the manifest for review.
Array positions and names are never identity. JSON layout, source reordering and
duplicate names cannot change an identity. Distinct variants are not merged.

When editing an unkeyed bank row, move its manifest binding to the new row hash
and retain the existing UUID. Update its manifest name if needed. Use
`content_hash(new_row)` to calculate the binding. New distinct entries need a
new UUID; remove bindings only when their source entry is intentionally removed.
Never regenerate the manifest wholesale. Strict loading rejects new/unbound rows,
orphan bindings and duplicate identities rather than guessing which row changed.
The report retains unbound rows with an explicit exclusion reason.

This leaves every source bank unchanged. Existing name-based media
`exercise_key` behaviour is untouched; catalogue references are separate from
media slugs and occurrence/block IDs. Non-workout content has no catalogue media
key. Rehab keeps its raw drill ID for its existing pathway/media consumers.

## Classification and selection boundary

| Source/content | Classification | Normal workout candidate |
| --- | --- | --- |
| Strength bank | Strength/power | Requires existing training validation |
| Three conditioning banks | Conditioning | Requires existing training validation |
| Footwork and coordination banks | Technical/coordination | Requires existing training validation |
| Musculoskeletal rehab groups | Rehabilitation | No; rehab pathway only |
| Surface injury groups | Care instruction | No |
| Tactical watch | Tactical/educational | No |
| Fight visualisation | Visualisation | No |

Classification follows the source, except surface care in rehab uses the existing
`SURFACE_TISSUE_TYPES` registry and the group type. Rehab retains group location,
injury type and phase progression independently of drill fields. Tactical tags
on a physical conditioning drill do not turn it into watch/educational content.
These are content classes, not new databases or proposed user-facing categories.

`normal_workout_candidate` describes catalogue scope, not permission to perform,
add or prescribe work. **Every record has `prescription_allowed: false`.** The
catalogue never evaluates an athlete or produces a prescription. Future write
paths must resolve the current source identity server-side and run existing
injury, sport/style, equipment, phase/countdown, familiarity and other planner
restrictions against the authoritative raw row and athlete context. Never trust
a client-supplied catalogue object, candidate flag or an old hash as permission.

Rehab must continue through `validate_clinical_bank`,
`filter_rehab_candidates` and the server injury-policy boundary: active pathway,
reviewed bank hash, current live stage, severity, laterality, episode evidence,
clinical clearance and reviewed dose remain their responsibility. A populated
rehab stage or reviewed movement metadata alone is not clearance. No rehab
progression, injury policy or prescribed output is changed here. Non-workout
content remains discoverable for appropriate future care/education experiences.

## Evidence and aliases

Each present field retains its exact raw value and source/hash/pointer provenance.
Absent, null, empty, unknown, ambiguous and known are distinct states. Explicit
`equipment: []` is known no equipment; missing/null/unknown equipment cannot
support that filter. Mixed known/unknown equipment remains ambiguous. Generic
strength is not made sport-specific by guessing. Sport evidence uses only an
explicit `sports` value or a recognised sport tag, and retains the evidence field.
`universal` stays explicit, without generating sport tags.

`search_evidence` indexes names, descriptions, cues, existing technical tags,
equipment, category, movement/focus and qualities with provenance. All other raw
fields, including restrictions, doses and cost classifications, remain available
without reinterpretation. A source assertion is evidence of what the bank says;
it does not certify efficacy, eligibility or clinical review.

`data/training_catalogue_aliases.json` contains a small inspectable language map:
aerobic → Stamina, anti-rotation → Core stability, explicit reaction qualities →
Reaction speed, scapular control → Shoulder control. Generic `reactive` rebound
mechanics, scapular retraction and alactic sprints are deliberately not broadened.
Stamina describes an explicit quality, not a sufficient standalone session dose.

Punching power is pinned only to Medicine Ball Hook Throw and Standing Cable
Punch Simulation: both explicitly have boxing category, rotational movement and
power method. Each override includes the reviewed row hash and rationale, so a
changed context loses that alias until reviewed. Other rotational work receives
no punching claim. Aliases carry evidence and never modify raw technical data.

Difficulty is unavailable: none of the 2,855 rows supplies it. Do not default to
Beginner. Future UI filters must use known, supported values and show unresolved
metadata honestly; neither empty search results nor incomplete metadata justify
dropping legitimate drills or inventing tags. This foundation does not claim
full consumer search readiness or verified prescriptions.

## Coverage and verification

`reports/training_catalogue_coverage.json` accounts for each source and each entry,
with field-state coverage, duplicate-name identities and per-entry exclusions:

- 2,855 total entries; zero missing stable IDs.
- 1,010 physical candidates requiring existing athlete-context validation.
- 1,499 rehab entries requiring pathway validation.
- 346 non-workout entries: 104 care, 183 tactical, 59 visualisation.
- 58 repeated-name groups, all with distinct catalogue identities.
- 1,845 entries outside normal workout selection, each with a reason.

Reproduce from any working directory:

```sh
python tools/report_training_catalogue.py --output reports/training_catalogue_coverage.json
python -m pytest tests/test_training_catalogue.py -q
python -m ruff check fightcamp/training_catalogue.py tools/report_training_catalogue.py tests/test_training_catalogue.py
python -m compileall -q fightcamp/training_catalogue.py tools/report_training_catalogue.py
```

Tests cover row reordering, reviewed identity rebinding after metadata/name edits,
missing/stale/duplicate bindings, repeated names and variants, raw restriction
preservation, alias context, equipment uncertainty and report reproducibility.
They compare bank hashes against the original audit's LF/CRLF equivalents, prove
complete catalogue/report equality across checkout line endings, and compare deterministic
plan text and Stage 2 prescribed payload before/after catalogue use. Existing
bank, phase, coordination, rehab selector and media tests provide regression
coverage. No frontend/deployment or live database behaviour is part of this PR.
The unrelated legacy bank-validator debt documented in #2816 is not repaired.
Full-suite follow-up also refreshes the generated API types for #2817's existing
contracts and updates three legacy static assertions to the current Plan
dashboard component. Neither change alters API or frontend behaviour.
