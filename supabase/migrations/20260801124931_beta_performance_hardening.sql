-- Beta performance hardening:
-- 1. Return compact generation-job status payloads without large planner blobs.
-- 2. Collapse the worker's three queue scans into one indexed query.
-- 3. Add missing foreign-key indexes and remove a duplicate unique index.
-- 4. Remove duplicate RLS policies and evaluate auth helpers once per statement.

create or replace function public.get_generation_job_status_v2(p_job_id uuid)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select jsonb_strip_nulls(
    jsonb_build_object(
      'id', j.id,
      'athlete_id', j.athlete_id,
      'client_request_id', j.client_request_id,
      'source', j.source,
      'status', j.status,
      'attempt_count', j.attempt_count,
      'created_at', j.created_at,
      'updated_at', j.updated_at,
      'started_at', j.started_at,
      'heartbeat_at', j.heartbeat_at,
      'completed_at', j.completed_at,
      'error', j.error,
      'intake_id', j.intake_id,
      'plan_id', j.plan_id,
      'progress_milestones', coalesce(j.progress_milestones, '[]'::jsonb),
      -- The response mapper only needs to know whether retry data exists.
      'request_payload', case when j.request_payload is null then null else '{}'::jsonb end,
      -- Keep only fields used by athlete-facing status mapping. Exclude plan text
      -- and other large terminal artifacts from routine polling responses.
      'final_result', case
        when j.final_result is null then null
        else jsonb_strip_nulls(
          jsonb_build_object(
            'status', j.final_result -> 'status',
            'stage2_status', j.final_result -> 'stage2_status',
            'why_log', j.final_result -> 'why_log'
          )
        )
      end
    )
  )
  from public.generation_jobs as j
  where j.id = p_job_id
  limit 1;
$$;

create or replace function public.get_visible_active_generation_job_status_v2(p_athlete_id uuid)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select public.get_generation_job_status_v2(j.id)
  from public.generation_jobs as j
  where j.athlete_id = p_athlete_id
    and j.status in ('queued', 'running')
  order by j.created_at desc
  limit 1;
$$;

create or replace function public.get_latest_generation_job_status_v2(p_athlete_id uuid)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select public.get_generation_job_status_v2(j.id)
  from public.generation_jobs as j
  where j.athlete_id = p_athlete_id
  order by j.created_at desc
  limit 1;
$$;

create or replace function public.list_claimable_generation_jobs_v2(
  p_limit integer,
  p_stale_before timestamptz,
  p_include_legacy_blank boolean default false
)
returns table (
  id uuid,
  status text,
  created_at timestamptz,
  started_at timestamptz,
  heartbeat_at timestamptz,
  completed_at timestamptz,
  progress_milestones jsonb
)
language sql
stable
security invoker
set search_path = public
as $$
  select
    j.id,
    j.status,
    j.created_at,
    j.started_at,
    j.heartbeat_at,
    j.completed_at,
    coalesce(j.progress_milestones, '[]'::jsonb) as progress_milestones
  from public.generation_jobs as j
  where
    j.status = 'queued'
    or (
      p_include_legacy_blank
      and coalesce(j.status, '') = ''
    )
    or (
      j.status = 'running'
      and (
        j.heartbeat_at <= p_stale_before
        or (j.heartbeat_at is null and j.started_at <= p_stale_before)
      )
    )
  order by
    case
      when j.status = 'queued' then 0
      when p_include_legacy_blank and coalesce(j.status, '') = '' then 1
      else 2
    end,
    j.created_at asc
  limit least(greatest(coalesce(p_limit, 1), 1), 100);
$$;

revoke all on function public.get_generation_job_status_v2(uuid) from public, anon, authenticated;
revoke all on function public.get_visible_active_generation_job_status_v2(uuid) from public, anon, authenticated;
revoke all on function public.get_latest_generation_job_status_v2(uuid) from public, anon, authenticated;
revoke all on function public.list_claimable_generation_jobs_v2(integer, timestamptz, boolean) from public, anon, authenticated;

grant execute on function public.get_generation_job_status_v2(uuid) to service_role;
grant execute on function public.get_visible_active_generation_job_status_v2(uuid) to service_role;
grant execute on function public.get_latest_generation_job_status_v2(uuid) to service_role;
grant execute on function public.list_claimable_generation_jobs_v2(integer, timestamptz, boolean) to service_role;

-- Cover foreign keys used during joins, deletes and ownership checks.
create index if not exists adaptation_notes_checkin_id_idx on public.adaptation_notes (checkin_id);
create index if not exists adaptation_notes_plan_id_idx on public.adaptation_notes (plan_id);
create index if not exists adaptation_notes_session_log_id_idx on public.adaptation_notes (session_log_id);
create index if not exists admin_reviews_adaptation_note_id_idx on public.admin_reviews (adaptation_note_id);
create index if not exists admin_reviews_injury_flag_id_idx on public.admin_reviews (injury_flag_id);
create index if not exists admin_role_audit_target_athlete_id_idx on public.admin_role_audit (target_athlete_id);
create index if not exists beta_feedback_plan_id_idx on public.beta_feedback (plan_id);
create index if not exists beta_feedback_today_checkin_id_idx on public.beta_feedback (today_checkin_id);
create index if not exists generation_jobs_intake_id_idx on public.generation_jobs (intake_id);
create index if not exists generation_jobs_plan_id_idx on public.generation_jobs (plan_id);
create index if not exists injury_flags_plan_id_idx on public.injury_flags (plan_id);
create index if not exists plans_intake_id_idx on public.plans (intake_id);
create index if not exists session_completions_plan_id_idx on public.session_completions (plan_id);
create index if not exists session_logs_plan_id_idx on public.session_logs (plan_id);
create index if not exists today_checkins_plan_id_idx on public.today_checkins (plan_id);

-- This duplicates the unique constraint-backed index with no additional value.
drop index if exists public.generation_jobs_athlete_client_request_uidx;

-- Remove overlapping permissive policies before optimizing the survivors.
drop policy if exists intakes_self_select on public.athlete_intakes;
drop policy if exists profiles_self_update on public.profiles;

alter policy athlete_intakes_self_or_admin_select on public.athlete_intakes
  using (
    athlete_id = (select auth.uid())
    or (select private.is_admin())
  );

alter policy profiles_self_insert on public.profiles
  with check (
    id = (select auth.uid())
    or (select private.is_admin())
  );

alter policy profiles_self_or_admin_update on public.profiles
  using (
    id = (select auth.uid())
    or (select private.is_admin())
  )
  with check (
    id = (select auth.uid())
    or (select private.is_admin())
  );

alter policy profiles_self_select on public.profiles
  using (id = (select auth.uid()));

alter policy generation_jobs_self_select on public.generation_jobs
  using (athlete_id = (select auth.uid()));

alter policy plans_self_select on public.plans
  using (athlete_id = (select auth.uid()));

alter policy daily_checkins_owner_select on public.daily_checkins
  using (athlete_id = (select auth.uid()));

alter policy session_logs_owner_select on public.session_logs
  using (athlete_id = (select auth.uid()));

alter policy injury_flags_owner_select on public.injury_flags
  using (athlete_id = (select auth.uid()));

alter policy adaptation_notes_owner_select on public.adaptation_notes
  using (athlete_id = (select auth.uid()));

alter policy today_checkins_owner_select on public.today_checkins
  using (athlete_id = (select auth.uid()));

alter policy session_completions_owner_select on public.session_completions
  using (athlete_id = (select auth.uid()));

alter policy push_subscriptions_owner_select on public.push_subscriptions
  using (profile_id = (select auth.uid()));
