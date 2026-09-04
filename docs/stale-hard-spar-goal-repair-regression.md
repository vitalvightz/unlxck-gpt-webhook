# Stale hard-spar suppression blocks goal preservation

## Confirmed production failure

A failed generation can resolve declared hard sparring to technical work later in camp while goal-preservation repair still carries the earlier `two_hard_spar_days` suppression.

Observed failed plan state:

- Week 2: Tuesday resolved to `effective_load: technical`; Friday remained hard. Effective hard count = 1.
- Week 3: Tuesday and Friday both resolved to technical. `effective_hard_sparring_days: []`.
- Goal-preservation repair still returned `authority_preserved` with `reason_codes: ["two_hard_spar_days"]` for missing speed/strength coverage.
- Stage 2 then failed with `goal_preservation_failed`.

The retry endpoint already creates a fresh generation job from the canonical request payload, so rerunning the deterministic planner simply reproduces the same invalid schedule while this stale suppression remains.

## Root cause boundary

`fightcamp.goal_preservation._restore_goal_roles()` treats week-level intentional-compression reason codes as immutable repair authority. A stale `two_hard_spar_days` reason therefore blocks candidate restoration even when the resolved sparring-dose plan for that week no longer contains two effective hard contact days.

The contact-dose resolver is authoritative. Goal repair must not treat declared/original hard-spar counts as higher authority after `hard_sparring_plan[].effective_load` has been resolved.

## Required fix

Before goal-preservation repair decides that `two_hard_spar_days` preserves suppression authority:

1. Read the resolved effective hard-spar state for the relevant week.
2. If fewer than two effective hard sparring days remain, remove/ignore the stale `two_hard_spar_days` blocker for goal-repair purposes.
3. Re-run the normal legality/capacity checks for the candidate role.
4. Do not weaken any other compression or safety reason.
5. Do not convert a technical/reduced contact day back to hard.
6. If another live reason still blocks the candidate, preserve that reason normally.

## Acceptance criteria

- Effective hard count >= 2: existing `two_hard_spar_days` behaviour is unchanged.
- Effective hard count = 1: `two_hard_spar_days` alone cannot block goal repair.
- Effective hard count = 0: `two_hard_spar_days` alone cannot block goal repair.
- A week with stale `two_hard_spar_days` plus another live compression reason still remains blocked by the live reason.
- Goal repair still passes through canonical calendar legality and session-cap checks.
- Strength/speed coverage is restored only when a genuinely legal slot exists.
- No Stage 1 fallback is introduced.
- `goal_preservation_failed` remains a hard blocker when the repaired deterministic contract is still unsatisfied.

## Regression tests

Add coverage around `reconcile_goal_preservation()` / `_restore_goal_roles()` proving that a stale `two_hard_spar_days` reason is invalidated by resolved effective contact state, while true two-hard-day weeks and unrelated live compression reasons remain protected.
