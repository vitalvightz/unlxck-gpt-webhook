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
and explicit poor-recovery, high-contact-load, aggressive/difficult-cut or
reduced-contact-request signals when supplied. A routine moderate cut alone
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
