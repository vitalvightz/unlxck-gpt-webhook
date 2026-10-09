-- The next-day question is offered on the day after the exposure only, but
-- this read returned the oldest 100 unanswered exposures and left the date
-- filter to the caller. An athlete with 100 expired exposures never saw
-- yesterday's. Window the rows before the limit: two UTC dates either side of
-- the previous training day cover any athlete timezone and the day rollover;
-- the API still applies the exact athlete-local day.
create or replace function public.pending_delayed_rehab(p_athlete_id uuid, p_training_day date)
returns setof public.rehab_exposures language sql security definer
set search_path = public, pg_temp as $$
  select e.* from public.rehab_exposures e
    join public.injury_flags i on i.id = e.injury_id and i.athlete_id = e.athlete_id
    where e.athlete_id = p_athlete_id
      and e.occurred_at::date between p_training_day - 2 and p_training_day
      and coalesce(e.response->>'next_day_response','not_yet_known') = 'not_yet_known'
      and not exists (select 1 from public.injury_episode_events o
         where o.athlete_id = e.athlete_id and o.event_type = 'delayed_rehab_response' and o.payload->>'exposure_id' = e.id::text)
    order by e.occurred_at, e.id limit 100;
$$;
revoke all on function public.pending_delayed_rehab(uuid, date) from public, anon, authenticated;
grant execute on function public.pending_delayed_rehab(uuid, date) to service_role;
