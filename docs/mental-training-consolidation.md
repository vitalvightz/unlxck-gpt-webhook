# Mental training consolidation — PR #2879

The existing branch was resumed, then merged with Main at `8217cdb7`, including
#2877 (contact visibility), #2878 (conversion performance) and #2880 (coaching
and fidelity). Their implementations remain in place.

## Policy and presentation

The banks and exercise identities are unchanged. Visualise contains Fight and
Neural Visualisation; Analyse contains Tactical Watch/Focus; Reflect contains
Self-Review. The shared governor filters proposed roles without adding work.

- Visualise: at most one per Monday-based calendar week, two for explicit mental priorities.
  Phase/progression rows sharing one calendar week use a single allowance.
- Analyse: at least 14 days apart, seven when explicitly prioritised. The open
  four-week rotation follows the same cadence.
- Reflect: at most one per week, attached to a contact appointment, none in fight week.
- Fight week: only familiar countdown rehearsals, at most one by default or two
  when prioritised, each capped at three minutes and attached to physical work.
- At most one mental task per day. Passive breathing/sleep resets do not make
  an otherwise empty day eligible. Empty and D-0-only generator exits are governed.
- The final weekly-map pass runs after physical movement and session budgets.
  Late-tail ownership is no exemption. All mental identities contribute zero to
  physical frequency and workload.

The compact React card is shared by plan and Today session layouts. Category,
duration and the selected activity’s authored instruction stay visible, shortened
at a sentence or word boundary. The original selected exercise, full bank
instructions and cues sit in a native disclosure. Existing completion
callbacks and exercise controls retain their identities. Contact visibility and
contact timers still use #2877's independent contact field.

## Affected boxer: fdf2fc9d-6e4b-4a54-8e6b-c98fd057169b

Replay uses the existing anonymised production intake, fixed creation time
2026-10-14 03:40 UTC and random seed 1. The before revision is current Main,
which predates the mental consolidation. This is deterministic regeneration and
recorded-response replay, not a write to the athlete's saved production row.

| Measure | Before | After |
| --- | ---: | ---: |
| Mental tasks | 31 | 8 |
| Mental minutes | 330 | 41 |
| Fight Visualisation | 19 | 3 |
| Neural Visualisation | 1 | 0 |
| Tactical Watch | 8 | 2 |
| Self-Review | 3 | 3 |
| Days with stacked mental cards | 6 | 0 |
| Standalone mental-only days | 5 | 0 |
| Physical appointments (canonical classifier) | 44 | 44 |
| Actual hard-sparring appointments visible on the card | 10 | 10 |

After dates: Fight Visualisation D-19, D-7, D-1; Tactical Watch D-45,
D-11; Self-Review D-49, D-35, D-21. These are ceilings, not quotas: no new
assignment is invented to fill an otherwise unused week. The D-1 rehearsal is
three minutes. Self-Review is two minutes.

The earlier “46 physical roles” count included two passive Breathing Resets.
Under the canonical physical-session classifier those count as zero; both
resets remain. All 47 nonmental roles (44 physical, two resets and fight-day
protocol) survive. Only execution-order/session-index numbering closes up where
mental roles were removed; nonmental dates, exercise selections, doses and
coaching are compared separately from those derived indices.

The four originally hidden Saturday hard-sparring appointments D-42, D-35,
D-28 and D-21 remain visible, including when Self-Review shares the day. Full
hard-sparring visibility also includes D-49, D-46, D-39, D-32, D-25 and D-18.
The later technical contact appointments keep their downgraded identity.

## Reproduction and validation

`tools/audit_mental_training.py /tmp/mental-after.json` regenerates the affected
boxer plus boxing, kickboxing, Muay Thai and MMA, each with 49-, 18- and 6-day
camps and explicit mental priority on/off. Run the same script in a clean Main
checkout for the baseline. Outputs contain dates, counts and full physical roles
for comparison; no live database or model is needed. Direct fight-week camps
are measured from the final countdown sequence, rather than the earlier weekly
allocation. The deterministic card fallback now reads that same final sequence
while preserving weekly contact-safety metadata, preventing stale exercise
selections from replacing the actual countdown appointments.

The representative-card tests check schema, exact selected doses, contact
visibility and every scheduled zero-load companion. The production-response
replay checks finalizer reconciliation, persistence/effective fallback, coaching
and retirement of unscheduled mental cards. Negative physical prescription and
missing-exercise controls remain active. The coaching release test no longer
skips direct fight-week cards: the final selected primer receives the same
coaching, fixed-dose and no-progression checks as every other physical row.

Frequency tests change only the retired three-per-week/five-day countdown and
weekly-watch assumptions. Bank content, safety, physical and fidelity
expectations remain intact.

### Independently established baseline failures

Main `8217cdb7` Python Quality run [38640493789](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/38640493789)
failed independently before this branch's changes: 45 distinct failed cases and
13 setup-error cases. Failures include stale historical source hashes for
`api/services/xp_progress.py`, API type-contract drift, old calendar/conditioning
snapshots and incomplete SimpleNamespace fixtures. Physical safety and fidelity
expectations in those tests are not weakened here. The complete inherited test
ID comparison is recorded with the final branch run below. Branch run
[38645063541](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/38645063541)
has exactly the same 45 failed IDs and 13 error IDs; neither set has additions
or omissions. Ruff, runtime surfaces, dependency audit and the coaching release
gate pass.

The original draft's Web Build failed in smoke/accessibility, while current
Main's [38640493836](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/38640493836)
passes after retries: its attempt-1 log contains the same custom-plan Back
navigation failures at `custom-plans.spec.ts:101` (320px and 390px). Branch
[38646910183](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/38646910183)
passes its build/browser job with the same retrying navigation cases and all
1,928 unit tests. Clean Main’s production build and targeted custom-plan cases
also pass locally. The inherited SegmentGroup ARIA annotation was a warning; the invalid
attribute is now attached to the control rather than its group. New renderer
failures from the first branch push were fixed in code: objectives keep their
Why label and mixed mental/physical cards retain the normal presentation.

Local `pytest -n 6` cannot collect the full suite because independently generated
UUID parameter IDs differ between workers in clinical-review/community tests.
This is independently reproduced on clean Main with those two modules and two
workers. GitHub Actions uses file shards and does not have this collection issue.

Focused results: 102 frequency/bank/open-rotation tests; 15 tactical/policy tests;
171 React renderer/Today/mental tests; 13 focused contact/mental interaction tests.
Mobile and desktop Playwright disclosure, keyboard, overflow and Axe checks pass
at 375px and 1280px. A contact-chip contrast fix was included after the actual
rendered audit. The fixture supplies the app's heading hierarchy.

The [PR description](https://github.com/vitalvightz/unlxck-gpt-webhook/pull/2879)
records the final representative matrix and the final CI-to-Main failure-ID
comparison. The replay command above makes the measurements reproducible.
