# Pre-hard-spar strength management

## Contract

- D-14 and farther out remains normal-planner owned. D-13 inward remains the existing late-fight path.
- Final calendar integrity gets first chance to relocate strength away from next-day effective hard contact.
- If no legal ALLOW destination exists and strength remains immediately before effective hard contact, the normal planner keeps at most one meaningful strength exposure.
- The surviving affected role reuses the existing D-17..D-14 strength-retention ceiling; stricter countdown and readiness limits still win.
- A pre-hard session may include at most one additional power/support item, and only when all cost metadata is affirmatively low/none.
- The resolved exercise allow-list is authoritative in both the finalizer and deterministic validator.
- Goal-repair trials re-enter final calendar integrity and the same pre-hard policy, so they cannot restore a suppressed second strength exposure.
- Technical-only contact does not trigger the rule. No two-days-before rule is introduced.

## Ownership

`combat_load_policy` remains the collision authority. `calendar_integrity` remains final placement authority. `pre_hard_contact_strength.py` is a subordinate normal role-budget consequence only; `prescription_resolver.py` owns dose resolution.

## Dense-day redistribution before hard sparring

Within the *existing* weekly appointment budget, an otherwise available
pre-hard-contact day may receive a portion of an overly dense main strength
session. This is not an extra training stimulus and not a blanket permission to
train before hard sparring.

The normal role-budget owner gets a **second, post-composition look** when
the actual main-session density is known. This is essential when a secondary
strength appointment was removed before exercise selection. The candidate
receiver must still be a declared, unoccupied day immediately before resolved
hard contact, within the existing appointment budget, and the athlete must not
have an active injury, high fatigue or significant weight-cut pressure.

The composition owner transfers **two or three** previously selected exercises
from a main session with **at least five** members. The donor retains **at
least three**, including an anchor and a primary-goal witness. Transfers are
not hard-coded to Monday/Saturday; e.g. Wednesday before Thursday hard contact
can also be a receiver. A single exercise is never a valid split.

There is ONE shared eligibility gate, consumed by both composition and
prescription. It measures risk from `impact_cost`, `landing_cost`,
`eccentric_cost`, `soreness_risk`, `movement_cost`, `cns_load`,
`contact_cost` and `lactate_load` (where authored), together with
high-CNS, systemic, and axial-load mechanical tags. Impact and landing must
be **none/low**; eccentric/soreness may be **moderate**, but never high or
unknown; high CNS/movement/systemic cost always vetoes.

A **meaningful_stress** label does not alone reject a *moved, reduced* power
exercise: the explicit cost and resulting dose decide. One non-maximal
anti-rotation strength exercise can move as capped, non-loaded trunk-control
work when its verified movement tags and bank dose permit. This is not
permission to move heavy strength, full jumps, high-impact landings, or
unpriceable isometrics. The receiving session must pass the existing graded
realised-load envelope (systemic <= LOW, neural/mechanical <= MODERATE,
<=24 total reps in the proposed candidate combination). When insufficient
verified exercises exist, the receiver is withdrawn.

The dose owner consumes the exact per-exercise `redistributed_dose_ceiling`
from the already selected bank rep-variant, including bank formats like
`2-4 sets x 6-10 reps or 20-40s tempo`; it never assumes timed seconds
are repetitions. Power stays capped at <=2 sets of <=2 reps, support at <=2
sets of <=6 reps, all at no more than RPE 6.

### Cross-bank tag audit (16 October 2026)

Inspected the **339 exercise**, **239 conditioning**, and **277
style-conditioning** records (855 total), and the shared consumer chain.
This is a metadata/consumer audit, **not** a claim that all records are
eligible strength candidates:

- Six exercise entries have `cns_load=high` without the
  `mech_cns_high` tag. The consumer must consult explicit CNS load.
- 34 exercise entries have `movement_cost=high` while their four
  individual impact/landing/eccentric/soreness fields are not high.
  This separate systemic movement cost must be checked.
- 53 records across the three banks have meaningful stress and low/none
  individual impact/landing/eccentric/soreness values; the actual movement,
  neural and systemic cost can still be substantial.
- Exercise-bank strength prescriptions include both `N x M` and
  `N sets x M reps`, plus time/distance/contrast formats; only
  verified rep-based alternatives may be moved by this narrow rule.
- Conditioning and style-conditioning banks have different cost-field
  coverage and are **not** made eligible for the strength redistribution.
  Rehab and injury-related banks are outside this change.

Real-bank regression tests cover relevant low/moderate-cost movement,
high CNS without a high-CNS tag, high movement cost, impact/landing,
unknown eccentric cost, and non-rep prescriptions. Weekday relocation,
appointment count and source membership conservation have distinct tests.

The **same selected bank assignments** (name, slot ID, phase, instructions)
are removed from the dense appointment and placed in the receiver. The existing
prescription authority limits them to at most two sets and reduces reps by
exercise kind; full loaded strength is prohibited. No new exercise, total weekly
set, or exercise membership is created. Idempotence, strict source conservation,
and an explicit skip reason are regression-tested.

Normal role-budget, hard-contact collision, realisation, injury, weight-cut,
fatigue and fight-week authorities remain unchanged. A recovery-restricted
athlete keeps an off day. This is a conditional redistribution opportunity,
not an obligation to populate every free weekday.
