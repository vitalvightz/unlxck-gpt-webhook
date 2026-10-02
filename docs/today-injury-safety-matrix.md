# Today injury and clinician-clearance safety audit

Audited against Main `30934d41` (including #2701 and #2702), 2 October 2026.
Scope: execution semantics for existing injuries and reviewed rehab. No clinical
policy, bank, stage activation, scheduler, database or allocation model changes.

## Decision equivalence classes

Rows describe boundaries, not an exhaustive Cartesian product. A stronger gate
always takes precedence over a later row. Stable means the existing `ongoing`
injury report; it is not a new progression signal.

| Class / boundary | Expected execution | Coverage |
| --- | --- | --- |
| Mild/moderate, ongoing/improving, full current clearance, green readiness | Relax only that episode's generic load/contact restrictions; preserve rehab stage | Clearance live-policy matrix; safety matrix stable/improving cases |
| Severe, worsening, structural/neuro, medical review or current red flags | Full clearance cannot remove the gate; ordinary Start/Done/Modified rejected | Clearance hard-gate/red-flag tests; second-injury and support-stop safety cases |
| Full clearance + modify readiness | Existing reduced-work guidance remains; accepted content is frozen, not regenerated | Frozen readiness equivalence classes; readiness tests |
| Full clearance + pull-back readiness | Hold camp/contact. Fresh independently eligible non-loading rehab uses the existing standalone replacement. Frozen camp stays intact and held | Frozen pull-back submission regression; non-loading rehab and hard-contact sleep cases |
| Stop readiness | Hold current execution even for support work; no generic completion bypass | Support-stop submission regression; existing red-flag matrix |
| Not checked in | Live prescriptions stay held. A current clearance report cannot bypass the check-in through a shadow/no-live policy | Frozen readiness classes; no-live clearance/check-in regression |
| Rehab only | Hold ordinary camp; allow only independently eligible reviewed rehab or explicitly safe support | Existing rehab-only and camp/rehab coexistence tests |
| Zero-load tactical watch + restrictive clearance | Combat-topic wording and a day-level coach contact header cannot turn cognitive work into contact. Start/resume/log only the safe support; held sparring remains outstanding, including after a clearance update | Support start/resume/completion, reversed source order, shadow policy and later clearance regressions; desktop/mobile browser QA |
| Mobility or support with physical demands | Explicitly known non-contact support outside injured regions may remain. Actual injured-region loading, contact metadata, medical restrictions and current red flags still win | Safe/unsafe mobility, misleading mindset label and zero-load red-flag regressions |
| Uncertain support identity or injury location | High-risk session titles veto support; bare mindset labels cannot hide loaded movement names. All active injury regions must be known before projecting physical support; genuinely cognitive blocks keep their separate exemption | High-risk parent, all executable name fields, live reconciliation and unknown-region cognitive/physical regressions |
| Train, no contact | Fresh mixed work keeps safe non-contact blocks; remove/substitute contact children. Contact-owned headings remain held | Existing mixed-session and contact-owned tests |
| No report / stale episode / resolved injury | Existing conservative policy remains. Old or resolved reports grant no permission | Existing clearance episode/setback and baseline tests |
| Malformed scopes | Conservative rehab-only ceiling; never relax baseline restrictions | Existing malformed-scope API/projection tests |
| Multiple injuries | Most restrictive current report wins regardless of order. Each uncleared injury retains its restrictions; any hard second injury wins | Multi-injury ceiling tests; two live clearance and second hard-gate safety cases |
| Rehab due / bundle due | Reviewed bank members only, correct stage, strictest gap; bundle uses one allocation | Bundle, clinical-policy and rehab schedule tests |
| Recovery day / already completed / allocation full / no eligible drill | No duplicate exposure; recovery gap and daily limits remain; full allocation explicitly defers work | Rehab schedule, bundle, multi-injury and real PostgreSQL guard tests |
| No camp / terminal camp / prior standalone rehab completed | Due rehab still owns Today; injury A's completion cannot hide injury B or replace outstanding camp | Multi-injury ownership and next-preview regressions |
| Started/frozen | Accepted session and revision remain unchanged; new clearance/readiness/injury restrictions can hold them | Frozen clearance and readiness tests |
| Done/modified / stopped / skipped / retro log | Accepted ownership remains stable. Explicitly stopping started held work remains loggable; skips and valid retro logs retain their existing contracts | Completion validation, Today/API, multi-injury ownership tests |
| Contact controls and copy | Backend tier/live hold and effective ceiling gate generic/contact actions. Clearance lock outranks check-in wording; no check-in promise can override it | Today panel clearance/status/copy and frozen-readiness frontend tests |

## Contradictions reproduced and corrected

1. Accepted sparring + full clearance + new manageable pain produced pull-back,
   but the frozen projection lacked a hold and the backend accepted Done.
   Current pull-back now holds frozen camp without rewriting its session/revision;
   submissions use the same authoritative tier.
2. A support-session exemption bypassed a current red-flag stop on submission
   when medical review yielded no live prescription. The exemption still permits
   safe support under injury-only restrictions; it no longer bypasses a STOP.
3. A current full-clearance report on a shadow policy had no live prescription,
   allowing Start before check-in. Current clearance execution now requires the
   check-in even on that no-live path.
4. Pull-back with safe non-loading rehab could produce mixed camp + rehab, which
   the UI held as a whole. The existing camp hold/replacement path now offers the
   independently reviewed rehab as its own occurrence. Frozen mixed work is held,
   not rewritten into a different owner.
5. A tactical watch's combat topic and the day's inherited contact header could
   hold zero-load work. Structured cognitive work now remains independently
   actionable. A partial accepted snapshot records held source owners using its
   existing changes field; completion fan-out and Today resolution preserve those
   outstanding owners. A later contact clearance can release the sparring owner
   without relogging the watch. The original day's allocation ceiling is retained.
6. A session labelled rehab could include ordinary camp work yet bypass the
   pull-back projection hold. Only a reviewed rehab-only prescription gets that
   exception. Standalone reviewed rehab receives the existing rehab-only flag;
   the UI tier regression also checks tier authority independently of safety_hold.
7. Cubic's follow-up found the cognitive shortcut could precede the high-risk
   session veto or erase a loaded movement name under a generic mindset label.
   The existing veto now runs first; the generic mindset shortcut rejects loaded
   name tokens. Existing curated tactical/mental categories retain their meaning.
   Physical support projection also requires every active injury region to be
   known; missing canonical locations are not evidence of safe physical loading.

## Authority and duplication

Backend `decision_tier`, effective clinician clearance and live `safety_hold`
remain authoritative. The frontend consumes those facts; it does not calculate
an injury's clinical clearance, stage, reviewed drills or allocation capacity.
Contact detection in the UI resolves timer/session ownership from the plan. The
backend independently checks actual executable contact, including parent/coach
headings and sibling sessions, because client controls cannot validate writes.
The frontend's severe-injury lookup only explains an existing backend hold; it
does not create a second decision tier. No new client safety model was added.

## Validation

- Relevant backend suite: 803 passed (clearance, multi-injury, readiness, Today/API,
  read amplification, bundles, schedules, injury journeys and surface safety).
- The 57 cases in the new audit test file are included in that backend count,
  including ten follow-up cases for Cubic's support classification findings.
- Focused frontend suite: 109 passed, including five frozen-contact tier cases
  and four zero-load watch start/resume cases.
- Desktop/mobile browser QA uses real backend fixture projections and the actual
  Today component: frozen pull-back closes an open completion form; zero-load
  watch stays actionable while the separate sparring owner stays locked.
- Ruff across `api fightcamp tests tools`, Python import/compile checks, TypeScript
  and changed-file ESLint passed.
- Full Python suite intentionally skipped at the user's earlier request.
- Real PostgreSQL and full Web Build verification are recorded in the PR checks.

## Product boundary left unchanged

Legacy logging without a clearance report or live policy can accept completion
without a daily check-in, while Today hides start controls until check-in. Existing
completion tests explicitly preserve that contract. Whether every legacy/manual
completion should require a check-in is a separate product decision; this audit
closes the current injury-clearance execution bypass without changing that wider
logging contract. Valid retro logging remains historical, not today's execution.

Support means the existing low-cost support classifier, not all work labelled
recovery. Injury-only holds may allow it; explicit red flags and current STOP do
not. Modify remains guidance for reduced work rather than silently redosing frozen
accepted content. Both rules use existing semantics and tests.

No migration is required.
