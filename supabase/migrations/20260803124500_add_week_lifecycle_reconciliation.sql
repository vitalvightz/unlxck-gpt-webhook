-- Durable repair checkpoint for plan lifecycle milestone reconciliation.
--
-- A completed week may already have its weekly XP while phase/plan/camp
-- processing failed later. This table records that lifecycle work is pending
-- until every currently implied milestone has been observed.

create table if not exists public.week_lifecycle_reconciliations (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid not null references public.plans(id) on delete cascade,
  week_id text not null check (
    char_length(btrim(week_id)) between 1 and 160
  ),
  status text not null default 'pending' check (
    status in ('pending', 'completed')
  ),
  attempt_count integer not null default 1 check (
    attempt_count >= 1
  ),
  last_attempt_at timestamptz not null default now(),
  reconciled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (athlete_id, plan_id, week_id),
  check (
    (status = 'pending' and reconciled_at is null)
    or (status = 'completed' and reconciled_at is not null)
  )
);

create index if not exists week_lifecycle_reconciliations_pending_idx
  on public.week_lifecycle_reconciliations (status, last_attempt_at)
  where status = 'pending';

create index if not exists week_lifecycle_reconciliations_athlete_idx
  on public.week_lifecycle_reconciliations (athlete_id, updated_at desc);

alter table public.week_lifecycle_reconciliations enable row level security;

revoke all on table public.week_lifecycle_reconciliations from anon, authenticated;
grant select on table public.week_lifecycle_reconciliations to authenticated;
grant all on table public.week_lifecycle_reconciliations to service_role;

drop policy if exists week_lifecycle_reconciliations_select_own
  on public.week_lifecycle_reconciliations;
create policy week_lifecycle_reconciliations_select_own
  on public.week_lifecycle_reconciliations
  for select
  to authenticated
  using (athlete_id = auth.uid());

create or replace function public.begin_week_lifecycle_reconciliation(
  p_athlete_id uuid,
  p_plan_id uuid,
  p_week_id text
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_week_id text := btrim(coalesce(p_week_id, ''));
  v_row public.week_lifecycle_reconciliations%rowtype;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'begin_week_lifecycle_reconciliation is restricted to the backend service role'
      using errcode = '42501';
  end if;

  if p_athlete_id is null or p_plan_id is null or not exists (
    select 1
    from public.plans
    where id = p_plan_id
      and athlete_id = p_athlete_id
  ) then
    raise exception 'plan not found for athlete' using errcode = '23503';
  end if;

  if char_length(v_week_id) not between 1 and 160 then
    raise exception 'invalid lifecycle week id' using errcode = '22023';
  end if;

  insert into public.week_lifecycle_reconciliations as existing (
    athlete_id,
    plan_id,
    week_id
  ) values (
    p_athlete_id,
    p_plan_id,
    v_week_id
  )
  on conflict (athlete_id, plan_id, week_id) do update
  set
    attempt_count = existing.attempt_count + 1,
    last_attempt_at = clock_timestamp(),
    updated_at = clock_timestamp()
  returning * into v_row;

  return jsonb_strip_nulls(jsonb_build_object(
    'id', v_row.id,
    'athlete_id', v_row.athlete_id,
    'plan_id', v_row.plan_id,
    'week_id', v_row.week_id,
    'status', v_row.status,
    'attempt_count', v_row.attempt_count,
    'last_attempt_at', v_row.last_attempt_at,
    'reconciled_at', v_row.reconciled_at
  ));
end;
$$;

create or replace function public.complete_week_lifecycle_reconciliation(
  p_athlete_id uuid,
  p_plan_id uuid,
  p_week_id text
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_week_id text := btrim(coalesce(p_week_id, ''));
  v_row public.week_lifecycle_reconciliations%rowtype;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'complete_week_lifecycle_reconciliation is restricted to the backend service role'
      using errcode = '42501';
  end if;

  update public.week_lifecycle_reconciliations
  set
    status = 'completed',
    reconciled_at = coalesce(reconciled_at, clock_timestamp()),
    updated_at = clock_timestamp()
  where athlete_id = p_athlete_id
    and plan_id = p_plan_id
    and week_id = v_week_id
  returning * into v_row;

  if v_row.id is null then
    raise exception 'lifecycle reconciliation checkpoint not found'
      using errcode = '23503';
  end if;

  return jsonb_strip_nulls(jsonb_build_object(
    'id', v_row.id,
    'athlete_id', v_row.athlete_id,
    'plan_id', v_row.plan_id,
    'week_id', v_row.week_id,
    'status', v_row.status,
    'attempt_count', v_row.attempt_count,
    'last_attempt_at', v_row.last_attempt_at,
    'reconciled_at', v_row.reconciled_at
  ));
end;
$$;

revoke all on function public.begin_week_lifecycle_reconciliation(
  uuid, uuid, text
) from public, anon, authenticated;
grant execute on function public.begin_week_lifecycle_reconciliation(
  uuid, uuid, text
) to service_role;

revoke all on function public.complete_week_lifecycle_reconciliation(
  uuid, uuid, text
) from public, anon, authenticated;
grant execute on function public.complete_week_lifecycle_reconciliation(
  uuid, uuid, text
) to service_role;
