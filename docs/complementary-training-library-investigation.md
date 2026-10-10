# Your Training: complementary plans and a shared library

Investigation only. No training flow, planner rule, bank data, schema, RLS policy,
environment variable or deployment is changed by this PR.

Audited baseline: `Main` at `339e7c138f492ab6682ca6f371bef2b1dfd3493d`
(10 October 2026). The original checkout was on a divergent feature branch with
substantial uncommitted changes. This investigation uses an isolated checkout of
the remote default branch; those local changes are not part of this evidence.
Database evidence comes from repository schema and migrations, not a live database.

## Product decision

Unlxck helps fighters manage their coach's sessions, their own routine and Unlxck
recommendations together. Keep the entry point in Plan. Build in this order:

1. **Log Training:** record completed work with activity, duration and effort.
2. **Add Session:** schedule a commitment alongside the active plan.
3. **Build My Own Plan:** save a weekly template and repeat it.

All three use one occurrence contract, one training-history service and the same
adaptive planning inputs. A searchable library supplies exercises to each flow.
This PR makes that implementation reviewable; it does not ship those features.

## Existing architecture and gaps

| Area | Existing implementation | Consequence |
| --- | --- | --- |
| Plan entry | `web/app/plan/page.tsx` redirects to the active `/plans/{id}` or `/plans`; `plan-detail-screen.tsx` mounts `PlanViewer` | Add the training workspace to the existing Plan surfaces, including the no-active-plan state. |
| Session history | `api/routes/today.py`, `api/services/today_service.py`, `api/models.py`, `session_completions` | A completion requires an owned plan and session. Retrospective logging still requires a scheduled session. It cannot represent arbitrary external training. |
| Exercise history | `api/services/exercise_log_service.py`, `api/routes/today.py`, migration `20261007141918_add_exercise_logs.sql` | Prescribed blocks can already be logged with frozen prescribed and actual values. Logging requires a started/completed session today and a server-owned block ID. Rehab evidence uses its own completion flow. Reuse the actual-value contract; retain these guards. |
| Legacy logs | `api/routes/daily.py`, `api/readiness.py`, `session_logs` | Legacy session-log HTTP routes were removed. Do not revive this as a parallel consumer history/adaptation engine. |
| Today adaptation | `api/contracts/readiness_message.py`, `today_service.py`, `today_readiness_boundary_core.py` | Today consumes recent completions, check-ins and injuries. Recent hard work is currently assessed from RPE/pain; `_recent_hard_session_count` inspects at most three rows. Duration is not an input to that rule. |
| Generation adaptation | `api/services/sparring_readiness_snapshot.py`, `fightcamp/sparring_readiness.py` | Generation reads dated completions and resolves contact load from the referenced plan session. External sparring has no reference session, so it currently cannot enter this evidence path. |
| Exercise identity | `fightcamp/exercise_identity.py`, `api/structured_block_identity.py` | Existing name-based `exercise_key` is shared with media. A block ID identifies an occurrence, not a library entry. Preserve both; add a source reference for bank-specific restrictions and variants. |
| Banks and search | `fightcamp/injury_filtering.py`, `conditioning.py`, `coordination_support_library.py`, `bank_authority.py` | `collect_banks()` covers five legacy reservoirs; it omits technical footwork, coordination V2, rehab and tactical/visualisation libraries. No shared consumer search endpoint or saved-library flow was found. |
| Recovery | `fightcamp/recovery.py` | Recovery guidance is generated in code, not a standalone exercise bank. Some mobility drills exist in strength/rehab banks. Do not turn every recovery instruction into a fictional exercise. |

Important storage detail: `supabase/schema.sql` is not the complete inventory.
`exercise_logs` is defined by its migration. `session_completions.plan_id` is
required and cascades on plan deletion; `exercise_logs.plan_id` permits null and
uses `ON DELETE SET NULL`. Preserving history after plan deletion needs an explicit
decision before implementation. Do not simply make completion plan IDs nullable:
completion, prescription, rehab, feedback and XP paths depend on those identities.

## Raw bank audit

Run `python tools/audit_training_library.py` from the repository. The checked-in
output is `reports/training_library_metadata_audit.json`. It includes per-file
SHA-256 hashes, field-state counts, raw tag counts and every repeated-name group.
The tool reads explicit live sources; it imports no runtime bank normalisers,
fills no defaults and changes no bank files. `coordination_bank.json` is a legacy
shim; the five files in `data/coordination/` are the live support library.

| Source | Entries | Explicit ID/key | Populated tags | Known equipment | Explicit sport field/tag |
| --- | ---: | ---: | ---: | ---: | ---: |
| Strength (`exercise_bank.json`) | 339 | 0 | 339 | 339 | 8 |
| Conditioning | 236 | 0 | 236 | 236 | 25 |
| Style conditioning | 277 | 0 | 277 | 277 | 259 |
| Style taper | 75 | 0 | 75 | 75 | 75 |
| Technical footwork | 25 | 0 | 25 | 25 | 25 |
| Legacy coordination shim | 0 | 0 | 0 | 0 | 0 |
| Coordination: universal | 12 | 12 | 12 | 12 | 12 |
| Coordination: striking | 18 | 18 | 18 | 18 | 18 |
| Coordination: kicks | 12 | 12 | 12 | 12 | 12 |
| Coordination: MMA transitions | 9 | 9 | 9 | 9 | 9 |
| Coordination: grappling | 7 | 7 | 7 | 7 | 7 |
| Rehab/care (755 groups) | 1,603 | 1,603 | 0 | 166 | 0 |
| Tactical watch | 183 | 183 | 183 | 0 | 183 |
| Fight visualisation | 59 | 59 | 0 | 0 | 59 |
| **Total** | **2,855** | | | | |

These are source entries, not 2,855 unique, eligible physical exercises. Rehab
contains wound-care and other care instructions. Tactical watch and visualisation
are distinct activity types. Repeated names must retain their context until
reviewed; the audit found **58 repeated-name groups**, including same-name drills
under different rehab groups. Names alone are unsafe as library selection IDs.

`equipment: []` explicitly means no equipment. Absent, null and unknown equipment
remain unresolved; they must not pass a "No equipment" filter. Sport counts only
include a populated `sports` field or explicit sport tag, not inferred suitability.
A low sport count for general strength does not establish a sport restriction.

No audited entry has populated `difficulty`. None of the five main strength,
conditioning and footwork sources has structured `why`, `progress`, `regress` or
`stop` fields. Notes often contain useful guidance, but prose is not structured
authority. Coordination has `why`/`cue`; tactical watch has `why`/`progress`;
visualisation has `why`/instructions. Do not fabricate missing preview guidance.

Rehab metadata is particularly incomplete: only **166/1,603** entries have a
populated stage; **3** have a populated dose; **8** have populated `stop_when`,
`regress_when`, severity and pain-ceiling fields; **2** have `progress_when`.
Those counts do not measure clinical clearance: pathway policy can supply or
restrict a dose, and entries with metadata are not automatically approved.
Use `rehab_metadata_review.json`, `rehab_pathways.json`, the existing regional
profiles and their validators to establish reviewed eligibility.

## One search library, with source authority intact

Use a shared, cached index derived from existing sources. Add small adapters for
flat banks, coordination V2, grouped rehab and tactical/visualisation content.
Each result carries source path, source ID/key where present, source revision,
name, existing `exercise_key` where applicable, raw metadata, display labels and
field provenance. For rows without an ID/key, introduce a reviewed source-ID
manifest in the implementation PR; do not use array position as a durable ID.
Keep a name/media alias separate from a bank source identity.

Search names, descriptions, notes, cues, instructions and explicit tags/qualities.
Use a small reviewed synonym dictionary for fighter language. Deterministic
ranking should prefer exact name, phrase/name tokens, reviewed goal synonyms,
then descriptive text. Apply eligibility and active filters before ranking;
break ties with durable source IDs. No LLM-generated metadata or embedding
service is required for the first release.

| Fighter language | Source evidence / mapping decision |
| --- | --- |
| High-intensity endurance | No literal `anaerobic_capacity` tag found. Review the existing system, modality and dose together; do not label every alactic sprint as endurance. |
| Punching power | Existing `rotational` tag occurs 27 times. Search alias is useful; a rotation tag alone does not prove punching relevance. Review movement descriptions and sport context before applying the goal label. |
| Reaction speed | Existing `reaction` and `reactive` tags; review reactive movement versus decision/reaction work. |
| Stamina | Existing `aerobic` and `endurance` tags; retain the distinction between low-cost support and a substantive conditioning session. |
| Core stability | Existing `anti_rotation` tag (40 occurrences); display alias can preserve the raw tag. |
| Shoulder control | Existing `scap_control` and `scap_retraction`; no literal `scapular_stability` tag found. Review the available mechanics before broadening the mapping. |
| Strength while lowering | Existing `eccentric`; `low_eccentric` describes low cost and must not receive this goal label. |
| Footwork & defence | Existing `footwork` and tactical-function metadata; do not label every footwork drill as defensive work. |

The language map changes display/search vocabulary only. It must not rewrite
technical tags, system classifications, phase logic, stress costs or injury rules.

Start with goal chips, sport, focus, equipment and training type. Show only options
supported by reviewed index values and relevant results. Put movement, intensity,
duration and solo/partner behind **More filters**. Difficulty and solo/partner
remain unavailable until source coverage is reviewed; missing data is not Beginner
or Solo. Boxing-specific offence, defence, counterpunching and footwork filters
need evidence-backed mappings, not assumptions from names. Distinguish available
equipment from an exact equipment facet, especially for multi-item requirements.

Every eligible result supports **Add to Plan**, **Log Exercise**, and **Save**.
Use existing prescribed-block logging when the selected block belongs to a started
or completed session today. Otherwise attach the exercise to a user-created occurrence. Saving a
reference is not a training event. Show Why, Progress, Regress and Stop in the
expanded preview, backed by existing guidance; say "Not provided" for missing
fields. Keep safety/clearance restrictions visible before selection.

## One occurrence model and history boundary

Proposed contract, not existing schema: an athlete-owned occurrence contains
an immutable occurrence ID, origin (`unlxck`, `added`, `custom`), optional owned
plan/template reference, activity type and display name, athlete-local training
day, scheduled time, lifecycle status, actual duration, qualitative effort,
optional reported numeric RPE, and optional exercise items/source references.
Prescribed and actual work remain separate. Capture snapshots where existing
prescription/rehab rules require them. Activity names and notes are untrusted text.

Use one server history service as the only training-evidence input for Today and
generation. Adapt existing completions into this contract; persist user-created
occurrences through the same service. New storage is required for plan-independent
occurrences; its name and migration are implementation decisions, not existing
tables. Do not dual-write copies of prescribed completions or count exercise
detail logs as extra sessions. Existing `exercise_logs` remain child evidence;
existing `rehab_exposures` remain authoritative injury evidence.

Scheduling creates a planned occurrence; completing it updates the same identity.
A standalone retrospective log creates a completed occurrence directly. Repeated
templates create new dated occurrences, with a uniqueness key for template,
template slot and local date. Editing a template affects future unstarted
occurrences only. Plan regeneration must preserve added commitments and completed
history. Explicitly link a manual entry to an existing occurrence when appropriate;
do not silently merge two sessions just because names/dates match.

Server-generated ownership, athlete-local dates, bounded duration values,
idempotency keys, correction revisions and source validation are required.
An edit/delete must invalidate future recommendation caches without rewriting
past prescriptions. Preserve owner-only reads and backend writes; check ownership
at service-role boundaries. Apply existing health-consent handling to optional
pain and notes. No real athlete records were accessed for this investigation.

## Adaptation: hard sparring is evidence, not automatic cancellation

For Carlos's completed 60-minute hard sparring session, store actual activity,
duration and **Hard** effort immediately. Do not pretend that qualitative Hard is
an athlete-reported RPE of 8. Preserve it as qualitative evidence; any numeric
workload proxy needs a versioned, reviewed mapping, with uncertainty exposed.
Contact exposure is a separate dimension: effort alone cannot establish how hard
head contact was. Keep contact questions optional in the basic form and retain
unknown contact exposure where it was not reported.

Build one dated workload snapshot from completed/modified occurrences, recent
readiness, injury restrictions and upcoming commitments. Planned sessions inform
scheduling conflicts and projected load; they never count as completed work.
Skipped work contributes no training load. Actual duration must not be replaced
by a bank's programmed interval time, elapsed UI time or a prescription estimate.

Feed that snapshot into the existing deterministic Today/generation authorities.
The current RPE/session-count rules need a reviewed duration-aware extension;
logging alone does not provide that behaviour. Bound and order the time window
explicitly rather than relying on the first three rows, and expose truncated or
unavailable history to the current failsafe boundary. Start with transparent rules,
not new arbitrary fatigue thresholds or a competing AI planner.

The next recommendation may retain training, reduce hard conditioning dose, or
offer lower-stress work depending on duration, intensity, recent load and readiness.
Preserve low-cost skill, mobility and recovery when appropriate. Explain the
decision and show the proposed change. Adapt Unlxck recommendations; keep
coach/user commitments fixed unless the athlete chooses to change them. Do not
erase a session or mutate a started/frozen prescription because a new log arrives.

Injury safeguards must be checked on the server when adding, scheduling, starting
or prescribing library work, including after saved items/templates are reopened.
Reuse `injury_guard`, injury exclusions, style quarantine, late-fight restrictions,
rehab selector/pathway policy and live-prescription revision checks. A historical
log records what happened; it must not imply present clearance, create a fake
prescribed completion, award prescription-based XP, or advance rehab progression.
Wound-care entries must not become selectable strength/rehab exercises.

## Plan interaction and implementation sequence

Follow the supplied dark, compact reference: **UNLXCK / PLAN**, **Your Training**,
two clear actions (**Add Session — Schedule training** and **Log Training — Record
completed work**), then dated rows with provenance and status. Tomorrow's roadwork
belongs under Tomorrow, not Today. Keep multiple sessions visible on one day;
do not replace the existing prescribed session with the last external log.
Use the Plan menu for **Build My Own Plan** and **Saved exercises**. Open the
library as a searchable selection view inside these flows rather than adding a
required navigation section. Keep the expanded exercise coaching preview.

| Implementation PR | Scope and integration points | Required evidence |
| --- | --- | --- |
| 1. Log completed training | Occurrence contract/storage, shared history service, three-field form on Plan, history rows; connect both Today and generation through the shared workload snapshot. Reuse exercise actual-value fields without relaxing prescribed-block guards. | No-plan and rest-day logging; ownership; timezone/DST; retry/edit identity; same-day multiple sessions; no double-counting; future/stale exclusion; duration validation; qualitative effort retained; history failure; unchanged rehab/XP evidence. Carlos's hard sparring must reach both recommendation paths. |
| 2. Add to existing plan | Planned occurrences with fixed user provenance; scheduling overlay and completion of the same occurrence; search index/adapters and library selection, save action and contextual filters. | Coach session survives regeneration; scheduled work is not actual load; restrictions rechecked on add/start; clearing a filter cannot bypass eligibility; deterministic ranking; unknown equipment excluded from No equipment; stable references across source edits. |
| 3. Build, save, repeat custom plans | Weekly templates made from existing library entries and custom activities; materialise dated occurrences through the same history/scheduling service. | Repeating twice is idempotent; recurrence across DST; template edits do not rewrite completed work; restrictions rechecked on repeat; deleted-plan history survives; custom activities never acquire invented bank/clinical metadata. |

Index development can run alongside PR 1, but the freeform training form must not
depend on complete tagging. Complete the metadata review in small batches before
enabling unsupported facets. Use descriptions as evidence, retain the source/hash,
and distinguish editorial labels from clinical or programming authority.

Acceptance checks for the full feature must also cover library actions end to end,
injury changes between selection and start, unknown/missing metadata, aliases and
same-name variants, mobile/keyboard operation, and preserved GPP/SPP/TAPER output.
Do not remove the original deterministic generation or change output formats to
make custom scheduling easier.

## Verification and remaining decisions

For this investigation: rerun the audit, compare its parsed JSON with the retained
report, and verify source hashes are unchanged. Use `python -m py_compile
tools/audit_training_library.py` for an import/syntax check. Existing bank validation
is available through `python tools/validate_banks.py --mode runtime`; its audit
mode always returns success even when it reports issues, so audit exit status alone
is not a clean-data claim.

Checks run for this PR: the new audit's import/syntax check passed; its rerun
matched the retained JSON; independent raw inventory counts matched; audited bank
hashes remained unchanged. The existing runtime bank validator **failed on the
unchanged baseline**, reporting 836 errors and 273 warnings. Its discovery also
treats 88 `rehab_pathways.json` policy entries as unnamed bank rows. These findings
need separate triage; no bank repair or validator rewrite is included here. Its
duplicate counts use a different scope/definition from this library audit.

Before implementation, settle the additive occurrence storage/migration and
deleted-plan retention policy, reviewed effort/workload rules, and durable source
IDs for the five banks without IDs. Check schema requirements and all migrations
against the intended environment. No live database behaviour, deployed UI or
duration-aware adaptive response is verified by this PR. No frontend build is
needed for these investigation files; implementation PRs must run relevant Python
tests, frontend unit/type/lint/build checks and complete-flow verification.
