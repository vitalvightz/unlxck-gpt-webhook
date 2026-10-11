# Equipment accuracy and requirements cleanup

Status: draft implementation PR; equipment changes and verification are pending.
Base: Main at `b074e8a1`, including #2822 and #2823.

This stage will correct evidenced equipment associations and expose reviewed
mandatory, alternative and optional requirements in Find a Drill. It reuses
the existing metadata audit and canonical projection rather than repeating
the inventory. This opening commit records scope only and is not completion
of the implementation request.

## Implementation scope

1. Review equipment candidates in
   `reports/metadata_integrity/remediation.json` against each exercise's
   instructions, notes and source identity.
2. Add a small reviewed representation for SINGLE, ALL, ANY, OPTIONAL and
   UNKNOWN requirements, retaining original values and provenance. Separators
   alone cannot determine a relationship.
3. Correct confirmed inaccurate associations, including the two reviewed
   climbing-rope entries, preserving permanent catalogue and media identities
   and updating affected source-hash bindings.
4. Integrate requirements with library results and filters, preserving legacy
   aliases, independent filter AND behaviour and explicit additional apparatus.
5. Check planner equipment consumers before any eligibility change. Document
   intentional corrections; preserve unrelated selections, doses, phase rules,
   injury exclusions, rehabilitation and clearance boundaries.

## Verification and delivery gates

- Cover full, partial and absent athlete equipment, simultaneous versus
  alternative requirements, optional items and unresolved requirements.
- Verify no-equipment exclusions and climbing-rope/battle-rope separation.
- Preserve catalogue/media identities and existing athlete equipment choices.
- Run relevant catalogue, search, generator, conditioning, strength, injury
  and rehabilitation regressions; record any intended eligibility differences.
- Report issues reviewed/corrected/unresolved, changed source records, filter
  differences, test results and outstanding blockers before marking ready.
- Reuse frozen audit evidence. Keep detailed generated outputs temporary;
  commit implementation, small reviewed mappings, tests and concise summaries.

No equipment review, source correction or regression result is claimed by this
opening scope document. The PR remains draft until implementation and the
verification gates are complete.
