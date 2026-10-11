# Remaining remediation and verification gates

This PR implements six terminology decisions for discovery only. It does not
close the underlying source-quality review or migrate any clinical identifier.
The 190 other register issues remain linked by original issue ID in
`before-after.json`; their full evidence remains in PR #2822's untouched reports.

| Order | Scope | Evidence needed before changing meaning | Before/after gate |
| --- | --- | --- | --- |
| PR 3 | Review equipment requirements and source associations | Read each compound's name, notes, instructions and equipment note. Explicitly record simultaneous requirements, alternatives, optional attachments, quantity, subtype or unknown. Review the two climbing associations and other apparatus accuracy findings independently of spelling. | Pin IDs, source rows and requirement evidence. Discovery can project only reviewed decisions; compare facet IDs, unique counts and negative apparatus matches. Keep planner requirements unchanged unless a separately approved programming change has its own eligibility and dose tests. |
| PR 4 | Qualified source accuracy corrections | Resolve questionable reaction, grip, mechanical loading, low-impact and apparatus assignments using drill instructions and intended stimulus; preserve uncertain entries as REVIEW. | Review every changed source hash and affected exact consumer. Compare plan selection, scores, ordering, phases, doses, injury exclusions and rehab eligibility for affected contexts. A changed safety outcome requires explicit clinical/programming approval, not alias inference. |
| PR 5 | Additional terminology and parent/subtype discovery | Review mats, resistance/mini bands, cycling apparatus, striking pads, timing, neck subtypes, full-body classifications and energy-system distinctions. Names alone are insufficient. | Add field-scoped discovery decisions with provenance. Retain distinct subtype IDs and apparatus evidence. Legacy filters and persisted athlete selections must survive; all 30 fighter-query controls and unrelated Goal facets must remain unchanged. |
| Later, separate clinical work | Anatomical and clinical registry alignment | Review target-region/tissue identity, clinical applicability and every restriction/progression consumer. Reuse existing registries; no discovery identity becomes clearance or proof of substitutability. | Clinical review plus exclusion, contact, pain-limit, stop/progress/regress and fight-proximity boundary tests; historical rehab completion/media identities remain resolvable. |
| Later, separate Goal evidence work | Evidence-backed missing goals | Investigate method, system, quality and tactical-function conjunctions against instructions, dose and context. Search synonyms alone cannot verify a goal. | Record per-entry source evidence and reviewer decisions; compare verified Goal counts separately from related search discovery. No percentage target or mass backfill. |

Every stage keeps its own frozen baseline and additive evidence report. No
stage overwrites PR #2822 reports or silently refreshes this PR's original
Main snapshot. Canonical display labels can evolve independently from stable
field-scoped identifiers; source metadata remains available for review.

Small shared mappings and pure library adapters are sufficient at this stage.
Do not add an ontology service, database, generic tagging framework, or a second
clinical registry. Introduce an explicit AND/OR requirement representation only
after compound meanings have been reviewed; retain the raw requirement alongside
any future structured representation.

The verification harness also exposed an existing hash-seed-dependent ordering
of two Stage 2 `movement_patterns` values. Investigate deterministic collection
serialization separately if cross-process payload byte stability is required.
This PR pins clocks and hash seed for full before/after payload comparisons and
does not change that programming representation.
