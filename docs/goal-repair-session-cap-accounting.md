# Goal-repair weekly session-cap regression

## Production failure

A dated MMA camp with `weekly_training_frequency=4`, primary goal `speed`, secondary goal `strength`, Tuesday/Friday declared hard sparring, and Wednesday support work still fails after the stale hard-spar fix with:

`goal_preservation_failed: deterministic repair/regeneration required for speed, strength`

The stale `two_hard_spar_days` blocker is no longer the active blocker in resolved Week 2/3. Goal repair now stops on `session_cap` / `calendar_capacity`.

## Confirmed root cause

`fightcamp.goal_preservation._restore_goal_roles()` currently calculates the user's weekly cap with:

```python
total = sum(r.get("category") != "support_insert" for r in roles)
frequency = _number(_athlete(brief).get("training_frequency"))
if current >= original_cap or (frequency and total >= frequency):
    ... calendar_capacity ...
```

This treats every non-`support_insert` role as one full planned training session, even when the resolved role is a filler, zero-cost/support item, recovery/freshness work, or technical-only downgraded contact.

That disagrees with the planner's own resolved role semantics and can make a week appear full or even over-cap before goal repair evaluates whether a legal meaningful goal exposure can fit.

## Required invariant

There must be one canonical definition of whether a resolved role consumes `weekly_training_frequency` capacity. Goal preservation must use that definition rather than `category != "support_insert"`.

At minimum:

- `camp_week_filler == true` does not consume weekly session capacity unless the role independently qualifies as a genuine meaningful training session.
- zero-cost tactical/support inserts do not consume weekly session capacity.
- recovery/freshness-only roles do not consume weekly session capacity.
- technical-only contact that is a resolved downgrade must be counted according to canonical resolved workload/session authority, not stale original role category.
- genuine hard sparring still consumes capacity.
- genuine strength/conditioning sessions still consume capacity.
- goal repair may never use this change to create a fifth genuine session when `weekly_training_frequency=4`.
- all existing calendar, contact-day exclusivity, D-17, taper, late-camp and injury legality checks remain authoritative.

## Acceptance tests

1. Four genuine sessions already present: repair cannot add a fifth genuine session.
2. Filler-only roles do not consume `weekly_training_frequency`.
3. Tactical watch / cue-card / visualization support does not consume `weekly_training_frequency`.
4. Recovery/freshness fillers do not consume `weekly_training_frequency`.
5. A resolved technical-only downgrade does not get blindly counted as a full session solely because its original category is sparring.
6. Genuine hard sparring still consumes capacity.
7. The original failing MMA shape reaches calendar-legality/repair evaluation rather than stopping on a false `session_cap`.
8. If resolved meaningful capacity is genuinely full, suppression remains valid and goal preservation may defer/fail according to the existing contract.

## Non-goals

- Do not weaken goal-preservation validation.
- Do not add Stage 1 fallback.
- Do not ignore the user's weekly session limit.
- Do not make fillers count as planned sessions.
- Do not move goal preservation upstream in this PR.
