# Remaining generator equipment gap

This PR corrects effective Find a Drill metadata through source-bound reviews.
It does **not** correct the raw banks used by the generator. Strength and
conditioning still interpret original equipment values through their existing
normalizers and subset checks. Accurate discovery metadata therefore does not
prove accurate prescription equipment eligibility. This remains an open cleanup
gap, including five sufficiently evidenced source-association problems.

## Next controlled source/programming stage

| Reviewed exercise | Current source equipment | Evidence-backed setup to test |
| --- | --- | --- |
| Rope Climb + Short Sprint | battle_ropes + climbing_rope | Climbing rope; battle ropes cannot perform the climb |
| Rope Climb Sprints | battle_rope + climbing_rope | Climbing rope; towel hangs are a separate substitution |
| Towel Pull-Up Sprints | empty list | Towel and pull-up support together |
| Slow-Lowered Pull-Up | bodyweight | Pull-up support; bodyweight loading does not eliminate apparatus |
| Towel-assisted lateral neck isometric | bodyweight | Towel for this named assisted variant |

Exact permanent IDs, original raw values, row hashes, audit references and
review evidence are recorded in `shared/equipment-requirements.json`.

1. Capture current equipment eligibility for these five rows through the actual
   strength/conditioning consumers, across full, partial and absent apparatus.
   Check injury, phase, late-fight and clinical gates independently.
2. Correct only evidenced source fields, retain original values as historical
   provenance, and rebind new row hashes to the **same** catalogue IDs. Update
   affected review/alias hash bindings together; prove media keys and historical
   references remain stable. Avoid rewriting unrelated bank rows.
3. Document exact intended equipment-gate changes: climbing-rope-only setups
   may pass the rope-climb equipment gate; battle-rope-only setups must fail.
   Apparatus-dependent pull-ups and towel-assisted work must fail their equipment
   gate when mandatory items are absent. Passing equipment never overrides any
   other exclusion or guarantees selection into a plan.
4. Run candidate-set and fixed-seed plan comparisons. Attribute intended changes
   to these reviewed rows; verify unrelated eligibility, scores, ordering,
   prescribed doses, injury exclusions and rehabilitation boundaries separately.
5. Review integrating shared requirement groups only where needed. Existing
   source splitting interprets separators as simultaneous requirements; it cannot
   establish alternative execution. Keep the 11 UNKNOWN decisions unresolved.
   Do not migrate ANY/OPTIONAL semantics, quantities, apparatus subtypes or partner
   permissions without source evidence and consumer-specific tests.

The current setup-only helper is intentionally unused by prescription engines.
Its capability-set input cannot prove a mandatory quantity greater than one.
Planner integration requires the relevant quantity evidence/inventory rather
than treating a canonical apparatus token as sufficient.
