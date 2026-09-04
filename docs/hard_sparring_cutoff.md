# Hard sparring eligibility

The hard-sparring resolver uses the session's scheduled D-day, not the countdown
when the athlete generated the plan.

- Normal risk: preserve otherwise eligible hard sparring through D-15; convert
  from D-14 onward.
- Elevated risk: convert from D-17 onward.
- Serious contact safety concern or active contact restriction: no contact or
  sparring at any D-day; surface medical evaluation/clearance guidance.
- Existing injury, readiness, contact-density and consecutive-day reductions
  still apply before the cutoff. Calendar eligibility never restores a reduced
  session to hard contact.

This change does not redesign the existing technical/rhythm conversions or
the D-14–D-8 and D-7–D-1 session formats.

`fightcamp/sparring_dose_planner.py` owns the cutoff. Elevated signals include
high fatigue, high cut pressure, moderate/high injury severity or worsening,
and observed poor recovery, high contact load, aggressive/difficult cuts or an
explicit reduced-contact request. `hard_sparring_risk_state()` resolves
`NORMAL`, `ELEVATED` or `CONTACT_BLOCKED` before the cutoff is applied. A routine moderate cut alone
does not select the earlier cutoff. Serious injury parsing uses the existing
negation-aware injury parser and structured injury/restriction data. Restriction
evidence remains authoritative regardless of the countdown or improving symptoms;
this resolver does not issue medical clearance or implement a new clearance store.

The late-window adapter and structured-card renderer consume the same cutoff.
Existing technical/reduced/blocked decisions must not be upgraded during render
or calendar repair. Unresolved weekdays in a dated week crossing the cutoff are
converted conservatively, using the active risk threshold.

Examples for one scheduled weekly hard session:

| State | D-23 | D-16 | D-9 | D-2 |
| --- | --- | --- | --- | --- |
| Normal | Hard eligible | Hard eligible | Existing downgrade | Existing downgrade |
| Elevated | Subject to existing restrictions | Existing downgrade | Existing downgrade | Existing downgrade |
| Serious safety concern | No contact | No contact | No contact | No contact |

D-14 and D-17 are scheduling defaults, not clinically validated safety thresholds.
The [Boxing Science taper article](https://boxingscience.co.uk/tapering-strategies-for-boxing/)
supports a roughly 14-day training taper, not a medically safe final hard-spar date.
The [ARP consensus](https://pmc.ncbi.nlm.nih.gov/articles/PMC6579496/) supports
contact restriction and an appropriate medical return pathway after concussion.

Focused verification: `python -m pytest -q tests/test_dynamic_sparring_cutoff.py
tests/test_sparring_dose_planner.py tests/test_structured_plan_sparring_reconcile.py`.

## Generation-time evidence

The generation worker reads athlete-scoped Today check-ins, session completions
and active injury flags through the existing store. It stamps a dated, ephemeral
`_sparring_readiness` snapshot on the planner payload. `PlanInput` and `TrainingContext` carry it only long enough to derive canonical
readiness/contact flags. The raw seven-day snapshot is not copied into the athlete
model or persisted planning brief. This does not write history back into intake or
change the database schema. Non-health generation
skips these reads. The snapshot is refreshed when generating a plan; this change
does not retroactively edit already-saved plans on every check-in.

Scheduling defaults (not validated medical thresholds):

- Poor recovery: poor sleep or a flat body on at least three distinct days within
  the seven-day window ending on the athlete's current training day.
- High contact load: at least three completed hard-sparring sessions in seven
  days, two in three days, or four sparring/contact sessions in seven days.
- Accumulated fatigue: at least two completed sessions at RPE 8+ in three days,
  or two distinct recent check-in days reporting a very hard previous session.
- Current meaningful pain/worsening and active moderate-or-worse injury flags
  also elevate risk. Stable surface-only injuries retain their existing exception.
- The intake checkbox supplies `reduced_contact_requested` directly. It is saved
  with intake and survives validation, regeneration and draft restoration.

Completion evidence is joined to the exact session ID and date in its owned
structured plan. An unrelated strength session on a sparring day is not contact.
Skipped, unstarted, future and stale rows never count; duplicates are deduplicated.
A modified sparring completion is counted as reduced contact, not confirmed hard
contact. Unlogged external sparring is not inferred from the weekly declaration.
Missing/unreadable completion classification or failed history reads are recorded
as unavailable and select the conservative D-17 cutoff; an empty history is normal.
Active serious injury restrictions remain blocking regardless of their age.

`tests/test_sparring_readiness_boundary.py` covers persisted inputs through the
canonical athlete model and D-16 conversion, including the actual worker hop.
