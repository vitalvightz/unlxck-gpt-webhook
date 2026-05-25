create table if not exists public.plan_generation_rate_limits (
  athlete_id text not null,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists plan_generation_rate_limits_athlete_created_idx
  on public.plan_generation_rate_limits (athlete_id, created_at);

create or replace function public.check_plan_generation_short_window_limit(
  p_athlete_id text,
  p_max_requests integer,
  p_window_seconds double precision
)
returns table(allowed boolean, retry_after_seconds integer)
language plpgsql
as $$
declare
  v_now timestamptz := timezone('utc', now());
  v_cutoff timestamptz := v_now - make_interval(secs => greatest(1, p_window_seconds)::integer);
  v_count integer := 0;
  v_oldest timestamptz;
begin
  if coalesce(p_max_requests, 0) <= 0 then
    return query select true, 0;
    return;
  end if;

  perform pg_advisory_xact_lock(hashtext('plan_generation_rate_limit:' || p_athlete_id));

  delete from public.plan_generation_rate_limits where created_at <= v_cutoff;

  select count(*), min(created_at)
    into v_count, v_oldest
  from public.plan_generation_rate_limits
  where athlete_id = p_athlete_id
    and created_at > v_cutoff;

  if v_count >= p_max_requests then
    return query
      select false, greatest(1, ceil(extract(epoch from ((v_oldest + make_interval(secs => greatest(1, p_window_seconds)::integer)) - v_now)))::integer);
    return;
  end if;

  insert into public.plan_generation_rate_limits (athlete_id, created_at)
  values (p_athlete_id, v_now);

  return query select true, 0;
end;
$$;
