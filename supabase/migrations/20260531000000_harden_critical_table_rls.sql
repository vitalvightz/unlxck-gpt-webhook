-- Harden critical app tables so authenticated browser clients cannot bypass
-- FastAPI business rules by writing through the Supabase anon client.
-- Service-role backend clients continue to bypass RLS by default.

-- athlete_intakes: keep SELECT policies, remove direct authenticated writes.
drop policy if exists "intakes_self_or_admin_insert" on public.athlete_intakes;
drop policy if exists "intakes_self_or_admin_update" on public.athlete_intakes;
drop policy if exists "intakes_self_or_admin_delete" on public.athlete_intakes;
drop policy if exists "athlete_intakes_self_or_admin_insert" on public.athlete_intakes;
drop policy if exists "athlete_intakes_self_or_admin_update" on public.athlete_intakes;
drop policy if exists "athlete_intakes_self_or_admin_delete" on public.athlete_intakes;

-- plans: keep SELECT policies, remove direct authenticated writes.
drop policy if exists "plans_self_or_admin_insert" on public.plans;
drop policy if exists "plans_self_or_admin_update" on public.plans;
drop policy if exists "plans_self_or_admin_delete" on public.plans;

-- generation_jobs: keep SELECT policies, remove direct authenticated writes.
drop policy if exists "generation_jobs_self_or_admin_insert" on public.generation_jobs;
drop policy if exists "generation_jobs_self_or_admin_update" on public.generation_jobs;
drop policy if exists "generation_jobs_self_or_admin_delete" on public.generation_jobs;
