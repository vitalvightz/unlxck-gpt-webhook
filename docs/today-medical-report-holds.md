# Current medical reports in Today

Bare dizziness previously had a symptom label without a concussion diagnosis,
but it also had no execution gate. Other serious intake triage signals were not
consistently projected into Today from mild or monitoring injury reports.

Current affirmative reports of worsening headache, dizziness, numbness, vision
changes or neck pain now impose STOP before support-work and clinician-clearance
exemptions. Body area, label and description are checked, including symptoms
split between fields. Persisted triage categories, injury types, flags and the
canonical neuro consequence also supply the same shared gate. Missing status
is treated conservatively as active; explicitly resolved history is excluded.
The subjective
`training_impact:not_limiting` marker does not release a medical hold.

The existing `injury_triage.py` rules supply the remaining serious gates:
medical-hold routes (including serious eye, cervical/spinal, head and internal
injuries), current neurological and dangerous red flags, urgent fractures and
severe fractures. Dangerous triage flags such as chest pain or shortness of
breath apply to execution even when intake triage lacks its additional context.
Ordinary restricted-rehab and needs-review routes are not globally promoted to
medical holds. Existing loading and injury restrictions continue to govern them.

Negation uses the existing shared injury parser. Resolved flags are excluded.
Bare dizziness retains its symptom label; no concussion diagnosis is inferred.
No clinician scope, impact label or missing daily check-in can override a current
medical gate, including when there is no active plan.

Started prescriptions remain frozen. The current hold prevents start, resume,
done and ordinary modified execution; honest stopped-session logging remains
available. Sparring readiness consumes the same symptom and triage gates, with
the injury label included in its existing snapshot.

No clinical policy content, rehab stages, allocation limits, completion ownership,
database schema or migrations change.

Validation: 1,114 targeted backend tests passed in three runs (657 execution,
triage and surface cases; 255 medical-report/readiness cases, including 115 new
report regressions; 202 ownership, bundle, schedule and failsafe cases). The 61
focused frontend tests cover both tier authority and independent medical holds.
Ruff, compile/import checks, TypeScript and changed-file ESLint passed. Full
Python suite remains skipped at user request; PostgreSQL and Web Build are
verified by the PR checks.
