# Metadata remediation execution plan

This is the authored plan template copied by the audit script to the reports directory. It authorises no runtime change. Generated register issue IDs, affected identities and dependencies supply each later PR's exact candidate list; every REVIEW decision stays unresolved until evidence is recorded.

## Smallest maintainable architecture

Extend the existing `shared/equipment-aliases.json` contract with reviewed apparatus identities, filter labels and explicit parent/subtype relationships. Keep `data/tag_vocabulary.json`, `fightcamp/rehab_schema.py`, `fightcamp/injury_location_registry.py`, `fightcamp/tag_maps.py`, and `fightcamp/sports.py` as their existing domain authorities. Do not invent a second clinical anatomy or injury registry.

For training classifications, a small `shared/training-metadata.json` file can hold field-scoped identifiers, labels and reviewed aliases for goals, qualities, movement and energy systems where no existing authority owns them. Add it only for the reviewed values that need one shared definition. Separate namespaces prevent `power` in method from proving a power goal, or `neck` anatomy from proving vestibular training. Keep review provenance alongside aliases.

Use small pure adapters around these contracts. Python and TypeScript should read the same labels/IDs, while source provenance remains raw. Avoid a generic ontology engine, recursive inheritance, database tables or a new taxonomy service. The first adapter must be catalogue-only; changing the planner or rehab normaliser requires its own compatibility PR and behavioural evidence.

Keep three representations explicit:

1. Original source evidence and pinned identity, retained exactly as today.
2. Canonical field-scoped identity used by filters and, only after migration/parity checks, planner consumers.
3. User-facing labels and discovery phrases with their own reviewed evidence rules.

Clinical and planning evidence standards remain stricter than search. Search may show labelled related work; it must not promote that match into a verified goal, injury permission, contact clearance or prescription. Existing `prescription_allowed: false` boundaries remain intact.

Equipment setup eventually needs `all_of` simultaneous requirements and `any_of` alternatives. Example: a reviewed sledgehammer strike can require both hammer and target; a treadmill/rower interval may allow either. Arrays alone do not settle that distinction. Preserve raw punctuation, unknown quantity, optional attachments, partner availability and subtype requirements until the source establishes them. An explicit empty equipment array means no apparatus; absent/null/unknown does not.

Parent/subtype relationships should be filter expansion, not implicit substitution permission. Mat thickness, band length/resistance, handheld pad type, bike design and vestibular focus need explicit suitability evidence. Runtime broad capability aliases do not prove identical implements.

Mechanical risks should live in `mechanical_risk_tags`, separate from training goals and anatomy. Existing mixed `tags` copies must remain until every injury/planning consumer switches with proven equivalence. No mass deletion of `mech_*` is safe now.

## PR 2 — canonical discovery projection and labels

Exact scope: add a small catalogue-only projection for the high-confidence MERGE/RENAME decisions in `remediation.json`; use raw source values as evidence and retain them in previews. First candidates are battle-rope apparatus terminology, kettlebell plurality, weight-vest synonyms, rower terminology, double-end-bag separators, and hip-adductor anatomical naming. Upper-back terminology needs the clinical identity migration gate below and is excluded from this first group. Mat/mats, hand/foot timing, cable setup, energy-system aliases, anatomy plural variants and all unresolved semantic assignments are excluded from automatic merges.

Use the projection to group equivalent equipment filter IDs and labels. Keep goal coverage and discovery concept rules unchanged. Preserve quantity in source instructions; do not infer one versus two implements. Broad equipment families may share a parent filter only if subtype/requirements are still visible. Keep compound strings unresolved in their original representation. A projection does not repair an inaccurate apparatus association: battle-rope tokens on a climbing drill still need PR 4 review.

Before: freeze this audit baseline, all catalogue IDs/media keys, search query anchors/exclusions, raw Goal facets, equipment known/unknown states and filter counts. Capture generation and rehab outputs for the current regression suite.

Keep the existing shared pads alias semantics unchanged in this PR. New catalogue aliases must use a separate field-scoped projection or an additive section ignored by current planner/intake readers. Check `canonicalizeEquipmentAccessValues`, `getOptionLabel`, `EquipmentSelector`, `TrainingLibrary` and `DrillPreview`: persisted intake values survive hydration, API facet identifiers stay exact, and display labels do not become capability or prescription evidence.

After: every source hash, raw row, identity and prescribed output remains identical. Filter-group counts equal the union of distinct source entry IDs, never the sum of overlapping aliases. Every projected value cites a reviewed alias and raw source evidence. No unknown becomes no-equipment; no climbing rope becomes battle ropes; no subtype becomes a permission substitute. Run catalogue/library/search-quality and metadata audit tests plus existing injury/phase regressions. Accepted changes are limited to documented equivalent filter grouping/labels; unrelated rankings and goals remain identical.

## PR 3 — planner alias compatibility, then source naming

Exact scope: handle verified spelling/plural terminology separately from semantic changes. First build consumer-specific compatibility adapters for those PR 2 aliases, including exact-match configuration maps and normalised runtime readers. Compare their outputs before changing any bank. Shared terminology must not replace modality/dose semantics or clinical identity keys.

Only then rename source values or remove truly repeated identical array tokens where review verifies no significance to order/multiplicity. Rebind existing catalogue manifest records to changed row hashes while preserving every source-scoped ID. Refresh pinned search aliases only for the same reviewed exercise meaning. Catalogue/search content revisions should change; permanent identities should not.

Before: capture raw and normalised tags/equipment, eligibility, score breakdowns, phase/system allocation, deterministic ordered candidate lists, D-21 through D-1 choices, hard-cut constraints and fixed-seed plan/Stage 2 outputs. Include constrained/no/unknown equipment and injury scenarios, not only healthy full-equipment examples.

After: all eligible sets, score evidence, order, programme doses and clinical outcomes are identical to before for naming-only migrations. Check source identity cardinality, no new UUIDs, preserved media keys and reviewed alias bindings. Audit bank/source hashes must change only for approved rows; archive and immutable historical evidence remain unchanged. Run bank validation and strength/conditioning/style/taper/coordination/restriction/identity regressions. If behaviour differs, stop source migration and review the adapter; never adjust golden tests simply to accept the difference.

## PR 4 — equipment grouping and inaccurate loading/classification

Use two separate reviewable groups (split into PRs 4a/4b if necessary):

- Equipment: inspect every compound and no-equipment/setup conflict. Establish simultaneous/alternative/optional requirements from instructions, source and intended variant; add explicit grouping only for reviewed rows. Review omitted carry weights, pull-up supports, pads/partners and climbing-rope versus battle-rope associations. Unknown requirements remain unresolved.
- Loading/programming: inspect stationary rope landing/reactive risk, low-impact versus high impact cost, eccentric intent versus low-eccentric claims, mixed energy emphasis, non-energy `system` values, total duration versus active work, and RPE ceilings. Use source provenance and qualified programming review. A conservative incorrect tag may exclude safe work; an incorrect low-demand claim may admit unsafe work. Neither is a spelling fix.

Also review declared restrictions without named readers (`avoid_if`, `contraindications`, `block_if_fight_within_days`) and case-dependent input aliases. `GOAL_NORMALIZER` currently distinguishes `Speed` from `speed`; forcing case-insensitivity can change selection rather than merely clean a label. Establish existing effective restrictions before deciding whether to add enforcement or retire an unsupported declaration.

Before: retain affected raw rows and all dependency receipts. Produce one reviewed decision per affected ID with explicit mechanics, actual dose, apparatus and intended adaptation. Capture baseline eligibility/block reasons, injury restrictions, score/order, workload profile and proximity windows.

After: expected behavioural differences are written per affected scenario and reviewed, while unrelated scenarios remain identical. Add negative controls for rebound mechanics versus cognitive cues, grip objective versus hand support, D-1 apparatus, contact permission and low-impact exceptions. Preserve IDs through reviewed rebinding and historical evidence. Do not mass-delete risk tags or infer cost from a modality alone. Run targeted injury/late-window/dose/generator tests and source validators. Broader generator testing is required because these changes intentionally affect selection.

## PR 5 — anatomical and clinical metadata reconciliation

Exact scope: upper-back separators, bicep/biceps, hamstring/hamstrings, group location/type joins and missing stage/function/dose/pain/contact declarations. Use `injury_location_registry` and `rehab_schema` as authorities. Review neck/vestibular and composite full-body/stance anatomy separately from clinical target regions.

Do not blanket-fill nulls. Read existing review records, pathways, regional policies and evidence notes. Distinguish a supported mechanics declaration from an active prescription and from demonstrated tolerance. Dose, progression, stop/regress rules and permissions require their own qualified evidence. Software validation or a data hash is not clinician approval.

Before: enumerate affected active/shadow prescriptions, bank-hash bindings, immutable exposure events, clinical criteria, live stages, clearance/contact scopes, contraindications and archived completion IDs. Capture all stage/region/type/side/severity/equipment/negative-response rejection reasons.

After: preserve historical identities and event interpretation. Use explicit compatibility for old region identifiers; never rewrite archive rows or silently regenerate policy hashes to approve new semantics. All existing holds, unknown-demand outcomes, non-promotable transitions, stage boundaries and contact restrictions must remain equivalent for a naming-only group. Any clinical behaviour change needs reviewed expectations and positive/negative evidence. Run rehab schema/selection/clinical/progression/exposure/completion/clearance tests. Keep unavailable or unreviewed stages blocked.

## PR 6 — evidence-backed Goal curation

Exact scope: review currently missing goals using explicit method/system/quality/tactical-function plus exercise guidance and programming context. Audit existing broad injury-prevention/readiness claims before adding new ones. Keep discovery synonyms as search language until they meet the stronger per-entry Goal evidence standard. No coverage percentage target.

Before: freeze explicit source goals, current facets, every reviewed discovery rule and query control. For proposed goals, retain source hashes, exercise instructions, intended adaptation and reviewer rationale. Separate a true goal from mechanics, anatomy, energy demand, apparatus and restriction.

After: only approved entries gain goals. Every new Goal facet has a source-backed review and stable identity; related search matches alone never qualify. Report changed coverage and which entries remain unknown, with no claim of efficacy certification. Re-run search anchors/exclusions, goal facet precision controls, catalogue identity and generator/injury tests. If planner scoring uses newly declared goals, handle that intended programming change in a separate reviewed consumer PR.

## PR 7 — obsolete metadata retirement, only where proven

No current value is approved for RETIRE. A missing literal/read is insufficient because generic field retention, inference, rank maps and dynamic configuration consume values. Investigate each candidate against active imports, dynamic reads, aliases, policy definitions, historical references and deployment compatibility. The empty coordination compatibility shim and rehab historical archive are explicitly preserved until their live readers have a replacement.

Before: prove zero active selection/search/configuration use or document a tested compatibility replacement, including persisted IDs/events and old client filters. Write explicit evidence and rollback for each retired value/source.

After: no unreachable references, no broken historical completion/media IDs, no changed clinical permissions and no undisclosed search/programming differences. Run consumer-specific regressions and regenerate the complete audit. Preserve compatibility until removal evidence is complete.

## Cross-PR acceptance

Each PR states issue IDs, affected source identities, approved semantics, consumers and expected output differences. Naming-only changes require behavioural parity. Semantic changes require narrowly specified and reviewed differences. Every group reruns the deterministic audit against an explicitly reviewed new baseline, checks source identity/hash bindings and retains previous evidence; never overwrite PR 1's evidence to hide a difference.

Keep source banks, policy content, catalogue identity, user-facing projection and clinical history independently reviewable. Ship only after relevant tests and before/after evidence pass. No deployment, schema change or remediation is part of PR 1.
