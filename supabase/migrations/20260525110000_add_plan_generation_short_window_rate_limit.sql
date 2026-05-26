create table if not exists public.plan_generation_rate_limits (
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now())
);

alter table public.plan_generation_rate_limits enable row level security;

create index if not exists plan_generation_rate_limits_athlete_created_idx
  on public.plan_generation_rate_limits (athlete_id, created_at);

create or replace function public.check_plan_generation_short_window_limit(
  p_athlete_id uuid,
  p_max_requests integer,
  p_window_seconds double precision
)
returns table (allowed boolean, retry_after_seconds integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_now timestamptz := timezone('utc', now());
  v_cutoff timestamptz;
  v_oldest timestamptz;
  v_count integer;
begin
  if p_max_requests <= 0 then
    return query select true, 0;
    return;
  end if;

  v_cutoff := v_now - make_interval(secs => p_window_seconds);

  perform pg_advisory_xact_lock(
    hashtext('plan_generation_rate_limits'),
    hashtext(p_athlete_id::text)
  );

  delete from public.plan_generation_rate_limits
  where athlete_id = p_athlete_id
    and created_at <= v_cutoff;

  select count(*), min(created_at)
  into v_count, v_oldest
  from public.plan_generation_rate_limits
  where athlete_id = p_athlete_id;

  if v_count >= p_max_requests then
    return query
    select
      false,
      greatest(1, ceil(extract(epoch from ((v_oldest + make_interval(secs => p_window_seconds)) - v_now)))::integer);
    return;
  end if;

  insert into public.plan_generation_rate_limits (athlete_id, created_at)
  values (p_athlete_id, v_now);

  return query select true, 0;
end;
$$;

revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from public;
revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from anon;
revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from authenticated;
grant execute on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) to service_role;
