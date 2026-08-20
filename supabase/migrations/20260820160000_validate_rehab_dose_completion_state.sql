-- Session completion proves that a rehab exposure occurred, but it does not
-- quantify every drill. Admit an explicit unquantified completion state at the
-- database boundary while retaining every identity, demand and response check
-- from the prior RPC revision.
create or replace function public.record_rehab_exposure(p_athlete_id uuid, p_event jsonb)
returns public.rehab_exposures
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_injury public.injury_flags%rowtype;
  v_existing public.rehab_exposures%rowtype;
  v_result public.rehab_exposures%rowtype;
  v_demand jsonb := p_event->'demand';
  v_completed jsonb := p_event->'dose_completed';
  v_response jsonb := coalesce(p_event->'response', '{}'::jsonb);
  v_side text := p_event->>'side';
  v_region text := p_event->>'body_region';
  v_completion_state text := v_completed->>'completion_state';
  v_key text;
  v_pain jsonb;
begin
  if p_event is null or jsonb_typeof(p_event) <> 'object'
     or jsonb_typeof(v_demand) <> 'object'
     or jsonb_typeof(v_completed) <> 'object'
     or jsonb_typeof(v_response) <> 'object' then
    raise exception 'invalid rehab exposure object' using errcode = '22023';
  end if;

  select * into v_injury from public.injury_flags
   where id = (p_event->>'injury_id')::uuid and athlete_id = p_athlete_id;
  if not found then raise exception 'injury not found' using errcode = '23503'; end if;
  if coalesce(v_side, '') not in ('left','right','bilateral','unknown')
     or v_injury.episode_id <> (p_event->>'injury_episode_id')::uuid
     or v_injury.body_region is null or v_injury.body_region <> v_region
     or v_injury.side = 'unknown' or v_side = 'unknown'
     or not (v_injury.side = v_side or v_injury.side = 'bilateral' or v_side = 'bilateral') then
    raise exception 'exposure does not match injury episode, region and side' using errcode = '23514';
  end if;

  -- Unknown demand remains a valid observation but is never capacity evidence;
  -- RehabExposureEvent.has_unknown_demand keeps it non-qualifying downstream.
  if coalesce(v_demand->>'load','') not in ('unknown','minimal','low','moderate','high')
     or coalesce(v_demand->>'impact','') not in ('unknown','none','low','moderate','high')
     or coalesce(v_demand->>'velocity','') not in ('unknown','low','moderate','high')
     or jsonb_typeof(v_demand->'target_regions') <> 'array'
     or not (v_demand->'target_regions' ? v_region) then
    raise exception 'invalid exposure demand' using errcode = '23514';
  end if;

  if v_completed = '{}'::jsonb or not exists (
    select 1 from jsonb_each(v_completed) item where jsonb_typeof(item.value) <> 'null'
  ) then
    raise exception 'completed dose is empty' using errcode = '23514';
  end if;
  for v_key in select jsonb_object_keys(v_completed) loop
    if v_key not in ('sets','reps','duration_seconds','external_load_kg','distance_metres','hold_seconds','completed_fraction','stopped_early','completion_state') then
      raise exception 'invalid completed dose field' using errcode = '23514';
    end if;
  end loop;
  foreach v_key in array array['sets','reps','duration_seconds','external_load_kg','distance_metres','hold_seconds','completed_fraction'] loop
    if v_completed ? v_key and jsonb_typeof(v_completed->v_key) <> 'null'
       and (jsonb_typeof(v_completed->v_key) <> 'number' or (v_completed->>v_key)::numeric < 0) then
      raise exception 'invalid completed dose value' using errcode = '23514';
    end if;
  end loop;
  if v_completed ? 'completed_fraction' and jsonb_typeof(v_completed->'completed_fraction') <> 'null'
     and (v_completed->>'completed_fraction')::numeric > 1 then
    raise exception 'invalid completed fraction' using errcode = '23514';
  end if;
  if v_completed ? 'stopped_early' and jsonb_typeof(v_completed->'stopped_early') not in ('boolean','null') then
    raise exception 'invalid stopped_early' using errcode = '23514';
  end if;
  if v_completed ? 'completion_state'
     and coalesce(v_completion_state, '') not in ('performed_amount_unknown','partial_amount_unknown','quantified') then
    raise exception 'invalid completion state' using errcode = '23514';
  end if;
  if v_completion_state in ('performed_amount_unknown','partial_amount_unknown') and exists (
    select 1
    from jsonb_each(v_completed) item
    where item.key in ('sets','reps','duration_seconds','external_load_kg','distance_metres','hold_seconds','completed_fraction')
      and jsonb_typeof(item.value) <> 'null'
  ) then
    raise exception 'unquantified completion state contains a measured amount' using errcode = '23514';
  end if;
  if v_completion_state = 'quantified' and not exists (
    select 1
    from jsonb_each(v_completed) item
    where item.key in ('sets','reps','duration_seconds','external_load_kg','distance_metres','hold_seconds','completed_fraction')
      and jsonb_typeof(item.value) = 'number'
  ) then
    raise exception 'quantified completion state lacks a measured amount' using errcode = '23514';
  end if;

  foreach v_key in array array['pain_during','pain_immediate_after'] loop
    v_pain := v_response->v_key;
    if v_pain is not null and jsonb_typeof(v_pain) <> 'null'
       and not (jsonb_typeof(v_pain) = 'string' and v_pain #>> '{}' = 'not_sure')
       and not (jsonb_typeof(v_pain) = 'number' and (v_pain #>> '{}')::numeric between 0 and 10) then
      raise exception 'invalid injury-specific pain response' using errcode = '23514';
    end if;
  end loop;
  if coalesce(v_response->>'next_day_response','not_yet_known') not in ('better','same','worse','not_yet_known','not_sure') then
    raise exception 'invalid next-day response' using errcode = '23514';
  end if;
  if coalesce(v_response->>'during_response','not_reported') not in ('better','same','worse','not_sure','not_reported') then
    raise exception 'invalid during-work response' using errcode = '23514';
  end if;
  foreach v_key in array array['stopped_due_to_symptoms','worsening_reported'] loop
    if v_response ? v_key and jsonb_typeof(v_response->v_key) not in ('boolean','null') then
      raise exception 'invalid response flag' using errcode = '23514';
    end if;
  end loop;

  select * into v_existing from public.rehab_exposures where id = (p_event->>'exposure_id')::uuid;
  if found then
    if v_existing.athlete_id <> p_athlete_id or v_existing.event_json <> p_event then
      raise exception 'exposure id already used with different evidence' using errcode = '23505';
    end if;
    return v_existing;
  end if;

  insert into public.rehab_exposures (
    id, athlete_id, injury_id, injury_episode_id, drill_id, body_region, side,
    demand, prescribed_dose, completed_dose, response, event_json,
    evidence_source, occurred_at, recorded_at
  ) values (
    (p_event->>'exposure_id')::uuid, p_athlete_id, (p_event->>'injury_id')::uuid,
    (p_event->>'injury_episode_id')::uuid, p_event->>'drill_id', v_region, v_side,
    v_demand, p_event->'prescribed_dose', v_completed, v_response, p_event,
    p_event#>>'{provenance,source}', (p_event->>'occurred_at')::timestamptz,
    (p_event#>>'{provenance,recorded_at}')::timestamptz
  ) returning * into v_result;
  return v_result;
end;
$$;

revoke all on function public.record_rehab_exposure(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.record_rehab_exposure(uuid, jsonb) to service_role;
