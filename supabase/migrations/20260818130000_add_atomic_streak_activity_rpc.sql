-- Serialize one athlete's insert and aggregate update in the same transaction.
-- The backend resolves p_activity_date from the athlete timezone; clients have
-- no execute grant and cannot supply their own date.
create or replace function public.record_athlete_daily_activity(
  p_athlete_id uuid,
  p_activity_date date
)
returns setof public.athlete_streaks
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_cursor date := p_activity_date;
  v_current integer := 0;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 0));

  insert into public.athlete_daily_activity (athlete_id, activity_date)
  values (p_athlete_id, p_activity_date)
  on conflict (athlete_id, activity_date) do nothing;

  while exists (
    select 1 from public.athlete_daily_activity
    where athlete_id = p_athlete_id and activity_date = v_cursor
  ) loop
    v_current := v_current + 1;
    v_cursor := v_cursor - 1;
  end loop;

  insert into public.athlete_streaks (
    athlete_id, login_current, login_best, login_last_active_date
  ) values (
    p_athlete_id, v_current, v_current, p_activity_date
  )
  on conflict (athlete_id) do update set
    login_current = excluded.login_current,
    login_best = greatest(public.athlete_streaks.login_best, excluded.login_current),
    login_last_active_date = greatest(
      public.athlete_streaks.login_last_active_date,
      excluded.login_last_active_date
    ),
    updated_at = now();

  return query
    select * from public.athlete_streaks where athlete_id = p_athlete_id;
end;
$$;

revoke all on function public.record_athlete_daily_activity(uuid, date) from public;
revoke all on function public.record_athlete_daily_activity(uuid, date) from authenticated;
grant execute on function public.record_athlete_daily_activity(uuid, date) to service_role;
