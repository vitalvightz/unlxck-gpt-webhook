# Conditioning programming audit and validation

Audit date: 2026-10-15. Baseline: `db8d855e` (PR #2881), including #2878.
Scope: existing candidate selection → role budget/contact resolution → composition
→ prescription resolution → goal evidence → read-only exercise coaching.
No new engine, model call, intake question, schema, media service or player.

## Evidence and reproducibility

The audit covers all **588** original conditioning entries: general 236,
style 277, taper 75. It also inspects all **58** `data/coordination/` records.
The legacy `data/coordination_bank.json` is empty at this revision. The selector
still reads that legacy bank; the directory's sport-specific records flow through
`coordination_support_library`. All 58 are support-only, not conditioning anchors.

`reports/conditioning_programming_audit.csv` records identity/media key, dose,
units, recovery, adaptation, equipment, sport/tags, phase, impact, fatigue cost,
governance and review flags for every entry. It contains 649 rows after the three
essential protocol additions. Regenerate without changing data:

```sh
python tools/audit_conditioning_programming.py --out reports/conditioning_programming_audit.csv
python tools/audit_conditioning_programming.py --ref db8d855e --out /tmp/conditioning-before.csv
```

The live `plans.planning_brief`, `plans.stage2_payload` for
`741aa47d-23fb-43d9-964a-b8e06b93a48a` and 732 `public.exercise_media` rows
were read through the connected Supabase project. No production data was written.
The existing anonymised programme fixture supplies the saved prescriptions;
two small additional fixtures preserve relevant intake/contact and numeric dose
facts. Names, contact details and athlete identifiers are not added to the fixtures.

## Confirmed mistakes corrected

| Record or consumer | Finding | Change |
| --- | --- | --- |
| Hill Sprint Repeats | 8 × 8s maximal / 120s recovery was glycolytic/high lactate | Alactic (`ATP-PCr`), low lactate; keep 8/120/8, high impact/mechanical cost and SPP eligibility |
| Concept2 Rower Zone 3 Block | Moderate zone-3 work, 3 × 4min / 2min easy, was glycolytic/high lactate | Aerobic capacity, moderate lactate; retain intensity, RPE 7 and original dose. This is **not** automatically red-zone HIIT |
| Active-work arithmetic | Legacy rep/metre values in `work_sec` and elapsed totals could count as seconds of conditioning | Abstain on rep/distance/mixed units; elapsed recovery never becomes active work; per-round minute tokens cannot become whole-session time |
| Continuous recovery fields | Swimming (Freestyle Laps), Footwork Ladder (Continuous Flow), Wrestler Chain Drills (50% Effort) stored a session-length value in `rest_sec` | Remove those three false recovery intervals; preserve written continuous doses and duration |
| Speed evidence for rep plyometrics | Rep counts could masquerade as seconds | Full-rest, low-rep maximal ballistic jump sets retain speed evidence in **sets/reps**, through the existing witness/validator contract |
| Primary-only developmental gate | Secondary conditioning/gas-tank priorities lost candidates needed to complete an existing role | Retain enough candidates for secondary priorities too; no additional role or session allowance |
| Secondary gas-tank weakness | Could disappear if conditioning was not also selected as a goal | One merged secondary conditioning obligation, using existing maintenance/deferral coverage |
| Generic weekly advice | “Add volume weekly” / “increase density or intensity weekly” was independent of future doses | Remove those instructions; the next resolved prescription authorises advancement |
| Taper complement evidence | Goal evidence could fall back to bank rounds after the countdown owner prescribed a single effort | Persist the authorised work/rest/rounds on the existing tail assignment; no taper dose changes |

Names, existing IDs/keys, order and media references are preserved. No entries are
deleted or renamed. The rower's original name is retained deliberately.
The snappy overhead-slam note now describes a light ball and crisp execution
without offering an unresolved kilogram range as an athlete-facing working dose.

## Eligibility and intentional distinctions

- **Reaction Ball Drills** already has `support_only: true`,
  `meaningful_stress: false`. Its legacy alactic label does not give it meaningful
  conditioning authority. Keep it as reaction/sharpness support.
- **Neck Harness Flexion/Extension** already has `placement: strength` and is
  support-only. Keep identity/strength placement; remove the unsupported claim
  that neck training reduces knockout risk. It does not satisfy conditioning.
- **Breath-Hold Shadowboxing Intervals** is excluded from automated selection
  with the existing manual-review flag. Breath-holding during exercise can cause
  dizziness/syncope; normal-breathing shadowboxing already exists. The record is
  retained for specialist review, not converted to another drill behind its name.
- **Heat Acclimation Rounds** is also excluded pending specialist review.
  Ambient heat/hydration/cut monitoring is not available to this planner. Its old
  “+20% fluid” instruction cannot establish safety or a conditioning adaptation.
- Easy aerobic output, demanding aerobic HIIT, buffering, repeated efforts and
  very short fully recovered speed work are distinct even when movements match.
  High systemic fatigue or lactate does not alone rename an aerobic adaptation.
- Equipment, sport, injury, phase/countdown and existing collision filters remain
  authoritative. A more specific score never makes an ineligible drill legal.

The original audit flags **87** rep/distance/mixed prescriptions (86 general,
one style), and 37 general entries without structured recovery. These are review
flags, not permission to invent seconds or recovery. Their written doses remain.
Examples: broad jumps are reps, sled starts are metres, and mixed rep circuits do
not state work seconds merely because they have a numeric round estimate.

Elapsed conventions also differ intentionally: 74 taper records include recovery
after the final effort; normal timed intervals use between-effort recovery.
They must not be silently treated as equal active work. The EMOM block includes
the last minute's reset. Three style records (Entry-Score-Exit Bursts, Backstep
Counter Reset, Straight-Shot Re-Angle) have totals that do not match either simple
interval arithmetic or an explicit transition allowance: leave those totals for
author review, using verified work × rounds for active work.

No exact duplicates remain when comparing all fields except name/ID/key. Similar
doses alone do not prove duplication. In particular, `Range Recovery Intervals`
and `Range-Recovery Intervals` share a media key but differ in boxing versus
kicking-range actions; this is an identity/media collision to review, not a safe
merge. `Pull-Counter-Reset` (taper) versus `Pull-Counter Reset` (coordination)
likewise has different placement/dose ownership. Historic base/suffixed clone
findings in `reports/conditioning_bank_audit.md` describe a pre-cleanup snapshot
and must not be applied again to the current 236-entry bank.

## Reference protocols and essential gaps

Sources read in full on the audit date:

1. [Boxing Science conditioning method](https://boxingscience.co.uk/conditioning-for-boxing-the-boxing-science-method/):
   aerobic HIIT examples 4/2, 6/3 and 8/4 minutes; 30s maximal SIT with 3–4min
   recovery; a buffering example of 2min work / 3min recovery. The article
   distinguishes central aerobic and peripheral adaptations and stresses output
   monitoring. Short active time can still impose substantial fatigue.
2. [Boxing fitness](https://boxingscience.co.uk/boxing-fitness/):
   production/recovery/repetition of high-intensity actions; monitored aerobic
   work, SIT, and repeatable measurable output. A four-minute effort alone does
   not establish the intensity required for aerobic HIIT.
3. [Planning the training week](https://boxingscience.co.uk/planning-your-training-week/):
   boxing quality comes first; sparring, work/study, experience and competition
   proximity govern S&C frequency. Its example schedules depend on timing and
   separation, not a universal number of additional interval sessions.
4. [Terri Harper case study](https://boxingscience.co.uk/terri-harper-strength-and-conditioning/):
   individualised peripheral/buffering and power-to-speed-endurance work, with
   nutrition and weight availability materially affecting what was possible.
   That athlete's late lifting/loading is not a generic taper prescription.

| Stimulus | Existing coverage | Essential action |
| --- | --- | --- |
| Easy aerobic | Zone-2 bikes, jog, swim and other continuous low-fatigue work | Reuse |
| Alactic speed | Short bursts with full rest; hill entry now correctly classified | Reuse/reclassify |
| Repeated efforts | Numerous shorter hard bag/machine/sport intervals with controlled recovery | Reuse; do not equate with fully recovered SIT |
| Aerobic HIIT | Rower zone 3 was moderate, not a documented high-intensity 4/2 protocol | Add **Air Bike Aerobic HIIT**, 3 × 240s / 120s, RPE 8 |
| Sprint intervals | Existing 30s entries mostly have 90–150s recovery or mixed movements | Add **Air Bike Sprint Interval Training**, 4 × 30s / 180s, maximal intent |
| Buffering | Existing long circuits/2min rope work do not reproduce demanding 2/3 work | Add **Air Bike Muscle Buffer Intervals**, 4 × 120s / 180s, RPE 8 |

These are introductory bank prescriptions, not universal copies of the elite
examples. All three are complete, high-cost `standalone_protocol` entries.
Composition measures their own authored dose instead of padding two minutes of
maximal sprints up to a generic eight-minute circuit target. They retain aerobic
or glycolytic system fields. Their work intervals never inherit a fight-round
length. Selection requires explicit low fatigue and fewer than two declared hard
contacts; existing injury/equipment/countdown filters still apply. Unknown
recovery is not an invitation to replace easy work with HIIT.

## Decisions and dose authority

`stage2_role_map` retains calendar/contact/session-budget ownership.
`conditioning_boxing.conditioning_load_context` reads the resolver's effective
hard days, including an explicitly empty result; duplicate weekday labels count
once. The calendar's structured session budget remains authoritative.
Ordinary coach-led boxing/padwork remains **unknown** in the evidence. It is not
credited as a known aerobic, buffering or SIT dose, and is not counted again as
app conditioning. Two effective hard days defer an additional hard exposure.

`prescription_resolver.apply_effective_conditioning_prescriptions` consumes
closed assignments and their composition ceilings:

- **Maintain:** repeat an authorised dose; uncertain units/recovery, an unchanged
  workload, a reached ceiling, and absence of adaptation data do not justify a ramp.
- **Reduce:** withhold one round of a verified timed interval for recovery/cut/
  injury pressure or dense/adjacent sparring. Keep work time, rest and effort.
  Record the deliberately reduced workload target without concealing an earlier
  composition underfill.
- **Increase:** restore at most one previously withheld round, within the
  composition ceiling, only after resolved hard-contact load falls, fatigue is
  explicitly low, additional coach intensity is not unknown, and work/rest/RPE
  remain comparable. This is restored headroom, not a claim of measured adaptation.
- **Defer:** retain the existing role-budget/suppression decision; do not insert
  sessions to compensate for a secondary limiter, unmeasured boxing, or a sparse
  week. Final-fortnight/taper shaping remains with the countdown owner.

The resolver is idempotent. It never changes coach-owned conditioning, exercise
identity, placement, membership, or the bank prescription. Changes are in the
next assignment's `effective_prescription` **before** the #2881 coaching lookup.
Coaching cannot write a dose. Example: heavy-contact week `3 × 120s / 180s`,
contact-relief week `4 × 120s / 180s`, then maintain four. Progress says:
“If recovered, next D-35: increase rounds only from 3 to 4; keep rest and effort
unchanged.” Easier reduces one known work quantity and preserves effort/rest.
No simultaneous work increase/rest decrease is authorised.

## Actual programme 741aa47d: before and after

The live intake has speed primary, conditioning secondary, balance primary
weakness and gas tank secondary, 10 × 3min, and **six** weekly sessions in the
structured frequency field. Tuesday/Saturday hard
sparring and Thursday/Friday coach-owned sessions compete with app S&C for that
six-session allowance. The structured intake owns the session budget, and fixed
coach sessions remain unchanged. Free-text session estimates are excluded from
the workload evidence and programming assessment.

The recorded Stage-2 payload was replayed through the actual
`build_planning_brief` on baseline and changed code, with the same selected pools.
This isolates planner/dose changes; it does not claim a new LLM-generated plan
or completed training response. A committed regression also replays the existing
anonymised saved prescriptions with the live numeric/contact facts.

| Week | Actual distinct conditioning before | After |
| --- | --- | --- |
| 1 GPP | D-50 Easy Assault Bike 30min continuous; D-45 Broad Jump Repeats 6 × 3 reps, 120s rest | Same |
| 2 GPP | D-38 Broad Jump Repeats 6 × 3 reps, 120s rest | Same |
| 3 SPP | No separate conditioning appointment | Same; defer extra hard work |
| 4 SPP | D-24 Swimming (Freestyle Laps) 35min continuous | Same |
| 5 SPP | D-15 Max-Power Bag Burst 8 × 5s, 60s rest | **7 × 5s, 60s rest** under two hard-contact exposures |
| 6 taper | D-10 Tempo Shadowboxing 30min continuous | Same countdown-owned dose |
| 7 taper | D-5 Explosive First-Step Cue 2 × 5s; Pocket Frame-Burst Touch 1 × 5s; Pull-Counter-Reset 1 × 5s; 120s rest | Same countdown-owned doses |

The limited number of distinct conditioning appointments is **justified by the
declared cap and resolved sparring/collision constraints**, rather than evidence
that the planner forgot to schedule intervals. Broad jumps and reaction work
are not aerobic development, however. Unmeasured boxing/padwork cannot prove
that the athlete receives enough of every conditioning stimulus. The confirmed
programming omission is the primary-only candidate gate, corrected without
overriding those constraints. Repeated easy doses do not need a Progress promise.

The existing D-10 30-minute shadowboxing prescription is a countdown-owned saved
dose; this PR neither treats it as new development nor rewrites the taper owner.

## Verification

`tests/test_conditioning_programming.py` covers authorised increase/maintain/
reduce/defer evidence, idempotence, fixed coach sessions, unknown intensity and
fatigue, secondary weakness merging, complete-protocol composition, unit
mismatches, elapsed recovery, the actual saved programme, primary conditioning,
primary gas tank, amateur/pro volume, 3 × 3 versus 10 × 3, short camp, injury/
fatigue, heavy sparring, final fortnight and taper. Existing combat-pressure,
goal-preservation, session-cap, injury, countdown and #2881 suites cover the
surrounding ownership contracts. See PR checks for the final CI result.

No extra model/network request is introduced. Local timing compares the same
recorded payload through the deterministic planning path, with warm caches;
it does not estimate provider or end-to-end generation latency. Timing and
final check results are recorded in the PR.

Measured locally over three builds: baseline median **603ms**, changed median
**571ms**; first cold builds 3.10s and 2.68s respectively. The difference is within
local run variability; no material increase was observed. A broad local run
passed 1,145 relevant tests; final production regeneration, saved-plan/API and
rendered React coaching release coverage passed **180 tests with no skips**.
The bank/unit correction suite passed 131 tests, and the explicit scenario/
combat-pressure/bout suites passed 159 tests. A subprocess timeout check also
passed in isolation after exhausting its ten-second import budget under local
concurrent load. See the final PR CI runs
for verification on the project's pinned Python 3.11 environment; local Python
is 3.12 with the fast development dependencies.

Media findings and the small unapproved protocol demonstration list are in
`reports/conditioning_video_manual_review.md`. Large-scale curation remains separate.
