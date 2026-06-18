-- Block 4 / PR #1800: explicit active-plan pointer on the athlete profile.
--
-- "Multiple plans may exist. Only one plan is active. Overview and Today always
-- read from the active plan. Archived plans are view-only."
--
-- Before this change the "active plan" was implicitly the athlete's latest
-- visible plan, derived independently in several places. This column gives the
-- athlete an explicit, persisted choice that the central resolver
-- (api/active_plan.resolve_active_plan) honours first, falling back to the
-- latest eligible plan only when no explicit choice is set.
--
-- ON DELETE SET NULL means a hard-deleted plan automatically clears the pointer
-- so the resolver never dereferences a missing plan. Archiving is a status
-- change (not a delete), so the application clears the pointer when the active
-- plan is archived; the resolver also rejects an ineligible explicit pointer
-- defensively and falls back.

alter table public.profiles
  add column if not exists active_plan_id uuid
    references public.plans(id) on delete set null;

create index if not exists profiles_active_plan_id_idx
  on public.profiles (active_plan_id);
